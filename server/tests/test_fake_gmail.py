from contextlib import ExitStack
from datetime import timezone
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from server.agents.execution_agent.runtime import ExecutionAgentRuntime
from server.agents.execution_agent.tasks.search_email import gmail_internal, tool as search_tool
from server.agents.execution_agent.tools import gmail as tools
from server.services.execution import ExecutionAgentLogStore
from server.services.gmail import client
from server.services.gmail.processing import parse_gmail_fetch_response
from server.tests.fixtures.catalogs import load_fixture
from server.tests.fixtures.fake_gmail import FakeGmail, use_fake_gmail


class FakeGmailTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.fake = FakeGmail()
        logs = ExecutionAgentLogStore(Path(directory.name) / "workers")
        self.stack.enter_context(patch.object(tools, "_LOG_STORE", logs))
        self.stack.enter_context(patch.object(search_tool, "_LOG_STORE", logs))
        self.stack.enter_context(patch.object(socket.socket, "connect", side_effect=AssertionError("Fixture attempted network access")))
        self.stack.enter_context(patch.object(socket.socket, "connect_ex", side_effect=AssertionError("Fixture attempted network access")))

    def test_search_uses_real_adapters_parser_and_exact_provider_ids(self):
        with use_fake_gmail(self.fake):
            raw = gmail_internal.gmail_fetch_emails(query='from:alice@example.test subject:"services contract"')
        emails, cursor = parse_gmail_fetch_response(raw, query="services contract")
        self.assertIsNone(cursor)
        email, = emails
        self.assertEqual(email.id, "18fa000000000002")
        self.assertEqual(email.thread_id, "18fa000000000102")
        self.assertEqual(email.attachment_filenames, ["services-contract.pdf"])
        self.assertIn("original services contract", email.clean_text)
        self.assertEqual(email.timestamp.astimezone(timezone.utc).isoformat(), "2026-11-08T11:50:00+00:00")
        self.assertEqual(raw["fixture"]["source_mode"], "mock")
        self.assertEqual(self.fake.calls[0]["arguments"]["user_id"], "me")
        self.assertEqual(self.fake.effects, [])

    def test_pagination_is_stable_and_bound_to_account_and_query(self):
        with use_fake_gmail(self.fake):
            first = gmail_internal.gmail_fetch_emails(query="from:alice@example.test", max_results=2)["data"]
            second = gmail_internal.gmail_fetch_emails(query="from:alice@example.test", max_results=2, page_token=first["nextPageToken"])["data"]
            with self.assertLogs("openpoke.server", level="ERROR"):
                with self.assertRaises(RuntimeError):
                    gmail_internal.gmail_fetch_emails(query="subject:lunch", page_token=first["nextPageToken"])
        self.assertFalse({row["id"] for row in first["messages"]} & {row["id"] for row in second["messages"]})
        self.assertEqual(len(first["messages"] + second["messages"]), 4)
        self.assertIsNone(second["nextPageToken"])
        with use_fake_gmail(self.fake, profile_id="fixture-profile-b"):
            with self.assertLogs("openpoke.server", level="ERROR"):
                with self.assertRaises(RuntimeError):
                    gmail_internal.gmail_fetch_emails(query="from:alice@example.test", page_token=first["nextPageToken"])

    def test_create_then_send_preserves_exact_body_recipients_and_attachments(self):
        body = "<p>Hi Alice — Café Étoile &amp; Montréal.</p>\n\n"
        attachment = {"s3key": "fixture/contract", "name": "contract.pdf", "mimetype": "application/pdf"}
        with use_fake_gmail(self.fake):
            draft = tools.gmail_create_draft(
                "alice@example.test", "Lunch", body, cc=["cc@example.test"], bcc=["bcc@example.test"],
                extra_recipients=["extra@example.test"], is_html=True,
                thread_id="18fa000000000101", attachment=attachment,
            )["data"]
            draft_id = draft["id"]
            draft["body"] = "Mutation of returned data must not change stored content"
            sent = tools.gmail_execute_draft(draft_id)["data"]
        created, effect = self.fake.effects
        self.assertEqual(created["kind"], "draft_created")
        self.assertEqual(effect["kind"], "draft_sent")
        self.assertEqual(effect["body"], body)
        self.assertEqual(effect["message"]["htmlBody"], body)
        self.assertEqual(effect["message"]["cc"], ["cc@example.test"])
        self.assertEqual(effect["message"]["bcc"], ["bcc@example.test"])
        self.assertEqual(effect["message"]["extra_recipients"], ["extra@example.test"])
        self.assertEqual(effect["message"]["attachmentList"], [attachment])
        self.assertEqual(sent["id"], effect["message"]["id"])
        self.assertEqual(sent["threadId"], "18fa000000000101")
        self.assertNotIn(draft_id, self.fake.snapshot()["accounts"]["fixture-gmail-a"]["drafts"])

    def test_duplicate_ids_in_two_accounts_never_cross_mailbox_boundaries(self):
        draft_id = "r100000000000000001"
        with use_fake_gmail(self.fake):
            tools.gmail_execute_draft(draft_id)
        with use_fake_gmail(self.fake, profile_id="fixture-profile-b"):
            remaining = tools.gmail_list_drafts()["data"]["drafts"]
            self.assertEqual([draft["id"] for draft in remaining], [draft_id])
            tools.gmail_execute_draft(draft_id)
            with self.assertLogs("openpoke.server", level="ERROR"):
                with self.assertRaises(RuntimeError):
                    tools.gmail_reply_to_thread("18fa000000000102", "alice@example.test", "wrong account")
        first, second = self.fake.effects
        self.assertEqual(first["account_id"], "fixture-gmail-a")
        self.assertEqual(first["message"]["to"], "alice@example.test")
        self.assertEqual(second["account_id"], "fixture-gmail-b")
        self.assertEqual(second["message"]["to"], "bob@example.test")
        self.assertEqual(second["body"], "Account B draft for Bob.")

    def test_before_and_after_failure_expose_the_actual_send_outcome(self):
        draft_id = "r100000000000000001"
        with use_fake_gmail(self.fake):
            self.fake.fail_next("GMAIL_SEND_DRAFT", phase="before")
            with self.assertLogs("openpoke.server", level="ERROR"):
                with self.assertRaises(RuntimeError):
                    tools.gmail_execute_draft(draft_id)
            self.assertEqual(self.fake.effects, [])
            self.assertIn(draft_id, self.fake.snapshot()["accounts"]["fixture-gmail-a"]["drafts"])
            self.fake.fail_next("GMAIL_SEND_DRAFT", phase="after")
            with self.assertLogs("openpoke.server", level="ERROR"):
                with self.assertRaisesRegex(RuntimeError, "reconcile effects"):
                    tools.gmail_execute_draft(draft_id)
            self.assertEqual(self.fake.calls[-1]["outcome"], "unknown")
            self.assertEqual(len(self.fake.effects), 1)
            with self.assertLogs("openpoke.server", level="ERROR"):
                with self.assertRaises(RuntimeError):
                    tools.gmail_execute_draft(draft_id)
        self.assertEqual(len(self.fake.effects), 1)

    def test_reply_retry_can_produce_a_duplicate_after_an_uncertain_result(self):
        with use_fake_gmail(self.fake):
            self.fake.fail_next("GMAIL_REPLY_TO_THREAD", phase="after")
            with self.assertLogs("openpoke.server", level="ERROR"):
                with self.assertRaises(RuntimeError):
                    tools.gmail_reply_to_thread("18fa000000000102", "alice@example.test", "Same reply")
            tools.gmail_reply_to_thread("18fa000000000102", "alice@example.test", "Same reply")
        self.assertEqual([effect["kind"] for effect in self.fake.effects], ["reply_sent", "reply_sent"])
        self.assertNotEqual(self.fake.effects[0]["message"]["id"], self.fake.effects[1]["message"]["id"])

    def test_delete_removes_a_draft_without_sending(self):
        with use_fake_gmail(self.fake):
            result = tools.gmail_delete_draft("r100000000000000001")["data"]
            drafts = tools.gmail_list_drafts()["data"]["drafts"]
        self.assertTrue(result["deleted"])
        self.assertEqual([row["id"] for row in drafts], ["r100000000000000002"])
        self.assertEqual([effect["kind"] for effect in self.fake.effects], ["draft_deleted"])

    def test_forward_retains_source_text_and_records_the_new_thread(self):
        source = load_fixture("gmail_mailbox.json")["accounts"][0]["messages"][0]
        with use_fake_gmail(self.fake):
            result = tools.gmail_forward_email(source["id"], "reviewer@example.test", "Please review.")["data"]
        effect, = self.fake.effects
        self.assertEqual(effect["kind"], "forward_sent")
        self.assertEqual(effect["body"], "Please review.\n\n" + source["textBody"])
        self.assertEqual(effect["source_message_id"], source["id"])
        self.assertEqual(effect["message"]["to"], "reviewer@example.test")
        self.assertEqual(result["threadId"], effect["message"]["threadId"])
        self.assertNotEqual(result["threadId"], source["threadId"])

    def test_people_search_and_people_paging_use_current_argument_names(self):
        with use_fake_gmail(self.fake):
            contact, = tools.gmail_search_people("Alice", page_size=1)["data"]["results"]
            first = tools.gmail_get_people(page_size=1)["data"]
            second = tools.gmail_get_people(page_size=1, page_token=first["nextPageToken"])["data"]
            contacts = tools.gmail_get_contacts()["data"]["connections"]
        self.assertEqual(contact["person"]["resourceName"], "people/fixture-alice")
        self.assertEqual(len(contacts), 2)
        self.assertNotEqual(first["connections"], second["connections"])
        self.assertIsNone(second["nextPageToken"])

    def test_fixed_clock_controls_recency_without_wall_clock_time(self):
        with use_fake_gmail(self.fake):
            first = gmail_internal.gmail_fetch_emails(query="label:INBOX newer_than:10m")["data"]["messages"]
            self.fake.clock.advance(seconds=601)
            later = gmail_internal.gmail_fetch_emails(query="label:INBOX newer_than:10m")["data"]["messages"]
        self.assertEqual(len(first), 2)
        self.assertEqual(later, [])
        self.assertEqual(self.fake.calls[-1]["timestamp"], "2026-11-08T12:10:01Z")

    def test_replaying_the_same_operations_reproduces_ids_and_evidence(self):
        def run():
            fake = FakeGmail()
            with use_fake_gmail(fake):
                draft = tools.gmail_create_draft("alice@example.test", "Subject", "Exact body")["data"]
                fake.clock.advance(seconds=30)
                tools.gmail_execute_draft(draft["id"])
                tools.gmail_forward_email("18fa000000000001", "reviewer@example.test")
            return fake.snapshot()

        self.assertEqual(run(), run())
        snapshot = self.fake.snapshot()
        snapshot["accounts"].clear()
        self.assertEqual(len(self.fake.snapshot()["accounts"]), 2)

    async def test_email_search_and_runtime_distinguish_failure_from_empty_success(self):
        with use_fake_gmail(self.fake):
            result = await search_tool._perform_search(
                arguments={"query": "subject:services"}, queries=[], emails={}, composio_user_id="fixture-profile-a",
            )
            self.assertEqual(result.status, "success")
            self.assertEqual(result.messages[0].thread_id, "18fa000000000102")
            self.fake.fail_next("GMAIL_FETCH_EMAILS")
            with self.assertLogs("openpoke.server", level="ERROR"):
                failed = await search_tool._perform_search(
                    arguments={"query": "subject:services"}, queries=[], emails={}, composio_user_id="fixture-profile-a",
                )
            self.assertEqual(failed.status, "error")
            runtime = object.__new__(ExecutionAgentRuntime)
            runtime.tool_registry = {"gmail_execute_draft": tools.gmail_execute_draft}
            self.fake.fail_next("GMAIL_SEND_DRAFT")
            with self.assertLogs("openpoke.server", level="ERROR"):
                success, payload = await runtime._execute_tool("gmail_execute_draft", {"draft_id": "r100000000000000001"})
            self.assertFalse(success)
            self.assertIn("error", payload)
            empty = gmail_internal.gmail_fetch_emails(query="no-matching-garden-message")["data"]["messages"]
            self.assertEqual(empty, [])
        self.assertEqual(self.fake.effects, [])

    def test_unsupported_operations_and_unknown_accounts_fail_without_fallback(self):
        with use_fake_gmail(self.fake):
            for tool, arguments in [
                ("GMAIL_UNKNOWN", {}), ("GMAIL_FETCH_EMAILS", {"query": "lunch OR contract"}),
                ("GMAIL_FETCH_EMAILS", {"query": "unsupported:value"}),
            ]:
                with self.assertLogs("openpoke.server", level="ERROR"):
                    with self.assertRaises(RuntimeError):
                        client.execute_gmail_tool(tool, "fixture-profile-a", arguments=arguments)
            with self.assertLogs("openpoke.server", level="ERROR"):
                with self.assertRaises(RuntimeError):
                    client.execute_gmail_tool("GMAIL_LIST_DRAFTS", "unknown-profile")
        self.assertEqual(self.fake.effects, [])
        self.assertTrue(all(call["outcome"] == "failed" for call in self.fake.calls))

    def test_fake_session_restores_the_connection_binding(self):
        prior = client._ACTIVE_USER_ID
        prior_getter = client._get_composio_client
        with use_fake_gmail(self.fake):
            self.assertEqual(client.get_active_gmail_user_id(), "fixture-profile-a")
            self.assertIsNot(client._get_composio_client, prior_getter)
        self.assertEqual(client._ACTIVE_USER_ID, prior)
        self.assertIs(client._get_composio_client, prior_getter)


if __name__ == "__main__":
    unittest.main()
