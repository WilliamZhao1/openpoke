"""Frozen synthetic catalog experiment. Does not import application runtime code."""

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import re
from statistics import mean, median
import sys
from time import perf_counter

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
MODEL = "sentence-transformers/all-MiniLM-L6-v2"
REVISION = "c9745ed1d9f207416be6d2e6f8de32d1f16199bf"
NEO4J_VERSION = "5.26.0"
INDEX = "poc_worker_vectors"
METHODS = ("flat", "ann", "community")
PARAMETERS = {"neighbors": 10, "seed": 42, "resolution": 1, "communities": 2, "top_k": 5}
REPRESENTATIVE_POLICY = "centroid_plus_two_farthest_v1"
SOURCES = ("server/tests/fixtures/catalogs.py", "server/tests/fixtures/catalog.json")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def source_hashes():
    return {name: hashlib.sha256((ROOT / name).read_text(encoding="utf-8")
                                .replace("\r\n", "\n").encode()).hexdigest() for name in SOURCES}


def public_catalog():
    # Import the pure fixture file directly: importing server would start the app.
    spec = importlib.util.spec_from_file_location("poc_frozen_catalogs", ROOT / SOURCES[0])
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    return [{"name": row["display_name"], "purpose": row["purpose"][:240],
             "recent_assignment": row["card"]["summary"][:240]} for row in fixture.build_catalog(1000)]


def normalize(vectors):
    vectors = np.asarray(vectors, dtype=np.float64)
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    if not np.isfinite(vectors).all() or (norms <= 1e-12).any():
        raise ValueError("Vectors must be finite and have nonzero norm")
    return (vectors / norms).astype(np.float32)


def check_vectors(vectors, count, dimensions):
    vectors = np.asarray(vectors, dtype=np.float32)
    if (vectors.shape != (count, dimensions) or not np.isfinite(vectors).all()
            or not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)):
        raise ValueError("Invalid embedding shape, values, or normalization; rebuild the snapshot")
    return vectors


def rank(names, vectors, query):
    if len(names) != len(set(names)):
        raise ValueError("Candidate names must be unique exact names")
    scores = np.asarray(vectors, dtype=np.float64) @ np.asarray(query, dtype=np.float64)
    order = sorted(range(len(names)), key=lambda i: (-float(scores[i]), names[i]))[:5]
    return [{"name": names[i], "score": float(scores[i])} for i in order]


def select_communities(communities, query, count):
    if count < 1:
        raise ValueError("Community count must be positive")
    scores = [float(np.max(np.asarray(c.get("representatives", [c["centroid"]]), dtype=np.float64)
                           @ np.asarray(query, dtype=np.float64))) for c in communities]
    order = sorted(range(len(communities)), key=lambda i: (-float(scores[i]), communities[i]["id"]))
    return [{"id": communities[i]["id"], "size": communities[i]["size"], "score": float(scores[i])}
            for i in order[:min(count, len(order))]]


def route(communities, query, count, fetch_members, worker_count):
    selected = select_communities(communities, query, count)
    members = fetch_members([c["id"] for c in selected])
    names = [m["name"] for m in members]
    if not members or len(names) != len(set(names)) or len(members) != sum(c["size"] for c in selected):
        raise ValueError("Membership union disagrees with selected sizes or contains duplicate names")
    dimensions = len(query)
    vectors = check_vectors([m["embedding"] for m in members], len(members), dimensions)
    representative_count = sum(len(c.get("representatives", [c["centroid"]])) for c in communities)
    return {"top5": rank(names, vectors, query), "selected_communities": selected,
            "candidate_count": len(members), "candidate_fraction": len(members) / worker_count,
            "representative_comparisons": representative_count, "worker_comparisons": len(members),
            "total_explicit_comparisons": representative_count + len(members),
            "covers_entire_catalog": len(members) == worker_count, "direct": False}


def diverse_representatives(centroid, members):
    """Centroid plus two label-free, farthest-first member exemplars."""
    members = sorted(members, key=lambda member: member["name"])
    names = [m["name"] for m in members]
    if not names or len(names) != len(set(names)):
        raise ValueError("Representative construction needs nonempty, unique members")
    vectors = check_vectors([m["embedding"] for m in members], len(members), len(centroid))
    matrix = vectors.astype(np.float64)
    closest_similarity = matrix @ np.asarray(centroid, dtype=np.float64)
    representatives, representative_names, selected = [list(centroid)], [None], set()
    comparisons = len(members)
    for step in range(min(2, len(members))):
        i = min((i for i in range(len(names)) if i not in selected),
                key=lambda i: (float(closest_similarity[i]), names[i]))
        selected.add(i)
        representatives.append(vectors[i].tolist())
        representative_names.append(names[i])
        if step == 0 and len(members) > 1:
            closest_similarity = np.maximum(closest_similarity, matrix @ matrix[i])
            comparisons += len(members)
    return representatives, representative_names, comparisons


