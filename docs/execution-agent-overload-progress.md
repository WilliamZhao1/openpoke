# Execution Agent Overload: Implementation Progress

Updated: 2026-11-08

The reduced-scope revision of
[`execution-agent-overload-implementation-plan.md`](execution-agent-overload-implementation-plan.md)
supersedes the earlier storage/migration roadmap. Phase 1 now means bounded worker
discovery; Phase 2 means bounded context/recovery; Phase 3 means focused comparison
and release. Revised Phase 1 discovery is implemented behind the development
strategy setting. Phase 2 has provider preflight, live full-content capture, and
bounded model-visible source recovery. Bounded history construction is next.
No backup/import phase precedes it.

Phase 0's data paths, isolated runner, telemetry, fixtures, fake Gmail, evaluation
command, and saved model-free baseline remain in active use. The unused workflow,
migration, and event-storage code from Steps 5–7 is preserved with its dedicated
tests/docs in a [verified deferred checkpoint](../deferred/execution-agent-overload-storage-2026-11-08/README.md)
and removed from the active implementation. The active suite now has 155 tests.

Each implementation step is reported with its motivation, old behavior, new
behavior, design rationale, validation, and any remaining limits or plan gaps.
Steps 1–7 and the earlier alignment review below are historical records under
the previous roadmap. Their phase numbers, next-step notes, test counts, and
workflow-package paths describe that implementation at the time; they are not
current delivery instructions. Deferred files are available inside the checkpoint.

## Step 1: Isolated data paths (complete)

**Motivation:** Migration, history clearing, and growing evaluation catalogs
need disposable state. Tests must not load a real mailbox connection or erase
the user's history while exercising those operations.

**Old behavior:** Each persistent service independently constructed a path under
`server/data/`. Several stores read or created files during imports, before tests
could patch service dependencies.

**New behavior:** `server/data_paths.py` resolves `Settings.data_dir`, configured
with `OPENPOKE_DATA_DIR` and defaulting to the original `server/data/` root.
Execution roster/logs, conversation/working-memory logs, trigger SQLite storage,
Gmail connection/seen-message state, and timezone preferences use that helper.
Relative paths resolve from the process working directory; `~` is expanded and
empty environment values are rejected. Configure the root before imports and
restart the backend after changes; the setting does not migrate files.

`server/tests/run_tests.py` configures a disposable root and dummy integration
credentials before test discovery imports the application. README and
`.env.example` document the setting and the test command.

**Why this approach:** One shared root keeps every participating store in the
same environment, while preserving the existing default locations and file
formats. Selecting the root before test discovery matters because importing
`server` initializes application services; patching dependencies in a test's
setup can happen too late. Fresh-process checks exercise that initialization
and actual disk reloads. Existing store constructors still accept explicit
paths for narrower tests. This provides isolation without rewriting service
lifecycle management ahead of its planned phase.

**Verification:** `.venv\Scripts\python.exe server/tests/run_tests.py` passed all
23 tests: the 18 existing tests and 5 new data-path tests. New coverage includes
the legacy default, environment overrides, path expansion, invalid empty values,
and fresh-process persistence across all configured stores. The integration
test verifies two independent roots and clearing one without affecting the
other; it rejects socket connections. No live Gmail or model calls were used.
`git diff --check` passed for the tracked changes.

## Step 2: Observability and correlation IDs (complete)

The original step was implemented and verified. Step 2b below completes the
observation-availability/provenance contract added in the revised plan.

**Motivation:** Later routing/context changes need a comparable baseline. We
must account for work in inner agents and callbacks, distinguish a successful
provider call from a successful user task, and avoid treating early failure or
missing usage as evidence of efficiency.

**Old behavior:** Model requests returned provider JSON without a standard
record of component-level usage, elapsed time, or failure categories. Workers
had local batch/request bookkeeping, but chat, callbacks, reminders, and Gmail
notifications had no common correlation path.

**New behavior:** `server/observability.py` adds immutable task-local trace
scopes and structured JSON events through the existing logger. Backend request,
turn, batch, run, model-call, and trigger identifiers link accepted chat work to
dispatch, tool outcomes, worker callbacks, and stored user-visible replies.
Callbacks have their own turn IDs. A combined legacy batch links all of its
originating traces instead of attributing the result to the last finisher.

All five model-calling components report provider input/output usage, elapsed
time, outcome, and a fixed failure category. Missing/invalid usage stays unknown
(`null`); zero is preserved. Prompts, email content, worker names, tool inputs
and outputs, credentials, and error text are excluded from telemetry. Model
payloads, output limits, routing, and batching behavior remain the baseline.
Trace IDs are observational; durable identities/recovery remain later phases.
See `observability.md` for the schema, examples, and event semantics.

**Why this approach:** The shared provider client observes all five current
model-calling components in one place. Immutable `ContextVar` scopes preserve
correlation when asyncio tasks spawn and interleave, without putting trace IDs
in prompts or threading new metadata arguments through every tool. Request,
turn, run, and batch IDs distinguish an initial turn from later worker replies;
combined batches link all contributing origins. The existing logger provides
evidence without introducing a second database before the storage phase.
Monotonic timing measures durations reliably, and provider-reported usage
avoids presenting guesses as measured counts. Metadata-only events limit
content exposure, and a failing telemetry sink preserves the operation's
original outcome. These observational IDs do not authorize routing or replace
the durable identity/state work in later phases.

