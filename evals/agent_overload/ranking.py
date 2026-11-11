"""Offline ranker comparison using production discovery and frozen catalog inputs."""

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from statistics import mean, median
from time import perf_counter
import tracemalloc

from .contracts import EvaluationConfigError, HERE, ROOT, digest, read_json
from .engine import write_json
from server.data_paths import get_data_dir
from server.services.execution.discovery import LOOKUP_CHAR_BUDGET, atomic_json, find_workers
from server.services.execution.ranking import SearchCatalog, get_ranker, rank_workers, ranker_parameters
from server.services.execution.roster import AgentRoster
from server.tests.fixtures.catalogs import build_catalog, load_fixture


def percentile95(values):
    return sorted(values)[max(0, math.ceil(0.95 * len(values)) - 1)] if values else None


def grade_ranking(names, packed_names, relevant_names, kind):
    relevant = set(relevant_names)
    ranks = [index + 1 for index, name in enumerate(names) if name in relevant]
    return {"top1_correct": bool(names and names[0] in relevant) if kind == "single" else None,
            "recall_at_5": len(set(names[:5]) & relevant) / len(relevant) if relevant else None,
            "reciprocal_rank": 1 / min(ranks) if ranks else 0.0 if relevant else None,
            "packed_recall": len(set(packed_names) & relevant) / len(relevant) if relevant else None,
            "no_match_false_positive": bool(packed_names) if kind == "none" else None}


def summarize_rankings(rows):
    groups = []
    for size, split, identifier in sorted({(row["catalog_size"], row["split"], row["ranker"]) for row in rows}):
        group = [row for row in rows if (row["catalog_size"], row["split"], row["ranker"]) == (size, split, identifier)]
        good = [row for row in group if row["failure"] is None]
        metrics = {}
        for metric in ("top1_correct", "recall_at_5", "reciprocal_rank", "packed_recall", "no_match_false_positive"):
            values = [row["metrics"][metric] for row in good if row["metrics"][metric] is not None]
            metrics[metric] = {"value": mean(values) if values else None, "cases": len(values)}
        lookup = [value for row in good for value in row["lookup_ms"]]
        ranking = [value for row in good for value in row["ranking_ms"]]
        groups.append({"catalog_size": size, "split": split, "ranker": identifier, "cases": len(group),
                       "failures": len(group) - len(good), "metrics": metrics,
                       "lookup_median_ms": median(lookup) if lookup else None, "lookup_p95_ms": percentile95(lookup),
                       "ranking_median_ms": median(ranking) if ranking else None, "ranking_p95_ms": percentile95(ranking)})
    return groups


def promotion_eligibility(groups, identifiers):
    by_id = {group["ranker"]: group for group in groups if group["catalog_size"] == 10000 and group["split"] == "evaluation"}
    baseline = by_id.get("heuristic_v1")
    decisions = {}
    for identifier in identifiers:
        candidate = by_id.get(identifier)
        if identifier == "heuristic_v1":
            decisions[identifier] = {"offline_eligible": None, "reason": "retained_baseline"}
        elif baseline is None or candidate is None:
            decisions[identifier] = {"offline_eligible": None, "reason": "requires_10000_worker_evaluation_and_baseline"}
        else:
            original = {key: metric["value"] for key, metric in baseline["metrics"].items()}
            changed = {key: metric["value"] for key, metric in candidate["metrics"].items()}
            quality = ("top1_correct", "recall_at_5", "reciprocal_rank", "packed_recall")
            evaluation = [group for group in groups if group["split"] == "evaluation"]
            paired = [(base, next((group for group in evaluation if group["ranker"] == identifier
                       and group["catalog_size"] == base["catalog_size"]), None))
                      for base in evaluation if base["ranker"] == "heuristic_v1"]
            no_recall_regression = all(other is not None and base["failures"] == other["failures"] == 0
                and all(base["metrics"][key]["value"] is not None and other["metrics"][key]["value"] is not None
                        and other["metrics"][key]["value"] >= base["metrics"][key]["value"] for key in ("recall_at_5", "packed_recall"))
                and other["metrics"]["no_match_false_positive"]["value"] <= base["metrics"]["no_match_false_positive"]["value"]
                for base, other in paired)
            eligible = (no_recall_regression and baseline["failures"] == candidate["failures"] == 0
                        and all(original[key] is not None and changed[key] is not None for key in original)
                        and any(changed[key] > original[key] for key in quality)
                        and candidate["lookup_median_ms"] <= 2 * baseline["lookup_median_ms"])
            decisions[identifier] = {"offline_eligible": eligible, "reason": "predeclared_quality_and_latency_gate",
                                     "promotion": "requires_separate_live_agent_evidence"}
    return decisions


