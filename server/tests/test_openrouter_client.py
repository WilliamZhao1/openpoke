import json
import unittest
from unittest.mock import patch

import httpx

from server.config import Settings
from server.openrouter_client import client


class OpenRouterClientTests(unittest.IsolatedAsyncioTestCase):
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
