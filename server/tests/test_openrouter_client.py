import asyncio
from contextlib import contextmanager
import json
import io
import unittest
from unittest.mock import patch

import httpx

from server.config import Settings
from server.openrouter_client import client
from server import observability
from server.observability import get_trace_context, trace_scope


class OpenRouterClientTests(unittest.IsolatedAsyncioTestCase):
    @contextmanager
    def transport(self, handle, *, settings=None):
        async_client = httpx.AsyncClient
        with (
            patch.object(client, "get_settings", return_value=settings or Settings(openrouter_api_key="test-key", openrouter_max_tokens=2048)),
            patch.object(client.httpx, "AsyncClient", side_effect=lambda: async_client(
                transport=httpx.MockTransport(handle)
            )),
        ):
            yield

    def metrics(self, captured):
        return [record.telemetry for record in captured.records if hasattr(record, "telemetry")]

    async def test_usage_and_timing_preserve_payload_and_exclude_content(self):
        provider_payload = {
            "choices": [{"message": {"content": "private response"}}],
            "usage": {"prompt_tokens": 123, "completion_tokens": 7, "private": "provider secret"},
        }
        requests = []

        def handle(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json=provider_payload)

        with (
            self.transport(handle),
            self.assertLogs("openpoke.server", level="INFO") as captured,
            patch.object(client, "perf_counter", side_effect=[10.0, 10.125]),
            trace_scope(origin="chat", new_request=True) as trace,
        ):
            result = await client.request_chat_completion(
                model="test-model", component="execution", api_key="private credential",
                messages=[{"role": "user", "content": "private prompt"}],
                system="private system prompt",
            )
        self.assertEqual(result, provider_payload)
        self.assertEqual(set(requests[0]), {"model", "messages", "stream", "max_tokens"})
        self.assertEqual(requests[0]["max_tokens"], 2048)
        metric, = self.metrics(captured)
        self.assertEqual(metric["input_tokens"], 123)
        self.assertEqual(metric["output_tokens"], 7)
        self.assertTrue(metric["usage_complete"])
        self.assertEqual(metric["elapsed_ms"], 125)
        self.assertEqual(metric["component"], "execution")
        self.assertEqual(metric["model"], "test-model")
        self.assertEqual(metric["request_id"], trace.request_id)
        self.assertEqual(metric["outcome"], "succeeded")
        self.assertNotIn("private", json.dumps(metric))
        self.assertNotIn("provider secret", json.dumps(metric))
        self.assertIsNone(get_trace_context())

    async def test_missing_and_invalid_usage_are_unknown_and_zero_is_preserved(self):
        cases = [
            (None, None, None),
            ({}, None, None),
            ({"prompt_tokens": 0, "completion_tokens": 0}, 0, 0),
            ({"prompt_tokens": 8}, 8, None),
            ({"prompt_tokens": -1, "completion_tokens": True}, None, None),
            ({"prompt_tokens": "12", "completion_tokens": 2.5}, None, None),
        ]
        for usage, expected_input, expected_output in cases:
            with self.subTest(usage=usage):
                with (
                    self.transport(lambda request: httpx.Response(200, json={
                        "choices": [{"message": {"content": "OK"}}], "usage": usage,
                    })),
                    self.assertLogs("openpoke.server", level="INFO") as captured,
                ):
                    await client.request_chat_completion(model="test", messages=[])
                metric, = self.metrics(captured)
                self.assertEqual(metric["input_tokens"], expected_input)
                self.assertEqual(metric["output_tokens"], expected_output)
                self.assertEqual(metric["usage_complete"], expected_input is not None and expected_output is not None)

    async def test_http_failures_have_safe_categories(self):
        for status, category in [(401, "authentication"), (429, "rate_limit"), (503, "provider_server"), (400, "provider_request")]:
            with self.subTest(status=status):
                with (
                    self.transport(lambda request: httpx.Response(status, json={"error": "private provider detail"})),
                    self.assertLogs("openpoke.server", level="INFO") as captured,
                ):
                    with self.assertRaises(client.OpenRouterError):
                        await client.request_chat_completion(model="test", messages=[])
                metric, = self.metrics(captured)
                self.assertEqual(metric["failure_category"], category)
                self.assertEqual(metric["status_code"], status)
                self.assertEqual(metric["outcome"], "failed")
                self.assertIsNone(metric["input_tokens"])
                self.assertNotIn("private provider detail", json.dumps(metric))

    async def test_transport_and_decoding_failures_are_measured(self):
        for exception, category in [(httpx.ReadTimeout("private timeout"), "timeout"), (httpx.ConnectError("private connection"), "network")]:
            with self.subTest(category=category):
                def handle(request):
                    raise exception

                with self.transport(handle), self.assertLogs("openpoke.server", level="INFO") as captured:
                    with self.assertRaises(client.OpenRouterError):
                        await client.request_chat_completion(model="test", messages=[])
                metric, = self.metrics(captured)
                self.assertEqual(metric["failure_category"], category)
                self.assertNotIn("private", json.dumps(metric))

        with (
            self.transport(lambda request: httpx.Response(200, text="private invalid json")),
            self.assertLogs("openpoke.server", level="INFO") as captured,
        ):
            with self.assertRaises(json.JSONDecodeError):
                await client.request_chat_completion(model="test", messages=[])
        metric, = self.metrics(captured)
        self.assertEqual(metric["failure_category"], "invalid_response")

    async def test_missing_key_is_measured_without_http_request(self):
        def handle(request):
            self.fail("A missing key must not reach the provider")

        with (
            self.transport(handle, settings=Settings(openrouter_api_key=None)),
            self.assertLogs("openpoke.server", level="INFO") as captured,
        ):
            with self.assertRaisesRegex(client.OpenRouterError, "Missing OpenRouter API key"):
                await client.request_chat_completion(model="test", messages=[])
        metric, = self.metrics(captured)
        self.assertEqual(metric["failure_category"], "configuration")

    async def test_error_envelope_is_measured_and_returned_unchanged(self):
        payload = {"error": {"message": "private provider detail"}}
        with (
            self.transport(lambda request: httpx.Response(200, json=payload)),
            self.assertLogs("openpoke.server", level="INFO") as captured,
        ):
            result = await client.request_chat_completion(model="test", messages=[])
        self.assertEqual(result, payload)
        metric, = self.metrics(captured)
        self.assertEqual(metric["failure_category"], "provider_error")
        self.assertNotIn("private provider detail", json.dumps(metric))

    async def test_cancellation_is_measured_once_and_propagates(self):
        entered = asyncio.Event()

        async def handle(request):
            entered.set()
            await asyncio.Event().wait()

        with self.transport(handle), self.assertLogs("openpoke.server", level="INFO") as captured:
            task = asyncio.create_task(client.request_chat_completion(model="test", messages=[]))
            await asyncio.wait_for(entered.wait(), timeout=2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        metric, = self.metrics(captured)
        self.assertEqual(metric["failure_category"], "cancelled")
        self.assertEqual(metric["outcome"], "failed")
        self.assertIsNone(get_trace_context())

    async def test_log_sink_failure_does_not_change_success_or_mask_provider_errors(self):
        for status in (200, 503):
            with self.subTest(status=status):
                with (
                    self.transport(lambda request: httpx.Response(status, json={"choices": [{"message": {"content": "OK"}}]})),
                    patch.object(observability.logger, "info", side_effect=RuntimeError("broken sink")),
                    patch.object(observability.sys, "stderr", new_callable=io.StringIO) as fallback,
                ):
                    if status == 200:
                        result = await client.request_chat_completion(model="test", messages=[])
                        self.assertEqual(result["choices"][0]["message"]["content"], "OK")
                    else:
                        with self.assertRaisesRegex(client.OpenRouterError, "OpenRouter request failed \\(503\\)"):
                            await client.request_chat_completion(model="test", messages=[])
                self.assertEqual(fallback.getvalue(), "OpenPoke telemetry emission failed\n")

    async def test_request_includes_configured_output_limit(self):
        settings = Settings(openrouter_api_key="test-key", openrouter_max_tokens=1234)
        payloads = []

        def handle(request):
            payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

        async_client = httpx.AsyncClient
        with (
            patch.object(client, "get_settings", return_value=settings),
            patch.object(client.httpx, "AsyncClient", side_effect=lambda: async_client(
                transport=httpx.MockTransport(handle)
            )),
        ):
            result = await client.request_chat_completion(
                model="test-model", messages=[{"role": "user", "content": "Hello"}]
            )
        self.assertEqual(payloads[0]["max_tokens"], 1234)
        self.assertEqual(result["choices"][0]["message"]["content"], "OK")

    def test_provider_error_keeps_message_without_metadata_dump(self):
        request = httpx.Request("POST", "https://example.test/chat/completions")
        response = httpx.Response(402, request=request, json={"error": {
            "message": "Insufficient credits for requested output limit",
            "metadata": {"previous_errors": ["Repeated provider details"]},
        }})
        with self.assertRaises(client.OpenRouterError) as raised:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                client._handle_response_error(exc)
        self.assertEqual(str(raised.exception),
                         "OpenRouter request failed (402): Insufficient credits for requested output limit")


if __name__ == "__main__":
    unittest.main()