**Verification:** `.venv\Scripts\python.exe server/tests/run_tests.py` passes
all 41 tests: the existing 23 plus 18 new tests. Coverage includes model-free
chat, trigger, Gmail, concurrent-trace,
combined-batch, component-label, usage, failure, and cancellation checks. Tests
also verify unchanged payloads/output limits, sensitive-content exclusion, and
preserved outcomes when the telemetry sink fails. No live model or Gmail calls
were used. `git diff --check` passed.

## Alignment review against the revised plan

Reviewed on 2026-11-08. The completed work remains compatible with the revised
architecture and delivery order. The initial audit identified the observation
gap below; Step 2b subsequently closed it. Phase 0 as a whole remains in progress.

| Plan requirement | Current alignment |
| --- | --- |
| Phase 0 isolated storage | Aligned: helper, default compatibility, all existing stores, temporary test runner, restart/clear isolation tests. |
| Phase 0 usage, timing, failures, and correlation | Implemented: all five model callers, chat, worker callbacks, triggers, and Gmail notifications. Routing and model/output-token configuration retain baseline behavior. |
| Phase 0 explicit observation availability and mock/live provenance | Aligned after Step 2b: per-observation four-state availability, fixed reasons, provenance, and transport-bound mock/live labels are present in schema-2 log evidence. The evaluation harness will preserve them in reports. |
| Expanded Phase 0 fixtures and controlled comparisons | Fixtures/comparison definitions implemented in Step 3. Step 4 captures the legacy baseline and scripted trace with explicit availability/provenance. Actual comparisons against later routing strategies remain unexecuted. |
| Phase 1 activity records and rebuildable cards | Future work: use source-linked outcomes, explicit obligation transitions, and revisions when implementing storage/migration. |
| Phase 2 intent isolation and enforced routing decisions | Future work: bind decisions to current intent, scope, generation, and revisions; recover or abstain on ambiguity/failure. Current trace IDs are not those decisions. |
| Phase 7 graph retrieval experiment | Future work after Phases 0-5 and the frozen baseline; Phase 6 remains optional and independent. |

**Follow-up identified by the audit (completed in Step 2b):** Add `available`, `inferred`, `unavailable`, and
`not_applicable` observation states, with safe reasons/provenance and separate
mock/live labels. Attach availability to individual observations: elapsed time
can be directly available while provider usage is missing in the same event.
Keep measurement availability separate from task success, retrieval status,
and execution source. A token count observed from a mock response is still mock
evidence, even though its value was directly observed. Do not infer cost or
confidence when the required evidence is absent.

**Review validation:** Re-ran `.venv\Scripts\python.exe server/tests/run_tests.py`:
all 41 current tests pass with isolated storage and mocked providers. Those
tests verify the implemented behavior; they do not establish compliance with
the new availability/provenance contract. No runtime code was changed in this
alignment review. The implementation-plan document was preserved.

## Step 2b: Explicit observation availability and provenance (complete)

**Motivation:** A missing measurement, an observed zero, a derived value, and a
metric that does not apply have different meanings in comparisons. A fabricated
provider response cannot support a claim about real provider usage or latency.
The revised Phase 0 requires these distinctions in recorded evidence.

**Old behavior:** Telemetry included scalar usage values, `null` for unknown
counts, and a `usage_complete` boolean. It had no explicit availability or
source mode. Tests patched the HTTP client independently of telemetry.

**New behavior:** Schema-2 events preserve the original scalar fields and add
typed observations with `available`, `inferred`, `unavailable`, or
`not_applicable` availability; fixed source/reason enums; source mode; and
derivation evidence. Missing/invalid counts remain null and actual zero counts
remain zero. `usage_complete` is explicitly derived from both token
observations. Timing can be available even when usage is unavailable; an
observed provider-error payload can also contain available usage.

`use_mock_provider(httpx.MockTransport(...))` binds a provider transport and its
mock label together. The normal transport is labeled live; clock/runtime
observations are local. Tasks inherit mock scope, nested scopes restore it,
and a mock failure does not select a live transport. Existing model-response
tests now use this interface.

**Why this approach:** Availability belongs to each measurement because an
event can contain several evidence states. Immutable typed observations reject
unsupported inferences and arbitrary reason text; named evidence must refer to
metrics in the same event. Transport selection determines the provider label,
avoiding a loose global flag that could mislabel a mixed evaluation. The
existing task-local scope mechanism handles asynchronous propagation. Keeping
the scalar fields supports current consumers while the schema version makes
the richer contract explicit. Provider payloads, configured output limits,
routing, and retry behavior retain their baseline contracts.

**Verification:** `.venv\Scripts\python.exe server/tests/run_tests.py` passed all
49 tests, including the existing 41 and 8 additional tests. Checks cover JSON
serialization of all four states, zero and partial usage, safe missing-data
reasons, derivation constraints, available usage on failed calls, nested/task
mock scopes, rejection of invalid mock transports, and no live fallback. The
existing callback, provider failure, cancellation, content-exclusion, and
payload/limit checks also pass. `git diff --check` passed. No live provider or
email calls were made.

**Remaining limits:** Historical schema-1 logs cannot gain missing provenance
retroactively. This step supplies structured log evidence; preserving it in
saved evaluation reports and labeling future scorers belong to the upcoming
harness/adapters. Call success remains separate from end-task correctness.

## Step 3: Fixed catalogs and deterministic fake Gmail (complete)