def prepare_representatives(session, manifest, communities, snapshot, count):
    if count == 1:
        return communities, {"policy": "centroid", "maximum_per_community": 1,
                             "total_representatives": len(communities), "cache_reused": None}
    if count != 3:
        raise ValueError("Supported representative counts are one or three")
    started = perf_counter()
    cache_path = snapshot / "representatives-3.json"
    identity = {"schema": 1, "policy": REPRESENTATIVE_POLICY, "snapshot_id": manifest["snapshot_id"]}
    reused = cache_path.exists()
    if reused:
        payload = read_json(cache_path)
        if (any(payload.get(key) != value for key, value in identity.items())
                or payload.get("fingerprint") != digest({k: v for k, v in payload.items() if k != "fingerprint"})):
            raise ValueError("Representative cache fingerprint mismatch; remove the derived cache to regenerate it")
    else:
        # One offline setup pass; no query text or relevance judgments enter selection.
        rows = db_rows(session, """MATCH (w:PoCWorker {snapshot: $snapshot})-[:MEMBER_OF]->
            (c:PoCCommunity {snapshot: $snapshot}) RETURN c.id AS community,
            w.name AS name, w.embedding AS embedding ORDER BY c.id, w.name""",
            snapshot=manifest["snapshot_id"])
        if len(rows) != manifest["worker_count"] or len({r["name"] for r in rows}) != len(rows):
            raise ValueError("Invalid member union while preparing representatives")
        groups = {c["id"]: [] for c in communities}
        for row in rows:
            groups[row["community"]].append({"name": row["name"], "embedding": row["embedding"]})
        enriched, build_comparisons = [], 0
        for community in communities:
            members = groups[community["id"]]
            if len(members) != community["size"]:
                raise ValueError("Representative input membership count mismatch")
            representatives, names, comparisons = diverse_representatives(community["centroid"], members)
            enriched.append({**community, "representatives": representatives, "representative_names": names})
            build_comparisons += comparisons
        payload = {**identity, "communities": enriched, "member_input_sha256": digest(rows),
                   "build_explicit_comparisons": build_comparisons,
                   "build_ms": (perf_counter() - started) * 1000}
        payload["fingerprint"] = digest(payload)
        write_json(cache_path, payload)
    enriched = payload["communities"]
    if len(enriched) != len(communities):
        raise ValueError("Representative cache community count mismatch")
    for actual, base in zip(enriched, communities):
        if any(actual.get(key) != base[key] for key in ("id", "size", "centroid")):
            raise ValueError("Representative cache does not match the frozen communities")
        names, representatives = actual["representative_names"], actual["representatives"]
        if (len(representatives) != 1 + min(2, base["size"]) or len(names) != len(representatives)
                or names[0] is not None or len(set(names[1:])) != len(names[1:])
                or any(not isinstance(name, str) or not name for name in names[1:])
                or representatives[0] != base["centroid"]):
            raise ValueError("Invalid cached representatives")
        check_vectors(representatives, len(representatives), manifest["dimensions"])
    return enriched, {"policy": REPRESENTATIVE_POLICY, "maximum_per_community": 3,
                      "total_representatives": sum(len(c["representatives"]) for c in enriched),
                      "cache_reused": reused, "cache_sha256": file_digest(cache_path),
                      "cache_fingerprint": payload["fingerprint"], "build_ms": payload["build_ms"],
                      "build_explicit_comparisons": payload["build_explicit_comparisons"],
                      "load_or_build_ms": (perf_counter() - started) * 1000}


def make_graph(names, vectors):
    import networkx as nx

    started = perf_counter()
    similarities = np.asarray(vectors, dtype=np.float64) @ np.asarray(vectors, dtype=np.float64).T
    graph = nx.Graph()
    graph.add_nodes_from(range(len(names)))  # Includes workers with no positive neighbors.
    for i in range(len(names)):
        order = sorted((j for j in range(len(names)) if i != j and similarities[i, j] > 0),
                       key=lambda j: (-float(similarities[i, j]), names[j]))[:10]
        for j in order:
            graph.add_edge(min(i, j), max(i, j), weight=float(similarities[i, j]))
    pairwise_ms = (perf_counter() - started) * 1000
    started = perf_counter()
    groups = (nx.community.louvain_communities(graph, seed=42, resolution=1)
              if graph.number_of_edges() else [{i} for i in graph])
    groups = sorted((sorted(group) for group in groups), key=lambda g: min(names[i] for i in g))
    if sorted(i for group in groups for i in group) != list(range(len(names))):
        raise ValueError("Louvain did not assign every worker exactly once")
    communities, membership = [], {}
    for index, group in enumerate(groups):
        identifier = f"community-{index:03d}"
        centroid = normalize(np.mean(vectors[group].astype(np.float64), axis=0))
        communities.append({"id": identifier, "size": len(group), "centroid": centroid.tolist()})
        membership.update({i: identifier for i in group})
    check_vectors([c["centroid"] for c in communities], len(communities), vectors.shape[1])
    edges = [{"left": names[i], "right": names[j], "score": data["weight"]}
             for i, j, data in sorted(graph.edges(data=True))]
    return communities, membership, edges, {"pairwise_graph_ms": pairwise_ms,
                                           "louvain_centroids_ms": (perf_counter() - started) * 1000}


