"""LLM-powered classifier for determining important Gmail emails."""

from __future__ import annotations

import json
from contextlib import nullcontext
from dataclasses import asdict
from typing import Any, Dict, Optional

from .processing import ProcessedEmail
from ...config import get_settings
from ...logging_config import logger
from ...openrouter_client import ContextBudgetError, OpenRouterError, request_chat_completion
from ...content_store import ContentStoreError, capture_scope, current_capture
from ...context_builder import ContextBuilder, validate_tool_calls
from ...inner_context import SourceReader, READ_SCHEMA, INNER_POLICY, INNER_GUIDANCE, MAX_TOOL_CALLS, arguments, prefix


_TOOL_NAME = "mark_email_importance"
_TOOL_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": _TOOL_NAME,
        "description": (
            "Decide whether an email should be proactively surfaced to the user and, "
            "if so, provide a natural-language summary explaining why."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "important": {
                    "type": "boolean",
                    "description": (
                        "Set to true only when the email requires timely attention, a decision, "
                        "coordination, or contains critical security information (e.g. OTPs)."
                    ),
                },
                "summary": {
                    "type": "string",
                    "description": (
                        "Concise 2-3 sentence summary highlighting sender, topic, and the "
                        "specific action or urgency for the user. Only include when important=true."
                    ),
                },
            },
            "required": ["important"],
            "additionalProperties": False,
        },
    },
}

_SYSTEM_PROMPT = (
    "You review incoming Gmail messages and decide whether they warrant an immediate proactive "
    "notification to the user. Only mark an email as important if it materially affects the "
    "user's plans, requires a prompt decision or action, is a security-sensitive OTP or login "
    "notice, or contains high-priority updates (e.g. interviews, meeting changes). Ignore "
    "order confirmations, routine marketing, newsletters, generic receipts, and low-impact "
    "status notifications. When important, craft a brief summary that will be forwarded to the "
    "user describing what happened and why it matters."
)


def _format_email_payload(email: ProcessedEmail, *, body=None) -> str:
    attachments = ", ".join(email.attachment_filenames) if email.attachment_filenames else "None"
    labels = ", ".join(email.label_ids) if email.label_ids else "None"
    header_lines = [
        f"Sender: {email.sender}",
        f"Recipient: {email.recipient}",
        f"Subject: {email.subject}",
        f"Received (user timezone): {email.timestamp.isoformat()}",
        f"Thread ID: {email.thread_id or 'None'}",
        f"Labels: {labels}",
        f"Has attachments: {'Yes' if email.has_attachments else 'No'}",
        f"Attachment filenames: {attachments}",
    ]

    return (
        "Email Metadata:\n"
        + "\n".join(header_lines)
        + "\n\nCleaned Body:\n"
        + (body if body is not None else email.clean_text or "(empty body)")
    )


class ClassificationUnavailable(ContextBudgetError):
    """No decision was established; the watcher must not mark the email seen."""


async def classify_email_importance(email: ProcessedEmail, *, composio_user_id=None, source_reference=None, strict=False) -> Optional[str]:
    if get_settings().context_strategy != "bounded":
        return await _legacy_classify_email_importance(email)
    try:
        with nullcontext() if current_capture() is not None else capture_scope("conversation"):
            return await _bounded_classify(email, composio_user_id, source_reference)
    except (OpenRouterError, ContextBudgetError, ContentStoreError) as exc:
        logger.error("Importance classification failed", extra={"message_id": email.id, "error": str(exc)})
        if strict:
            raise ClassificationUnavailable("Email classification is unavailable or incomplete; it was not decided unimportant") from exc
        return None
    except Exception as exc:
        logger.error("Importance classification failed", extra={"message_id": email.id, "error": type(exc).__name__})
        if strict:
            raise ClassificationUnavailable("Classifier response is unavailable; no decision was established") from exc
        return None