**Motivation:** Later discovery changes need reproducible known-owner,
new-work, and ambiguous-owner inputs. Task correctness must be scored from
actual tool effects rather than worker prose, including exact draft bodies,
mailbox/thread identity, and uncertain or duplicate sends.

**Old behavior:** Tests used small ad hoc mocks for individual Gmail calls.
There was no shared, frozen retrieval catalog, labeled scenario set, or
stateful mailbox for inspecting effects across several operations.

**New behavior:** `server/tests/fixtures/` contains seven core workflows,
deterministic catalogs of 100/1,000/10,000 records plus an empty catalog,
fourteen labeled tuning/held-out cases, and predeclared one-factor comparison
rows. Cases cover both Alice workflows, dormant ownership, genuinely new work,
alternating topics, pronoun/draft follow-ups, competing drafts, stale cards,
near ties, lookup failure/partial coverage, exact references, and multiple
owners. Source inputs and generated catalogs have frozen SHA-256 checksums.

The local Gmail backend supplies two account-qualified mailboxes, deliberately
reused provider IDs, exact draft/body/recipient evidence, contacts, pagination,
a fixed clock, deterministic new IDs, and before/after failure injection. It
binds under the shared Composio service so the public Gmail tools and email
search/parser use their actual adapters. Calls and effects explicitly record
mock provenance. Runtime source files and routing behavior were not changed.

**Why this approach:** A compact core plus deterministic distractors keeps
large catalogs reviewable while frozen checksums detect input drift. Gold
owners/actions stay separate from model metadata to prevent answer leakage.
Scripted lookup/ranking inputs are labeled controls, not measured retrieval
results. Comparison rows separate discovery, richer metadata, decision checks,
and an optional ranker. Binding the fake below the service avoids duplicating
adapter behavior, while recording requested effects without manufacturing
approvals or deduplication exposes application mistakes. Unknown queries and
resources fail visibly instead of masquerading as successful empty results.

**Verification:** `.venv\Scripts\python.exe server/tests/run_tests.py` passed all
70 tests, including the existing 49 and 21 new tests. Checks include fixed
catalog hashes/IDs, case coverage, account-qualified resource mappings,
separate gold labels, comparison controls, and the unchanged full-roster prompt.
Fake Gmail tests exercise all nine public tools and internal search through
real adapters; verify exact content/recipients, pagination, clock advancement,
repeatable effects, cross-account isolation, error propagation, and uncertainty
before/after writes. Socket connections are rejected in fake Gmail tests.
No live email or model calls were used.

**Remaining limits:** The fake implements the documented checkout tool subset,
not all Gmail/Composio APIs or OAuth. Scenario labels do not prove current
routing/approval/lifecycle correctness. Model-free evaluation execution,
sanitized saved evidence, and provider/configuration manifests are the next
step. Fixture use and examples are documented in `server/tests/fixtures/README.md`.

## Step 4: Executable harness and saved baseline evidence (complete)

**Motivation:** Later changes need a reproducible reference and evidence that
the measurement/grading pipeline observes actual requests, identities, and tool
effects. A scripted success cannot establish real routing quality, and missing
usage/cost must not make a baseline look artificially efficient.

**Old behavior:** Frozen fixtures and tracing existed, but there was no
standalone evaluation command, pinned public model/configuration manifest,
saved input/trace bundle, or durable record of full-roster prompt growth.

**New behavior:** `evals/agent_overload/run.py` bootstraps disposable storage
and dummy credentials before importing the application, blocks network connects,
and writes a new evidence directory without overwriting earlier runs. The
manifest pins the inspected shared `anthropic/claude-sonnet-4.6` model, 2,048
output tokens, provider contract, summary settings, loop/batch limits, fixture
digests, and explicit mock script. Runtime production files were not changed.

The default run captures 40 contexts from 14 cases: 13 main-catalog cases at
100/1,000/10,000 workflows and one empty-catalog case. It saves representative
payloads and every rendered request in a reproducible compressed archive,
independent fixture snapshots/recipe, source/dependency fingerprints, raw
schema-2 telemetry, a stored conversation, fake-mail effects, and separate
routing/effect grades for one scripted approved-draft trace. All observation
states and mock/live/local provenance survive into evidence and reports.

**Why this approach:** Fresh-process bootstrap avoids import-time stores using
the wrong data root. A public settings allowlist prevents exporting credentials
or unrelated environment data. Actual prompt helpers and runtime/tool adapters
preserve the baseline behavior; full payloads and hashes make input drift
reviewable. Expected owners stay outside model input, and the mock response
script is explicitly separate from gold labels. Graders inspect observed
legacy aliases and exact recorded sends rather than trusting worker prose.
The compressed archive keeps every case inspectable without repeating large
rosters as uncompressed files. Evidence byte hashes are preserved across Git
checkouts, while source hashes normalize line endings.

**Verification:** `.venv\Scripts\python.exe server/tests/run_tests.py` passed
all 78 tests (70 existing plus 8 new). New checks cover fresh-process data/key
isolation, fixture drift rejection, overwrite prevention, archive/input
reproducibility, saved recipe reuse, artifact hashes, all four observation
states, multi-owner routing grades, and rejection of altered content,
recipients, drafts, accounts, threads, attachments, or duplicate sends.

Ran `.venv\Scripts\python.exe evals/agent_overload/run.py --output
evals/agent_overload/baseline`; all structural and scripted trace/effect checks
passed. Independently verified all 18 indexed artifacts and every recorded
runtime source fingerprint. The measured full-roster character counts are
4 for the empty `None` roster, 4,702 at 100 workflows, 47,947 at 1,000, and
480,397 at 10,000. These are character counts, not token estimates. No live
provider or email calls were made.