def load_model(snapshot, revision, offline):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL, revision=revision, device="cpu", trust_remote_code=False,
                               cache_folder=str(snapshot / "model-cache"), local_files_only=offline)


def connect(args):
    from neo4j import GraphDatabase

    password = os.environ.get("POC_NEO4J_PASSWORD")
    if not password:
        raise ValueError("Set POC_NEO4J_PASSWORD for the dedicated disposable Neo4j instance")
    driver = GraphDatabase.driver(args.uri, auth=(args.user, password), connection_timeout=10,
                                  max_transaction_retry_time=0)
    try:
        driver.verify_connectivity()
        with driver.session(database=args.database) as session:
            info = session.run("CALL dbms.components() YIELD versions RETURN versions[0] AS version").single()
            if info["version"] != NEO4J_VERSION:
                raise ValueError(f"This experiment requires Neo4j {NEO4J_VERSION}; found {info['version']}")
    except Exception:
        driver.close()
        raise
    return driver


def db_rows(session, query, **parameters):
    return [record.data() for record in session.run(query, **parameters)]


def validate_database(session, manifest, communities):
    snapshot_id = manifest["snapshot_id"]
    counts = session.run("""
        MATCH (w:PoCWorker)
        OPTIONAL MATCH (w)-[m:MEMBER_OF]->(c:PoCCommunity)
        WITH w, count(m) AS degree, collect(c.snapshot) AS snapshots
        RETURN count(w) AS workers,
               sum(CASE WHEN w.snapshot = $snapshot AND degree = 1 AND snapshots = [$snapshot]
                        THEN 0 ELSE 1 END) AS invalid
        """, snapshot=snapshot_id).single()
    actual = db_rows(session, """
        MATCH (c:PoCCommunity) OPTIONAL MATCH (w:PoCWorker)-[:MEMBER_OF]->(c)
        RETURN c.id AS id, c.size AS size, c.snapshot AS snapshot, count(w) AS members ORDER BY id
        """)
    expected = [{"id": c["id"], "size": c["size"], "snapshot": snapshot_id, "members": c["size"]}
                for c in sorted(communities, key=lambda c: c["id"])]
    edges = session.run("MATCH (:PoCWorker)-[r:SIMILAR_TO]->(:PoCWorker) RETURN count(r) AS n").single()["n"]
    if counts["workers"] != manifest["worker_count"] or counts["invalid"] or actual != expected or edges != manifest["edge_count"]:
        raise ValueError("Database does not match this snapshot; explicitly rebuild the dedicated PoC data")
    session.run("CALL db.awaitIndex($name, 120)", name=INDEX).consume()


def store_graph(session, manifest, catalog, vectors, communities, membership, edges):
    session.run(f"DROP INDEX {INDEX} IF EXISTS").consume()
    session.run("CREATE CONSTRAINT poc_worker_name IF NOT EXISTS FOR (w:PoCWorker) REQUIRE w.name IS UNIQUE").consume()
    session.run("CREATE CONSTRAINT poc_community_id IF NOT EXISTS FOR (c:PoCCommunity) REQUIRE c.id IS UNIQUE").consume()
    workers = [{"name": row["name"], "profile": "\n".join(row.values()), "embedding": vectors[i].tolist(),
                "community": membership[i]} for i, row in enumerate(catalog)]

    def replace(tx):
        # Only reserved PoC labels are touched; application stores are never imported.
        tx.run("MATCH (n) WHERE n:PoCWorker OR n:PoCCommunity DETACH DELETE n").consume()
        tx.run("""UNWIND $rows AS row CREATE (:PoCCommunity {
            id: row.id, size: row.size, centroid: row.centroid, snapshot: $snapshot})""",
               rows=communities, snapshot=manifest["snapshot_id"]).consume()
        tx.run("""UNWIND $rows AS row MATCH (c:PoCCommunity {id: row.community})
            CREATE (w:PoCWorker {name: row.name, profile: row.profile,
                embedding: row.embedding, snapshot: $snapshot}) CREATE (w)-[:MEMBER_OF]->(c)""",
               rows=workers, snapshot=manifest["snapshot_id"]).consume()
        tx.run("""UNWIND $rows AS row MATCH (a:PoCWorker {name: row.left}), (b:PoCWorker {name: row.right})
            CREATE (a)-[:SIMILAR_TO {score: row.score}]->(b)""", rows=edges).consume()

    session.execute_write(replace)
    session.run(f"""CREATE VECTOR INDEX {INDEX} FOR (w:PoCWorker) ON w.embedding
        OPTIONS {{indexConfig: {{`vector.dimensions`: {manifest['dimensions']},
                  `vector.similarity_function`: 'cosine'}}}}""").consume()
    validate_database(session, manifest, communities)


