"""Tool definitions for interaction agent."""

import asyncio
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Optional

from ...logging_config import logger
from ...services.conversation import get_conversation_log
from ...services.execution import get_agent_roster, get_execution_agent_logs
from ...services.execution.discovery import WorkerDiscoveryError, find_workers
from ...content_store import ContentStoreError, capture_text, current_capture
from ...draft_content import DRAFT_REFERENCE_SCHEMA, DraftReferenceError, load_draft, render_draft, review_summary, save_draft
from ...context_recovery import SCHEMAS as RECOVERY_SCHEMAS, RECOVERY_NAMES, handle_recovery_tool
from ..execution_agent.batch_manager import ExecutionBatchManager


@dataclass
class ToolResult:
    """Standardized payload returned by interaction-agent tools."""

    success: bool
    payload: Any = None
    user_message: Optional[str] = None
    recorded_reply: bool = False


@dataclass
class DiscoveryState:
    """Small per-loop backend state; never supplied through model arguments."""
    successful: bool = False


FIND_WORKER_SCHEMA = {
    "type": "function", "function": {
        "name": "find_worker",
        "description": "Search all exact worker names, purposes and recent assignments. Use before creating a new worker; a failed lookup is not no matches.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Current task, distinguishing topic, or exact worker name; capped at 256 characters."},
            "limit": {"type": "integer", "description": "Result count, clamped to 1–5.", "default": 5},
        }, "required": ["query"], "additionalProperties": False},
    },
}

# Tool schemas for OpenRouter
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "send_message_to_agent",
            "description": "Deliver instructions to a specific execution agent. Creates a new agent if the name doesn't exist in the roster, or reuses an existing one.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "Human-readable agent name describing its purpose (e.g., 'Vercel Job Offer', 'Email to Sharanjeet'). This name will be used to identify and potentially reuse the agent."
                    },
                    "instructions": {"type": "string", "description": "Instructions for the agent to execute."},
                },
                "required": ["agent_name", "instructions"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message_to_user",
            "description": "Deliver a natural-language response directly to the user. Use this for updates, confirmations, or any assistant response the user should see immediately.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Plain-text message that will be shown to the user and recorded in the conversation log.",
                    },
                },
                "required": ["message"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_draft",
            "description": "Record an email draft so the user can review the exact text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email for the draft.",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject for the draft.",
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body content (plain text).",
                    },
                },
                "required": ["to", "subject", "body"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Wait silently when a message is already in conversation history to avoid duplicating responses. Adds a <wait> log entry that is not visible to the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Brief explanation of why waiting (e.g., 'Message already sent', 'Draft already created').",
                    },
                },
                "required": ["reason"],
                "additionalProperties": False,
            },
        },
    },
]

_EXECUTION_BATCH_MANAGER = ExecutionBatchManager()


# Create or reuse execution agent and dispatch instructions asynchronously
def send_message_to_agent(agent_name: str, instructions: str, *, discovery=None) -> ToolResult:
    """Send instructions to an execution agent."""
    if not isinstance(instructions, str) or not instructions.strip():
        return ToolResult(False, {"error": "instructions must be a nonempty string"})
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return ToolResult(False, {"error": "No event loop available"})
    roster = get_agent_roster()
    try:
        is_new = roster.register(agent_name, allow_creation=discovery is None or discovery.successful)
    except (WorkerDiscoveryError, ValueError) as exc:
        return ToolResult(False, {"error": str(exc)})

    get_execution_agent_logs().record_request(agent_name, instructions)

    action = "Created" if is_new else "Reused"
    logger.info(f"{action} agent: {agent_name}")

    async def _execute_async() -> None:
        try:
            result = await _EXECUTION_BATCH_MANAGER.execute_agent(agent_name, instructions)
            status = "SUCCESS" if result.success else "FAILED"
            logger.info(f"Agent '{agent_name}' completed: {status}")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(f"Agent '{agent_name}' failed: {str(exc)}")

    loop.create_task(_execute_async())

    return ToolResult(
        success=True,
        payload={
            "status": "submitted",
            "agent_name": agent_name,
            "new_agent_created": is_new,
        },
    )


# Send immediate message to user and record in conversation history
def send_message_to_user(message: str) -> ToolResult:
    """Record a user-visible reply in the conversation log."""
    log = get_conversation_log()
    log.record_reply(message)

    return ToolResult(
        success=True,
        payload={"status": "delivered"},
        user_message=message,
        recorded_reply=True,
    )