**Remaining limits:** This is a model-free infrastructure/input baseline.
Real routing accuracy, incorrect reuse, end-task success rates, live cost, and
provider latency are unavailable. Recall@5 is inapplicable to the unranked
legacy roster. Later strategies and longitudinal/model-backed comparisons are
unexecuted. Phase 5 must supply their release evidence. The earlier Step 2b/3
harness follow-ups are now covered by this step.

The saved report is `evals/agent_overload/baseline/report.md`; harness design,
commands, artifact semantics, and limitations are in `evals/agent_overload/README.md`.

## Step 5: Stable workflow identities and SQLite foundation (complete)

This completes the first slice of Phase 1, not the whole migration phase.

**Motivation:** Discovery, migration, and recall need identities that survive
renames and restarts. Names can share a filename slug, while revisions and
history generations are needed to reject stale writes and later callbacks.
The revised plan also requires explicit unknown historical state and storage
failure handling before the database becomes authoritative.

**Old behavior:** The roster is a list of names; worker log filenames derive
from those names. `Alice / Lunch` and `Alice - Lunch`, for example, normalize
to the same slug. Existing stores have no shared workflow UUID, workflow
revision, or data-generation contract. These legacy runtime paths remain in
use during this preparatory step.

**New behavior:** `server/services/workflows/` adds frozen workflow/alias models
and an explicitly opened `WorkflowStore`, defaulting to the isolated data-root
helper's `workflows.db`. Version 1 stores immutable UUIDs, scope, exact aliases,
purpose/summary, workflow state, UTC timestamps, archive metadata, and revision.
Renaming preserves previous aliases. Unknown historical status is nullable;
it is not inferred to be completed or archived. Run failure is not a workflow
state. No history is imported in this slice.

Schema initialization is atomic and repeatable. Connections enable foreign
keys; short write transactions use WAL and a bounded busy timeout. Missing,
corrupt, incompatible, or busy storage raises explicit errors rather than
becoming an empty catalog. Reads through an existing handle do not recreate a
removed database. Updates and alias additions require the inspected revision;
all operations verify the handle's cached generation. Metadata, aliases,
compact search documents, and FTS5 updates commit or roll back together. An
explicit rebuild regenerates the index from stored metadata.

**Why this approach:** UUIDs separate identity from names without guessing
semantic ownership. Exact scoped aliases retain legacy spelling and reject
conflicts instead of silently merging unrelated work. Revision checks prevent
lost updates; generation checks prepare for a later history-clear boundary.
Transactional index maintenance avoids metadata/search divergence, while
rebuildable documents keep the index a projection. Per-operation connections
close deterministically, and bounded SQLite contention handling avoids retry
storms. The in-memory FTS5 probe runs before persistent initialization and gives
an actionable error when unavailable. Explicit construction keeps migration
and live adoption independently reviewable.

**Verification:** `.venv\Scripts\python.exe server/tests/run_tests.py` passed
all 104 tests: 78 existing and 26 new. The new checks cover persistence/reopen,
exact aliases, legacy slug collisions, scope boundaries, workflow statuses,
bounded paging, stale revisions and concurrent writers, foreign keys, search
rebuilds, index-error rollback, lock timeout/retry, transactional schema failure,
incompatible schemas, corruption/missing storage, changed generations, absent
FTS5, and import/data-root isolation. SQLite FTS5 was exercised locally, with
the unsupported-runtime path simulated. All storage was temporary; no live
model or Gmail calls were made. `git diff --check` passed for tracked changes.

**Remaining limits / plan alignment:** The new package is not wired into app
startup, agents, schedulers, or existing stores. Its `create` method is a
persistence primitive, not the future model-visible creation/admission handler.
Source/event import, consistent backups, reconciliation/checkpoints, trigger
IDs, summary mappings, activity records/cards, authoritative adapters, and
feature-gated startup remain Phase 1 work. The archived field and generation
guard do not themselves implement archive or history-clear operations. Phase 2
will add public search and richer indexed metadata; this step makes no routing
quality claim. Existing baseline evidence is preserved.

Design details and executable API examples are in
`server/services/workflows/README.md`.

## Step 6: Non-destructive migration dry-run and reconciliation report (complete)

This completes the second slice of Phase 1. Apply mode remains unimplemented.

**Motivation:** Migration must expose ambiguity and missing evidence before
allocating durable mappings or changing writers. Filename collisions cannot
establish historical ownership, and background writers can change a source
while it is being inspected. The plan requires these cases to be reported,
not silently merged or treated as empty data.

**Old behavior:** Legacy store constructors initialize files during application
imports. Roster loading coerces non-string values, and log readers skip
unparsed lines. Several failed reads become empty state. There was no separate
inventory of source fingerprints, exact roster positions, unresolved owners,
or summary-boundary references.

**New behavior:** `server/services/workflows/migration.py` provides a stdlib-only
standalone CLI with an explicit data root and optional new report file outside
that root. It never imports the app, constructs a live store, allocates IDs,
or changes source files. It inventories every roster position, exact aliases,
worker/conversation entry locations and indices, raw-source/payload hashes,
request references, working-memory summary metadata/boundary/tail, and trigger
owner bindings. Reports omit conversation and tool text while retaining names
needed for reconciliation. Unknown workflow state and purpose remain unknown.