async def _bounded_classify(email, account_id, source_reference):
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise ClassificationUnavailable("Importance classification requires a configured provider")
    reader = SourceReader()
    if source_reference:
        original = reader.register(source_reference)
        if original["provider"] != "gmail" or account_id is not None and original["account_id"] != account_id:
            raise ClassificationUnavailable("Original email source qualification differs from the fetched account")
    body = email.clean_text or ""
    serialized = json.dumps(asdict(email), ensure_ascii=False, default=str)
    if len(serialized.encode()) > 4096:
        reader.save(serialized, "email_classifier.input", provider="gmail", account_id=account_id)
    reference = reader.save(body, "email_classifier.body", provider="gmail", account_id=account_id)
    schemas = [_TOOL_SCHEMA, READ_SCHEMA]
    builder = ContextBuilder(settings=settings, model=settings.email_classifier_model, tools=schemas,
                             record_reference=reader.record, policy=INNER_POLICY, guidance=INNER_GUIDANCE)
    messages = None
    for limit in (len(body.encode()), 1024, 0):
        visible = body if limit == len(body.encode()) else prefix(body, limit)
        payload = (_format_email_payload(email, body=visible) + f"\nMessage ID: {email.id}\nProvider: gmail; account: {account_id!r}\n"
                   f"Complete body source: {reference}; size_bytes={len(body.encode())}. "
                   "An incomplete body cannot establish unimportant. Read omitted content or report no decision."
                   + (f"\nOriginal raw Gmail source: {source_reference}." if source_reference else "\nOriginal raw Gmail source is unavailable; body is the processed input."))
        candidate = [{"role": "user", "content": payload}]
        try:
            builder.build(_SYSTEM_PROMPT, candidate)
        except ContextBudgetError:
            continue
        messages = candidate
        reader.include(reference, 0, visible)
        break
    if messages is None:
        raise ClassificationUnavailable("Required email metadata/instructions cannot fit; source saved and no decision made")
    for _ in range(8):
        system, prepared = builder.build(_SYSTEM_PROMPT, messages)
        response = await request_chat_completion(component="email_classifier", model=settings.email_classifier_model,
                                                messages=prepared, system=system + "\n\n" + INNER_GUIDANCE,
                                                api_key=settings.openrouter_api_key, tools=schemas)
        assistant = ((response.get("choices") or [{}])[0].get("message") or {})
        calls = assistant.get("tool_calls") or []
        validate_tool_calls(calls)
        if not calls or len(calls) > MAX_TOOL_CALLS:
            raise ClassificationUnavailable("Classifier produced no bounded explicit decision")
        reader.check()
        messages.append({"role": "assistant", "content": assistant.get("content") or "", "tool_calls": calls})
        for call in calls:
            name = call["function"]["name"]
            args = arguments(call["function"].get("arguments"))
            result = {"status": "error", "error": "Use read_result or one separate importance decision"}
            if name == "read_result":
                result = reader.read(args)
            elif name == _TOOL_NAME and len(calls) == 1 and args is not None and type(args.get("important")) is bool:
                if not args["important"] and reader.complete(reference):
                    return None
                if args["important"] and isinstance(args.get("summary"), str) and args["summary"].strip():
                    if len(args["summary"].encode("utf-8")) > 2048:
                        reader.save(args["summary"], "email_classifier.rejected", provider="gmail", account_id=account_id)
                        raise ClassificationUnavailable("Importance summary exceeds its bounded notification limit; no partial notification was returned")
                    return args["summary"].strip()
                result = {"status": "error", "error": "Unread content cannot establish unimportant; read the rest or stop without a decision"}
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, ensure_ascii=False)})
        reader.prune(messages)
    raise ClassificationUnavailable("Classifier exhausted its bounded decision/read iterations")


async def _legacy_classify_email_importance(email: ProcessedEmail) -> Optional[str]:
    """Return summary text when email should be surfaced; otherwise None."""

    settings = get_settings()
    api_key = settings.openrouter_api_key
    model = settings.email_classifier_model

    if not api_key:
        logger.warning("Skipping importance check; OpenRouter API key missing")
        return None

    user_payload = _format_email_payload(email)
    messages = [{"role": "user", "content": user_payload}]

    try:
        response = await request_chat_completion(
            component="email_classifier",
            model=model,
            messages=messages,
            system=_SYSTEM_PROMPT,
            api_key=api_key,
            tools=[_TOOL_SCHEMA],
        )
    except (OpenRouterError, ContextBudgetError) as exc:
        logger.error(
            "Importance classification failed",
            extra={"message_id": email.id, "error": str(exc)},
        )
        return None
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception(
            "Unexpected error during importance classification",
            extra={"message_id": email.id},
        )
        return None

    choice = (response.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    tool_calls = message.get("tool_calls") or []

    for tool_call in tool_calls:
        function_block = tool_call.get("function") or {}
        if function_block.get("name") != _TOOL_NAME:
            continue

        raw_arguments = function_block.get("arguments")
        arguments = _coerce_arguments(raw_arguments)
        if arguments is None:
            logger.warning(
                "Importance tool returned invalid arguments",
                extra={"message_id": email.id},
            )
            return None

        important = bool(arguments.get("important"))
        summary = arguments.get("summary")

        if not important:
            return None

        if not isinstance(summary, str) or not summary.strip():
            logger.warning(
                "Importance tool marked email important without summary",
                extra={"message_id": email.id},
            )
            return None

        return summary.strip()

    logger.debug(
        "Importance classification produced no tool call",
        extra={"message_id": email.id},
    )
    return None


def _coerce_arguments(raw: Any) -> Optional[Dict[str, Any]]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


__all__ = ["classify_email_importance", "ClassificationUnavailable"]