def check_output(path):
    path = path.resolve()
    for forbidden in (ROOT / "server" / "data", ROOT / "data"):
        if path == forbidden or forbidden in path.parents:
            raise ValueError("Experiment output must be separate from application data")
    return path


def load_snapshot(path, *, workers=False):
    manifest = read_json(path / "manifest.json")
    if (manifest.get("schema") != 1 or manifest.get("status") != "ready"
            or manifest["model"] != MODEL or manifest["parameters"] != PARAMETERS
            or manifest["sources"] != source_hashes()):
        raise ValueError("Snapshot metadata or catalog sources changed; use build --rebuild")
    filenames = ["communities.json"] + (["catalog.json", "vectors.npy"] if workers else [])
    for name in filenames:
        if file_digest(path / name) != manifest["files"][name]:
            raise ValueError(f"Snapshot cache fingerprint mismatch: {name}; use build --rebuild")
    communities = read_json(path / "communities.json")
    if (len({c["id"] for c in communities}) != len(communities) or not communities
            or any(type(c["size"]) is not int or c["size"] < 1 for c in communities)
            or sum(c["size"] for c in communities) != manifest["worker_count"]):
        raise ValueError("Invalid cached community partition")
    check_vectors([c["centroid"] for c in communities], len(communities), manifest["dimensions"])
    catalog, vectors = None, None
    if workers:
        catalog = read_json(path / "catalog.json")
        if digest(catalog) != manifest["catalog_sha256"] or len({r["name"] for r in catalog}) != manifest["worker_count"]:
            raise ValueError("Cached catalog fingerprint/count mismatch")
        vectors = check_vectors(np.load(path / "vectors.npy", allow_pickle=False),
                                manifest["worker_count"], manifest["dimensions"])
    return manifest, communities, catalog, vectors


def build(args):
    started = perf_counter()
    path = check_output(args.output)
    catalog = public_catalog()
    if not re.fullmatch(r"[0-9a-f]{40}", args.model_revision):
        raise ValueError("--model-revision must be an immutable 40-character model commit SHA")
    if len({row["name"] for row in catalog}) != 1000:
        raise ValueError("Frozen catalog must contain 1,000 unique exact names")
    if path.exists() and any(path.iterdir()):
        if not (path / "manifest.json").exists():
            raise ValueError("Output is nonempty and is not a PoC snapshot; choose a new directory")
        previous = read_json(path / "manifest.json")
        if previous.get("schema") != 1 or previous.get("model") != MODEL:
            raise ValueError("Output is not a recognized PoC snapshot")
        if not args.rebuild:
            manifest, communities, _, _ = load_snapshot(path, workers=True)
            if manifest["catalog_sha256"] != digest(catalog) or manifest["model_revision"] != args.model_revision:
                raise ValueError("Catalog/model fingerprint changed; use build --rebuild")
            with connect(args) as driver, driver.session(database=args.database) as session:
                validate_database(session, manifest, communities)
            print(json.dumps({"cache_reused": True, "manifest": manifest}, indent=2))
            return
    path.mkdir(parents=True, exist_ok=True)
    with connect(args) as driver, driver.session(database=args.database) as session:
        present = session.run("MATCH (n) WHERE n:PoCWorker OR n:PoCCommunity RETURN count(n) AS n").single()["n"]
        if present and not args.rebuild:
            raise ValueError("Dedicated database already contains PoC data; use --rebuild explicitly")
        manifest = {"schema": 1, "status": "building", "model": MODEL, "model_revision": args.model_revision,
                    "catalog_sha256": digest(catalog), "sources": source_hashes(), "parameters": PARAMETERS,
                    "worker_count": 1000, "created_at": datetime.now(timezone.utc).isoformat(),
                    "neo4j_version": NEO4J_VERSION,
                    "versions": {p: version(p) for p in ("numpy", "networkx", "sentence-transformers", "neo4j",
                                                          "torch", "transformers", "huggingface-hub")},
                    "python": platform.python_version(), "platform": platform.platform()}
        write_json(path / "manifest.json", manifest)
        tick = perf_counter()
        model = load_model(path, args.model_revision, offline=False)
        timings = {"model_setup_ms": (perf_counter() - tick) * 1000}
        tick = perf_counter()
        vectors = normalize(model.encode(["\n".join(row.values()) for row in catalog],
                                          normalize_embeddings=True, show_progress_bar=True))
        check_vectors(vectors, 1000, vectors.shape[1])
        timings["catalog_embedding_ms"] = (perf_counter() - tick) * 1000
        names = [row["name"] for row in catalog]
        communities, membership, edges, graph_timings = make_graph(names, vectors)
        timings.update(graph_timings)
        write_json(path / "catalog.json", catalog)
        np.save(path / "vectors.npy", vectors, allow_pickle=False)
        write_json(path / "communities.json", communities)
        manifest.update(dimensions=vectors.shape[1], edge_count=len(edges),
                        community_sizes={c["id"]: c["size"] for c in communities},
                        files={name: file_digest(path / name) for name in ("catalog.json", "vectors.npy", "communities.json")})
        manifest["snapshot_id"] = digest({key: manifest[key] for key in
            ("model", "model_revision", "catalog_sha256", "parameters", "files")})
        tick = perf_counter()
        store_graph(session, manifest, catalog, vectors, communities, membership, edges)
        timings["database_write_index_validation_ms"] = (perf_counter() - tick) * 1000
        timings["total_build_ms"] = (perf_counter() - started) * 1000
        manifest.update(status="ready", build_ms=timings)
        write_json(path / "manifest.json", manifest)
    print(json.dumps({"cache_reused": False, "manifest": manifest}, indent=2))


