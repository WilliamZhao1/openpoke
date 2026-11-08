"""Transactional schema migrations. Legacy file import is a separate operation."""

SCHEMA_VERSION = 1

# Execute individual statements inside the caller's transaction. executescript()
# may commit a pending transaction before running the script.
SCHEMA_V1 = (
    """CREATE TABLE schema_migrations (
        version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
    )""",
    """CREATE TABLE store_state (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        generation_id TEXT NOT NULL UNIQUE CHECK (length(generation_id) = 36)
    )""",
    """CREATE TABLE workflows (
        workflow_id TEXT PRIMARY KEY NOT NULL CHECK (length(workflow_id) = 36),
        scope TEXT NOT NULL CHECK (length(trim(scope)) > 0),
        generation_id TEXT NOT NULL REFERENCES store_state(generation_id),
        display_name TEXT NOT NULL CHECK (length(trim(display_name)) > 0),
        purpose TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '',
        status TEXT CHECK (status IN ('open', 'waiting_for_approval',
            'waiting_for_external_event', 'completed', 'cancelled')),
        created_at TEXT NOT NULL, last_activity_at TEXT NOT NULL,
        archived_at TEXT,
        revision INTEGER NOT NULL CHECK (typeof(revision) = 'integer' AND revision >= 1),
        UNIQUE (workflow_id, scope, generation_id),
        CHECK (last_activity_at >= created_at)
    )""",
    """CREATE INDEX workflow_scope_page
        ON workflows(scope, generation_id, workflow_id)""",
    """CREATE TABLE workflow_aliases (
        scope TEXT NOT NULL, generation_id TEXT NOT NULL,
        alias TEXT COLLATE BINARY NOT NULL, workflow_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (scope, generation_id, alias),
        FOREIGN KEY (workflow_id, scope, generation_id)
            REFERENCES workflows(workflow_id, scope, generation_id) ON DELETE CASCADE
    )""",
    """CREATE INDEX workflow_alias_owner
        ON workflow_aliases(workflow_id, scope, generation_id)""",
    """CREATE TABLE workflow_search_documents (
        doc_id INTEGER PRIMARY KEY, workflow_id TEXT NOT NULL UNIQUE,
        scope TEXT NOT NULL, generation_id TEXT NOT NULL, document TEXT NOT NULL,
        FOREIGN KEY (workflow_id, scope, generation_id)
            REFERENCES workflows(workflow_id, scope, generation_id) ON DELETE CASCADE
    )""",
    """CREATE INDEX workflow_document_scope
        ON workflow_search_documents(scope, generation_id, workflow_id)""",
    """CREATE VIRTUAL TABLE workflow_search_fts USING fts5(
        document, content='workflow_search_documents', content_rowid='doc_id'
    )""",
    """CREATE TRIGGER workflow_document_insert AFTER INSERT ON workflow_search_documents BEGIN
        INSERT INTO workflow_search_fts(rowid, document) VALUES(new.doc_id, new.document);
    END""",
    """CREATE TRIGGER workflow_document_delete AFTER DELETE ON workflow_search_documents BEGIN
        INSERT INTO workflow_search_fts(workflow_search_fts, rowid, document)
            VALUES('delete', old.doc_id, old.document);
    END""",
    """CREATE TRIGGER workflow_document_update AFTER UPDATE ON workflow_search_documents BEGIN
        INSERT INTO workflow_search_fts(workflow_search_fts, rowid, document)
            VALUES('delete', old.doc_id, old.document);
        INSERT INTO workflow_search_fts(rowid, document) VALUES(new.doc_id, new.document);
    END""",
)

REQUIRED_TABLES = {
    "schema_migrations", "store_state", "workflows", "workflow_aliases",
    "workflow_search_documents", "workflow_search_fts",
}
REQUIRED_TRIGGERS = {
    "workflow_document_insert", "workflow_document_delete", "workflow_document_update",
}
