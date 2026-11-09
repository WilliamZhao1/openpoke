# Legacy migration dry-run

This is the second slice of Phase 1. It inventories legacy state and produces a
reconciliation report. Applying migration, creating workflow/event mappings,
backups, and switching live writers remain separate steps.

## Why inspection comes first

Legacy services load themselves when `server` is imported. Some create missing
files, coerce roster entries into strings, skip malformed log lines, or turn
failed reads into empty state. Worker filenames also cannot distinguish names
that share a slug. Reusing those live services for inspection would hide
problems or change the inputs before they could be reviewed.

`migration.py` uses only the standard library, reads the original formats
directly, and constructs no live stores. It preserves every roster position and
exact string alias, exposes invalid entries and read failures, and leaves
ambiguous ownership unresolved. It allocates no new workflow or event IDs.

## Command

Run the file directly from the repository root, with an explicit existing data
directory. For example, in PowerShell:

```powershell
.\.venv\Scripts\python.exe .\server\services\workflows\migration.py --data-dir .\server\data --output .\migration-report.json
```

Use the actual `OPENPOKE_DATA_DIR` location if different. This standalone
command does not import application settings or read `.env`, and needs no API
credentials. Do not invoke it with `python -m server...`, which would initialize
the application package before running the command.

`--output` is optional; without it, JSON goes to stdout. A requested output must
be a new file outside the inspected root, with an existing parent directory.
The command refuses to overwrite an existing report or write inside the source
root. `--scope` defaults to `local` and labels the proposed destination scope.

Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | `review_ready`: no blocking issues detected; warnings may remain. |
| 2 | `blocked` report requiring reconciliation, or invalid CLI arguments. |
| 1 | Inspection could not run or the output could not be written. |

Both report statuses include `apply_supported: false`. The command has no apply
mode and does not open or initialize `workflows.db`.

## What the report contains

- `sources`: byte SHA-256, size, filesystem identity/modification metadata, and
  explicit available/missing/unavailable state for the roster, worker logs,
  conversation log, working-memory log, and trigger database sidecars. Missing
  expected worker logs are recorded as well. Missing optional files are not
  created; unavailable or malformed inputs block the report.
- `roster_entries`: every original array position, exact name, value type, and
  expected legacy log path. Non-string values are reported rather than coerced.
  Duplicate exact aliases and empty display names need reconciliation.
- `worker_logs` and `conversation`: streamed entry inventories with original
  byte offsets/lengths, line numbers, legacy parsed-entry indices, tags, raw
  timestamp strings, and decoded-payload hashes. Unparsed lines retain source
  locations and block the report. Noncanonical records and ambiguous Unicode
  line separators also block migration rather than silently changing indices.
  Logs retain first/latest request references for later metadata recovery.
- `working_memory`: summary and metadata references/hashes, recorded
  `last_index`/`updated_at`, the matching conversation boundary reference, and
  verification that the unsummarized tail matches the conversation. Duplicate
  summaries, invalid metadata, missing boundaries, and differing tails block
  the report. Summary text remains in its original source.
- `triggers`: exact trigger ID/name, alias resolution and roster positions,
  status, row fingerprints, and schema/logical-data fingerprints. Trigger
  payloads and errors are not copied into the report. Exact alias resolution
  is separate from whether that worker's history is unambiguous.
- `issues` and `counts`: structured diagnostic codes and source locations.
  Names are retained for reconciliation; conversation, request, summary, and
  tool-body text are omitted. The report is not an anonymized artifact.

For example, roster names `Alice / Lunch` and `Alice - Lunch` share
`execution_agents/alice-lunch.log`. The report contains a `slug_collision` issue
with both names, inventories the shared file once, and marks its owner
unresolved. It does not merge the workflows or duplicate the shared history.
A trigger named `Unknown worker` produces `trigger_owner_unresolved`; a
log without any matching roster alias produces `orphan_worker_log`.

Missing worker logs are warnings because a newly registered worker may not have
run yet. Possible truncation is also a warning: the legacy writer caps action
arguments and tool results, and inspection cannot reconstruct omitted text or
reliably distinguish every shortened response. Workflow status and purpose
remain unknown; request references support later source-backed recovery.

## Consistency and remaining work

The inspector never opens the original trigger database through SQLite. It
copies the main database and any WAL into a temporary directory, verifies the
copies against the captured hashes, and reads the scratch database. It does
not copy the shared-memory sidecar. This includes committed WAL data while
keeping SQLite recovery and shared-memory writes away from the original files.
A nonempty rollback journal blocks inspection instead of guessing its state.
The temporary directory is removed after inspection.

All captured source fingerprints and the discovered log set are rechecked at
the end. Detected changes invalidate the report. Unreadable inputs cannot be
certified unchanged. These checks are observational,
not an atomic snapshot across files and databases. Pause request processing,
schedulers, polling, and other writers before the future migration apply mode,
then rescan and validate against consistent backups. This slice does not manage
that maintenance window or produce a recoverable backup.

Next comes immutable source/event persistence and legacy-reference mappings.
Resumable apply mode, consistent backups, trigger/summary reconciliation,
activity records/cards, authoritative adapters, and startup feature gating must
be completed before live adoption. Existing application behavior is unchanged.

## Verification

`python server/tests/run_tests.py` passes all 119 tests, including 15 new dry-run
tests. Coverage includes repeated reports, byte/mtime/file-set preservation,
WAL-only commits, scratch cleanup, roster collisions/invalid entries, orphan
logs, unresolved triggers, entry offsets and parser parity, summary boundaries
and tails, source mutation, unreadable/corrupt inputs, CLI exit codes, and
overwrite protection. A guarded fresh process rejects application imports and
network connections. All inputs are synthetic and temporary.