def direct_lookup(session, snapshot_id, query):
    rows = db_rows(session, "MATCH (w:PoCWorker {name: $name, snapshot: $snapshot}) RETURN w.name AS name",
                   name=query, snapshot=snapshot_id)
    if not rows:
        return None
    return {"top5": [{"name": rows[0]["name"], "score": None}], "direct": True,
            "selected_communities": [], "candidate_count": 1, "candidate_fraction": 0.001,
            "representative_comparisons": 0, "worker_comparisons": 0,
            "total_explicit_comparisons": 0, "covers_entire_catalog": False}


def lookup(method, session, manifest, communities, query, vector, catalog=None, vectors=None, count=2):
    direct = direct_lookup(session, manifest["snapshot_id"], query)
    if direct:
        return direct
    if method == "community":
        def fetch(identifiers):
            return db_rows(session, """UNWIND $ids AS id MATCH (c:PoCCommunity {id: id, snapshot: $snapshot})
                <-[:MEMBER_OF]-(w:PoCWorker {snapshot: $snapshot})
                RETURN w.name AS name, w.embedding AS embedding ORDER BY name""",
                ids=identifiers, snapshot=manifest["snapshot_id"])
        return route(communities, vector, count, fetch, manifest["worker_count"])
    if method == "flat":
        return {"top5": rank([r["name"] for r in catalog], vectors, vector), "direct": False,
                "selected_communities": [], "candidate_count": len(catalog), "candidate_fraction": 1.0,
                "representative_comparisons": 0, "worker_comparisons": len(catalog),
                "total_explicit_comparisons": len(catalog), "covers_entire_catalog": True}
    if method != "ann":
        raise ValueError(f"Unknown method {method}")
    matches = db_rows(session, f"""CALL db.index.vector.queryNodes('{INDEX}', 5, $vector)
        YIELD node, score RETURN node.name AS name, node.snapshot AS snapshot, score
        ORDER BY score DESC, name ASC""", vector=vector.tolist())
    if len(matches) != 5 or len({r["name"] for r in matches}) != 5 or any(r["snapshot"] != manifest["snapshot_id"] for r in matches):
        raise ValueError("ANN index returned missing, duplicate, or foreign-snapshot workers")
    return {"top5": [{"name": r["name"], "score": 2 * r["score"] - 1} for r in matches],
            "direct": False, "selected_communities": [], "candidate_count": None, "candidate_fraction": None,
            "representative_comparisons": 0, "worker_comparisons": None,
            "total_explicit_comparisons": None, "covers_entire_catalog": None,
            "ann_internal_comparisons": "unknown", "score_source": "2 * Neo4j cosine score - 1"}


def query(args):
    path = args.snapshot.resolve()
    manifest, communities, _, _ = load_snapshot(path)
    with connect(args) as driver, driver.session(database=args.database) as session:
        validate_database(session, manifest, communities)
        started = perf_counter()
        result = direct_lookup(session, manifest["snapshot_id"], args.query)
        if result:
            result.update(embedding_ms=0.0, lookup_ms=(perf_counter() - started) * 1000)
        else:
            communities, representative_setup = prepare_representatives(
                session, manifest, communities, path, args.representatives)
            model = load_model(path, manifest["model_revision"], offline=True)
            tick = perf_counter()
            vector = normalize(model.encode(args.query, normalize_embeddings=True))
            embedding_ms = (perf_counter() - tick) * 1000
            tick = perf_counter()
            result = lookup("community", session, manifest, communities, args.query, vector, count=args.communities)
            result.update(embedding_ms=embedding_ms, lookup_ms=(perf_counter() - tick) * 1000,
                          representative_setup=representative_setup)
    result.update(query=args.query, requested_communities=args.communities, snapshot_id=manifest["snapshot_id"],
                  timing_scope="lookup excludes model/cache/connection validation and query embedding")
    print(json.dumps(result, indent=2, ensure_ascii=False))


def p95(values):
    return sorted(values)[math.ceil(0.95 * len(values)) - 1] if values else None


