"""Email search task implementation."""

from __future__ import annotations

import json
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from server.config import get_settings
from server.logging_config import logger
from server.openrouter_client import ContextBudgetError, request_chat_completion
from server.services.execution import get_execution_agent_logs
from server.services.execution.log_store import preserve_worker_content
from server.content_store import ContentStoreError, current_capture, capture_scope
from server.context_builder import ContextBuilder, validate_tool_calls
from server.inner_context import SourceReader, READ_SCHEMA, INNER_POLICY, INNER_GUIDANCE, MAX_TOOL_CALLS, arguments as parse_inner_arguments, prefix
from server.services.gmail import (
    EmailTextCleaner,
    ProcessedEmail,
    execute_gmail_tool,
    get_active_gmail_user_id,
    parse_gmail_fetch_response,
)
from .gmail_internal import GMAIL_FETCH_EMAILS_SCHEMA
from .schemas import (
    GmailSearchEmail,
    EmailSearchToolResult,
    TaskEmailSearchPayload,
    COMPLETE_TOOL_NAME,
    SEARCH_TOOL_NAME,
    TASK_TOOL_NAME,
    get_completion_schema,
)
from .system_prompt import get_system_prompt
from server.services.gmail.processing import has_gmail_messages_response

# Constants
MAX_LLM_ITERATIONS = 8
ERROR_GMAIL_NOT_CONNECTED = "Gmail not connected. Please connect Gmail in settings first."
ERROR_OPENROUTER_NOT_CONFIGURED = "OpenRouter API key not configured. Set OPENROUTER_API_KEY."
ERROR_EMPTY_QUERY = "search_query must not be empty"
ERROR_QUERY_REQUIRED = "query parameter is required"
ERROR_MESSAGE_IDS_REQUIRED = "message_ids parameter is required"
ERROR_MESSAGE_IDS_MUST_BE_LIST = "message_ids must be provided as a list"
ERROR_TOOL_ARGUMENTS_INVALID = "Tool arguments must be an object"
ERROR_ITERATION_LIMIT = "Email search orchestrator exceeded iteration limit"



_COMPLETION_TOOL_SCHEMA = get_completion_schema()
_LOG_STORE = get_execution_agent_logs()
_EMAIL_CLEANER = EmailTextCleaner(max_url_length=40)


# Create standardized error response for tool calls
def _create_error_response(call_id: str, query: Optional[str], error: str) -> Tuple[str, str]:
    """Create standardized error response for tool calls."""
    result = EmailSearchToolResult(status="error", query=query, error=error)
    return (call_id, _safe_json_dumps(result.model_dump(exclude_none=True)))


# Create standardized success response for tool calls
def _create_success_response(call_id: str, data: Dict[str, Any]) -> Tuple[str, str]:
    """Create standardized success response for tool calls."""
    return (call_id, _safe_json_dumps(data))


def _validate_search_query(search_query: str) -> Optional[str]:
    """Validate search query and return error message if invalid."""
    if not (search_query or "").strip():
        return ERROR_EMPTY_QUERY
    return None


def _validate_gmail_connection() -> Optional[str]:
    """Validate Gmail connection and return user ID or None."""
    return get_active_gmail_user_id()


def _validate_openrouter_config() -> Tuple[Optional[str], Optional[str]]:
    """Validate OpenRouter configuration and return (api_key, model) or (None, error)."""
    settings = get_settings()
    api_key = settings.openrouter_api_key
    if not api_key:
        return None, ERROR_OPENROUTER_NOT_CONFIGURED
    return api_key, settings.execution_agent_search_model


# Return task tool callables
def build_registry(agent_name: str) -> Dict[str, Callable[..., Any]]:  # noqa: ARG001
    """Return task tool callables."""

    return {
        TASK_TOOL_NAME: task_email_search,
    }


