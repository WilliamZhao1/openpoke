"""Frozen discovery-v2 inputs; generation never reads query judgments."""

from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import random
import re
from uuid import UUID, uuid5

from .contracts import EvaluationConfigError, digest, read_json


DATASET_ROOT = Path(__file__).parent / "datasets" / "discovery_v2"
SIZES = (100, 1000, 10000)
DRAWS = (11, 22, 33)
NAMESPACE = UUID("9bb8f40a-d2d0-49e2-bec9-4c1a02ca6796")
CATEGORIES = ("exact_name", "description", "paraphrase", "same_entity", "period_artifact",
              "dormant", "multiple", "ambiguous", "no_match", "insufficient_metadata")
FILES = ("workers.json", "families.json", "queries.json", "judgments.json", "background.json", "scenario_source.json")
PUBLIC_FIELDS = {"worker_id", "name", "purpose", "recent_assignment", "last_activity"}


def contains_project(text, project):
    return re.search(r"(?<!\w)" + re.escape(project) + r"(?!\w)", text, flags=re.IGNORECASE) is not None


def validate_dataset(data):
    workers, families, queries, judgments = (data[key] for key in ("workers", "families", "queries", "judgments"))
    if (len(workers), len(families), len(queries), len(judgments)) != (100, 20, 200, 200):
        raise EvaluationConfigError("Discovery-v2 requires 100 workers, 20 families and 200 separate queries/judgments")
    ids = [row["worker_id"] for row in workers]
    names = [row["name"] for row in workers]
    if len(set(ids)) != 100 or len(set(names)) != 100:
        raise EvaluationConfigError("Worker identities must be unique")
    for row in workers:
        if set(row) != PUBLIC_FIELDS or not isinstance(row["name"], str) or not 1 <= len(row["name"]) <= 200:
            raise EvaluationConfigError("Worker projection contains unsupported fields or names")
        for field in ("purpose", "recent_assignment"):
            if row[field] is not None and (not isinstance(row[field], str) or len(row[field]) > 240):
                raise EvaluationConfigError("Metadata exceeds the production field bound")
        if row["last_activity"] is not None and datetime.fromisoformat(row["last_activity"]).utcoffset() is None:
            raise EvaluationConfigError("Activity requires an explicit timezone")
    by_family = {row["id"]: row for row in families}
    membership = [worker for family in families for worker in family["worker_ids"]]
    if len(by_family) != 20 or Counter(membership) != Counter(ids) or any(len(row["worker_ids"]) != 5 for row in families):
        raise EvaluationConfigError("Workers must belong to exactly one five-worker family")
    if len({row["domain"] for row in families}) < 15:
        raise EvaluationConfigError("Dataset needs at least 15 domains")
    if Counter(row["split"] for row in families) != {"development": 5, "evaluation": 15}:
        raise EvaluationConfigError("Family split must be five development and fifteen evaluation families")
    labels = {row["id"]: row for row in judgments}
    query_ids = [row["id"] for row in queries]
    if len(labels) != 200 or len(set(query_ids)) != 200 or set(labels) != set(query_ids):
        raise EvaluationConfigError("Queries and judgments must join one to one")
    if len({row["query"].casefold() for row in queries}) != 200:
        raise EvaluationConfigError("Duplicate query wording")
    targets = set()
    for query in queries:
        family = by_family.get(query["family_id"])
        label = labels[query["id"]]
        if (set(query) != {"id", "family_id", "split", "category", "answerability", "query"}
                or family is None or query["split"] != family["split"]
                or query["category"] not in CATEGORIES or not 1 <= len(query["query"]) <= 256):
            raise EvaluationConfigError("Invalid public query or family split")
        relevant = label["relevant_worker_ids"]
        category = query["category"]
        expected_kind = category if category in {"multiple", "ambiguous"} else "none" if category == "no_match" else "single"
        expected_answerability = "insufficient_metadata" if category == "insufficient_metadata" else "ambiguous" if category == "ambiguous" else "answerable"
        expected_count = 0 if expected_kind == "none" else 2 if expected_kind in {"multiple", "ambiguous"} else 1
        if (set(label) != {"id", "kind", "relevant_worker_ids", "rationale"} or label["kind"] != expected_kind
                or query["answerability"] != expected_answerability or len(set(relevant)) != expected_count
                or len(relevant) != expected_count or not set(relevant).issubset(family["worker_ids"])
                or not isinstance(label["rationale"], str) or not label["rationale"]):
            raise EvaluationConfigError("Invalid relevance judgment")
        if category != "insufficient_metadata" and not contains_project(query["query"], family["project"]):
            raise EvaluationConfigError("Judged request must identify the protected base project")
        if category == "exact_name" and query["query"] not in names:
            raise EvaluationConfigError("Exact-name case does not name an original worker")
        targets.update(relevant)
    if targets != set(ids) or Counter(row["split"] for row in queries) != {"development": 50, "evaluation": 150}:
        raise EvaluationConfigError("Split counts or owner coverage changed")
    for family in families:
        categories = [row["category"] for row in queries if row["family_id"] == family["id"]]
        if Counter(categories) != Counter(CATEGORIES):
            raise EvaluationConfigError("Each family must contain all ten request categories")
    # A lexical target inferred solely from private tokens would be a fixture leak.
    searchable = "\n".join(str(row[field] or "") for row in workers for field in ("name", "purpose", "recent_assignment")).casefold()
    for query in queries:
        if query["category"] == "insufficient_metadata":
            token = query["query"].rstrip("?.").split()[-1].casefold()
            if token in searchable:
                raise EvaluationConfigError("Private diagnostic reference leaked into searchable metadata")


