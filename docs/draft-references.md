# Exact draft bodies passed by reference

This fifth slice of revised Phase 2 connects immutable content to the existing
Gmail and draft-review adapters. It is available under
`OPENPOKE_CONTEXT_STRATEGY=bounded` with the model allowances described in
[context-budgets.md](context-budgets.md). Restart after changing settings. The
default is `bounded`; existing inline tool schemas remain available in explicit legacy mode.

## Motivation, old behavior, and design

Previously, the model had to repeat an entire email body in tool arguments and
worker callbacks. Large exact bodies could exhaust the model budget even when
the source was already saved. A full draft review also put the whole displayed
body back into the latest conversation episode on the next confirmation turn.
Rebuilding that body from a preview would lose content and invalidate the review.

The new path resolves exact text in backend code. An immutable draft record
contains the recipient, subject, body reference, body hash/size, optional Cc/Bcc,
additional recipients, HTML flag, requested thread, attachment metadata, and the
provider's draft ID when available. The body and record remain tied to their
exact worker, provider, executed Composio routing account, and content generation.
They use the existing content files and journals; no new database, history
migration, approval ledger, or document service is introduced.

The live body adapters are Gmail text/HTML operations. Exact document text inside
an already-saved raw Gmail payload can be selected as a body. There is no separate
document-writing adapter in this application to integrate in this step.

## Body references

Bounded Gmail schemas accept `body_reference` as an alternative to inline `body`
for draft creation, `message_body` for replies, or `additional_text` for forwards.
Backend validation rejects both forms together. Creation/replies require one;
forwarding may omit both. Recipient fields and other options retain their exact
submitted values.

```text
gmail_create_draft(
  recipient_email="alice@example.test",
  subject="Contract",
  body_reference={"reference": "<saved raw Gmail reference>",
                  "pointer": "/data/drafts/0/body"})
```

`pointer` is a JSON Pointer to a string field in a complete original raw Gmail
result or arguments object. It supports object fields, array indexes, and the
`~0`/`~1` escapes. An empty pointer selects a JSON string root. A pure saved draft
body uses only `{"reference": "<body reference>"}`. Missing/non-string fields,
duplicate JSON keys, ambiguous/invalid selectors, aggregate summaries, snippet
fields, recognized truncation flags, and result wrappers without an exact field
selection fail explicitly. No model summary or preview is promoted to a body.

Gmail actions resolve only sources owned by that worker and qualified to the
account actually used by the operation. Unknown or different mailbox provenance
fails before calling Gmail. A later active-account switch does not relabel the
saved source. Complete files are read in bounded pages and verified against their
hashes before decoding; size checks alone are insufficient for exact body reuse.

Resolution caps a source/pure body at 8 MiB, draft metadata at 64 KiB, and pointers
at 1,024 characters/32 steps. These are application limits, not claimed Gmail
limits. Oversized sources return an explicit error rather than shortened text.

## Draft creation, full review, and confirmation

Large or referenced Gmail draft creation returns a compact `draft_reference`,
`body_reference`, and recipient/mailbox metadata. The full original SDK payload
remains saved. A returned reference says that review and confirmation are still
required; it does not claim that the draft has been shown. A provider response
without an exact draft ID returns `draft_id_unavailable`. Sending by reference
then requires another lookup rather than inventing an ID or repeating creation.

The worker forwards the returned exact reference in its normal callback. The
Interaction Agent displays it with:

```text
send_draft(draft_reference={"reference": "<email_draft reference>",
                            "agent_name": "Alice contract"})
```

The backend loads and verifies the complete body and recipient metadata. Inline
recipient/subject/body overrides are rejected in this mode. The normal chat reply
contains the entire body, To/Subject, supplied Cc/Bcc/additional recipients, and
attachment name. Text/HTML content is preserved. Referenced reviews use a
lossless JSON-string encoding in the existing `poke_reply` entry; CRLF, literal
backslash-n, Unicode separators, control characters, and whitespace survive chat
history reads. Existing legacy entries keep their original decoding. New full
reviews remain readable when switching the strategy back to legacy.

