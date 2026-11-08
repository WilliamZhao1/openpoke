from html import escape
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID

from server.agents.interaction_agent import agent
from server.services.execution import AgentRoster
from server.tests.fixtures.catalogs import build_catalog, fingerprint, load_fixture, routing_cases


class CatalogFixtureTests(unittest.TestCase):
    def test_catalog_sizes_ids_and_content_match_frozen_fingerprints(self):
        expected = load_fixture("checksums.json")
        first = build_catalog(100)
        for size in (0, 100, 1000, 10000):
            with self.subTest(size=size):
                catalog = build_catalog(size)
                self.assertEqual(len(catalog), size)
                self.assertEqual(fingerprint(catalog), expected["catalogs"][str(size)])
                ids = [str(UUID(row["workflow_id"])) for row in catalog]
                self.assertEqual(len(set(ids)), size)
                if size:
                    self.assertEqual(catalog[:100], first)
                self.assertTrue(all(not row["archived"] or row["status"] == "completed" for row in catalog))
                self.assertTrue(all("expected" not in row and "lookup" not in row for row in catalog))
        for name in ("routing_cases", "gmail_mailbox"):
            self.assertEqual(fingerprint(load_fixture(name + ".json")), expected[name])

    def test_fixture_loads_are_independent_and_reject_unfrozen_sizes_or_paths(self):
        modified = build_catalog(100)
        modified[0]["card"]["summary"] = "changed by one experiment"
        self.assertNotEqual(modified, build_catalog(100))
        for size in (True, -1, 1, 101):
            with self.assertRaises(ValueError):
                build_catalog(size)
        with self.assertRaises(ValueError):
            load_fixture("../../.env")

    def test_cases_cover_revised_contracts_without_leaking_gold_into_profiles(self):
        cases = {case["id"]: case for case in routing_cases()}
        self.assertEqual(len(cases), 14)
        self.assertEqual({case["split"] for case in cases.values()}, {"tuning", "held_out"})
        ids = {row["workflow_id"] for row in build_catalog(100)}
        for case in cases.values():
            self.assertTrue(set(case["expected"]["workflow_ids"]).issubset(ids))
            self.assertTrue(set(case["lookup"]["candidate_ids"]).issubset(ids))
            self.assertIn(case["expected"]["action"], {"reuse", "create_new", "abstain"})
        self.assertNotEqual(cases["alice-lunch"]["expected"]["workflow_ids"], cases["alice-contract"]["expected"]["workflow_ids"])
        self.assertEqual(cases["alternating-topics"]["expected"]["workflow_ids"], ["00000000-0000-4000-8000-000000000005"])
        self.assertEqual(cases["pronoun-draft"]["expected"]["draft_id"], "r100000000000000001")
        self.assertEqual(cases["empty-catalog"]["catalog"], "empty")
        self.assertEqual(cases["genuinely-new"]["expected"]["action"], "create_new")
        self.assertEqual({case["lookup"]["status"] for case in cases.values()}, {"complete", "partial", "unavailable"})
        for name in ("near-tied-owners", "partial-lookup", "lookup-unavailable", "competing-drafts"):
            self.assertEqual(cases[name]["expected"]["action"], "abstain")
        self.assertEqual(cases["near-tied-owners"]["lookup"]["ranking"]["source_mode"], "mock")
        self.assertEqual(len(cases["two-owners"]["expected"]["workflow_ids"]), 2)

    def test_stale_card_and_dormant_owner_are_explicit_test_inputs(self):
        catalog = build_catalog(100)
        old = catalog[2]
        recent = sorted(catalog, key=lambda row: row["last_activity_at"], reverse=True)[:5]
        self.assertTrue(old["archived"])
        self.assertNotIn(old["workflow_id"], {row["workflow_id"] for row in recent})
        stale = catalog[6]
        self.assertLess(stale["card"]["revision"], stale["revision"])
        self.assertEqual(stale["card"]["obligations"][0]["state"], "open")
        self.assertEqual(stale["current_obligations"][0]["state"], "resolved")

    def test_core_resource_bindings_resolve_to_the_correct_fixture_mailbox(self):
        accounts = {account["account_id"]: account for account in load_fixture("gmail_mailbox.json")["accounts"]}
        for workflow in load_fixture("catalog.json")["core_workflows"]:
            for ref in workflow["resource_refs"]:
                account = accounts[ref["account_id"]]
                self.assertEqual(ref["provider"], "gmail")
                if ref["resource_type"] == "thread":
                    self.assertIn(ref["resource_id"], {message["threadId"] for message in account["messages"]})
                else:
                    self.assertIn(ref["resource_id"], {draft["id"] for draft in account["drafts"]})
        self.assertEqual(accounts["fixture-gmail-a"]["messages"][0]["id"], accounts["fixture-gmail-b"]["messages"][0]["id"])
        self.assertNotEqual(accounts["fixture-gmail-a"]["messages"][0]["textBody"], accounts["fixture-gmail-b"]["messages"][0]["textBody"])

    def test_comparisons_change_one_declared_factor_at_a_time(self):
        comparisons = load_fixture("routing_cases.json")["comparisons"]
        self.assertEqual([row["id"] for row in comparisons], [
            "legacy_full_roster", "lexical_names", "lexical_cards", "lexical_cards_checked", "semantic_cards_checked",
        ])
        factors = ("metadata", "discovery", "decision_checks", "semantic_ranker")
        for left, right in zip(comparisons, comparisons[1:]):
            self.assertEqual(sum(left[field] != right[field] for field in factors), 1)

    def test_current_legacy_prompt_still_contains_the_entire_fixture_roster(self):
        catalog = build_catalog(100)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "roster.json"
            path.write_text(json.dumps([row["display_name"] for row in catalog]), encoding="utf-8")
            roster = AgentRoster(path)
            with patch.object(agent, "get_agent_roster", return_value=roster):
                message = agent.prepare_message_with_history("Continue lunch planning.", "")[0]["content"]
        self.assertEqual(message.count("<agent name="), 100)
        for row in catalog:
            self.assertIn(f'<agent name="{escape(row["display_name"], quote=True)}" />', message)
            self.assertNotIn(row["workflow_id"], message)


if __name__ == "__main__":
    unittest.main()
