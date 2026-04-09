"""Hibernation domain models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class HibernateState(str, Enum):
    ACTIVE = "active"
    HIBERNATING = "hibernating"
    HIBERNATED = "hibernated"
    RESTORING = "restoring"


@dataclass
class HibernateSnapshot:
    session_id: str
    snapshot_key: str           # storage prefix: hibernate/{session_id}/
    hibernated_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None


@dataclass
class RestoreResult:
    session_id: str
    restored_from: str
    restore_ms: int