# Format and record email draft for user review
def send_draft(
    to: Optional[str] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    *, draft_reference=None,
) -> ToolResult:
    """Record a draft update in the conversation log for the interaction agent."""
    log = get_conversation_log()

    reference, draft = None, None
    if draft_reference is not None:
        if any(value is not None for value in (to, subject, body)):
            raise DraftReferenceError("Supply a complete draft_reference without inline recipient, subject or body overrides.")
        draft = load_draft(draft_reference)
        to, subject, body = draft["to"], draft["subject"], draft["body"]
        message = render_draft(draft)
    else:
        if not all(isinstance(value, str) for value in (to, subject, body)):
            raise DraftReferenceError("Provide exact to, subject and body strings or one complete draft_reference.")
        reference = capture_text(body, kind="reviewed_draft_body", provider="gmail", account_id=None)
        message = f"To: {to}\nSubject: {subject}\n\n{body}"
        if current_capture() is not None and reference is not None:
            selector = save_draft(to=to, subject=subject, body=body, account_id=None,
                                  body_reference=reference, record_reference=log.record_content_reference)
            draft = load_draft(selector)

    log.record_reply(message, exact=draft_reference is not None)
    if reference:
        log.record_content_reference(reference, "reviewed_draft_body")
    if draft is not None:
        try:
            log.record_draft_review(draft["draft_reference"], message)
        except OSError as exc:
            raise ContentStoreError("Full draft review was recorded but its reference marker failed; check the displayed draft before retrying") from exc
    logger.info(f"Draft recorded for: {to}")

    return ToolResult(
        success=True,
        payload={
            "status": "draft_recorded",
            "to": to,
            "subject": subject,
            **(review_summary(draft, reviewed=True) if draft is not None else {}),
        },
        recorded_reply=True,
    )


# Record silent wait state to avoid duplicate responses
def wait(reason: str) -> ToolResult:
    """Wait silently and add a wait log entry that is not visible to the user."""
    log = get_conversation_log()
    
    # Record a dedicated wait entry so the UI knows to ignore it
    log.record_wait(reason)
    

    return ToolResult(
        success=True,
        payload={
            "status": "waiting",
            "reason": reason,
        },
        recorded_reply=True,
    )


# Return predefined tool schemas for LLM function calling
def get_tool_schemas(*, bounded=False, recovery=False):
    """Return OpenAI-compatible tool schemas."""
    schemas = deepcopy(TOOL_SCHEMAS) if recovery else TOOL_SCHEMAS
    if recovery:
        draft = next(schema["function"] for schema in schemas if schema["function"]["name"] == "send_draft")
        draft["parameters"]["properties"]["draft_reference"] = DRAFT_REFERENCE_SCHEMA
        draft["parameters"]["required"] = []
        draft["description"] += " Supply either all inline fields or a complete draft_reference, without overrides. The backend displays the full exact body and recipients. Review is not send authorization."
    return [*schemas, *([FIND_WORKER_SCHEMA] if bounded else []), *(RECOVERY_SCHEMAS if recovery else [])]


def find_worker(query, limit=5, *, discovery=None):
    if discovery is not None:
        discovery.successful = False
    try:
        payload = find_workers(get_agent_roster(), query, limit)
    except (WorkerDiscoveryError, ValueError) as exc:
        return ToolResult(False, {"status": "unavailable", "error": str(exc)})
    if discovery is not None:
        discovery.successful = True
    return ToolResult(True, payload)


# Route tool calls to appropriate handlers with argument validation and error handling
def handle_tool_call(name: str, arguments: Any, *, discovery=None, recovery=None) -> ToolResult:
    """Handle tool calls from interaction agent."""
    if name == "find_worker" and discovery is not None:
        discovery.successful = False
    try:
        if isinstance(arguments, str):
            args = json.loads(arguments) if arguments.strip() else {}
        elif isinstance(arguments, dict):
            args = arguments
        else:
            return ToolResult(success=False, payload={"error": "Invalid arguments format"})

        if name in RECOVERY_NAMES:
            payload = handle_recovery_tool(name, args, expected_owner="conversation", budget=recovery)
            return ToolResult(payload.get("status") == "ok", payload)
        if name == "send_message_to_agent":
            return send_message_to_agent(**args, discovery=discovery)
        if name == "find_worker":
            return find_worker(**args, discovery=discovery)
        if name == "send_message_to_user":
            return send_message_to_user(**args)
        if name == "send_draft":
            return send_draft(**args)
        if name == "wait":
            return wait(**args)

        logger.warning("unexpected tool", extra={"tool": name})
        return ToolResult(success=False, payload={"error": f"Unknown tool: {name}"})
    except json.JSONDecodeError:
        return ToolResult(success=False, payload={"error": "Invalid JSON"})
    except TypeError as exc:
        return ToolResult(success=False, payload={"error": f"Missing required arguments: {exc}"})
    except ContentStoreError:
        raise
    except DraftReferenceError as exc:
        return ToolResult(False, {"error": str(exc), "status": "unavailable"})
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("tool call failed", extra={"tool": name, "error": str(exc)})
        return ToolResult(success=False, payload={"error": "Failed to execute"})
