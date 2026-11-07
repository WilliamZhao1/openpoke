import unittest
from unittest.mock import AsyncMock, patch

from server.agents.execution_agent.runtime import ExecutionAgentRuntime
from server.agents.execution_agent.tasks.search_email import gmail_internal


class GmailToolErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_execution_tool_recognizes_error_payload(self):
        runtime = object.__new__(ExecutionAgentRuntime)
        runtime.tool_registry = {"task_email_search": AsyncMock(return_value={"error": "Gmail not connected"})}
        success, result = await runtime._execute_tool("task_email_search", {"search_query": "today"})
        self.assertFalse(success)
        self.assertEqual(result["error"], "Gmail not connected")

    async def test_empty_search_result_is_successful(self):
        runtime = object.__new__(ExecutionAgentRuntime)
        runtime.tool_registry = {"task_email_search": AsyncMock(return_value=[])}
        success, result = await runtime._execute_tool("task_email_search", {"search_query": "today"})
        self.assertTrue(success)
        self.assertEqual(result, [])

    def test_internal_fetch_passes_keyword_only_arguments(self):
        with (
            patch.object(gmail_internal, "get_active_gmail_user_id", return_value="web-test"),
            patch.object(gmail_internal, "execute_gmail_tool", autospec=True, return_value={"data": {}}) as execute,
        ):
            gmail_internal.gmail_fetch_emails(query="in:inbox", max_results=1)
        self.assertEqual(execute.call_args.args, ("GMAIL_FETCH_EMAILS", "web-test"))
        self.assertEqual(execute.call_args.kwargs["arguments"]["query"], "in:inbox")


if __name__ == "__main__":
    unittest.main()
