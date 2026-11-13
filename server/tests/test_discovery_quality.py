"""Discovery-v2 input integrity, real packing, metric and CLI regressions."""

from copy import deepcopy
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from evals.agent_overload.contracts import EvaluationConfigError, digest
from evals.agent_overload.discovery_dataset import (
    DATASET_ROOT, FILES, build_snapshot, generate_workers, load_dataset, search_projection, validate_dataset,
)
from evals.agent_overload.discovery_quality import grade_case, family_interval, query_values, summarize
from server.services.execution.discovery import atomic_json, render_recent
from server.services.execution.log_store import _slugify
from server.services.execution.roster import AgentRoster


ROOT = Path(__file__).resolve().parents[2]


class DiscoveryDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_dataset()

    def test_frozen_families_cover_every_owner_with_disjoint_splits(self):
        data = self.data
        validate_dataset(data)
        splits = {key: {row["family_id"] for row in data["queries"] if row["split"] == key} for key in ("development", "evaluation")}
        self.assertFalse(splits["development"] & splits["evaluation"])
        self.assertEqual((len(splits["development"]), len(splits["evaluation"])), (5, 15))
        self.assertEqual(len({key for row in data["judgments"] for key in row["relevant_worker_ids"]}), 100)
        self.assertEqual(data["manifest"]["authoring"]["review_status"], "author_checked_pending_independent_review")

    def test_corrupted_source_is_rejected_instead_of_refreezing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (*FILES, "manifest.json"):
                (root / name).write_bytes((DATASET_ROOT / name).read_bytes())
            value = json.loads((root / "workers.json").read_text(encoding="utf-8"))
            value[0]["purpose"] = "changed after freezing"
            (root / "workers.json").write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(EvaluationConfigError, "content changed"):
                load_dataset(root)

    def test_invalid_labels_cross_family_splits_and_oversized_metadata_are_rejected(self):
        for mutation in ("wrong_owner", "wrong_split", "duplicate_query", "oversized", "extra_field", "private_leak"):
            with self.subTest(mutation=mutation):
                data = deepcopy(self.data)
                if mutation == "wrong_owner":
                    data["judgments"][0]["relevant_worker_ids"] = [data["families"][1]["worker_ids"][0]]
                elif mutation == "wrong_split":
                    data["queries"][0]["split"] = "evaluation"
                elif mutation == "duplicate_query":
                    data["queries"][1]["query"] = data["queries"][0]["query"]
                elif mutation == "oversized":
                    data["workers"][0]["purpose"] = "x" * 241
                elif mutation == "extra_field":
                    data["workers"][0]["expected_owner"] = True
                else:
                    data["workers"][0]["recent_assignment"] = "QX-VENDOR-48"
                with self.assertRaises(EvaluationConfigError):
                    validate_dataset(data)

    def test_catalogs_are_nested_and_three_draws_have_different_backgrounds(self):
        base = build_snapshot(self.data, 100, 11)
        self.assertEqual(base, build_snapshot(self.data, 100, 33))
        hashes = []
        for draw in (11, 22, 33):
            small = build_snapshot(self.data, 1000, draw)
            large = build_snapshot(self.data, 10000, draw)
            self.assertEqual(small[:100], base)
            self.assertEqual(large[:1000], small)
            self.assertEqual(len({_slugify(row["name"]) for row in large}), 10000)
            hashes.append(digest(large))
        self.assertEqual(len(set(hashes)), 3)

    def test_generation_and_search_projection_do_not_consume_queries_or_gold(self):
        changed = deepcopy(self.data)
        changed["queries"] = [{"query": "forged expected answer"}]
        changed["judgments"] = [{"expected": "forged"}]
        self.assertEqual(generate_workers(changed, 1000, 11), generate_workers(self.data, 1000, 11))
        names, metadata = search_projection(build_snapshot(self.data, 100, 11))
        self.assertEqual(len(names), 100)
        self.assertTrue(all(set(row) == {"purpose", "recent_assignment", "last_activity"} for row in metadata.values()))

    def test_dormant_targets_really_are_outside_the_recent_roster(self):
        with tempfile.TemporaryDirectory() as directory:
            roster = AgentRoster(Path(directory) / "roster.json")
            workers = build_snapshot(self.data, 100, 11)
            names, metadata = search_projection(workers)
            atomic_json(roster._roster_path, names)
            atomic_json(roster.metadata_path, metadata)
            rendered = render_recent(roster)
            by_id = {row["worker_id"]: row["name"] for row in workers}
            self.assertTrue(all(by_id[family["worker_ids"][0]] not in rendered for family in self.data["families"]))


