import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from server.config import Settings
from server.models import GmailConnectPayload, GmailDisconnectPayload, GmailStatusPayload
from server.services.gmail import client as gmail


class GmailConnectionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "gmail" / "active_user_id.txt"
        for name, value in (
            ("_ACTIVE_USER_ID_PATH", self.path),
            ("_ACTIVE_USER_ID", None),
            ("_PROFILE_CACHE", {}),
        ):
            patcher = patch.object(gmail, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.sdk = Mock()
        patcher = patch.object(gmail, "_get_composio_client", return_value=self.sdk)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(gmail, "_fetch_profile_from_composio", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_status_finds_sdk_items_and_restores_user_after_restart(self):
        account = SimpleNamespace(id="ca_test", user_id="web-test", status="ACTIVE")
        self.sdk.connected_accounts.list.return_value = SimpleNamespace(items=[account])
        response = gmail.fetch_status(GmailStatusPayload(user_id="web-test"))
        self.assertTrue(json.loads(response.body)["connected"])
        self.sdk.connected_accounts.list.assert_called_once_with(
            user_ids=["web-test"], toolkit_slugs=["gmail"], statuses=["ACTIVE"]
        )
        self.assertEqual(self.path.read_text(encoding="utf-8"), "web-test")
        gmail._ACTIVE_USER_ID = None
        self.assertEqual(gmail.get_active_gmail_user_id(), "web-test")

    def test_connection_owner_is_used_instead_of_stale_browser_user(self):
        self.sdk.connected_accounts.wait_for_connection.return_value = SimpleNamespace(
            id="ca_test", user_id="actual-owner", status="ACTIVE"
        )
        response = gmail.fetch_status(GmailStatusPayload(
            connection_request_id="ca_test", user_id="stale-browser-id"
        ))
        self.assertEqual(json.loads(response.body)["user_id"], "actual-owner")
        self.assertEqual(gmail.get_active_gmail_user_id(), "actual-owner")

    def test_pending_oauth_does_not_activate_user(self):
        self.sdk.connected_accounts.link.return_value = SimpleNamespace(id="ca_pending", redirect_url="https://example.test")
        response = gmail.initiate_connect(
            GmailConnectPayload(user_id="web-test", auth_config_id="ac_test"), Settings()
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(gmail.get_active_gmail_user_id())
        self.assertFalse(self.path.exists())

    def test_unconnected_status_clears_saved_user(self):
        gmail._set_active_gmail_user_id("web-test")
        self.sdk.connected_accounts.list.return_value = SimpleNamespace(items=[])
        response = gmail.fetch_status(GmailStatusPayload(user_id="web-test"))
        self.assertFalse(json.loads(response.body)["connected"])
        self.assertIsNone(gmail.get_active_gmail_user_id())
        self.assertFalse(self.path.exists())

    def test_status_service_error_preserves_saved_connection(self):
        gmail._set_active_gmail_user_id("web-test")
        self.sdk.connected_accounts.list.side_effect = RuntimeError("Service unavailable")
        with self.assertLogs("openpoke.server", level="ERROR"):
            response = gmail.fetch_status(GmailStatusPayload(user_id="web-test"))
        self.assertEqual(response.status_code, 500)
        self.assertEqual(gmail.get_active_gmail_user_id(), "web-test")

    def test_disconnect_lists_items_and_clears_saved_user(self):
        account = SimpleNamespace(id="ca_test", user_id="web-test", status="ACTIVE")
        gmail._set_active_gmail_user_id("web-test")
        self.sdk.connected_accounts.list.return_value = SimpleNamespace(items=[account])
        self.sdk.connected_accounts.get.return_value = account
        response = gmail.disconnect_account(GmailDisconnectPayload(user_id="web-test"))
        self.assertTrue(json.loads(response.body)["disconnected"])
        self.sdk.connected_accounts.delete.assert_called_once_with("ca_test")
        self.assertIsNone(gmail.get_active_gmail_user_id())
        self.assertFalse(self.path.exists())

    def test_failed_disconnect_keeps_saved_connection(self):
        account = SimpleNamespace(id="ca_test", user_id="web-test", status="ACTIVE")
        gmail._set_active_gmail_user_id("web-test")
        self.sdk.connected_accounts.list.return_value = SimpleNamespace(items=[account])
        self.sdk.connected_accounts.get.return_value = account
        self.sdk.connected_accounts.delete.side_effect = RuntimeError("Service unavailable")
        with self.assertLogs("openpoke.server", level="ERROR"):
            response = gmail.disconnect_account(GmailDisconnectPayload(user_id="web-test"))
        self.assertEqual(response.status_code, 500)
        self.assertEqual(gmail.get_active_gmail_user_id(), "web-test")

    def test_account_response_shapes(self):
        account = {"id": "ca_test"}
        for response in (
            {"items": [account]}, {"data": [account]},
            SimpleNamespace(items=[account]), SimpleNamespace(data=[account]),
        ):
            with self.subTest(response=response):
                self.assertEqual(gmail._connected_account_items(response), [account])

    def test_failed_composio_result_raises_instead_of_becoming_empty_mailbox(self):
        self.sdk.client.tools.execute.return_value = {"successful": False, "error": "Authorization expired"}
        with self.assertLogs("openpoke.server", level="ERROR"):
            with self.assertRaisesRegex(RuntimeError, "Authorization expired"):
                gmail.execute_gmail_tool("GMAIL_FETCH_EMAILS", "web-test")


if __name__ == "__main__":
    unittest.main()
