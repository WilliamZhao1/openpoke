import asyncio
from contextlib import ExitStack
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

from server import content_store, context_builder as contexts, context_recovery, draft_content as drafts
from server.config import Settings
from server.content_store import ContentStore, capture_scope, capture_text
from server.context_budget import prepare_budgeted_request
from server.agents.execution_agent import agent as worker_agent, runtime as workers, batch_manager
from server.agents.execution_agent.tools import gmail, registry
from server.agents.interaction_agent import agent as interaction_agent, runtime as interactions, tools
from server.openrouter_client import client
from server.services.conversation.log import ConversationLog
from server.services.conversation.summarization.working_memory_log import WorkingMemoryLog
from server.services.execution import AgentRoster, ExecutionAgentLogStore
from server.tests.fixtures.fake_gmail import FakeGmail, use_fake_gmail


OWNER = "worker:Alice contract"
ACCOUNT = "fixture-profile-a"  # The executed Composio routing ID, not a guessed email address.


class DraftReferenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.settings = Settings(openrouter_api_key="test-key", context_strategy="bounded", worker_discovery_strategy="bounded",
                                 interaction_agent_model="interaction-test", execution_agent_model="worker-test",
                                 execution_agent_search_model="worker-test", summarizer_model="worker-test", email_classifier_model="worker-test",
                                 model_context_windows={"interaction-test": 200000, "worker-test": 200000},
                                 context_input_tokens=32768, context_headroom_tokens=64, openrouter_max_tokens=256,
                                 conversation_summary_threshold=0)
        self.memory = WorkingMemoryLog(self.root / "memory.log")
        self.stack.enter_context(patch("server.services.conversation.log._resolve_working_memory_log", return_value=self.memory))
        self.log = ConversationLog(self.root / "conversation" / "poke_conversation.log")
        self.logs = ExecutionAgentLogStore(self.root / "execution_agents")
        self.roster = AgentRoster(self.root / "execution_agents" / "roster.json")
        for name in ("Alice contract", "Alice lunch"):
            self.roster.add_agent(name)
        for module in (content_store, workers, interactions, client):
            self.stack.enter_context(patch.object(module, "get_settings", return_value=self.settings))
        self.stack.enter_context(patch("server.services.conversation.log.get_settings", return_value=self.settings))
        self.stack.enter_context(patch.object(content_store, "get_data_dir", return_value=self.root))
        for module in (contexts, context_recovery, interaction_agent, tools):
            self.stack.enter_context(patch.object(module, "get_agent_roster", return_value=self.roster))
        for module in (interactions, tools, context_recovery):
            self.stack.enter_context(patch.object(module, "get_conversation_log", return_value=self.log))
        self.stack.enter_context(patch.object(interactions, "get_working_memory_log", return_value=self.memory))
        for module in (worker_agent, tools, context_recovery):
            self.stack.enter_context(patch.object(module, "get_execution_agent_logs", return_value=self.logs))
        self.stack.enter_context(patch.object(gmail, "_LOG_STORE", self.logs))
        self.store = ContentStore(self.root / "content")
        self.fake = FakeGmail()

    def source(self, text, *, kind="GMAIL_FETCH_EMAILS.result", provider="gmail", account_id=ACCOUNT):
        return capture_text(text, kind=kind, provider=provider, account_id=account_id, min_bytes=-1)

    def create(self, body="Exact body\r\n旅🦉", **options):
        with capture_scope(OWNER), use_fake_gmail(self.fake):
            reference = self.source(json.dumps({"data": {"a/b~c": [body]}}, ensure_ascii=False))
            result = gmail.gmail_create_draft("Exact.Recipient@example.test", "Exact subject",
                                             body_reference={"reference": reference, "pointer": "/data/a~1b~0c/0"}, **options)
        return result

    def body_path(self, reference):
        _, generation, identifier = reference.split("_")
        return self.store.root / "objects" / generation / identifier / "body.txt"

    def test_create_from_json_reference_preserves_complete_body_and_all_recipient_options(self):
        body = "<p>Exact\r\n" + "旅🦉 &amp; " * 15000 + "MIDDLE\x00end</p>  "
        attachment = {"s3key": "fixture/file", "name": "contract.pdf", "mimetype": "application/pdf"}
        result = self.create(body, cc=["CC@example.test"], bcc=["BCC@example.test"], extra_recipients=["Extra@example.test"],
                             is_html=True, thread_id="18fa000000000101", attachment=attachment)
        effect = self.fake.effects[0]
        self.assertEqual(effect["body"], body)
        self.assertEqual(effect["message"]["to"], "Exact.Recipient@example.test")
        self.assertEqual(effect["message"]["cc"], ["CC@example.test"])
        self.assertEqual(effect["message"]["bcc"], ["BCC@example.test"])
        self.assertEqual(effect["message"]["extra_recipients"], ["Extra@example.test"])
        self.assertEqual(effect["message"]["attachmentList"], [attachment])
        self.assertIn("still required", result["review"])
        self.assertNotIn(body, json.dumps(result))
        with capture_scope(OWNER):
            draft = drafts.load_draft(result["draft_reference"], account_id=ACCOUNT, for_action=True)
            self.assertEqual(draft["body"], body)
            self.assertEqual(draft["body_sha256"], sha256(body.encode()).hexdigest())
            self.assertEqual(drafts.resolve_body(result["body_reference"], account_id=ACCOUNT), body)

    def test_full_review_and_bounded_history_keep_exact_draft_refs_for_small_and_giant_bodies(self):
        for body in ("small\r\n  body C:\\new-folder \\n literal\u2028旅  ", "large\r\n" + "旅🦉" * 40000 + "\x00last  "):
            with self.subTest(size=len(body)):
                self.log.clear()
                result = self.create(body, cc=["cc@example.test"], bcc=["bcc@example.test"], extra_recipients=["extra@example.test"], is_html=True)
                with capture_scope("conversation"):
                    self.log.record_agent_message("[SUCCESS] Alice contract: draft reference available")
                    review = tools.send_draft(draft_reference=result["draft_reference"])
                    self.assertTrue(review.success)
                    original_file = self.log._path.read_bytes()
                    history = contexts.load_recent_history(self.log)
                    self.assertEqual(self.log._path.read_bytes(), original_file)
                    rendered = "".join(history.episodes)
                    self.assertIn(result["draft_reference"]["reference"], rendered)
                    self.assertIn("Alice contract", rendered)
                    self.assertIn("cc@example.test", rendered)
                    self.assertIn("bcc@example.test", rendered)
                    self.assertIn("explicit confirmation", rendered)
                    self.assertNotIn(body, rendered)
                    self.assertLess(len(rendered.encode()), 5000)
                    displayed = next(entry.content for entry in self.log.to_chat_messages() if entry.role == "assistant")
                    self.assertIn(body, displayed)
                    self.assertIn("Additional recipients: extra@example.test", displayed)
        self.assertTrue(all(effect["kind"] == "draft_created" for effect in self.fake.effects))

    def test_inline_overrides_cannot_change_a_referenced_draft_or_its_recipients(self):
        result = self.create()
        with capture_scope("conversation"):
            for overrides in ({"to": "other@example.test"}, {"subject": "changed"}, {"body": "preview"}):
                with self.subTest(overrides=overrides), self.assertRaises(drafts.DraftReferenceError):
                    tools.send_draft(draft_reference=result["draft_reference"], **overrides)
        with capture_scope(OWNER), use_fake_gmail(self.fake):
            with self.assertRaises(drafts.DraftReferenceError):
                gmail.gmail_execute_draft("different-id", draft_reference=result["draft_reference"])
            with self.assertRaises(drafts.DraftReferenceError):
                gmail.gmail_create_draft("recipient@example.test", "subject", "inline", body_reference=result["body_reference"])
        self.assertEqual(len(self.fake.effects), 1)
        self.assertEqual(list(self.log.iter_entries()), [])

    def test_other_worker_and_forged_owner_selectors_never_resolve_the_original(self):
        result = self.create()
        before = len(self.fake.calls)
        with capture_scope("worker:Alice lunch"), use_fake_gmail(self.fake):
            for selector in (result["draft_reference"], {"reference": result["draft_reference"]["reference"]}):
                with self.assertRaises(drafts.DraftReferenceError):
                    gmail.gmail_execute_draft(draft_reference=selector)
            with self.assertRaises(drafts.DraftReferenceError):
                gmail.gmail_create_draft("recipient@example.test", "subject", body_reference=result["body_reference"])
        with capture_scope("conversation"):
            with self.assertRaises(drafts.DraftReferenceError):
                tools.send_draft(draft_reference={**result["draft_reference"], "agent_name": "Alice lunch"})
        self.assertEqual(len(self.fake.calls), before)

    def test_mailbox_change_does_not_rebind_body_or_draft_references(self):
        result = self.create()
        before = len(self.fake.calls)
        with capture_scope(OWNER), use_fake_gmail(self.fake, profile_id="fixture-profile-b"):
            with self.assertRaisesRegex(drafts.DraftReferenceError, "mailbox"):
                gmail.gmail_execute_draft(draft_reference=result["draft_reference"])
            with self.assertRaisesRegex(drafts.DraftReferenceError, "mailbox"):
                gmail.gmail_create_draft("recipient@example.test", "subject", body_reference=result["body_reference"])
        with capture_scope("conversation"), use_fake_gmail(self.fake, profile_id="fixture-profile-b"):
            review = tools.send_draft(draft_reference=result["draft_reference"])
            self.assertEqual(review.payload["account_id"], ACCOUNT)
        self.assertEqual(len(self.fake.calls), before)

    def test_unknown_mailbox_draft_can_be_reviewed_but_cannot_be_sent_by_reference(self):
        with capture_scope(OWNER):
            selector = drafts.save_draft(to="recipient@example.test", subject="Unknown mailbox", body="Exact unknown text",
                                         account_id=None, draft_id="unqualified-id", record_reference=lambda ref, kind: self.logs.record_content_reference("Alice contract", ref, kind))
        with capture_scope("conversation"):
            review = tools.send_draft(draft_reference=selector)
            self.assertIsNone(review.payload["account_id"])
        with capture_scope(OWNER), use_fake_gmail(self.fake):
            with self.assertRaisesRegex(drafts.DraftReferenceError, "unknown"):
                gmail.gmail_execute_draft(draft_reference=selector)
            with self.assertRaisesRegex(drafts.DraftReferenceError, "unknown"):
                gmail.gmail_create_draft("recipient@example.test", "subject", body_reference=review.payload["body_reference"])
        self.assertEqual(self.fake.calls, [])

    def test_missing_truncated_and_changed_same_size_bodies_fail_before_effects_or_review(self):
        result = self.create("Exact original body")
        path = self.body_path(result["body_reference"]["reference"])
        original = path.read_bytes()
        for damaged in (None, original[:-1], b"x" * len(original)):
            with self.subTest(damaged=damaged):
                if damaged is None:
                    path.unlink()
                else:
                    path.write_bytes(damaged)
                with capture_scope(OWNER), use_fake_gmail(self.fake):
                    with self.assertRaises(drafts.DraftReferenceError):
                        gmail.gmail_execute_draft(draft_reference=result["draft_reference"])
                with capture_scope("conversation"):
                    with self.assertRaises(drafts.DraftReferenceError):
                        tools.send_draft(draft_reference=result["draft_reference"])
                path.write_bytes(original)
        self.assertEqual(len(self.fake.effects), 1)
        self.assertEqual(list(self.log.iter_entries()), [])

    def test_body_pointer_missing_ambiguous_or_non_string_is_an_explicit_limitation(self):
        with capture_scope(OWNER), use_fake_gmail(self.fake):
            source = self.source('{"body":"full", "array":["exact"], "object":{}, "a~b/c":"escaped"}')
            cases = [{"reference": source}, {"reference": source, "pointer": "/missing"}, {"reference": source, "pointer": "/object"},
                     {"reference": source, "pointer": "/array/01"}, {"reference": source, "pointer": "/array/-1"},
                     {"reference": source, "pointer": "/bad~2escape"}, {"reference": source, "pointer": "/array/-"},
                     {"reference": source, "pointer": "body"}, {"reference": "../../history.log"},
                     {"reference": source, "pointer": "/body", "owner": OWNER}]
            for selector in cases:
                with self.subTest(selector=selector), self.assertRaises(drafts.DraftReferenceError):
                    gmail.gmail_create_draft("recipient@example.test", "subject", body_reference=selector)
            duplicate = self.source('{"body":"first", "body":"second"}')
            with self.assertRaises(drafts.DraftReferenceError):
                drafts.resolve_body({"reference": duplicate, "pointer": "/body"}, account_id=ACCOUNT)
            preview = self.source('{"result":{"body":"historically shortened..."}}', kind="model_tool_result", provider=None, account_id=None)
            with self.assertRaisesRegex(drafts.DraftReferenceError, "unknown"):
                drafts.resolve_body({"reference": preview, "pointer": "/result/body"}, account_id=ACCOUNT)
            summary = self.source('{"body":"only a summary"}', kind="task_email_search.result")
            with self.assertRaisesRegex(drafts.DraftReferenceError, "aggregate"):
                drafts.resolve_body({"reference": summary, "pointer": "/body"}, account_id=ACCOUNT)
            for document, pointer in (({"snippet": "short"}, "/snippet"), ({"body": "cut", "truncated": True}, "/body")):
                incomplete = self.source(json.dumps(document))
                with self.assertRaisesRegex(drafts.DraftReferenceError, "incomplete"):
                    drafts.resolve_body({"reference": incomplete, "pointer": pointer}, account_id=ACCOUNT)
            self.assertEqual(drafts.resolve_body({"reference": source, "pointer": "/a~0b~1c"}, account_id=ACCOUNT), "escaped")
            root = self.source(json.dumps("root string\r\n旅🦉"))
            self.assertEqual(drafts.resolve_body({"reference": root, "pointer": ""}, account_id=ACCOUNT), "root string\r\n旅🦉")
        self.assertEqual(self.fake.calls, [])

    def test_empty_body_and_backend_read_limits_are_exact_and_never_silently_truncate(self):
        result = self.create("")
        with capture_scope(OWNER):
            self.assertEqual(drafts.load_draft(result["draft_reference"])["body"], "")
            with patch.object(drafts, "MAX_SOURCE_BYTES", 2), self.assertRaisesRegex(drafts.DraftReferenceError, "limit"):
                source = self.source("long pure body", kind="email_draft_body")
                drafts.resolve_body({"reference": source}, account_id=ACCOUNT)
        self.assertEqual(self.fake.effects[0]["body"], "")

    def test_manifest_body_qualification_and_digest_cannot_point_to_another_source(self):
        result = self.create("original body")
        with capture_scope(OWNER):
            original = drafts.load_draft(result["draft_reference"])
            manifest = json.loads(self.body_path(result["draft_reference"]["reference"]).read_text(encoding="utf-8"))
            for body, account in (("original body", "fixture-profile-b"), ("differentbody", ACCOUNT)):
                bad_body = self.source(body, kind="email_draft_body", account_id=account)
                forged = self.source(json.dumps({**manifest, "body_reference": bad_body}), kind="email_draft")
                with self.assertRaises(drafts.DraftReferenceError):
                    drafts.load_draft({"reference": forged})
            self.assertEqual(original["body"], "original body")

    def test_review_marker_binding_is_checked_instead_of_hiding_a_different_visible_draft(self):
        result = self.create("Exact displayed body")
        with capture_scope("conversation"):
            self.log.record_agent_message("Alice contract returned draft")
            tools.send_draft(draft_reference=result["draft_reference"])
            data = self.log._path.read_text(encoding="utf-8")
            self.log._path.write_text(data.replace("Exact displayed body", "Wrong displayed body"), encoding="utf-8")
            with self.assertRaises(drafts.DraftReferenceError):
                contexts.load_recent_history(self.log)
            self.log._path.write_text(data, encoding="utf-8")
            notice = next(payload for tag, _, payload in self.log.iter_entries() if tag == "draft_review")
            original = json.loads(notice)["display_sha256"]
            self.log._path.write_text(data.replace(original, "0" * 64), encoding="utf-8")
            with self.assertRaises(drafts.DraftReferenceError):
                contexts.load_recent_history(self.log)

    def test_clear_invalidates_old_drafts_and_body_refs_without_resolving_replacement_history(self):
        result = self.create("old body")
        with capture_scope(OWNER), use_fake_gmail(self.fake):
            self.store.clear()
            with self.assertRaises(content_store.ContentExpiredError):
                gmail.gmail_execute_draft(draft_reference=result["draft_reference"])
        with capture_scope("conversation"):
            with self.assertRaises(content_store.ContentExpiredError):
                tools.send_draft(draft_reference=result["draft_reference"])
            self.store.clear()
            with self.assertRaises(content_store.ContentExpiredError):
                self.log.record_draft_review(result["draft_reference"], "late review marker")
        self.assertEqual(len(self.fake.effects), 1)
        self.assertEqual(list(self.log.iter_entries()), [])

    def test_draft_refs_survive_a_network_blocked_fresh_process_restart(self):
        body = "persisted\r\n旅🦉\x00end"
        result = self.create(body, cc=["cc@example.test"])
        script = """
import json, socket, sys
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import patch
def reject(*args, **kwargs):
    raise AssertionError('No network in draft restart tests')
socket.socket.connect = socket.socket.connect_ex = reject
from server import content_store, draft_content
with patch.object(content_store, 'get_settings', return_value=SimpleNamespace(context_strategy='bounded')):
    with content_store.capture_scope('conversation'):
        draft = draft_content.load_draft(json.loads(sys.argv[1]))
print(json.dumps({'sha256': sha256(draft['body'].encode()).hexdigest(), 'to': draft['to'], 'cc': draft['cc'], 'account': draft['account_id']}))
"""
        environment = dict(os.environ, OPENPOKE_DATA_DIR=str(self.root), OPENROUTER_API_KEY="test-key", COMPOSIO_API_KEY="test-key",
                           COMPOSIO_GMAIL_AUTH_CONFIG_ID="test-auth", OPENPOKE_CONTEXT_STRATEGY="legacy", OPENPOKE_MODEL_CONTEXT_WINDOWS="{}")
        probe = subprocess.run([sys.executable, "-c", script, json.dumps(result["draft_reference"])], env=environment,
                               capture_output=True, text=True, timeout=15, cwd=Path(__file__).resolve().parents[2])
        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertEqual(json.loads(probe.stdout), {"sha256": sha256(body.encode()).hexdigest(), "to": "Exact.Recipient@example.test", "cc": ["cc@example.test"], "account": ACCOUNT})

    def test_schema_changes_are_bounded_only_and_have_existing_executable_handlers(self):
        for bounded in (False, True):
            schemas = registry.get_tool_schemas(bounded_context=bounded)
            handlers = registry.get_tool_registry("Alice contract", bounded_context=bounded)
            self.assertEqual({schema["function"]["name"] for schema in schemas}, set(handlers))
            create = next(schema["function"] for schema in schemas if schema["function"]["name"] == "gmail_create_draft")
            self.assertEqual("body_reference" in create["parameters"]["properties"], bounded)
            self.assertEqual("body" in create["parameters"]["required"], not bounded)
            display = next(schema["function"] for schema in tools.get_tool_schemas(recovery=bounded) if schema["function"]["name"] == "send_draft")
            self.assertEqual("draft_reference" in display["parameters"]["properties"], bounded)

    def test_reply_and_forward_resolve_exact_referenced_text_without_changing_recipients(self):
        body = "Reviewed exact reply\r\n" + "旅🦉" * 1000
        result = self.create(body)
        with capture_scope(OWNER), use_fake_gmail(self.fake):
            gmail.gmail_reply_to_thread("18fa000000000101", "Reply.Recipient@example.test", body_reference=result["body_reference"], cc=["cc@example.test"])
            gmail.gmail_forward_email("18fa000000000001", "Forward.Recipient@example.test", body_reference=result["body_reference"])
        self.assertEqual(self.fake.effects[-2]["body"], body)
        self.assertEqual(self.fake.effects[-2]["message"]["to"], "Reply.Recipient@example.test")
        self.assertEqual(self.fake.effects[-2]["message"]["cc"], ["cc@example.test"])
        self.assertTrue(self.fake.effects[-1]["body"].startswith(body + "\n\n"))
        self.assertEqual(self.fake.effects[-1]["message"]["to"], "Forward.Recipient@example.test")

    def test_provider_missing_draft_id_is_explicit_and_never_guessed_for_sending(self):
        with capture_scope(OWNER), patch.object(gmail, "get_active_gmail_user_id", return_value=ACCOUNT), patch.object(gmail, "execute_gmail_tool", return_value={"successful": True, "data": {}}) as backend:
            result = gmail.gmail_create_draft("recipient@example.test", "subject", "x" * 6000)
            self.assertEqual(result["status"], "draft_id_unavailable")
            self.assertIsNone(result["draft_id"])
            with self.assertRaisesRegex(drafts.DraftReferenceError, "draft ID"):
                gmail.gmail_execute_draft(draft_reference=result["draft_reference"])
            backend.assert_called_once()

    def test_review_markers_preserve_exact_worker_names_and_remain_readable_in_legacy_mode(self):
        name = "Special\\name\nreview"
        self.roster.add_agent(name)
        body = "Literal \\n text\r\n旅\u2028body"
        with capture_scope(f"worker:{name}"), use_fake_gmail(self.fake):
            source = self.source(json.dumps({"body": body}, ensure_ascii=False))
            created = gmail.gmail_create_draft("recipient@example.test", "subject", body_reference={"reference": source, "pointer": "/body"})
        with capture_scope("conversation"):
            tools.send_draft(draft_reference=created["draft_reference"])
            history = contexts.load_recent_history(self.log)
            notice = next(json.loads(payload) for tag, _, payload in self.log.iter_entries() if tag == "draft_review")
            self.assertEqual(notice["draft_reference"]["agent_name"], name)
            self.assertIn(created["draft_reference"]["reference"], "".join(history.episodes))
        with patch.object(content_store, "get_settings", return_value=self.settings.model_copy(update={"context_strategy": "legacy"})):
            self.assertIn(body, self.log.to_chat_messages()[-1].content)

    async def test_post_create_reference_failure_stops_worker_without_replaying_external_action(self):
        with capture_scope(OWNER):
            source = self.source(json.dumps({"body": "x" * 10000}))
        call = {"choices": [{"message": {"tool_calls": [{"id": "create", "type": "function", "function": {
            "name": "gmail_create_draft", "arguments": json.dumps({"recipient_email": "recipient@example.test", "subject": "subject", "body_reference": {"reference": source, "pointer": "/body"}})}}]}}]}
        original_capture = drafts.capture_text

        def fail_manifest(text, **kwargs):
            if kwargs["kind"] == "email_draft":
                raise content_store.ContentStoreError("draft persistence failed")
            return original_capture(text, **kwargs)

        with use_fake_gmail(self.fake), patch.object(drafts, "capture_text", fail_manifest), patch.object(workers.ExecutionAgentRuntime, "_make_llm_call", new=AsyncMock(return_value=call)) as model:
            result = await workers.ExecutionAgentRuntime("Alice contract").execute("Create the draft; do not send it")
        self.assertFalse(result.success)
        self.assertIn("check the operation outcome", result.error)
        self.assertEqual([effect["kind"] for effect in self.fake.effects], ["draft_created"])
        model.assert_awaited_once()

    async def test_post_review_marker_failure_does_not_repeat_the_full_visible_review(self):
        created = self.create("body\r\n" + "x" * 10000)
        call = {"choices": [{"message": {"tool_calls": [{"id": "review", "type": "function", "function": {
            "name": "send_draft", "arguments": json.dumps({"draft_reference": created["draft_reference"]})}}]}}]}
        with patch.object(self.log, "record_draft_review", side_effect=OSError("marker failed")), patch.object(interactions.InteractionAgentRuntime, "_make_llm_call", new=AsyncMock(return_value=call)) as model:
            result = await interactions.InteractionAgentRuntime().handle_agent_message("Alice contract: review the referenced draft")
        self.assertFalse(result.success)
        self.assertIn("check the displayed draft", result.error)
        self.assertEqual(len([entry for entry in self.log.to_chat_messages() if entry.role == "assistant"]), 1)
        model.assert_awaited_once()

    async def test_large_draft_two_agent_review_confirmation_and_send_stay_bounded_and_exact(self):
        body = "Full draft\r\n" + "旅🦉" * 40000 + "\x00middle and final text  "
        with capture_scope(OWNER):
            source = self.source(json.dumps({"document": {"body": body}}, ensure_ascii=False))
        requests, created = [], {}
        manager = Mock(execute_agent=AsyncMock(return_value=Mock(success=True)))
        self.stack.enter_context(patch.object(tools, "_EXECUTION_BATCH_MANAGER", manager))

        def invoke(name, arguments):
            return {"choices": [{"message": {"tool_calls": [{"id": f"call-{len(requests)}", "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)}}]}}]}

        def final(text):
            return {"choices": [{"message": {"content": text}}]}

        def respond(request):
            payload = json.loads(request.content)
            requests.append(payload)
            prepare_budgeted_request(payload, context_window=200000, input_cap=32768, headroom=64)
            current = payload["messages"][1]["content"]
            last = payload["messages"][-1]
            prior = json.loads(last["content"]) if last["role"] == "tool" else None
            if payload["model"] == "worker-test":
                confirming = "User confirmed" in current
                if prior:
                    if prior["tool"] == "gmail_create_draft":
                        created.update(prior["result"])
                        return httpx.Response(200, json=final(json.dumps({"draft_reference": created["draft_reference"]})))
                    return httpx.Response(200, json=final("Sent confirmed draft"))
                arguments = {"draft_reference": created["draft_reference"]} if confirming else {
                    "recipient_email": "Exact.Recipient@example.test", "subject": "Exact subject", "cc": ["cc@example.test"], "bcc": ["bcc@example.test"],
                    "body_reference": {"reference": source, "pointer": "/document/body"}}
                return httpx.Response(200, json=invoke("gmail_execute_draft" if confirming else "gmail_create_draft", arguments))
            confirming = "Yes, send the reviewed draft" in current
            if prior:
                if prior["tool"] == "send_draft":
                    return httpx.Response(200, json=invoke("send_message_to_user", {"message": "Please confirm this exact draft before sending."}))
                return httpx.Response(200, json=final("Waiting for confirmation" if not confirming else "Dispatching confirmed draft"))
            if confirming:
                self.assertIn(created["draft_reference"]["reference"], current)
                self.assertNotIn(body, current)
                return httpx.Response(200, json=invoke("send_message_to_agent", {"agent_name": "Alice contract", "instructions": "User confirmed: " + json.dumps(created["draft_reference"])}))
            return httpx.Response(200, json=invoke("send_draft", {"draft_reference": created["draft_reference"]}))

        with use_fake_gmail(self.fake), client.use_mock_provider(httpx.MockTransport(respond)):
            worker = await workers.ExecutionAgentRuntime("Alice contract").execute("Create the exact draft from the saved document body; do not send")
            self.assertTrue(worker.success, worker)
            callback = batch_manager.ExecutionBatchManager()._format_batch_payload([worker])
            interaction = await interactions.InteractionAgentRuntime().handle_agent_message(callback)
            self.assertTrue(interaction.success, interaction)
            self.assertEqual([effect["kind"] for effect in self.fake.effects], ["draft_created"])
            full_review = next(entry.content for entry in self.log.to_chat_messages() if entry.role == "assistant")
            self.assertIn(body, full_review)
            confirmed = await interactions.InteractionAgentRuntime().execute("Yes, send the reviewed draft")
            self.assertTrue(confirmed.success, confirmed)
            await asyncio.sleep(0)
            manager.execute_agent.assert_awaited_once()
            instructions = manager.execute_agent.call_args.args[1]
            sent = await workers.ExecutionAgentRuntime("Alice contract").execute(instructions)
            self.assertTrue(sent.success, sent)
        self.assertEqual([effect["kind"] for effect in self.fake.effects], ["draft_created", "draft_sent"])
        self.assertEqual(self.fake.effects[-1]["body"], body)
        self.assertEqual(self.fake.effects[-1]["message"]["cc"], ["cc@example.test"])
        self.assertEqual(self.fake.effects[-1]["message"]["bcc"], ["bcc@example.test"])
        self.assertTrue(all(len(json.dumps(request).encode()) < 32768 for request in requests))
