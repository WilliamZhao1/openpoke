"""Content-free telemetry and task-local correlation for asynchronous work."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from functools import wraps
import json
import sys
from time import perf_counter
from typing import Iterator, Optional
from uuid import uuid4

from .logging_config import logger


@dataclass(frozen=True)
class TraceContext:
    request_id: str
    turn_id: str
    origin: str
    parent_turn_id: Optional[str] = None
    batch_id: Optional[str] = None
    run_id: Optional[str] = None
    trigger_id: Optional[int] = None


_trace: ContextVar[Optional[TraceContext]] = ContextVar("openpoke_trace", default=None)
_METRIC_FIELDS = frozenset({
    "outcome", "failure_category", "elapsed_ms", "model", "call_id",
    "input_tokens", "output_tokens", "usage_complete", "status_code",
    "tool_name", "parents",
})


def get_trace_context() -> Optional[TraceContext]:
    return _trace.get()


@contextmanager
def trace_scope(
    *,
    context: Optional[TraceContext] = None,
    origin: Optional[str] = None,
    new_request: bool = False,
    new_turn: bool = False,
    **updates,
) -> Iterator[TraceContext]:
    """Bind immutable metadata; asyncio tasks inherit their own context copy."""
    current = context or _trace.get()
    if current is None or new_request:
        current = TraceContext(str(uuid4()), str(uuid4()), origin or "internal")
    else:
        if origin is not None:
            current = replace(current, origin=origin)
        if new_turn:
            current = replace(current, turn_id=str(uuid4()), parent_turn_id=current.turn_id)
    current = replace(current, **updates)
    token = _trace.set(current)
    try:
        yield current
    finally:
        _trace.reset(token)


def traced(**scope_options):
    """Ensure an async entry point has a trace, restoring its caller on exit."""
    def decorate(function):
        @wraps(function)
        async def wrapped(*args, **kwargs):
            with trace_scope(**scope_options):
                return await function(*args, **kwargs)
        return wrapped
    return decorate


def record_event(event: str, *, component: str, **metrics) -> None:
    """Emit JSON to the existing logger, accepting only metadata field names.

    Do not pass content through event/component/model/tool names. Callers use
    fixed component/tool names, configured model IDs, and backend-generated IDs.
    Error messages, arguments, responses, and credentials are never copied here.
    """
    context = get_trace_context()
    record = {
        "schema_version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "component": component,
        **(asdict(context) if context else {}),
        **{key: value for key, value in metrics.items() if key in _METRIC_FIELDS},
    }
    try:
        logger.info("telemetry %s", json.dumps(record, sort_keys=True), extra={"telemetry": record})
    except Exception:
        # A broken log sink must not mask provider errors or repeat a tool action.
        try:
            sys.stderr.write("OpenPoke telemetry emission failed\n")
        except Exception:
            pass


@dataclass
class ToolObservation:
    success: bool = False


@contextmanager
def observe_tool(component: str, tool_name: str) -> Iterator[ToolObservation]:
    started = perf_counter()
    observation = ToolObservation()
    failure = "tool_error"
    try:
        yield observation
    except asyncio.CancelledError:
        failure = "cancelled"
        raise
    finally:
        record_event(
            "tool.completed", component=component, tool_name=tool_name,
            outcome="succeeded" if observation.success else "failed",
            failure_category=None if observation.success else failure,
            elapsed_ms=(perf_counter() - started) * 1000,
        )
