"""AuditEvent model — immutable record of privileged operations."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class AuditEvent:
    actor: str
    action: str
    resource: str
    outcome: str
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "actor": self.actor,
            "action": self.action,
            "resource": self.resource,
            "outcome": self.outcome,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }
