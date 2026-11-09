from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx

from server.config import Settings
from server.context_budget import ContextBudgetError, ContextBudgetExceeded, prepare_budgeted_request
from server.openrouter_client import client
from server.agents.interaction_agent.runtime import InteractionAgentRuntime
from server.agents.execution_agent.runtime import ExecutionAgentRuntime
from server.agents.execution_agent.tasks.search_email import tool as search_tool
from server.services.conversation.summarization import summarizer
from server.services.conversation.summarization.prompt_builder import SummaryPrompt
from server.services.gmail import importance_classifier
from server.services.gmail.processing import ProcessedEmail


MODEL = "budget-test-model"
MODEL_FIELDS = ("interaction_agent_model", "execution_agent_model", "execution_agent_search_model",
                "summarizer_model", "email_classifier_model")


def settings(**changes):
    return Settings(**{**dict.fromkeys(MODEL_FIELDS, MODEL), "context_strategy": "bounded",
                       "model_context_windows": {MODEL: 20000}, "context_input_tokens": 10000,
                       "context_headroom_tokens": 64, "openrouter_max_tokens": 32,
                       "openrouter_api_key": "test-key", **changes})


def request(**changes):
    return {"model": MODEL, "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 32, "stream": False, **changes}


def prepare(payload, **changes):
    return prepare_budgeted_request(payload, **{"context_window": 20000, "input_cap": 10000, "headroom": 64, **changes})


def events(captured):
    return [record.telemetry for record in captured.records if hasattr(record, "telemetry")]


class ContextBudgetTests(unittest.TestCase):
    def test_all_input_sections_are_counted_and_preserved(self):
        payload = request(messages=[
            {"role": "system", "content": "instructions"},
            {"role": "user", "content": "earlier history"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "call-1", "type": "function",
                "function": {"name": "lookup", "arguments": '{"query":"history"}'}}]},
            {"role": "tool", "tool_call_id": "call-1", "content": "exact result"},
            {"role": "user", "content": "current message"},
        ], tools=[{"type": "function", "function": {"name": "lookup", "description": "tool instructions",
                  "parameters": {"type": "object"}}}])
        before = deepcopy(payload)
        body, estimate = prepare(payload)
        self.assertEqual(json.loads(body), before)
        self.assertEqual(payload, before)
        self.assertEqual(estimate.request_bytes, len(body))
        self.assertGreater(estimate.estimated_input_tokens, len(body))
        self.assertEqual(estimate.method, "utf8_json_bytes_estimate")
        for index in range(len(payload["messages"])):
            changed = deepcopy(payload)
            changed["messages"][index]["content"] = (changed["messages"][index]["content"] or "") + "x" * 100
            self.assertGreater(prepare(changed)[1].estimated_input_tokens, estimate.estimated_input_tokens)
        changed = deepcopy(payload)
        changed["tools"][0]["function"]["description"] += "x" * 100
        self.assertGreater(prepare(changed)[1].estimated_input_tokens, estimate.estimated_input_tokens)

    def test_exact_estimated_boundary_passes_and_one_over_is_rejected(self):
        payload = request()
        _, estimate = prepare(payload)
        body, accepted = prepare(payload, input_cap=estimate.estimated_input_tokens)
        self.assertEqual(accepted.input_limit, estimate.estimated_input_tokens)
        self.assertEqual(json.loads(body), payload)
        with self.assertRaises(ContextBudgetExceeded) as raised:
            prepare(payload, input_cap=estimate.estimated_input_tokens - 1)
        self.assertEqual(raised.exception.estimate.input_limit, estimate.estimated_input_tokens - 1)

    def test_output_and_headroom_reduce_the_effective_input_allowance(self):
        payload = request()
        _, estimate = prepare(payload)
        window = estimate.estimated_input_tokens + payload["max_tokens"] + 64
        self.assertEqual(prepare(payload, context_window=window)[1].input_limit, estimate.estimated_input_tokens)
        with self.assertRaises(ContextBudgetExceeded):
            prepare(payload, context_window=window - 1)
        with self.assertRaises(ContextBudgetExceeded):
            prepare({**payload, "max_tokens": 33}, context_window=window)
        with self.assertRaises(ContextBudgetExceeded):
            prepare(payload, context_window=window, headroom=65)

    def test_multilingual_unicode_uses_utf8_bytes_and_remains_an_estimate(self):
        ascii_body, ascii_estimate = prepare(request(messages=[{"role": "user", "content": "a" * 20}]))
        unicode_body, unicode_estimate = prepare(request(messages=[{"role": "user", "content": "旅" * 20}]))
        self.assertEqual(len(unicode_body) - len(ascii_body), 40)
        self.assertEqual(unicode_estimate.estimated_input_tokens - ascii_estimate.estimated_input_tokens, 40)
        self.assertEqual(json.loads(unicode_body)["messages"][0]["content"], "旅" * 20)
        self.assertIn("estimate", unicode_estimate.method)

    def test_invalid_allowances_and_unsupported_media_fail_explicitly(self):
        for change in ({"context_window": None}, {"context_window": True}, {"input_cap": 0},
                       {"headroom": -1}, {"context_window": 96}):
            with self.subTest(change=change), self.assertRaises(ContextBudgetError):
                prepare(request(), **change)
        for payload in (request(messages="invalid"), request(tools={"invalid": "shape"}),
                        request(messages=[{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "private-url"}}]}]),
                        request(messages=[{"role": "user", "content": "\ud800"}])):
            with self.assertRaises(ContextBudgetError) as raised:
                prepare(payload)
            self.assertNotIn("private-url", str(raised.exception))

    def test_configuration_requires_explicit_allowances_for_every_selected_model(self):
        with self.assertRaisesRegex(ValueError, "every configured model"):
            settings(model_context_windows={})
        with self.assertRaisesRegex(ValueError, "every configured model"):
            settings(email_classifier_model="another-model")
        configured = settings(email_classifier_model="another-model", model_context_windows={MODEL: 20000, "another-model": 1000})
        self.assertEqual(configured.model_context_windows["another-model"], 1000)
        self.assertEqual(Settings(context_strategy="legacy").model_context_windows, {})

    def test_configuration_rejects_invalid_flags_values_and_reservations(self):
        for change in ({"context_strategy": "unknown"}, {"context_input_tokens": 0}, {"context_input_tokens": True},
                       {"context_headroom_tokens": -1}, {"model_context_windows": {MODEL: True}},
                       {"model_context_windows": {MODEL: 0}}, {"model_context_windows": {"": 10000}},
                       {"model_context_windows": {MODEL: 96}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                settings(**change)

    def test_invalid_environment_values_are_not_silently_replaced_with_defaults(self):
        for variable, value in (("OPENPOKE_MODEL_CONTEXT_WINDOWS", "not json"),
                                ("OPENPOKE_CONTEXT_INPUT_TOKENS", "not a number"),
                                ("OPENPOKE_CONTEXT_HEADROOM_TOKENS", "-1")):
            with patch.dict(os.environ, {variable: value}), self.assertRaises(ValueError):
                Settings()


class ContextBudgetProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_fitting_request_preserves_content_tools_output_and_actual_usage(self):
        messages = [{"role": "user", "content": "exact user message"},
                    {"role": "assistant", "content": None, "tool_calls": [{"id": "call-1", "type": "function",
                     "function": {"name": "lookup", "arguments": "{}"}}]},
                    {"role": "tool", "tool_call_id": "call-1", "content": "exact draft body"}]
        schemas = [{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object"}}}]
        captured_payloads = []
        def handle(http_request):
            captured_payloads.append(json.loads(http_request.content))
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}],
                                             "usage": {"prompt_tokens": 7, "completion_tokens": 0}})
        with (patch.object(client, "get_settings", return_value=settings()),
              client.use_mock_provider(httpx.MockTransport(handle)),
              self.assertLogs("openpoke.server", level="INFO") as captured):
            await client.request_chat_completion(model=MODEL, messages=messages, system="system instructions", tools=schemas)
        self.assertEqual(captured_payloads, [request(messages=[{"role": "system", "content": "system instructions"}, *messages], tools=schemas)])
        self.assertEqual(events(captured)[0]["input_tokens"], 7)
        self.assertEqual(events(captured)[0]["output_tokens"], 0)
        self.assertEqual(messages[-1]["content"], "exact draft body")

    async def test_oversized_request_does_not_open_http_or_expose_private_content(self):
        with (patch.object(client, "get_settings", return_value=settings(context_input_tokens=500)),
              patch.object(client.httpx, "AsyncClient") as http_client,
              self.assertLogs("openpoke.server", level="INFO") as captured):
            with self.assertRaises(ContextBudgetExceeded) as raised:
                await client.request_chat_completion(model=MODEL, messages=[{"role": "user", "content": "private-body" * 1000}])
        http_client.assert_not_called()
        metric, = events(captured)
        self.assertEqual(metric["failure_category"], "context_budget")
        self.assertEqual(metric["observations"]["input_tokens"]["availability"], "not_applicable")
        self.assertEqual(metric["observations"]["input_tokens"]["reason"], "request_not_sent")
        self.assertEqual(metric["observations"]["status_code"]["availability"], "not_applicable")
        self.assertIsNone(metric["input_tokens"])
        self.assertNotIn("private-body", json.dumps(metric) + str(raised.exception))
        self.assertIn("estimate", str(raised.exception))

    async def test_unknown_model_and_unsupported_media_cannot_bypass_preflight(self):
        with (patch.object(client, "get_settings", return_value=settings()),
              patch.object(client.httpx, "AsyncClient") as http_client):
            with self.assertRaisesRegex(ContextBudgetError, "No configured context allowance"):
                await client.request_chat_completion(model="unconfigured-model", messages=[])
            with self.assertRaisesRegex(ContextBudgetError, "structured media"):
                await client.request_chat_completion(model=MODEL, messages=[{"role": "user", "content": [{"type": "image_url"}]}])
        http_client.assert_not_called()

    async def test_wire_snapshot_cannot_grow_while_http_client_opens(self):
        messages = [{"role": "user", "content": "small"}]
        captured = []
        transport = httpx.MockTransport(lambda req: (captured.append(json.loads(req.content)) or
                                       httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})))
        original = httpx.AsyncClient
        class MutatingClient:
            def __init__(self, **kwargs):
                self.client = original(**kwargs)
            async def __aenter__(self):
                messages[0]["content"] = "x" * 100000
                return await self.client.__aenter__()
            async def __aexit__(self, *args):
                return await self.client.__aexit__(*args)
        with (patch.object(client, "get_settings", return_value=settings(context_input_tokens=500)),
              patch.object(client.httpx, "AsyncClient", MutatingClient), client.use_mock_provider(transport)):
            await client.request_chat_completion(model=MODEL, messages=messages)
        self.assertEqual(captured[0]["messages"][0]["content"], "small")

    async def test_missing_provider_usage_stays_unknown_despite_local_estimate(self):
        with (patch.object(client, "get_settings", return_value=settings()),
              client.use_mock_provider(httpx.MockTransport(lambda req: httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}))),
              self.assertLogs("openpoke.server", level="INFO") as captured):
            await client.request_chat_completion(model=MODEL, messages=[{"role": "user", "content": "small"}])
        metric, = events(captured)
        self.assertIsNone(metric["input_tokens"])
        self.assertEqual(metric["observations"]["input_tokens"]["availability"], "unavailable")

    async def test_growing_tool_results_are_rechecked_on_every_call(self):
        calls = []
        transport = httpx.MockTransport(lambda req: (calls.append(req) or httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})))
        messages = [{"role": "user", "content": "small"}]
        with patch.object(client, "get_settings", return_value=settings(context_input_tokens=500)), client.use_mock_provider(transport):
            await client.request_chat_completion(model=MODEL, messages=messages)
            messages.append({"role": "tool", "tool_call_id": "lookup", "content": "x" * 2000})
            with self.assertRaises(ContextBudgetExceeded):
                await client.request_chat_completion(model=MODEL, messages=messages)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(messages[-1]["content"]), 2000)

    async def test_summarizer_does_not_retry_a_deterministic_budget_error(self):
        with (patch.object(client, "get_settings", return_value=settings(context_input_tokens=500)),
              patch.object(client, "prepare_budgeted_request", wraps=prepare_budgeted_request) as preflight,
              patch.object(client.httpx, "AsyncClient") as http_client):
            with self.assertRaises(ContextBudgetExceeded):
                await summarizer._call_openrouter(SummaryPrompt("system", [{"role": "user", "content": "x" * 2000}]), MODEL, "test-key")
        self.assertEqual(preflight.call_count, 1)
        http_client.assert_not_called()

    async def test_all_five_real_model_callers_reach_the_shared_guard(self):
        interaction = InteractionAgentRuntime.__new__(InteractionAgentRuntime)
        interaction.model, interaction.api_key, interaction.tool_schemas = MODEL, "test-key", []
        interaction.bounded_context = True
        worker = ExecutionAgentRuntime.__new__(ExecutionAgentRuntime)
        worker.model, worker.api_key, worker.tool_schemas = MODEL, "test-key", []
        worker.bounded_context = True
        worker.agent = SimpleNamespace(name="exact worker")
        messages = [{"role": "user", "content": "x" * 10000}]
        email = ProcessedEmail(id="email", thread_id="thread", query="query", subject="subject", sender="sender", recipient="recipient",
                               timestamp=datetime(2026, 11, 8, tzinfo=timezone.utc), label_ids=[], clean_text="x" * 10000,
                               has_attachments=False, attachment_count=0, attachment_filenames=[])
        configured = settings(context_input_tokens=500)
        with (patch.object(client, "get_settings", return_value=configured),
              patch.object(importance_classifier, "get_settings", return_value=configured),
              patch.object(client.httpx, "AsyncClient") as http_client,
              self.assertLogs("openpoke.server", level="INFO") as captured):
            for call in (lambda: interaction._make_llm_call("system", messages),
                         lambda: worker._make_llm_call("system", messages, with_tools=True),
                         lambda: search_tool._run_email_search(search_query="x" * 10000, composio_user_id="test-account", model=MODEL, api_key="test-key"),
                         lambda: summarizer._call_openrouter(SummaryPrompt("system", messages), MODEL, "test-key")):
                with self.assertRaises(ContextBudgetExceeded):
                    await call()
            self.assertIsNone(await importance_classifier.classify_email_importance(email))
        http_client.assert_not_called()
        rejected = [event for event in events(captured) if event["event"] == "model_call.completed"]
        self.assertEqual(len(rejected), 5)
        self.assertEqual({event["component"] for event in rejected}, {"interaction", "execution", "search_email", "summarizer", "email_classifier"})
        self.assertTrue(all(event["failure_category"] == "context_budget" for event in rejected))
        self.assertTrue(any(record.getMessage().startswith("Importance classification failed") for record in captured.records))