After the full reply is recorded, a small `draft_review` marker binds the exact
draft reference to the displayed text's SHA-256. Bounded history verifies that
binding and the original source, then replaces that display in model context
with recipient metadata and exact references. The full UI/source files remain
unchanged. A display larger than the tail window can be retained through this
verified review anchor, explicitly labeled as source evidence rather than a
fabricated missing user request. Corrupt/missing sources or a mismatched visible
display fail explicitly. New review-marker writes check the original generation
under the content-store lock, so a stale run cannot append a marker after clear.

The Interaction Agent then asks for confirmation using the existing workflow.
After the user confirms, the owning worker can call:

```text
gmail_execute_draft(draft_reference={"reference": "<same draft reference>",
                                     "agent_name": "Alice contract"})
```

The backend resolves the original account-qualified draft ID and verifies the
body source. It rejects an inline ID override. Confirmation remains the existing
agent-policy workflow; neither the content reference nor the review marker is
authorization. No natural-language approval parser or new durable approval state
is added. External edits to a Gmail draft after review are not revision-locked by
this slice. Ordinary body/reference validation occurs before an external action.
Persistence failures after creation or visible review stop the model loop with
outcome-check guidance, avoiding automatic replay of that operation.

## Gmail draft IDs and saved references

A Gmail provider draft ID and an OpenPoke saved-content reference are different
identifiers. After the existing full review and explicit user confirmation:

```text
gmail_execute_draft(draft_id="r100000000000000001")
```

uses the original provider ID shown in that reviewed draft. It does not require
resolving a content-store object. When a tool instead returns `draft_reference`,
forward that exact object with its `c1_<generation>_<object>` reference; do not
invent a reference or put a provider ID inside it. `read_result` also expects a
saved-content reference rather than a Gmail ID.

The first live comparison exposed this confusion: the model supplied a Gmail ID
as `draft_reference.reference`, interpreted a generic missing-source error as an
expired Gmail draft, and asked to recreate it. Bounded schemas and context now
explain which field to use, and the saved-draft schema declares the opaque
reference format. Backend validation rejects a malformed selector before source
reads with an argument-specific error. That error does not establish provider
draft status, automatically change fields, send, or recreate anything.

The caller can explicitly retry using its original known provider `draft_id`
when review/confirmation already covers it. A real saved reference still goes
through the existing owner, mailbox, generation, hash, and complete-body checks;
its failure is not permission to bypass those checks or reconstruct content.
The legacy inline-ID schema and normal confirmation policy retain their behavior.

## Verification and plan position

`python server/tests/run_tests.py` passes 241 tests, including the 23 draft-reference tests.
The existing fake Gmail backend verifies actual create/reply/forward/send effects,
full bodies and recipient options, UTF-8/CRLF/control/literal text, full review and
compact history, overrides, wrong workers/accounts, unknown provenance, missing/
truncated/checksum-invalid data, strict JSON selection, backend limits, marker
bindings, generation clear, a network-blocked fresh-process restart, legacy schema
and history compatibility, missing draft IDs, and failures without operation
replay. A two-agent model-transport test carries a large saved body through
creation, callback, full review, a separate user confirmation, exact worker reuse,
and sending; every request passes the shared budget preflight. All storage and
providers are temporary/mocked. Scripted model replies do not establish live
routing quality, provider cost, latency, or compliance with instructions.

Three focused regressions cover malformed selector rejection before source/Gmail
IO, a confirmed provider ID sent directly, and a mistaken selector followed by
an explicit corrected call. The worker tests use the real loop, mocked provider
transport, full-request preflight, and exact fake Gmail effects. The retained
draft tests continue to cover genuine reference ownership/integrity and full
review/confirmation. See the [comparison report](agent-overload-comparison.md)
for separate live-model evidence and its limits.

Phase 0 assets remain retained and Phase 1 discovery now defaults to bounded.
Phase 2 items 1–6 are implemented: shared preflight, bounded outer context,
full capture, recovery, exact body adapters, and [inner email-search, summarizer,
and classifier limits](inner-context.md). Required oversized inputs can still
fail explicitly. Phase 3 comparison, checks, reporting and default promotion are
complete; see [release findings](agent-overload-release-checks.md). General giant
current inputs/callbacks can still fail when required instructions cannot fit;
this step handles referenced bodies, not every possible oversized request.
