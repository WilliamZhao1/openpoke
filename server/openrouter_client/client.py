from __future__ import annotations

import asyncio
import json
from time import perf_counter
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from ..config import get_settings
from ..observability import record_event, traced

OpenRouterBaseURL = "https://openrouter.ai/api/v1"


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


def _usage_count(usage: Any, key: str) -> Optional[int]:
    value = usage.get(key) if isinstance(usage, dict) else None
    return value if type(value) is int and value >= 0 else None


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
        async with httpx.AsyncClient() as client:
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
        input_tokens = _usage_count(usage, "prompt_tokens")
        output_tokens = _usage_count(usage, "completion_tokens")
        record_event(
            "model_call.completed", component=component, model=model, call_id=call_id,
            outcome="failed" if failure else "succeeded", failure_category=failure,
            elapsed_ms=(perf_counter() - started) * 1000, status_code=status_code,
            input_tokens=input_tokens, output_tokens=output_tokens,
            usage_complete=input_tokens is not None and output_tokens is not None,
        )


__all__ = ["OpenRouterError", "request_chat_completion", "OpenRouterBaseURL"]
