# Workflow storage foundation

This is the first slice of Phase 1 in the execution-agent overload plan.
`WorkflowStore` is backend persistence, not a model-visible creation or routing
handler. The application still uses the legacy stores. Importing this package
does not open a workflow database; explicitly constructing a store does.

## Motivation and behavior

The legacy roster identifies workers by name, and worker log paths use a
normalized filename slug. For example, `Alice / Lunch` and `Alice - Lunch`
produce the same legacy slug. A name also needs to remain resolvable after a
display-name change. The new store assigns immutable UUIDs, retains exact name
aliases, and keeps both independent of display names and filenames.

Schema version 1 contains workflow metadata, exact aliases, generation metadata,
schema migration history, compact search documents, and their FTS5 index.
Workflow records are frozen dataclasses with scope, purpose, summary, status,
UTC timestamps, archive timestamp, and revision. Workflow statuses are `open`,
`waiting_for_approval`, `waiting_for_external_event`, `completed`, and `cancelled`.
`None` means explicitly unknown historical state; it does not mean completed or
archived. A run failure is not a workflow status.

Aliases preserve case, Unicode, whitespace, and even empty historical names.
Display names and scopes must be nonempty. A display name is also reserved as an
alias. An alias already owned by another workflow in the same scope/generation
raises a conflict; the persistence layer never silently reuses or merges it.
This is exact identity protection, not semantic deduplication or an ownership
decision. Different scopes may use the same name.

## Example

Use this inside the configured backend or the isolated test runner. Importing
`server` initializes existing application services, so configure the data root
before importing it. For standalone experimentation, use a disposable root as
described in the repository README.

```python
from pathlib import Path
from server.services.workflows import WorkflowStore

store = WorkflowStore(Path("disposable-state/workflows.db"))
lunch = store.create(
    scope="local", display_name="Alice lunch", purpose="Arrange lunch with Alice",
)
renamed = store.update(
    lunch.workflow_id, scope="local", expected_revision=lunch.revision,
    display_name="Alice birthday lunch",
)
assert renamed.workflow_id == lunch.workflow_id
assert renamed.revision == 2
assert store.get_by_alias("Alice lunch", scope="local") == renamed
assert store.get_by_alias("Alice birthday lunch", scope="local") == renamed

reopened = WorkflowStore(store.db_path)
assert reopened.get(lunch.workflow_id, scope="local") == renamed
```

Updates and alias additions require `expected_revision`. Reusing revision 1
after the rename raises `WorkflowRevisionError`, allowing the caller to inspect
the newer state before retrying. A no-op leaves the revision unchanged.
`get` and `get_by_alias` return `None` only for absence in the requested scope
and current generation. Storage failures raise typed exceptions from `errors.py`.
`list_workflows` uses UUID keyset paging with a maximum page size of 100 and
does not exclude completed or archived workflows.

## Why the store works this way

- The default path is `get_data_dir() / "workflows.db"`; explicit paths support
  isolated tests. The constructor probes FTS5 in memory before creating the
  persistent database. Missing support produces an actionable configuration
  error. No dependency was added.
- Each operation opens and closes its own connection and enables foreign keys.
  Writes use short `BEGIN IMMEDIATE` transactions and WAL mode on a supporting
  local filesystem. The native busy timeout defaults to 250 ms, accepts 0–5,000
  ms, and raises `WorkflowBusyError` on contention instead of retrying forever.
  Model calls and network operations do not belong inside these transactions.
- Workflow changes, aliases, search documents, and FTS trigger updates commit
  together. An index failure rolls back the metadata change too. Documents
  currently contain display name, purpose, summary, and aliases. The explicit
  `rebuild_search_index` operation regenerates this projection from stored
  metadata without scanning legacy logs. Public lookup/ranking and richer
  source-backed cards are later steps.
- Schema initialization is transactional and repeatable. Unknown, newer, or
  incomplete databases are rejected rather than overwritten or silently
  repaired. Version 1 currently supports initializing an empty database, not
  upgrading another application schema. Existing handles never recreate a
  missing database during normal reads or writes.
- The constructor caches a history-generation UUID; every operation verifies
  it. A changed generation raises `WorkflowGenerationError`. This prepares for
  later history-clear protection; it does not yet implement clearing history
  or checking callbacks. Activity timestamps never move backward on updates.

The index follows SQLite's [external-content FTS5 maintenance
contract](https://www.sqlite.org/fts5.html#external_content_tables), and foreign
keys are enabled on each connection as required by [SQLite foreign-key
enforcement](https://www.sqlite.org/foreignkeys.html#fk_enable).

## Verification and remaining work

Run `python server/tests/run_tests.py` from the repository root. All 119 tests
pass. The 26 storage tests in `test_workflow_store.py` cover restart
persistence, aliases and slug collisions, scoped access, revisions, concurrent
writers, index rollback/rebuild, foreign keys, bounded lock handling, schema
rollback/rejection, missing/corrupt data, generation changes, FTS5 failure, and
import/data-root isolation. Tests use disposable state and no live providers.

The [non-destructive migration dry-run](MIGRATION.md) is now available as a
standalone CLI and has 15 additional tests. Applying migration still requires
source/event persistence, consistent backups, resumable mappings,
trigger/summary reconciliation, and validation.
Activity records/cards, authoritative compatibility adapters, startup ordering,
and feature-gated adoption remain unfinished Phase 1 work. No migration apply,
history-clear operation, model tool, or live routing path is enabled here.
