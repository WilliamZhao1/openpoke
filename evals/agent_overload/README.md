# Agent overload evaluation harness

## Motivation and scope

The first comparison needs a durable record of the current behavior, fixed
inputs, and evidence that the tracing/grading pipeline works. This Phase 0
runner captures the actual legacy full-roster prompt and a complete scripted
chat/worker/Gmail/callback/reply trace. It measures prompt structure and checks
local effects. It does not measure the quality of a live model's decisions.

The frozen profile preserves the inspected configuration:

- OpenRouter contract and endpoint, with `anthropic/claude-sonnet-4.6` for all
  five model-calling components.
- A 2,048-token output limit, non-streaming requests, and the provider's existing
  sampling defaults; no extra temperature, seed, or model overrides.
- Existing loop/batch limits and summary threshold/tail settings.

The model name is retained in request payloads, but all completions in this
runner come from `httpx.MockTransport`. All Gmail operations use the fixture
backend. This default path remains model-free. Revised Phase 3 now adds the
paired comparison below without changing or regenerating the frozen baseline.

## Run

From the repository root:

```powershell
.\.venv\Scripts\python.exe evals/agent_overload/run.py
```

This writes a new directory beneath `evals/agent_overload/runs/`. To choose a
new destination or request a smaller input capture:

```powershell
.\.venv\Scripts\python.exe evals/agent_overload/run.py --sizes 0 100 --output evals/agent_overload/runs/local-check
```

The destination must not already exist. The runner never overwrites previous
evidence. Its default sizes are 0, 100, 1,000, and 10,000. This produces 40 case
contexts: 13 main-catalog cases at each nonempty size, plus the empty-catalog
case once. There are 14 distinct labeled scenarios, not 40 independent tasks.

`run.py` loads only standard-library bootstrap/configuration code before setting
a disposable data root and dummy integration credentials. It then imports the
app. A socket guard blocks network connects, and scoped mock bindings cover
both integrations. A Windows event loop's local self-pipe is created before the
guard; application/provider code executes after the guard is installed. The
supported entry point is a fresh standalone process, avoiding cached stores
from an already imported application. The temporary state is removed afterward.

## Frozen inputs and artifacts

`manifest.json` pins the model/configuration profile, fixture checksums, smoke
script digest, and limits. Unknown fields, credential fields, live mode, changed
fixtures, and unsupported profiles fail visibly. The script's fixed responses
are declared in `approved_draft.json`; they do not consult the gold owner labels
to generate a model response. The responses intentionally exercise one known
approved draft path and cannot support a routing-quality claim.

Each completed run contains:

| Artifact | Evidence |
| --- | --- |
| `manifest.json` | Validated public configuration only; no keys, environment dump, or user data path. |
| `inputs/` | Frozen fixture JSON and standalone deterministic catalog recipe. |
| `approved_draft.json` | Frozen synthetic review, approval, scripted responses, and grading expectations. |
| `prompts/catalog-*.json` | One readable representative request per selected catalog size. |
| `case_requests.jsonl.gz` | Every rendered case request, without gold labels or scripted lookup results. |
| `case_contexts.json` | Case/split/catalog identity, request hash, archive line, and separate gold expectations. |
| `prompt_shapes.json` | Directly observed roster counts, characters, and UTF-8 bytes. |
| `smoke.json` | Actual five mock request payloads, raw telemetry, stored conversation, fake calls/effects/state, and separate routing/effect grades. |
| `provenance.json` | Fixture/input/source hashes, actual dependency/Python versions, selected sizes, and predeclared comparison controls. |
| `summary.json` / `report.md` | Contract-check results and explicit measurement availability. |
| `artifacts.json` | SHA-256 byte hashes for saved files, excluding the index itself. |

The compressed request archive uses a fixed gzip header and is reproducible
for the same inputs/code. Case rows identify its zero-based line and canonical
JSON hash. Source hashes normalize line endings to LF; artifact byte hashes
measure the files as written. Runtime timestamps, UUIDs, and measured local
durations in the smoke evidence may vary between runs. Reproducible inputs do
not imply identical observations.

