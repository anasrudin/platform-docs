"""ServiceRegistry Protocol — register/deregister service instances."""
from __future__ import annotations

from typing import Protocol


class ServiceRegistry(Protocol):
    def register(self, service_id: str, name: str, address: str, port: int, tags: list[str] | None = None) -> None: ...
    def deregister(self, service_id: str) -> None: ...
    def healthy_instances(self, service_name: str) -> list[dict]: ...