def run_ranking_comparison(manifest, sizes, output, data_root, *, identifiers, repeats=3):
    if get_data_dir() != data_root.resolve():
        raise EvaluationConfigError("Ranking comparison requires disposable stores")
    fixture = read_json(HERE / "ranking_queries.json")
    cases = fixture["cases"]
    checksums = load_fixture("checksums.json")
    if checksums != manifest["fixture_checksums"]:
        raise EvaluationConfigError("Frozen catalog checksums changed")
    # Public query inputs and grading judgments are saved separately. Neither
    # labels nor fixture-only state/resource fields enter a SearchCatalog.
    write_json(output / "queries.json", [{key: case[key] for key in ("id", "query", "split")} for case in cases])
    write_json(output / "relevance.json", fixture)
    public = {"profile": "worker_ranking_v1", "decision_mode": "local", "model_calls": 0, "rankers": identifiers,
              "parameters": {identifier: ranker_parameters(get_ranker(identifier)) for identifier in identifiers},
              "catalog_sizes": sizes, "repeats": repeats, "query_sha256": digest(fixture),
              "metadata": "name,purpose[:240],recent_assignment[:240],last_activity; no gold labels",
              "latency": "local timings include no tracing; lookup includes JSON reads, preparation, scoring and packing",
              "memory": "separate tracemalloc preparation peak; Python allocations only, not process RSS",
              "default_ranker": "heuristic_v1", "defaults_promoted": False}
    write_json(output / "comparison.json", public)
    rows, preparation = [], []
    for size in sizes:
        source = build_catalog(size)
        if digest(source) != checksums["catalogs"][str(size)]:
            raise EvaluationConfigError("Frozen generated catalog changed")
        names = [row["display_name"] for row in source]
        metadata = {row["display_name"]: {"purpose": row["purpose"][:240], "recent_assignment": row["card"]["summary"][:240],
                    "last_activity": row["last_activity_at"]} for row in source}
        write_json(output / f"catalog-{size}.json", {"names": names, "metadata": metadata})
        roster = AgentRoster(data_root / f"ranking-{size}" / "roster.json")
        atomic_json(roster._roster_path, names)
        atomic_json(roster.metadata_path, metadata)
        started = perf_counter()
        catalog = SearchCatalog.build(names, metadata)
        elapsed = (perf_counter() - started) * 1000
        tracemalloc.start()
        try:
            measured = SearchCatalog.build(names, metadata)
            peak = tracemalloc.get_traced_memory()[1]
            del measured
        finally:
            tracemalloc.stop()
        preparation.append({"catalog_size": size, "preparation_ms": elapsed, "preparation_peak_python_bytes": peak})
        for index, case in enumerate(cases):
            relevant = case["relevant_names"] if size else []
            kind = case["kind"] if size else "none"
            if size and not set(relevant).issubset(names):
                raise EvaluationConfigError("Relevance judgment selects a nonexistent worker")
            # Rotate first method to reduce a fixed execution-order advantage.
            order = identifiers[index % len(identifiers):] + identifiers[:index % len(identifiers)]
            for identifier in order:
                row = {"case_id": case["id"], "split": case["split"], "kind": kind, "catalog_size": size,
                       "ranker": identifier, "failure": None, "ranking_ms": [], "lookup_ms": []}
                try:
                    ranker = get_ranker(identifier)
                    for _ in range(repeats):
                        started = perf_counter()
                        ranked = rank_workers(ranker, case["query"], catalog)
                        row["ranking_ms"].append((perf_counter() - started) * 1000)
                        started = perf_counter()
                        packed = find_workers(roster, case["query"], ranker=ranker)
                        row["lookup_ms"].append((perf_counter() - started) * 1000)
                        if len(json.dumps(packed)) > LOOKUP_CHAR_BUDGET:
                            raise AssertionError("Production lookup exceeded its response budget")
                    ranked_names = [match.name for match in ranked]
                    row.update(total_matches=len(ranked), top_matches=[asdict(match) for match in ranked[:5]], packed=packed,
                               relevant_ranks={name: ranked_names.index(name) + 1 if name in ranked_names else None for name in relevant},
                               metrics=grade_ranking(ranked_names, [card["agent_name"] for card in packed["workers"]], relevant, kind))
                except Exception as exc:
                    row["failure"] = type(exc).__name__
                rows.append(row)
                write_json(output / "results.json", rows)
    groups = summarize_rankings(rows)
    summary = {"profile": public["profile"], "checks_passed": all(row["failure"] is None for row in rows),
               "case_context_count": len(rows), "routing_quality": "unavailable_no_model_decisions",
               "defaults_promoted": False, "preparation": preparation, "groups": groups,
               "eligibility": promotion_eligibility(groups, identifiers)}
    write_json(output / "summary.json", summary)
    sources = ("server/services/execution/ranking.py", "server/services/execution/discovery.py", "server/config.py",
               "evals/agent_overload/ranking.py", "evals/agent_overload/ranking_queries.json", "evals/agent_overload/run.py")
    write_json(output / "provenance.json", {"created_at": datetime.now(timezone.utc).isoformat(),
               "fixture_checksums": checksums, "source_sha256_lf_normalized": {
                   path: hashlib.sha256((ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n").encode()).hexdigest() for path in sources}})
    lines = ["# Local worker ranking comparison", "", "Authored synthetic retrieval judgments; no model or Gmail calls. "
             "Passing checks indicate the comparison ran, not that a new default is justified.", "",
             "| Workers | Split | Ranker | Top-1 | Recall@5 | MRR | Packed recall | No-match FP | Lookup median / p95 ms |",
             "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    def number(value):
        return "unavailable" if value is None else f"{value:.3f}"
    for group in groups:
        values = [number(group["metrics"][key]["value"]) for key in ("top1_correct", "recall_at_5", "reciprocal_rank", "packed_recall", "no_match_false_positive")]
        lines.append(f'| {group["catalog_size"]} | {group["split"]} | {group["ranker"]} | ' + " | ".join(values)
                     + f' | {number(group["lookup_median_ms"])} / {number(group["lookup_p95_ms"])} |')
    lines += ["", "Eligibility under the predeclared offline gate:", "", "```json", json.dumps(summary["eligibility"], indent=2), "```", "",
              "Timing is local and noisy; preprocessing memory excludes native allocations. Scores are not confidence. "
              "See summary.json for denominators/failures, results.json for disagreements and scores, and provenance.json for source hashes. "
              "Agent decisions and effects need a separate fixed-strategy comparison. Production remains heuristic_v1.", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    write_json(output / "artifacts.json", {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(output.iterdir()) if path.is_file()})
    return summary
