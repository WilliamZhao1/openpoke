"""Ranker contracts, controlled comparisons, and real discovery/agent integration."""

from dataclasses import FrozenInstanceError
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx

from server.agents.interaction_agent import runtime, tools
from server.config import Settings, get_settings
from server.openrouter_client import client
from server.services.execution.discovery import WorkerDiscoveryError, atomic_json, find_workers
from server.services.execution.ranking import (
    RANKER_IDS, SearchCatalog, RankedWorker, RankingError, get_ranker, rank_workers, terms,
)
from server.services.execution.roster import AgentRoster
from server.tests.fixtures.catalogs import build_catalog
from evals.agent_overload.contracts import HERE, ROOT
from evals.agent_overload.ranking import grade_ranking


class WorkerRankingTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.roster = AgentRoster(Path(directory.name) / "roster.json")

    def seed(self, names, metadata=None):
        atomic_json(self.roster._roster_path, names)
        atomic_json(self.roster.metadata_path, metadata or {})
        return SearchCatalog.build(names, metadata or {})

    def test_heuristic_matches_frozen_pre_refactor_responses(self):
        fixture = json.loads((HERE / "heuristic_golden.json").read_text(encoding="utf-8"))
        for case in fixture["cases"]:
            rows = build_catalog(case["size"])
            metadata = {row["display_name"]: {"purpose": row["purpose"][:240], "recent_assignment": row["card"]["summary"][:240],
                        "last_activity": row["last_activity_at"]} for row in rows}
            self.seed([row["display_name"] for row in rows], metadata)
            result = find_workers(self.roster, case["query"], ranker=get_ranker("heuristic_v1"))
            encoded = json.dumps(result, sort_keys=True, ensure_ascii=True).encode()
            self.assertEqual(hashlib.sha256(encoded).hexdigest(), case["sha256"], case)

    def test_exact_names_unicode_ties_and_missing_metadata_in_every_method(self):
        names = ["Alice lunch", "alice lunch", "旅行計画", " Café Étude ", "zebra task", "alpha task"]
        catalog = self.seed(names)
        for identifier in RANKER_IDS:
            ranker = get_ranker(identifier)
            for name in names:
                ranked = rank_workers(ranker, name, catalog)
                self.assertEqual(ranked[0].name, name)
                self.assertEqual(ranked[0].reasons[0], "exact_name")
            self.assertEqual([match.name for match in rank_workers(ranker, "task", catalog)], ["alpha task", "zebra task"])
            self.assertEqual(rank_workers(ranker, "quasar", catalog), [])
            self.assertEqual(rank_workers(ranker, "alice", SearchCatalog.build([], {})), [])
        self.assertEqual(terms("ＣＯＮＴＲＡＣＴ"), {"contract"})

    def test_catalog_is_detached_immutable_and_never_contains_fixture_gold(self):
        metadata = {"Alpha": {"purpose": "original", "expected_owner": "secret"}}
        catalog = SearchCatalog.build(["Alpha", "Alpha"], metadata)
        metadata["Alpha"]["purpose"] = "changed"
        self.assertEqual(len(catalog.documents), 1)
        self.assertEqual(catalog.documents[0].values, ("Alpha", "original", ""))
        self.assertNotIn("secret", repr(catalog))
        with self.assertRaises(TypeError):
            catalog.document_frequency["x"] = 1
        with self.assertRaises(TypeError):
            catalog.documents[0].frequencies[0]["alpha"] = 2
        with self.assertRaises(FrozenInstanceError):
            catalog.documents = ()

    def test_idf_prefers_distinctive_topics_and_rewards_coverage(self):
        catalog = self.seed(["Alice lunch", "Contract work", *[f"Alice project {n}" for n in range(20)]],
                            {"Contract work": {"purpose": "Alice original services"}})
        ranker = get_ranker("idf_v1")
        ranked = rank_workers(ranker, "Alice contract", catalog)
        self.assertEqual(ranked[0].name, "Contract work")
        self.assertGreater(catalog.idf("contract"), catalog.idf("alice"))
        once = {match.name: match.score for match in rank_workers(ranker, "Alice contract", catalog)}
        repeated = {match.name: match.score for match in rank_workers(ranker, "Alice contract contract", catalog)}
        self.assertEqual(once, repeated)
        first = SearchCatalog.build(["item"], {"item": {"purpose": "contract"}})
        copied = SearchCatalog.build(["item"], {"item": {"purpose": "contract", "recent_assignment": "contract"}})
        self.assertEqual(ranker.rank("contract", first)[0].score, ranker.rank("contract", copied)[0].score)

    def test_bm25_saturates_frequency_and_normalizes_field_length(self):
        catalog = self.seed(["single", "double", "many", "padded"], {
            "single": {"purpose": "contract"}, "double": {"purpose": "contract contract"},
            "many": {"purpose": "contract " * 10}, "padded": {"purpose": "contract " + "filler " * 20}})
        scores = {match.name: match.score for match in rank_workers(get_ranker("bm25_v1"), "contract", catalog)}
        self.assertGreater(scores["double"], scores["single"])
        self.assertLess(scores["double"], 2 * scores["single"])
        self.assertLess(scores["many"], 10 * scores["single"])
        self.assertGreater(scores["single"], scores["padded"])

    def test_injected_ranker_contract_failures_are_not_empty_successes(self):
        catalog = self.seed(["Alpha", "Beta"])
        invalid = ([RankedWorker("unknown", 1, ())], [RankedWorker("Alpha", float("nan"), ())],
                   [RankedWorker("Alpha", True, ())], [RankedWorker("Alpha", 0, ())],
                   [RankedWorker("Alpha", 1, ("x" * 65,))],
                   [RankedWorker("Alpha", 1, ()), RankedWorker("Alpha", 2, ())], [], None)
        for output in invalid:
            with self.subTest(output=output):
                ranker = SimpleNamespace(rank=lambda query, catalog: output)
                with self.assertRaises(RankingError):
                    rank_workers(ranker, "Alpha", catalog)
                with self.assertRaises(WorkerDiscoveryError):
                    find_workers(self.roster, "Alpha", ranker=ranker)

    def test_lookup_limits_collisions_metadata_updates_and_clear_for_all_rankers(self):
        self.seed(["Alice / Lunch", "Alice - Lunch", "旅行計画"], {"旅行計画": {"purpose": "𐐀" * 240}})
        for identifier in RANKER_IDS:
            ranker = get_ranker(identifier)
            result = find_workers(self.roster, "Alice", ranker=ranker)
            self.assertTrue(all(card["history_collision"] for card in result["workers"]))
            self.assertLessEqual(len(json.dumps(find_workers(self.roster, "旅行計画", ranker=ranker))), 3500)
            self.assertEqual(len(find_workers(self.roster, "Alice", limit=0, ranker=ranker)["workers"]), 1)
        self.roster.record_assignment("旅行計画", "quasar")
        for identifier in RANKER_IDS:
            self.assertEqual(find_workers(self.roster, "quasar", ranker=get_ranker(identifier))["workers"][0]["agent_name"], "旅行計画")
        self.roster.clear()
        for identifier in RANKER_IDS:
            self.assertEqual(find_workers(self.roster, "quasar", ranker=get_ranker(identifier))["workers"], [])

    def test_setting_selection_is_validated_independent_and_constructor_wins(self):
        for identifier in RANKER_IDS:
            with patch.dict(os.environ, {"OPENPOKE_WORKER_RANKER": identifier}):
                settings = Settings(context_strategy="legacy", worker_discovery_strategy="legacy")
                self.assertEqual(settings.worker_ranker, identifier)
                self.assertEqual(Settings(worker_ranker="heuristic_v1").worker_ranker, "heuristic_v1")
                with patch("server.config.get_settings", return_value=settings):
                    self.seed(["Alice lunch"])
                    self.assertEqual(find_workers(self.roster, "Alice lunch")["workers"][0]["agent_name"], "Alice lunch")
        with self.assertRaises(ValueError):
            Settings(worker_ranker="unknown")
        with patch.dict(os.environ, {"OPENPOKE_WORKER_RANKER": "unknown"}), self.assertRaises(ValueError):
            Settings()
        with self.assertRaises(ValueError):
            get_ranker("unknown")

    def test_retrieval_metrics_distinguish_ambiguity_packing_and_no_match_cases(self):
        metrics = grade_ranking(["wrong", "a", "b"], ["wrong", "a"], ["a", "b"], "ambiguous")
        self.assertIsNone(metrics["top1_correct"])
        self.assertEqual(metrics["recall_at_5"], 1)
        self.assertEqual(metrics["packed_recall"], 0.5)
        self.assertEqual(metrics["reciprocal_rank"], 0.5)
        self.assertTrue(grade_ranking(["wrong"], ["wrong"], [], "none")["no_match_false_positive"])
        self.assertFalse(grade_ranking([], [], [], "none")["no_match_false_positive"])


class WorkerRankingAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_ranker_failure_revokes_discovery_and_cannot_create_a_worker(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        roster = AgentRoster(Path(directory.name) / "roster.json")
        roster.register("Existing")
        state = tools.DiscoveryState()
        with patch.object(tools, "get_agent_roster", return_value=roster):
            self.assertTrue(tools.find_worker("Existing", discovery=state).success)
            self.assertTrue(state.successful)
            broken = SimpleNamespace(rank=lambda query, catalog: [RankedWorker("forged", 1, ())])
            with patch("server.services.execution.discovery.get_ranker", return_value=broken):
                self.assertFalse(tools.find_worker("Existing", discovery=state).success)
            self.assertFalse(state.successful)
            result = tools.send_message_to_agent("Another", "New task", discovery=state)
            self.assertFalse(result.success)
            self.assertEqual(roster.get_agents(), ["Existing"])

    async def test_real_lookup_loop_uses_selected_ranker_with_bounded_preflight(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        roster = AgentRoster(Path(directory.name) / "roster.json")
        atomic_json(roster._roster_path, ["Alice lunch", "Contract work", *[f"Alice project {n}" for n in range(20)]])
        atomic_json(roster.metadata_path, {"Contract work": {"purpose": "Alice original services"}})
        settings = get_settings()
        for identifier in RANKER_IDS:
            requests = []
            def respond(request):
                payload = json.loads(request.content)
                requests.append(payload)
                if len(requests) == 1:
                    message = {"tool_calls": [{"id": "lookup", "type": "function", "function": {
                        "name": "find_worker", "arguments": json.dumps({"query": "Alice contract"})}}]}
                else:
                    result = json.loads(payload["messages"][-1]["content"])["result"]
                    expected = find_workers(roster, "Alice contract", ranker=get_ranker(identifier))
                    self.assertEqual(result, expected)
                    message = {"content": "Found existing workers."}
                return httpx.Response(200, json={"choices": [{"message": message}]})
            with (patch.object(settings, "worker_ranker", identifier), patch.object(settings, "worker_discovery_strategy", "bounded"),
                  patch.object(settings, "context_strategy", "bounded"), patch.object(settings, "model_context_windows", {settings.interaction_agent_model: 65536}),
                  patch.object(settings, "conversation_summary_threshold", 0), patch.object(tools, "get_agent_roster", return_value=roster),
                  patch("server.agents.interaction_agent.agent.get_agent_roster", return_value=roster),
                  client.use_mock_provider(httpx.MockTransport(respond)),
                  patch.object(client, "prepare_budgeted_request", wraps=client.prepare_budgeted_request) as guard):
                result = await runtime.InteractionAgentRuntime().execute("Find Alice contract work")
                self.assertTrue(result.success, result.error)
                self.assertEqual(guard.call_count, len(requests))
                self.assertEqual(len(requests), 2)


class WorkerRankingCliTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.private = self.root / "private"
        self.private.mkdir()
        (self.private / "marker").write_text("private-sentinel", encoding="utf-8")
        self.environment = dict(os.environ, OPENPOKE_DATA_DIR=str(self.private), OPENPOKE_WORKER_RANKER="invalid",
            OPENROUTER_API_KEY="secret-sentinel", COMPOSIO_API_KEY="secret-sentinel")

    def run_cli(self, output, *extra):
        return subprocess.run([sys.executable, str(HERE / "run.py"), "--compare-rankers", *RANKER_IDS,
            "--sizes", "100", "--repeats", "1", "--output", str(output), *extra], cwd=ROOT,
            env=self.environment, capture_output=True, text=True, timeout=60)

    def test_offline_comparison_saves_real_rankings_separate_labels_and_artifact_hashes(self):
        output = self.root / "ranking"
        result = self.run_cli(output)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary = json.loads((output / "summary.json").read_text())
        self.assertEqual(summary["case_context_count"], 16 * 3)
        self.assertTrue(summary["checks_passed"])
        self.assertFalse(summary["defaults_promoted"])
        self.assertEqual(summary["routing_quality"], "unavailable_no_model_decisions")
        catalog = json.loads((output / "catalog-100.json").read_text())
        self.assertEqual(set(catalog), {"names", "metadata"})
        self.assertNotIn("relevant_names", (output / "queries.json").read_text())
        self.assertNotIn("relevant_names", json.dumps(catalog))
        rows = json.loads((output / "results.json").read_text())
        self.assertTrue(all(row["failure"] is None and len(json.dumps(row["packed"])) <= 3500 for row in rows))
        for filename, checksum in json.loads((output / "artifacts.json").read_text()).items():
            content = (output / filename).read_bytes()
            self.assertEqual(hashlib.sha256(content).hexdigest(), checksum)
            self.assertNotIn(b"secret-sentinel", content)
            self.assertNotIn(b"private-sentinel", content)
        self.assertEqual(list(self.private.iterdir()), [self.private / "marker"])
        self.assertEqual(self.run_cli(output).returncode, 2)

    def test_fixed_agent_comparison_keeps_strategies_effects_and_model_controls(self):
        output = self.root / "agents"
        result = self.run_cli(output, "--ranker-agent-check", "--context-window", "65536", "--cases", "alice-lunch")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        public = json.loads((output / "comparison.json").read_text())
        self.assertEqual(public["worker_discovery_strategy"], "bounded")
        self.assertEqual(public["context_strategy"], "bounded")
        self.assertEqual(public["strategies"], list(RANKER_IDS))
        summary = json.loads((output / "summary.json").read_text())
        self.assertEqual(summary["routing_quality"], "unavailable_scripted_decisions")
        self.assertTrue(all(arm["exact_fake_draft_effect"] for arm in summary["arms"].values()))
        rows = json.loads((output / "results.json").read_text())
        for row in rows:
            self.assertLessEqual(row["roster_shape"]["visible_workers"], 5)
            for request in row["provider_requests"]:
                self.assertEqual(request["payload"]["model"], "anthropic/claude-sonnet-4.6")
                self.assertEqual(request["payload"]["max_tokens"], 2048)

    def test_invalid_controls_and_live_without_agent_mode_do_not_create_evidence(self):
        for extra in (("--mode", "live"), ("--repeats", "0"), ("--compare",)):
            output = self.root / str(len(list(self.root.iterdir())))
            result = self.run_cli(output, *extra)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertFalse(output.exists())
