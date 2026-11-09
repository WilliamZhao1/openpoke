from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

from server import content_store, inner_context
from server.config import Settings
from server.content_store import ContentStore, capture_scope
from server.context_budget import ContextBudgetError, prepare_budgeted_request
from server.agents.execution_agent.tasks.search_email import tool as search
from server.services.conversation.log import ConversationLog
from server.services.conversation.summarization import summarizer, bounded as summary_bounds
from server.services.conversation.summarization.state import SummaryState
from server.services.conversation.summarization.working_memory_log import WorkingMemoryLog
from server.services.execution import AgentRoster, ExecutionAgentLogStore
from server.services.gmail import importance_classifier as classifier, importance_watcher as watcher_module
from server.services.gmail.processing import ProcessedEmail
from server.services.gmail.seen_store import GmailSeenStore
from server.openrouter_client import client
from server.tests.fixtures.fake_gmail import FakeGmail, use_fake_gmail


MODEL = "inner-test"
ACCOUNT = "fixture-profile-a"
OWNER = "worker:Alice contract"
MODEL_FIELDS = ("interaction_agent_model", "execution_agent_model", "execution_agent_search_model", "summarizer_model", "email_classifier_model")


class InnerContextTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.settings = Settings(**{**dict.fromkeys(MODEL_FIELDS, MODEL), "context_strategy": "bounded", "worker_discovery_strategy": "bounded",
                                   "model_context_windows": {MODEL: 100000}, "context_input_tokens": 12000,
                                   "context_headroom_tokens": 64, "openrouter_max_tokens": 256,
                                   "openrouter_api_key": "test-key", "conversation_summary_threshold": 0})
        self.memory = WorkingMemoryLog(self.root / "memory.log")
        self.stack.enter_context(patch("server.services.conversation.log._resolve_working_memory_log", return_value=self.memory))
        self.log = ConversationLog(self.root / "conversation.log")
        self.logs = ExecutionAgentLogStore(self.root / "workers")
        self.store = ContentStore(self.root / "content")
        for module in (content_store, search, classifier, watcher_module, summarizer, client):
            self.stack.enter_context(patch.object(module, "get_settings", return_value=self.settings))
        # Prevent background scheduling while fixtures append source data. Summary
        # runs below are explicitly awaited with their own enabled settings.
        self.stack.enter_context(patch("server.services.conversation.log.get_settings", return_value=self.settings))
        self.stack.enter_context(patch.object(content_store, "get_data_dir", return_value=self.root))
        self.stack.enter_context(patch.object(inner_context, "get_conversation_log", return_value=self.log))
        self.stack.enter_context(patch.object(inner_context, "get_execution_agent_logs", return_value=self.logs))
        self.stack.enter_context(patch.object(search, "_LOG_STORE", self.logs))
        self.stack.enter_context(patch.object(summarizer, "_resolve_conversation_log", return_value=self.log))
        self.stack.enter_context(patch.object(summarizer, "get_working_memory_log", return_value=self.memory))
        self.fake = FakeGmail()

    def check(self, request):
        payload = json.loads(request.content)
        prepare_budgeted_request(payload, context_window=100000, input_cap=self.settings.context_input_tokens, headroom=64)
        return payload

    @staticmethod
    def call(name, args, identifier="call"):
        return {"choices": [{"message": {"tool_calls": [{"id": identifier, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}}]}

    @staticmethod
    def final(text):
        return {"choices": [{"message": {"content": text}}]}

    def read(self, reference, owner="conversation"):
        offset, parts = 0, []
        while True:
            page = self.store.read_source_page(reference, owner=owner, offset=offset, limit=65536)
            parts.append(page.content)
            if page.next_offset is None:
                return b"".join(parts).decode()
            offset = page.next_offset

    def email(self, body="Routine body", **changes):
        return ProcessedEmail(**{"id": "email-1", "thread_id": "thread-1", "query": "INBOX", "subject": "Subject",
                                 "sender": "sender@example.test", "recipient": "owner@example.test", "timestamp": datetime.now(timezone.utc),
                                 "label_ids": [], "clean_text": body, "has_attachments": False, "attachment_count": 0,
                                 "attachment_filenames": [], **changes})

    def summary_settings(self, threshold=2, tail=0):
        return self.settings.model_copy(update={"conversation_summary_threshold": threshold, "conversation_summary_tail_size": tail})

    async def test_search_previews_large_email_and_recovers_middle_fact_under_real_preflight(self):
        body = "x" * 25000 + "CRITICAL_MIDDLE" + "旅🦉" * 5000
        self.fake._accounts["fixture-gmail-a"]["messages"]["18fa000000000001"]["textBody"] = body
        requests, selected = [], []

        def respond(request):
            payload = self.check(request)
            requests.append(payload)
            if len(requests) == 1:
                result = self.call("gmail_fetch_emails", {"query": "subject:lunch", "max_results": 100000}, "fetch")
            elif len(requests) == 2:
                tool = json.loads(payload["messages"][-1]["content"])
                if tool.get("preview"):
                    tool = json.loads(self.read(tool["reference"], OWNER))
                email = tool["messages"][0]
                selected.append(email["id"])
                self.assertFalse(email["content_complete"])
                self.assertEqual(email["account_id"], ACCOUNT)
                full = self.read(email["content_reference"], OWNER)
                self.assertIn(body, json.loads(full)["clean_text"])
                result = self.call("read_result", {"reference": email["content_reference"], "offset": full.encode().index(b"CRITICAL_MIDDLE"), "limit": 64}, "read")
            else:
                self.assertIn("CRITICAL_MIDDLE", payload["messages"][-1]["content"])
                result = self.call("return_search_results", {"message_ids": selected}, "complete")
            return httpx.Response(200, json=result)

        with capture_scope(OWNER), use_fake_gmail(self.fake), client.use_mock_provider(httpx.MockTransport(respond)):
            result = await search.task_email_search("Find the lunch message with the critical middle fact")
        self.assertIsInstance(result, list)
        self.assertEqual(result[0]["id"], selected[0])
        self.assertNotIn("CRITICAL_MIDDLE", result[0]["clean_text"])
        self.assertEqual(self.fake.calls[0]["arguments"]["max_results"], 20)
        self.assertEqual(len(self.fake.calls), 1)
        self.assertEqual(len(requests), 3)

    async def test_search_parent_hints_are_bounded_with_a_complete_qualified_index(self):
        references = []
        result = [{"id": "selected", "clean_text": "body"}]

        async def search_with_sources(**kwargs):
            reader = inner_context.SourceReader()
            for number in range(20):
                references.append(reader.save(f"source {number}", "email_search.email", provider="gmail", account_id=ACCOUNT))
            return result

        with capture_scope(OWNER) as capture, patch.object(search, "get_active_gmail_user_id", return_value=ACCOUNT), patch.object(search, "_run_email_search", side_effect=search_with_sources):
            self.assertEqual(await search.task_email_search("Find lunch"), result)
            self.assertEqual(len(capture.sources), 8)
            index = next(item for item in capture.sources if item["kind"] == "task_email_search.sources")
            self.assertIsNone(index["provider"])
            self.assertIsNone(index["account_id"])
            descriptors = json.loads(self.read(index["reference"], OWNER))["source_references"]
            self.assertEqual({item["reference"] for item in descriptors}, set(references))
            self.assertTrue(all(item["provider"] == "gmail" and item["account_id"] == ACCOUNT for item in descriptors))
            for number, reference in enumerate(references):
                self.assertEqual(self.read(reference, OWNER), f"source {number}")

    async def test_search_failure_cannot_complete_as_an_empty_lookup(self):
        for raw in ({"successful": False, "error": "Unavailable"}, {"messages": [{"error": "Unavailable"}]}, {"messages": ["invalid row"]}):
            requests = []
            def respond(request):
                requests.append(self.check(request))
                result = self.call("gmail_fetch_emails", {"query": "subject:lunch"}) if len(requests) == 1 else self.call("return_search_results", {"message_ids": []})
                return httpx.Response(200, json=result)
            with self.subTest(raw=raw), capture_scope(OWNER), patch.object(search, "get_active_gmail_user_id", return_value=ACCOUNT), patch.object(search, "execute_gmail_tool", return_value=raw) as sdk, client.use_mock_provider(httpx.MockTransport(respond)):
                result = await search.task_email_search("Find lunch")
            self.assertIn("error", result)
            self.assertEqual(len(requests), search.MAX_LLM_ITERATIONS)
            sdk.assert_called_once()

    async def test_search_successful_empty_lookup_can_complete_and_unknown_ids_cannot(self):
        for selected in ([], ["invented-id"]):
            requests = []
            def respond(request):
                requests.append(self.check(request))
                result = self.call("gmail_fetch_emails", {"query": "subject:absent"}) if len(requests) == 1 else self.call("return_search_results", {"message_ids": selected})
                return httpx.Response(200, json=result)
            with self.subTest(selected=selected), capture_scope(OWNER), use_fake_gmail(self.fake), client.use_mock_provider(httpx.MockTransport(respond)):
                result = await search.task_email_search("Find nonexistent mail")
            self.assertEqual(result, []) if not selected else self.assertIn("error", result)

    async def test_search_cache_and_query_caps_stop_more_sdk_work_with_sources_preserved(self):
        with capture_scope(OWNER):
            reader = inner_context.SourceReader()
            work = search._SearchWork(reader)
            cache, queries = {}, []
            for number in range(6):
                raw = {"messages": [{"id": f"id-{number}-{i}", "subject": "Subject", "sender": "sender@example.test", "to": "owner@example.test",
                                      "messageTimestamp": "2026-11-08T12:00:00Z", "textBody": "body"} for i in range(20)]}
                with patch.object(search, "execute_gmail_tool", return_value=raw):
                    if number == 5:
                        with self.assertRaisesRegex(ContextBudgetError, "cache limit"):
                            await search._perform_search(arguments={"query": str(number)}, queries=queries, emails=cache, composio_user_id=ACCOUNT, work=work)
                    else:
                        await search._perform_search(arguments={"query": str(number)}, queries=queries, emails=cache, composio_user_id=ACCOUNT, work=work)
            self.assertEqual(len(cache), 100)
            work.calls = 8
            with patch.object(search, "execute_gmail_tool") as sdk, self.assertRaisesRegex(ContextBudgetError, "query limit"):
                await search._perform_search(arguments={"query": "too many"}, queries=queries, emails=cache, composio_user_id=ACCOUNT, work=work)
            sdk.assert_not_called()

    async def test_source_and_retained_message_budgets_do_not_discard_the_original(self):
        with capture_scope(OWNER):
            reader = inner_context.SourceReader()
            with patch.object(inner_context, "MAX_SOURCE_BYTES", 10):
                with self.assertRaises(ContextBudgetError):
                    reader.save("full source text", "input", provider="gmail", account_id=ACCOUNT)
                with self.assertRaises(ContextBudgetError):
                    reader.save("full source text", "input", provider="gmail", account_id=ACCOUNT)
            self.assertEqual(self.read(next(iter(reader.allowed)), OWNER), "full source text")
            messages = [{"role": "user", "content": "goal"}]
            for i in range(3):
                messages.extend([{"role": "assistant", "content": "", "tool_calls": [{"id": str(i), "function": {"name": "read_result", "arguments": "{}"}}]},
                                 {"role": "tool", "tool_call_id": str(i), "content": "x" * 800}])
            original = deepcopy(messages)
            other = inner_context.SourceReader()
            other.prune(messages, maximum=1500)
            self.assertLess(len(messages), len(original))
            self.assertEqual(messages[-2:], original[-2:])
            self.assertIn(original[1:3], [json.loads(self.read(reference, OWNER)) for reference in other.allowed])
            self.assertTrue(all(reference in messages[0]["content"] for reference in other.allowed))

    async def test_classifier_can_recover_a_middle_detail_without_overflowing(self):
        body = "x" * 25000 + "SECURITY_ALERT" + "z" * 25000
        requests = []
        def respond(request):
            payload = self.check(request)
            requests.append(payload)
            if len(requests) == 1:
                reference = re.search(r"Complete body source: (c1_[0-9a-f_]+)", payload["messages"][1]["content"])[1]
                result = self.call("read_result", {"reference": reference, "offset": 25000, "limit": 32}, "read")
            else:
                page = json.loads(payload["messages"][-1]["content"])
                self.assertEqual(page["account_id"], ACCOUNT)
                self.assertIn("SECURITY_ALERT", page["text"])
                result = self.call("mark_email_importance", {"important": True, "summary": "Security alert needs attention."}, "decide")
            return httpx.Response(200, json=result)
        with client.use_mock_provider(httpx.MockTransport(respond)):
            result = await classifier.classify_email_importance(self.email(body), composio_user_id=ACCOUNT, strict=True)
        self.assertEqual(result, "Security alert needs attention.")
        self.assertEqual(len(requests), 2)

    async def test_classifier_rejects_an_oversized_notification_without_truncating_it(self):
        summary = "Urgent \u65c5\U0001f989 " * 400
        requests = []

        def respond(request):
            requests.append(self.check(request))
            return httpx.Response(200, json=self.call("mark_email_importance", {"important": True, "summary": summary}))

        with capture_scope("conversation") as capture, client.use_mock_provider(httpx.MockTransport(respond)), self.assertRaises(classifier.ClassificationUnavailable):
            await classifier.classify_email_importance(self.email(), composio_user_id=ACCOUNT, strict=True)
        self.assertEqual(len(requests), 1)
        rejected = next(item for item in capture.sources if item["kind"] == "email_classifier.rejected")
        self.assertEqual(self.read(rejected["reference"]), summary)

    async def test_classifier_incomplete_body_is_unavailable_instead_of_a_negative_decision(self):
        calls = []
        def respond(request):
            calls.append(self.check(request))
            return httpx.Response(200, json=self.call("mark_email_importance", {"important": False}))
        with client.use_mock_provider(httpx.MockTransport(respond)), self.assertRaises(classifier.ClassificationUnavailable):
            await classifier.classify_email_importance(self.email("x" * 50000), composio_user_id=ACCOUNT, strict=True)
        self.assertEqual(len(calls), 8)
        with client.use_mock_provider(httpx.MockTransport(respond)):
            self.assertIsNone(await classifier.classify_email_importance(self.email(), composio_user_id=ACCOUNT, strict=True))

    async def test_classifier_required_headers_and_unsupported_decisions_fail_without_guesses(self):
        with patch.object(client.httpx, "AsyncClient", side_effect=AssertionError("metadata cannot reach HTTP")), self.assertRaises(classifier.ClassificationUnavailable):
            await classifier.classify_email_importance(self.email(subject="x" * 50000), strict=True)
        calls = []
        def respond(request):
            calls.append(self.check(request))
            return httpx.Response(200, json=self.call("mark_email_importance", {"important": "false", "summary": "Not a boolean"}))
        with client.use_mock_provider(httpx.MockTransport(respond)), self.assertRaises(classifier.ClassificationUnavailable):
            await classifier.classify_email_importance(self.email(), strict=True)
        self.assertEqual(len(calls), 8)

    def watcher(self):
        watcher = watcher_module.ImportantEmailWatcher(seen_store=GmailSeenStore(self.root / "seen.json"))
        watcher._has_seeded_initial_snapshot = True
        return watcher

    async def test_watcher_does_not_mark_an_incomplete_classification_seen_and_retries_past_age_cutoff(self):
        now = self.fake.clock.current
        self.fake._accounts["fixture-gmail-a"]["messages"]["18fa000000000001"]["messageTimestamp"] = (now - timedelta(seconds=5)).isoformat()
        watcher = self.watcher()
        watcher._last_poll_timestamp = now - timedelta(seconds=60)
        watcher._bounded_account = ACCOUNT
        with use_fake_gmail(self.fake), patch.object(watcher_module, "datetime", wraps=datetime) as clock, patch.object(watcher_module, "convert_to_user_timezone", side_effect=lambda value: value), patch.object(watcher_module, "classify_email_importance", new=AsyncMock(side_effect=[classifier.ClassificationUnavailable("unknown"), None])) as classify:
            clock.now.return_value = now
            await watcher._poll_once()
            key = "g1_" + json.dumps([ACCOUNT, "18fa000000000001"])
            self.assertFalse(watcher._seen_store.is_seen(key))
            self.assertEqual(watcher._last_poll_timestamp, now - timedelta(seconds=60))
            clock.now.return_value = now + timedelta(seconds=120)
            await watcher._poll_once()
            self.assertTrue(watcher._seen_store.is_seen(key))
            self.assertEqual(classify.await_count, 2)
            self.assertLessEqual(len(watcher._classification_retry_ids), 50)

    async def test_watcher_seen_ids_are_qualified_and_notifications_keep_the_fetched_account(self):
        now = self.fake.clock.current
        for account in self.fake._accounts.values():
            account["messages"]["18fa000000000001"]["messageTimestamp"] = (now - timedelta(seconds=5)).isoformat()
        watcher = self.watcher()
        with patch.object(watcher_module, "datetime", wraps=datetime) as clock, patch.object(watcher_module, "convert_to_user_timezone", side_effect=lambda value: value), patch.object(watcher_module, "classify_email_importance", new=AsyncMock(return_value="Important update")) as classify, patch.object(watcher, "_dispatch_summary", new=AsyncMock()) as dispatch:
            clock.now.return_value = now
            for profile in ("fixture-profile-a", "fixture-profile-b"):
                with use_fake_gmail(self.fake, profile_id=profile):
                    await watcher._poll_once()
                reference = dispatch.call_args.kwargs["source_reference"]
                page = self.store.read_source_page(reference, owner="conversation")
                self.assertEqual(page.metadata["account_id"], profile)
                self.assertEqual(classify.call_args.kwargs["composio_user_id"], profile)
        self.assertTrue(watcher._seen_store.is_seen("g1_" + json.dumps(["fixture-profile-a", "18fa000000000001"])))
        self.assertTrue(watcher._seen_store.is_seen("g1_" + json.dumps(["fixture-profile-b", "18fa000000000001"])))

    async def test_watcher_clear_or_failed_lookup_cannot_emit_or_commit_an_old_notification(self):
        watcher = self.watcher()
        with patch.object(watcher_module, "get_active_gmail_user_id", return_value=ACCOUNT), patch.object(watcher_module, "execute_gmail_tool", return_value={}), self.assertRaises(ContextBudgetError):
            await watcher._poll_once()
        now = self.fake.clock.current
        self.fake._accounts["fixture-gmail-a"]["messages"]["18fa000000000001"]["messageTimestamp"] = now.isoformat()
        async def clearing(*args, **kwargs):
            self.store.clear()
            return "Old notification"
        with use_fake_gmail(self.fake), patch.object(watcher_module, "datetime", wraps=datetime) as clock, patch.object(watcher_module, "convert_to_user_timezone", side_effect=lambda value: value), patch.object(watcher_module, "classify_email_importance", new=clearing), patch.object(watcher, "_dispatch_summary", new=AsyncMock()) as dispatch:
            clock.now.return_value = now
            with self.assertRaises(content_store.ContentExpiredError):
                await watcher._poll_once()
        dispatch.assert_not_awaited()
        self.assertFalse(watcher._seen_store.has_entries())

    async def test_summary_resumes_at_committed_offset_and_legacy_can_recover_the_pending_tail(self):
        for i in range(3):
            self.log.record_user_message(f"required message {i}")
        before = self.log._path.read_bytes()
        settings = self.summary_settings(tail=1)
        requests = []
        def respond(request):
            payload = self.check(request)
            requests.append(payload)
            return httpx.Response(200, json=self.final("Briefing literal \\n stays literal\r\n旅\u2028note"))
        with patch.object(summarizer, "get_settings", return_value=settings), client.use_mock_provider(httpx.MockTransport(respond)), patch.object(self.log, "iter_entries", side_effect=AssertionError("bounded summary must stream")), patch.object(self.memory, "load_summary_state", side_effect=AssertionError("bounded summary must read only header")):
            self.assertTrue(await summarizer.summarize_conversation())
            header = self.memory.load_summary_header()
            self.assertEqual(header.last_index, 1)
            self.assertIsNotNone(header.source_offset)
            self.assertIn("\\n", header.summary_text)
            self.log.record_user_message("required message 3")
            self.log.record_user_message("required message 4")
            self.assertTrue(await summarizer.summarize_conversation())
            header = self.memory.load_summary_header()
            self.assertEqual(header.last_index, 3)
            self.assertIn("required message 2", requests[-1]["messages"][1]["content"])
            self.assertNotIn("required message 0", requests[-1]["messages"][1]["content"])
        self.assertTrue(self.log._path.read_bytes().startswith(before))
        with patch("server.services.conversation.log.get_conversation_log", return_value=self.log):
            recovered = self.memory.load_summary_state()
        self.assertEqual([entry.payload for entry in recovered.unsummarized_entries], ["required message 4"])
        legacy = self.summary_settings(threshold=1).model_copy(update={"context_strategy": "legacy"})
        with patch("server.services.conversation.log.get_conversation_log", return_value=self.log), patch.object(summarizer, "get_settings", return_value=legacy), patch.object(client, "get_settings", return_value=legacy), client.use_mock_provider(httpx.MockTransport(respond)):
            self.assertTrue(await summarizer.summarize_conversation())
        self.assertEqual(self.memory.load_summary_header().last_index, 4)
        self.assertIsNone(self.memory.load_summary_header().source_offset)

    async def test_search_pagination_stays_with_the_executed_account_after_active_account_changes(self):
        from server.services.gmail import client as gmail_client
        requests, token = [], None
        def respond(request):
            nonlocal token
            payload = self.check(request)
            requests.append(payload)
            if len(requests) == 1:
                result = self.call("gmail_fetch_emails", {"query": "from:alice@example.test", "max_results": 1}, "fetch-1")
            elif len(requests) == 2:
                data = json.loads(payload["messages"][-1]["content"])
                token = data["next_page_token"]
                gmail_client._ACTIVE_USER_ID = "fixture-profile-b"
                result = self.call("gmail_fetch_emails", {"query": "from:alice@example.test", "max_results": 1, "page_token": token}, "fetch-2")
            else:
                data = json.loads(payload["messages"][-1]["content"])
                self.assertEqual(data["messages"][0]["account_id"], ACCOUNT)
                result = self.call("return_search_results", {"message_ids": [data["messages"][0]["id"]]}, "complete")
            return httpx.Response(200, json=result)
        with capture_scope(OWNER), use_fake_gmail(self.fake), client.use_mock_provider(httpx.MockTransport(respond)):
            result = await search.task_email_search("Find the second Alice message")
        self.assertIsInstance(result, list)
        self.assertEqual([call["profile_id"] for call in self.fake.calls], [ACCOUNT, ACCOUNT])
        self.assertEqual(self.fake.calls[1]["arguments"]["page_token"], token)

    async def test_classifier_checks_original_source_qualification_before_model_work(self):
        with capture_scope("conversation"):
            reader = inner_context.SourceReader()
            raw = reader.save('{"messages": []}', "GMAIL_FETCH_EMAILS.result", provider="gmail", account_id="fixture-profile-b")
        with patch.object(client.httpx, "AsyncClient", side_effect=AssertionError("wrong source account cannot reach HTTP")), self.assertRaises(classifier.ClassificationUnavailable):
            await classifier.classify_email_importance(self.email(), composio_user_id=ACCOUNT, source_reference=raw, strict=True)

    async def test_legacy_summary_index_adoption_is_bounded_then_writes_a_resume_cursor(self):
        for i in range(45):
            self.log.record_user_message(f"entry-{i} " + "x" * 300)
        self.memory.write_summary_state(SummaryState(summary_text="Old legacy briefing", last_index=39))
        original = self.memory._path.read_bytes()
        with patch.object(summarizer, "get_settings", return_value=self.summary_settings(threshold=2)), patch.object(summary_bounds, "MAX_SCAN_BYTES", 1024), self.assertRaises(ContextBudgetError):
            await summarizer.summarize_conversation()
        self.assertEqual(self.memory._path.read_bytes(), original)
        requests = []
        def respond(request):
            payload = self.check(request)
            requests.append(payload)
            self.assertIn("Old legacy briefing", payload["messages"][1]["content"])
            self.assertIn("entry-40 ", payload["messages"][1]["content"])
            self.assertNotIn("entry-0 ", payload["messages"][1]["content"])
            return httpx.Response(200, json=self.final("Updated briefing"))
        with patch.object(summarizer, "get_settings", return_value=self.summary_settings(threshold=2)), client.use_mock_provider(httpx.MockTransport(respond)):
            self.assertTrue(await summarizer.summarize_conversation())
        self.assertEqual(self.memory.load_summary_header().last_index, 41)
        self.assertIsNotNone(self.memory.load_summary_header().source_offset)

    async def test_summary_existing_source_refs_have_executable_bounded_reads_and_are_retained(self):
        with capture_scope("conversation"):
            reader = inner_context.SourceReader()
            reference = reader.save("Stored source with a commitment", "source")
        requests = []
        def respond(request):
            payload = self.check(request)
            requests.append(payload)
            if len(requests) == 1:
                result = self.call("read_result", {"reference": reference, "limit": 128}, "source")
            else:
                self.assertIn("Stored source with a commitment", payload["messages"][-1]["content"])
                result = self.final("Pending: keep the commitment")
            return httpx.Response(200, json=result)
        with patch.object(summarizer, "get_settings", return_value=self.summary_settings(threshold=1)), client.use_mock_provider(httpx.MockTransport(respond)):
            self.assertTrue(await summarizer.summarize_conversation())
        self.assertIn(reference, self.memory.load_summary_header().summary_text)

    async def test_summary_keeps_the_existing_two_attempt_limit_for_transient_failure(self):
        self.log.record_user_message("Keep the meeting at noon.")
        requests = []

        def respond(request):
            requests.append(self.check(request))
            if len(requests) == 1:
                return httpx.Response(503, json={"error": {"message": "temporarily unavailable"}})
            return httpx.Response(200, json=self.final("Meeting remains at noon."))

        with patch.object(summarizer, "get_settings", return_value=self.summary_settings(threshold=1)), client.use_mock_provider(httpx.MockTransport(respond)):
            self.assertTrue(await summarizer.summarize_conversation())
        self.assertEqual(len(requests), 2)
        self.assertEqual(self.memory.load_summary_header().last_index, 0)

    async def test_default_summary_settings_use_a_bounded_effective_window(self):
        for number in range(73):
            self.log.record_user_message(f"short message {number}")
        settings = self.summary_settings(threshold=100, tail=10)
        requests = []

        def respond(request):
            requests.append(self.check(request))
            return httpx.Response(200, json=self.final("Keep the recorded short messages."))

        with patch.object(summarizer, "get_settings", return_value=settings), client.use_mock_provider(httpx.MockTransport(respond)):
            self.assertFalse(await summarizer.summarize_conversation())
            self.log.record_user_message("short message 73")
            self.assertTrue(await summarizer.summarize_conversation())
        self.assertEqual(len(requests), 1)
        self.assertLessEqual(self.memory.load_summary_header().last_index, 63)

    def test_legacy_memory_loading_does_not_inherit_bounded_header_limits(self):
        text = "legacy memory " * 30000
        self.memory.write_summary_state(SummaryState(summary_text=text, last_index=2))
        self.assertEqual(self.memory.load_summary_state().summary_text, text)
        with self.assertRaises(ContextBudgetError):
            self.memory.load_summary_header()

    async def test_summary_shrinks_complete_batches_and_never_advances_past_input_it_did_not_process(self):
        for i in range(8):
            self.log.record_user_message(f"message-{i} " + "x" * 1800)
        payloads = []
        def respond(request):
            payloads.append(self.check(request))
            return httpx.Response(200, json=self.final("Bounded briefing"))
        with patch.object(summarizer, "get_settings", return_value=self.summary_settings(threshold=8)), client.use_mock_provider(httpx.MockTransport(respond)):
            self.assertTrue(await summarizer.summarize_conversation())
        header = self.memory.load_summary_header()
        self.assertGreaterEqual(header.last_index, 0)
        self.assertLess(header.last_index, 7)
        self.assertIn(f"message-{header.last_index} ", payloads[0]["messages"][1]["content"])
        self.assertNotIn(f"message-{header.last_index + 1} ", payloads[0]["messages"][1]["content"])

    async def test_summary_saves_large_informational_entries_and_recovers_middle_details(self):
        text = "x" * 25000 + "MIDDLE_COMMITMENT" + "z" * 25000
        self.log.record_agent_message(text)
        requests = []
        def respond(request):
            payload = self.check(request)
            requests.append(payload)
            if len(requests) == 1:
                reference = re.search(r"full source reference=(c1_[0-9a-f_]+)", payload["messages"][1]["content"])[1]
                result = self.call("read_result", {"reference": reference, "offset": 25000, "limit": 64}, "read")
            else:
                self.assertIn("MIDDLE_COMMITMENT", payload["messages"][-1]["content"])
                result = self.final("Pending: MIDDLE_COMMITMENT remains open.")
            return httpx.Response(200, json=result)
        with patch.object(summarizer, "get_settings", return_value=self.summary_settings(threshold=1)), client.use_mock_provider(httpx.MockTransport(respond)):
            self.assertTrue(await summarizer.summarize_conversation())
        header = self.memory.load_summary_header()
        self.assertEqual(header.last_index, 0)
        reference = re.search(r"c1_[0-9a-f_]+", header.summary_text)[0]
        self.assertEqual(self.read(reference), text)
        self.assertEqual(len(requests), 2)
        self.assertEqual(len(list(self.log.iter_entries())), 1)  # No self-feeding source journal.

    async def test_summary_required_user_input_and_generated_output_limits_preserve_old_progress(self):
        self.log.record_user_message("x" * 50000)
        initial = self.memory._path.read_bytes()
        with patch.object(summarizer, "get_settings", return_value=self.summary_settings(threshold=1)), patch.object(client.httpx, "AsyncClient", side_effect=AssertionError("required input cannot reach HTTP")), self.assertRaises(ContextBudgetError):
            await summarizer.summarize_conversation()
        self.assertEqual(self.memory._path.read_bytes(), initial)
        self.log.clear()
        self.log.record_user_message("small required input")
        initial = self.memory._path.read_bytes()
        with patch.object(summarizer, "get_settings", return_value=self.summary_settings(threshold=1)), client.use_mock_provider(httpx.MockTransport(lambda request: httpx.Response(200, json=self.final("x" * 10000)))), self.assertRaises(ContextBudgetError):
            await summarizer.summarize_conversation()
        self.assertEqual(self.memory._path.read_bytes(), initial)

    async def test_summary_read_budget_source_limits_and_stale_generation_do_not_commit(self):
        self.log.record_agent_message("x" * 50000)
        initial = self.memory._path.read_bytes()
        requests = []
        def respond(request):
            payload = self.check(request)
            requests.append(payload)
            first = payload["messages"][1]["content"]
            reference = re.search(r"full source reference=(c1_[0-9a-f_]+)", first)[1]
            return httpx.Response(200, json=self.call("read_result", {"reference": reference, "offset": 0, "limit": 32}, str(len(requests))))
        with patch.object(summarizer, "get_settings", return_value=self.summary_settings(threshold=1)), client.use_mock_provider(httpx.MockTransport(respond)), self.assertRaises(ContextBudgetError):
            await summarizer.summarize_conversation()
        self.assertEqual(len(requests), 2)
        self.assertEqual(self.memory._path.read_bytes(), initial)
        with patch.object(summarizer, "get_settings", return_value=self.summary_settings(threshold=1)), patch.object(summary_bounds, "MAX_ENTRY_BYTES", 128), self.assertRaises(ContextBudgetError):
            await summarizer.summarize_conversation()
        def clearing(request):
            self.check(request)
            self.store.clear()
            return httpx.Response(200, json=self.final("Old result must not revive memory"))
        with patch.object(summarizer, "get_settings", return_value=self.summary_settings(threshold=1)), client.use_mock_provider(httpx.MockTransport(clearing)), self.assertRaises(content_store.ContentExpiredError):
            await summarizer.summarize_conversation()
        self.assertEqual(self.memory._path.read_bytes(), initial)

    async def test_summary_cas_and_replaced_conversation_cannot_adopt_stale_state(self):
        self.log.record_user_message("new input")
        def respond(request):
            self.check(request)
            self.memory.write_summary_state(SummaryState(summary_text="Concurrent newer memory", last_index=7))
            return httpx.Response(200, json=self.final("Stale memory"))
        with patch.object(summarizer, "get_settings", return_value=self.summary_settings(threshold=1)), client.use_mock_provider(httpx.MockTransport(respond)), self.assertRaisesRegex(ContextBudgetError, "changed"):
            await summarizer.summarize_conversation()
        self.assertEqual(self.memory.load_summary_header().summary_text, "Concurrent newer memory")
        with capture_scope("conversation") as capture:
            stat = self.log._path.stat()
            self.memory.write_summary_state(SummaryState(summary_text="Cursor memory", last_index=0, source_offset=stat.st_size,
                                                        source_identity=[stat.st_dev, stat.st_ino], source_generation=capture.generation))
        self.log._path.write_text("short", encoding="utf-8")
        with patch.object(summarizer, "get_settings", return_value=self.summary_settings(threshold=1)), self.assertRaises(ContextBudgetError):
            await summarizer.summarize_conversation()

    def test_source_recovery_rejects_foreign_refs_exhaustion_and_old_cached_writes(self):
        with capture_scope(OWNER):
            reader = inner_context.SourceReader()
            reference = reader.save("x" * 10000, "input", provider="gmail", account_id=ACCOUNT)
            for _ in range(8):
                self.assertEqual(reader.read({"reference": reference})["status"], "ok")
            self.assertEqual(reader.read({"reference": reference})["code"], "turn_limit")
            with patch.object(ContentStore, "read_source_page", side_effect=AssertionError("foreign refs must not touch IO")):
                other = inner_context.SourceReader()
                self.assertEqual(other.read({"reference": reference})["status"], "error")
            self.store.clear()
            with self.assertRaises(content_store.ContentExpiredError):
                reader.save("x" * 10000, "input", provider="gmail", account_id=ACCOUNT)
        with capture_scope(OWNER), self.assertRaises(content_store.ContentExpiredError):
            reader.save("new text after clear", "input", provider="gmail", account_id=ACCOUNT)
