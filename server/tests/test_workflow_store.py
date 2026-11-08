from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
from time import perf_counter
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from server.services.execution.log_store import _slugify
from server.services.workflows import WorkflowStatus, WorkflowStore
from server.services.workflows import store as store_module
from server.services.workflows.errors import (
    WorkflowBusyError, WorkflowConfigurationError, WorkflowConflictError,
    WorkflowGenerationError, WorkflowIntegrityError, WorkflowNotFoundError,
    WorkflowRevisionError, WorkflowSchemaError, WorkflowStorageError,
)


@contextmanager
def database(path):
    connection = sqlite3.connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


class WorkflowStoreTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "state with spaces" / "workflows.db"
        self.now = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
        self.store = WorkflowStore(self.path, clock=lambda: self.now)

    def create(self, name="Alice lunch", **kwargs):
        return self.store.create(scope="local", display_name=name, **kwargs)

    def match(self, query, *, scope="local"):
        with database(self.path) as connection:
            return [row[0] for row in connection.execute(
                """SELECT d.workflow_id FROM workflow_search_fts f
                    JOIN workflow_search_documents d ON d.doc_id=f.rowid
                    WHERE workflow_search_fts MATCH ? AND d.scope=? AND d.generation_id=?
                    ORDER BY d.workflow_id""",
                (query, scope, str(self.store.generation_id)),
            )]

    def test_create_reopen_preserves_identity_generation_and_aliases(self):
        identifier = uuid4()
        workflow = self.create(workflow_id=identifier, purpose="Arrange lunch", aliases=("Lunch with Alice",))
        reopened = WorkflowStore(self.path)
        self.assertEqual(reopened.generation_id, self.store.generation_id)
        self.assertEqual(reopened.get(identifier, scope="local"), workflow)
        self.assertEqual(reopened.get_by_alias("Lunch with Alice", scope="local"), workflow)
        self.assertEqual(workflow.revision, 1)
        self.assertEqual(workflow.status, WorkflowStatus.OPEN)
        self.assertIsNone(workflow.archived_at)
        self.assertEqual(workflow.created_at, self.now)
        with self.assertRaises(FrozenInstanceError):
            workflow.display_name = "changed"

    def test_reopening_is_idempotent_and_records_one_schema_migration(self):
        self.create()
        for _ in range(3):
            WorkflowStore(self.path)
        with database(self.path) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM workflows").fetchone()[0], 1)
            self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")

    def test_names_that_collide_as_legacy_slugs_remain_distinct(self):
        first = self.create("Alice / Lunch", purpose="first task")
        second = self.create("Alice - Lunch", purpose="another task")
        self.assertEqual(_slugify(first.display_name), _slugify(second.display_name))
        self.assertNotEqual(first.workflow_id, second.workflow_id)
        reopened = WorkflowStore(self.path)
        self.assertEqual(reopened.get_by_alias(first.display_name, scope="local").purpose, "first task")
        self.assertEqual(reopened.get_by_alias(second.display_name, scope="local").purpose, "another task")

    def test_aliases_preserve_case_unicode_whitespace_and_empty_legacy_names(self):
        first = self.create("Alice", aliases=("Café Étoile", " Alice ", "", "'; DROP TABLE workflows; --"))
        second = self.create("alice")
        self.assertNotEqual(first.workflow_id, second.workflow_id)
        for alias in ("Alice", "Café Étoile", " Alice ", "", "'; DROP TABLE workflows; --"):
            self.assertEqual(self.store.get_by_alias(alias, scope="local").workflow_id, first.workflow_id)
        self.assertEqual(self.store.get_by_alias("alice", scope="local"), second)
        self.assertIsNone(self.store.get_by_alias("ALICE", scope="local"))
        self.assertEqual(len(self.store.list_workflows(scope="local")), 2)

    def test_scope_boundaries_apply_to_aliases_ids_updates_and_lists(self):
        first = self.create()
        other = self.store.create(scope="other", display_name="Alice lunch")
        self.assertIsNone(self.store.get(first.workflow_id, scope="other"))
        self.assertEqual(self.store.get_by_alias("Alice lunch", scope="other"), other)
        self.assertEqual(self.store.list_workflows(scope="local"), [first])
        with self.assertRaises(WorkflowNotFoundError):
            self.store.update(first.workflow_id, scope="other", expected_revision=1, purpose="cross-scope")
        with self.assertRaises(WorkflowNotFoundError):
            self.store.list_aliases(first.workflow_id, scope="other")

    def test_rename_keeps_original_alias_and_rejects_stale_updates(self):
        first = self.create(purpose="sushi")
        self.now += timedelta(minutes=1)
        updated = self.store.update(first.workflow_id, scope="local", expected_revision=1,
                                    display_name="Alice meal planning", purpose="tapas", summary="Dinner options")
        self.assertEqual(updated.workflow_id, first.workflow_id)
        self.assertEqual(updated.created_at, first.created_at)
        self.assertEqual(updated.last_activity_at, self.now)
        self.assertEqual(updated.revision, 2)
        for name in (first.display_name, updated.display_name):
            self.assertEqual(self.store.get_by_alias(name, scope="local"), updated)
        self.assertEqual({alias.alias for alias in self.store.list_aliases(first.workflow_id, scope="local")}, {first.display_name, updated.display_name})
        self.assertEqual(self.match("sushi"), [])
        self.assertEqual(self.match("tapas"), [str(first.workflow_id)])
        with self.assertRaises(WorkflowRevisionError):
            self.store.update(first.workflow_id, scope="local", expected_revision=1, summary="lost update")
        self.assertEqual(self.store.get(first.workflow_id, scope="local"), updated)

    def test_noop_and_repeated_alias_do_not_advance_revision(self):
        workflow = self.create()
        self.assertEqual(self.store.update(workflow.workflow_id, scope="local", expected_revision=1), workflow)
        updated = self.store.add_alias(workflow.workflow_id, "Historical lunch", scope="local", expected_revision=1)
        self.assertEqual(updated.revision, 2)
        self.assertEqual(self.store.add_alias(workflow.workflow_id, "Historical lunch", scope="local", expected_revision=2), updated)
        self.assertEqual(self.match("Historical"), [str(workflow.workflow_id)])

    def test_conflicting_names_aliases_and_ids_roll_back_without_reuse(self):
        first = self.create()
        second = self.create("Alice contract")
        with self.assertRaises(WorkflowConflictError):
            self.create("Alice lunch", purpose="different valid task")
        with self.assertRaises(WorkflowConflictError):
            self.create("Another name", workflow_id=first.workflow_id)
        with self.assertRaises(WorkflowConflictError):
            self.store.update(second.workflow_id, scope="local", expected_revision=1,
                              display_name="Alice lunch", purpose="must roll back")
        with self.assertRaises(WorkflowConflictError):
            self.store.add_alias(second.workflow_id, "Alice lunch", scope="local", expected_revision=1)
        self.assertEqual(self.store.get(second.workflow_id, scope="local"), second)
        self.assertEqual(len(self.store.list_workflows(scope="local")), 2)

    def test_unknown_history_status_is_not_completed_or_archived(self):
        workflow = self.create(status=None)
        reopened = WorkflowStore(self.path)
        self.assertIsNone(reopened.get(workflow.workflow_id, scope="local").status)
        self.assertIsNone(workflow.archived_at)
        with self.assertRaises(ValueError):
            self.store.update(workflow.workflow_id, scope="local", expected_revision=1, status="failed")
        self.assertIsNone(self.store.get(workflow.workflow_id, scope="local").status)

    def test_workflow_states_are_separate_from_run_outcomes(self):
        workflow = self.create()
        for status in WorkflowStatus:
            workflow = self.store.update(workflow.workflow_id, scope="local", expected_revision=workflow.revision, status=status)
            self.assertEqual(workflow.status, status)
            self.assertIsNone(workflow.archived_at)

    def test_paging_is_bounded_stable_and_does_not_skip_records(self):
        ids = {self.create(f"Task {index}").workflow_id for index in range(5)}
        first = self.store.list_workflows(scope="local", limit=2)
        second = self.store.list_workflows(scope="local", limit=2, after_id=first[-1].workflow_id)
        third = self.store.list_workflows(scope="local", limit=2, after_id=second[-1].workflow_id)
        self.assertEqual({workflow.workflow_id for workflow in first + second + third}, ids)
        self.assertEqual(len(first + second + third), 5)
        for limit in (0, -1, 101, True):
            with self.assertRaises(ValueError):
                self.store.list_workflows(scope="local", limit=limit)

    def test_rebuild_restores_documents_from_workflows_and_aliases(self):
        workflow = self.create(purpose="sushi")
        with database(self.path) as connection:
            connection.execute("UPDATE workflow_search_documents SET document='incorrect projection', scope='wrong-scope'")
        self.assertEqual(self.match("sushi"), [])
        self.assertEqual(self.store.rebuild_search_index(), 1)
        self.assertEqual(self.match("sushi"), [str(workflow.workflow_id)])
        self.assertEqual(self.match("incorrect"), [])
        self.assertEqual(self.store.get(workflow.workflow_id, scope="local"), workflow)
        with database(self.path) as connection:
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_index_write_failure_rolls_back_workflow_alias_and_revision_writes(self):
        workflow = self.create(purpose="sushi")
        with database(self.path) as connection:
            connection.execute("""CREATE TRIGGER reject_document_update BEFORE UPDATE ON workflow_search_documents
                                  BEGIN SELECT RAISE(ABORT, 'injected index failure'); END""")
            connection.execute("""CREATE TRIGGER reject_document_insert BEFORE INSERT ON workflow_search_documents
                                  BEGIN SELECT RAISE(ABORT, 'injected index failure'); END""")
        with self.assertRaises(WorkflowIntegrityError):
            self.create("New worker")
        with self.assertRaises(WorkflowIntegrityError):
            self.store.update(workflow.workflow_id, scope="local", expected_revision=1, display_name="New name", purpose="tapas")
        self.assertIsNone(self.store.get_by_alias("New worker", scope="local"))
        self.assertIsNone(self.store.get_by_alias("New name", scope="local"))
        self.assertEqual(self.store.get(workflow.workflow_id, scope="local"), workflow)
        self.assertEqual(self.match("sushi"), [str(workflow.workflow_id)])
        self.assertEqual(self.match("tapas"), [])

    def test_foreign_keys_reject_cross_scope_links_and_detect_external_orphans(self):
        workflow = self.create()
        with self.assertRaises(WorkflowIntegrityError):
            with self.store._connection() as connection:
                self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                connection.execute("INSERT INTO workflow_aliases VALUES(?, ?, ?, ?, ?)",
                                   ("wrong-scope", str(self.store.generation_id), "bad", str(workflow.workflow_id), "2026-11-08T12:00:00.000000Z"))
        with database(self.path) as connection:
            connection.execute("INSERT INTO workflow_aliases VALUES(?, ?, ?, ?, ?)",
                               ("wrong-scope", str(self.store.generation_id), "orphan", str(workflow.workflow_id), "2026-11-08T12:00:00.000000Z"))
        with self.assertRaises(WorkflowIntegrityError):
            WorkflowStore(self.path)

    def test_busy_writer_fails_with_a_bounded_error_then_can_retry(self):
        store = WorkflowStore(self.path, busy_timeout_ms=30)
        blocker = sqlite3.connect(self.path, isolation_level=None)
        try:
            blocker.execute("BEGIN IMMEDIATE")
            started = perf_counter()
            with self.assertRaises(WorkflowBusyError):
                store.create(scope="local", display_name="Blocked task")
            self.assertLess(perf_counter() - started, 2)
        finally:
            blocker.rollback()
            blocker.close()
        self.assertEqual(store.list_workflows(scope="local"), [])
        self.assertEqual(store.create(scope="local", display_name="Blocked task").revision, 1)

    def test_two_store_instances_cannot_claim_the_same_alias(self):
        other = WorkflowStore(self.path)
        barrier = threading.Barrier(2)

        def create(store):
            barrier.wait(timeout=2)
            try:
                return store.create(scope="local", display_name="Shared name")
            except WorkflowConflictError:
                return None

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(create, [self.store, other]))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(len(self.store.list_workflows(scope="local")), 1)

    def test_two_revisions_cannot_overwrite_one_another(self):
        workflow = self.create()
        other = WorkflowStore(self.path)
        barrier = threading.Barrier(2)

        def update(item):
            store, summary = item
            barrier.wait(timeout=2)
            try:
                return store.update(workflow.workflow_id, scope="local", expected_revision=1, summary=summary)
            except WorkflowRevisionError:
                return None

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(update, [(self.store, "first"), (other, "second")]))
        winner, = [result for result in results if result is not None]
        self.assertEqual(winner.revision, 2)
        self.assertEqual(self.store.get(workflow.workflow_id, scope="local"), winner)

    def test_missing_or_corrupt_storage_is_never_reported_as_empty(self):
        self.path.unlink()
        with self.assertRaises(WorkflowStorageError):
            self.store.list_workflows(scope="local")
        self.assertFalse(self.path.exists())
        self.path.write_bytes(b"not a SQLite database")
        with self.assertRaises(WorkflowStorageError):
            WorkflowStore(self.path)
        self.assertEqual(self.path.read_bytes(), b"not a SQLite database")

    def test_corrupt_workflow_fields_raise_instead_of_becoming_not_found(self):
        workflow = self.create()
        with database(self.path) as connection:
            connection.execute("UPDATE workflows SET last_activity_at='invalid timestamp'")
        with self.assertRaises(WorkflowIntegrityError):
            self.store.get(workflow.workflow_id, scope="local")

    def test_newer_or_incomplete_schemas_are_not_silently_repaired(self):
        with database(self.path) as connection:
            connection.execute("PRAGMA user_version=99")
        with self.assertRaises(WorkflowSchemaError):
            WorkflowStore(self.path)
        with database(self.path) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 99)
            connection.execute("PRAGMA user_version=1")
            connection.execute("DROP TRIGGER workflow_document_update")
        with self.assertRaises(WorkflowSchemaError):
            WorkflowStore(self.path)
        with database(self.path) as connection:
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name='workflow_document_update'").fetchone())

    def test_an_unrelated_database_is_left_unchanged(self):
        other = self.path.parent / "unrelated.db"
        with database(other) as connection:
            connection.execute("CREATE TABLE existing_data(value TEXT)")
            connection.execute("INSERT INTO existing_data VALUES('preserve me')")
        before = other.read_bytes()
        with self.assertRaises(WorkflowSchemaError):
            WorkflowStore(other)
        self.assertEqual(other.read_bytes(), before)

    def test_schema_initialization_is_transactional(self):
        path = self.path.parent / "interrupted.db"
        with patch.object(store_module, "SCHEMA_V1", (*store_module.SCHEMA_V1, "INVALID SQL")):
            with self.assertRaises(WorkflowStorageError):
                WorkflowStore(path)
        with database(path) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [])
        self.assertEqual(WorkflowStore(path).list_workflows(scope="local"), [])

    def test_old_handles_reject_a_changed_history_generation(self):
        with database(self.path) as connection:
            connection.execute("UPDATE store_state SET generation_id=?", (str(uuid4()),))
        with self.assertRaises(WorkflowGenerationError):
            self.store.list_workflows(scope="local")
        with self.assertRaises(WorkflowGenerationError):
            self.create()
        reopened = WorkflowStore(self.path)
        self.assertNotEqual(reopened.generation_id, self.store.generation_id)
        self.assertEqual(reopened.list_workflows(scope="local"), [])

    def test_fts5_requirement_fails_before_creating_state(self):
        path = self.path.parent / "unsupported" / "workflows.db"
        connection = Mock()
        connection.execute.side_effect = sqlite3.OperationalError("no such module: fts5")
        with patch.object(store_module.sqlite3, "connect", return_value=connection):
            with self.assertRaisesRegex(WorkflowConfigurationError, "FTS5"):
                WorkflowStore(path)
        connection.close.assert_called_once()
        self.assertFalse(path.exists())

    def test_validation_and_backwards_clock_do_not_create_invalid_metadata(self):
        workflow = self.create()
        self.now -= timedelta(days=1)
        updated = self.store.update(workflow.workflow_id, scope="local", expected_revision=1, purpose="new purpose")
        self.assertEqual(updated.last_activity_at, workflow.last_activity_at)
        for kwargs in ({"display_name": " "}, {"display_name": "Bad", "scope": ""}, {"display_name": "Bad", "aliases": "not a list"}):
            with self.assertRaises(ValueError):
                self.store.create(**{"scope": "local", **kwargs})
        for invalid in (0, True, -1):
            with self.assertRaises(ValueError):
                self.store.update(workflow.workflow_id, scope="local", expected_revision=invalid)
        with self.assertRaises(ValueError):
            replace(workflow, created_at=datetime(2026, 11, 8))
        self.assertEqual(len(self.store.list_workflows(scope="local")), 1)


class WorkflowStoreActivationTests(unittest.TestCase):
    def test_default_path_is_injected_and_import_does_not_activate_the_store(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(store_module, "get_data_dir", return_value=root):
                store = WorkflowStore()
            self.assertEqual(store.db_path, (root / "workflows.db").resolve())
            self.assertTrue(store.db_path.is_file())
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(os.environ, OPENPOKE_DATA_DIR=directory,
                               OPENROUTER_API_KEY="test-key", COMPOSIO_API_KEY="test-key")
            code = "from pathlib import Path; import os; import server.app; import server.services.workflows; assert not (Path(os.environ['OPENPOKE_DATA_DIR']) / 'workflows.db').exists()"
            result = subprocess.run([sys.executable, "-c", code], env=environment,
                                    cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
