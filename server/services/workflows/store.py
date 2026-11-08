"""Explicitly opened local store; importing it never opens a workflow database."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Callable, Optional
from uuid import UUID, uuid4

from ...data_paths import get_data_dir
from .errors import (
    WorkflowBusyError, WorkflowConfigurationError, WorkflowConflictError,
    WorkflowGenerationError, WorkflowIntegrityError, WorkflowNotFoundError,
    WorkflowRevisionError, WorkflowSchemaError, WorkflowStorageError,
)
from .models import (
    Workflow, WorkflowAlias, WorkflowStatus, decode_timestamp, encode_timestamp,
    require_revision, require_text, utc_datetime,
)
from .schema import REQUIRED_TABLES, REQUIRED_TRIGGERS, SCHEMA_V1, SCHEMA_VERSION


_UNSET = object()


def probe_fts5():
    """Check the actual SQLite driver before opening or changing stored state."""
    connection = None
    try:
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE VIRTUAL TABLE fts_probe USING fts5(document)")
    except sqlite3.OperationalError as exc:
        if "no such module: fts5" in str(exc).lower():
            raise WorkflowConfigurationError(
                "Workflow storage requires SQLite FTS5. Install a Python/SQLite build "
                "with FTS5 enabled before enabling the workflow store."
            ) from exc
        raise WorkflowStorageError("Could not probe SQLite FTS5 support") from exc
    except sqlite3.Error as exc:
        raise WorkflowStorageError("Could not probe SQLite FTS5 support") from exc
    finally:
        if connection is not None:
            connection.close()


class WorkflowStore:
    """Backend persistence only; this is not a routing/admission tool handler.

    Each operation owns and closes its connection. Writes use short IMMEDIATE
    transactions; no model/network work belongs inside them. A cached generation
    prevents an older handle from silently attaching to replacement history.
    """

    def __init__(
        self, db_path: Optional[Path] = None, *, busy_timeout_ms: int = 250,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        if type(busy_timeout_ms) is not int or not 0 <= busy_timeout_ms <= 5000:
            raise ValueError("Workflow busy timeout must be between 0 and 5000 milliseconds")
        self.db_path = Path(db_path if db_path is not None else get_data_dir() / "workflows.db").expanduser().resolve()
        self.busy_timeout_ms = busy_timeout_ms
        self._clock = clock
        probe_fts5()
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise WorkflowStorageError("Could not prepare the workflow data directory") from exc
        self.generation_id = self._initialize()

    @contextmanager
    def _connection(self, *, create=False):
        connection = None
        try:
            # Normal reads/writes never recreate a missing database as empty state.
            uri = self.db_path.as_uri() + ("?mode=rwc" if create else "?mode=rw")
            connection = sqlite3.connect(uri, uri=True, timeout=self.busy_timeout_ms / 1000, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
                raise WorkflowConfigurationError("SQLite foreign-key enforcement is required for workflow storage")
            connection.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
            yield connection
        except sqlite3.Error as exc:
            message = str(exc).lower()
            code = getattr(exc, "sqlite_errorcode", None)
            busy = isinstance(code, int) and (code & 0xFF) in {5, 6}  # SQLITE_BUSY / SQLITE_LOCKED, including extended codes.
            if busy or any(text in message for text in (
                "database is locked", "database table is locked", "database schema is locked", "database is busy",
            )):
                raise WorkflowBusyError("Workflow storage is busy; retry this operation later") from exc
            if isinstance(exc, sqlite3.IntegrityError):
                raise WorkflowIntegrityError("Workflow storage constraint failed") from exc
            raise WorkflowStorageError("Workflow database operation failed") from exc
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _rollback(connection):
        try:
            connection.rollback()
        except sqlite3.Error:
            pass  # Preserve the original error; closing the connection also rolls back.

    def _initialize(self) -> UUID:
        with self._connection(create=True) as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version > SCHEMA_VERSION:
                    raise WorkflowSchemaError("Workflow schema is newer than this application; upgrade the application before opening it")
                if version == 0:
                    existing = connection.execute(
                        "SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND type IN ('table', 'view', 'trigger')"
                    ).fetchall()
                    if existing:
                        raise WorkflowSchemaError("Refusing to initialize an unrecognized database; use a separate workflow database path")
                    for statement in SCHEMA_V1:
                        connection.execute(statement)
                    generation = str(uuid4())
                    connection.execute("INSERT INTO store_state VALUES(1, ?)", (generation,))
                    connection.execute("INSERT INTO schema_migrations VALUES(?, ?)", (SCHEMA_VERSION, encode_timestamp(self._clock())))
                    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                elif version != SCHEMA_VERSION:
                    raise WorkflowSchemaError("No supported workflow schema upgrade path")
                self._validate_schema(connection)
                generation = UUID(connection.execute("SELECT generation_id FROM store_state WHERE singleton=1").fetchone()[0])
                connection.commit()
            except BaseException:
                self._rollback(connection)
                raise
            # Change persistent journal settings only after recognizing our schema.
            if connection.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() != "wal":
                raise WorkflowConfigurationError("Workflow storage requires a local filesystem supporting SQLite WAL mode")
            return generation

    @staticmethod
    def _validate_schema(connection):
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        triggers = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        if not REQUIRED_TABLES.issubset(tables) or not REQUIRED_TRIGGERS.issubset(triggers):
            raise WorkflowSchemaError("Workflow schema is incomplete; restore or reconcile it before use")
        if [row[0] for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version")] != [SCHEMA_VERSION]:
            raise WorkflowSchemaError("Workflow schema version and migration history disagree")
        states = connection.execute("SELECT singleton, generation_id FROM store_state").fetchall()
        if len(states) != 1 or states[0][0] != 1:
            raise WorkflowIntegrityError("Workflow generation metadata is missing or inconsistent")
        try:
            UUID(states[0][1])
        except (ValueError, TypeError, AttributeError) as exc:
            raise WorkflowIntegrityError("Workflow generation ID is invalid") from exc
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise WorkflowIntegrityError("Workflow foreign-key validation failed")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise WorkflowIntegrityError("Workflow database integrity validation failed")
        # A declared version is not permission to silently repair missing columns.
        connection.execute("SELECT workflow_id, scope, generation_id, display_name, purpose, summary, status, created_at, last_activity_at, archived_at, revision FROM workflows LIMIT 0")
        connection.execute("SELECT scope, generation_id, alias, workflow_id, created_at FROM workflow_aliases LIMIT 0")
        connection.execute("SELECT doc_id, workflow_id, scope, generation_id, document FROM workflow_search_documents LIMIT 0")
        connection.execute("SELECT rowid, document FROM workflow_search_fts LIMIT 0")

    @contextmanager
    def _transaction(self, *, write=False):
        with self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                if connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                    raise WorkflowSchemaError("Workflow schema changed; reopen with a compatible application")
                row = connection.execute("SELECT generation_id FROM store_state WHERE singleton=1").fetchone()
                if row is None or row[0] != str(self.generation_id):
                    raise WorkflowGenerationError("Workflow history generation changed; reopen the store")
                yield connection
                connection.commit()
            except BaseException:
                self._rollback(connection)
                raise

    @staticmethod
    def _workflow(row):
        try:
            return Workflow(
                workflow_id=row["workflow_id"], scope=row["scope"], generation_id=row["generation_id"],
                display_name=row["display_name"], purpose=row["purpose"], summary=row["summary"],
                status=row["status"], created_at=decode_timestamp(row["created_at"]),
                last_activity_at=decode_timestamp(row["last_activity_at"]),
                archived_at=decode_timestamp(row["archived_at"]) if row["archived_at"] else None,
                revision=row["revision"],
            )
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise WorkflowIntegrityError("Stored workflow data is invalid") from exc

    def _find(self, connection, workflow_id, scope):
        return connection.execute(
            "SELECT * FROM workflows WHERE workflow_id=? AND scope=? AND generation_id=?",
            (str(workflow_id), scope, str(self.generation_id)),
        ).fetchone()

    def _required(self, connection, workflow_id, scope, expected_revision=None):
        row = self._find(connection, workflow_id, scope)
        if row is None:
            raise WorkflowNotFoundError("Workflow does not exist in this scope/generation")
        workflow = self._workflow(row)
        if expected_revision is not None and workflow.revision != expected_revision:
            raise WorkflowRevisionError("Workflow revision changed; inspect current state before retrying")
        return workflow

    def _put_alias(self, connection, workflow, alias, timestamp):
        owner = connection.execute(
            "SELECT workflow_id FROM workflow_aliases WHERE scope=? AND generation_id=? AND alias=?",
            (workflow.scope, str(self.generation_id), alias),
        ).fetchone()
        if owner:
            if owner[0] != str(workflow.workflow_id):
                raise WorkflowConflictError("Alias is already assigned to another workflow in this scope")
            return False
        connection.execute("INSERT INTO workflow_aliases VALUES(?, ?, ?, ?, ?)",
                           (workflow.scope, str(self.generation_id), alias, str(workflow.workflow_id), timestamp))
        return True

    def _refresh_document(self, connection, workflow):
        aliases = [row[0] for row in connection.execute(
            "SELECT alias FROM workflow_aliases WHERE workflow_id=? AND scope=? AND generation_id=? ORDER BY alias COLLATE BINARY",
            (str(workflow.workflow_id), workflow.scope, str(self.generation_id)),
        )]
        document = "\n".join(dict.fromkeys([workflow.display_name, workflow.purpose, workflow.summary, *aliases]))
        connection.execute(
            """INSERT INTO workflow_search_documents(workflow_id, scope, generation_id, document)
                VALUES(?, ?, ?, ?) ON CONFLICT(workflow_id) DO UPDATE SET
                scope=excluded.scope, generation_id=excluded.generation_id, document=excluded.document""",
            (str(workflow.workflow_id), workflow.scope, str(self.generation_id), document),
        )

    def create(self, *, scope, display_name, purpose="", summary="", status=WorkflowStatus.OPEN, aliases=(), workflow_id=None):
        timestamp = utc_datetime(self._clock())
        workflow = Workflow(
            workflow_id=UUID(str(workflow_id)) if workflow_id is not None else uuid4(),
            scope=scope, generation_id=self.generation_id, display_name=display_name,
            purpose=purpose, summary=summary, status=status,
            created_at=timestamp, last_activity_at=timestamp, archived_at=None, revision=1,
        )
        if isinstance(aliases, (str, bytes)):
            raise ValueError("Aliases must be a collection of exact strings")
        names = tuple(dict.fromkeys([display_name, *(require_text(alias) for alias in aliases)]))
        with self._transaction(write=True) as connection:
            if connection.execute("SELECT 1 FROM workflows WHERE workflow_id=?", (str(workflow.workflow_id),)).fetchone():
                raise WorkflowConflictError("Workflow ID is already present")
            stamp = encode_timestamp(timestamp)
            connection.execute("INSERT INTO workflows VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 1)", (
                str(workflow.workflow_id), scope, str(self.generation_id), display_name, purpose, summary,
                workflow.status.value if workflow.status is not None else None, stamp, stamp,
            ))
            for name in names:
                self._put_alias(connection, workflow, name, stamp)
            self._refresh_document(connection, workflow)
        return workflow

    def get(self, workflow_id, *, scope):
        identifier = UUID(str(workflow_id))
        require_text(scope, nonempty=True)
        with self._transaction() as connection:
            row = self._find(connection, identifier, scope)
            return self._workflow(row) if row is not None else None

    def get_by_alias(self, alias, *, scope):
        require_text(alias)
        require_text(scope, nonempty=True)
        with self._transaction() as connection:
            row = connection.execute(
                """SELECT w.* FROM workflows w JOIN workflow_aliases a
                    ON w.workflow_id=a.workflow_id AND w.scope=a.scope AND w.generation_id=a.generation_id
                    WHERE a.scope=? AND a.generation_id=? AND a.alias=?""",
                (scope, str(self.generation_id), alias),
            ).fetchone()
            return self._workflow(row) if row is not None else None

    def list_workflows(self, *, scope, limit=20, after_id=None):
        require_text(scope, nonempty=True)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Workflow page limit must be between 1 and 100")
        after = str(UUID(str(after_id))) if after_id is not None else ""
        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM workflows WHERE scope=? AND generation_id=? AND workflow_id>? ORDER BY workflow_id LIMIT ?",
                (scope, str(self.generation_id), after, limit),
            ).fetchall()
            return [self._workflow(row) for row in rows]

    def list_aliases(self, workflow_id, *, scope):
        identifier = UUID(str(workflow_id))
        require_text(scope, nonempty=True)
        with self._transaction() as connection:
            self._required(connection, identifier, scope)
            rows = connection.execute(
                "SELECT * FROM workflow_aliases WHERE workflow_id=? AND scope=? AND generation_id=? ORDER BY alias COLLATE BINARY",
                (str(identifier), scope, str(self.generation_id)),
            ).fetchall()
            try:
                return [WorkflowAlias(identifier, scope, self.generation_id, row["alias"], decode_timestamp(row["created_at"])) for row in rows]
            except (ValueError, TypeError, AttributeError) as exc:
                raise WorkflowIntegrityError("Stored alias data is invalid") from exc

    def _write_metadata(self, connection, workflow):
        stamp = encode_timestamp(workflow.last_activity_at)
        cursor = connection.execute(
            """UPDATE workflows SET display_name=?, purpose=?, summary=?, status=?, last_activity_at=?, revision=?
                WHERE workflow_id=? AND scope=? AND generation_id=? AND revision=?""",
            (workflow.display_name, workflow.purpose, workflow.summary,
             workflow.status.value if workflow.status is not None else None, stamp, workflow.revision,
             str(workflow.workflow_id), workflow.scope, str(self.generation_id), workflow.revision - 1),
        )
        if cursor.rowcount != 1:
            raise WorkflowRevisionError("Workflow revision changed; inspect current state before retrying")
        self._refresh_document(connection, workflow)

    def update(self, workflow_id, *, scope, expected_revision, display_name=None, purpose=None, summary=None, status=_UNSET):
        identifier = UUID(str(workflow_id))
        require_text(scope, nonempty=True)
        require_revision(expected_revision)
        with self._transaction(write=True) as connection:
            current = self._required(connection, identifier, scope, expected_revision)
            fields = {name: value for name, value in (("display_name", display_name), ("purpose", purpose), ("summary", summary)) if value is not None}
            if status is not _UNSET:
                fields["status"] = status
            updated = replace(current, **fields)
            if updated == current:
                return current
            updated = replace(updated, revision=current.revision + 1,
                              last_activity_at=max(current.last_activity_at, utc_datetime(self._clock())))
            self._put_alias(connection, updated, updated.display_name, encode_timestamp(updated.last_activity_at))
            self._write_metadata(connection, updated)
            return updated

    def add_alias(self, workflow_id, alias, *, scope, expected_revision):
        identifier = UUID(str(workflow_id))
        require_text(alias)
        require_text(scope, nonempty=True)
        require_revision(expected_revision)
        with self._transaction(write=True) as connection:
            current = self._required(connection, identifier, scope, expected_revision)
            timestamp = max(current.last_activity_at, utc_datetime(self._clock()))
            if not self._put_alias(connection, current, alias, encode_timestamp(timestamp)):
                return current
            updated = replace(current, revision=current.revision + 1, last_activity_at=timestamp)
            self._write_metadata(connection, updated)
            return updated

    def rebuild_search_index(self):
        """Rebuild the derived metadata/index from identities and exact aliases."""
        with self._transaction(write=True) as connection:
            count = 0
            for row in connection.execute("SELECT * FROM workflows WHERE generation_id=?", (str(self.generation_id),)):
                self._refresh_document(connection, self._workflow(row))
                count += 1
            connection.execute("INSERT INTO workflow_search_fts(workflow_search_fts) VALUES('rebuild')")
            return count
