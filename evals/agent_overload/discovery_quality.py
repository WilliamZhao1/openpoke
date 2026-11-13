"""Discovery-v2 measurement through the existing production ranking/packing APIs."""

from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
from math import ceil
from pathlib import Path
import platform
import random
from statistics import mean, median
from time import perf_counter
import tracemalloc

from .contracts import EvaluationConfigError, ROOT, digest
from .discovery_dataset import FILES, DATASET_ROOT, build_snapshot, load_dataset, search_projection
from .engine import write_json
from .ranking import grade_ranking, percentile95
from server.data_paths import get_data_dir
from server.services.execution.discovery import LOOKUP_CHAR_BUDGET, find_workers
from server.services.execution.ranking import SearchCatalog, get_ranker, rank_workers, ranker_parameters
from server.services.execution.roster import AgentRoster
from server.services.execution.discovery import atomic_json


METRICS = ("top1_correct", "recall_at_5", "reciprocal_rank", "packed_recall", "all_owners_at_5",
           "all_owners_packed", "precision_at_5", "packed_precision", "no_match_false_positive", "irrelevant_packed_count")


def grade_case(names, packed_names, relevant_names, kind, answerability):
    relevant = set(relevant_names)
    metrics = grade_ranking(names, packed_names, relevant_names, kind)
    metrics.update(all_owners_at_5=relevant.issubset(names[:5]) if relevant else None,
                   all_owners_packed=relevant.issubset(packed_names) if relevant else None,
                   precision_at_5=len(set(names[:5]) & relevant) / len(names[:5]) if relevant and names else 0.0 if relevant else None,
                   packed_precision=len(set(packed_names) & relevant) / len(packed_names) if relevant and packed_names else 0.0 if relevant else None,
                   irrelevant_packed_count=len(set(packed_names) - relevant))
    if answerability == "insufficient_metadata":
        return {key: None for key in METRICS}, metrics
    return metrics, None


def query_values(rows, metric):
    """Collapse draws within a request; never count seeds as independent cases."""
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["case_id"]].append(row)
    values, failed = [], 0
    for request in grouped.values():
        if any(row["failure"] is not None for row in request):
            failed += 1
            continue
        measurements = [row["metrics"][metric] for row in request if row["metrics"][metric] is not None]
        if measurements:
            values.append({"case_id": request[0]["case_id"], "family_id": request[0]["family_id"], "value": mean(measurements)})
    return values, failed


def family_interval(values, *, samples=1000):
    """Descriptive cluster bootstrap of authored families, not population inference."""
    families = defaultdict(list)
    for row in values:
        families[row["family_id"]].append(row["value"])
    groups = [families[key] for key in sorted(families)]
    result = {"value": mean(row["value"] for row in values) if values else None,
              "queries": len(values), "families": len(groups), "interval_95": None,
              "method": "family_cluster_bootstrap_after_per_query_draw_mean", "bootstrap_samples": samples}
    if len(groups) >= 2:
        rng = random.Random(20261112)
        estimates = sorted(mean(value for _ in groups for value in rng.choice(groups)) for _ in range(samples))
        result["interval_95"] = [estimates[ceil(0.025 * samples) - 1], estimates[ceil(0.975 * samples) - 1]]
    return result


def summarize_group(rows, *, intervals=False):
    metrics = {}
    for key in METRICS:
        values, failed = query_values(rows, key)
        if intervals:
            metrics[key] = family_interval(values)
        else:
            metrics[key] = {"value": mean(row["value"] for row in values) if values else None,
                            "queries": len(values), "families": len({row["family_id"] for row in values})}
        metrics[key]["failed_queries_excluded"] = failed
    good = [row for row in rows if row["failure"] is None]
    lookup = [value for row in good for value in row["lookup_ms"]]
    ranking = [value for row in good for value in row["ranking_ms"]]
    return {"rows": len(rows), "distinct_queries": len({row["case_id"] for row in rows}),
            "failures": len(rows) - len(good), "metrics": metrics,
            "lookup_median_ms": median(lookup) if lookup else None, "lookup_p95_ms": percentile95(lookup),
            "ranking_median_ms": median(ranking) if ranking else None, "ranking_p95_ms": percentile95(ranking)}


