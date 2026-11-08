"""Immutable workflow identities, independent of execution-run outcomes."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID


class WorkflowStatus(str, Enum):
    OPEN = "open"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    WAITING_FOR_EXTERNAL_EVENT = "waiting_for_external_event"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


def require_text(value: str, *, nonempty=False) -> str:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        raise ValueError("Expected a nonempty string" if nonempty else "Expected a string")
    # Preserve exact spelling, case, Unicode, and whitespace for legacy aliases.
    return value


def require_revision(value: int) -> int:
    if type(value) is not int or value < 1:
        raise ValueError("Workflow revision must be a positive integer")
    return value


def utc_datetime(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Workflow timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def encode_timestamp(value: datetime) -> str:
    return utc_datetime(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def decode_timestamp(value: str) -> datetime:
    return utc_datetime(datetime.fromisoformat(value.replace("Z", "+00:00")))


@dataclass(frozen=True)
class Workflow:
    workflow_id: UUID
    scope: str
    generation_id: UUID
    display_name: str
    purpose: str
    summary: str
    status: Optional[WorkflowStatus]
    created_at: datetime
    last_activity_at: datetime
    archived_at: Optional[datetime]
    revision: int

    def __post_init__(self):
        for field in ("workflow_id", "generation_id"):
            object.__setattr__(self, field, UUID(str(getattr(self, field))))
        require_text(self.scope, nonempty=True)
        require_text(self.display_name, nonempty=True)
        require_text(self.purpose)
        require_text(self.summary)
        require_revision(self.revision)
        if self.status is not None:
            object.__setattr__(self, "status", WorkflowStatus(self.status))
        for field in ("created_at", "last_activity_at"):
            object.__setattr__(self, field, utc_datetime(getattr(self, field)))
        if self.archived_at is not None:
            object.__setattr__(self, "archived_at", utc_datetime(self.archived_at))
        if self.last_activity_at < self.created_at:
            raise ValueError("Workflow activity cannot precede creation")


@dataclass(frozen=True)
class WorkflowAlias:
    workflow_id: UUID
    scope: str
    generation_id: UUID
    alias: str
    created_at: datetime

    def __post_init__(self):
        object.__setattr__(self, "workflow_id", UUID(str(self.workflow_id)))
        object.__setattr__(self, "generation_id", UUID(str(self.generation_id)))
        require_text(self.scope, nonempty=True)
        require_text(self.alias)
        object.__setattr__(self, "created_at", utc_datetime(self.created_at))