# Run an agentic Gmail search for the provided query
async def task_email_search(search_query: str) -> Any:
    """Run an agentic Gmail search for the provided query."""
    logger.info(f"[EMAIL_SEARCH] Starting search for: '{search_query}'")
    
    # Validate inputs
    cleaned_query = (search_query or "").strip()
    if error := _validate_search_query(cleaned_query):
        logger.error(f"[EMAIL_SEARCH] Invalid query: {error}")
        return {"error": error}
    
    composio_user_id = _validate_gmail_connection()
    if not composio_user_id:
        logger.error(f"[EMAIL_SEARCH] Gmail not connected")
        return {"error": ERROR_GMAIL_NOT_CONNECTED}
    
    api_key, model_or_error = _validate_openrouter_config()
    if not api_key:
        logger.error(f"[EMAIL_SEARCH] OpenRouter not configured: {model_or_error}")
        return {"error": model_or_error}
    
    capture = current_capture()
    source_start = len(capture.sources) if capture is not None else 0
    try:
        preserve_worker_content(search_query, "task_email_search.arguments", provider="gmail", account_id=composio_user_id,
                                min_bytes=200, log_store=_LOG_STORE)
        result = await _run_email_search(
            search_query=cleaned_query,
            composio_user_id=composio_user_id,
            model=model_or_error,
            api_key=api_key,
        )
        if current_capture() is not None:
            preserve_worker_content(_safe_json_dumps(result), "task_email_search.result", provider="gmail",
                                    account_id=composio_user_id, log_store=_LOG_STORE)
        logger.info(f"[EMAIL_SEARCH] Found {len(result) if isinstance(result, list) else 0} emails")
        return result
    except ContentStoreError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception(f"[EMAIL_SEARCH] Search failed: {exc}")
        return {"error": f"Email search failed: {exc}"}
    finally:
        if capture is not None and capture.owner.startswith("worker:") and get_settings().context_strategy == "bounded":
            hints = capture.sources[source_start:]
            if len(hints) > 8:
                if current_capture() is not capture:
                    raise ContentStoreError("Search source hints changed ownership")
                # Keep all qualifications in one readable index, rather than
                # copying hundreds of descriptors into the parent model request.
                reference = preserve_worker_content(_safe_json_dumps({"source_references": hints}), "task_email_search.sources",
                                                    min_bytes=-1, log_store=_LOG_STORE)
                indexed = next(item for item in capture.sources[source_start:] if item["reference"] == reference)
                capture.sources[source_start:] = [indexed, *hints[-7:]]


# Execute the main email search orchestration loop
async def _run_email_search(
    *,
    search_query: str,
    composio_user_id: str,
    model: str,
    api_key: str,
) -> List[Dict[str, Any]]:
    """Execute the main email search orchestration loop."""
    if get_settings().context_strategy == "bounded":
        with nullcontext() if current_capture() is not None else capture_scope("conversation"):
            return await _run_bounded_search(search_query=search_query, composio_user_id=composio_user_id, model=model, api_key=api_key)
    messages: List[Dict[str, Any]] = [
        {"role": "user", "content": _render_user_message(search_query)}
    ]
    queries: List[str] = []
    emails: Dict[str, GmailSearchEmail] = {}
    selected_ids: Optional[List[str]] = None
    
    for iteration in range(MAX_LLM_ITERATIONS):
        logger.debug(
            "[task_email_search] LLM iteration",
            extra={"iteration": iteration + 1, "tool": TASK_TOOL_NAME},
        )
        
        # Get LLM response
        response = await request_chat_completion(
            component="search_email",
            model=model,
            messages=messages,
            system=get_system_prompt(),
            api_key=api_key,
            tools=[GMAIL_FETCH_EMAILS_SCHEMA, _COMPLETION_TOOL_SCHEMA],
        )
        
        # Process assistant response
        assistant = _extract_assistant_message(response)
        tool_calls = assistant.get("tool_calls") or []
        
        # Add assistant message to conversation
        assistant_entry = {
            "role": "assistant",
            "content": assistant.get("content", "") or "",
        }
        if tool_calls:
            assistant_entry["tool_calls"] = tool_calls
        messages.append(assistant_entry)
        
        # Handle case where LLM doesn't make tool calls
        if not tool_calls:
            logger.info(f"[EMAIL_SEARCH] LLM completed search - no more queries needed")
            selected_ids = []
            break
        
        # Execute tool calls and process responses
        tool_responses, completed_ids = await _execute_tool_calls(
            tool_calls=tool_calls,
            queries=queries,
            emails=emails,
            composio_user_id=composio_user_id,
        )
        
        # Add tool responses to conversation
        for call_id, content in tool_responses:
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": content,
            })
        
        # Check if search is complete
        if completed_ids is not None:
            logger.info(f"[EMAIL_SEARCH] Search completed - selected {len(completed_ids)} emails")
            selected_ids = completed_ids
            break
    else:
        logger.error(f"[EMAIL_SEARCH] {ERROR_ITERATION_LIMIT}")
        raise RuntimeError(ERROR_ITERATION_LIMIT)
    
    final_result = _build_response(queries, emails, selected_ids or [])
    unique_queries = list(dict.fromkeys(queries))
    logger.info(f"[EMAIL_SEARCH] Completed - {len(unique_queries)} queries executed, {len(final_result)} emails selected")
    return final_result