def summarize(rows, identifiers):
    groups, pooled, paired = [], [], []
    for size, draw, split, ranker in sorted({(row["catalog_size"], row["draw"], row["split"], row["ranker"]) for row in rows}):
        selected = [row for row in rows if (row["catalog_size"], row["draw"], row["split"], row["ranker"]) == (size, draw, split, ranker)]
        groups.append({"catalog_size": size, "draw": draw, "split": split, "ranker": ranker,
                       **summarize_group(selected),
                       "categories": {key: summarize_group([row for row in selected if row["category"] == key]) for key in sorted({row["category"] for row in selected})},
                       "answerability": {key: summarize_group([row for row in selected if row["answerability"] == key]) for key in sorted({row["answerability"] for row in selected})}})
    for size, split in sorted({(row["catalog_size"], row["split"]) for row in rows}):
        for identifier in identifiers:
            selected = [row for row in rows if (row["catalog_size"], row["split"], row["ranker"]) == (size, split, identifier)]
            pooled.append({"catalog_size": size, "split": split, "ranker": identifier, **summarize_group(selected, intervals=True)})
        if "heuristic_v1" in identifiers:
            for identifier in identifiers:
                if identifier == "heuristic_v1":
                    continue
                metrics = {}
                for key in ("recall_at_5", "packed_recall", "all_owners_packed"):
                    arms = {}
                    for ranker in ("heuristic_v1", identifier):
                        selected = [row for row in rows if (row["catalog_size"], row["split"], row["ranker"]) == (size, split, ranker)]
                        values, _ = query_values(selected, key)
                        arms[ranker] = {row["case_id"]: row for row in values}
                    common = sorted(arms[identifier].keys() & arms["heuristic_v1"].keys())
                    deltas = [{**arms[identifier][case], "value": arms[identifier][case]["value"] - arms["heuristic_v1"][case]["value"]} for case in common]
                    metrics[key] = family_interval(deltas)
                paired.append({"catalog_size": size, "split": split, "candidate": identifier, "baseline": "heuristic_v1", "difference": "candidate_minus_baseline", "metrics": metrics})
    return groups, pooled, paired


def run_quality_comparison(manifest, sizes, output, data_root, *, identifiers, repeats=3, draws=(11, 22, 33), split="all"):
    if get_data_dir() != data_root.resolve():
        raise EvaluationConfigError("Discovery evaluation requires disposable stores")
    data = load_dataset()
    queries = [row for row in data["queries"] if split == "all" or row["split"] == split]
    labels = {row["id"]: row for row in data["judgments"]}
    public = {"profile": "discovery_quality_v2", "decision_mode": "local", "model_calls": 0, "gmail_calls": 0,
              "rankers": list(identifiers), "parameters": {key: ranker_parameters(get_ranker(key)) for key in identifiers},
              "catalog_sizes": sizes, "draws": list(draws), "base_evaluated_once": True, "repeats": repeats, "split": split,
              "dataset_manifest_sha256": digest(data["manifest"]), "review_status": data["manifest"]["authoring"]["review_status"],
              "default_ranker": "heuristic_v1", "defaults_promoted": False,
              "scope": "offline_worker_discovery_only; no agent, context, draft or community comparison",
              "quality_gate": "first_baseline_only; independent_review_pending; no_automatic_promotion",
              "latency": "ranking uses prepared snapshot; lookup includes fresh JSON reads, preparation, ranking and packing",
              "memory": "separate preparation pass; Python allocations, not RSS",
              "uncertainty": "average draws per query, then resample whole families; authored synthetic sample, not production inference"}
    write_json(output / "comparison.json", public)
    for filename in (*FILES, "manifest.json"):
        # Preserve complete frozen source inputs, including the unselected split.
        (output / "inputs").mkdir(exist_ok=True)
        (output / "inputs" / filename).write_bytes((DATASET_ROOT / filename).read_bytes())
    rows, preparation, snapshots = [], [], []
    with gzip.open(output / "results.jsonl.gz", "wt", encoding="utf-8", newline="\n") as archive:
        for size in sizes:
            for draw in ((draws[0],) if size == 100 else draws):
                workers = build_snapshot(data, size, draw)
                draw_label = "base" if size == 100 else str(draw)
                names, metadata = search_projection(workers)
                by_id = {row["worker_id"]: row["name"] for row in workers}
                snapshot_name = f"catalogs/{size}-{draw_label}.json.gz"
                (output / "catalogs").mkdir(exist_ok=True)
                with gzip.open(output / snapshot_name, "wt", encoding="utf-8", newline="\n") as handle:
                    json.dump(workers, handle, ensure_ascii=False, separators=(",", ":"))
                snapshots.append({"size": size, "draw": draw_label, "path": snapshot_name, "canonical_sha256": digest(workers)})
                roster = AgentRoster(data_root / f"discovery-{size}-{draw_label}" / "roster.json")
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
                preparation.append({"catalog_size": size, "draw": draw_label, "preparation_ms": elapsed, "preparation_peak_python_bytes": peak})
                for index, query in enumerate(queries):
                    label = labels[query["id"]]
                    relevant = [by_id[key] for key in label["relevant_worker_ids"]]
                    order = identifiers[index % len(identifiers):] + identifiers[:index % len(identifiers)]
                    for identifier in order:
                        row = {"case_id": query["id"], "family_id": query["family_id"], "split": query["split"],
                               "category": query["category"], "answerability": query["answerability"], "catalog_size": size,
                               "draw": draw_label, "ranker": identifier, "failure": None, "ranking_ms": [], "lookup_ms": [],
                               "metrics": {key: None for key in METRICS}}
                        try:
                            ranker = get_ranker(identifier)
                            for _ in range(repeats):
                                started = perf_counter()
                                ranked = rank_workers(ranker, query["query"], catalog)
                                row["ranking_ms"].append((perf_counter() - started) * 1000)
                                started = perf_counter()
                                packed = find_workers(roster, query["query"], ranker=ranker)
                                row["lookup_ms"].append((perf_counter() - started) * 1000)
                                if len(json.dumps(packed)) > LOOKUP_CHAR_BUDGET:
                                    raise AssertionError("Production lookup exceeded its response bound")
                            ranked_names = [match.name for match in ranked]
                            packed_names = [card["agent_name"] for card in packed["workers"]]
                            metrics, diagnostic = grade_case(ranked_names, packed_names, relevant, label["kind"], query["answerability"])
                            row.update(metrics=metrics, diagnostic_metrics=diagnostic, packed=packed,
                                       total_matches=len(ranked), top_matches=[{"name": match.name, "score": match.score, "reasons": match.reasons} for match in ranked[:5]],
                                       relevant_ranks={name: ranked_names.index(name) + 1 if name in ranked_names else None for name in relevant})
                        except Exception as exc:
                            row["failure"] = type(exc).__name__
                        rows.append(row)
                        archive.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                        archive.flush()  # Preserve failed and partial rows as they occur.
                    if (index + 1) % 25 == 0:
                        print(f"Discovery-v2 {size}/{draw_label}: {index + 1}/{len(queries)} requests", flush=True)
                write_json(output / "progress.json", {"completed_rows": len(rows), "last_catalog": size, "draw": draw_label})
    groups, pooled, paired = summarize(rows, identifiers)
    summary = {"profile": public["profile"], "checks_passed": all(row["failure"] is None for row in rows),
               "case_context_count": len(rows), "distinct_queries": len(queries), "families": len({row["family_id"] for row in queries}),
               "routing_quality": "unavailable_no_model_decisions", "review_status": public["review_status"],
               "defaults_promoted": False, "failures": sum(row["failure"] is not None for row in rows),
               "preparation": preparation, "snapshots": snapshots, "groups": groups, "pooled": pooled, "paired_differences": paired}
    write_json(output / "summary.json", summary)
    sources = ("evals/agent_overload/discovery_dataset.py", "evals/agent_overload/discovery_quality.py", "evals/agent_overload/ranking.py",
               "evals/agent_overload/run.py", "server/services/execution/discovery.py", "server/services/execution/ranking.py", "server/config.py")
    write_json(output / "provenance.json", {"created_at": datetime.now(timezone.utc).isoformat(), "dataset_manifest_sha256": digest(data["manifest"]),
               "legacy_manifest_sha256": digest(manifest), "python_version": platform.python_version(),
               "package_versions": {name: importlib.metadata.version(name) for name in ("httpx", "fastapi", "pydantic")}, "source_sha256_lf_normalized": {
                   path: hashlib.sha256((ROOT / path).read_text(encoding="utf-8").replace("\r\n", "\n").encode()).hexdigest() for path in sources}})
    write_report(output, summary)
    write_json(output / "artifacts.json", {path.relative_to(output).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
               for path in sorted(output.rglob("*")) if path.is_file()})
    return summary


