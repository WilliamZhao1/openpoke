"""Content-free telemetry and task-local correlation for asynchronous work."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from functools import wraps
from enum import Enum
import json
import math
import sys
from time import perf_counter
from typing import Iterator, Mapping, Optional, Union
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
    "tool_name", "parents", "provider_mode",
})
_OBSERVATION_FIELDS = frozenset({
    "outcome", "failure_category", "elapsed_ms", "input_tokens",
    "output_tokens", "usage_complete", "status_code",
})


class Availability(str, Enum):
    AVAILABLE = "available"
    INFERRED = "inferred"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"


class EvidenceMode(str, Enum):
    LOCAL = "local"
    LIVE = "live"
    MOCK = "mock"


class ObservationSource(str, Enum):
    RUNTIME = "runtime"
    CLOCK = "monotonic_clock"
    PROVIDER_USAGE = "provider_usage"
    HTTP_RESPONSE = "http_response"
    DERIVED = "derived"


class ObservationReason(str, Enum):
    NOT_RECORDED = "not_recorded"
    NO_FAILURE = "no_failure"
    REQUEST_NOT_SENT = "request_not_sent"
    NO_HTTP_RESPONSE = "no_http_response"
    REQUEST_FAILED = "request_failed"
    RESPONSE_INVALID = "response_invalid"
    USAGE_MISSING = "usage_missing"
    USAGE_INVALID = "usage_invalid"
    USAGE_FIELD_MISSING = "usage_field_missing"
    USAGE_VALUE_INVALID = "usage_value_invalid"


@dataclass(frozen=True)
class Observation:
    """One scalar with availability and bounded provenance, independent of success."""

    value: Union[str, int, float, bool, None]
    availability: Availability
    source: ObservationSource
    source_mode: EvidenceMode = EvidenceMode.LOCAL
    reason: Optional[ObservationReason] = None
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Normalize enum inputs and reject arbitrary free-text reasons/sources.
        for name, enum in (
            ("availability", Availability), ("source", ObservationSource),
            ("source_mode", EvidenceMode),
        ):
            object.__setattr__(self, name, enum(getattr(self, name)))
        if self.reason is not None:
            object.__setattr__(self, "reason", ObservationReason(self.reason))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        if self.value is not None and type(self.value) not in {str, int, float, bool}:
            raise ValueError("Observation values must be scalars")
        if type(self.value) is float and not math.isfinite(self.value):
            raise ValueError("Observation values must be finite")
        missing = self.availability in {Availability.UNAVAILABLE, Availability.NOT_APPLICABLE}
        if missing and (self.value is not None or self.reason is None):
            raise ValueError("Unavailable/inapplicable observations require a null value and reason")
        if not missing and (self.value is None or self.reason is not None):
            raise ValueError("Available/inferred observations require a value and no missing-data reason")
        if any(field not in _OBSERVATION_FIELDS for field in self.evidence):
            raise ValueError("Observation evidence must name known metric fields")
        if self.availability == Availability.INFERRED:
            if self.source != ObservationSource.DERIVED or not self.evidence:
                raise ValueError("Inferred observations require a derivation source and evidence")
        elif self.evidence or self.source == ObservationSource.DERIVED:
            raise ValueError("Only inferred observations may have derivation evidence")
        if self.source in {ObservationSource.PROVIDER_USAGE, ObservationSource.HTTP_RESPONSE}:
            if self.source_mode == EvidenceMode.LOCAL:
                raise ValueError("Provider observations require an explicit live/mock source mode")
        if self.source == ObservationSource.CLOCK and self.source_mode != EvidenceMode.LOCAL:
            raise ValueError("The monotonic clock is a local observation")


def _runtime_observation(field: str, value, *, outcome=None) -> Observation:
    source = ObservationSource.CLOCK if field == "elapsed_ms" else ObservationSource.RUNTIME
    if value is None:
        if field == "failure_category" and outcome == "succeeded":
            return Observation(None, Availability.NOT_APPLICABLE, source, reason=ObservationReason.NO_FAILURE)
        return Observation(None, Availability.UNAVAILABLE, source, reason=ObservationReason.NOT_RECORDED)
    return Observation(value, Availability.AVAILABLE, source)


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


def record_event(
    event: str, *, component: str,
    observations: Optional[Mapping[str, Observation]] = None,
    **metrics,
) -> None:
    """Emit JSON to the existing logger, accepting only metadata field names.

    Do not pass content through event/component/model/tool names. Callers use
    fixed component/tool names, configured model IDs, and backend-generated IDs.
    Error messages, arguments, responses, and credentials are never copied here.
    """
    try:
        context = get_trace_context()
        fields = {key: value for key, value in metrics.items() if key in _METRIC_FIELDS}
        measured = {
            key: _runtime_observation(key, value, outcome=fields.get("outcome"))
            for key, value in fields.items() if key in _OBSERVATION_FIELDS
        }
        for key, observation in (observations or {}).items():
            if key in _OBSERVATION_FIELDS:
                measured[key] = observation
                # Preserve the original scalar fields for existing log consumers.
                fields[key] = observation.value
        for observation in measured.values():
            if any(field not in measured for field in observation.evidence):
                raise ValueError("Derivation evidence must exist in the same event")
        record = {
            "schema_version": 2,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "component": component,
            **(asdict(context) if context else {}),
            **fields,
            "observations": {key: asdict(value) for key, value in measured.items()},
        }
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