class DiscoveryMetricTests(unittest.TestCase):
    def test_all_owner_coverage_precision_and_packing_have_distinct_meanings(self):
        metrics, diagnostic = grade_case(["a", "x", "b"], ["a", "x"], ["a", "b"], "multiple", "answerable")
        self.assertIsNone(diagnostic)
        self.assertEqual(metrics["recall_at_5"], 1)
        self.assertEqual(metrics["packed_recall"], 0.5)
        self.assertTrue(metrics["all_owners_at_5"])
        self.assertFalse(metrics["all_owners_packed"])
        self.assertAlmostEqual(metrics["precision_at_5"], 2 / 3)
        self.assertEqual(metrics["packed_precision"], 0.5)

    def test_missing_evidence_and_no_match_do_not_inflate_recall_denominators(self):
        metrics, diagnostic = grade_case(["a"], ["a"], ["a"], "single", "insufficient_metadata")
        self.assertTrue(all(value is None for value in metrics.values()))
        self.assertEqual(diagnostic["packed_recall"], 1)
        metrics, diagnostic = grade_case(["x"], ["x"], [], "none", "answerable")
        self.assertIsNone(metrics["recall_at_5"])
        self.assertTrue(metrics["no_match_false_positive"])
        self.assertEqual(metrics["irrelevant_packed_count"], 1)

    def test_draws_collapse_before_family_intervals_and_failures_exclude_whole_requests(self):
        rows = [{"case_id": case, "family_id": family, "failure": failure, "metrics": {"recall_at_5": value}}
                for case, family, failure, value in (("a", "one", None, 0), ("a", "one", None, 1),
                    ("b", "two", None, 1), ("c", "three", None, 1), ("c", "three", "Error", None))]
        values, failed = query_values(rows, "recall_at_5")
        self.assertEqual(failed, 1)
        interval = family_interval(values)
        self.assertEqual((interval["queries"], interval["families"], interval["value"]), (2, 2, 0.75))
        self.assertEqual(interval, family_interval(values))
        self.assertIsNone(family_interval(values[:1])["interval_95"])

    def test_paired_comparison_uses_matching_requests_and_family_clusters(self):
        rows = []
        metrics, _ = grade_case(["a"], ["a"], ["a"], "single", "answerable")
        for identifier in ("heuristic_v1", "idf_v1"):
            for family in ("one", "two"):
                for draw in ("11", "22"):
                    rows.append({"case_id": family, "family_id": family, "split": "evaluation", "category": "description",
                                 "answerability": "answerable", "catalog_size": 1000, "draw": draw, "ranker": identifier,
                                 "failure": None, "metrics": metrics, "lookup_ms": [1], "ranking_ms": [0.5]})
        groups, pooled, paired = summarize(rows, ["heuristic_v1", "idf_v1"])
        self.assertEqual(pooled[0]["metrics"]["recall_at_5"]["queries"], 2)
        delta = paired[0]["metrics"]["recall_at_5"]
        self.assertEqual(delta["value"], 0)
        self.assertEqual(delta["interval_95"], [0, 0])


class DiscoveryQualityCliTests(unittest.TestCase):
    def invoke(self, output, *extra):
        return subprocess.run([sys.executable, str(ROOT / "evals/agent_overload/run.py"), "--output", str(output), *extra],
                              cwd=ROOT, capture_output=True, text=True, timeout=90)

    def test_cli_runs_real_rankers_preserves_inputs_hashes_and_existing_destinations(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence"
            result = self.invoke(output, "--compare-rankers", "heuristic_v1", "idf_v1", "bm25_v1", "--dataset", "discovery-v2",
                                 "--sizes", "100", "--split", "development", "--repeats", "1")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertTrue(summary["checks_passed"])
            self.assertEqual((summary["case_context_count"], summary["distinct_queries"], summary["families"]), (150, 50, 5))
            self.assertFalse(summary["defaults_promoted"])
            with gzip.open(output / "results.jsonl.gz", "rt", encoding="utf-8") as handle:
                rows = [json.loads(line) for line in handle]
            self.assertEqual(len(rows), 150)
            self.assertTrue(all(row["draw"] == "base" and row["split"] == "development" for row in rows))
            self.assertTrue(all(len(json.dumps(row["packed"])) <= 3500 for row in rows))
            self.assertEqual(len(json.loads((output / "inputs/queries.json").read_text(encoding="utf-8"))), 200)
            for name, expected in json.loads((output / "artifacts.json").read_text()).items():
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), expected)
            before = (output / "artifacts.json").read_bytes()
            repeated = self.invoke(output, "--compare-rankers", "heuristic_v1", "--dataset", "discovery-v2", "--sizes", "100")
            self.assertEqual(repeated.returncode, 2)
            self.assertEqual((output / "artifacts.json").read_bytes(), before)

    def test_live_agent_empty_catalog_and_duplicate_draw_controls_fail_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            for index, args in enumerate((
                ("--compare", "--dataset", "discovery-v2", "--mode", "live"),
                ("--compare-rankers", "heuristic_v1", "--dataset", "discovery-v2", "--ranker-agent-check"),
                ("--compare-rankers", "heuristic_v1", "--dataset", "discovery-v2", "--sizes", "0"),
                ("--compare-rankers", "heuristic_v1", "--dataset", "discovery-v2", "--draws", "11", "11"),
                ("--compare-rankers", "heuristic_v1", "--split", "development"),
            )):
                output = Path(directory) / str(index)
                result = self.invoke(output, *args)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertFalse(output.exists())
