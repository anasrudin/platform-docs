"""Session and tier models."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Tier(str, Enum):
    WASM = "wasm"
    MICROVM = "microvm"
    GUI = "gui"
    FIRECRACKER = "firecracker"


class SnapshotMode(str, Enum):
    CLEAN = "clean"
    CONTINUOUS = "continuous"


@dataclass
class Session:
    id: str
    runtime: Tier
    status: str
    created_at: datetime
    updated_at: datetime
    snapshot_mode: SnapshotMode = SnapshotMode.CLEAN


@dataclass
class CreateSessionRequest:
    runtime: str = "wasm"
    snapshot_mode: str = "clean"


@dataclass
class CreateSessionResponse:
    session_id: str
    runtime: Tier
    status: str
    snapshot_mode: SnapshotMode = SnapshotMode.CLEAN


@dataclass
class HealthResponse:
    status: str
    version: str
    services: dict[str, str]
