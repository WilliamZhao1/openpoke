"""Aggregate execution agent tool schemas and registries."""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from . import gmail, triggers
from ..tasks import get_task_registry, get_task_schemas
from ....config import get_settings
from ....context_recovery import SCHEMAS as RECOVERY_SCHEMAS, build_registry as recovery_registry


# Return OpenAI/OpenRouter-compatible tool schemas
def get_tool_schemas(*, bounded_context=None) -> List[Dict[str, Any]]:
    """Return OpenAI/OpenRouter-compatible tool schemas."""

    bounded_context = get_settings().context_strategy == "bounded" if bounded_context is None else bounded_context
    return [
        *gmail.get_schemas(),
        *get_task_schemas(),
        *triggers.get_schemas(),
        *(RECOVERY_SCHEMAS if bounded_context else []),
    ]


# Return Python callables for executing tools by name
def get_tool_registry(agent_name: str, *, bounded_context=None) -> Dict[str, Callable[..., Any]]:
    """Return Python callables for executing tools by name."""

    registry: Dict[str, Callable[..., Any]] = {}
    registry.update(gmail.build_registry(agent_name))
    registry.update(get_task_registry(agent_name))
    registry.update(triggers.build_registry(agent_name))
    bounded_context = get_settings().context_strategy == "bounded" if bounded_context is None else bounded_context
    if bounded_context:
        registry.update(recovery_registry(f"worker:{agent_name}"))
    return registry


__all__ = [
    "get_tool_registry",
    "get_tool_schemas",
]
