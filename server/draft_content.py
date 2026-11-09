"""Exact email body and draft references for the existing Gmail/review adapters."""

from hashlib import sha256
from html import escape
import json
import re

from .content_store import ContentExpiredError, ContentStoreError, capture_text, current_capture
from .context_recovery import _RecoveryError, _select_owner
from .services.execution.discovery import WorkerDiscoveryError


MAX_SOURCE_BYTES = 8 * 1024 * 1024  # Application read limit, not a Gmail/provider limit.
MAX_DRAFT_BYTES = 64 * 1024
DRAFT_REFERENCE_PATTERN = r"c1_[0-9a-f]{32}_[0-9a-f]{32}"
BODY_REFERENCE_SCHEMA = {"type": "object", "properties": {
    "reference": {"type": "string", "description": "Opaque saved source reference, owned by this worker and qualified to the executed Gmail account."},
    "pointer": {"type": "string", "description": "Optional exact JSON Pointer to a string body inside a saved JSON result/arguments, e.g. /data/drafts/0/body. Omit only for a saved pure body."},
}, "required": ["reference"], "additionalProperties": False}
DRAFT_REFERENCE_SCHEMA = {"type": "object", "properties": {
    "reference": {"type": "string", "pattern": f"^{DRAFT_REFERENCE_PATTERN}$",
                  "description": "Exact saved c1_ email_draft reference returned inside a tool's draft_reference field. Never put a Gmail provider draft ID here; that belongs in draft_id. Do not invent a saved reference. This is not send authorization."},
    "agent_name": {"type": "string", "description": "Exact owning worker name, required when the Interaction Agent selects a worker's draft. Workers cannot select another owner."},
}, "required": ["reference"], "additionalProperties": False}


class DraftReferenceError(ValueError):
    pass


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DraftReferenceError("Saved JSON has ambiguous duplicate fields; the body was not guessed.")
        result[key] = value
    return result


def _context():
    context = current_capture()
    if context is None:
        raise DraftReferenceError("Draft references require an owning bounded agent turn.")
    context.store.assert_generation(context.generation)
    return context


def _read(reference, *, owner, maximum=None):
    context = _context()
    maximum = MAX_SOURCE_BYTES if maximum is None else maximum
    offset, chunks, digest = 0, [], sha256()
    try:
        while True:
            page = context.store.read_source_page(reference, owner=owner, offset=offset, limit=65536)
            if page.metadata["size_bytes"] > maximum:
                raise DraftReferenceError("Exact source exceeds the backend body-resolution limit; it was not shortened.")
            chunks.append(page.content)
            digest.update(page.content)
            if page.next_offset is None:
                break
            offset = page.next_offset
        if digest.hexdigest() != page.metadata["sha256"]:
            raise DraftReferenceError("Exact source checksum failed; do not reconstruct its body from a preview.")
        context.store.assert_generation(context.generation)
        return b"".join(chunks).decode("utf-8"), page.metadata
    except ContentExpiredError:
        raise
    except (ContentStoreError, UnicodeError) as exc:
        raise DraftReferenceError("Exact source is missing, incomplete, or unavailable; recover the original rather than reconstructing it.") from exc


def _selector(value, allowed):
    if not isinstance(value, dict) or set(value) - allowed or not isinstance(value.get("reference"), str):
        raise DraftReferenceError("Use an opaque reference and only the documented selector fields.")


def resolve_body(reference, *, account_id):
    _selector(reference, {"reference", "pointer"})
    context = _context()
    if not context.owner.startswith("worker:"):
        raise DraftReferenceError("Gmail body resolution requires the owning worker turn.")
    text, metadata = _read(reference["reference"], owner=context.owner)
    if (metadata["provider"], metadata["account_id"]) != ("gmail", account_id):
        raise DraftReferenceError("Body source mailbox is unknown or differs from the executed account; no mailbox was inferred.")
    if "pointer" not in reference:
        if metadata["kind"] not in {"email_draft_body", "reviewed_draft_body"}:
            raise DraftReferenceError("This source is not a pure body; select its exact JSON string field instead of sending a result wrapper.")
        return text
    if not metadata["kind"].startswith("GMAIL_") or not metadata["kind"].endswith((".arguments", ".result")):
        raise DraftReferenceError("Use an original raw Gmail payload, not an aggregate, preview or summary, for exact body selection.")
    pointer = reference["pointer"]
    if not isinstance(pointer, str) or len(pointer) > 1024 or (pointer and not pointer.startswith("/")):
        raise DraftReferenceError("Use a JSON Pointer of at most 1024 characters.")
    tokens = pointer.split("/")[1:] if pointer else []
    if len(tokens) > 32 or any(re.search(r"~(?![01])", token) for token in tokens):
        raise DraftReferenceError("Invalid JSON Pointer; the body was not guessed.")
    try:
        value = json.loads(text, object_pairs_hook=_object)
        for token in tokens:
            token = token.replace("~1", "/").replace("~0", "~")
            if token.casefold() in {"snippet", "summary", "preview"} or (isinstance(value, dict) and any(
                    value.get(flag) is True for flag in ("truncated", "preview", "is_truncated", "body_truncated", "bodyTruncated"))):
                raise DraftReferenceError("Selected source is abbreviated or marked incomplete; recover its full original body.")
            if isinstance(value, list):
                if re.fullmatch(r"0|[1-9][0-9]*", token) is None:
                    raise ValueError()
                value = value[int(token)]
            elif isinstance(value, dict):
                value = value[token]
            else:
                raise ValueError()
        if not isinstance(value, str):
            raise ValueError()
        return value
    except DraftReferenceError:
        raise
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise DraftReferenceError("Selected body string is unavailable; missing or historically truncated content cannot be reconstructed.") from exc


