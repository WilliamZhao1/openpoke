from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

from server import content_store, context_builder as contexts
from server.config import Settings
from server.content_store import ContentStore, capture_scope
from server.context_budget import ContextBudgetError, prepare_budgeted_request
from server.context_recovery import GUIDANCE
from server.agents.execution_agent import runtime as workers, agent as worker_agent
from server.agents.execution_agent.tools import gmail
from server.agents.interaction_agent import runtime as interactions, agent as interaction_agent, tools
from server.openrouter_client import client
from server.services.conversation.log import ConversationLog
from server.services.conversation.summarization.working_memory_log import WorkingMemoryLog
from server.services.execution import AgentRoster, ExecutionAgentLogStore


MODEL = "context-test"
MODEL_FIELDS = ("interaction_agent_model", "execution_agent_model", "execution_agent_search_model", "summarizer_model", "email_classifier_model")


def tool_group(identifier, content, *, arguments="{}"):
    return [{"role": "assistant", "content": "", "tool_calls": [{"id": identifier, "type": "function",
             "function": {"name": "lookup", "arguments": arguments}}]},
            {"role": "tool", "tool_call_id": identifier, "content": content}]


class ContextBuilderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.settings = Settings(**{**dict.fromkeys(MODEL_FIELDS, MODEL), "context_strategy": "bounded",
                                   "worker_discovery_strategy": "bounded", "model_context_windows": {MODEL: 200000},
                                   "context_input_tokens": 32768, "context_headroom_tokens": 64,
                                   "openrouter_max_tokens": 256, "openrouter_api_key": "test-key", "conversation_summary_threshold": 0})
        self.memory = WorkingMemoryLog(self.root / "memory.log")
        self.stack.enter_context(patch("server.services.conversation.log._resolve_working_memory_log", return_value=self.memory))
        self.log = ConversationLog(self.root / "conversation.log")
        self.logs = ExecutionAgentLogStore(self.root / "execution_agents")
        self.roster = AgentRoster(self.root / "execution_agents" / "roster.json")
        for name in ("Alice lunch", "Alice contract"):
            self.roster.add_agent(name)
        self.stack.enter_context(patch.object(content_store, "get_data_dir", return_value=self.root))
        for module in (content_store, workers, interactions, client):
            self.stack.enter_context(patch.object(module, "get_settings", return_value=self.settings))
        self.stack.enter_context(patch("server.services.conversation.log.get_settings", return_value=self.settings))
        self.stack.enter_context(patch.object(contexts, "get_agent_roster", return_value=self.roster))
        self.stack.enter_context(patch.object(worker_agent, "get_execution_agent_logs", return_value=self.logs))
        self.stack.enter_context(patch.object(interactions, "get_conversation_log", return_value=self.log))
        self.stack.enter_context(patch.object(interactions, "get_working_memory_log", return_value=self.memory))
        self.stack.enter_context(patch.object(interaction_agent, "get_agent_roster", return_value=self.roster))
        self.store = ContentStore(self.root / "content")

    def builder(self, *, history=None, cap=10000):
        return contexts.ContextBuilder(settings=self.settings.model_copy(update={"context_input_tokens": cap}),
                                       model=MODEL, tools=[], history=history, record_reference=self.log.record_content_reference)

    def assert_fits(self, system, messages, *, cap=10000, tools=None):
        payload = {"model": MODEL, "messages": [{"role": "system", "content": system + "\n\n" + GUIDANCE}, *messages],
                   "max_tokens": 256, "stream": False}
        if tools:
            payload["tools"] = tools
        return prepare_budgeted_request(payload, context_window=200000, input_cap=cap, headroom=64)

    def read_all(self, reference, *, owner="conversation"):
        offset, chunks = 0, []
        while True:
            page = self.store.read_source_page(reference, owner=owner, offset=offset, limit=65536)
            chunks.append(page.content)
            if page.next_offset is None:
                return b"".join(chunks).decode()
            offset = page.next_offset

    def test_bounded_tail_keeps_recent_whole_episodes_without_full_transcript_reads(self):
        for i in range(1000):
            self.logs.record_request("Alice lunch", f"request-{i} " + "旅\u2028\u0085" * 100)
            self.logs.record_agent_response("Alice lunch", f"reply-{i}")
        original = self.logs._log_path("Alice lunch").read_bytes()
        with patch.object(self.logs, "load_transcript", side_effect=AssertionError("unbounded")), patch.object(self.logs, "iter_entries", side_effect=AssertionError("unbounded")):
            history = contexts.load_recent_history(self.logs, worker_name="Alice lunch")
        self.assertTrue(history.omitted)
        self.assertEqual(len(history.episodes), contexts.HISTORY_EPISODES)
        self.assertIn("request-999", history.episodes[-1])
        self.assertIn("reply-999", history.episodes[-1])
        self.assertNotIn("request-0 ", "".join(history.episodes))
        self.assertTrue(all('status="complete"' in episode for episode in history.episodes))
        self.assertEqual(self.logs._log_path("Alice lunch").read_bytes(), original)

    def test_dispatch_current_request_does_not_displace_the_previous_draft_episode(self):
        self.logs.record_request("Alice lunch", "Create the lunch draft")
        self.logs.record_agent_response("Alice lunch", "draft=d-1; to=alice@example.test; body=exact lunch text")
        self.logs.record_request("Alice lunch", "yes, send it")
        history = contexts.load_recent_history(self.logs, worker_name="Alice lunch", current_request="yes, send it")
        self.assertEqual(len(history.episodes), 1)
        self.assertIn("draft=d-1", history.episodes[-1])
        self.assertNotIn("yes, send it", history.episodes[-1])
        self.assertTrue(history.current_recorded)

    def test_summary_and_latest_followup_evidence_are_pinned_while_old_history_is_recoverable(self):
        for i in range(4):
            self.log.record_user_message(f"old-{i}" + "x" * 3000)
            self.log.record_reply(f"reply-{i}")
        self.log.record_agent_message("[SUCCESS] Alice contract: draft d-2")
        self.log.record_reply("To: alice@example.test\nSubject: Contract\nEXACT DRAFT TEXT")
        self.memory._path.write_text('<summary_info>{}</summary_info>\n<conversation_summary>Always retain the approval rule &amp; recipients.</conversation_summary>\n' + 'unused tail' * 30000, encoding="utf-8")
        with patch.object(self.memory, "render_transcript", side_effect=AssertionError("unbounded")), patch.object(self.memory, "load_summary_state", side_effect=AssertionError("unbounded")):
            history = contexts.load_recent_history(self.log, summary_log=self.memory)
        current = [{"role": "user", "content": "yes, send it"}]
        with capture_scope("conversation"):
            system, messages = self.builder(history=history, cap=5000).build("Required send confirmation rule", current)
        self.assert_fits(system, messages, cap=5000)
        self.assertIn("Always retain the approval rule &amp; recipients.", messages[0]["content"])
        self.assertIn("EXACT DRAFT TEXT", messages[0]["content"])
        self.assertIn("Alice contract", messages[0]["content"])
        self.assertIn("recall_history", messages[0]["content"])
        self.assertNotIn("old-3", messages[0]["content"])
        self.assertIn("old-3", self.log._path.read_text(encoding="utf-8"))
        self.assertEqual(current, [{"role": "user", "content": "yes, send it"}])

    def test_large_results_have_qualified_originals_and_exact_recoverable_composite_snapshots(self):
        raw = "first\r\n" + "旅🦉" * 6000 + "MIDDLE FACT\x00last"
        with capture_scope("conversation"):
            source = content_store.capture_text(raw, kind="gmail.result", provider="gmail", account_id="account-a")
            full = json.dumps({"result": raw, "source_references": [{"reference": source, "provider": "gmail", "account_id": "account-a"}]}, ensure_ascii=False)
            original = [{"role": "user", "content": "Find the middle fact"}, *tool_group("lookup-1", full)]
            before = deepcopy(original)
            builder = self.builder()
            system, messages = builder.build("Required rules", original)
            preview = json.loads(messages[-1]["content"])
            self.assertTrue(preview["preview"])
            self.assertEqual(preview["source_references"][0]["account_id"], "account-a")
            self.assertEqual(self.read_all(preview["reference"]), full)
            references = len(builder.references)
            self.assertEqual(builder.build("Required rules", original), (system, messages))
            self.assertEqual(len(builder.references), references)
        self.assertEqual(original, before)
        self.assertEqual(messages[-2]["tool_calls"], original[-2]["tool_calls"])
        self.assert_fits(system, messages)

    def test_dropped_tool_episodes_keep_complete_parallel_call_result_groups_in_the_archive(self):
        original = [{"role": "user", "content": "Current request"}]
        for i in range(7):
            original.extend(tool_group(f"old-{i}", "x" * 1900))
        last = tool_group("last-a", "Exact latest result")
        last[0]["tool_calls"].append(tool_group("last-b", "unused")[0]["tool_calls"][0])
        last.append({"role": "tool", "tool_call_id": "last-b", "content": "Second exact result"})
        original.extend(last)
        before = deepcopy(original)
        with capture_scope("conversation"), patch.object(contexts, "prepare_budgeted_request", wraps=prepare_budgeted_request) as count:
            builder = self.builder(cap=6000)
            system, messages = builder.build("Rules", original)
            self.assertLessEqual(count.call_count, 7)
            self.assertEqual(messages[-3:], last)
            archive = next(value for (kind, _), value in builder.references.items() if kind == "model_tool_episodes")
            self.assertEqual(json.loads(self.read_all(archive)), original[1:-3])
            self.assertIn(archive, messages[0]["content"])
        self.assertEqual(original, before)
        self.assert_fits(system, messages, cap=6000)

    def test_required_input_summary_latest_history_and_exact_tool_arguments_never_get_truncated(self):
        cases = [([{ "role": "user", "content": "旅" * 10000}], contexts.HistoryWindow()),
                 ([{"role": "user", "content": "yes"}], contexts.HistoryWindow(["latest draft " + "x" * 30000])),
                 ([{"role": "user", "content": "now"}], contexts.HistoryWindow(summary="standing instructions " + "x" * 30000)),
                 ([{"role": "user", "content": "review"}, *tool_group("draft", "created", arguments=json.dumps({"to": "exact@example.test", "body": "x" * 30000}))], contexts.HistoryWindow())]
        for messages, history in cases:
            with self.subTest(history=bool(history.episodes)), capture_scope("conversation"):
                original = deepcopy(messages)
                builder = self.builder(history=history)
                with patch.object(content_store.ContentStore, "put_text", side_effect=AssertionError("required floor must fail before preview writes")):
                    with self.assertRaisesRegex(ContextBudgetError, "Required context cannot fit"):
                        builder.build("Do not send without confirmation", messages)
                self.assertEqual(messages, original)

    def test_invalid_or_missing_pairs_fail_even_when_the_episode_would_have_been_omitted(self):
        invalid = [tool_group("missing", "result")[:1], tool_group("dup", "result")]
        invalid[1][0]["tool_calls"] *= 2
        invalid += [[{"role": "tool", "tool_call_id": "orphan", "content": "result"}],
                    [{"role": "assistant", "tool_calls": [{"function": {"name": "lookup"}}]}]]
        for groups in invalid:
            with self.subTest(groups=groups), capture_scope("conversation"):
                with self.assertRaises(ContextBudgetError):
                    self.builder().build("Rules", [{"role": "user", "content": "current"}, *groups, *tool_group("valid", "last")])

    def test_missing_huge_or_corrupt_history_is_explicit_and_collision_does_not_open_another_worker(self):
        self.assertEqual(contexts.load_recent_history(self.log).episodes, [])
        self.logs._log_path("Alice lunch").write_bytes(b"<agent_request>" + b"x" * (contexts.HISTORY_BYTES * 2) + b"</agent_request>\n")
        with self.assertRaisesRegex(ContextBudgetError, "Most recent history"):
            contexts.load_recent_history(self.logs, worker_name="Alice lunch")
        self.log._path.write_text("broken entry")
        with self.assertRaisesRegex(ContextBudgetError, "incomplete or invalid"):
            contexts.load_recent_history(self.log)
        with self.assertRaisesRegex(ContextBudgetError, "ownership"):
            contexts.load_recent_history(self.logs, worker_name="Alice-lunch")
        self.roster._roster_path.write_text(json.dumps(["Alice lunch", "Alice-lunch"]))
        with self.assertRaisesRegex(ContextBudgetError, "ambiguous"):
            contexts.load_recent_history(self.logs, worker_name="Alice lunch")

    def test_clear_invalidates_builder_cached_references_and_scope_is_required(self):
        with self.assertRaises(content_store.ContentStoreError):
            self.builder().build("Rules", [{"role": "user", "content": "current"}])
        with capture_scope("conversation"):
            builder = self.builder()
            original = [{"role": "user", "content": "current"}, *tool_group("large", "x" * 50000)]
            builder.build("Rules", original)
            self.assertTrue(builder.references)
            failing = self.builder()
            failing.record_reference = Mock(side_effect=OSError("journal unavailable"))
            with self.assertRaisesRegex(content_store.ContentStoreError, "journal reference failed"):
                failing.build("Rules", original)
            self.store.clear()
            with self.assertRaises(content_store.ContentExpiredError):
                builder.build("Rules", original)

    async def test_real_worker_gmail_result_is_previewed_and_recovered_under_provider_preflight(self):
        from server import context_recovery
        self.stack.enter_context(patch.object(context_recovery, "get_agent_roster", return_value=self.roster))
        self.stack.enter_context(patch.object(gmail, "_LOG_STORE", self.logs))
        self.stack.enter_context(patch.object(gmail, "get_active_gmail_user_id", return_value="account-a"))
        backend = self.stack.enter_context(patch.object(gmail, "execute_gmail_tool", return_value={"body": "x" * 50000 + "MIDDLE FACT" + "旅" * 10000}))
        requests = []

        def response(name, arguments):
            return {"choices": [{"message": {"tool_calls": [{"id": f"call-{len(requests)}", "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)}}]}}]}

        def respond(request):
            payload = json.loads(request.content)
            requests.append(payload)
            prepare_budgeted_request(payload, context_window=200000, input_cap=32768, headroom=64)
            if len(requests) == 1:
                result = response("gmail_list_drafts", {})
            elif len(requests) == 2:
                preview = json.loads(payload["messages"][-1]["content"])
                self.assertTrue(preview["preview"])
                self.assertIn("account-a", json.dumps(preview["source_references"]))
                full = self.read_all(preview["reference"], owner="worker:Alice lunch")
                result = response("read_result", {"reference": preview["reference"], "offset": full.encode().index(b"MIDDLE FACT"), "limit": 32})
            else:
                self.assertIn("MIDDLE FACT", payload["messages"][-1]["content"])
                result = {"choices": [{"message": {"content": "Recovered MIDDLE FACT"}}]}
            return httpx.Response(200, json=result)

        with client.use_mock_provider(httpx.MockTransport(respond)):
            result = await workers.ExecutionAgentRuntime("Alice lunch").execute("Find the middle fact; preserve mailbox provenance")
        self.assertTrue(result.success, result)
        self.assertEqual(len(requests), 3)
        backend.assert_called_once()
        for payload in requests:
            contexts._episodes(payload["messages"][1:])

    async def test_giant_user_and_combined_callback_are_saved_and_rejected_before_http(self):
        text = "Required instruction\r\n" + "旅🦉" * 10000 + "\r\nDo not send this message."
        for callback in (False, True):
            with self.subTest(callback=callback):
                self.log.clear()
                runtime = interactions.InteractionAgentRuntime()
                with patch.object(client.httpx, "AsyncClient", side_effect=AssertionError("required input must not reach HTTP")):
                    result = await (runtime.handle_agent_message("[SUCCESS] Alice lunch: " + text + "\n[SUCCESS] Alice contract: " + text) if callback else runtime.execute(text))
                self.assertFalse(result.success)
                self.assertIn("Required context cannot fit", result.error)
                refs = [json.loads(payload) for tag, _, payload in self.log.iter_entries() if tag == "content_reference"]
                original = self.read_all(refs[0]["reference"])
                self.assertIn(text, original)

    async def test_real_interaction_followup_retains_exact_draft_and_reuses_exact_worker(self):
        for i in range(20):
            self.log.record_user_message(f"unrelated-{i} " + "x" * 1000)
            self.log.record_reply("old answer")
        self.log.record_agent_message("[SUCCESS] Alice contract: created draft d-contract")
        self.log.record_reply("To: alice@example.test\nSubject: Contract\nEXACT approved draft body")
        self.stack.enter_context(patch.object(tools, "get_agent_roster", return_value=self.roster))
        self.stack.enter_context(patch.object(tools, "get_execution_agent_logs", return_value=self.logs))
        manager = Mock(execute_agent=AsyncMock(return_value=Mock(success=True)))
        self.stack.enter_context(patch.object(tools, "_EXECUTION_BATCH_MANAGER", manager))
        requests = []

        def respond(request):
            payload = json.loads(request.content)
            requests.append(payload)
            prepare_budgeted_request(payload, context_window=200000, input_cap=32768, headroom=64)
            if len(requests) == 1:
                current = payload["messages"][1]["content"]
                self.assertIn("EXACT approved draft body", current)
                self.assertIn("Alice contract", current)
                self.assertNotIn("unrelated-0 ", current)
                result = {"choices": [{"message": {"tool_calls": [{"id": "dispatch", "type": "function", "function": {
                    "name": "send_message_to_agent", "arguments": json.dumps({"agent_name": "Alice contract", "instructions": "User confirms draft d-contract; retain exact recipients and body"})}}]}}]}
            else:
                result = {"choices": [{"message": {"content": "Dispatched confirmation"}}]}
            return httpx.Response(200, json=result)

        with client.use_mock_provider(httpx.MockTransport(respond)):
            result = await interactions.InteractionAgentRuntime().execute("yes, send that draft")
        self.assertTrue(result.success, result)
        import asyncio
        await asyncio.sleep(0)
        manager.execute_agent.assert_awaited_once_with("Alice contract", "User confirms draft d-contract; retain exact recipients and body")
        self.assertEqual(self.roster.get_agents(), ["Alice lunch", "Alice contract"])

    async def test_preview_storage_failure_stops_after_one_external_tool_call(self):
        self.stack.enter_context(patch.object(gmail, "_LOG_STORE", self.logs))
        self.stack.enter_context(patch.object(gmail, "get_active_gmail_user_id", return_value="account-a"))
        backend = self.stack.enter_context(patch.object(gmail, "execute_gmail_tool", return_value={"body": "x" * 100000}))
        real_put = ContentStore.put_text

        def fail_preview(store, text, **kwargs):
            if kwargs["kind"] == "model_tool_result":
                raise content_store.ContentStoreError("Preview source persistence failed; check completed operation before retrying")
            return real_put(store, text, **kwargs)

        response = {"choices": [{"message": {"tool_calls": [{"id": "fetch", "type": "function", "function": {
            "name": "gmail_list_drafts", "arguments": "{}"}}]}}]}
        with patch.object(ContentStore, "put_text", fail_preview), patch.object(workers.ExecutionAgentRuntime, "_make_llm_call", new=AsyncMock(return_value=response)) as model:
            result = await workers.ExecutionAgentRuntime("Alice lunch").execute("Read the result")
        self.assertFalse(result.success)
        self.assertIn("persistence failed", result.error)
        backend.assert_called_once()
        model.assert_awaited_once()

    async def test_malformed_parallel_calls_are_rejected_before_any_tool_executes(self):
        calls = tool_group("duplicate", "unused")[0]["tool_calls"] * 2
        response = {"choices": [{"message": {"tool_calls": calls}}]}
        for runtime_type, args in ((workers.ExecutionAgentRuntime, ("Alice lunch",)),
                                   (interactions.InteractionAgentRuntime, ())):
            with self.subTest(runtime=runtime_type.__name__), patch.object(runtime_type, "_make_llm_call", new=AsyncMock(return_value=response)), patch.object(runtime_type, "_execute_tool", new=AsyncMock()) as tool:
                result = await runtime_type(*args).execute("Current task")
                self.assertFalse(result.success)
                self.assertIn("Duplicate tool-call IDs", result.error)
                tool.assert_not_called()

    async def test_bounded_interaction_preserves_full_draft_review_and_original_body_bytes(self):
        self.stack.enter_context(patch.object(tools, "get_conversation_log", return_value=self.log))
        body = "Exact draft\r\n" + "x" * 6000 + "旅🦉\r\n  final line  "
        draft_args = {"to": "Exact.Recipient@example.test", "subject": "Exact subject", "body": body}
        response = {"choices": [{"message": {"tool_calls": [{"id": "review", "type": "function", "function": {
            "name": "send_draft", "arguments": json.dumps(draft_args)}}]}}]}
        final = {"choices": [{"message": {"content": "Draft ready for review"}}]}
        requests = []

        def respond(request):
            payload = json.loads(request.content)
            requests.append(payload)
            prepare_budgeted_request(payload, context_window=200000, input_cap=32768, headroom=64)
            return httpx.Response(200, json=response if len(requests) == 1 else final)

        with client.use_mock_provider(httpx.MockTransport(respond)):
            result = await interactions.InteractionAgentRuntime().execute("Show this draft for review; do not send it")
        self.assertTrue(result.success, result)
        entries = list(self.log.iter_entries())
        shown = next(payload for tag, _, payload in entries if tag == "poke_reply")
        self.assertEqual(shown, f'To: {draft_args["to"]}\nSubject: {draft_args["subject"]}\n\n{body}'.replace("\r\n", "\n"))
        ref = next(json.loads(payload)["reference"] for tag, _, payload in entries if tag == "content_reference" and json.loads(payload)["kind"] == "reviewed_draft_body")
        self.assertEqual(self.read_all(ref), body)
        self.assertIn("Make sure you get user confirmation before sending", requests[0]["messages"][0]["content"])
        self.assertEqual(json.loads(requests[1]["messages"][-2]["tool_calls"][0]["function"]["arguments"]), draft_args)

    async def test_trigger_style_direct_worker_turns_get_request_boundaries_without_double_logging_dispatch(self):
        final = {"choices": [{"message": {"content": "Completed"}}]}
        with patch.object(workers.ExecutionAgentRuntime, "_make_llm_call", new=AsyncMock(return_value=final)):
            runtime = workers.ExecutionAgentRuntime("Alice lunch")
            for text in ("trigger instruction 1", "trigger instruction 2"):
                self.assertTrue((await runtime.execute(text)).success)
            self.logs.record_request("Alice lunch", "prelogged dispatch")
            self.assertTrue((await runtime.execute("prelogged dispatch")).success)
        requests = [payload for tag, _, payload in self.logs.iter_entries("Alice lunch") if tag == "agent_request"]
        self.assertEqual(requests, ["trigger instruction 1", "trigger instruction 2", "prelogged dispatch"])
        history = contexts.load_recent_history(self.logs, worker_name="Alice lunch")
        self.assertEqual(len(history.episodes), 3)
        self.assertTrue(all('status="complete"' in episode for episode in history.episodes))