Duplicate aliases, slug collisions, orphan logs, unresolved trigger names,
malformed records, inaccessible storage, and inconsistent summary state are
explicit blocking issues. Missing worker logs and possibly truncated tool
content are warnings. Existing truncation is not repaired or presented as full
source. Repeated scans of unchanged inputs produce the same report.

**Why this approach:** Inspecting formats directly avoids the legacy services'
initialization and error-swallowing behavior. Streaming logs retain original
locations without accumulating source payloads. Parser parity preserves legacy
indices; ambiguous/noncanonical formats block rather than promise a safe map.
SQLite reads only temporary copies of the trigger database and WAL, preserving
committed WAL data without writing source shared-memory files. Copy hashes,
source fingerprint rechecks, and log-set rechecks detect observed drift. The
report explicitly does not claim an atomic snapshot across these sources.
Separating inspection from apply makes reconciliation reviewable before
resumable mappings, backups, or live writers are introduced.

**Verification:** `.venv\Scripts\python.exe server/tests/run_tests.py` passed
all 119 tests: 104 existing and 15 new. Tests verify source bytes, mtimes, and
file sets remain unchanged; repeated reports; committed WAL-only rows and
scratch cleanup; collision/orphan/owner diagnostics; exact aliases and roster
positions; parser parity and byte offsets; summary boundaries and tail checks;
corrupt/unreadable inputs; detected source mutations; CLI status codes and
overwrite protection. A guarded fresh process rejects any app import or network
connection. Inputs are synthetic and temporary; no real data was inspected.
`git diff --check` passed for tracked changes.

**Remaining limits / plan alignment:** `review_ready` means no blocking issue
was detected, not that migration can be applied. Every report states
`apply_supported: false`. Byte hashes and locations are source locators, not
durable workflow/event mappings. Pause all writers and revalidate during the
future maintenance window; consistent backups, source/event storage, resumable
apply, trigger backfill, summary mapping, activity records/cards, authoritative
adapters, and startup gating remain Phase 1 work. Live behavior and the saved
baseline are unchanged. CLI usage and examples are in
`server/services/workflows/MIGRATION.md`.

## Step 7: Immutable sources, events, and legacy-event mappings (complete)

This completes the third slice of Phase 1; it does not apply legacy migration.

**Motivation:** Hashes and log positions alone cannot supply the original
content when a summary omits it. Migration also needs durable per-entry mappings
so retrying an interrupted import does not duplicate history and old summary
indices can resolve to stable events after restart.

**Old behavior:** Workflow metadata had stable UUIDs, while worker/conversation
content remained in legacy text files. The dry-run reported hashes/locations
without persisting source objects or event mappings. Worker responses could
already be truncated; parsed-entry positions were not durable source IDs.

**New behavior:** `WorkflowStore.history` adds immutable captured source bytes,
event UUIDs, scoped event streams, and durable legacy references. Source metadata
includes hash, size, media type, provenance, and explicit completeness. Event
envelopes carry sequence/kind, source ID, workflow/conversation bindings, optional
run/turn IDs, occurrence time when known, and capture time. Exact lookup and
bounded event/byte paging recover stored content without returning entire
histories. An observed empty source remains distinct from missing storage.

Legacy capture stores decoded payload and exact raw record separately. It
preserves original path/index, whole-file fingerprint, line/byte location, and
timestamp text. Replays return the same event/source IDs; changed content,
locators, frozen-file fingerprints, or owner bindings conflict. A legacy path
is bound to one frozen input and stream per scope/generation. Known truncation
and unknown completeness remain qualified; timezone-less timestamps are not
converted into invented occurrence times.

**Why this approach:** Canonical bytes remain recoverable independently of
summaries and search text. Distinct captures keep their provenance even when
their bytes match. Stream bindings prevent unrelated workflow history from
sharing an owner accidentally; unique sequences and serialized writes preserve
order under concurrency. One transaction commits source/event/legacy mappings
and FTS5, preventing partial import entries. Hashing happens before the writer
lock. Frozen models and SQL guards prevent ordinary update/delete/replace of
history. Backend replay keys deduplicate local capture, not upstream sends.
The FTS projection is explicitly supplied and rebuildable; it does not confer
ownership or approval. Capturing history alone does not change workflow state.

Schema version 2 validates version 1 before upgrading, then commits the added
schema, migration record, and user version atomically. Failed upgrades roll back
without changing existing workflow identities, aliases, revisions, generation,
or search records. This is a workflow-database schema upgrade, not file import.

**Verification:** `.venv\Scripts\python.exe server/tests/run_tests.py` passed
all 143 tests: 119 existing and 24 new. Tests cover exact large/binary/empty
content recovery; bounded pages; persistence through restart, rename, and summary
changes; legacy raw records and qualified completeness; changed-input conflicts;
cross-scope/owner rejection; concurrent replay/appends; SQL immutability and
foreign keys; index rebuild; transactional write/index/mapping rollback;
missing/corrupt data and generation changes; and successful, rejected, failed,
and resumed schema upgrades. The empty-source test caught SQLite returning NULL
for an empty-BLOB slice; the reader now preserves it explicitly as empty bytes.
All state was temporary; no real data, model, or Gmail calls were used.
`git diff --check` passed for tracked changes.