The saved baseline's Git attributes disable line-ending conversion for its
artifacts, so their byte hashes survive Windows/Linux checkouts. This setting
applies to captured evidence, while runtime source hashes normalize to LF.

## Interpreting results

The legacy prompt is built by the existing Interaction Agent helpers and
contains every workflow name at each catalog size. Character and byte counts
are exact observations, not token counts. No tokenizer estimate is substituted
for missing provider usage.

Case contexts are input captures. They are not routed by a live model or scored
using the fixture's scripted lookup candidates. Their actual route remains
unavailable. Gold labels are saved on the grading side and excluded from every
archived provider payload. The predeclared lexical, richer-card, decision-check,
and optional semantic comparisons are recorded as unexecuted, not simulated
as if those production strategies existed.

The smoke trace enters the actual chat handler, delegates through the existing
batch manager, sends the fixture draft through the actual Gmail tool/service,
then processes the callback and stores the reply. The grader checks the
observed legacy alias against the frozen workflow UUID, and grades the Gmail
write separately: account, draft, thread, subject, body, recipient, cc/bcc,
additional recipients, and attachments. Missing sends, wrong recipients,
duplicates, and unrequested mutations cannot be excused by worker prose.
This verifies the scripted local contract, not general approval enforcement.

Telemetry is preserved with its schema-2 per-observation availability and
provenance. Report observations retain the same four states; derivations point
to saved artifact evidence. The mock supplies no token-usage fields, so usage
remains unavailable. Local elapsed time is directly measured but is not live
provider latency. Real routing accuracy, incorrect reuse, task-success rates,
live prices/cost, and live latency stay unavailable. Recall@5 is inapplicable
to this unranked legacy roster. Do not interpret unknown values as zero.

Exit 0 means the local structural/trace/effect checks passed. Failed checks
return 1; invalid configuration or an existing output directory returns 2.
Unexpected failures expose a safe exception type and relative code location,
without copying arbitrary exception text or credentials. A passing report is
not published when input validation fails.

## Validation and saved baseline

Run the ordinary isolated suite with `python server/tests/run_tests.py`. It
includes fresh-process CLI runs, data/credential isolation, input/archive
reproducibility, artifact hashes, fixture drift rejection, overwrite prevention,
and independent routing/effect grader tests.

The saved [model-free baseline](baseline/report.md) preserves the initial
default-size capture. It completes the Phase 0 infrastructure baseline.
The reduced-scope plan supersedes the old migration roadmap. Discovery and
bounded-context implementation, release checks and default promotion are now
complete. The runner still selects its comparison controls explicitly rather
than inheriting production defaults.

## Phase 3: Paired comparison

`run.py --compare` uses the existing agents, fixed catalog/cases, fake Gmail,
telemetry, and graders. It compares the combined production `legacy` and
`bounded` discovery/context strategies with the same pinned model and 2,048-token
output reservation. It does not implement the old proposed ranker/card ablations.
The existing `manifest.json`, fixture checksums, and saved baseline stay intact.

Check the comparison's local plumbing without network calls:

```powershell
.\.venv\Scripts\python.exe evals/agent_overload/run.py --compare --context-window 65536
```

Offline comparison defaults to `alice-lunch` plus the approved-draft trace in
both arms. It reuses the frozen approved-draft responses; it does not choose
responses from gold labels. Passing these four scripted rows establishes
integration behavior, not live routing quality. No live fallback occurs.

Run actual model decisions while keeping every Gmail operation synthetic:

```powershell
.\.venv\Scripts\python.exe evals/agent_overload/run.py --compare --mode live --context-window 65536 --sizes 100 --max-calls 64
```

Live mode reads only `OPENROUTER_API_KEY` from the environment, or `.env` when
the environment does not define it. It uses the pinned OpenRouter endpoint and
can incur provider charges. Every application store is initialized under a new
temporary root before importing the server. Composio credentials are dummy and
Gmail is bound to the fixture backend. The process never loads the runtime
mailbox/history, and exports no authentication headers, environment dump, or
provider error text. Public evidence contains synthetic prompts and decisions.

`--context-window` is required: choose an explicit allowance for the pinned model,
as described in [context configuration](../../docs/context-budgets.md). The
example is an evaluation allowance, not a provider capacity assertion. The
default input cap is 32,768 with 1,024 headroom. Both arms preserve the model and
output settings; bounded mode performs the production input preflight.
Both arms also have a 256 KiB evaluation request-size ceiling.

Live comparison defaults to five routing cases: original Alice contract,
dormant tax owner, genuinely new garden work, competing drafts, and two owners.
It then runs the approved-draft case. Each scenario resets to identical synthetic
catalog/history/metadata/mailbox state before each arm. Arms are paired, and
which strategy goes first alternates by scenario. This limits ordering bias.
Metadata is seeded from frozen public purpose/activity fields in both arms;
only the production bounded strategy exposes its metadata through discovery.
Gold owner IDs, expected actions, and scripted lookup candidates never enter
provider payloads. `find_worker` executes the real lexical implementation.

Routing-only cases execute the real Interaction Agent and public dispatch
tool, including lookup/registration checks, then record accepted dispatches in
place of running workers. They measure routing, not completion of those tasks.
The approved-draft case runs actual chat acceptance, workers, batch callbacks,
and Gmail adapters, grading the exact recorded fake send separately. A downstream
failure does not erase an observed route, and a recoverable tool error does not
by itself mean the final task failed. Model/tool errors remain counted.

Controls:

- `--cases` selects unique frozen IDs from the five defaults, `alice-lunch`,
  `alternating-topics`, and `empty-catalog`. Empty-catalog requires `--sizes 0`.
  This first comparison excludes cases requiring deferred card/resource-index
  behavior and simulated lookup-failure conditions.
- `--sizes` supports the existing 0/100/1,000/10,000 catalogs; comparison defaults
  to 100. Large legacy requests may hit the evaluation ceiling; that is recorded
  as failure rather than silently enabling bounded behavior in the legacy arm.
- `--max-calls` caps actual HTTP requests across both arms (default 64, maximum
  128). Unrun cases stay unavailable. There is no automatic replay of an
  uncertain external action.
- `--case-timeout` caps each case including background work (default 180 seconds,
  range 10–300). Existing agent iteration/batch limits remain unchanged.
- `--request-interval` serializes HTTP admission at a minimum interval (default
  3.1 seconds live, zero offline; range 0–10). It reduces rate-limit pressure but
  cannot guarantee provider admission. Timing includes this deliberate pacing.
- `--output` must name a new directory, as in the baseline command.

Each comparison writes public settings, separate inputs/labels, per-case requests
and responses, accepted dispatches, telemetry, fake effects, a numeric summary,
source hashes, a short report, and artifact hashes. Partial results are saved
after each case. Usage/cost totals remain unknown if any request lacks valid
provider values; available subtotals are labeled separately. Actual zero stays
zero. Routing counts include their graded/attempted denominators, and a live
run with no completed decisions has unavailable routing quality. Request totals
and model-call attempts are separate because preflight/admission can reject an
attempt without HTTP. Elapsed time is local end-to-end time, not isolated provider
latency. All Gmail effects retain mock provenance even in live-model runs.

Exit 0 means the selected routing and draft/callback checks passed, 1 records
failed checks/provider/runtime errors, and 2 means invalid configuration or an
existing destination. A failed comparison still retains its evidence. The
runner never changes product defaults. A small live sample is not a general
accuracy estimate or proof of release readiness; application checks for triggers,
large full review, callbacks, chat acceptance, and clearing remain Phase 3 work.

The [first live comparison report](../../docs/agent-overload-comparison.md)
records a bounded draft-ID/reference confusion and a failed effect check despite
correct routing. Its compressed traces and numeric evidence are retained under
`comparisons/2026-11-09/`. A [focused guidance fix and passing live recheck](../../docs/agent-overload-comparison.md#follow-up-draft-id-guidance-and-live-recheck)
are recorded separately under `comparisons/2026-11-09-draft-id-fix/`. The original
failure remains preserved. Later [application and default-promotion checks](../../docs/agent-overload-release-checks.md)
pass, and production now defaults to bounded strategies. The runner itself
never promotes defaults or rewrites prior evidence.