def write_report(output, summary):
    def number(value):
        return "unavailable" if value is None else f"{value:.4f}"
    lines = ["# Discovery-quality v2 first baseline", "", "Offline production discovery/ranking; model and Gmail calls: zero. No defaults promoted.", "",
             f"Rows: {summary['case_context_count']}; distinct requests: {summary['distinct_queries']}; families: {summary['families']}; failures: {summary['failures']}.",
             f"Review: `{summary['review_status']}`. Integrity checks are not independent semantic review.", "",
             "Draws are averaged within a request before family-cluster bootstrap intervals. Repeats/seeds are not new independent requests. "
             "Intervals describe authored synthetic families, not production accuracy. Insufficient-metadata requests are diagnostic; no-match has no recall denominator. "
             "Ambiguous coverage does not establish model clarification or authorization.", "",
             "| Workers | Split | Ranker | Top-1 | Recall@5 | Packed recall | Every owner packed | No-match FP |",
             "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for group in summary["pooled"]:
        values = [number(group["metrics"][key]["value"]) for key in ("top1_correct", "recall_at_5", "packed_recall", "all_owners_packed", "no_match_false_positive")]
        lines.append(f"| {group['catalog_size']} | {group['split']} | {group['ranker']} | " + " | ".join(values) + " |")
    lines += ["", "## Per-draw timings", "", "Fresh JSON reads, preparation, scoring and packing are included. Timing repeats do not increase quality denominators. "
              "Preparation allocations are measured separately and are not process RSS.", "", "| Workers | Draw | Split | Ranker | Median ms | p95 ms |", "| ---: | --- | --- | --- | ---: | ---: |"]
    for group in summary["groups"]:
        lines.append(f"| {group['catalog_size']} | {group['draw']} | {group['split']} | {group['ranker']} | {number(group['lookup_median_ms'])} | {number(group['lookup_p95_ms'])} |")
    lines += ["", "See [summary.json](summary.json) for category/answerability breakdowns, denominators, failures, intervals and paired differences; "
              "`results.jsonl.gz` for every scored/packed result; `catalogs/` for complete frozen snapshots; `inputs/` for separate queries/judgments and authoring provenance. "
              "This more varied fixture remains synthetic and templated, with independent review pending. Historical v1 scores are not directly comparable.", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