def load_dataset(directory=DATASET_ROOT):
    directory = Path(directory)
    manifest = read_json(directory / "manifest.json")
    if (manifest.get("profile") != "discovery_quality_v2" or manifest.get("schema_version") != 2
            or set(manifest.get("file_sha256_canonical", {})) != set(FILES)):
        raise EvaluationConfigError("Unsupported discovery dataset manifest")
    data = {Path(name).stem: read_json(directory / name) for name in FILES}
    if any(digest(data[Path(name).stem]) != manifest["file_sha256_canonical"][name] for name in FILES):
        raise EvaluationConfigError("Frozen discovery dataset content changed")
    data["manifest"] = manifest
    validate_dataset(data)
    return data


def generate_workers(data, size, draw):
    """Only worker/family/vocabulary inputs influence generated worker metadata."""
    if type(size) is not int or size not in SIZES or type(draw) is not int or draw not in DRAWS:
        raise EvaluationConfigError("Discovery-v2 supports sizes 100/1000/10000 and draws 11/22/33")
    workers = deepcopy(data["workers"])
    if size == 100:
        return workers
    rng = random.Random(draw)
    vocabulary = data["background"]
    core = {row["worker_id"]: row for row in workers}
    base_clock = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
    protected = [row["project"].casefold() for row in data["families"]]
    for index in range(size - 100):
        family = rng.choice(data["families"])
        person = rng.choice(vocabulary["given_names"]) + " " + rng.choice(vocabulary["surnames"])
        scope = f'{rng.choice(vocabulary["project_adjectives"])} {rng.choice(vocabulary["project_nouns"])} {index:05d}'
        close = index % 10 < 3
        if close:
            original = core[rng.choice(family["worker_ids"])]
            organization = family["organization"]
            replace = lambda text: text.replace(family["project"], scope).replace("2026", "2024").replace("2027", "2025")
            title = replace(original["name"])
            purpose = replace(original["purpose"] or original["recent_assignment"])
            assignment = f"{person} continues this separate project: {scope}."
        else:
            organization = rng.choice(vocabulary["organization_starts"]) + " " + rng.choice(vocabulary["organization_ends"])
            task, detail = rng.choice(vocabulary["activities"])
            title = rng.choice((f"{organization} / {scope}: {task}", f"{task} — {scope}", f"{scope} ({organization})", f"{person}: {task} / {scope}"))
            purpose = rng.choice((f"{detail} for {organization}, project {scope}.", f"For {scope} at {organization}, {detail[0].lower() + detail[1:]}.",
                                  f"{person} owns {scope} at {organization}: {detail[0].lower() + detail[1:]}."))
            assignment = rng.choice((f"{person} is collecting the next decisions for {scope}.", f"Follow up with {person} on {organization} {scope}.",
                                     f"Earlier notes for {scope} retained; next check with {person}.", f"Confirm open questions and dates on {scope}."))
        if any(contains_project(title + " " + purpose + " " + assignment, project) for project in protected):
            raise EvaluationConfigError("Generated project overlaps a protected judged project")
        if len(title) > 200 or len(purpose) > 240 or len(assignment) > 240:
            raise EvaluationConfigError("Generated worker exceeds production bounds")
        workers.append({"worker_id": str(uuid5(NAMESPACE, f"draw:{draw}:worker:{index}")), "name": title,
                        "purpose": purpose if index % 17 else None, "recent_assignment": assignment if index % 13 else None,
                        "last_activity": (base_clock - timedelta(days=rng.randrange(1460), minutes=index)).isoformat() if index % 19 else None})
    if len({row["name"] for row in workers}) != size or len({row["worker_id"] for row in workers}) != size:
        raise EvaluationConfigError("Generated worker identities collide")
    return workers


def build_snapshot(data, size, draw):
    workers = generate_workers(data, size, draw)
    key = "100:base" if size == 100 else f"{size}:{draw}"
    if digest(workers) != data["manifest"]["catalog_sha256"].get(key):
        raise EvaluationConfigError("Generated catalog differs from its frozen fingerprint")
    return workers


def search_projection(workers):
    """Strip identities and every judgment/intent annotation before ranking."""
    names = [row["name"] for row in workers]
    metadata = {row["name"]: {key: row[key] for key in ("purpose", "recent_assignment", "last_activity")} for row in workers}
    return names, metadata
