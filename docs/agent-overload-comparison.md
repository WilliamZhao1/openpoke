# Legacy and bounded comparison, 2026-11-09

The first focused live-model comparison is complete. **Release checks did not
pass:** both strategies selected the expected routes, but bounded mode failed
to send the approved draft. Both product defaults remain `legacy`.
The [focused follow-up](#follow-up-draft-id-guidance-and-live-recheck) below
records a fix and a passing rerun of the affected scenario; broader release
checks are tracked separately. The original results and evidence are preserved.
The later [application release checks and final findings](agent-overload-release-checks.md)
now pass; default promotion remains a separate step. Earlier status/metrics below
describe their individual runs.

## Motivation and implementation

The previous harness captured the legacy prompt and one scripted draft trace.
Its mock replies could verify integration but could not show what a model would
actually route, whether bounded context preserved useful behavior, or the cost
of recovery mistakes.

`evals/agent_overload/run.py --compare` now runs both production strategies using
the existing fixtures, agents, fake Gmail, telemetry, and graders. The baseline
command and frozen evidence remain unchanged. An offline comparison reuses the
frozen smoke replies; `--mode live` requests actual OpenRouter decisions. There
is no automatic live fallback.

Each case resets to the same synthetic roster, metadata, histories, and mailbox
before each arm. Arms are paired with alternating first strategy. Routing-only
cases observe accepted public dispatch after real lookup/registration checks;
their workers are replaced with a recorder. The draft case runs real chat
acceptance, worker execution, callbacks, and Gmail adapters against fake Gmail.
Routing is graded independently from downstream effects. A worker's success
message does not substitute for an actual recorded send.

This approach reuses the existing evaluation path rather than adding another
platform. Full synthetic traces remain inspectable, gold labels stay separate
from model inputs, and every Gmail effect keeps mock provenance. Credentials
are read only for provider authentication and are excluded from artifacts.

## Controls and observations

The primary run used `anthropic/claude-sonnet-4.6` in both arms, a 2,048-token
output reservation, the provider's sampling defaults, and the same 100-worker
catalog. Bounded input used a configured allowance of 65,536, input cap of
32,768, and headroom of 1,024. These are planning settings, not a native tokenizer
measurement or provider-capacity claim. Both arms had a 256 KiB evaluation
request ceiling, 180 seconds per case, a global 64-request cap, and at least
3.1 seconds between HTTP requests. The paced run received no HTTP rate-limit
errors; an earlier unpaced attempt did. No failed send was automatically replayed.

| Observation | Legacy | Bounded |
| --- | ---: | ---: |
| Expected routing action and every owner | 6 / 6 | 6 / 6 |
| Correct reuse | 4 | 4 |
| Incorrect reuse / unnecessary creation | 0 / 0 | 0 / 0 |
| Prompt roster entries | 100 | 5 |
| Roster characters | 4,702 | 1,083 |
| Model attempts / HTTP requests | 21 / 21 | 25 / 25 |
| Provider-reported input tokens | 106,344 | 143,212 |
| Provider-reported output tokens | 1,506 | 2,092 |
| Provider-reported `cost` total | 0.341622 | 0.461016 |
| Sum of case elapsed time, including pacing | 64.17 s | 79.47 s |
| Terminal runtime/model failures | 0 / 0 | 0 / 0 |
| Tool errors, including recoverable errors | 0 | 4 |
| Exact approved fake draft sent once | Yes | **No: zero sends** |
| Unexpected fake mutations | 0 | 0 |
| Chat accepted and callback observed | Yes | Yes |

All 46 provider responses supplied valid usage/cost fields; the totals are sums
of returned fields, not prices inferred from a rate card. The harness keeps a
total unknown if any request lacks valid values, preserving available subtotals
separately. Timing is local end-to-end time under deliberate pacing, not isolated
provider latency. A smaller roster did not reduce total tokens/calls/cost here.

The five routing cases were original Alice contract, dormant 2023 tax owner,
new garden work, competing drafts, and two owners. The sixth was the approved
lunch draft. The dormant owner remained discoverable through real lexical lookup.
Bounded mode initially attempted dispatch without successful discovery in two
cases; backend checks rejected those attempts, and the model then looked up and
selected the expected workers. Those errors are retained in the trace and totals.

## Draft failure and remaining release work

The reviewed provider draft ID was `r100000000000000001`. Legacy called
`gmail_execute_draft(draft_id="r100000000000000001")`, producing exactly one
matching fake send with the original account, body, recipient, subject, and thread.

Bounded mode instead called:

```json
{"draft_reference": {"reference": "r100000000000000001"}}
```

That field requires an owned saved-content reference, not a Gmail draft ID.
The backend rejected it. The model then supplied the same provider ID to
`read_result`, received another error, and concluded that the draft had expired.
It asked to recreate the draft rather than using `draft_id`. No Gmail SDK call
or mutation occurred in that arm, although the worker returned a success status
and the callback completed. Effect grading correctly failed the task.

This result motivated focused schema/prompt guidance, a regression case, and
the affected-scenario rerun recorded below. Remaining application checks cover
triggers, callbacks, full large-draft review, chat acceptance, and clearing before
default promotion. Reference validation and exact-body requirements remain.

This is one small sample of a combined discovery/context strategy, not a ranker
or metadata ablation, a general accuracy estimate, or a live test of every inner
model component. Large histories/emails, all catalog sizes, asynchronous clearing
races, and all failure cases were not measured by these live decisions. The
existing scripted suite covers many of those contracts, but cannot replace
model-backed/application release evidence. An exploratory run also varied on
new-work creation and encountered rate limits, so these results do not establish
deterministic model compliance. No production behavior was changed in this step.

## Validation and evidence

The isolated backend runner passes **225 tests**, including seven new comparison
tests for paired real paths, exact fake effects, gold-label separation, credential
and data isolation, unchanged model/output settings, unknown versus zero usage,
limits/redaction, partial evidence, independent routing/effects, live-mode
configuration checks, artifact hashes, and overwrite prevention. Offline scripted
comparison passes; the live comparison intentionally returns exit 1 because the
bounded draft effect check failed. This is a recorded finding, not a passing
release result.

The primary run completed at 2026-11-09 16:54:51 UTC. Its retained evidence is:

- [Public comparison settings](../evals/agent_overload/comparisons/2026-11-09/comparison.json)
- [Numeric summary](../evals/agent_overload/comparisons/2026-11-09/summary.json)
- [Separate input and grading labels](../evals/agent_overload/comparisons/2026-11-09/inputs.json)
- [Complete compressed requests, decisions, telemetry, and fake effects](../evals/agent_overload/comparisons/2026-11-09/results.json.gz)
- [Executed source provenance](../evals/agent_overload/comparisons/2026-11-09/provenance.json)
- [Artifact byte hashes](../evals/agent_overload/comparisons/2026-11-09/artifacts.json)

See [the harness instructions](../evals/agent_overload/README.md#phase-3-paired-comparison)
for the reproducible command and controls. Repetition can produce different model
decisions; keep new runs separate rather than overwriting this evidence.

## Follow-up: Draft ID guidance and live recheck

The observed failure came from treating two different identifiers as
interchangeable. The old bounded schema called `draft_reference` opaque but did
not state its `c1_` format or clearly distinguish it from `draft_id`. Invalid
selectors reached the content reader and produced a generic missing-source
error, which the model interpreted as a missing provider draft.

The bounded schema now describes both fields explicitly and declares the saved
reference format. The bounded context policy tells both agents to keep provider
IDs and saved references separate. `load_draft` rejects malformed selectors
before source IO with an argument-specific error explaining the correct field.
It does not send, change fields, or recreate a draft automatically. Valid saved
references still pass through the existing ownership, mailbox, generation,
integrity, and exact-body checks. Both send paths retain user confirmation.

For the reviewed provider ID, the correct call remains:

```json
{"draft_id": "r100000000000000001"}
```

A real `draft_reference` must instead be the exact `c1_...` reference returned
by a tool. An invalid selector is not evidence that the Gmail draft expired.
This small change clarifies the existing adapters; it adds no lookup fallback,
approval ledger, or new identifier conversion layer.

The isolated suite passed **228 tests**, including three new regressions for:

- malformed saved selectors failing before source/Gmail IO;
- directly sending a reviewed, confirmed provider ID without source resolution;
- a mistaken selector followed by a separate explicit corrected call, with
  exactly one original send and no recreation.

The existing large-reference, full-review, cross-owner/account, integrity, and
clear tests also pass. Scripted worker requests still go through complete-request
preflight and real fake-Gmail adapters.

The focused live recheck completed at 2026-11-09 17:17:10 UTC using the same model,
2,048-token output limit, 100-worker catalog, synthetic review/approval, and
3.1-second request pacing. It selected `alice-lunch` plus the approved-draft case
in both arms, with a global 32-request cap. The comparison passed (exit 0), using
22 requests across all four rows. Both strategies selected the expected owners,
accepted chat, and completed callbacks. Every model response was live; every
Gmail effect was mock.

For the approved-draft rows only:

| Observation | Legacy | Bounded |
| --- | ---: | ---: |
| Executed argument | `draft_id` | `draft_id` |
| Exact original fake draft sent | Once | Once |
| Duplicate sends / unexpected mutations | 0 / 0 | 0 / 0 |
| Tool errors | 0 | 0 |
| Model/HTTP calls | 8 | 7 |
| Returned input tokens | 40,026 | 40,843 |
| Returned output tokens | 541 | 445 |
| Returned `cost` total | 0.128193 | 0.129204 |
| Local case elapsed time including pacing | 24.79 s | 21.51 s |

Bounded mode directly chose `gmail_execute_draft(draft_id=...)`; it did not attempt
the invalid selector or call `read_result` for that provider ID. The SDK received
one send of the original ID, preserving its account, body, recipients, subject,
and thread. No draft was recreated.

This is a targeted recheck, not a rerun of all six original scenarios or a claim
of general model compliance/performance. The original failed run remains above.
Product defaults remain `legacy` until the remaining application release checks
pass. Retained follow-up evidence:

- [Public settings](../evals/agent_overload/comparisons/2026-11-09-draft-id-fix/comparison.json)
- [Numeric summary](../evals/agent_overload/comparisons/2026-11-09-draft-id-fix/summary.json)
- [Separate inputs and grading labels](../evals/agent_overload/comparisons/2026-11-09-draft-id-fix/inputs.json)
- [Complete compressed trace](../evals/agent_overload/comparisons/2026-11-09-draft-id-fix/results.json.gz)
- [Executed source provenance](../evals/agent_overload/comparisons/2026-11-09-draft-id-fix/provenance.json)
- [Artifact hashes](../evals/agent_overload/comparisons/2026-11-09-draft-id-fix/artifacts.json)

Recheck command:

```powershell
.\.venv\Scripts\python.exe evals/agent_overload/run.py --compare --mode live --context-window 65536 --sizes 100 --cases alice-lunch --max-calls 32
```