**Remaining limits / plan alignment:** These are backend persistence APIs. The
legacy primitive trusts its future importer to validate supplied bytes against
the frozen source and resolve ownership; it reads no files and imports nothing
automatically. Existing live writers, dry-run behavior, and saved baseline
remain unchanged. Backups/validation manifests, durable workflow-import maps,
resumable apply orchestration, trigger backfill, summary import, activity/card
state transitions, adapters, and startup gating remain Phase 1 work. Public
recall/search tools and lifecycle clearing are later work. Usage, examples, and
design rationale are in `server/services/workflows/HISTORY.md`.

## Reduced-scope alignment: checkpoint and cleanup (complete)

**Motivation:** The release now needs bounded discovery and recoverable context
through existing dispatch. Inactive workflow identities, migrations, universal
events, and their schema machinery have no immediate runtime use under that
scope. Keeping them on the critical path would add work the revised plan defers.

**Old behavior:** Steps 5–7 added an inactive SQLite workflow/history package,
migration inspector, 65 dedicated tests, and supporting docs. The old next step
was a consistent backup/snapshot framework before import. Agents and schedulers
still used name-based dispatch and the original stores.

**New behavior:** Before cleanup, saved and verified an explicit named archive
containing all 16 selected working-tree files, including the 4 untracked history
files, plus the earlier plan and tracked working diff. The checkpoint is
`deferred/execution-agent-overload-storage-2026-11-08/storage-checkpoint.zip`;
its manifest records file hashes, byte sizes, tracking status, and origin commit.
The revised plan and unrelated changes were excluded. No branch pointer was
treated as a substitute for saving uncommitted files.

Removed the unused workflow/migration/event package and its dedicated tests/docs
from active source after checking imports. Updated README/current progress to
describe the smaller roadmap. Kept historical progress entries and preserved
the deferred checkpoint. Phase 0 code, fixtures, baseline artifacts, runtime
data, and existing dispatch/history/confirmation behavior are retained.

**Why this approach:** A source archive with exact byte/hash verification
preserves tracked and untracked work without resetting the repository or
rewriting history. Keeping code and tests together makes the deferred work
recoverable. A separate cleanup step makes scope reduction reviewable before
adding functional discovery changes. JSON metadata and lexical lookup will be
added only where the live Interaction Agent uses them.

**Verification:** Verified the archive checksum, ZIP integrity, every archived
file's hash, and equality with its working-tree bytes before deletion. Import
searches found no dependency from live agents/services/routes or retained tests
on the workflow package. `.venv\Scripts\python.exe server/tests/run_tests.py`
passed all 78 retained tests. The 65 archived tests account for the reduction
from 143; retained tests were not removed or weakened. The retained evaluation
checks exercise the existing baseline command and exact fake-mail effects.
`git diff --check` passed. The revised implementation-plan bytes were preserved.

**Remaining limits:** This cleanup introduces no bounded roster, lookup tool,
context limits, or routing-quality claim. The previous backup/import next step
is superseded. Deferred source paths in the historical entries are archive
references now, not active modules.

## Revised Phase 1: Bounded roster and worker lookup (implemented)

**Motivation:** A full roster makes prompt size grow with every worker, while
unconditional creation can duplicate work that already has an owner. The smaller
plan calls for a bounded recent list, lexical lookup over all names, and a local
creation guard without replacing dispatch or migrating history.

**Old behavior:** Every name appeared in the Interaction Agent prompt. Dispatch
created unknown names without a discovery attempt. Roster read errors could be
treated as empty state; name creation did not recheck filename collisions.

**New behavior:** `OPENPOKE_WORKER_DISCOVERY=bounded` selects at most five entries
within a 2,000-character roster budget, total/hidden counts, and lookup guidance.
`find_worker` searches the entire authoritative roster and optional exact-name
metadata. Queries are capped at 256 characters; result counts at five; JSON
payloads at 3,500 characters; and formatted lookup responses at 4,000 characters.
Descriptions shorten before exact names are omitted, with explicit limit flags.
Unknown purpose/activity remains unknown. No lookup scans worker logs.

The batch manager incrementally saves first/latest assignment snippets and
activity time to `roster.metadata.json` under the configured root. Metadata is
rebuildable and cannot create membership. History clearing removes it, and a
late assignment for an absent worker cannot recreate it. Exact dispatch and
trigger names retain their existing path. The prompt distinguishes unrelated
topic switches from genuine follow-ups and preserves confirmation/draft rules.

Each bounded interaction loop owns a small discovery-success flag. A successful
lookup is required before creating a new name when older workers exist; failed
or invalid lookup revokes it. Existing exact names remain reusable directly.
Creation reloads/rechecks membership and filename collisions under a local lock,
then atomically replaces roster JSON. Read/write failures are explicit. New
names colliding with roster or orphan-log filenames are rejected; historical
collisions are reported without merging histories.

**Why this approach:** One small helper supplies metadata, lexical matching,
and bounded rendering directly to live callers. The roster remains authoritative;
there are no workflow IDs, migration, event schema, semantic ranker, or persistent
routing decisions. Local loop state cannot leak into another turn or be forged
through tool arguments. A shared in-process lock plus atomic writes makes local
creation reviewable; cross-process writers remain deferred. Metadata failure
does not authorize creation or prevent trusted exact-name background dispatch.

The default strategy remains `legacy` during development; the evaluation command
and isolated test runner explicitly pin that mode before imports. The original
prompt/tool schema path remains available for comparison. Bounded failures never
fall back to the full roster. Default promotion follows Phase 3 evidence.

