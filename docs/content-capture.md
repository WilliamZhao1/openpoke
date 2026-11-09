# Full-content capture under opaque references

This is the second slice of revised Phase 2. In bounded context mode, live
message/result paths preserve oversized text in immutable content files before
existing journal truncation or any future preview. Capture keeps original model
message content and the existing full draft-review path intact.
[Model-visible recovery](context-recovery.md) and
[bounded outer-agent context](bounded-context.md) now use these sources.

## Motivation and old behavior

The worker journal keeps only the first 200 characters of tool arguments and
500 characters of results. Conversation logs keep full text but normalize line
endings. A later preview cannot recover a middle fact or exact draft body from
material already discarded by those paths. The budget preflight can reject an
oversized request, but it does not preserve that content independently.

The new capture paths save the full UTF-8 text and record a usable opaque
reference in the existing worker/conversation journal. For example, an 8 KB
result containing a fact after character 4,000 retains that fact in its content
file even though the normal worker journal still contains its 500-character
excerpt. New capture does not reconstruct older truncated results.

## Storage and identity

`server/content_store.py` uses the configured data root:

```text
content/generation.json
content/objects/<generation>/<object>/body.txt
content/objects/<generation>/<object>/metadata.json
```

References have the opaque form `c1_<generation>_<object>`. Both identifiers are
random; they contain no worker name, mailbox, or arbitrary filesystem path.
Metadata records the owner, kind, provider/account qualification, byte length,
SHA-256, UTF-8 media type, and creation timestamp. There is no workflow migration,
database schema, universal event log, or automatic historical import.

Body and metadata are written into a private temporary directory and published
together by a same-directory rename. The store exposes no update API. A failed
publication leaves no readable partial reference. The local lock is shared
across store handles in the single writer process; cross-process coordination
and power-loss durability are not claimed.

## Active capture paths

Capture is enabled by the existing `OPENPOKE_CONTEXT_STRATEGY=bounded` setting.
The model allowances required by context preflight still apply. No new feature
flag or storage setup is needed. Importing the module does not create files;
an accepted bounded run initializes its generation lease.

| Path | Capture point |
| --- | --- |
| User messages and execution callbacks | Original text before existing prompt normalization; over 4,096 UTF-8 bytes. |
| User-visible replies, worker instructions/responses | Over 4,096 bytes; full legacy messages remain visible/stored. |
| Generic worker tool arguments/results | Before the existing 200/500-character journal cut, using conservative 200/500-byte capture thresholds. |
| Gmail adapters | Arguments and normalized full results at the actual account-bound call, before journal cuts. |
| Inner email search | Full fetch output before cleaning/parsing, plus oversized task arguments and selected aggregate results. |
| Reviewed draft body | Original body text, separately from its review wrapper; over 4,096 bytes. |

Gmail account qualification is the Composio user/routing ID supplied to the
operation. It is not guessed from the currently active account after the call,
nor claimed to be a Google email address or connected-account ID. Generic
worker logging skips a second unqualified capture of Gmail/search payloads.
The draft-display tool does not know the originating mailbox, so that capture
explicitly records `provider=gmail, account_id=None`; it never borrows the
currently connected account. Qualified original tool results remain available
through their own references.

These are captured text/normalized JSON results, not original provider HTTP
wire bytes. The body values and original text retain their exact UTF-8 bytes,
including Unicode, CRLF, and surrounding whitespace. Existing prompts/journals
retain their prior normalization behavior.

## Backend reads and qualifications

`ContentStore.read_page(reference, owner=..., provider=..., account_id=...,
offset=0, limit=8192)` retrieves one byte page. Limits are 1–65,536 bytes and the
response includes metadata plus a next offset. Pages may split UTF-8 characters;
assemble bytes before decoding text. The returned whole-object SHA-256 lets a
reader verify assembled content. Reads validate metadata and file size; they do
not hash the entire object on every page.

Owner and provider/account qualifiers must match the stored values exactly.
Worker owners use `worker:<exact name>`; interaction content uses `conversation`.
An unknown Gmail account is readable only as explicitly unknown, not under a
newly connected account. These checks are backend data boundaries, not a
multi-user authentication system. Invalid, missing, incomplete, or expired
references fail explicitly; absence never manufactures historical content.

This slice exposes backend reads only. There is no `read_result` model schema
without a handler, and no arbitrary-path reader. Large draft bodies are still
reviewed and sent through the existing adapters; reference-based sending and
its content/recipient validation come later.

## Clearing and late work

Each accepted bounded run carries a content-only generation lease through
async tasks. Worker scopes change the owner while retaining the originating
generation. Batches retain their first generation for callbacks, rather than
letting the last finisher attach older content to a new history.

History clearing first atomically advances the generation, then deletes managed
content directories, then follows the existing journal/roster/trigger clearing
path. It validates resolved deletion paths and rejects linked/unexpected
directories. If cleanup fails, the old references and leases are already invalid.
Old reads, queued captures, and callbacks fail instead of resolving into
replacement history. References also survive an ordinary restart within their
original data root.

This does not cancel external actions already in flight or solve every legacy
journal-clear race. A mixed old/new batch callback is rejected when its first
generation has expired. A capture failure after a successful Gmail call aborts
the worker's tool loop and identifies the need to check that operation's outcome
before retrying; it does not claim exactly-once external effects.

## Verification and next step

`python server/tests/run_tests.py` passes all 171 tests, including the 23 capture
tests. They cover full Unicode/CRLF/middle-content recovery, bounded byte pages,
exact empty content, ordinary/fresh-process reloads, owner/account isolation,
unknown provenance, corrupt/missing/truncated storage, atomic publication failure,
concurrent writes/scopes, clear and failed cleanup, queued work and stale/mixed
callbacks, original user/draft visibility, real worker/Gmail/search capture paths,
and capture-failure propagation. Legacy mode remains covered by the retained
suite. Tests use temporary roots, fake results, and mocked providers.

Bounded `read_result`/selected-history handlers now expose these sources with
per-turn recovery budgets; see [context-recovery.md](context-recovery.md).
[Outer-agent context builders](bounded-context.md) now use references for large
results and omitted tool groups, carrying original captured source qualifications
alongside composite snapshots. Background classification/summarization capture, inner model
limits, and exact draft-by-reference adapters remain unfinished Phase 2 work.
No old history is imported or deleted as part of enabling capture.
