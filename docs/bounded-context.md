# Bounded context for the two outer agents

This fourth slice of revised Phase 2 connects source recovery to the Interaction
Agent and Execution Agent prompt builders. Enable
`OPENPOKE_CONTEXT_STRATEGY=bounded` with the explicit model allowances described
in [context-budgets.md](context-budgets.md), then restart. For large worker
catalogs, also enable `OPENPOKE_WORKER_DISCOVERY=bounded`. The legacy discovery
roster is not silently shortened by this context builder.

## Motivation and old behavior

Previously, the Interaction Agent embedded the full conversation or rendered
working-memory transcript in its first message. The Execution Agent embedded
its full selected history in the system prompt. Both loops kept appending
unmodified tool results. The shared preflight could reject an oversized request,
but these paths did not rebuild it using the stored content and recovery tools.

The new builder keeps required instructions intact and tries a small fixed
sequence of reductions. It runs before every outer-agent model call, including
calls after tools execute. Full executed tool arguments, full user-visible draft
review, provider output reservations, and the final provider preflight remain
in use. No migration, new model, tokenizer dependency, or observation framework
is introduced.

## History selection and required context

The builder reads at most 128 KiB from the selected legacy log's tail. It does
not call the full-transcript loaders or scan other workers' logs. A partial
first line/episode is excluded. Up to four recent incoming-message episodes are
retained, using the existing incoming-request and reply/wait tags as boundaries.
Unfinished episodes are labeled unfinished. A small legacy file missing its
opening request retains its available entries with that explicit status; an
unidentifiable latest episode outside the read window fails clearly.

The Interaction Agent also reads the existing working summary from the first
two working-memory lines when summarization is enabled. Each line read is
bounded, and the summary is retained intact. It does not render the entire
working-memory file. Summaries remain contextual evidence, not approval state.

The required portion contains the full static system instructions, current
message/instruction/callback, current roster section, existing summary, most
recent available history episode, and most recent assistant tool-call arguments.
The latest tool-call/result group remains structurally complete. Exact draft
bodies or recipients in required history/arguments are not cut to fit.

Worker dispatch sometimes already logs the current request before execution.
That exact unfinished current request is separated from prior history, so it
does not displace the previous draft episode or duplicate the current message.
For direct/trigger-style executions without a prelogged request, bounded mode
appends a request boundary through the existing journal before model execution.
This makes subsequent turns recoverable as separate episodes. It preserves
the exact worker name and does not introduce a new execution identity scheme.

Older instructions and dependencies outside this window remain available via
`recall_history`. The prompt requires lookup when they matter to the current
request. Tail selection does not establish semantic routing accuracy or detect
every long-range dependency; genuine uncertainty still requires recovery or
clarification. An unrelated topic must not inherit the latest worker.

## Rebuilding and source preservation

There are at most seven builder budget checks per call, followed by the existing
provider preflight. Checks use the same complete UTF-8 JSON planning estimate,
model allowance, output reservation, headroom, and tool schemas as the provider.
They are estimates, not native token measurements.

1. Check whether the required portion could fit at all. Empty tool-result bodies
   are used only for this lower-bound check and are never sent to the provider.
2. Try the selected recent history and all current tool episodes unchanged.
3. If necessary, omit older history while preserving its latest episode and
   source-recall guidance.
4. Save large tool-result strings and replace them with labeled previews, full
   source references, byte sizes, and exact original source qualifications.
5. If growth still exceeds the budget, save older current tool episodes together
   and retain the latest complete group. Previews may shrink from 1,024 bytes to
   256 or zero excerpt bytes. A clear error is returned if required content and
   recovery information still cannot fit.

All assistant calls and matching results in a parallel-call group travel
together. Malformed/missing/duplicate IDs are rejected before execution, and
incomplete result groups are rejected before another model request. Historical
XML fragments are source text; they are not fabricated provider tool messages.

Snapshots are immutable content-store objects journaled under the current owner
and generation before any preview/omission is sent. A per-turn hash cache reuses
the same snapshots during rebuilds. A snapshot of a model result or several
episodes is composite data with explicitly unknown mailbox provenance. Captured
original Gmail/search source references carry the provider and actual executed
Composio routing account separately; they are copied into model results and
previews without looking up a later active account. Full account-qualified raw
sources remain available through `read_result`.

Recovery-tool pages themselves are kept intact. If a page cannot fit, request a
smaller page rather than recursively previewing it. The normal recovery call,
read, and response caps remain in force. Snapshot persistence failure stops the
loop instead of encouraging a model retry of an already-completed external tool.

## Examples and limits

- A worker with 1,000 earlier small request/reply episodes loads only its bounded
  tail and keeps up to four recent episodes. Older details remain in the original
  log, reachable through selected-history recall.
- A large Gmail result can become a short preview. The model receives its saved
  reference and original mailbox labels, then can call `read_result` for a needed
  middle detail. The executed Gmail call is not repeated to recover that text.
- For “yes, send that draft,” the most recent draft episode and current user
  confirmation remain intact. The existing exact worker name remains available;
  a preview or summary does not grant send permission.
- A giant current request ending with “do not send” is saved and rejected before
  HTTP if it cannot fit with the required instructions. Its prefix is not used
  as a substitute instruction. Combined callbacks and oversized required draft
  bodies receive the same explicit behavior.

This slice uses clear errors for oversized required content.
[Exact body/draft adapters](draft-references.md) now resolve saved large bodies
and compact verified full-review displays without altering UI/source files.
Generic giant callbacks are not split into independently processed worker notices.
Inner email-search, summarizer, and classifier builders/cumulative
growth limits also remain unfinished; their final provider preflight still
rejects oversized input. Backend message copies and content-file storage can
grow within existing iteration limits; this is a model-input bound, not a new
retention or memory-quota system. Existing asynchronous journal/clear races and
cross-process coordination remain outside this slice.

## Verification

`python server/tests/run_tests.py` passes 191 tests, including the 16 context-builder tests.
These cover bounded history tails and Unicode separators; previous
draft retention and dispatch deduplication; existing summary/instruction
preservation; exact result and episode recovery; parallel tool pairs; immutable
arguments and current messages; tiny/insufficient budgets; missing/corrupt/
oversized histories and owner collisions; clear and cached-reference invalidation;
Gmail source qualifications; before-HTTP rejection of giant user/callback input;
both actual outer loops with provider preflight; failed preview persistence;
malformed calls rejected before tool effects; full draft review/original body
bytes; and direct/trigger-style journal boundaries. Tests use temporary data and
mocked model/Gmail results. Scripted model responses establish integration
behavior, not live routing quality, cost, or provider performance.