@dataclass
class _SearchWork:
    reader: SourceReader
    calls: int = 0
    successful: int = 0
    retained_bytes: int = 0


async def _run_bounded_search(*, search_query, composio_user_id, model, api_key):
    reader = SourceReader()
    reader.save(search_query, "task_email_search.arguments", provider="gmail", account_id=composio_user_id)
    schema = deepcopy(GMAIL_FETCH_EMAILS_SCHEMA)
    schema["function"]["parameters"]["properties"]["page_token"] = {"type": "string", "description": "Exact pagination token for the same query/account."}
    schemas = [schema, _COMPLETION_TOOL_SCHEMA, READ_SCHEMA]
    builder = ContextBuilder(settings=get_settings(), model=model, tools=schemas, record_reference=reader.record,
                             policy=INNER_POLICY, guidance=INNER_GUIDANCE)
    messages = [{"role": "user", "content": _render_user_message(search_query) + f"\nProvider: gmail; executed account: {composio_user_id}"}]
    work, queries, emails = _SearchWork(reader), [], {}
    for _ in range(MAX_LLM_ITERATIONS):
        system, prepared = builder.build(get_system_prompt(), messages)
        response = await request_chat_completion(component="search_email", model=model, messages=prepared,
                                                system=system + "\n\n" + INNER_GUIDANCE, api_key=api_key, tools=schemas)
        assistant = _extract_assistant_message(response)
        calls = assistant.get("tool_calls") or []
        validate_tool_calls(calls)
        if not calls or len(calls) > MAX_TOOL_CALLS:
            raise ContextBudgetError("Search requires an explicit completion after a successful lookup; tool/call limit reached")
        messages.append({"role": "assistant", "content": assistant.get("content") or "", "tool_calls": calls})
        completed = None
        for call in calls:
            name = call["function"]["name"]
            args = parse_inner_arguments(call["function"].get("arguments"))
            payload = {"status": "error", "error": "Invalid or unsupported search tool arguments"}
            if name == COMPLETE_TOOL_NAME:
                if len(calls) != 1:
                    payload = {"status": "error", "error": "Complete in a separate call after reading search results"}
                elif (args is not None and work.successful and isinstance(args.get("message_ids"), list)
                      and all(isinstance(item, str) and item in emails for item in args["message_ids"])):
                    completed = list(dict.fromkeys(args["message_ids"]))
                    payload = {"status": "success", "message_ids": completed}
                else:
                    payload = {"status": "error", "error": "Lookup failed or selected IDs are unknown; this is not a successful empty search"}
            elif name == "read_result":
                payload = reader.read(args)
            elif name == SEARCH_TOOL_NAME and args is not None and not any(c["function"]["name"] == COMPLETE_TOOL_NAME for c in calls):
                result = await _perform_search(arguments=args, queries=queries, emails=emails,
                                               composio_user_id=composio_user_id, work=work)
                payload = result.model_dump(mode="json", exclude_none=True)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": _safe_json_dumps(payload)})
        if completed is not None:
            reader.check()
            return [emails[identifier].model_dump(mode="json", exclude_none=True) for identifier in completed]
        reader.prune(messages)
    raise ContextBudgetError("Email search exhausted its existing iteration budget; results remain available through saved sources")