def summarize(rows):
    groups = []
    for split in ("development", "evaluation"):
        cases = [r for r in rows if r["split"] == split]
        for method in METHODS:
            samples = [sample for row in cases for sample in row["methods"][method]]
            failures = sum(sample["failure"] is not None for sample in samples)
            qualities = [row["methods"][method][0] for row in cases if row["relevant_names"]]
            times = [s["lookup_ms"] for s in samples if s["failure"] is None]
            effort = [row["methods"][method][0]["total_explicit_comparisons"] for row in cases
                      if not row["direct"] and row["methods"][method][0]["failure"] is None]
            fractions = [row["methods"][method][0]["candidate_fraction"] for row in cases
                         if not row["direct"] and row["methods"][method][0]["failure"] is None]
            complete = not failures
            groups.append({"split": split, "method": method, "cases": len(cases), "quality_cases": len(qualities),
                           "timing_samples": len(times), "failed_samples": failures, "complete": complete,
                           "owner_recall_at_5": mean(q["owner_recall_at_5"] for q in qualities) if complete and qualities else None,
                           "vector_recall_at_5": mean(q["vector_recall_at_5"] for q in qualities)
                           if complete and qualities and all(q["vector_recall_at_5"] is not None for q in qualities) else None,
                           "lookup_median_ms": median(times) if times else None, "lookup_p95_ms": p95(times),
                           "non_direct_median_explicit_comparisons": median(effort)
                           if complete and effort and all(e is not None for e in effort) else None,
                           "non_direct_median_candidate_fraction": median(fractions)
                           if complete and fractions and all(f is not None for f in fractions) else None})
    flat = next(g for g in groups if g["split"] == "evaluation" and g["method"] == "flat")
    routed = next(g for g in groups if g["split"] == "evaluation" and g["method"] == "community")
    measurable = all(g["complete"] and g["owner_recall_at_5"] is not None for g in (flat, routed))
    effort_ok = routed["non_direct_median_explicit_comparisons"] <= 500 if measurable else None
    recall_ok = routed["owner_recall_at_5"] >= flat["owner_recall_at_5"] - 0.05 - 1e-12 if measurable else None
    return groups, {"measurable": measurable, "median_comparisons_at_most_500": effort_ok,
                    "owner_recall_within_5_percentage_points": recall_ok,
                    "both_targets_met": effort_ok and recall_ok if measurable else None,
                    "scope": "non-direct evaluation effort; nonempty relevant-owner cases; demo targets only"}


def current_demo_targets(rows, worker_count):
    evaluation = [r for r in rows if r["split"] == "evaluation" and r["relevant_names"]]
    complete = bool(evaluation) and all(sample["failure"] is None for row in rows
                                      for samples in row["methods"].values() for sample in samples)
    result = {"measurable": complete, "maximum_absolute_recall_gap": 0.03,
              "comparison_fraction_exclusive": 1 / 3,
              "scope": "mean evaluation owner recall; every non-direct sample including routing overhead; no latency gate"}
    if not complete:
        return {**result, "both_targets_met": None}
    flat = mean(r["methods"]["flat"][0]["owner_recall_at_5"] for r in evaluation)
    routed = mean(r["methods"]["community"][0]["owner_recall_at_5"] for r in evaluation)
    non_direct = [sample for row in rows if not row["direct"] for sample in row["methods"]["community"]]
    maximum = max((s["total_explicit_comparisons"] for s in non_direct), default=None)
    recall_ok = abs(routed - flat) <= 0.03 + 1e-12
    effort_ok = maximum < worker_count / 3 if maximum is not None else False
    return {**result, "flat_owner_recall_at_5": flat, "community_owner_recall_at_5": routed,
            "absolute_recall_gap": abs(routed - flat), "recall_within_3_percentage_points": recall_ok,
            "max_explicit_comparisons": maximum, "max_comparison_fraction": maximum / worker_count if maximum is not None else None,
            "every_non_direct_sample_below_one_third": effort_ok, "both_targets_met": recall_ok and effort_ok}


