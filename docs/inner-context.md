# Bounded inner model context

Revised Phase 2, item 6 is implemented behind `OPENPOKE_CONTEXT_STRATEGY=bounded`.
It completes the implementation items in Phase 2. Phase 3's live comparison,
application release checks, report, and default promotion remain pending. Both
context and discovery still default to `legacy`; this step used no live calls.

## Motivation and previous behavior

An outer agent's preview is produced after its email-search task returns. It
cannot protect the search model from full results accumulated inside that task.
Likewise, classification submitted the complete cleaned email, and summarization
loaded the full conversation and mirrored working-memory tail before selecting
a batch. A growing briefing or batch could exceed the shared provider preflight.
Classification failure also returned the same `None` as a valid unimportant
decision, allowing the watcher to mark an undecided message seen.

The new paths reuse the context builder and final provider preflight. Required
instructions stay intact; optional text becomes an explicitly incomplete preview
after its original is saved. Every exposed `read_result` schema has a handler.
The complete serialized UTF-8 request size remains a conservative planning
estimate, not native tokens or measured usage. See [configuration](context-budgets.md).

## Shared source handling and design

`server/inner_context.py` supplies source capture, an operation-local reference
allowlist, recovery counters, UTF-8 prefixes, and complete-group pruning. It
reuses immutable content files and the existing recovery handler, without a
digest agent, another model, a general tool dispatcher, or history migration.

Full received sources are preserved before previews or source-quota errors.
Owner, generation, provider, and executed account remain fixed. Unknown mailbox
provenance stays unknown. Inner readers cannot select another worker or read
arbitrary references merely because the model invents an ID.

Each source reader allows 16 MiB of newly saved source text; exceeding it saves
the received original and stops progress. This is a processing limit, not a hard
download, heap, or disk quota. Recovery reuses eight calls, 32 KiB of accepted
responses, and 512 KiB of read/scan work; source pages are at most 2 KiB and encoded
responses at most 8 KiB. Each model response may contain at most eight parallel
tool calls. Retained loop messages cap at 256 KiB by saving and removing whole
earlier call/result groups. Required groups that cannot fit cause a clear error.

## Email search

The existing eight model iterations remain. Bounded search also caps Gmail
attempts at eight, processes at most 20 emails per query, and retains at most
100 distinct IDs under a 256 KiB serialized cache limit. Provider pagination
keeps the original executed account on every page. Large cleaned bodies have a
1 KiB UTF-8 preview and complete email reference; rows also identify their raw
Gmail result and mailbox.

Completion requires a recognizable successful lookup and IDs actually returned
by it. A valid empty lookup can return `[]`; SDK errors, malformed rows, unknown
IDs, and exhausted budgets cannot become an empty success. The query and fixed
mailbox instruction stay full or fail before HTTP when they cannot fit.

The parent worker receives at most eight new source hints per search. When there
are more, a saved index retains every original descriptor and its provider/account
qualification, and seven recent hints remain inline. This avoids overflowing the
parent request through a long reference list.

For example, a 60 KiB email with a deadline in its middle no longer enters every
search request verbatim. The model can read a page containing the deadline and
return its selected ID and references. Hitting the cache/query cap reports
incomplete work rather than claiming no matching email exists.

## Importance classification and polling

Metadata and instructions stay full. The builder tries the full cleaned body,
then a 1 KiB preview, then a source-only body view. Large processed inputs and
complete bodies are saved with the fetched mailbox. Standalone callers without
an account keep unknown provenance instead of consulting a later active account.

Classification allows eight model iterations and the same bounded source reader.
A positive decision can use evidence recovered from a page. An unimportant
decision requires coverage of the entire cleaned body: a prefix cannot prove the
rest contains nothing urgent. Important summaries must fit 2 KiB of UTF-8 text;
an oversized response is saved and rejected whole.

`ClassificationUnavailable` separates incomplete/failed work from a valid
negative. The watcher uses the strict interface, leaves those messages unseen,
and retries while they remain in its fetched window of at most 50 messages.
Failed classification does not advance the poll time. A retry set permits those
IDs past the next age cutoff and is bounded by the current fetch. Seen IDs include
the executed account; old unqualified IDs are not assigned to it. Account changes
reset the old cutoff. Notifications carry the raw source and generation through
the existing callback path.

For example, repeatedly proposing `important=false` after seeing only the start
of a 100 KiB email yields unavailable classification. A small, fully supplied
routine email still finishes with one negative decision. Existing initial warmup
and best-effort notification delivery remain; the retry set is not durable and
does not guarantee retries after restart, lookback expiry, or dispatch failure.

## Conversation summarization

The bounded summarizer reads just the working-memory header and a streamed
window of the selected conversation. A cursor in the existing summary metadata
records byte offset, file identity, and content generation alongside the last
summarized index. Pending rows remain in the original conversation; no new event
store or full-history import is required.

Effective threshold and tail are each clamped to 64 entries, including when the
existing configured threshold is 100. Each run scans at
most 16 MiB with an 8 MiB individual-entry limit. Adopting an old summary without
a cursor scans from the beginning under the same cap; large old histories can
fail explicitly. Subsequent runs seek directly to the saved position.

The previous briefing and user instructions stay full. Large informational
entries are saved and previewed. The builder reduces the batch to a smaller
complete prefix until it fits and commits only through that prefix. The existing
two provider attempts include source reads and transient retries. Required input
that cannot fit fails without an unchanged retry. Generated memory must fit
`min(16384, context_input_tokens // 2)` UTF-8 bytes, including retained source
citations. An oversized briefing is saved, leaving the old summary/cursor intact.

Memory keeps references to the previous briefing and selected saved entries even
if the model omits them. Snapshots are linked from memory instead of appended back
into the conversation being summarized, avoiding summaries of their own capture
records. Before commit, the backend checks generation, source identity/length,
and the previous summary index. Briefings use lossless JSON-string log encoding.

For example, if only two entries of an eight-entry batch fit, the cursor advances
through those two. The next run starts at the third, keeping the pending tail in
the canonical log. Legacy mode reconstructs that pending tail when re-enabled.
The cursor assumes append-only logs; it cannot detect every same-file manual
edit. Required giant user entries can still block progress with an explicit error.

## Validation and remaining plan work

`python server/tests/run_tests.py` passes 218 tests: 191 retained and 27 new inner
context tests. New cases exercise actual model-calling paths with mocked HTTP
and complete-request preflight, retained fake Gmail, and disposable data roots.
They cover middle-content recovery, multilingual text, executable schemas/tool
pairs, query/cache/source/read/message caps, qualified pagination/source indexes,
empty-versus-failed lookup, incomplete classification/watcher retry, mailbox
changes, overlong output, streamed resume/legacy rollback, batch-prefix progress,
transient retry, existing default settings and legacy loading, concurrent summary
changes, source replacement/truncation, and
clearing. Mandatory oversized classifier headers now fail in its builder before
the provider call; accepted classifier requests still pass the final guard.

Scripted decisions do not establish live routing accuracy, cost, latency, or model
compliance. Phase 3 must compare actual model decisions, check application flows,
publish findings and known limits, and then promote defaults. The archived storage
work, frozen baseline, and telemetry framework remain unchanged. Source retention,
cross-process coordination, durable callback delivery, and existing asynchronous
journal clear races are not expanded by this step.