**Verification:** `.venv\Scripts\python.exe server/tests/run_tests.py` passed
all 98 tests: 78 retained and 20 new. New checks cover 100/1,000/10,000-worker
budgets; dormant and exact-name lookup; separate Alice topics; metadata persistence,
rebuild and clearing; unknown times; corruption and atomic-write failures;
concurrent creation; collisions; per-loop success/failure checks; forged/invalid
arguments; exact history reuse; chat/callback prompt integration; and assignment
metadata through the real batch manager. Existing fake draft effects, trigger
ownership, telemetry, and legacy evaluation checks pass. The legacy evaluation
is tested even when the caller's environment requests bounded discovery.

Measured roster characters were 1,108 / 1,110 / 1,112 versus the legacy 4,702 /
47,947 / 480,397 at the three catalog sizes. Each showed five workers; formatted
lookup responses were 1,801 / 1,804 / 1,807 characters. These are model-free text
measurements, not token counts or routing-quality results. Temporary state and
mocked providers were used; no live Gmail/model calls occurred. The saved baseline
and deferred checkpoint were preserved. `git diff --check` passed.

**Remaining limits:** Lexical retrieval cannot establish semantic uniqueness.
Metadata snippets are not authoritative task/approval state, and historical
truncation/collisions remain historical limitations. Real routing decisions for
topic switches and ambiguous follow-ups require the Phase 3 comparison. Whole
model requests and large source bodies are not yet bounded by this step.
Usage and examples are in [`worker-discovery.md`](worker-discovery.md).

## Revised Phase 2, step 1: Shared budget helper and preflight (complete)

**Motivation:** A bounded roster alone cannot prevent oversized messages,
histories, tool schemas/results, callbacks, or inner-agent requests from reaching
the provider. The full request must be checked after construction, with room
reserved for output and framing uncertainty.

**Old behavior:** The shared client supplied `max_tokens` but did not compare
input size against a model context allowance. Model capacity and an input cap
were not configured, and every component could send arbitrarily large text.

**New behavior:** `server/context_budget.py` estimates complete text requests
and computes the allowed input as the smaller of the configured input cap and
model allowance minus output reservation/headroom. Bounded context mode requires
explicit per-model allowances, validates all selected models at startup, and
rejects unknown dynamic models. Invalid mode/JSON/numeric/relationship settings
fail explicitly. No allowance is inferred from the output-token limit.

The final provider preflight covers all five callers and every loop iteration.
It sends exactly the immutable bytes that passed the check. Oversized or
unsupported requests fail before HTTP client creation, with a content-free
budget error. Accepted content, tool-call/result pairs, schemas, output limits,
and provider response contracts remain unchanged. Summarization does not retry
the same deterministic rejection. No content is trimmed by this step.

**Why this approach:** One small helper at the common provider boundary guards
outer and inner calls without five independent implementations. Native counting
is not available in the installed runtime, so UTF-8 JSON byte sizing plus framing
allowances is explicitly an estimate, not provider usage or a guaranteed native
token bound. It avoids assuming four characters per token for multilingual text.
Headroom and per-model configured allowances remain separate. Frozen wire bytes
prevent a mutable message list growing after approval. Structured media is
rejected because text sizing cannot account for it. Local budget failures reuse
the existing telemetry failure fields; measured usage semantics are unchanged.

The context strategy defaults to `legacy` during development, independently of
worker discovery. Evaluation/test bootstrap pins legacy and controlled budget
values before imports so external settings cannot alter the frozen comparison.

**Verification:** `.venv\Scripts\python.exe server/tests/run_tests.py` passed
all 114 tests: 98 retained and 16 new. New checks cover complete section accounting,
exact fit/overflow boundaries, reservation/headroom arithmetic, UTF-8 text,
invalid configuration and unsupported media, zero HTTP setup on rejection,
immutable request snapshots, unchanged accepted content/output, unknown/zero
provider usage, growing tool results, no summarizer retry, and all five actual
model-calling paths reaching preflight. Existing baseline CLI tests use conflicting
bounded caller settings to verify isolation. All state/providers were temporary
or mocked; no live Gmail/model calls occurred. `git diff --check` passed.

**Remaining limits:** This completes only Phase 2's initial helper/preflight
slice. Estimates are conservative planning values, not exact model token counts;
configured capacities still need independent verification. Oversized required
input currently produces a clear error. History rebuilding, full source capture,
opaque-reference reads, draft-by-reference adapters, and cumulative recall/work
limits remain unfinished. Usage and examples are in
[`context-budgets.md`](context-budgets.md).

## Revised Phase 2, step 2: Full-content capture (complete)

**Motivation:** Full text must exist before previews or history pruning can omit
it. The worker journal already cuts arguments/results at 200/500 characters;
conversation formatting also normalizes line endings. Neither can supply exact
original text that was discarded. The preflight guard alone supplies no durable
source for recovery after a rejection or restart.

**Old behavior:** Workers wrote shortened tool payloads; there was no opaque
content store or owner/account-qualified source reference. History clearing did
not invalidate content-write leases because those references did not exist.

**New behavior:** `server/content_store.py` publishes immutable UTF-8 bodies and
minimal JSON metadata beneath the configured root. Opaque IDs contain random
generation/object identifiers, not names or paths. Metadata carries owner, kind,
provider/account qualification, hash, size, media type, and capture time. Backend
reads return bounded byte pages after qualification and generation checks.
Missing, invalid, incomplete, or expired references fail explicitly.

