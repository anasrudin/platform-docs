"""Workflow models — DAGWorkflow, WorkflowStep, StepResult."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WorkflowStep:
    id: str
    tool: str
    input: dict
    depends_on: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "tool": self.tool,
            "input": self.input,
            "depends_on": self.depends_on,
        }


@dataclass
class StepResult:
    step_id: str
    status: StepStatus = StepStatus.PENDING
    output: dict | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def duration_ms(self) -> int | None:
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return None

    def as_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass
class DAGWorkflow:
    id: str
    name: str
    steps: list[WorkflowStep]
    timeout: int = 600
    tenant_id: str = "default"
    status: WorkflowStatus = field(default=WorkflowStatus.PENDING)
    results: dict[str, StepResult] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "workflow_id": self.id,
            "name": self.name,
            "status": self.status.value,
            "tenant_id": self.tenant_id,
            "steps": {
                r.step_id: r.as_dict()
                for r in self.results.values()
            },
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }
