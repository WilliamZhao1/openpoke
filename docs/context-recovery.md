# Bounded result reads and selected-history recall

This third slice of revised Phase 2 makes source recovery executable in the
Interaction Agent and Execution Agent. Enable it with
`OPENPOKE_CONTEXT_STRATEGY=bounded` and the model allowances described in
[context-budgets.md](context-budgets.md). Restart after changing settings. The
default remains `legacy`; disabling the strategy preserves captured files.

## Motivation, old behavior, and design

Previously, oversized live content was captured under opaque IDs, but neither
agent had a tool to read those IDs or search one selected legacy history. The
provider preflight could reject a large prompt without offering model-visible
source recovery. The worker journal's old argument/result cuts still lost text
that had never been saved elsewhere.

Both agents now advertise executable `read_result` and `recall_history` handlers
in bounded mode. Recovery must work before context builders can replace full
history/results with references. This step provides that path without importing
legacy files, activating the deferred workflow package, or adding a general tool
session framework. Per-turn state counts calls, read/scan bytes, and response bytes.

The existing agent loops own this state and replace it each turn. Model arguments
cannot select a filesystem path or override the backend owner, generation,
account qualification, or counters. Worker registries bind the exact worker
owner; the Interaction Agent can select an exact existing roster name using
`agent_name`, or omit it to select the conversation. A worker can read only its
own sources. Historical log filename collisions produce an ambiguity error.

## Tools and limits

| Limit | Behavior |
| --- | --- |
| Source text per page | Default/max 2,048 UTF-8 bytes; integer limits clamp to 4–2,048. |
| Serialized tool response | At most 8,192 bytes, including runtime wrappers and JSON escaping. Arguments are not echoed. |
| Recovery calls per turn | Eight accepted attempts across both recovery tools. Further calls return a small refusal. |
| History scan per call | At most 128 KiB, including the returned page read. |
| Source reads/scans per turn | At most 512 KiB. |
| Recovery responses per turn | At most 32 KiB of accepted responses; later refusals contain only a small error. |
| History query | At most 256 characters; literal, case-sensitive text search. Overlong queries are rejected. |

`read_result(reference, offset=0, limit=2048, agent_name=None)` returns exact text,
the immutable owner/provider/account labels, byte size, SHA-256, and
`next_offset`. Follow the returned byte offset rather than counting characters.
The handler leaves a partial trailing UTF-8 character for the next page. An
arbitrary offset inside a character fails explicitly; text is never decoded with
replacement characters. JSON escaping can shrink the returned page further.
Empty content and reads exactly at EOF succeed with empty text.

Recovery uses `ContentStore.read_source_page` to browse a validated owner's
source **with the stored qualification**, including explicitly unknown accounts.
It never fetches an active Gmail account to relabel a source. For example, a
saved source from account A still reports A after the active account changes
to B. The existing `read_page` API continues to require an exact supplied
provider/account match. Neither API authorizes an external mailbox operation.

`recall_history(query="", cursor=None, limit=2048, agent_name=None)` reads only
the selected log, in bounded binary chunks. An empty query returns consecutive
pages. A nonempty query scans for a match and returns a fragment beginning at
that match. Its cursor continues the same query's search after the fragment;
it does not promise that every intervening log byte was returned. Search
accounts for the journals' XML escaping and normalized newline encoding. A
partial scan with `match_found=false` and `complete=false` means more scanning
remains. Only completion with no match in the remaining scanned range establishes
that there was no match there; it does not undo matches found on earlier pages.

History fragments are raw logged XML, potentially starting inside an entry;
they are source data, not model conversation/tool messages. The handler does not
parse a giant line or load a whole transcript. Legacy text may be normalized or
historically truncated, and its mailbox provenance is unknown. Follow a saved
`content_reference` with `read_result` for the exact original when one exists.
Missing originals cannot be reconstructed from these fragments.

Cursors contain no path. They bind the selected owner/query, content generation,
file identity, snapshot length, and next byte position. They survive restart,
ignore later appends during continuation, and reject changed selections, replaced
files, truncation, and cleared history. This assumes the existing append-only
journals; arbitrary in-place edits that preserve file identity and size are not
detected. Cursors are continuation data, not authentication credentials. No
cross-process writer coordination is added.

## Examples

Given an actual saved opaque reference from history:

```text
read_result(reference="<saved c1_ reference>", offset=0)
read_result(reference="<same reference>", offset=<returned next_offset>)
```

The pages can recover a fact in the middle of an omitted result. Their text
retains Unicode, CRLF, whitespace, and embedded control characters. The hash
supports verification after assembling all pages; the store does not rehash an
entire body on every read.

The Interaction Agent can search an older worker found through discovery:

```text
recall_history(agent_name="Alice contract", query="renewal date")
recall_history(agent_name="Alice contract", query="renewal date",
               cursor=<returned next_cursor>)
```

An Alice lunch worker attempting that other owner's lookup gets `wrong_owner`.
A missing source gets `source_unavailable`; failed roster access gets
`lookup_unavailable`; a filename collision gets `ambiguous_history`. None is
reported as a successful empty search. Old content references return `expired`
after history clearing. Invalid/changed cursors and exhausted budgets also
produce small explicit errors.

## Verification and remaining scope

`python server/tests/run_tests.py` passes 155 tests: 137 retained and 18 new.
Recovery checks cover exact Unicode/CRLF/middle-content paging; JSON escaping
and actual runtime wrappers; owner selection and immutable mailbox labels;
invalid offsets/paths/arguments; missing/empty content; streaming one selected
history and partial scans; matches across chunk/scan boundaries; XML/newline
search; cursor snapshot, restart, replacement, truncation, and clear behavior;
failed lookup/collisions; per-turn limits and counter reset; executable schemas;
both real agent loops; and unchanged tool-call/result pairing. The restart test
blocks network connections. All storage and provider results are temporary or
mocked; no live model/Gmail requests were made.

This step does not prune model histories, preview current messages/callbacks,
or resolve draft bodies in send/display adapters. Oversized prompts can still
fail the final provider preflight. Those builders, exact draft-by-reference
adapters, and inner email-search/classifier/summarizer limits remain Phase 2
work. Existing full draft review and confirmation remain in force. Source
recovery does not claim to fix all asynchronous legacy-journal clear races or
cancel already-running external actions.
