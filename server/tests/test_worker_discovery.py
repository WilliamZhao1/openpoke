import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, Mock, patch

from server.agents.interaction_agent import agent, runtime, tools
from server.agents.execution_agent import batch_manager
from server.config import Settings
from server.routes import chat
from server import services
from server.services.execution import AgentRoster, ExecutionAgentLogStore
from server.services.execution import discovery
from server.tests.fixtures.catalogs import build_catalog


class WorkerDiscoveryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.roster = AgentRoster(self.root / "execution_agents" / "roster.json")
        self.logs = ExecutionAgentLogStore(self.roster._roster_path.parent)

    def seed(self, names):
        self.roster._roster_path.write_text(json.dumps(names), encoding="utf-8")
        self.roster.load()

    def test_catalogs_obey_roster_and_lookup_budgets_without_log_scans(self):
        measurements = []
        for size in (100, 1000, 10000):
            catalog = build_catalog(size)
            self.seed([row["display_name"] for row in catalog])
            metadata = {row["display_name"]: {"purpose": row["purpose"][:240], "recent_assignment": None,
                        "last_activity": row["last_activity_at"].replace("Z", "+00:00")} for row in catalog}
            discovery.atomic_json(self.roster.metadata_path, metadata)
            with patch.object(ExecutionAgentLogStore, "iter_entries", side_effect=AssertionError("Lookup must not scan history")):
                rendered = discovery.render_recent(self.roster)
                result = discovery.find_workers(self.roster, catalog[0]["display_name"], limit=10000)
            self.assertLessEqual(len(rendered), discovery.ROSTER_CHAR_BUDGET)
            self.assertLessEqual(rendered.count("<agent name="), 5)
            self.assertIn(f'total="{size}"', rendered)
            self.assertLessEqual(len(result["workers"]), 5)
            self.assertLessEqual(len(json.dumps(result)), discovery.LOOKUP_CHAR_BUDGET)
            self.assertEqual(result["workers"][0]["agent_name"], catalog[0]["display_name"])
            self.assertEqual(result["workers"][0]["match_reasons"][0], "exact_name")
            measurements.append((size, len(rendered), len(json.dumps(result))))
        self.assertEqual(len(measurements), 3)

    def test_old_worker_is_findable_outside_recent_entries(self):
        self.seed(["Dormant research", *[f"Recent {index}" for index in range(6)]])
        for index in range(6):
            self.roster.record_assignment(f"Recent {index}", f"Current project {index}")
        rendered = discovery.render_recent(self.roster)
        self.assertNotIn('name="Dormant research"', rendered)
        result = discovery.find_workers(self.roster, "Dormant research")
        self.assertEqual(result["workers"][0]["agent_name"], "Dormant research")
        self.assertIsNone(result["workers"][0]["purpose"])
        self.assertIsNone(result["workers"][0]["last_activity"])

    def test_names_are_exact_and_alice_topics_stay_separate(self):
        names = ["Alice lunch", "Alice contract", "alice lunch", " Café Étude ", "旅行計画"]
        self.seed(names)
        for name in names:
            result = discovery.find_workers(self.roster, name)
            self.assertEqual(result["workers"][0]["agent_name"], name)
        self.assertEqual(discovery.find_workers(self.roster, "Alice contract")["workers"][0]["agent_name"], "Alice contract")
        self.assertEqual(self.roster.get_agents(), names)
        self.assertFalse(self.roster.metadata_path.exists())

    def test_assignment_metadata_is_incremental_persistent_and_rebuildable(self):
        self.seed(["Alice lunch"])
        self.logs.record_request("Alice lunch", "Original history")
        before = {path: path.read_bytes() for path in (self.roster._roster_path, self.logs._log_path("Alice lunch"))}
        self.roster.record_assignment("Alice lunch", "Arrange sushi lunch")
        self.roster.record_assignment("Alice lunch", "Compare vegetarian options " + "x" * 500)
        reopened = AgentRoster(self.roster._roster_path)
        result = discovery.find_workers(reopened, "vegetarian")["workers"][0]
        self.assertEqual(result["purpose"], "Arrange sushi lunch")
        self.assertEqual(len(result["recent_assignment"]), 120)
        self.assertTrue(result["descriptions_limited"])
        self.assertEqual(len(json.loads(reopened.metadata_path.read_text())["Alice lunch"]["recent_assignment"]), 240)
        self.assertIn("recent_assignment_terms", result["match_reasons"])
        self.assertIsNotNone(result["last_activity"])
        reopened.rebuild_metadata()
        result = discovery.find_workers(reopened, "Alice lunch")["workers"][0]
        self.assertIsNone(result["purpose"])
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_unknown_activity_is_labelled_and_giant_names_do_not_break_budget(self):
        self.seed(["x" * 20000, "Normal worker"])
        rendered = discovery.render_recent(self.roster)
        self.assertLessEqual(len(rendered), 2000)
        self.assertIn('last_activity="unknown"', rendered)
        self.assertIn('hidden="1"', rendered)
        result = discovery.find_workers(self.roster, "x" * 10000)
        self.assertEqual(result["query_characters"], 256)
        self.assertTrue(result["query_truncated"])
        self.assertEqual(result["total_matches"], 1)
        self.assertEqual(result["workers"], [])
        self.assertEqual(result["omitted_matches"], 1)

    def test_historical_collisions_are_reported_and_new_collisions_rejected(self):
        self.seed(["Alice / Lunch", "Alice - Lunch"])
        original = self.roster._roster_path.read_bytes()
        cards = discovery.find_workers(self.roster, "Alice")["workers"]
        self.assertEqual(len(cards), 2)
        self.assertTrue(all(card["history_collision"] for card in cards))
        with self.assertRaisesRegex(ValueError, "collides"):
            self.roster.register("Alice:Lunch")
        self.assertEqual(self.roster._roster_path.read_bytes(), original)
        self.assertFalse(self.roster.register("Alice / Lunch", allow_creation=False))
        self.logs.record_request("Forgotten worker", "Orphan history")
        with self.assertRaisesRegex(ValueError, "collides"):
            self.roster.register("Forgotten worker")

    def test_concurrent_membership_and_collision_checks_use_fresh_state(self):
        other = AgentRoster(self.roster._roster_path)
        barrier = threading.Barrier(2)
        def register(roster):
            barrier.wait(timeout=2)
            return roster.register("Same worker")
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(register, [self.roster, other])), [False, True])
        self.assertEqual(self.roster.get_agents(), ["Same worker"])
        other.add_agent("Second")
        with self.assertRaisesRegex(ValueError, "find_worker"):
            self.roster.register("Third", allow_creation=False)
        self.assertEqual(self.roster.get_agents(), ["Same worker", "Second"])

    def test_atomic_write_failure_keeps_original_roster(self):
        self.seed(["Original"])
        before = self.roster._roster_path.read_bytes()
        with patch.object(discovery.os, "replace", side_effect=PermissionError("injected")):
            with self.assertRaises(discovery.WorkerDiscoveryError):
                self.roster.add_agent("New")
        self.assertEqual(self.roster._roster_path.read_bytes(), before)
        self.assertEqual(self.roster.get_agents(), ["Original"])
        self.assertEqual([path.name for path in self.roster._roster_path.parent.iterdir()], ["roster.json"])

    def test_invalid_roster_or_metadata_is_explicit_not_empty_results(self):
        self.seed(["Original"])
        self.roster.metadata_path.write_text("not json", encoding="utf-8")
        with self.assertRaises(discovery.WorkerDiscoveryError):
            discovery.find_workers(self.roster, "Original")
        with patch.object(agent, "get_agent_roster", return_value=self.roster):
            rendered = agent._render_active_agents(bounded=True)
        self.assertIn('status="unavailable"', rendered)
        self.assertNotIn('total="0"', rendered)
        for raw in ("not json", '["Original", 1]', '{"wrong":"shape"}'):
            self.roster._roster_path.write_text(raw, encoding="utf-8")
            with self.assertRaises(discovery.WorkerDiscoveryError):
                self.roster.get_agents()
            self.assertEqual(self.roster._roster_path.read_text(encoding="utf-8"), raw)

    def test_clamps_query_and_count_and_rejects_invalid_queries(self):
        self.seed([f"worker {index}" for index in range(8)])
        self.assertEqual(len(discovery.find_workers(self.roster, "worker", limit=0)["workers"]), 1)
        self.assertEqual(len(discovery.find_workers(self.roster, "worker", limit=999)["workers"]), 5)
        for query in (None, "", "!!!"):
            with self.assertRaises(ValueError):
                discovery.find_workers(self.roster, query)
        for limit in (True, "5"):
            with self.assertRaises(ValueError):
                discovery.find_workers(self.roster, "worker", limit)
        self.seed(["旅行計画"])
        self.roster.record_assignment("旅行計画", "\U00010400" * 240)
        result = discovery.find_workers(self.roster, "旅行計画")["workers"][0]
        self.assertEqual(result["agent_name"], "旅行計画")
        self.assertTrue(result["descriptions_limited"])

    def test_clear_route_removes_sidecar_and_late_assignment_does_not_restore_it(self):
        self.seed(["Alice lunch"])
        self.roster.record_assignment("Alice lunch", "Arrange lunch")
        self.logs.record_request("Alice lunch", "Arrange lunch")
        with (patch.object(services, "get_agent_roster", return_value=self.roster),
              patch.object(services, "get_execution_agent_logs", return_value=self.logs),
              patch.object(chat, "get_conversation_log", return_value=Mock()),
              patch.object(chat, "get_trigger_service", return_value=Mock())):
            chat.clear_history()
        self.roster.record_assignment("Alice lunch", "late old assignment")
        self.assertFalse(self.roster.metadata_path.exists())
        self.assertEqual(self.roster.get_agents(), [])
        self.assertFalse(self.logs._log_path("Alice lunch").exists())

    def test_strategy_is_validated_and_legacy_prompt_and_tools_remain_available(self):
        with self.assertRaises(ValueError):
            Settings(worker_discovery_strategy="unknown")
        self.seed(["Alice lunch"])
        with patch.object(agent, "get_agent_roster", return_value=self.roster):
            self.assertEqual(agent._render_active_agents(bounded=False), '<agent name="Alice lunch" />')
        self.assertEqual(agent.build_system_prompt(bounded=False), agent.SYSTEM_PROMPT)
        self.assertIn("CURRENT request", agent.build_system_prompt(bounded=True))
        self.assertIn("competing drafts", agent.build_system_prompt(bounded=True))
        self.assertNotIn("find_worker", [schema["function"]["name"] for schema in tools.get_tool_schemas()])
        self.assertIn("find_worker", [schema["function"]["name"] for schema in tools.get_tool_schemas(bounded=True)])


class WorkerDiscoveryRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.roster = AgentRoster(self.root / "execution_agents" / "roster.json")
        self.roster.add_agent("Alice lunch")
        self.roster.add_agent("Alice contract")
        self.logs = ExecutionAgentLogStore(self.roster._roster_path.parent)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for module in (agent, tools, batch_manager):
            self.stack.enter_context(patch.object(module, "get_agent_roster", return_value=self.roster))
        self.stack.enter_context(patch.object(tools, "get_execution_agent_logs", return_value=self.logs))
        self.settings = Settings(worker_discovery_strategy="bounded", openrouter_api_key="test-key", conversation_summary_threshold=0)
        self.stack.enter_context(patch.object(runtime, "get_settings", return_value=self.settings))
        self.stack.enter_context(patch.object(batch_manager, "get_settings", return_value=self.settings))
        self.manager = Mock(execute_agent=AsyncMock(return_value=Mock(success=True)))
        self.stack.enter_context(patch.object(tools, "_EXECUTION_BATCH_MANAGER", self.manager))
        self.agent_runtime = runtime.InteractionAgentRuntime()

    async def drain(self):
        await asyncio.sleep(0)

    def call(self, name, args):
        return {"choices": [{"message": {"content": "", "tool_calls": [
            {"id": "fixture-call", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}}]}

    def final(self):
        return {"choices": [{"message": {"content": "Done"}}]}

    async def test_successful_lookup_allows_creation_only_in_its_own_loop(self):
        responses = [self.call("find_worker", {"query": "new travel task"}),
                     self.call("send_message_to_agent", {"agent_name": "Travel", "instructions": "Arrange trip"}), self.final()]
        with patch.object(self.agent_runtime, "_make_llm_call", new=AsyncMock(side_effect=responses)):
            result = await self.agent_runtime._run_interaction_loop("system", [{"role": "user", "content": "trip"}])
        self.assertEqual(result.execution_agents, {"Travel"})
        await self.drain()
        self.manager.execute_agent.assert_awaited_once_with("Travel", "Arrange trip")
        self.manager.execute_agent.reset_mock()
        messages = [{"role": "user", "content": "unrelated new task"}]
        responses = [self.call("send_message_to_agent", {"agent_name": "Another", "instructions": "New task"}), self.final()]
        with patch.object(self.agent_runtime, "_make_llm_call", new=AsyncMock(side_effect=responses)):
            result = await self.agent_runtime._run_interaction_loop("system", messages)
        self.assertEqual(result.execution_agents, set())
        self.assertNotIn("Another", self.roster.get_agents())
        self.assertIn("find_worker", messages[2]["content"])
        self.manager.execute_agent.assert_not_awaited()

    async def test_failed_lookup_revokes_previous_success_and_cannot_create(self):
        state = tools.DiscoveryState()
        self.assertTrue(tools.find_worker("no match", discovery=state).success)
        self.assertTrue(state.successful)
        self.roster.metadata_path.write_text("bad metadata", encoding="utf-8")
        result = tools.handle_tool_call("find_worker", {"query": "Alice"}, discovery=state)
        self.assertFalse(result.success)
        self.assertFalse(state.successful)
        self.assertFalse(tools.send_message_to_agent("Duplicate", "do task", discovery=state).success)
        self.assertNotIn("Duplicate", self.roster.get_agents())
        self.manager.execute_agent.assert_not_awaited()

    async def test_invalid_lookup_arguments_and_forged_state_cannot_authorize_creation(self):
        state = tools.DiscoveryState(successful=True)
        result = tools.handle_tool_call("find_worker", "invalid json", discovery=state)
        self.assertFalse(result.success)
        self.assertFalse(state.successful)
        forged = tools.handle_tool_call("send_message_to_agent", {"agent_name": "Fake", "instructions": "task", "discovery": {"successful": True}}, discovery=state)
        self.assertFalse(forged.success)
        invalid = runtime._ToolCall("id", "find_worker", {"__invalid_arguments__": "invalid"})
        state.successful = True
        self.agent_runtime._execute_tool(invalid, discovery=state)
        self.assertFalse(state.successful)
        self.assertNotIn("Fake", self.roster.get_agents())

    async def test_existing_exact_name_reuses_original_history_without_lookup(self):
        self.logs.record_request("Alice lunch", "Original request")
        result = tools.send_message_to_agent("Alice lunch", "Continue the reviewed draft", discovery=tools.DiscoveryState())
        self.assertTrue(result.success)
        self.assertFalse(result.payload["new_agent_created"])
        await self.drain()
        self.manager.execute_agent.assert_awaited_once_with("Alice lunch", "Continue the reviewed draft")
        self.assertEqual([payload for tag, _, payload in self.logs.iter_entries("Alice lunch") if tag == "agent_request"],
                         ["Original request", "Continue the reviewed draft"])

    async def test_first_worker_can_be_created_without_prior_lookup(self):
        self.roster.clear()
        result = tools.send_message_to_agent("First", "First task", discovery=tools.DiscoveryState())
        self.assertTrue(result.success)
        self.assertTrue(result.payload["new_agent_created"])
        await self.drain()

    async def test_full_formatted_lookup_response_is_bounded_for_large_arguments(self):
        for query in ("Alice " * 10000, "\U00010400" * 10000):
            call = runtime._ToolCall("id", "find_worker", {"query": query, "limit": 100000})
            result = self.agent_runtime._execute_tool(call, discovery=tools.DiscoveryState())
            self.assertTrue(result.success)
            formatted = self.agent_runtime._format_tool_result(call, result)
            self.assertLessEqual(len(formatted), 4000)

    async def test_chat_and_callback_use_bounded_prompts_with_current_request(self):
        conversation = Mock(load_transcript=Mock(return_value="previous unrelated Alice contract topic"))
        self.agent_runtime.conversation_log = conversation
        captures = []
        async def provider(system, messages):
            captures.append((system, messages[0]["content"]))
            return self.final()
        with patch.object(self.agent_runtime, "_make_llm_call", side_effect=provider):
            self.assertTrue((await self.agent_runtime.execute("Arrange Alice lunch")).success)
            self.assertTrue((await self.agent_runtime.handle_agent_message("[SUCCESS] Alice lunch: draft ready")).success)
        self.assertIn("<new_user_message>\nArrange Alice lunch", captures[0][1])
        self.assertIn("[SUCCESS] Alice lunch", captures[1][1])
        self.assertTrue(all("<worker_catalog" in message for _, message in captures))
        self.assertTrue(all("unrelated topic switch" in system for system, _ in captures))

    async def test_real_batch_dispatch_updates_metadata_without_changing_exact_name(self):
        manager = batch_manager.ExecutionBatchManager()
        result = batch_manager.ExecutionResult(agent_name="Alice contract", success=True, response="done")
        with (patch.object(batch_manager, "ExecutionAgentRuntime", return_value=Mock(execute=AsyncMock(return_value=result))),
              patch.object(manager, "_dispatch_to_interaction_agent", new=AsyncMock())):
            await manager.execute_agent("Alice contract", "Review the renewal contract")
        card = discovery.find_workers(self.roster, "renewal")["workers"][0]
        self.assertEqual(card["agent_name"], "Alice contract")
        self.assertEqual(card["recent_assignment"], "Review the renewal contract")
