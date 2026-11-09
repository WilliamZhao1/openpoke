from copy import deepcopy
import hashlib
import gzip
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest

from evals.agent_overload.contracts import (
    EvaluationConfigError, HERE, ROOT, digest, grade_draft_effects, grade_routing,
    load_manifest, observation, read_json,
)


class EvaluationGradingTests(unittest.TestCase):
    def test_routing_grades_action_all_owners_and_wrong_reuse_separately(self):
        expected = {"action": "reuse", "workflow_ids": ["workflow-a", "workflow-b"]}
        correct = grade_routing(expected, {"action": "reuse", "workflow_ids": ["workflow-b", "workflow-a"]}, source_mode="mock")
        self.assertTrue(correct["action_correct"])
        self.assertTrue(correct["owners_correct"])
        partial = grade_routing(expected, {"action": "reuse", "workflow_ids": ["workflow-a", "workflow-c"]}, source_mode="mock")
        self.assertTrue(partial["action_correct"])
        self.assertFalse(partial["owners_correct"])
        self.assertTrue(partial["incorrect_reuse"])
        self.assertEqual(partial["missed_owner_ids"], ["workflow-b"])
        self.assertEqual(partial["unexpected_owner_ids"], ["workflow-c"])
        created = grade_routing(expected, {"action": "create_new", "workflow_ids": []}, source_mode="mock")
        self.assertTrue(created["unnecessary_creation"])
        absent = grade_routing(expected, None, source_mode="mock")
        self.assertEqual(absent["availability"], "unavailable")
        self.assertNotIn("action_correct", absent)

    def test_task_grading_uses_exact_write_evidence_and_rejects_extra_recipients(self):
        expected = read_json(HERE / "approved_draft.json")["expected"]
        effect = {
            "kind": "draft_sent", "account_id": expected["account_id"], "draft_id": expected["draft_id"],
            "body": expected["body"], "message": {
                "threadId": expected["thread_id"], "to": expected["recipient"], "subject": expected["subject"],
                "textBody": expected["body"], "cc": [], "bcc": [], "extra_recipients": [], "attachmentList": [],
            },
        }
        self.assertTrue(grade_draft_effects(expected, [effect])["exact_approved_draft_sent_once"])
        for target, field, value in [
            ("effect", "account_id", "wrong-account"), ("effect", "draft_id", "wrong-draft"),
            ("effect", "body", "changed body"), ("message", "to", "wrong@example.test"),
            ("message", "threadId", "wrong-thread"), ("message", "subject", "wrong subject"),
            ("message", "textBody", "changed stored content"),
            ("message", "cc", ["extra@example.test"]), ("message", "bcc", ["hidden@example.test"]),
            ("message", "extra_recipients", ["extra@example.test"]),
            ("message", "attachmentList", [{"name": "unapproved.pdf"}]),
        ]:
            with self.subTest(field=field):
                changed = deepcopy(effect)
                (changed if target == "effect" else changed["message"])[field] = value
                self.assertFalse(grade_draft_effects(expected, [changed])["exact_approved_draft_sent_once"])
        duplicate = grade_draft_effects(expected, [effect, deepcopy(effect)])
        self.assertFalse(duplicate["exact_approved_draft_sent_once"])
        self.assertEqual(duplicate["duplicate_send_count"], 1)
        self.assertFalse(grade_draft_effects(expected, [])["exact_approved_draft_sent_once"])
        extra_mutation = grade_draft_effects(expected, [effect, {"kind": "draft_created"}])
        self.assertEqual(extra_mutation["unexpected_mutation_count"], 1)

    def test_report_observations_preserve_four_states_and_require_evidence(self):
        rows = [
            observation(0),
            observation(True, availability="inferred", evidence_refs=["smoke.json#/gmail/effects"]),
            observation(None, availability="unavailable", reason="model_not_run"),
            observation(None, availability="not_applicable", reason="no_ranked_shortlist"),
        ]
        self.assertEqual({row["availability"] for row in json.loads(json.dumps(rows))}, {"available", "inferred", "unavailable", "not_applicable"})
        self.assertEqual(rows[0]["value"], 0)
        with self.assertRaises(ValueError):
            observation(1, availability="inferred")
        with self.assertRaises(ValueError):
            observation(0, availability="unavailable", reason="missing")

    def test_manifest_rejects_credentials_unpinned_modes_and_invalid_limits(self):
        original = read_json(HERE / "manifest.json")
        for field, value in [("api_key", "do-not-export-secret"), ("run_mode", "live"), ("schema_version", 99)]:
            changed = deepcopy(original)
            changed[field] = value
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "manifest.json"
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaises(EvaluationConfigError):
                    load_manifest(path)
        changed = deepcopy(original)
        changed["runtime_settings"]["openrouter_max_tokens"] = 0
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(EvaluationConfigError):
                load_manifest(path)


class EvaluationCliTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.real_data = self.root / "untouched-profile"
        self.real_data.mkdir()
        (self.real_data / "marker.txt").write_text("private-history-marker", encoding="utf-8")
        self.environment = dict(os.environ, OPENPOKE_DATA_DIR=str(self.real_data),
                                OPENPOKE_WORKER_DISCOVERY="bounded",
                                OPENPOKE_CONTEXT_STRATEGY="bounded", OPENPOKE_MODEL_CONTEXT_WINDOWS='{"not-the-model":1}',
                                OPENPOKE_CONTEXT_INPUT_TOKENS="invalid", OPENPOKE_CONTEXT_HEADROOM_TOKENS="invalid",
                                OPENROUTER_API_KEY="do-not-export-api-sentinel", COMPOSIO_API_KEY="do-not-export-gmail-sentinel",
                                UNRELATED_PRIVATE_SETTING="do-not-export-environment-sentinel")

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(HERE / "run.py"), *map(str, args)], cwd=ROOT,
                              env=self.environment, capture_output=True, text=True, timeout=30)

    def test_cli_captures_full_roster_inputs_and_trace_with_isolated_safe_evidence(self):
        output = self.root / "evidence"
        result = self.run_cli("--output", output)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["routing_quality"], "unavailable")
        summary = read_json(output / "summary.json")
        self.assertTrue(summary["checks_passed"])
        self.assertEqual(summary["case_context_count"], 40)
        self.assertEqual(summary["catalog_sizes"], [0, 100, 1000, 10000])
        for field in ("routing_accuracy", "end_task_success_rate", "live_provider_cost", "live_provider_latency"):
            self.assertEqual(summary["measurements"][field]["availability"], "unavailable")
            self.assertIsNone(summary["measurements"][field]["value"])
        shapes = read_json(output / "prompt_shapes.json")
        self.assertEqual([row["visible_workflows"]["value"] for row in shapes], [0, 100, 1000, 10000])
        self.assertLess(shapes[1]["roster_characters"]["value"], shapes[3]["roster_characters"]["value"])
        for row in shapes:
            self.assertEqual(row["roster_tokens"]["availability"], "unavailable")
        contexts = read_json(output / "case_contexts.json")
        self.assertEqual(len({row["case_id"] for row in contexts}), 14)
        self.assertTrue(all(row["routing_grade"]["availability"] == "unavailable" for row in contexts))
        with gzip.open(output / "case_requests.jsonl.gz", "rt", encoding="utf-8") as stream:
            archived = [json.loads(line) for line in stream]
        self.assertEqual(len(archived), 40)
        for row in contexts:
            request = archived[row["payload_line"]]
            self.assertEqual(set(request), {"case_id", "catalog_size", "payload"})
            self.assertEqual(request["case_id"], row["case_id"])
            self.assertEqual(request["catalog_size"], row["catalog_size"])
            self.assertEqual(digest(request["payload"]), row["request_sha256"])
        self.assertEqual(digest(read_json(output / "inputs/routing_cases.json")), read_json(output / "manifest.json")["fixture_checksums"]["routing_cases"])
        frozen_generator = runpy.run_path(str(output / "inputs/catalogs.py"))
        self.assertEqual(digest(frozen_generator["build_catalog"](100)), read_json(output / "manifest.json")["fixture_checksums"]["catalogs"]["100"])
        manifest = read_json(output / "manifest.json")
        smoke = read_json(output / "smoke.json")
        self.assertEqual(len(smoke["provider_requests"]), 5)
        self.assertTrue(all(payload["max_tokens"] == manifest["runtime_settings"]["openrouter_max_tokens"] for payload in smoke["provider_requests"]))
        self.assertTrue(smoke["effect_grade"]["exact_approved_draft_sent_once"])
        self.assertTrue(smoke["routing_grade"]["owners_correct"])
        self.assertTrue(all(smoke["checks"].values()))
        events = smoke["telemetry"]
        self.assertTrue(all(event["provider_mode"] == "mock" for event in events if event["event"] == "model_call.completed"))
        states = {value["availability"] for event in events for value in event["observations"].values()}
        self.assertEqual(states, {"available", "inferred", "unavailable", "not_applicable"})
        for relative, expected_hash in read_json(output / "artifacts.json").items():
            self.assertEqual(hashlib.sha256((output / relative).read_bytes()).hexdigest(), expected_hash)
        serialized = "\n".join(path.read_text(encoding="utf-8") for path in output.rglob("*") if path.is_file() and path.suffix != ".gz")
        serialized += json.dumps(archived)
        for private in ("do-not-export", "private-history-marker", str(self.root), str(self.real_data)):
            self.assertNotIn(private, serialized)
        self.assertEqual([path.name for path in self.real_data.iterdir()], ["marker.txt"])
        self.assertEqual((self.real_data / "marker.txt").read_text(encoding="utf-8"), "private-history-marker")

    def test_repeated_runs_keep_input_fingerprints_and_never_overwrite_evidence(self):
        first, second = self.root / "first", self.root / "second"
        for output in (first, second):
            result = self.run_cli("--sizes", 0, 100, "--output", output)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(read_json(first / "prompt_shapes.json"), read_json(second / "prompt_shapes.json"))
        self.assertEqual(read_json(first / "case_contexts.json"), read_json(second / "case_contexts.json"))
        self.assertEqual((first / "case_requests.jsonl.gz").read_bytes(), (second / "case_requests.jsonl.gz").read_bytes())
        before = (first / "artifacts.json").read_bytes()
        result = self.run_cli("--sizes", 0, "--output", first)
        self.assertEqual(result.returncode, 2)
        self.assertIn("already exists", result.stderr)
        self.assertEqual((first / "artifacts.json").read_bytes(), before)

    def test_invalid_or_live_modes_fail_before_a_run_is_created(self):
        output = self.root / "invalid"
        result = self.run_cli("--mode", "live", "--output", output)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())
        invalid = read_json(HERE / "manifest.json")
        invalid["api_key"] = "do-not-export-api-sentinel"
        path = self.root / "bad-manifest.json"
        path.write_text(json.dumps(invalid), encoding="utf-8")
        result = self.run_cli("--manifest", path, "--output", output)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(output.exists())
        self.assertNotIn("do-not-export", result.stderr)

    def test_fixture_drift_fails_instead_of_publishing_a_passing_report(self):
        manifest = read_json(HERE / "manifest.json")
        manifest["fixture_checksums"]["gmail_mailbox"] = "0" * 64
        path = self.root / "drifted-manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        output = self.root / "drifted-output"
        result = self.run_cli("--manifest", path, "--sizes", 0, "--output", output)
        self.assertEqual(result.returncode, 2)
        self.assertIn("checksums", result.stderr)
        self.assertFalse((output / "summary.json").exists())


if __name__ == "__main__":
    unittest.main()