def render_report(result):
    def number(value):
        return "unknown" if value is None else f"{value:.4f}"

    lines = ["# Frozen community catalog PoC", "", f"Run status: **{result['status']}**.", "",
             "Authored synthetic retrieval judgments at 1,000 workers; no live agent, dispatch, Gmail, or production quality evidence.",
             f"Run settings: ten positive neighbors, Louvain seed 42 / resolution 1, top {result['settings']['communities']} communities, "
             f"up to {result['settings']['representatives']} representatives per community, top five workers.",
             f"Query evidence scope: {result['evaluation_scope']}. {result['query_provenance']}",
             "Cases retain their authored splits. No tuning or parameter sweep within this run. Exact-name rows bypass embedding and routing.", "",
             "| Split | Method | Owner recall@5 | Vector recall@5 | Quality cases | Failed samples | Median / p95 ms | Median explicit comparisons (non-direct) | Median candidate fraction (non-direct) |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for g in result["summary"]:
        lines.append(f"| {g['split']} | {g['method']} | {number(g['owner_recall_at_5'])} | {number(g['vector_recall_at_5'])} | "
                     f"{g['quality_cases']} | {g['failed_samples']} | {number(g['lookup_median_ms'])} / {number(g['lookup_p95_ms'])} | "
                     f"{number(g['non_direct_median_explicit_comparisons'])} | {number(g['non_direct_median_candidate_fraction'])} |")
    lines += ["", "Original-plan targets (retained for comparison):", "", "```json", json.dumps(result["targets"], indent=2), "```", "",
              "Current user-requested demo targets (three percentage points / fewer than one third of comparisons per request):", "",
              "```json", json.dumps(result["demo_targets"], indent=2), "```", "",
              "Each case has three timed repetitions in rotating method order, not three quality examples. Quality uses the first repetition; all outputs and any variation are retained in results.json. "
              "Recall excludes both no-match cases. Failed samples remain recorded; affected quality aggregates and targets are unavailable. Any timing from an incomplete run is partial.",
              "Warm lookup includes the common exact-name DB probe and method-specific fetches/scoring, and excludes shared embedding and setup. "
              "Median/p95 use only three samples per case and a small authored sample overall. ANN internal comparisons and candidate fraction are unknown. "
              "Neo4j ANN scores are converted from [0,1] to cosine; tie ordering is deterministic within its approximate returned set.", "",
              "Embedding and offline build times (ms; first build can include model download):", "", "```json",
              json.dumps({"embedding_ms": {r["case_id"]: r["embedding_ms"] for r in result["rows"]},
                          "build_ms": result.get("manifest", {}).get("build_ms"),
                          "evaluation_setup_ms": result.get("setup_ms"),
                          "representative_setup": result.get("representative_setup")}, indent=2), "```", "",
              "Per-case first-repetition results (exact names; misses are judged owners):", "",
              "| Case / split | Method | Direct | Selected groups (size) | Candidates / representatives / total comparisons | Owner / vector recall@5 | Top names | Misses / failure |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in result["rows"]:
        for method in METHODS:
            sample = row["methods"][method][0]
            if sample["failure"]:
                lines.append(f"| {row['case_id']} / {row['split']} | {method} | {row['direct']} | unknown | unknown | unknown | — | {sample['failure']} |")
                continue
            selected = ", ".join(f"{c['id']} ({c['size']})" for c in sample["selected_communities"]) or "—"
            names = "; ".join(r["name"] for r in sample["top5"])
            misses = "; ".join(sample["misses"]) or "—"
            effort = " / ".join(str(sample[k]) for k in ("candidate_count", "representative_comparisons", "total_explicit_comparisons"))
            lines.append(f"| {row['case_id']} / {row['split']} | {method} | {row['direct']} | {selected} | {effort} | "
                         f"{number(sample['owner_recall_at_5'])} / {number(sample['vector_recall_at_5'])} | {names} | {misses} |")
    lines += ["", "No-match rows are qualitative diagnostics: this experiment always retrieves candidates and has no semantic abstention policy. "
              "Subset routing can exclude relevant owners; widen manually. Searching every community performs representatives plus the full worker scan. "
              "The quadratic frozen build, cached warm timings, and synthetic sample establish neither scalable ingestion nor lower application cost/latency. "
              "Do not compare these timings directly with historical fresh-JSON lookup measurements. A poor flat baseline remains poor even when routing preserves its recall.", ""]
    if result.get("setup_failure"):
        lines += [f"Setup failure: {result['setup_failure']}", ""]
    return "\n".join(lines)


def evaluate(args):
    output = check_output(args.output)
    output.mkdir(parents=True, exist_ok=False)
    fixture = read_json(args.queries)
    cases = fixture["cases"]
    rows = [{**{k: case[k] for k in ("split", "kind", "query", "relevant_names")}, "case_id": case["id"],
             "direct": None, "embedding_ms": None, "methods": {m: [] for m in METHODS}} for case in cases]
    result = {"status": "incomplete", "created_at": datetime.now(timezone.utc).isoformat(), "rows": rows,
              "query_fixture_sha256": digest(fixture), "query_provenance": fixture["provenance"],
              "settings": {**PARAMETERS, "communities": args.communities, "representatives": args.representatives},
              "repetitions": 3, "quality_repetition": 0,
              "evaluation_scope": fixture.get("evaluation_scope", "repeat_on_existing_authored_queries_not_independent_holdout"),
              "implementation_sha256": file_digest(Path(__file__)), "setup_failure": None}
    started = perf_counter()
    driver = None
    try:
        path = args.snapshot.resolve()
        manifest, communities, catalog, vectors = load_snapshot(path, workers=True)
        result["manifest"] = manifest
        result["routing_width"] = {"requested": args.communities, "effective": min(args.communities, len(communities)),
                                   "original_snapshot_setting": manifest["parameters"]["communities"]}
        if any(not set(case["relevant_names"]).issubset(r["name"] for r in catalog) for case in cases):
            raise ValueError("Query judgments reference missing workers")
        driver = connect(args)
        with driver.session(database=args.database) as session:
            validate_database(session, manifest, communities)
            communities, representative_setup = prepare_representatives(
                session, manifest, communities, path, args.representatives)
            result["representative_setup"] = representative_setup
            if args.representatives == 3:
                (output / "representatives.json").write_bytes((path / "representatives-3.json").read_bytes())
            model = load_model(path, manifest["model_revision"], offline=True)
            model.encode("warm up", normalize_embeddings=True)
            encoded = {}
            for row in rows:
                try:
                    row["direct"] = direct_lookup(session, manifest["snapshot_id"], row["query"]) is not None
                    tick = perf_counter()
                    encoded[row["case_id"]] = (None if row["direct"] else normalize(model.encode(row["query"], normalize_embeddings=True)))
                    row["embedding_ms"] = 0.0 if row["direct"] else (perf_counter() - tick) * 1000
                except Exception as exc:
                    row["preparation_failure"] = f"{type(exc).__name__}: {exc}"
            warm = next(r for r in rows if r["case_id"] in encoded and not r["direct"])
            for method in METHODS:
                lookup(method, session, manifest, communities, warm["query"], encoded[warm["case_id"]],
                       catalog, vectors, count=args.communities)
            result["setup_ms"] = (perf_counter() - started) * 1000
            for index, row in enumerate(rows):
                for repetition in range(3):
                    offset = (index + repetition) % len(METHODS)
                    for method in METHODS[offset:] + METHODS[:offset]:
                        try:
                            if row.get("preparation_failure"):
                                raise ValueError(row["preparation_failure"])
                            tick = perf_counter()
                            sample = lookup(method, session, manifest, communities, row["query"],
                                            encoded[row["case_id"]], catalog, vectors, count=args.communities)
                            sample.update(lookup_ms=(perf_counter() - tick) * 1000, failure=None)
                        except Exception as exc:
                            sample = {"failure": f"{type(exc).__name__}: {exc}", "lookup_ms": None}
                        row["methods"][method].append(sample)
    except Exception as exc:
        result["setup_failure"] = f"{type(exc).__name__}: {exc}"
    finally:
        if driver is not None:
            driver.close()
    for row in rows:
        for method in METHODS:
            while len(row["methods"][method]) < 3:
                row["methods"][method].append({"failure": result["setup_failure"] or "Run interrupted", "lookup_ms": None})
        reference = row["methods"]["flat"][0]
        reference_names = {r["name"] for r in reference.get("top5", [])}
        for method in METHODS:
            for sample in row["methods"][method]:
                if sample["failure"]:
                    continue
                names = {r["name"] for r in sample["top5"]}
                relevant = set(row["relevant_names"])
                sample.update(misses=sorted(relevant - names),
                              owner_recall_at_5=len(names & relevant) / len(relevant) if relevant else None,
                              vector_recall_at_5=len(names & reference_names) / len(reference_names)
                              if relevant and reference_names else None)
    result["summary"], result["targets"] = summarize(rows)
    result["demo_targets"] = current_demo_targets(rows, result.get("manifest", {}).get("worker_count", 1000))
    result["status"] = "complete" if all(g["complete"] for g in result["summary"]) else "incomplete"
    write_json(output / "results.json", result)
    (output / "report.md").write_text(render_report(result), encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(output), "targets": result["targets"],
                      "demo_targets": result["demo_targets"]}, indent=2))
    return 0 if result["status"] == "complete" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "query", "evaluate"):
        command = subparsers.add_parser(name)
        command.add_argument("--uri", default=os.environ.get("POC_NEO4J_URI", "bolt://127.0.0.1:17687"))
        command.add_argument("--user", default=os.environ.get("POC_NEO4J_USER", "neo4j"))
        command.add_argument("--database", default=os.environ.get("POC_NEO4J_DATABASE", "neo4j"))
        if name == "build":
            command.add_argument("--output", type=Path, required=True)
            command.add_argument("--rebuild", action="store_true", help="Explicit full rebuild of reserved PoC data")
            command.add_argument("--model-revision", default=REVISION)
        else:
            command.add_argument("--snapshot", type=Path, required=True)
            command.add_argument("--representatives", type=int, choices=(1, 3), default=1,
                                 help="One centroid, or centroid plus two diverse cached member vectors")
        if name == "query":
            command.add_argument("--query", required=True)
            command.add_argument("--communities", type=int, default=2)
        if name == "evaluate":
            command.add_argument("--output", type=Path, required=True)
            command.add_argument("--queries", type=Path,
                                 default=ROOT / "evals" / "agent_overload" / "ranking_queries.json")
            command.add_argument("--communities", type=int, default=PARAMETERS["communities"],
                                 help="Query-time routing width; reuses the unchanged frozen snapshot")
    args = parser.parse_args()
    try:
        if args.command in ("query", "evaluate") and args.communities < 1:
            raise ValueError("Use a positive community count")
        if args.command == "query" and not args.query.strip():
            raise ValueError("Use a nonempty query and a positive community count")
        return {"build": build, "query": query, "evaluate": evaluate}[args.command](args) or 0
    except Exception as exc:
        print(f"ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
