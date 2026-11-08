# Execution Agent Overload: Implementation Progress

Updated: 2026-11-08

The implementation follows `execution-agent-overload-implementation-plan.md`
in separately reviewable steps. Phase 0 is in progress.

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

## Step 2: Observability and correlation IDs (revision follow-up pending)

The original step was implemented and verified. The revised plan adds an
observation-availability/provenance contract that requires the follow-up below.

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
architecture and delivery order. It does not yet satisfy every newly added
Phase 0 observation requirement.

| Plan requirement | Current alignment |
| --- | --- |
| Phase 0 isolated storage | Aligned: helper, default compatibility, all existing stores, temporary test runner, restart/clear isolation tests. |
| Phase 0 usage, timing, failures, and correlation | Implemented: all five model callers, chat, worker callbacks, triggers, and Gmail notifications. Routing and model/output-token configuration retain baseline behavior. |
| Phase 0 explicit observation availability and mock/live provenance | Follow-up required: token values can be `null` and `usage_complete` is recorded, but there is no explicit four-state availability contract or machine-readable mock/live evidence label. |
| Expanded Phase 0 fixtures and controlled comparisons | Pending, as before; include the newly added topic-switch, genuine follow-up, stale-card, near-tie, and complete/partial/unavailable lookup cases. |
| Phase 1 activity records and rebuildable cards | Future work: use source-linked outcomes, explicit obligation transitions, and revisions when implementing storage/migration. |
| Phase 2 intent isolation and enforced routing decisions | Future work: bind decisions to current intent, scope, generation, and revisions; recover or abstain on ambiguity/failure. Current trace IDs are not those decisions. |
| Phase 7 graph retrieval experiment | Future work after Phases 0-5 and the frozen baseline; Phase 6 remains optional and independent. |

**Required Step 2 follow-up:** Add `available`, `inferred`, `unavailable`, and
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

## Next steps in Phase 0

1. Complete the observation-availability and mock/live provenance follow-up,
   with tests for every state, missing-data reasons, and source labeling.
2. Add the fixed workflow catalogs and deterministic fake Gmail backend,
   including the expanded routing/lookup scenarios in the revised plan.
3. Add the executable evaluation harness, frozen manifest/inputs, and saved
   full-roster baseline evidence. Predeclare comparisons that separate richer
   metadata, backend decision checks, and optional ranker effects; preserve
   availability/provenance in evidence and reports.

Phases 1–7 remain pending; Phase 6 is optional, and Phase 7 follows the baseline
release rather than being a prerequisite for it.
