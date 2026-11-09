from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from server.services.execution.log_store import _slugify, ExecutionAgentLogStore
from server.services.workflows import migration


STAMP = "2026-11-08 12:00:00"
COMMAND = Path(__file__).resolve().parents[1] / "services" / "workflows" / "migration.py"


def line(tag, payload, timestamp=STAMP):
    encoded = escape(payload.replace("\n", "\\n"), quote=False)
    attr = f' timestamp="{timestamp}"' if timestamp is not None else ""
    return f"<{tag}{attr}>{encoded}</{tag}>\n"


class WorkflowMigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.root = self.directory / "legacy profile"
        self.root.mkdir()

    def write(self, relative, contents):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents.encode("utf-8") if isinstance(contents, str) else contents)
        return path

    def roster(self, names):
        self.write(migration.ROSTER, json.dumps(names, ensure_ascii=False))

    def seed(self):
        self.roster(["Alice lunch"])
        self.write("execution_agents/alice-lunch.log", line("agent_request", "PRIVATE worker request") + line("tool_response", "PRIVATE tool body"))
        self.write(migration.CONVERSATION, line("user_message", "PRIVATE first message") + line("poke_reply", "PRIVATE reply"))
        self.memory(last_index=0, tail=line("poke_reply", "PRIVATE reply"))
        self.trigger_database([(1, "Alice lunch"), (2, "Alice lunch")])

    def memory(self, *, last_index=-1, tail="", summary="PRIVATE summary"):
        return self.write(migration.MEMORY,
                          line("summary_info", json.dumps({"last_index": last_index, "updated_at": "2026-11-08T12:00:00+00:00"}), None)
                          + line("conversation_summary", summary, None) + tail)

    def trigger_database(self, records, *, wal=False):
        connection = sqlite3.connect(self.root / migration.TRIGGERS)
        self.addCleanup(connection.close)
        if wal:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("""CREATE TABLE triggers (
            id INTEGER PRIMARY KEY, agent_name TEXT, payload TEXT, start_time TEXT,
            next_trigger TEXT, recurrence_rule TEXT, timezone TEXT, status TEXT,
            last_error TEXT, created_at TEXT, updated_at TEXT)""")
        for identifier, name in records:
            connection.execute("INSERT INTO triggers VALUES (?, ?, ?, NULL, NULL, NULL, 'UTC', 'active', NULL, ?, ?)",
                               (identifier, name, "PRIVATE trigger payload", STAMP, STAMP))
        connection.commit()
        if not wal:
            connection.close()
        return connection

    def snapshot(self):
        return {str(path.relative_to(self.root)): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.root.rglob("*") if path.is_file()}

    def inspect(self):
        return migration.LegacyMigrationInspector(self.root).inspect()

    def codes(self, report):
        return {issue["code"] for issue in report["issues"]}

    def command(self, *args, environment=None):
        return subprocess.run([sys.executable, str(COMMAND), "--data-dir", str(self.root), *map(str, args)],
                              capture_output=True, text=True, timeout=15, env=environment)

    def test_complete_inventory_preserves_sources_and_excludes_private_payloads(self):
        self.seed()
        before = self.snapshot()
        inspector = migration.LegacyMigrationInspector(self.root)
        report = inspector.inspect()
        self.assertEqual(report, inspector.inspect())
        self.assertEqual(report["status"], "review_ready")
        self.assertTrue(report["source_set_unchanged"])
        self.assertFalse(report["apply_supported"])
        self.assertEqual(before, self.snapshot())
        self.assertEqual(report["counts"]["triggers"], 2)
        self.assertEqual(report["worker_logs"][0]["owner_resolution"], "resolved")
        self.assertIsNone(report["worker_logs"][0]["workflow_status"])
        self.assertIsNone(report["roster_entries"][0]["workflow_id"])
        self.assertEqual(report["working_memory"]["last_index"], 0)
        self.assertEqual(report["working_memory"]["boundary_ref"]["line"], 1)
        self.assertTrue(report["working_memory"]["tail_matches_conversation"])
        self.assertIn("legacy_tool_content_may_be_truncated", self.codes(report))
        rendered = json.dumps(report)
        self.assertNotIn("PRIVATE", rendered)
        self.assertFalse((self.root / "workflows.db").exists())
        for source in report["sources"]:
            if source["status"] == "available":
                self.assertEqual(source["sha256"], sha256((self.root / source["path"]).read_bytes()).hexdigest())

    def test_duplicate_aliases_slug_collisions_and_orphans_remain_unresolved(self):
        names = ["Alice / Lunch", "Alice - Lunch", "Same", "Same", "", "  ", 5, None]
        self.roster(names)
        self.write("execution_agents/alice-lunch.log", line("agent_request", "shared unknown history"))
        self.write("execution_agents/forgotten.log", line("agent_response", "orphan history"))
        self.trigger_database([(1, "Alice / Lunch"), (2, "Same"), (3, "Missing"), (4, None)])
        report = self.inspect()
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(len(report["roster_entries"]), len(names))
        self.assertTrue({"duplicate_roster_alias", "slug_collision", "orphan_worker_log", "display_name_required",
                         "roster_name_not_string", "trigger_owner_unresolved"}.issubset(self.codes(report)))
        shared = next(log for log in report["worker_logs"] if log["path"].endswith("alice-lunch.log"))
        self.assertEqual(shared["owner_names"], names[:2])
        self.assertEqual(shared["owner_resolution"], "unresolved")
        self.assertEqual(len(shared["entries"]), 1)
        # Exact trigger alias is resolvable even when its history needs reconciliation.
        self.assertEqual([record["owner_resolution"] for record in report["triggers"]["records"]],
                         ["resolved", "unresolved", "unresolved", "unresolved"])

    def test_exact_unicode_case_and_whitespace_names_and_missing_logs_are_preserved(self):
        names = ["Alice", "alice", " Café Étoile ", "🦉", "!!!"]
        self.roster(names)
        report = self.inspect()
        self.assertEqual([entry["name"] for entry in report["roster_entries"]], names)
        for name in names:
            self.assertEqual(migration.legacy_slug(name), _slugify(name))
        self.assertIn("worker_log_missing", self.codes(report))
        self.assertIn("slug_collision", self.codes(report))  # Two names use the fallback 'agent'.

    def test_log_offsets_hashes_and_indices_preserve_legacy_parser_semantics(self):
        self.roster(["Alice"])
        first = line("agent_request", "Café\n& <request>").replace("\n", "\r\n").encode("utf-8")
        invalid = b"not an entry\r\n"
        last = line("agent_response", "done", None).encode("utf-8")
        self.write("execution_agents/alice.log", first + invalid + last)
        report = self.inspect()
        log = report["worker_logs"][0]
        self.assertEqual([entry["legacy_index"] for entry in log["entries"]], [0, 1])
        self.assertEqual(log["entries"][1]["ref"], {"path": "execution_agents/alice.log", "line": 3,
                                                   "byte_offset": len(first + invalid), "byte_length": len(last)})
        self.assertEqual(log["entries"][0]["payload_sha256"], sha256("Café\n& <request>".encode()).hexdigest())
        self.assertEqual(log["first_request_ref"], log["latest_request_ref"])
        self.assertEqual(log["unparsed_lines"][0]["line"], 2)
        self.assertEqual(report["status"], "blocked")
        parser = ExecutionAgentLogStore.__new__(ExecutionAgentLogStore)
        for raw in (first.decode(), invalid.decode(), last.decode(), "<tag>data</tag>trailer", "<a></b>"):
            self.assertEqual(migration.parse_legacy_line(raw), parser._parse_line(raw))

    def test_invalid_utf8_and_noncanonical_entries_are_reported_without_dropping_source(self):
        self.roster(["Alice"])
        self.write("execution_agents/alice.log", b'\xff\n<tag>ok</tag>trailer\n')
        report = self.inspect()
        self.assertTrue({"unparsed_log_line", "noncanonical_log_line"}.issubset(self.codes(report)))
        self.assertEqual(len(report["worker_logs"][0]["entries"]), 1)
        self.assertEqual(report["status"], "blocked")

    def test_missing_inputs_do_not_get_created_and_invalid_rosters_are_not_empty_success(self):
        report = self.inspect()
        self.assertEqual(report["status"], "review_ready")
        self.assertFalse(any(self.root.iterdir()))
        for value, code in (("{broken", "roster_invalid_json"), ('{"name":"Alice"}', "roster_not_a_list")):
            self.write(migration.ROSTER, value)
            report = self.inspect()
            self.assertEqual(report["status"], "blocked")
            self.assertIn(code, self.codes(report))

    def test_unreadable_input_is_distinct_from_missing(self):
        self.roster(["Alice"])
        original = migration._fingerprint
        def deny(path):
            if path.name == "roster.json":
                raise PermissionError()
            return original(path)
        with patch.object(migration, "_fingerprint", side_effect=deny):
            report = self.inspect()
        source = next(item for item in report["sources"] if item["path"] == migration.ROSTER)
        self.assertEqual(source["status"], "unavailable")
        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["source_set_unchanged"])
        self.assertIn("source_unreadable", self.codes(report))

    def test_summary_boundary_and_working_tail_require_exact_references(self):
        self.write(migration.CONVERSATION, line("user_message", "first") + line("poke_reply", "second"))
        self.memory(last_index=10)
        self.assertIn("summary_boundary_missing", self.codes(self.inspect()))
        self.memory(last_index=0, tail=line("poke_reply", "wrong reply"))
        self.assertIn("working_memory_tail_mismatch", self.codes(self.inspect()))
        self.memory(last_index=1)
        report = self.inspect()
        self.assertEqual(report["status"], "review_ready")
        self.assertEqual(report["working_memory"]["boundary_ref"]["line"], 2)
        self.memory(last_index=-1, tail=line("user_message", "first") + line("poke_reply", "second"))
        self.assertTrue(self.inspect()["working_memory"]["tail_matches_conversation"])

    def test_summary_metadata_invalid_or_duplicated_is_not_guessed(self):
        for metadata in ("bad", "[]", '{"last_index":true}', '{"last_index":-2}', '{"last_index":0,"updated_at":5}'):
            self.write(migration.MEMORY, line("summary_info", metadata, None) + line("conversation_summary", "text", None))
            self.assertIn("summary_metadata_invalid", self.codes(self.inspect()))
        self.memory()
        with (self.root / migration.MEMORY).open("a", encoding="utf-8") as handle:
            handle.write(line("conversation_summary", "duplicate", None))
        self.assertIn("summary_records_ambiguous", self.codes(self.inspect()))

    def test_wal_only_commits_are_read_from_copies_without_touching_source_sqlite(self):
        self.roster(["Alice"])
        self.trigger_database([(1, "Alice")], wal=True)
        before = self.snapshot()
        original = sqlite3.connect
        opened = []
        def guarded(path, *args, **kwargs):
            self.assertFalse(Path(path).resolve().is_relative_to(self.root))
            opened.append(Path(path))
            return original(path, *args, **kwargs)
        with patch.object(migration.sqlite3, "connect", side_effect=guarded):
            report = self.inspect()
        self.assertEqual(report["status"], "review_ready")
        self.assertEqual(len(report["triggers"]["records"]), 1)
        self.assertEqual(report["triggers"]["records"][0]["owner_resolution"], "resolved")
        self.assertEqual(before, self.snapshot())
        self.assertTrue(opened)
        self.assertTrue(all(not path.parent.exists() for path in opened))

    def test_trigger_failure_corruption_journal_or_missing_main_is_explicit(self):
        self.write(migration.TRIGGERS, b"not a sqlite database")
        self.assertIn("trigger_snapshot_read_failed", self.codes(self.inspect()))
        self.write("triggers.db-journal", b"pending")
        self.assertIn("trigger_rollback_journal_present", self.codes(self.inspect()))
        (self.root / migration.TRIGGERS).unlink()
        self.write("triggers.db-wal", b"unresolved wal")
        self.assertIn("trigger_database_missing_with_wal", self.codes(self.inspect()))

    def test_unsupported_trigger_schema_is_not_initialized_or_repaired(self):
        connection = sqlite3.connect(self.root / migration.TRIGGERS)
        try:
            connection.execute("CREATE TABLE other (id INTEGER)")
            connection.commit()
        finally:
            connection.close()
        before = self.snapshot()
        self.assertIn("trigger_schema_unsupported", self.codes(self.inspect()))
        self.assertEqual(before, self.snapshot())

    def test_source_mutation_and_new_files_during_scan_invalidate_report(self):
        self.roster(["Alice"])
        inspector = migration.LegacyMigrationInspector(self.root)
        original = inspector._memory
        def mutate(conversation):
            self.roster(["Bob"])
            self.write("execution_agents/new-orphan.log", line("agent_response", "new"))
            return original(conversation)
        with patch.object(inspector, "_memory", side_effect=mutate):
            report = inspector.inspect()
        self.assertFalse(report["source_set_unchanged"])
        self.assertEqual(report["status"], "blocked")
        self.assertTrue({"source_changed_during_scan", "source_set_changed_during_scan"}.issubset(self.codes(report)))

    def test_direct_cli_has_no_app_import_initialization_credentials_or_network(self):
        self.seed()
        before = self.snapshot()
        unused_root = self.directory / "must not initialize"
        environment = dict(os.environ, OPENPOKE_DATA_DIR=str(unused_root), OPENROUTER_API_KEY="",
                           COMPOSIO_API_KEY="", COMPOSIO_GMAIL_AUTH_CONFIG_ID="")
        result = self.command(environment=environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "review_ready")
        self.assertEqual(before, self.snapshot())
        self.assertFalse(unused_root.exists())
        # runpy supplies a fresh interpreter and fails immediately on any server import.
        probe = """
import importlib.abc, runpy, socket, sys
class RejectServer(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname == 'server' or fullname.startswith('server.'):
            raise AssertionError('Migration must not import the application')
sys.meta_path.insert(0, RejectServer())
def reject(*args, **kwargs):
    raise AssertionError('Migration must not connect to network')
socket.socket.connect = socket.socket.connect_ex = reject
sys.argv = [sys.argv[1], '--data-dir', sys.argv[2]]
runpy.run_path(sys.argv[0], run_name='__main__')
"""
        guarded = subprocess.run([sys.executable, "-c", probe, str(COMMAND), str(self.root)],
                                 capture_output=True, text=True, timeout=15, env=environment)
        self.assertEqual(guarded.returncode, 0, guarded.stderr)
        self.assertEqual(before, self.snapshot())

    def test_cli_exit_codes_new_output_and_source_overwrite_protection(self):
        output = self.directory / "report.json"
        result = self.command("--output", output)
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = output.read_bytes()
        self.assertEqual(self.command("--output", output).returncode, 1)
        self.assertEqual(output.read_bytes(), saved)
        self.assertEqual(self.command("--output", self.root / "new.json").returncode, 1)
        self.assertFalse((self.root / "new.json").exists())
        self.write(migration.ROSTER, "bad")
        blocked = self.command()
        self.assertEqual(blocked.returncode, 2)
        self.assertEqual(json.loads(blocked.stdout)["status"], "blocked")
        self.assertEqual(self.command("--data-dir", self.directory / "nonexistent").returncode, 1)
        self.assertFalse((self.directory / "nonexistent").exists())


if __name__ == "__main__":
    unittest.main()
