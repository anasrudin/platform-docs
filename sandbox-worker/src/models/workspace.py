"""Workspace domain models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MountDriver(str, Enum):
    SYNC = "sync"          # download before boot, upload after destroy
    VIRTIOFS = "virtiofs"  # mount via virtiofsd (Linux + KVM only)


@dataclass
class WorkspaceFile:
    path: str
    size: int
    modified: datetime


@dataclass
class Workspace:
    id: str
    name: str
    tenant_id: str = "default"
    created_at: datetime = field(default_factory=datetime.utcnow)
    size_bytes: int = 0
    files: list[WorkspaceFile] = field(default_factory=list)


@dataclass
class MountConfig:
    workspace_id: str
    driver: MountDriver = MountDriver.SYNC
    local_mount_path: str = "/workspace"
