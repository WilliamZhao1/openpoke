import asyncio
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

from server.agents.execution_agent import agent as worker_agent
from server.agents.execution_agent import batch_manager, runtime as worker_runtime
from server.agents.execution_agent.tasks.search_email import tool as search_tool
from server.agents.interaction_agent import agent as interaction_agent
from server.agents.interaction_agent import runtime as interaction_runtime, tools
from server.config import Settings
from server.models import ChatMessage, ChatRequest
from server.observability import get_trace_context, record_event, trace_scope
from server.openrouter_client import client
from server.services.conversation import chat_handler, log as conversation_log
from server.services.conversation.summarization import summarizer
from server.services.conversation.summarization.prompt_builder import SummaryPrompt
from server.services.conversation.summarization.working_memory_log import WorkingMemoryLog
from server.services.execution import AgentRoster, ExecutionAgentLogStore
from server.services.gmail import importance_classifier, importance_watcher
from server.services.gmail.processing import ProcessedEmail
from server.services.gmail.seen_store import GmailSeenStore
from server.services import trigger_scheduler
from server.services.triggers import TriggerRecord


def telemetry(captured):
    return [record.telemetry for record in captured.records if hasattr(record, "telemetry")]


class TraceContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_requests_keep_independent_ids_and_restore_context(self):
        ready = asyncio.Event()
        traces = []

        async def run():
            with trace_scope(origin="chat", new_request=True) as root:
                traces.append(root)
                if len(traces) == 2:
                    ready.set()
                await ready.wait()
                with trace_scope(run_id="local-run"):
                    await asyncio.sleep(0)
                    self.assertEqual(get_trace_context().request_id, root.request_id)
                self.assertEqual(get_trace_context(), root)
            self.assertIsNone(get_trace_context())

        await asyncio.wait_for(asyncio.gather(run(), run()), timeout=2)
        self.assertNotEqual(traces[0].request_id, traces[1].request_id)
        self.assertNotEqual(traces[0].turn_id, traces[1].turn_id)

    async def test_child_turn_and_exception_restore_the_parent_and_filter_content_fields(self):
        with trace_scope(origin="chat", new_request=True) as root:
            with self.assertRaises(RuntimeError):
                with trace_scope(new_turn=True) as callback:
                    self.assertEqual(callback.request_id, root.request_id)
                    self.assertEqual(callback.parent_turn_id, root.turn_id)
                    self.assertNotEqual(callback.turn_id, root.turn_id)
                    raise RuntimeError("test")
            self.assertEqual(get_trace_context(), root)
            with self.assertLogs("openpoke.server", level="INFO") as captured:
                record_event("test", component="test", outcome="succeeded", prompt="private prompt", api_key="private key")
        metric, = telemetry(captured)
        self.assertNotIn("private", json.dumps(metric))
        self.assertIsNone(get_trace_context())


class AgentTraceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.root = root
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.settings = Settings(
            openrouter_api_key="test-key", openrouter_max_tokens=777,
            interaction_agent_model="interaction-test", execution_agent_model="execution-test",
            email_classifier_model="classifier-test", conversation_summary_threshold=0,
        )
        self.memory = WorkingMemoryLog(root / "memory.log")
        self.stack.enter_context(patch.object(conversation_log, "_resolve_working_memory_log", return_value=self.memory))
        self.log = conversation_log.ConversationLog(root / "conversation.log")
        self.roster = AgentRoster(root / "roster.json")
        self.logs = ExecutionAgentLogStore(root / "workers")
        for module in (interaction_runtime, worker_runtime, client, conversation_log, importance_classifier):
            self.stack.enter_context(patch.object(module, "get_settings", return_value=self.settings))
        for module in (interaction_runtime, tools, chat_handler):
            self.stack.enter_context(patch.object(module, "get_conversation_log", return_value=self.log))
        self.stack.enter_context(patch.object(interaction_runtime, "get_working_memory_log", return_value=self.memory))
        for module in (interaction_agent, tools):
            self.stack.enter_context(patch.object(module, "get_agent_roster", return_value=self.roster))
        for module in (worker_agent, tools):
            self.stack.enter_context(patch.object(module, "get_execution_agent_logs", return_value=self.logs))
        self.stack.enter_context(patch.object(search_tool, "_LOG_STORE", self.logs))
        self.manager = batch_manager.ExecutionBatchManager()
        self.stack.enter_context(patch.object(tools, "_EXECUTION_BATCH_MANAGER", self.manager))
        self.fake_tool = AsyncMock(return_value={"body": "private tool content"})
        self.stack.enter_context(patch.object(worker_runtime, "get_tool_registry", return_value={"test_lookup": self.fake_tool}))
        self.stack.enter_context(patch.object(worker_runtime, "get_tool_schemas", return_value=[{
            "type": "function", "function": {"name": "test_lookup", "parameters": {"type": "object"}},
        }]))
        self.payloads = []
        self.stack.enter_context(client.use_mock_provider(httpx.MockTransport(self.provider)))

    def provider(self, request):
        payload = json.loads(request.content)
        self.payloads.append(payload)
        last = payload["messages"][-1]
        model = payload["model"]
        if model == "interaction-test":
            if "<new_agent_message>" in last.get("content", ""):
                message = {"content": "Finished."}
            elif last["role"] == "tool":
                message = {"content": "Started."}
            else:
                message = self.tool_call("send_message_to_agent", {"agent_name": "private worker", "instructions": "private instructions"})
        elif model == "execution-test":
            message = {"content": "private execution response"} if last["role"] == "tool" else self.tool_call("test_lookup", {})
        elif model == "classifier-test":
            message = self.tool_call("mark_email_importance", {"important": True, "summary": "private email summary"})
        else:
            message = {"content": "Summary."}
        return httpx.Response(200, json={
            "choices": [{"message": message}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 5},
        })

    def tool_call(self, name, arguments):
        return {"content": "", "tool_calls": [{
            "id": "call-test", "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)},
        }]}

    @contextmanager
    def track_tasks(self):
        loop = asyncio.get_running_loop()
        create_task = loop.create_task
        tasks = []

        def capture(coroutine, *args, **kwargs):
            task = create_task(coroutine, *args, **kwargs)
            tasks.append(task)
            return task

        with patch.object(loop, "create_task", side_effect=capture):
            yield tasks

    async def drain(self, tasks):
        index = 0
        for _ in range(20):
            batch = tasks[index:]
            index = len(tasks)
            if not batch:
                return
            await asyncio.wait_for(asyncio.gather(*batch), timeout=3)
        self.fail("Background tasks did not drain")

    async def test_chat_trace_reaches_worker_tool_callback_and_user_reply(self):
        with self.assertLogs("openpoke.server", level="INFO") as captured, self.track_tasks() as tasks:
            response = await chat_handler.handle_chat_request(ChatRequest(messages=[
                ChatMessage(role="user", content="private user request"),
            ]))
            self.assertEqual(response.status_code, 202)
            await self.drain(tasks)
        events = telemetry(captured)
        accepted, = [event for event in events if event["event"] == "chat.accepted"]
        dispatched, = [event for event in events if event["event"] == "execution.dispatched"]
        tool, = [event for event in events if event["event"] == "tool.completed" and event["component"] == "execution"]
        callback, = [event for event in events if event["event"] == "callback.received"]
        reply, = [event for event in events if event["event"] == "reply.recorded" and event["turn_id"] == callback["turn_id"]]
        self.assertEqual({event["request_id"] for event in events}, {accepted["request_id"]})
        self.assertEqual(tool["run_id"], dispatched["run_id"])
        self.assertEqual(callback["batch_id"], dispatched["batch_id"])
        self.assertIsNone(callback["run_id"])
        self.assertEqual(callback["parent_turn_id"], accepted["turn_id"])
        self.assertNotEqual(callback["turn_id"], accepted["turn_id"])
        self.assertEqual(reply["outcome"], "succeeded")
        self.assertEqual(self.log.to_chat_messages()[-1].content, "Finished.")
        self.fake_tool.assert_awaited_once()
        model_events = [event for event in events if event["event"] == "model_call.completed"]
        self.assertEqual(len(model_events), 5)
        self.assertEqual({event["component"] for event in model_events}, {"interaction", "execution"})
        self.assertEqual({event["provider_mode"] for event in model_events}, {"mock"})
        self.assertTrue(all(event["observations"]["input_tokens"]["source_mode"] == "mock" for event in model_events))
        self.assertTrue(all(payload["max_tokens"] == 777 for payload in self.payloads))
        self.assertTrue(all("request_id" not in payload and "component" not in payload for payload in self.payloads))
        self.assertNotIn("private", json.dumps(events))
        self.assertIsNone(get_trace_context())

    async def test_trigger_trace_survives_worker_and_async_callback(self):
        service = Mock()
        with patch.object(trigger_scheduler, "get_trigger_service", return_value=service):
            scheduler = trigger_scheduler.TriggerScheduler()
        trigger = TriggerRecord(
            id=42, agent_name="private worker", payload="private reminder", status="active",
            created_at="2026-11-08T10:00:00Z", updated_at="2026-11-08T10:00:00Z",
        )
        with self.assertLogs("openpoke.server", level="INFO") as captured, self.track_tasks() as tasks:
            await scheduler._execute_trigger(trigger)
            await self.drain(tasks)
        events = telemetry(captured)
        self.assertEqual({event["origin"] for event in events}, {"trigger"})
        self.assertEqual({event["trigger_id"] for event in events}, {42})
        self.assertEqual(len({event["request_id"] for event in events}), 1)
        self.assertIn("reply.recorded", {event["event"] for event in events})
        service.schedule_next_occurrence.assert_called_once()
        self.assertNotIn("private", json.dumps(events))

    async def test_gmail_poll_links_classification_to_notification(self):
        now = datetime(2026, 11, 8, 10, tzinfo=timezone.utc)
        email = ProcessedEmail(
            id="private-message", thread_id="private-thread", query="private query",
            subject="private subject", sender="private sender", recipient="private recipient",
            timestamp=now, label_ids=[], clean_text="private email body",
            has_attachments=False, attachment_count=0, attachment_filenames=[],
        )
        watcher = importance_watcher.ImportantEmailWatcher(seen_store=GmailSeenStore(self.root / "seen.json"))
        watcher._has_seeded_initial_snapshot = True
        with (
            patch.object(importance_watcher, "datetime", wraps=datetime) as clock,
            patch.object(importance_watcher, "convert_to_user_timezone", side_effect=lambda value: value),
            patch.object(importance_watcher, "get_active_gmail_user_id", return_value="test-account"),
            patch.object(importance_watcher, "execute_gmail_tool", return_value={}),
            patch.object(importance_watcher, "parse_gmail_fetch_response", return_value=([email], None)),
            self.assertLogs("openpoke.server", level="INFO") as captured,
        ):
            clock.now.return_value = now
            await watcher._poll_once()
        events = telemetry(captured)
        self.assertEqual({event["origin"] for event in events}, {"gmail"})
        self.assertEqual(len({event["request_id"] for event in events}), 1)
        self.assertEqual({event["component"] for event in events if event["event"] == "model_call.completed"}, {"email_classifier", "interaction"})
        self.assertEqual(watcher._seen_store.snapshot(), ["private-message"])
        self.assertIn("reply.recorded", {event["event"] for event in events})
        self.assertNotIn("private", json.dumps(events))

    async def test_search_and_summary_calls_label_their_component_and_keep_the_parent(self):
        with trace_scope(origin="chat", new_request=True) as root:
            with self.assertLogs("openpoke.server", level="INFO") as captured:
                result = await search_tool._run_email_search(
                    search_query="private query", composio_user_id="test-account", model="search-test", api_key="test-key",
                )
                summary = await summarizer._call_openrouter(
                    SummaryPrompt("private system", [{"role": "user", "content": "private history"}]),
                    "summary-test", "test-key",
                )
        self.assertEqual(result, [])
        self.assertEqual(summary, "Summary.")
        events = telemetry(captured)
        self.assertEqual({event["component"] for event in events}, {"search_email", "summarizer"})
        self.assertEqual({event["request_id"] for event in events}, {root.request_id})
        self.assertNotIn("private", json.dumps(events))

    async def test_mixed_request_batch_links_every_parent_without_changing_the_callback(self):
        ready = asyncio.Event()
        roots = []
        callback_contexts = []

        async def execute(instructions):
            roots.append(get_trace_context())
            if len(roots) == 2:
                ready.set()
            await ready.wait()
            return worker_runtime.ExecutionResult(agent_name=instructions, success=True, response="done")

        async def dispatch(payload):
            callback_contexts.append(get_trace_context())
            self.assertIn("first: done", payload)
            self.assertIn("second: done", payload)

        async def run(name):
            with trace_scope(origin="chat", new_request=True):
                return await self.manager.execute_agent(name, name)

        with (
            patch.object(batch_manager, "ExecutionAgentRuntime", return_value=Mock(execute=execute)),
            patch.object(self.manager, "_dispatch_to_interaction_agent", side_effect=dispatch) as callback,
            self.assertLogs("openpoke.server", level="INFO") as captured,
        ):
            results = await asyncio.wait_for(asyncio.gather(run("first"), run("second")), timeout=3)
        self.assertTrue(all(result.success for result in results))
        callback.assert_awaited_once()
        dispatched, = [event for event in telemetry(captured) if event["event"] == "callback.dispatched"]
        self.assertEqual({parent["request_id"] for parent in dispatched["parents"]}, {root.request_id for root in roots})
        context, = callback_contexts
        self.assertEqual(context.origin, "batch")
        self.assertNotIn(context.request_id, {root.request_id for root in roots})
        self.assertIsNone(context.run_id)
        self.assertIsNone(get_trace_context())

    async def test_execution_timeout_is_measured_without_changing_the_result(self):
        manager = batch_manager.ExecutionBatchManager(timeout_seconds=0)
        with (
            patch.object(batch_manager, "ExecutionAgentRuntime", return_value=Mock(execute=AsyncMock())),
            patch.object(manager, "_dispatch_to_interaction_agent", new=AsyncMock()),
            self.assertLogs("openpoke.server", level="INFO") as captured,
        ):
            result = await manager.execute_agent("worker", "instructions")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Timeout")
        finished, = [event for event in telemetry(captured) if event["event"] == "execution.completed"]
        self.assertEqual(finished["failure_category"], "timeout")
        self.assertIsNone(get_trace_context())

    async def test_execution_cancellation_is_measured_and_propagates(self):
        entered = asyncio.Event()

        async def execute(instructions):
            entered.set()
            await asyncio.Event().wait()

        with (
            patch.object(batch_manager, "ExecutionAgentRuntime", return_value=Mock(execute=execute)),
            patch.object(self.manager, "_dispatch_to_interaction_agent", new=AsyncMock()) as callback,
            self.assertLogs("openpoke.server", level="INFO") as captured,
        ):
            task = asyncio.create_task(self.manager.execute_agent("worker", "instructions"))
            await asyncio.wait_for(entered.wait(), timeout=2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        callback.assert_not_awaited()
        finished, = [event for event in telemetry(captured) if event["event"] == "execution.completed"]
        self.assertEqual(finished["failure_category"], "cancelled")
        self.assertEqual(self.manager.get_pending_executions(), [])
        self.assertIsNone(get_trace_context())

    async def test_trigger_state_update_failure_records_one_failed_completion(self):
        service = Mock()
        service.schedule_next_occurrence.side_effect = RuntimeError("private storage error")
        with patch.object(trigger_scheduler, "get_trigger_service", return_value=service):
            scheduler = trigger_scheduler.TriggerScheduler()
        trigger = TriggerRecord(
            id=43, agent_name="private worker", payload="private reminder", status="active",
            created_at="2026-11-08T10:00:00Z", updated_at="2026-11-08T10:00:00Z",
        )
        with self.assertLogs("openpoke.server", level="INFO") as captured, self.track_tasks() as tasks:
            await scheduler._execute_trigger(trigger)
            await self.drain(tasks)
        events = telemetry(captured)
        completed, = [event for event in events if event["event"] == "trigger.completed"]
        self.assertEqual(completed["outcome"], "failed")
        self.assertEqual(completed["failure_category"], "trigger_error")
        service.record_failure.assert_called_once()
        self.assertNotIn("private", json.dumps(events))
