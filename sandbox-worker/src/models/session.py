"""Session and tier models."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Tier(str, Enum):
    WASM = "wasm"
    MICROVM = "microvm"
    GUI = "gui"


@dataclass
class Session:
    id: str
    runtime: Tier
    status: str
    created_at: datetime
    updated_at: datetime


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
    services: dict[str, str]
