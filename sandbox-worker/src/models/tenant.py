"""Tenant and TenantQuota models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class TenantQuota:
    max_sessions: int = 2
    max_rpm: int = 30                            # requests per minute
    max_cpu_seconds_per_hour: int = 600
    max_storage_bytes: int = 1_073_741_824       # 1 GB
    max_execution_timeout: int = 30              # seconds

    def as_dict(self) -> dict:
        return {
            "max_sessions": self.max_sessions,
            "max_rpm": self.max_rpm,
            "max_cpu_seconds_per_hour": self.max_cpu_seconds_per_hour,
            "max_storage_bytes": self.max_storage_bytes,
            "max_execution_timeout": self.max_execution_timeout,
        }


@dataclass
class Tenant:
    id: str
    name: str
    quota: TenantQuota = field(default_factory=TenantQuota)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "quota": self.quota.as_dict(),
            "created_at": self.created_at.isoformat(),
        }
