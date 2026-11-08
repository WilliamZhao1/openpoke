from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
import json
from time import perf_counter
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from ..config import get_settings
from ..observability import (
    Availability, EvidenceMode, Observation, ObservationReason, ObservationSource,
    record_event, traced,
)

OpenRouterBaseURL = "https://openrouter.ai/api/v1"
_mock_transport: ContextVar[Optional[httpx.MockTransport]] = ContextVar("openrouter_mock_transport", default=None)


@contextmanager
def use_mock_provider(transport: httpx.MockTransport):
    """Bind a local provider transport and its mock provenance together.

    Tasks inherit this binding. Mock failure propagates through normal error
    handling; it never selects a live transport as an automatic fallback.
    """
    if not isinstance(transport, httpx.MockTransport):
        raise TypeError("Mock provider requires httpx.MockTransport")
    token = _mock_transport.set(transport)
    try:
        yield
    finally:
        _mock_transport.reset(token)


def get_provider_mode() -> EvidenceMode:
    return EvidenceMode.MOCK if _mock_transport.get() is not None else EvidenceMode.LIVE


class OpenRouterError(RuntimeError):
    """Raised when the OpenRouter API returns an error response."""


def _headers(*, api_key: Optional[str] = None) -> Dict[str, str]:
    settings = get_settings()
    key = (api_key or settings.openrouter_api_key or "").strip()
    if not key:
        raise OpenRouterError("Missing OpenRouter API key")

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    return headers


def _build_messages(messages: List[Dict[str, str]], system: Optional[str]) -> List[Dict[str, str]]:
    if system:
        return [{"role": "system", "content": system}, *messages]
    return messages


def _handle_response_error(exc: httpx.HTTPStatusError) -> None:
    response = exc.response
    detail: str
    try:
        payload = response.json()
        detail = payload.get("error") or payload.get("message") or json.dumps(payload)
        if isinstance(detail, dict):
            detail = detail.get("message") or json.dumps(detail)
    except Exception:
        detail = response.text
    raise OpenRouterError(f"OpenRouter request failed ({response.status_code}): {detail}") from exc


def _usage_observation(
    usage: Any, key: str, *, request_started: bool, failure: Optional[str], mode: EvidenceMode,
) -> Observation:
    source = ObservationSource.PROVIDER_USAGE
    if not request_started:
        return Observation(None, Availability.NOT_APPLICABLE, source, mode, ObservationReason.REQUEST_NOT_SENT)
    if isinstance(usage, dict) and key in usage:
        value = usage[key]
        if type(value) is int and value >= 0:
            return Observation(value, Availability.AVAILABLE, source, mode)
        reason = ObservationReason.USAGE_VALUE_INVALID
    elif failure:
        reason = ObservationReason.RESPONSE_INVALID if failure == "invalid_response" else ObservationReason.REQUEST_FAILED
    elif usage is None:
        reason = ObservationReason.USAGE_MISSING
    elif not isinstance(usage, dict):
        reason = ObservationReason.USAGE_INVALID
    else:
        reason = ObservationReason.USAGE_FIELD_MISSING
    return Observation(None, Availability.UNAVAILABLE, source, mode, reason)


def _http_failure(status_code: int) -> str:
    if status_code in {401, 403}:
        return "authentication"
    if status_code == 429:
        return "rate_limit"
    return "provider_server" if status_code >= 500 else "provider_request"


@traced()
async def request_chat_completion(
    *,
    model: str,
    messages: List[Dict[str, str]],
    system: Optional[str] = None,
    api_key: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    base_url: str = OpenRouterBaseURL,
    component: str = "unspecified",
) -> Dict[str, Any]:
    """Return raw provider JSON and record metadata for each call attempt."""
    started = perf_counter()
    call_id = str(uuid4())
    result = None
    status_code = None
    failure = None
    stage = "configuration"
    request_started = False
    transport = _mock_transport.get()
    mode = get_provider_mode()
    try:
        payload: Dict[str, object] = {
            "model": model,
            "messages": _build_messages(messages, system),
            "stream": False,
            "max_tokens": get_settings().openrouter_max_tokens,
        }
        if tools:
            payload["tools"] = tools
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = _headers(api_key=api_key)
        stage = "internal"
        client_options = {"transport": transport} if transport is not None else {}
        async with httpx.AsyncClient(**client_options) as client:
            request_started = True
            response = await client.post(
                url,
                headers=headers,
                json=payload,
                timeout=60.0,
            )
            status_code = response.status_code
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                failure = _http_failure(status_code)
                _handle_response_error(exc)
            stage = "invalid_response"
            result = response.json()
            # Preserve the raw return contract, including malformed/error payloads.
            if not isinstance(result, dict) or not result.get("choices"):
                failure = "provider_error" if isinstance(result, dict) and result.get("error") else "invalid_response"
            return result
    except asyncio.CancelledError:
        failure = "cancelled"
        raise
    except httpx.TimeoutException as exc:
        failure = "timeout"
        raise OpenRouterError(f"OpenRouter request failed: {exc}") from exc
    except httpx.HTTPError as exc:
        failure = "network"
        raise OpenRouterError(f"OpenRouter request failed: {exc}") from exc
    except Exception:
        failure = failure or stage
        raise
    finally:
        usage = result.get("usage") if isinstance(result, dict) else None
        input_tokens = _usage_observation(usage, "prompt_tokens", request_started=request_started, failure=failure, mode=mode)
        output_tokens = _usage_observation(usage, "completion_tokens", request_started=request_started, failure=failure, mode=mode)
        if status_code is not None:
            status = Observation(status_code, Availability.AVAILABLE, ObservationSource.HTTP_RESPONSE, mode)
        else:
            status = Observation(
                None, Availability.UNAVAILABLE if request_started else Availability.NOT_APPLICABLE,
                ObservationSource.HTTP_RESPONSE, mode,
                ObservationReason.NO_HTTP_RESPONSE if request_started else ObservationReason.REQUEST_NOT_SENT,
            )
        coverage = Observation(
            input_tokens.availability == Availability.AVAILABLE and output_tokens.availability == Availability.AVAILABLE,
            Availability.INFERRED, ObservationSource.DERIVED,
            evidence=("input_tokens", "output_tokens"),
        )
        record_event(
            "model_call.completed", component=component, model=model, call_id=call_id,
            outcome="failed" if failure else "succeeded", failure_category=failure,
            elapsed_ms=(perf_counter() - started) * 1000, provider_mode=mode,
            observations={
                "input_tokens": input_tokens, "output_tokens": output_tokens,
                "status_code": status, "usage_complete": coverage,
            },
        )


__all__ = [
    "OpenRouterError", "request_chat_completion", "OpenRouterBaseURL",
    "use_mock_provider", "get_provider_mode",
]
