import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from server.agents.interaction_agent import runtime as agent_runtime
from server.agents.interaction_agent.runtime import InteractionResult
from server.config import Settings
from server.models import ChatMessage, ChatRequest
from server.openrouter_client import OpenRouterError
from server.services.conversation import chat_handler


class ChatFailureTests(unittest.IsolatedAsyncioTestCase):
    async def _submit(self, runtime, log):
        # Wait for the background task without touching the real conversation log.
        tasks = []
        create_task = asyncio.create_task

        def capture_task(coroutine):
            task = create_task(coroutine)
            tasks.append(task)
            return task

        with (
            patch.object(chat_handler, "InteractionAgentRuntime", return_value=runtime),
            patch.object(chat_handler, "get_conversation_log", return_value=log),
            patch.object(chat_handler.asyncio, "create_task", side_effect=capture_task),
        ):
            response = await chat_handler.handle_chat_request(
                ChatRequest(messages=[ChatMessage(role="user", content="Hello")])
            )
            self.assertEqual(response.status_code, 202)
            await asyncio.gather(*tasks)

    async def test_failed_result_is_visible_in_chat(self):
        runtime = Mock(execute=AsyncMock(return_value=InteractionResult(
            success=False, response="", error="OpenRouter request failed (404): model unavailable"
        )))
        log = Mock()
        with self.assertLogs("openpoke.server", level="ERROR") as captured:
            await self._submit(runtime, log)
        log.record_reply.assert_called_once()
        self.assertIn("couldn't process", log.record_reply.call_args.args[0])
        self.assertIn("model unavailable", "\n".join(captured.output))

    async def test_unexpected_exception_is_visible_in_chat(self):
        runtime = Mock(execute=AsyncMock(side_effect=RuntimeError("unexpected failure")))
        log = Mock()
        with self.assertLogs("openpoke.server", level="ERROR") as captured:
            await self._submit(runtime, log)
        log.record_reply.assert_called_once()
        self.assertIn("RuntimeError: unexpected failure", "\n".join(captured.output))

    async def test_success_does_not_add_a_duplicate_reply(self):
        runtime = Mock(execute=AsyncMock(return_value=InteractionResult(
            success=True, response="Hello!"
        )))
        log = Mock()
        await self._submit(runtime, log)
        log.record_reply.assert_not_called()

    async def test_runtime_logs_provider_error_and_traceback(self):
        settings = Settings(openrouter_api_key="test-key", conversation_summary_threshold=0)
        log = Mock()
        log.load_transcript.return_value = ""
        with (
            patch.object(agent_runtime, "get_settings", return_value=settings),
            patch.object(agent_runtime, "get_conversation_log", return_value=log),
            patch.object(agent_runtime, "get_working_memory_log", return_value=Mock()),
            patch.object(agent_runtime, "build_system_prompt", return_value="Test prompt"),
            patch.object(agent_runtime, "prepare_message_with_history", return_value=[]),
        ):
            runtime = agent_runtime.InteractionAgentRuntime()
            with (
                patch.object(runtime, "_run_interaction_loop", new=AsyncMock(
                    side_effect=OpenRouterError("OpenRouter request failed (404): model unavailable")
                )),
                self.assertLogs("openpoke.server", level="ERROR") as captured,
            ):
                result = await runtime.execute("Hello")
        self.assertFalse(result.success)
        self.assertIn("model unavailable", result.error)
        output = "\n".join(captured.output)
        self.assertIn("Traceback", output)
        self.assertIn("OpenRouter request failed (404)", output)


if __name__ == "__main__":
    unittest.main()
