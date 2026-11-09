import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from server import content_store, services
from server.content_store import ContentExpiredError, ContentStore, ContentStoreError, capture_scope, capture_text
from server.config import Settings
from server.agents.execution_agent import agent as worker_agent, runtime as worker_runtime, batch_manager
from server.agents.execution_agent.tools import gmail
from server.agents.execution_agent.tasks.search_email import tool as search_tool
from server.agents.interaction_agent import runtime as interaction_runtime, tools
from server.routes import chat
from server.services.conversation.log import ConversationLog
from server.services.conversation.summarization.working_memory_log import WorkingMemoryLog
from server.services.execution import AgentRoster, ExecutionAgentLogStore


class ContentStoreTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.store = ContentStore(self.root / "profile" / "content")
        self.generation = self.store.generation()

    def put(self, text="Original text", **kwargs):
        return self.store.put_text(text, **{"owner": "worker:Alice lunch", "generation": self.generation,
                                           "kind": "tool_result", **kwargs})

    def read(self, reference, **kwargs):
        return self.store.read_page(reference, **{"owner": "worker:Alice lunch", **kwargs})

    def test_full_unicode_text_and_middle_fact_round_trip_in_bounded_byte_pages(self):
        text = "first\r\n" + "🦉" * 20000 + "MIDDLE FACT & exact punctuation" + "旅" * 20000 + "\x00end"
        reference = self.put(text)
        offset, chunks = 0, []
        while True:
            page = self.read(reference, offset=offset, limit=8191)
            self.assertLessEqual(len(page.content), 8191)
            chunks.append(page.content)
            if page.next_offset is None:
                break
            offset = page.next_offset
        self.assertEqual(b"".join(chunks).decode(), text)
        self.assertEqual(page.metadata["sha256"], sha256(text.encode()).hexdigest())
        self.assertEqual(page.metadata["size_bytes"], len(text.encode()))
        self.assertNotIn("Alice", reference)
        self.assertEqual(self.read(reference, offset=len(text.encode())).content, b"")

    def test_restart_preserves_refs_and_qualification(self):
        reference = self.put("same body", provider="gmail", account_id="account-a")
        reopened = ContentStore(self.store.root)
        self.assertEqual(reopened.generation(), self.generation)
        self.assertEqual(reopened.read_page(reference, owner="worker:Alice lunch", provider="gmail", account_id="account-a").content, b"same body")
        for kwargs in ({"owner": "worker:Alice contract", "provider": "gmail", "account_id": "account-a"},
                       {"provider": "gmail", "account_id": "account-b"}, {"provider": "gmail"}, {}):
            with self.assertRaisesRegex(ContentStoreError, "owner or mailbox"):
                self.read(reference, **kwargs)

    def test_unknown_mailbox_never_inherits_a_known_account(self):
        reference = self.put("unknown legacy provenance", provider="gmail")
        self.assertIsNone(self.read(reference, provider="gmail").metadata["account_id"])
        with self.assertRaises(ContentStoreError):
            self.read(reference, provider="gmail", account_id="current-mailbox")
        with self.assertRaises(ValueError):
            self.put(account_id="account-without-provider")

    def test_empty_content_and_distinct_captures_have_distinct_immutable_refs(self):
        first, second = self.put(""), self.put("")
        self.assertNotEqual(first, second)
        self.assertEqual(self.read(first).content, b"")
        self.assertIsNone(self.read(first).next_offset)
        self.assertEqual(self.read(first).metadata["sha256"], sha256(b"").hexdigest())

    def test_clear_invalidates_refs_and_rejects_old_writes_without_touching_other_files(self):
        original = self.root / "profile" / "original.log"
        original.write_text("preserved history")
        reference = self.put()
        self.store.clear()
        self.assertNotEqual(self.store.generation(), self.generation)
        with self.assertRaises(ContentExpiredError):
            self.read(reference)
        with self.assertRaises(ContentExpiredError):
            self.put("late write")
        self.assertEqual(original.read_text(), "preserved history")
        self.assertEqual(list((self.store.root / "objects").iterdir()), [])
        replacement = self.put("new", generation=self.store.generation())
        self.assertEqual(self.read(replacement).content, b"new")

    def test_failed_cleanup_still_invalidates_history(self):
        reference = self.put()
        with patch.object(content_store.shutil, "rmtree", side_effect=PermissionError("injected")):
            with self.assertRaisesRegex(ContentStoreError, "invalidated"):
                self.store.clear()
        with self.assertRaises(ContentExpiredError):
            self.read(reference)
        with self.assertRaises(ContentExpiredError):
            self.put()

    def test_invalid_refs_bounds_missing_and_truncated_content_fail_explicitly(self):
        for reference in ("../outside", "C:/private.txt", "c1_../../..", None):
            with self.assertRaises(ContentStoreError):
                self.read(reference)
        reference = self.put()
        for kwargs in ({"offset": -1}, {"limit": 0}, {"limit": 65537}, {"offset": True}):
            with self.assertRaises(ValueError):
                self.read(reference, **kwargs)
        path = self.store.root / "objects" / self.generation / reference.split("_")[-1]
        (path / "body.txt").write_bytes(b"short")
        with self.assertRaisesRegex(ContentStoreError, "incomplete"):
            self.read(reference)
        (path / "body.txt").unlink()
        with self.assertRaisesRegex(ContentStoreError, "unavailable"):
            self.read(reference)

    def test_corrupt_or_removed_generation_is_not_silently_reinitialized(self):
        self.put()
        path = self.store.root / "generation.json"
        path.write_text("invalid json")
        with self.assertRaises(ContentStoreError):
            self.store.generation()
        path.unlink()
        with self.assertRaisesRegex(ContentStoreError, "missing"):
            self.store.generation()
        self.assertFalse(path.exists())

    def test_failed_publication_does_not_leave_a_readable_partial_object(self):
        with patch.object(content_store.os, "rename", side_effect=PermissionError("injected")):
            with self.assertRaises(ContentStoreError):
                self.put("large" * 1000)
        self.assertEqual(list((self.store.root / "objects" / self.generation).iterdir()), [])

    def test_profiles_and_concurrent_appends_remain_separate(self):
        other = ContentStore(self.root / "other-profile" / "content")
        other.generation()
        barrier = threading.Barrier(2)
        def put(index):
            barrier.wait(timeout=2)
            return self.put(str(index))
        with ThreadPoolExecutor(max_workers=2) as pool:
            references = list(pool.map(put, range(2)))
        self.assertEqual({self.read(ref).content for ref in references}, {b"0", b"1"})
        with self.assertRaises(ContentExpiredError):
            other.read_page(references[0], owner="worker:Alice lunch")
        other.clear()
        self.assertEqual(self.read(references[0]).content, b"0")

    def test_fresh_process_can_read_content_from_its_original_root(self):
        reference = self.put("restart payload")
        script = """
import json, socket, sys
def reject(*args, **kwargs):
    raise AssertionError('No network in content reload tests')
socket.socket.connect = socket.socket.connect_ex = reject
from server.content_store import ContentStore
root, reference = sys.argv[1:]
page = ContentStore(root).read_page(reference, owner='worker:Alice lunch')
print(json.dumps({'text': page.content.decode(), 'owner': page.metadata['owner']}))
"""
        environment = dict(os.environ, OPENPOKE_DATA_DIR=str(self.root / "probe-config"), OPENROUTER_API_KEY="test-key",
                           COMPOSIO_API_KEY="test-key", COMPOSIO_GMAIL_AUTH_CONFIG_ID="test-auth",
                           OPENPOKE_CONTEXT_STRATEGY="legacy", OPENPOKE_MODEL_CONTEXT_WINDOWS="{}")
        result = subprocess.run([sys.executable, "-c", script, str(self.store.root), reference],
                                capture_output=True, text=True, timeout=15, env=environment,
                                cwd=Path(__file__).resolve().parents[2])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["text"], "restart payload")


class ContentCaptureTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.store = ContentStore(self.root / "content")
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(content_store, "get_data_dir", return_value=self.root))
        self.stack.enter_context(patch.object(content_store, "get_settings", return_value=SimpleNamespace(context_strategy="bounded")))
        self.stack.enter_context(patch("server.services.conversation.log.get_settings", return_value=Settings(conversation_summary_threshold=0)))
        self.logs = ExecutionAgentLogStore(self.root / "execution_agents")
        for module in (worker_agent,):
            self.stack.enter_context(patch.object(module, "get_execution_agent_logs", return_value=self.logs))
        self.memory = WorkingMemoryLog(self.root / "memory.log")
        self.stack.enter_context(patch("server.services.conversation.log._resolve_working_memory_log", return_value=self.memory))
        self.log = ConversationLog(self.root / "conversation.log")
        self.stack.enter_context(patch.object(tools, "get_conversation_log", return_value=self.log))
        self.stack.enter_context(patch.object(gmail, "_LOG_STORE", self.logs))
        self.stack.enter_context(patch.object(search_tool, "_LOG_STORE", self.logs))

    def refs(self, owner_name="Alice lunch"):
        return [json.loads(payload) for tag, _, payload in self.logs.iter_entries(owner_name) if tag == "content_reference"]

    def read_all(self, reference, *, owner="worker:Alice lunch", provider=None, account_id=None):
        offset, chunks = 0, []
        while True:
            page = self.store.read_page(reference, owner=owner, provider=provider, account_id=account_id, offset=offset)
            chunks.append(page.content)
            if page.next_offset is None:
                return b"".join(chunks).decode()
            offset = page.next_offset

    async def test_worker_journal_preserves_content_before_its_existing_truncation(self):
        worker = worker_agent.ExecutionAgent("Alice lunch")
        body = "x" * 4000 + "IMPORTANT MIDDLE FACT" + "y" * 4000
        arguments = json.dumps({"body": body})
        with capture_scope("worker:Alice lunch"):
            worker.record_tool_execution("document_lookup", arguments, body)
        refs = self.refs()
        self.assertEqual(len(refs), 2)
        self.assertEqual(self.read_all(refs[0]["reference"]), arguments)
        self.assertEqual(self.read_all(refs[1]["reference"]), body)
        recorded = [payload for tag, _, payload in self.logs.iter_entries("Alice lunch") if tag == "tool_response"]
        self.assertEqual(recorded, ["document_lookup: " + body[:500]])

    async def test_gmail_capture_uses_the_executed_account_without_changing_result(self):
        result = {"successful": True, "data": {"id": "same-id-in-both-accounts", "body": "x" * 8000}}
        with (capture_scope("worker:Alice lunch"),
              patch.object(gmail, "execute_gmail_tool", return_value=result),
              patch.object(gmail, "get_active_gmail_user_id", return_value="account-b")):
            returned = gmail._execute("GMAIL_LIST_DRAFTS", "account-a", {})
        self.assertIs(returned, result)
        reference = self.refs()[0]["reference"]
        self.assertEqual(json.loads(self.read_all(reference, provider="gmail", account_id="account-a")), result)
        with self.assertRaises(ContentStoreError):
            self.read_all(reference, provider="gmail", account_id="account-b")

    async def test_inner_email_search_preserves_raw_result_before_cleaning(self):
        result = {"raw": "uncleaned middle fact " * 400}
        with (capture_scope("worker:Alice lunch"), patch.object(search_tool, "execute_gmail_tool", return_value=result),
              patch.object(search_tool, "parse_gmail_fetch_response", return_value=([], None))):
            await search_tool._perform_search(arguments={"query": "subject:report"}, queries=[], emails={}, composio_user_id="account-a")
        reference = self.refs()[0]["reference"]
        self.assertEqual(json.loads(self.read_all(reference, provider="gmail", account_id="account-a")), result)

    async def test_large_chat_and_callback_messages_are_captured_without_previews(self):
        configured = Settings(openrouter_api_key="test-key", conversation_summary_threshold=0)
        with (patch.object(interaction_runtime, "get_settings", return_value=configured),
              patch.object(interaction_runtime, "get_conversation_log", return_value=self.log),
              patch.object(interaction_runtime, "get_working_memory_log", return_value=self.memory)):
            runtime = interaction_runtime.InteractionAgentRuntime()
        inputs = ["user message " * 500, "callback " * 700]
        snapshots = []
        async def model(system, messages):
            snapshots.append(messages[0]["content"])
            return {"choices": [{"message": {"content": "done"}}]}
        with patch.object(runtime, "_make_llm_call", side_effect=model):
            self.assertTrue((await runtime.execute(inputs[0])).success)
            self.assertTrue((await runtime.handle_agent_message(inputs[1])).success)
        refs = [json.loads(payload) for tag, _, payload in self.log.iter_entries() if tag == "content_reference"]
        self.assertEqual([self.read_all(ref["reference"], owner="conversation") for ref in refs], inputs)
        # Existing prompt construction strips surrounding whitespace; capture
        # deliberately preserves the original bytes before that normalization.
        self.assertTrue(all(value.strip() in snapshot for value, snapshot in zip(inputs, snapshots)))

    async def test_draft_review_keeps_exact_body_and_unknown_mailbox_provenance(self):
        body = "Hello,\r\n" + "Reviewed body 🦉 " * 500
        with capture_scope("conversation"):
            result = tools.send_draft("recipient@example.test", "Subject", body)
        self.assertTrue(result.success)
        replies = [payload for tag, _, payload in self.log.iter_entries() if tag == "poke_reply"]
        self.assertEqual(replies, [f"To: recipient@example.test\nSubject: Subject\n\n{body}".replace("\r\n", "\n")])
        refs = [json.loads(payload) for tag, _, payload in self.log.iter_entries() if tag == "content_reference"]
        reference = next(ref["reference"] for ref in refs if ref["kind"] == "reviewed_draft_body")
        self.assertEqual(self.read_all(reference, owner="conversation", provider="gmail"), body)
        with self.assertRaises(ContentStoreError):
            self.read_all(reference, owner="conversation", provider="gmail", account_id="current-account")

    async def test_queued_task_inherits_old_generation_and_cannot_capture_after_clear(self):
        ready = asyncio.Event()
        async def queued():
            await ready.wait()
            with capture_scope("worker:Alice lunch"):
                capture_text("late result " * 1000, kind="tool_result")
        with capture_scope("conversation"):
            task = asyncio.create_task(queued())
        self.store.clear()
        ready.set()
        with self.assertRaises(ContentExpiredError):
            await task
        self.assertEqual(list((self.store.root / "objects").glob("*/*/metadata.json")), [])

    async def test_stale_callback_is_rejected_even_if_its_body_is_small(self):
        with capture_scope("worker:Alice lunch") as capture:
            old = capture.generation
        self.store.clear()
        runtime = interaction_runtime.InteractionAgentRuntime.__new__(interaction_runtime.InteractionAgentRuntime)
        runtime.conversation_log = Mock()
        result = await runtime.handle_agent_message("old callback", content_generation=old)
        self.assertFalse(result.success)
        runtime.conversation_log.record_agent_message.assert_not_called()

    async def test_mixed_batch_retains_its_first_generation_for_callback(self):
        manager = batch_manager.ExecutionBatchManager()
        with capture_scope("worker:Old") as context:
            generation = context.generation
            batch_id = await manager._register_pending_execution("Old", "old", "request-old")
        self.store.clear()
        with capture_scope("worker:New"):
            self.assertEqual(await manager._register_pending_execution("New", "new", "request-new"), batch_id)
            await manager._complete_execution(batch_id, worker_runtime.ExecutionResult("Old", True, "old"), "Old")
            with patch.object(manager, "_dispatch_to_interaction_agent", new=AsyncMock()) as callback:
                await manager._complete_execution(batch_id, worker_runtime.ExecutionResult("New", True, "new"), "New")
        self.assertEqual(callback.call_args.kwargs["content_generation"], generation)

    async def test_clear_route_invalidates_content_and_removes_only_managed_content(self):
        with capture_scope("worker:Alice lunch"):
            reference = capture_text("x" * 8000, kind="tool_result")
        roster = AgentRoster(self.logs._base_dir / "roster.json")
        with (patch.object(services, "get_agent_roster", return_value=roster),
              patch.object(services, "get_execution_agent_logs", return_value=self.logs),
              patch.object(chat, "get_conversation_log", return_value=self.log),
              patch.object(chat, "get_trigger_service", return_value=Mock())):
            chat.clear_history()
        with self.assertRaises(ContentExpiredError):
            self.read_all(reference)

    async def test_capture_failure_after_gmail_result_does_not_continue_tool_loop(self):
        with (capture_scope("worker:Alice lunch"), patch.object(gmail, "execute_gmail_tool", return_value={"body": "x" * 8000}),
              patch.object(ContentStore, "put_text", side_effect=ContentStoreError("injected"))):
            with self.assertRaisesRegex(ContentStoreError, "operation outcome"):
                gmail._execute("GMAIL_SEND_DRAFT", "account-a", {})
        runtime = worker_runtime.ExecutionAgentRuntime.__new__(worker_runtime.ExecutionAgentRuntime)
        runtime.tool_registry = {"gmail_send_draft": Mock(side_effect=ContentStoreError("capture failed"))}
        with self.assertRaises(ContentStoreError):
            await runtime._execute_tool_impl("gmail_send_draft", {})

    async def test_legacy_mode_and_unscoped_helpers_do_not_create_content(self):
        with patch.object(content_store, "get_settings", return_value=SimpleNamespace(context_strategy="legacy")):
            with capture_scope("conversation"):
                self.assertIsNone(capture_text("x" * 8000, kind="message"))
        self.assertIsNone(capture_text("x" * 8000, kind="unowned"))
        self.assertFalse(self.store.root.exists())

    async def test_concurrent_capture_scopes_keep_owner_identity_separate(self):
        ready = asyncio.Event()
        entered = []
        async def capture(owner):
            with capture_scope(owner):
                entered.append(owner)
                if len(entered) == 2:
                    ready.set()
                await ready.wait()
                return capture_text(owner * 500, kind="tool_result")
        owners = ["worker:Alice lunch", "worker:Alice contract"]
        refs = await asyncio.wait_for(asyncio.gather(*(capture(owner) for owner in owners)), timeout=3)
        for owner, reference in zip(owners, refs):
            self.assertEqual(self.read_all(reference, owner=owner), owner * 500)
        with self.assertRaises(ContentStoreError):
            self.read_all(refs[0], owner=owners[1])
