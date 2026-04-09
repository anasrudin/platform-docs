"""No-op ServiceRegistry untuk testing tanpa Consul."""
from __future__ import annotations


class NoopRegistry:
    def register(self, service_id: str, name: str, address: str, port: int, tags: list[str] | None = None) -> None:
        pass

    def deregister(self, service_id: str) -> None:
        pass

    def healthy_instances(self, service_name: str) -> list[dict]:
        return []
