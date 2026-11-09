from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import httpx

from evals.agent_overload.contracts import HERE, ROOT
from evals.agent_overload.comparison import ProviderCapture, grade_dispatches, summarize, usage_total
from server.openrouter_client.client import OpenRouterError


class ComparisonUsageTests(unittest.TestCase):
    def test_observed_routing_remains_gradable_after_a_later_task_failure(self):
        expected = {"action": "reuse", "workflow_ids": ["owner"]}
        catalog = [{"display_name": "exact name", "workflow_id": "owner"}]
        grade = grade_dispatches(expected, catalog, [{"agent_name": "exact name"}], "live", True)
        self.assertTrue(grade["action_correct"])
        self.assertTrue(grade["owners_correct"])
        self.assertEqual(grade_dispatches(expected, catalog, [], "live", True)["availability"], "unavailable")

    def test_missing_invalid_and_real_zero_usage_are_not_interchangeable(self):
        requests = [{"usage": {"cost": 0, "prompt_tokens": 0}}]
        self.assertEqual(usage_total(requests, "cost", "live")["value"], 0)
        self.assertEqual(usage_total(requests, "prompt_tokens", "live")["value"], 0)
        for invalid in (None, True, -1, "10", float("nan")):
            rows = deepcopy(requests) + [{"usage": {"cost": invalid, "prompt_tokens": invalid}}]
            for field in ("cost", "prompt_tokens"):
                result = usage_total(rows, field, "live")
                self.assertEqual(result["availability"], "unavailable")
                self.assertIsNone(result["value"])
                self.assertEqual(result["reported_subtotal"], 0)
                self.assertEqual(result["reported_calls"], 1)
        self.assertIsNone(usage_total([], "cost", "mock")["value"])

    def test_no_completed_live_decisions_have_no_routing_quality_measurement(self):
        rows = [{"strategy": strategy, "case_id": "approved-draft", "failure": "not_run_request_limit",
                 "routing_grade": {"availability": "unavailable"}} for strategy in ("legacy", "bounded")]
        summary = summarize(rows, {"strategies": ["legacy", "bounded"], "profile": "test", "decision_mode": "live"})
        self.assertEqual(summary["routing_quality"], "unavailable_no_completed_decisions")
        self.assertFalse(summary["checks_passed"])
        self.assertTrue(all(arm["graded"] == 0 and arm["exact_fake_draft_effect"] is None for arm in summary["arms"].values()))


class ComparisonCaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_endpoint_size_call_limits_and_error_redaction_precede_public_evidence(self):
        capture = ProviderCapture(1)
        endpoint = "https://openrouter.ai/api/v1/chat/completions"
        for request in (httpx.Request("POST", "https://example.test/", json={}), httpx.Request("POST", endpoint, content=b"x" * (256 * 1024 + 1))):
            with self.assertRaises(OpenRouterError):
                await capture.on_request(request)
        self.assertEqual(capture.requests, [])
        request = httpx.Request("POST", endpoint, json={"model": "synthetic"}, headers={"Authorization": "Bearer do-not-export"})
        await capture.on_request(request)
        response = httpx.Response(401, request=request, json={"error": {"message": "do-not-export"}, "usage": {"cost": "do-not-export"}})
        await capture.on_response(response)
        self.assertNotIn("do-not-export", json.dumps(capture.requests))
        self.assertEqual(capture.requests[0]["status_code"], 401)
        with self.assertRaises(OpenRouterError):
            await capture.on_request(httpx.Request("POST", endpoint, json={}))


class ComparisonCliTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.private = self.root / "private"
        self.private.mkdir()
        (self.private / "marker").write_text("private-history-sentinel", encoding="utf-8")
        self.environment = dict(os.environ, OPENPOKE_DATA_DIR=str(self.private),
            OPENROUTER_API_KEY="do-not-export-key-sentinel", COMPOSIO_API_KEY="do-not-export-mailbox-sentinel",
            OPENPOKE_CONTEXT_STRATEGY="bounded", OPENPOKE_WORKER_DISCOVERY="bounded",
            OPENPOKE_MODEL_CONTEXT_WINDOWS="invalid", OPENPOKE_CONTEXT_INPUT_TOKENS="invalid")

    def run_cli(self, output, *extra, environment=None):
        return subprocess.run([sys.executable, str(HERE / "run.py"), "--compare", "--context-window", "65536", "--sizes", "100",
                               "--cases", "alice-lunch", "--output", str(output), *extra], cwd=ROOT,
                              env=self.environment if environment is None else environment, capture_output=True, text=True, timeout=45)

    def read(self, output, name):
        return json.loads((output / name).read_text(encoding="utf-8"))

    def test_paired_actual_paths_keep_models_inputs_effects_provenance_and_private_data_separate(self):
        output = self.root / "paired"
        result = self.run_cli(output)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary = self.read(output, "summary.json")
        self.assertTrue(summary["checks_passed"])
        self.assertEqual(summary["decision_mode"], "mock")
        self.assertEqual(summary["routing_quality"], "unavailable_scripted_decisions")
        self.assertFalse(summary["defaults_promoted"])
        rows = self.read(output, "results.json")
        self.assertEqual(len(rows), 4)
        by_case = {}
        for row in rows:
            by_case.setdefault(row["case_id"], []).append(row)
            self.assertEqual(row["decision_mode"], "mock")
            self.assertEqual(row["gmail_mode"], "mock")
            self.assertEqual(row["routing_grade"]["actual"]["workflow_ids"], ["00000000-0000-4000-8000-000000000001"])
            self.assertIsNone(row["measurements"]["input_tokens"]["value"])
            for request in row["provider_requests"]:
                payload = request["payload"]
                self.assertEqual(payload["model"], "anthropic/claude-sonnet-4.6")
                self.assertEqual(payload["max_tokens"], 2048)
                self.assertFalse(payload["stream"])
                serialized = json.dumps(payload)
                for forbidden in ("workflow_ids", "owner_numbers", "candidate_numbers", "00000000-0000-4000"):
                    self.assertNotIn(forbidden, serialized)
            if row["case_id"] == "approved-draft":
                self.assertTrue(row["effect_grade"]["exact_approved_draft_sent_once"])
                self.assertEqual(row["effect_grade"]["unexpected_mutation_count"], 0)
                self.assertTrue(row["chat_accepted"])
                self.assertTrue(row["callback_received"])
            else:
                self.assertEqual(row["gmail"]["effects"], [])
        for pair in by_case.values():
            shapes = {row["strategy"]: row["roster_shape"] for row in pair}
            self.assertEqual(shapes["legacy"]["visible_workers"], 100)
            self.assertLessEqual(shapes["bounded"]["visible_workers"], 5)
            self.assertLessEqual(shapes["bounded"]["characters"], 2000)
        for path in output.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                for forbidden in ("do-not-export", "private-history-sentinel", str(self.private)):
                    self.assertNotIn(forbidden, text)
        for name, expected in self.read(output, "artifacts.json").items():
            self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), expected)
        self.assertEqual(list(self.private.iterdir()), [self.private / "marker"])
        self.assertEqual(self.run_cli(output).returncode, 2)

    def test_call_exhaustion_keeps_partial_evidence_and_marks_unrun_cases_unavailable(self):
        output = self.root / "limited"
        result = self.run_cli(output, "--max-calls", "1")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        summary = self.read(output, "summary.json")
        self.assertFalse(summary["checks_passed"])
        self.assertEqual(sum(arm["http_requests"] for arm in summary["arms"].values()), 1)
        rows = self.read(output, "results.json")
        self.assertTrue(any(row["failure"] == "not_run_request_limit" for row in rows))
        # The first response already submitted its worker before the next model
        # request was blocked. That route remains observed, while unrun rows do not.
        self.assertTrue(rows[0]["routing_grade"]["owners_correct"])
        self.assertTrue(all(row["routing_grade"]["availability"] == "unavailable" for row in rows if row["failure"] == "not_run_request_limit"))

    def test_live_missing_key_and_invalid_controls_fail_without_network_or_evidence(self):
        environment = dict(self.environment, OPENROUTER_API_KEY="")
        for args in (("--mode", "live"), ("--max-calls", "0"), ("--context-window", "4096"), ("--case-timeout", "301")):
            output = self.root / str(len(list(self.root.iterdir())))
            result = self.run_cli(output, *args, environment=environment)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertFalse(output.exists())
            self.assertNotIn("do-not-export", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
