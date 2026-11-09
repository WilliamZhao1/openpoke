"""Release checks across HTTP, actual agent loops, scheduler and local stores."""

import asyncio
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

from evals.agent_overload.engine import capture_tasks, drain
from server import content_store, context_builder, context_recovery, services
from server.app import app
from server.config import Settings
from server.content_store import ContentStore, ContentExpiredError, capture_scope, capture_text
from server.context_budget import prepare_budgeted_request
from server.agents.execution_agent import agent as worker_agent, runtime as workers, batch_manager
from server.agents.execution_agent.tools import gmail, registry, triggers
from server.agents.interaction_agent import agent as interaction_agent, runtime as interactions, tools
from server.openrouter_client import client
from server.routes import chat
from server.services.conversation import chat_handler
from server.services.conversation.log import ConversationLog
from server.services.conversation.summarization.working_memory_log import WorkingMemoryLog
from server.services.execution import AgentRoster, ExecutionAgentLogStore
from server.services import trigger_scheduler
from server.services.triggers import TriggerService
from server.services.triggers import service as trigger_service_module
from server.services.triggers.store import TriggerStore
from server.tests.fixtures.fake_gmail import FakeGmail, use_fake_gmail


OWNER = "Alice contract"
ACCOUNT = "fixture-profile-a"


class BoundedApplicationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.settings = Settings(openrouter_api_key="test-key", context_strategy="bounded", worker_discovery_strategy="bounded",
            interaction_agent_model="release-interaction", execution_agent_model="release-worker", execution_agent_search_model="release-worker",
            summarizer_model="release-worker", email_classifier_model="release-worker",
            model_context_windows={"release-interaction": 200000, "release-worker": 200000},
            context_input_tokens=32768, context_headroom_tokens=64, openrouter_max_tokens=256, conversation_summary_threshold=0)
        self.memory = WorkingMemoryLog(self.root / "conversation" / "memory.log")
        self.stack.enter_context(patch("server.services.conversation.log._resolve_working_memory_log", return_value=self.memory))
        self.log = ConversationLog(self.root / "conversation" / "conversation.log")
        self.logs = ExecutionAgentLogStore(self.root / "execution_agents")
        self.roster = AgentRoster(self.logs._base_dir / "roster.json")
        for name in (OWNER, "Alice lunch"):
            self.roster.add_agent(name)
        self.service = TriggerService(TriggerStore(self.root / "triggers.db"))
        for module in (content_store, workers, interactions, batch_manager, client):
            self.stack.enter_context(patch.object(module, "get_settings", return_value=self.settings))
        self.stack.enter_context(patch("server.services.conversation.log.get_settings", return_value=self.settings))
        self.stack.enter_context(patch.object(content_store, "get_data_dir", return_value=self.root))
        for module in (context_builder, context_recovery, interaction_agent, tools, batch_manager, services):
            self.stack.enter_context(patch.object(module, "get_agent_roster", return_value=self.roster))
        for module in (interactions, tools, context_recovery, chat_handler, chat):
            self.stack.enter_context(patch.object(module, "get_conversation_log", return_value=self.log))
        self.stack.enter_context(patch.object(interactions, "get_working_memory_log", return_value=self.memory))
        for module in (worker_agent, tools, context_recovery, services):
            self.stack.enter_context(patch.object(module, "get_execution_agent_logs", return_value=self.logs))
        for module in (gmail, triggers):
            self.stack.enter_context(patch.object(module, "_LOG_STORE", self.logs))
        self.stack.enter_context(patch.object(triggers, "_TRIGGER_SERVICE", self.service))
        for module in (chat, trigger_scheduler):
            self.stack.enter_context(patch.object(module, "get_trigger_service", return_value=self.service))
        self.stack.enter_context(patch.object(triggers, "get_timezone_store", return_value=Mock(get_timezone=Mock(return_value="UTC"))))
        self.manager = batch_manager.ExecutionBatchManager()
        self.addAsyncCleanup(self.manager.shutdown)
        self.stack.enter_context(patch.object(tools, "_EXECUTION_BATCH_MANAGER", self.manager))
        self.stack.enter_context(patch.object(trigger_scheduler, "ExecutionBatchManager", return_value=self.manager))
        self.fake = FakeGmail()
        self.requests = []

    def request(self, request):
        payload = json.loads(request.content)
        prepare_budgeted_request(payload, context_window=200000, input_cap=32768, headroom=64)
        self.requests.append(payload)
        return payload

    def invoke(self, name, arguments):
        return httpx.Response(200, json={"choices": [{"message": {"tool_calls": [{
            "id": f"call-{len(self.requests)}", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}
        }]}}]})

    def final(self, text):
        return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})

    def api(self):
        # ASGITransport exercises routes without opening a socket or starting polling.
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://release.test")

    def test_trigger_store_releases_connections_after_success_and_failure(self):
        opened = []
        original = sqlite3.connect

        def connect(*args, **kwargs):
            connection = original(*args, **kwargs)
            opened.append(connection)
            return connection

        try:
            with patch("server.services.triggers.store.sqlite3.connect", side_effect=connect):
                self.assertEqual(self.service.list_triggers(agent_name=OWNER), [])
                with self.assertRaises(sqlite3.ProgrammingError):
                    self.service._store.fetch_one(object(), OWNER)
            self.assertEqual(len(opened), 2)
            for connection in opened:
                with self.assertRaisesRegex(sqlite3.ProgrammingError, "closed"):
                    connection.execute("SELECT 1")
        finally:
            for connection in opened:
                connection.close()

    async def test_http_acceptance_is_async_and_invalid_submissions_do_not_call_provider(self):
        started, release = asyncio.Event(), asyncio.Event()

        async def respond(request):
            self.request(request)
            started.set()
            await release.wait()
            return self.final("The accepted request completed.")

        with client.use_mock_provider(httpx.MockTransport(respond)):
            async with self.api() as api, capture_tasks() as tasks:
                self.assertEqual((await api.post("/api/v1/chat/send", json={"messages": []})).status_code, 400)
                self.assertEqual((await api.post("/api/v1/chat/send", json={"messages": "invalid"})).status_code, 422)
                self.assertEqual(self.requests, [])
                response = await api.post("/api/v1/chat/send", json={"messages": [{"role": "user", "content": "Release check"}]})
                self.assertEqual(response.status_code, 202)
                await asyncio.wait_for(started.wait(), timeout=2)
                history = (await api.get("/api/v1/chat/history")).json()["messages"]
                self.assertEqual([row["role"] for row in history], ["user"])
                release.set()
                await drain(tasks)
                history = (await api.get("/api/v1/chat/history")).json()["messages"]
        self.assertEqual([row["content"] for row in history], ["Release check", "The accepted request completed."])
        self.assertEqual(len(self.requests), 1)

    async def test_http_provider_failure_becomes_a_visible_history_reply(self):
        def respond(request):
            self.request(request)
            return httpx.Response(503, json={"error": {"message": "synthetic unavailable provider"}})

        with client.use_mock_provider(httpx.MockTransport(respond)):
            async with self.api() as api, capture_tasks() as tasks:
                response = await api.post("/api/v1/chat/send", json={"messages": [{"role": "user", "content": "Release failure check"}]})
                self.assertEqual(response.status_code, 202)
                await drain(tasks)
                history = (await api.get("/api/v1/chat/history")).json()["messages"]
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(history[-1]["role"], "assistant")
        self.assertIn("couldn't process", history[-1]["content"])
        self.assertNotIn("synthetic unavailable provider", history[-1]["content"])

    async def test_http_large_review_confirmation_callbacks_and_clear_preserve_exact_content(self):
        body = "Exact review\\n stays literal\r\n" + "旅🦉" * 40000 + '\nMIDDLE <&> \\t\nEND  '
        created = {}
        with capture_scope(f"worker:{OWNER}") as capture:
            generation = capture.generation
            source = capture_text(json.dumps({"document": {"body": body}}, ensure_ascii=False), kind="GMAIL_FETCH_EMAILS.result",
                                  provider="gmail", account_id=ACCOUNT, min_bytes=-1)
            self.logs.record_content_reference(OWNER, source, "GMAIL_FETCH_EMAILS.result")

        def respond(request):
            payload = self.request(request)
            current, last = payload["messages"][1]["content"], payload["messages"][-1]
            prior = json.loads(last["content"]) if last["role"] == "tool" else None
            if payload["model"] == "release-worker":
                if prior:
                    self.assertEqual(prior["status"], "success")
                    if prior["tool"] == "gmail_create_draft":
                        created.update(prior["result"])
                        return self.final("CREATED_FOR_REVIEW " + json.dumps({"draft_reference": created["draft_reference"]}))
                    return self.final("SENT_REVIEWED_DRAFT")
                if "CONFIRM_SEND_REVIEWED" in current:
                    return self.invoke("gmail_execute_draft", {"draft_reference": created["draft_reference"]})
                return self.invoke("gmail_create_draft", {"recipient_email": "Exact.Recipient@example.test", "subject": "Exact subject",
                    "cc": ["cc@example.test"], "bcc": ["bcc@example.test"], "body_reference": {"reference": source, "pointer": "/document/body"}})
            if prior:
                if prior["tool"] == "send_draft":
                    return self.invoke("send_message_to_user", {"message": "Please confirm the complete reviewed draft."})
                return self.final("Waiting for the next event.")
            if "<new_agent_message>" in current:
                if "SENT_REVIEWED_DRAFT" in current:
                    return self.invoke("send_message_to_user", {"message": "Sent the exact reviewed draft."})
                return self.invoke("send_draft", {"draft_reference": created["draft_reference"]})
            if "CONFIRM_SEND_REVIEWED" in current:
                self.assertNotIn(body, json.dumps(payload, ensure_ascii=False))
                self.assertIn(created["draft_reference"]["reference"], current)
                return self.invoke("send_message_to_agent", {"agent_name": OWNER, "instructions": "CONFIRM_SEND_REVIEWED " + json.dumps(created["draft_reference"])})
            return self.invoke("send_message_to_agent", {"agent_name": OWNER, "instructions": "Create the exact source draft for review; do not send. " + source})

        with use_fake_gmail(self.fake), client.use_mock_provider(httpx.MockTransport(respond)):
            async with self.api() as api, capture_tasks() as tasks:
                response = await api.post("/api/v1/chat/send", json={"messages": [{"role": "user", "content": "Prepare my contract draft for review. " + source}]})
                self.assertEqual(response.status_code, 202)
                await drain(tasks)
                self.assertEqual([effect["kind"] for effect in self.fake.effects], ["draft_created"])
                history = (await api.get("/api/v1/chat/history")).json()["messages"]
                review = next(row["content"] for row in history if body in row["content"])
                self.assertIn("To: Exact.Recipient@example.test", review)
                self.assertTrue(any("Please confirm" in row["content"] for row in history))
                self.settings.context_strategy = self.settings.worker_discovery_strategy = "legacy"
                legacy_history = (await api.get("/api/v1/chat/history")).json()["messages"]
                self.assertEqual(legacy_history, history)
                self.settings.context_strategy = self.settings.worker_discovery_strategy = "bounded"
                response = await api.post("/api/v1/chat/send", json={"messages": [{"role": "user", "content": "CONFIRM_SEND_REVIEWED: send the complete draft I reviewed."}]})
                self.assertEqual(response.status_code, 202)
                await drain(tasks)
                self.assertEqual([effect["kind"] for effect in self.fake.effects], ["draft_created", "draft_sent"])
                sent = self.fake.effects[-1]
                self.assertEqual(sent["body"], body)
                self.assertEqual(sent["message"]["to"], "Exact.Recipient@example.test")
                self.assertEqual(sent["message"]["cc"], ["cc@example.test"])
                self.assertEqual(sent["message"]["bcc"], ["bcc@example.test"])
                self.assertEqual(set(self.roster.get_agents()), {OWNER, "Alice lunch"})
                for name in self.roster.get_agents():
                    self.service.create_trigger(agent_name=name, payload="Pending reminder", timezone_name="UTC")
                unrelated = self.root / "unrelated.txt"
                unrelated.write_text("preserve", encoding="utf-8")
                response = await api.delete("/api/v1/chat/history")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"ok": True})
                self.assertEqual((await api.get("/api/v1/chat/history")).json(), {"messages": []})
                self.assertEqual(self.roster.get_agents(), [])
                self.assertFalse(self.roster.metadata_path.exists())
                self.assertEqual(list(self.logs._base_dir.glob("*.log")), [])
                self.assertEqual(self.memory.load_summary_header().summary_text, "")
                self.assertEqual(self.service.list_triggers(agent_name=OWNER), [])
                self.assertEqual(self.service.list_triggers(agent_name="Alice lunch"), [])
                self.assertEqual(unrelated.read_text(encoding="utf-8"), "preserve")
                with self.assertRaises(ContentExpiredError):
                    ContentStore().read_source_page(source, owner=f"worker:{OWNER}")
                requests_before = len(self.requests)
                await self.manager._dispatch_to_interaction_agent("Late cleared callback", content_generation=generation)
                await drain(tasks)
                self.assertEqual(len(self.requests), requests_before)
                self.assertEqual((await api.get("/api/v1/chat/history")).json(), {"messages": []})
        self.assertEqual(self.manager.get_pending_executions(), [])

    async def test_owned_triggers_poll_once_advance_recurrence_and_deliver_real_callbacks(self):
        now = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
        first_fire = now + timedelta(minutes=1)
        second_fire = first_fire + timedelta(hours=1)
        scheduler = trigger_scheduler.TriggerScheduler()
        fired_owners = []

        def respond(request):
            payload = self.request(request)
            current, last = payload["messages"][1]["content"], payload["messages"][-1]
            if payload["model"] == "release-worker":
                if last["role"] == "tool":
                    return self.final("Reminder scheduled.")
                if "Trigger fired at" in current:
                    name = OWNER if f"Agent Name: {OWNER}" in payload["messages"][0]["content"] else "Alice lunch"
                    fired_owners.append(name)
                    self.assertIn("Payload:", current)
                    return self.final("TRIGGER_RESULT for " + name)
                return self.invoke("createTrigger", {"payload": "Check the contract status and report", "start_time": first_fire.isoformat()})
            if last["role"] == "tool":
                return self.final("Reminder callback delivered.")
            self.assertIn("<new_agent_message>", current)
            return self.invoke("send_message_to_user", {"message": "Reminder callback reached chat."})

        with use_fake_gmail(self.fake), client.use_mock_provider(httpx.MockTransport(respond)), patch.object(trigger_service_module, "utc_now", return_value=now):
            async with self.api() as api, capture_tasks() as tasks:
                result = await workers.ExecutionAgentRuntime(OWNER).execute("Schedule the release reminder")
                self.assertTrue(result.success, result.error)
                one_shot, = self.service.list_triggers(agent_name=OWNER)
                other = self.service.create_trigger(agent_name="Alice lunch", payload="Check lunch status", timezone_name="UTC",
                    start_time=second_fire.isoformat(), recurrence_rule="FREQ=DAILY;COUNT=2")
                other_tools = registry.get_tool_registry("Alice lunch", bounded_context=True)
                self.assertIn("error", other_tools["updateTrigger"](trigger_id=one_shot.id, status="paused"))
                self.assertEqual([row["id"] for row in other_tools["listTriggers"]()["triggers"]], [other.id])
                with patch.object(trigger_scheduler, "_utc_now", return_value=now):
                    await scheduler._poll_once()
                self.assertEqual(fired_owners, [])
                with self.assertLogs("openpoke.server", level="INFO") as captured:
                    with patch.object(trigger_scheduler, "_utc_now", return_value=first_fire + timedelta(seconds=1)):
                        await scheduler._poll_once()
                        await scheduler._poll_once()  # The existing in-flight set prevents duplicate admission.
                        await drain(tasks)
                    self.assertEqual(fired_owners, [OWNER])
                    completed, = self.service.list_triggers(agent_name=OWNER)
                    self.assertEqual(completed.status, "completed")
                    self.assertIsNone(completed.next_trigger)
                    with patch.object(trigger_scheduler, "_utc_now", return_value=second_fire + timedelta(seconds=1)):
                        await scheduler._poll_once()
                        await drain(tasks)
                self.assertEqual(fired_owners, [OWNER, "Alice lunch"])
                recurring, = self.service.list_triggers(agent_name="Alice lunch")
                self.assertEqual(recurring.status, "active")
                self.assertEqual(datetime.fromisoformat(recurring.next_trigger.replace("Z", "+00:00")), second_fire + timedelta(days=1))
                events = [record.telemetry for record in captured.records if hasattr(record, "telemetry")]
                for trigger_id in (one_shot.id, other.id):
                    correlated = [event for event in events if event.get("trigger_id") == trigger_id]
                    self.assertTrue(any(event["event"] == "callback.completed" and event["outcome"] == "succeeded" for event in correlated))
                    self.assertEqual({event["origin"] for event in correlated}, {"trigger"})
                    self.assertEqual(len({event["request_id"] for event in correlated}), 1)
                history = (await api.get("/api/v1/chat/history")).json()["messages"]
                self.assertEqual(sum(row["content"] == "Reminder callback reached chat." for row in history), 2)
        self.assertEqual(scheduler._in_flight, set())
        self.assertEqual(self.manager.get_pending_executions(), [])
        self.assertEqual(self.fake.effects, [])

    async def test_application_lifecycle_starts_and_stops_existing_background_services(self):
        scheduler = trigger_scheduler.TriggerScheduler(poll_interval_seconds=3600)
        watcher = Mock(start=AsyncMock(), stop=AsyncMock())
        with patch("server.app.get_trigger_scheduler", return_value=scheduler), patch("server.app.get_important_email_watcher", return_value=watcher):
            async with app.router.lifespan_context(app):
                self.assertTrue(scheduler._running)
                watcher.start.assert_awaited_once()
                async with self.api() as api:
                    response = await api.get("/api/v1/health")
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.json()["ok"])
        self.assertFalse(scheduler._running)
        self.assertIsNone(scheduler._task)
        watcher.stop.assert_awaited_once()