def _record(reference, kind, record_reference):
    try:
        record_reference(reference, kind)
    except OSError as exc:
        raise ContentStoreError("Draft content was saved but its journal reference failed; check completed tool outcomes before retrying") from exc


def save_draft(*, to, subject, body, account_id, record_reference, body_reference=None, **options):
    context = _context()
    if not all(isinstance(value, str) for value in (to, subject, body)):
        raise DraftReferenceError("Exact recipient, subject and body strings are required.")
    if len(body.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise DraftReferenceError("Draft body exceeds the backend body-resolution limit; it was not shortened.")
    if body_reference is None:
        body_reference = capture_text(body, kind="email_draft_body", provider="gmail", account_id=account_id, min_bytes=-1)
        _record(body_reference, "email_draft_body", record_reference)
    manifest = {"to": to, "subject": subject, "body_reference": body_reference,
                "body_sha256": sha256(body.encode("utf-8")).hexdigest(), "body_size_bytes": len(body.encode("utf-8")), **options}
    serialized = json.dumps(manifest, ensure_ascii=False, allow_nan=False)
    if len(serialized.encode("utf-8")) > MAX_DRAFT_BYTES:
        raise DraftReferenceError("Draft metadata exceeds its backend limit; recipients and subject were not shortened.")
    reference = capture_text(serialized, kind="email_draft", provider="gmail", account_id=account_id, min_bytes=-1)
    _record(reference, "email_draft", record_reference)
    selector = {"reference": reference}
    if context.owner.startswith("worker:"):
        selector["agent_name"] = context.owner[len("worker:"):]
    return selector


def load_draft(selector, *, account_id=None, for_action=False):
    _selector(selector, {"reference", "agent_name"})
    if re.fullmatch(DRAFT_REFERENCE_PATTERN, selector["reference"]) is None:
        raise DraftReferenceError(
            "draft_reference.reference requires the exact saved c1_ reference returned by a tool. "
            "For an original Gmail provider draft ID, use gmail_execute_draft(draft_id=...) after user confirmation of the reviewed draft. "
            "This invalid selector does not establish the Gmail draft's status; do not recreate it to repair this argument."
        )
    context = _context()
    if for_action and not context.owner.startswith("worker:"):
        raise DraftReferenceError("Sending a referenced draft requires its owning worker turn.")
    try:
        owner = _select_owner(context, selector.get("agent_name"))
    except (_RecoveryError, WorkerDiscoveryError) as exc:
        raise DraftReferenceError("Exact draft owner lookup failed or selected another worker; retry lookup without guessing ownership.") from exc
    text, metadata = _read(selector["reference"], owner=owner, maximum=MAX_DRAFT_BYTES)
    if metadata["kind"] != "email_draft" or metadata["provider"] != "gmail":
        raise DraftReferenceError("Select a complete email_draft reference; a body, result preview, or summary is insufficient.")
    if for_action and (account_id is None or metadata["account_id"] != account_id):
        raise DraftReferenceError("Draft mailbox is unknown or differs from the executed account; no mailbox was inferred.")
    try:
        draft = json.loads(text, object_pairs_hook=_object)
        if (not isinstance(draft, dict) or set(draft) - {"to", "subject", "body_reference", "body_sha256", "body_size_bytes", "cc", "bcc", "extra_recipients", "is_html", "thread_id", "attachment", "draft_id"}
                or not isinstance(draft["to"], str) or not isinstance(draft["subject"], str)
                or not isinstance(draft["body_reference"], str) or not isinstance(draft["body_sha256"], str)
                or re.fullmatch(r"[0-9a-f]{64}", draft["body_sha256"]) is None
                or type(draft["body_size_bytes"]) is not int or draft["body_size_bytes"] < 0):
            raise ValueError()
        for key in ("cc", "bcc", "extra_recipients"):
            if draft.get(key) is not None and (not isinstance(draft[key], list) or any(not isinstance(item, str) for item in draft[key])):
                raise ValueError()
        if draft.get("is_html") is not None and type(draft["is_html"]) is not bool:
            raise ValueError()
        if any(draft.get(key) is not None and not isinstance(draft[key], str) for key in ("draft_id", "thread_id")):
            raise ValueError()
        if draft.get("attachment") is not None and not isinstance(draft["attachment"], dict):
            raise ValueError()
    except (ValueError, TypeError, KeyError) as exc:
        raise DraftReferenceError("Stored draft metadata is incomplete or invalid; no fields were reconstructed.") from exc
    body, body_metadata = _read(draft["body_reference"], owner=owner)
    if (body_metadata["kind"] not in {"email_draft_body", "reviewed_draft_body"}
            or (body_metadata["provider"], body_metadata["account_id"]) != (metadata["provider"], metadata["account_id"])
            or (body_metadata["sha256"], body_metadata["size_bytes"]) != (draft["body_sha256"], draft["body_size_bytes"])):
        raise DraftReferenceError("Draft body qualification differs from its manifest.")
    return {**draft, "body": body, "provider": metadata["provider"], "account_id": metadata["account_id"],
            "owner": owner, "draft_reference": selector}


def render_draft(draft):
    headers = [f'To: {draft["to"]}', f'Subject: {draft["subject"]}']
    for key, label in (("cc", "Cc"), ("bcc", "Bcc"), ("extra_recipients", "Additional recipients")):
        if draft.get(key):
            headers.append(f'{label}: {", ".join(draft[key])}')
    if draft.get("attachment"):
        headers.append(f'Attachment: {draft["attachment"].get("name", "(unnamed)")}')
    return "\n".join(headers) + "\n\n" + draft["body"]


def review_summary(draft, *, reviewed=False):
    return {"draft_reference": draft["draft_reference"], "provider": draft["provider"], "account_id": draft["account_id"],
            "to": draft["to"], "subject": draft["subject"], "cc": draft.get("cc"), "bcc": draft.get("bcc"),
            "extra_recipients": draft.get("extra_recipients"), "is_html": draft.get("is_html"),
            "attachment": draft.get("attachment"), "thread_id": draft.get("thread_id"),
            "draft_id": draft.get("draft_id"), "body_reference": {"reference": draft["body_reference"]},
            "body_size_bytes": len(draft["body"].encode("utf-8")),
            "review": ("Full body shown to user; sending still requires explicit confirmation." if reviewed
                       else "Draft created; full user review and explicit confirmation are still required before sending.")}


def compact_review_lines(lines, parse_line, *, prefix_omitted):
    """Replace only verified full review displays in model history, leaving UI files intact."""
    from .services.execution.log_store import _encode_payload, _decode_payload
    result = list(lines)
    for index, line in enumerate(lines):
        parsed = parse_line(line)
        if not parsed or parsed[0] != "draft_review":
            continue
        try:
            notice = json.loads(parsed[2])
            if not isinstance(notice, dict) or set(notice) != {"draft_reference", "display_sha256"}:
                raise ValueError()
            draft = load_draft(notice["draft_reference"])
            display = render_draft(draft)
            if sha256(display.encode("utf-8")).hexdigest() != notice["display_sha256"]:
                raise ValueError()
            replacement = '<draft_review>' + escape(json.dumps(review_summary(draft, reviewed=True), ensure_ascii=False), quote=False) + '</draft_review>'
            match = None
            for earlier in range(index - 1, -1, -1):
                entry = parse_line(lines[earlier])
                if entry and entry[0] == "poke_reply":
                    encoded = re.search(r'\bencoding="json"', lines[earlier].split(">", 1)[0])
                    expected = display if encoded else _decode_payload(_encode_payload(display))
                    if entry[2] != expected:
                        raise ValueError()
                    match = earlier
                    break
            if match is not None:
                result[match], result[index] = replacement, ""
            elif prefix_omitted:
                result[index] = replacement
            else:
                raise ValueError()
        except (ValueError, TypeError, KeyError) as exc:
            raise DraftReferenceError("Draft review source or display binding is unavailable; exact review cannot be replaced by a summary.") from exc
    return result
