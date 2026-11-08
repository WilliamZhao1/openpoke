# Execution Agent Overload: Implementation Progress

Updated: 2026-11-08

The implementation follows `execution-agent-overload-implementation-plan.md`
in separately reviewable steps. Phase 0's model-free baseline and infrastructure
are complete. Phase 1's storage foundation is implemented; migration and runtime
adoption remain pending. Model-backed release comparisons remain in Phase 5.

Each implementation step is reported with its motivation, old behavior, new
behavior, design rationale, validation, and any remaining limits or plan gaps.
The alignment review below uses the 2026-11-08 revision of the plan.

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

## Next implementation step

Add a non-destructive migration dry-run and reconciliation report that inventories
the legacy roster, logs, conversation state, and triggers; surfaces collisions,
orphans, and unresolved owners; and leaves all input files untouched. Source/event
storage and verified apply mode will follow before compatibility adapters or
background dispatch use the new database.

Phase 1 is in progress; Phases 2–7 remain pending. Phase 6 is optional, and
Phase 7 follows the baseline release rather than being a prerequisite for it.