Bounded user/callback/reply and worker instruction/response paths capture text
over 4,096 bytes. Worker arguments/results are additionally preserved before
the existing journal cuts, with references written into the same journals.
Gmail adapters bind capture to the actual Composio routing account; inner search
saves fetch output before cleaning and its selected aggregate. Reviewed draft
bodies retain original bytes with explicitly unknown mailbox provenance when
the display tool lacks that information. No result or review body is previewed
or replaced in model input by this step.

**Why this approach:** Small body/metadata files supply the required source
without workflow migration or an event schema. Private-directory publication
keeps partially written objects from becoming usable references. Content-only
async capture scopes carry exact owners and the original generation through
queued work; they contain no tool dispatch/approval machinery. Clear advances
the generation before deleting managed files, so failed cleanup cannot revive
old references. Batches preserve their first generation for callbacks, avoiding
attachment of mixed older content to the last finisher's newer history.

Gmail/search capture occurs where the executed account is known, rather than
guessing from later active-account state. Generic worker logging avoids a second
unqualified capture of those results. Reference journaling failures are explicit.
Persistence failure after a Gmail result aborts the tool loop with outcome-check
guidance instead of offering that tool error to the model for automatic retry.

**Verification:** `.venv\Scripts\python.exe server/tests/run_tests.py` passed
all 137 tests: 114 retained and 23 new. Coverage includes exact Unicode/CRLF and
middle-fact recovery; empty bodies; bounded paging; fresh-process persistence;
owner/account and profile boundaries; unknown provenance; missing/corrupt/
truncated content; atomic publication failure; concurrent writes/scopes; clear
and failed cleanup; queued writes and stale/mixed callbacks; original chat/draft
visibility; real worker/Gmail/inner-search capture paths; and capture-failure
propagation. Tests also preserve the existing prompt's whitespace normalization
while verifying that captured originals remain exact. All storage/results were
temporary or mocked; no live model/Gmail calls occurred. `git diff --check` passed.

**Remaining limits:** Backend paging is available, but model-visible recovery,
bounded episode construction, cumulative recall limits, and draft-by-reference
send adapters remain unfinished. Background classifier/summarizer source capture
will be added with their bounded context paths. This guards content references
and old content writes; it does not cancel already-running external actions or
solve all existing legacy-journal clear races. Body hashes accompany pages for
assembled-content verification, not a whole-file rehash on every page. Details
and examples are in [`content-capture.md`](content-capture.md).

## Revised Phase 2, step 3: Bounded source recovery (complete)

**Motivation:** Captured references need executable reads before context builders
can omit full text. Earlier worker journals may contain only shortened payloads;
recovery must distinguish an existing exact source from an unavailable original.

**Old behavior:** Only backend byte-page APIs could read captured content.
Neither model had a result-read or selected-history recall tool. Legacy
transcript loaders read the entire selected file into memory.

**New behavior:** Bounded mode advertises `read_result` and `recall_history` with
handlers in both existing agent loops. Result pages retain exact UTF-8 text and
immutable owner/mailbox labels, with byte offsets and hashes. History lookup
streams a single selected legacy log, can search literal text, and returns
bounded XML fragments with continuation cursors and explicit legacy limitations.
It does not call the full-transcript loaders. Partial scans, successful no-match
completion, lookup failures, missing content, and owner ambiguity are distinct.

The backend owns per-turn counters: eight recovery attempts, 512 KiB read/scan
work, and 32 KiB accepted responses. Per-call scan work is at most 128 KiB;
source pages cap at 2,048 bytes, and formatted responses cap at 8,192 bytes,
including escaping. Refused calls return only a small error. Recovery arguments
are not echoed into responses, and worker journaling avoids recapturing pages
of already-stored sources. The normal tool-call/result pair construction remains
intact; no pruning is introduced yet.

**Why this approach:** Fixed worker bindings and exact roster selection reuse
the existing ownership model. Stored mailbox labels accompany source browsing
without borrowing the currently active Gmail account. History cursors bind
generation, source/query, file identity, and snapshot end, so ordinary restart
works while clear/replacement fails explicitly. Reading raw bounded fragments
avoids loading a giant legacy entry or building a history-import/event layer.
Source data does not grant send permission or restore a missing exact draft.

**Verification:** `.venv\Scripts\python.exe server/tests/run_tests.py` passed
all 155 tests: 137 retained and 18 new. Checks cover Unicode/CRLF and middle-fact
recovery; escaping and actual response wrappers; mailbox/owner qualification;
invalid/missing/empty sources; selected-file streaming and partial scans;
matches across chunk/scan boundaries; cursor snapshots, fresh-process restart,
changed source/query, replacement, truncation and clear; lookup failure and
historical collisions; cumulative caps; executable schemas; per-turn reset; and
real interaction/worker loop invocation with valid call/result pairs. Storage
and providers were temporary/mocked, with no live Gmail/model calls.

**Remaining limits:** This step makes recovery usable before changing context
assembly. Oversized histories/current messages/callbacks can still fail preflight.
Exact draft-by-reference adapters and inner email-search/classifier/summarizer
limits are also pending. Append-only history is assumed; cursor identity/size
checks do not detect arbitrary same-size edits in place. Existing legacy-journal
clear races remain outside this slice. Details and examples are in
[`context-recovery.md`](context-recovery.md).

## Next implementation step under the revised plan

Use captured references and these recovery handlers when constructing bounded
complete conversation/tool episodes. Keep required instructions and genuine
follow-up dependencies, bound current messages and callbacks, preserve valid
tool-call/result pairs, and retain final provider preflight. Revised Phase 3
comparison and default promotion remain pending.