# Create user message for the LLM with search context
def _render_user_message(search_query: str) -> str:
    """Create user message for the LLM with search context."""
    return f"Please help me find emails: {search_query}"


# Execute tool calls from LLM and process search/completion responses
async def _execute_tool_calls(
    *,
    tool_calls: List[Dict[str, Any]],
    queries: List[str],
    emails: Dict[str, GmailSearchEmail],
    composio_user_id: str,
) -> Tuple[List[Tuple[str, str]], Optional[List[str]]]:
    responses: List[Tuple[str, str]] = []
    completion_ids: Optional[List[str]] = None

    for call in tool_calls:
        call_id = call.get("id") or SEARCH_TOOL_NAME
        function = call.get("function") or {}
        name = function.get("name") or ""
        raw_arguments = function.get("arguments", {})
        arguments, parse_error = _parse_arguments(raw_arguments)

        if parse_error:
            # Handle argument parsing errors
            query = arguments.get("query") if arguments else None
            logger.warning(f"[EMAIL_SEARCH] Tool argument parsing failed: {parse_error}")
            responses.append(_create_error_response(call_id, query, parse_error))

        elif name == COMPLETE_TOOL_NAME:
            # Handle completion tool - signals end of search
            completion_ids_candidate, response_data = _handle_completion_tool(arguments)
            responses.append(_create_success_response(call_id, response_data))
            if completion_ids_candidate is not None:
                logger.info(f"[EMAIL_SEARCH] LLM selected {len(completion_ids_candidate)} emails")
                completion_ids = completion_ids_candidate
                break

        elif name == SEARCH_TOOL_NAME:
            # Handle Gmail search tool
            search_query = arguments.get("query", "<unknown>")
            logger.info(f"[SEARCH_QUERY] LLM generated query: '{search_query}'")
            
            result_model = await _perform_search(
                arguments=arguments,
                queries=queries,
                emails=emails,
                composio_user_id=composio_user_id,
            )
            response_data = result_model.model_dump(exclude_none=True)
            
            if result_model.status == "success":
                count = result_model.result_count or 0
                logger.info(f"[SEARCH_RESULT] Query '{search_query}' → {count} emails found")
            else:
                logger.warning(f"[SEARCH_RESULT] Query '{search_query}' → FAILED: {result_model.error}")
            
            responses.append(_create_success_response(call_id, response_data))

        else:
            # Handle unsupported tools
            query = arguments.get("query")
            error = f"Unsupported tool: {name}"
            logger.warning(f"[EMAIL_SEARCH] Unsupported tool: {name}")
            responses.append(_create_error_response(call_id, query, error))

    return responses, completion_ids


# Perform Gmail search using Composio and process results
async def _perform_search(
    *,
    arguments: Dict[str, Any],
    queries: List[str],
    emails: Dict[str, GmailSearchEmail],
    composio_user_id: str,
    work: Optional[_SearchWork] = None,
) -> EmailSearchToolResult:
    query = (arguments.get("query") or "").strip()
    if not query:
        logger.warning(f"[EMAIL_SEARCH] Search called with empty query")
        return EmailSearchToolResult(
            status="error",
            error=ERROR_QUERY_REQUIRED,
        )

    # Use LLM-provided max_results or default to 10
    max_results = arguments.get("max_results", 10)
    if work is not None:
        if work.calls >= 8:
            raise ContextBudgetError("Email search cumulative query limit reached; lookup is incomplete")
        work.calls += 1
        if type(max_results) is not int or not isinstance(arguments.get("page_token", ""), str) or len(arguments.get("page_token", "")) > 2048:
            return EmailSearchToolResult(status="error", query=query, error="Invalid result count or page token")
        max_results = min(20, max(1, max_results))
    
    composio_arguments = {
        "query": query,
        "max_results": max_results,  # Use LLM-provided value or default 10
        "include_payload": True,  # REQUIRED: Need full email content for text cleaning
        "verbose": True,  # REQUIRED: Need parsed content including messageText
        "include_spam_trash": arguments.get("include_spam_trash", False),  # Default: False
        "format": "full",  # Request full email format
        "metadata_headers": ["From", "To", "Subject", "Date"],  # Ensure we get key headers
    }
    if work is not None and arguments.get("page_token"):
        composio_arguments["page_token"] = arguments["page_token"]

    _LOG_STORE.record_action(
        TASK_TOOL_NAME,
        description=f"{TASK_TOOL_NAME} search | query={query} | max_results={max_results}",
    )

    try:
        raw_result = execute_gmail_tool(
            "GMAIL_FETCH_EMAILS",
            composio_user_id,
            arguments=composio_arguments,
        )
    except ContentStoreError:
        raise
    except Exception as exc:
        logger.error(f"[EMAIL_SEARCH] Gmail API failed for '{query}': {exc}")
        return EmailSearchToolResult(
            status="error",
            query=query,
            error=str(exc),
        )

    source_reference = None
    if work is not None:
        source_reference = work.reader.save(_safe_json_dumps(raw_result), "GMAIL_FETCH_EMAILS.result", provider="gmail", account_id=composio_user_id)
        if not has_gmail_messages_response(raw_result):
            return EmailSearchToolResult(status="error", query=query, error="Gmail lookup failed or returned no recognizable result; not an empty success", source_reference=source_reference)
    elif current_capture() is not None:
        preserve_worker_content(_safe_json_dumps(raw_result), "GMAIL_FETCH_EMAILS.result", provider="gmail",
                                account_id=composio_user_id, log_store=_LOG_STORE)
    processed_emails, next_page_token = parse_gmail_fetch_response(
        raw_result,
        query=query,
        cleaner=_EMAIL_CLEANER, **({"max_messages": 20} if work is not None else {}),
    )
    parsed_emails = [_processed_to_schema(email) for email in processed_emails]
    if work is not None:
        bounded = []
        for email in parsed_emails:
            original = _safe_json_dumps(email.model_dump(mode="json", exclude_none=True))
            reference = work.reader.save(original, "email_search.email", provider="gmail", account_id=composio_user_id) if len(email.clean_text.encode()) > 1024 else None
            item = email.model_copy(update={"clean_text": prefix(email.clean_text, 1024), "content_reference": reference,
                                           "source_reference": source_reference, "content_complete": reference is None,
                                           "provider": "gmail", "account_id": composio_user_id})
            if item.id not in emails:
                size = len(_safe_json_dumps(item.model_dump(mode="json", exclude_none=True)).encode())
                if len(emails) >= 100 or work.retained_bytes + size > 256 * 1024:
                    work.reader.save(original, "email_search.email", provider="gmail", account_id=composio_user_id)
                    raise ContextBudgetError("Email search cumulative cache limit reached; full source saved, selection incomplete")
                work.retained_bytes += size
                emails[item.id] = item
            bounded.append(item)
        parsed_emails = bounded
        work.successful += 1

    queries.append(query)
    for email in parsed_emails:
        if email.id not in emails:
            emails[email.id] = email

    return EmailSearchToolResult(
        status="success",
        query=query,
        result_count=len(parsed_emails),
        next_page_token=next_page_token,
        messages=parsed_emails,
        source_reference=source_reference,
        limitation="Bodies may be previews; use content_reference/raw source for omitted details. At most 20 messages processed per query; refine or page for more." if work is not None else None,
    )


# Build final response with selected emails and logging
def _build_response(
    queries: List[str],
    emails: Dict[str, GmailSearchEmail],
    selected_ids: Sequence[str],
) -> List[Dict[str, Any]]:
    # Deduplicate queries while preserving order
    unique_queries = list(dict.fromkeys(queries))
    
    # Deduplicate and filter valid email IDs efficiently
    valid_ids = [id.strip() for id in selected_ids if id and id.strip()]
    unique_ids = list(dict.fromkeys(valid_ids))
    selected_emails = [emails[id] for id in unique_ids if id in emails]
    
    # Log any missing email IDs
    missing_ids = [id for id in unique_ids if id not in emails]
    if missing_ids:
        logger.warning(f"[EMAIL_SEARCH] {len(missing_ids)} selected email IDs not found")
    
    payload = TaskEmailSearchPayload(emails=selected_emails)
    
    _LOG_STORE.record_action(
        TASK_TOOL_NAME,
        description=(
            f"{TASK_TOOL_NAME} completed | queries={len(unique_queries)} "
            f"| emails={len(selected_emails)}"
        ),
    )
    
    return [email.model_dump(exclude_none=True) for email in payload.emails]


def _extract_assistant_message(response: Dict[str, Any]) -> Dict[str, Any]:
    """Extract assistant message from OpenRouter API response."""
    return response.get("choices", [{}])[0].get("message", {})


def _parse_arguments(raw_arguments: Any) -> Tuple[Dict[str, Any], Optional[str]]:
    """Parse tool arguments with proper error handling."""
    if isinstance(raw_arguments, dict):
        return raw_arguments, None
    if isinstance(raw_arguments, str):
        if not raw_arguments.strip():
            return {}, None
        try:
            return json.loads(raw_arguments), None
        except json.JSONDecodeError as exc:
            return {}, f"Failed to parse tool arguments: {exc}"
    return {}, ERROR_TOOL_ARGUMENTS_INVALID



def _handle_completion_tool(arguments: Dict[str, Any]) -> Tuple[Optional[List[str]], Dict[str, Any]]:
    """Handle completion tool call, parsing message IDs and returning response."""
    raw_ids = arguments.get("message_ids")
    if raw_ids is None:
        return None, {"status": "error", "error": ERROR_MESSAGE_IDS_REQUIRED}
    if not isinstance(raw_ids, list):
        return None, {"status": "error", "error": ERROR_MESSAGE_IDS_MUST_BE_LIST}
    
    # Filter out empty/invalid IDs efficiently
    message_ids = [str(value).strip() for value in raw_ids if str(value).strip()]
    
    return message_ids, {"status": "success", "message_ids": message_ids}


def _safe_json_dumps(payload: Any) -> str:
    """Safely serialize payload to JSON string."""
    try:
        return json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps({"repr": repr(payload)})





def _processed_to_schema(email: ProcessedEmail) -> GmailSearchEmail:
    """Convert shared processed email into GmailSearchEmail schema."""

    return GmailSearchEmail(
        id=email.id,
        thread_id=email.thread_id,
        query=email.query,
        subject=email.subject,
        sender=email.sender,
        recipient=email.recipient,
        timestamp=email.timestamp,
        label_ids=list(email.label_ids),
        clean_text=email.clean_text,
        has_attachments=email.has_attachments,
        attachment_count=email.attachment_count,
        attachment_filenames=list(email.attachment_filenames),
    )


__all__ = [
    "GmailSearchEmail",
    "EmailSearchToolResult",
    "build_registry",
    "task_email_search",
]
