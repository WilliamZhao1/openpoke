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
backend. Live mode is deliberately unsupported at this stage; the release
evaluation still requires the separate model-backed runs in Phase 5.

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
Migration, routing/context changes, lifecycle work, and model-backed release
comparisons remain later phases.
