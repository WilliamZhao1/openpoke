"""Text-request budgeting without changing or dropping caller content."""

from dataclasses import dataclass
import json


ESTIMATE_METHOD = "utf8_json_bytes_estimate"


class ContextBudgetError(RuntimeError):
    """A deterministic local rejection; retrying the same request will not help."""


@dataclass(frozen=True)
class BudgetEstimate:
    estimated_input_tokens: int
    input_limit: int
    context_window: int
    output_reservation: int
    headroom: int
    request_bytes: int
    method: str = ESTIMATE_METHOD


class ContextBudgetExceeded(ContextBudgetError):
    def __init__(self, estimate: BudgetEstimate):
        self.estimate = estimate
        super().__init__(
            f"Context input estimate {estimate.estimated_input_tokens} exceeds limit {estimate.input_limit} "
            f"({estimate.method}; output reservation {estimate.output_reservation}; headroom {estimate.headroom}). "
            "Request was not sent. Shorten the request before retrying."
        )


def _integer(value, label, *, minimum=1):
    if type(value) is not int or value < minimum:
        raise ContextBudgetError(f"{label} must be an integer of at least {minimum}")
    return value


def prepare_budgeted_request(payload, *, context_window, input_cap, headroom):
    """Return immutable wire bytes plus a content-free planning estimate.

    No native tokenizer is installed for the configured OpenRouter models. Count
    UTF-8 JSON bytes as estimated tokens, with extra framing allowances. This is
    intentionally conservative for text, not a provider-native count or a
    universal upper bound. Images/audio/files require different accounting.
    """
    _integer(context_window, "Configured model context allowance")
    _integer(input_cap, "Input cap")
    _integer(headroom, "Headroom", minimum=0)
    if not isinstance(payload, dict):
        raise ContextBudgetError("Context preflight requires a request object")
    reserved = _integer(payload.get("max_tokens"), "Output reservation")
    available = context_window - reserved - headroom
    if available < 1:
        raise ContextBudgetError("Context allowance must exceed output reservation plus headroom")
    messages, tools = payload.get("messages"), payload.get("tools", [])
    if not isinstance(messages, list) or any(not isinstance(message, dict) for message in messages):
        raise ContextBudgetError("Context preflight requires a list of messages")
    if not isinstance(tools, list) or any(not isinstance(tool, dict) for tool in tools):
        raise ContextBudgetError("Context preflight requires a list of tool schemas")
    for message in messages:
        if message.get("content") is not None and not isinstance(message["content"], str):
            raise ContextBudgetError("Text context preflight cannot account for structured media content")
    try:
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ContextBudgetError("Context preflight requires a valid UTF-8 JSON request") from exc
    # The full body covers system/history/current messages, call IDs/arguments,
    # results and schemas. Extra per-message/schema allowances cover framing.
    estimate = BudgetEstimate(
        estimated_input_tokens=len(body) + 32 + 16 * len(messages) + 32 * len(tools),
        input_limit=min(input_cap, available), context_window=context_window,
        output_reservation=reserved, headroom=headroom, request_bytes=len(body),
    )
    if estimate.estimated_input_tokens > estimate.input_limit:
        raise ContextBudgetExceeded(estimate)
    return body, estimate
