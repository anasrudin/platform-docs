"""Job and execution models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from models.session import Tier


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    session_id: str
    tool: str
    tier: Tier
    input: dict[str, Any]
    status: JobStatus
    output: str = ""
    error_message: str = ""
    duration_ms: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ExecuteRequest:
    tool: str
    session_id: str = ""
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecuteResponse:
    job_id: str
    status: JobStatus
    output: str = ""
    error_message: str = ""
    duration_ms: int = 0


@dataclass
class RuntimeResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


@dataclass
class ArtifactMeta:
    id: str
    name: str
    key: str
    url: str
    size: int
    content_type: str
    session_id: str = ""


@dataclass
class ArtifactUploadResponse:
    artifact_id: str
    key: str
    url: str
    size: int


class RuntimeEngine(Protocol):
    """Interface semua runtime engine harus implement."""

    def name(self) -> str: ...
    def tier(self) -> Tier: ...
    def execute(self, job: Job) -> RuntimeResult: ...
    def health(self) -> None: ...
