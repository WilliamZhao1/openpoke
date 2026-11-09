from contextlib import ExitStack
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from server import content_store
from server import context_recovery as recovery
from server import context_builder
from server.config import Settings
from server.content_store import ContentStore, capture_scope
from server.agents.execution_agent import agent as worker_agent, runtime as worker_runtime
from server.agents.execution_agent.tools import registry
from server.agents.interaction_agent import runtime as interaction_runtime, tools
from server.services.conversation.log import ConversationLog
from server.services.conversation.summarization.working_memory_log import WorkingMemoryLog
from server.services.execution import AgentRoster, ExecutionAgentLogStore


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(content_store, "get_data_dir", return_value=self.root))
        self.stack.enter_context(patch.object(content_store, "get_settings", return_value=SimpleNamespace(context_strategy="bounded")))
        self.settings = Settings(openrouter_api_key="test-key", conversation_summary_threshold=0,
                                 context_strategy="bounded", worker_discovery_strategy="bounded",
                                 model_context_windows={"anthropic/claude-sonnet-4.6": 200000})
        self.stack.enter_context(patch("server.services.conversation.log.get_settings", return_value=self.settings))
        self.memory = WorkingMemoryLog(self.root / "memory.log")
        self.stack.enter_context(patch("server.services.conversation.log._resolve_working_memory_log", return_value=self.memory))
        self.log = ConversationLog(self.root / "conversation" / "poke_conversation.log")
        self.logs = ExecutionAgentLogStore(self.root / "execution_agents")
        self.roster = AgentRoster(self.root / "execution_agents" / "roster.json")
        self.roster.add_agent("Alice lunch")
        self.roster.add_agent("Alice contract")
        self.stack.enter_context(patch.object(recovery, "get_conversation_log", return_value=self.log))
        self.stack.enter_context(patch.object(recovery, "get_execution_agent_logs", return_value=self.logs))
        self.stack.enter_context(patch.object(recovery, "get_agent_roster", return_value=self.roster))
        self.stack.enter_context(patch.object(context_builder, "get_agent_roster", return_value=self.roster))
        self.store = ContentStore(self.root / "content")
        self.generation = self.store.generation()

    def put(self, text, **kwargs):
        return self.store.put_text(text, **{"owner": "worker:Alice lunch", "generation": self.generation,
                                           "kind": "tool_result", **kwargs})

    def call(self, name, args=None, *, owner="worker:Alice lunch", budget=None):
        with capture_scope(owner):
            return recovery.handle_recovery_tool(name, args or {}, expected_owner=owner,
                                                 budget=budget if budget is not None else recovery.RecoveryBudget())

    def assert_ok(self, result):
        self.assertEqual(result["status"], "ok", result)
        self.assertLessEqual(recovery._size(result), recovery.RESPONSE_BYTES - 512)

    def test_result_paging_recovers_exact_unicode_crlf_and_middle_detail(self):
        text = "first\r\n" + "旅🦉" * 600 + "MIDDLE FACT" + "\x00\\\r\n" * 300
        reference = self.put(text)
        offset, pages, budget = 0, [], recovery.RecoveryBudget()
        while True:
            page = self.call("read_result", {"reference": reference, "offset": offset}, budget=budget)
            self.assert_ok(page)
            self.assertLessEqual(len(page["text"].encode()), recovery.PAGE_BYTES)
            pages.append(page["text"])
            if page["next_offset"] is None:
                break
            self.assertGreater(page["next_offset"], offset)
            offset = page["next_offset"]
        self.assertEqual("".join(pages), text)
        self.assertEqual(page["sha256"], sha256(text.encode()).hexdigest())
        self.assertEqual(page["size_bytes"], len(text.encode()))

    def test_json_escaping_and_actual_runtime_wrappers_are_bounded(self):
        reference = self.put("\x00" * 10000)
        page = self.call("read_result", {"reference": reference, "limit": 999999})
        self.assert_ok(page)
        self.assertLess(len(page["text"].encode()), recovery.PAGE_BYTES)
        agent = worker_runtime.ExecutionAgentRuntime.__new__(worker_runtime.ExecutionAgentRuntime)
        formatted = agent._format_tool_result("read_result", True, page, {"reference": "giant" * 10000})
        self.assertLessEqual(len(formatted.encode()), recovery.RESPONSE_BYTES)
        call = interaction_runtime._ToolCall("r", "read_result", {"reference": "giant" * 10000})
        interaction = interaction_runtime.InteractionAgentRuntime.__new__(interaction_runtime.InteractionAgentRuntime)
        formatted = interaction._format_tool_result(call, tools.ToolResult(True, page))
        self.assertLessEqual(len(formatted.encode()), recovery.RESPONSE_BYTES)
        self.assertEqual(json.loads(formatted)["arguments"], {})
        giant_metadata = self.call("read_result", {"reference": self.put("source", kind="k" * 20000)})
        self.assertEqual(giant_metadata["code"], "response_limit")
        self.assertLessEqual(recovery._size(giant_metadata), recovery.RESPONSE_BYTES)
        formatted_error = json.loads(agent._format_tool_result("read_result", False, giant_metadata, {}))
        self.assertEqual(formatted_error["error"]["code"], "response_limit")

    def test_mailbox_qualification_is_preserved_without_using_the_active_account(self):
        reference = self.put("from mailbox A", provider="gmail", account_id="account-a")
        with patch("server.services.gmail.get_active_gmail_user_id", side_effect=AssertionError("Do not rebind sources")):
            page = self.call("read_result", {"reference": reference})
        self.assert_ok(page)
        self.assertEqual((page["provider"], page["account_id"]), ("gmail", "account-a"))
        unknown = self.call("read_result", {"reference": self.put("unknown", provider="gmail")})
        self.assertIsNone(unknown["account_id"])
        with self.assertRaises(content_store.ContentStoreError):
            self.store.read_page(reference, owner="worker:Alice lunch", provider="gmail", account_id="account-b")
        self.assertEqual(self.call("read_result", {"reference": reference, "account_id": "account-b"})["code"], "invalid_arguments")

    def test_owner_selection_is_exact_and_cannot_be_overridden_by_a_worker(self):
        reference = self.put("contract fact", owner="worker:Alice contract")
        self.assertEqual(self.call("read_result", {"reference": reference})["code"], "source_unavailable")
        self.assertEqual(self.call("read_result", {"reference": reference, "agent_name": "Alice contract"})["code"], "wrong_owner")
        self.assertEqual(self.call("read_result", {"reference": reference}, owner="conversation")["code"], "source_unavailable")
        selected = self.call("read_result", {"reference": reference, "agent_name": "Alice contract"}, owner="conversation")
        self.assert_ok(selected)
        self.assertEqual(selected["owner"], "worker:Alice contract")
        self.assertEqual(self.call("recall_history", {"agent_name": "Alice"}, owner="conversation")["code"], "unknown_worker")

    def test_invalid_arguments_paths_offsets_and_missing_content_fail_explicitly(self):
        reference = self.put("🦉 content")
        cases = [{"reference": "../../secrets"}, {"reference": reference, "offset": True},
                 {"reference": reference, "offset": -1}, {"reference": reference, "offset": 1},
                 {"reference": reference, "limit": False}, {"reference": reference, "owner": "conversation"},
                 {"reference": reference, "path": str(self.root)}, {}]
        for args in cases:
            with self.subTest(args=args):
                result = self.call("read_result", args)
                self.assertEqual(result["status"], "error")
                self.assertNotIn(str(self.root), json.dumps(result))
        empty = self.call("read_result", {"reference": self.put("")})
        self.assert_ok(empty)
        self.assertEqual(empty["text"], "")
        self.assertIsNone(empty["next_offset"])
        short = self.call("read_result", {"reference": reference, "limit": -10})
        self.assertEqual(short["text"], "🦉")
        metadata_path = self.store.root / "objects" / self.generation / reference.rsplit("_", 1)[-1] / "metadata.json"
        original_metadata = metadata_path.read_text(encoding="utf-8")
        metadata = json.loads(original_metadata)
        del metadata["kind"]
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        self.assertEqual(self.call("read_result", {"reference": reference})["code"], "source_unavailable")
        metadata_path.write_text(original_metadata, encoding="utf-8")
        (self.store.root / "objects" / self.generation / reference.rsplit("_", 1)[-1] / "body.txt").unlink()
        self.assertEqual(self.call("read_result", {"reference": reference})["code"], "source_unavailable")

    def test_legacy_history_pages_are_bounded_and_preserve_logged_bytes(self):
        self.logs.record_request("Alice lunch", "older\nrequest旅" * 500)
        self.logs.record_tool_response("Alice lunch", "gmail", "historically shortened...")
        path = self.logs._log_path("Alice lunch")
        original = path.read_bytes()
        cursor, parts, budget = None, [], recovery.RecoveryBudget()
        while True:
            page = self.call("recall_history", {"cursor": cursor}, budget=budget)
            self.assert_ok(page)
            parts.append(page["text"])
            self.assertIn("historically truncated", page["limitation"])
            self.assertIsNone(page["account_id"])
            if page["next_cursor"] is None:
                break
            cursor = page["next_cursor"]
        self.assertEqual("".join(parts).encode(), original)
        self.assertEqual(path.read_bytes(), original)

    def test_selected_history_search_streams_one_file_and_distinguishes_partial_scan(self):
        path = self.logs._log_path("Alice lunch")
        path.write_bytes(b"<agent_request>" + b"x" * (recovery.SCAN_BYTES + 2000) + b"MIDDLE SECRET</agent_request>\n")
        other = self.logs._log_path("Alice contract")
        other.write_text("must not read")
        opened = []
        original_open = Path.open

        def track(selected, *args, **kwargs):
            if selected.suffix == ".log":
                opened.append(selected)
                self.assertEqual(selected, path)
            return original_open(selected, *args, **kwargs)

        budget = recovery.RecoveryBudget()
        with patch.object(Path, "open", track), patch.object(self.logs, "load_transcript", side_effect=AssertionError("unbounded")), patch.object(self.logs, "iter_entries", side_effect=AssertionError("unbounded")):
            first = self.call("recall_history", {"query": "MIDDLE SECRET"}, budget=budget)
            self.assert_ok(first)
            self.assertFalse(first["match_found"])
            self.assertFalse(first["complete"])
            self.assertIsNotNone(first["next_cursor"])
            self.assertLessEqual(first["scanned_bytes"], recovery.SCAN_BYTES)
            second = self.call("recall_history", {"query": "MIDDLE SECRET", "cursor": first["next_cursor"]}, budget=budget)
        self.assert_ok(second)
        self.assertTrue(second["match_found"])
        self.assertIn("MIDDLE SECRET", second["text"])
        self.assertEqual(set(opened), {path})
        no_match = self.call("recall_history", {"query": "absent"})
        while no_match["next_cursor"]:
            no_match = self.call("recall_history", {"query": "absent", "cursor": no_match["next_cursor"]})
        self.assertFalse(no_match["match_found"])
        self.assertTrue(no_match["complete"])

    def test_search_finds_matches_across_chunks_and_scan_pages(self):
        path = self.logs._log_path("Alice lunch")
        for boundary in (4096, recovery.SCAN_BYTES - recovery.PAGE_BYTES):
            with self.subTest(boundary=boundary):
                path.write_bytes(b"x" * (boundary - 3) + b"needle" + b" end")
                result = self.call("recall_history", {"query": "needle"})
                if not result["match_found"]:
                    result = self.call("recall_history", {"query": "needle", "cursor": result["next_cursor"]})
                self.assert_ok(result)
                self.assertIn("needle", result["text"])
        self.logs.record_request("Alice lunch", "XML <&>\n旅")
        result = self.call("recall_history", {"query": "XML <&>\n旅"})
        while result["next_cursor"] and not result["match_found"]:
            result = self.call("recall_history", {"query": "XML <&>\n旅", "cursor": result["next_cursor"]})
        self.assertTrue(result["match_found"])
        self.assertIn("XML &lt;&amp;&gt;\\n旅", result["text"])

    def test_conversation_selection_and_missing_history_are_distinct_from_no_matches(self):
        missing = self.call("recall_history", owner="conversation")
        self.assertEqual(missing["code"], "source_unavailable")
        self.log.record_user_message("conversation only")
        self.logs.record_request("Alice lunch", "worker only")
        conversation = self.call("recall_history", owner="conversation")
        worker = self.call("recall_history", {"agent_name": "Alice lunch"}, owner="conversation")
        self.assertIn("conversation only", conversation["text"])
        self.assertNotIn("worker only", conversation["text"])
        self.assertIn("worker only", worker["text"])
        no_match = self.call("recall_history", {"query": "absent"}, owner="conversation")
        self.assertEqual(no_match["status"], "ok")
        self.assertFalse(no_match["match_found"])
        self.assertTrue(no_match["complete"])

    def test_history_cursors_pin_source_query_snapshot_and_generation(self):
        self.logs.record_request("Alice lunch", "x" * 100)
        first = self.call("recall_history", {"limit": 16})
        cursor = first["next_cursor"]
        end = first["snapshot_bytes"]
        self.logs.record_request("Alice lunch", "appended later")
        remaining = self.call("recall_history", {"cursor": cursor})
        self.assert_ok(remaining)
        self.assertEqual(remaining["snapshot_bytes"], end)
        self.assertNotIn("appended later", remaining["text"])
        self.assertEqual(self.call("recall_history", {"cursor": cursor, "query": "different"})["code"], "invalid_cursor")
        self.assertEqual(self.call("recall_history", {"cursor": cursor}, owner="worker:Alice contract")["code"], "invalid_cursor")
        self.store.clear()
        self.assertEqual(self.call("recall_history", {"cursor": cursor})["code"], "invalid_cursor")

    def test_replaced_truncated_and_malformed_history_cursors_fail_explicitly(self):
        path = self.logs._log_path("Alice lunch")
        path.write_text("x" * 200)
        cursor = self.call("recall_history", {"limit": 16})["next_cursor"]
        replacement = path.with_suffix(".replacement")
        replacement.write_text("y" * 200)
        os.replace(replacement, path)
        self.assertEqual(self.call("recall_history", {"cursor": cursor})["code"], "source_changed")
        cursor = self.call("recall_history", {"limit": 16})["next_cursor"]
        path.write_text("short")
        self.assertEqual(self.call("recall_history", {"cursor": cursor})["code"], "source_changed")
        for cursor in ("../../file", "h1_!", "h1_" + "x" * 3000, recovery._cursor({"offset": 1})):
            self.assertEqual(self.call("recall_history", {"cursor": cursor})["code"], "invalid_arguments")

    def test_lookup_failure_and_historical_filename_collision_never_guess_an_owner(self):
        self.logs.record_request("Alice lunch", "lunch only")
        self.assertEqual(self.call("recall_history", owner="worker:Alice-lunch")["code"], "unknown_worker")
        self.roster._roster_path.write_text(json.dumps(["Alice lunch", "Alice-lunch"]))
        self.logs.record_request("Alice lunch", "mixed unknown owners")
        self.assertEqual(self.call("recall_history")["code"], "ambiguous_history")
        self.roster._roster_path.write_text("broken JSON")
        self.assertEqual(self.call("recall_history", {"agent_name": "Alice lunch"}, owner="conversation")["code"], "lookup_unavailable")

    def test_per_turn_call_scan_and_response_limits_stop_recovery(self):
        reference = self.put("\x00" * 10000)
        budget = recovery.RecoveryBudget()
        for _ in range(8):
            self.call("read_result", {"reference": reference}, budget=budget)
        self.assertLessEqual(budget.response_bytes, recovery.TURN_RESPONSE_BYTES)
        with patch.object(ContentStore, "read_source_page", side_effect=AssertionError("limit must stop IO")):
            self.assertEqual(self.call("read_result", {"reference": reference}, budget=budget)["code"], "turn_limit")
        path = self.logs._log_path("Alice lunch")
        path.write_bytes(b"x" * (recovery.TURN_SCAN_BYTES * 2))
        budget, cursor = recovery.RecoveryBudget(), None
        for _ in range(6):
            result = self.call("recall_history", {"query": "absent", "cursor": cursor}, budget=budget)
            if result["status"] == "error":
                break
            cursor = result["next_cursor"]
        self.assertEqual(result["code"], "work_limit")
        self.assertLessEqual(budget.scanned_bytes, recovery.TURN_SCAN_BYTES)

    def test_history_clear_and_clear_during_a_read_invalidate_results(self):
        reference = self.put("old text")
        read = ContentStore.read_source_page

        def clearing(store, *args, **kwargs):
            result = read(store, *args, **kwargs)
            store.clear()
            return result

        with patch.object(ContentStore, "read_source_page", clearing):
            result = self.call("read_result", {"reference": reference})
        self.assertEqual(result["code"], "expired")
        self.assertNotIn("old text", json.dumps(result))
        self.assertEqual(self.call("read_result", {"reference": reference})["code"], "expired")

    def test_recovery_restarts_without_in_memory_cursor_or_reference_state(self):
        reference = self.put("persisted mailbox text", provider="gmail", account_id="account-a")
        self.logs.record_request("Alice lunch", "persisted history" * 100)
        cursor = self.call("recall_history", {"limit": 32})["next_cursor"]
        script = """
import json, socket, sys
from types import SimpleNamespace
from unittest.mock import patch
def reject(*args, **kwargs):
    raise AssertionError('No network in restart tests')
socket.socket.connect = socket.socket.connect_ex = reject
from server import content_store, context_recovery as r
reference, cursor = sys.argv[1:]
with patch.object(content_store, 'get_settings', return_value=SimpleNamespace(context_strategy='bounded')):
    with content_store.capture_scope('worker:Alice lunch'):
        data = [r.handle_recovery_tool(name, args, expected_owner='worker:Alice lunch', budget=r.RecoveryBudget())
                for name, args in [('read_result', {'reference': reference}), ('recall_history', {'cursor': cursor})]]
print(json.dumps(data))
"""
        environment = dict(os.environ, OPENPOKE_DATA_DIR=str(self.root), OPENROUTER_API_KEY="test-key",
                           COMPOSIO_API_KEY="test-key", COMPOSIO_GMAIL_AUTH_CONFIG_ID="test-auth",
                           OPENPOKE_CONTEXT_STRATEGY="legacy", OPENPOKE_MODEL_CONTEXT_WINDOWS="{}")
        result = subprocess.run([sys.executable, "-c", script, reference, cursor], env=environment,
                                capture_output=True, text=True, timeout=15, cwd=Path(__file__).resolve().parents[2])
        self.assertEqual(result.returncode, 0, result.stderr)
        content, history = json.loads(result.stdout)
        self.assertEqual(content["text"], "persisted mailbox text")
        self.assertEqual(content["account_id"], "account-a")
        self.assert_ok(history)
        self.assertIn("persisted history", history["text"])

    def test_tools_are_executable_only_with_a_backend_owned_scope_and_budget(self):
        handlers = recovery.build_registry("worker:Alice lunch")
        reference = self.put("source")
        self.assertEqual(handlers["read_result"](reference=reference)["code"], "unavailable")
        self.assertEqual(handlers["read_result"](reference=reference, _budget=recovery.RecoveryBudget())["code"], "wrong_owner")
        with capture_scope("worker:Alice contract"):
            self.assertEqual(handlers["read_result"](reference=reference, _budget=recovery.RecoveryBudget())["code"], "wrong_owner")
        self.assertEqual({s["function"]["name"] for s in recovery.SCHEMAS}, set(handlers))
        for bounded in (False, True):
            schemas = registry.get_tool_schemas(bounded_context=bounded)
            handlers = registry.get_tool_registry("Alice lunch", bounded_context=bounded)
            self.assertEqual({s["function"]["name"] for s in schemas}, set(handlers))
            self.assertEqual(recovery.RECOVERY_NAMES <= set(handlers), bounded)
            names = {s["function"]["name"] for s in tools.get_tool_schemas(recovery=bounded)}
            self.assertEqual(recovery.RECOVERY_NAMES <= names, bounded)

    async def test_both_runtime_loops_execute_recovery_and_preserve_tool_pairs(self):
        reference = self.put("WORKER MIDDLE FACT")
        self.logs.record_content_reference("Alice lunch", reference, "tool_result")
        self.log.record_user_message("CONVERSATION FACT")
        self.stack.enter_context(patch.object(worker_runtime, "get_settings", return_value=self.settings))
        self.stack.enter_context(patch.object(worker_agent, "get_execution_agent_logs", return_value=self.logs))
        self.stack.enter_context(patch.object(interaction_runtime, "get_settings", return_value=self.settings))
        self.stack.enter_context(patch.object(interaction_runtime, "get_conversation_log", return_value=self.log))
        self.stack.enter_context(patch.object(interaction_runtime, "get_working_memory_log", return_value=self.memory))
        self.stack.enter_context(patch("server.agents.interaction_agent.agent.get_agent_roster", return_value=self.roster))

        def invoke(name, args):
            return {"choices": [{"message": {"content": "", "tool_calls": [
                {"id": "source-call", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}}]}

        for kind in ("worker", "interaction"):
            with self.subTest(kind=kind):
                runtime = worker_runtime.ExecutionAgentRuntime("Alice lunch") if kind == "worker" else interaction_runtime.InteractionAgentRuntime()
                snapshots = []
                responses = iter([invoke("read_result", {"reference": reference}) if kind == "worker" else invoke("recall_history", {}),
                                  {"choices": [{"message": {"content": "Done"}}]}])

                async def respond(system, messages, **kwargs):
                    if kind == "worker":
                        self.assertIn(reference, json.dumps(messages))
                    snapshots.append(json.loads(json.dumps(messages)))
                    return next(responses)

                with patch.object(runtime, "_make_llm_call", side_effect=respond):
                    result = await runtime.execute("Recover the source")
                self.assertTrue(result.success, result)
                second = snapshots[1]
                self.assertEqual(second[-2]["tool_calls"][0]["id"], second[-1]["tool_call_id"])
                self.assertEqual(second[-1]["role"], "tool")
                self.assertIn("WORKER MIDDLE FACT" if kind == "worker" else "CONVERSATION FACT", second[-1]["content"])

    async def test_runtime_counters_reset_between_turns_and_legacy_has_no_recovery_tools(self):
        self.stack.enter_context(patch.object(interaction_runtime, "get_settings", return_value=self.settings))
        runtime = interaction_runtime.InteractionAgentRuntime()
        seen = []

        def handle(name, args, **kwargs):
            budget = kwargs["recovery"]
            seen.append(budget)
            budget.calls += 1
            return tools.ToolResult(True, {"status": "ok"})

        call = {"choices": [{"message": {"tool_calls": [{"id": "r", "function": {"name": "recall_history", "arguments": "{}"}}]}}]}
        final = {"choices": [{"message": {"content": "done"}}]}
        with patch.object(interaction_runtime, "handle_tool_call", side_effect=handle):
            for _ in range(2):
                with capture_scope("conversation"), patch.object(runtime, "_make_llm_call", new=AsyncMock(side_effect=[call, final])):
                    await runtime._run_interaction_loop("system", [{"role": "user", "content": "read"}])
        self.assertIsNot(seen[0], seen[1])
        self.assertEqual([budget.calls for budget in seen], [1, 1])
        legacy = self.settings.model_copy(update={"context_strategy": "legacy"})
        with patch.object(interaction_runtime, "get_settings", return_value=legacy), patch.object(worker_runtime, "get_settings", return_value=legacy):
            for runtime in (interaction_runtime.InteractionAgentRuntime(), worker_runtime.ExecutionAgentRuntime("Alice lunch")):
                self.assertFalse(recovery.RECOVERY_NAMES & {s["function"]["name"] for s in runtime.tool_schemas})
