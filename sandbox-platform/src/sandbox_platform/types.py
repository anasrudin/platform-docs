"""Core types for the sandbox execution platform.

Mirrors pkg/types/types.go.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol


class Tier(str, Enum):
    WASM = "wasm"
    MICROVM = "microvm"
    GUI = "gui"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Session:
    id: str
    runtime: Tier
    status: str
    created_at: datetime
    updated_at: datetime


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
class CreateSessionRequest:
    runtime: str = "wasm"


@dataclass
class CreateSessionResponse:
    session_id: str
    runtime: Tier
    status: str


@dataclass
class HealthResponse:
    status: str
    version: str
    services: dict[str, str] = field(default_factory=dict)


@dataclass
class ArtifactMeta:
    id: str
    name: str
    key: str        # MinIO key: <id>/<name>
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


@dataclass
class RuntimeResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


class RuntimeEngine(Protocol):
    """Interface that all runtime engines must implement."""

    def name(self) -> str: ...
    def tier(self) -> Tier: ...
    def execute(self, job: Job) -> RuntimeResult: ...
    def health(self) -> None: ...  # raises on unhealthy
