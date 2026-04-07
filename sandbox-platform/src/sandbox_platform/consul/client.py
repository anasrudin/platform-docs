"""Consul HTTP API client (async, httpx).

Environment variables:
  CONSUL_HOST   — Consul agent address (default: 127.0.0.1)
  CONSUL_PORT   — Consul agent HTTP port (default: 8500)
  CONSUL_TOKEN  — ACL token (default: empty / no auth)
"""
from __future__ import annotations

import os
from typing import Any

import httpx
import structlog

log = structlog.get_logger()


def _env_or(key: str, default: str) -> str:
    return os.environ.get(key) or default


class ConsulClient:
    """Thin async wrapper around the Consul HTTP API v1."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        token: str | None = None,
    ) -> None:
        self._host = host or _env_or("CONSUL_HOST", "127.0.0.1")
        self._port = port or int(_env_or("CONSUL_PORT", "8500"))
        self._token = token if token is not None else _env_or("CONSUL_TOKEN", "")
        self._base_url = f"http://{self._host}:{self._port}"
        # Replaced by test mocks via client._transport = ...
        self._transport: httpx.AsyncBaseTransport | None = None

    def _build_client(self) -> httpx.AsyncClient:
        headers: dict[str, str] = {}
        if self._token:
            headers["X-Consul-Token"] = self._token
        kwargs: dict[str, Any] = {"base_url": self._base_url, "headers": headers}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    # ── Service registration ───────────────────────────────────────────────────

    async def register_service(
        self,
        name: str,
        service_id: str,
        address: str,
        port: int,
        health_url: str,
        tags: list[str],
    ) -> None:
        """Register a service with the local Consul agent."""
        payload = {
            "Name": name,
            "ID": service_id,
            "Address": address,
            "Port": port,
            "Tags": tags,
            "Check": {
                "HTTP": health_url,
                "Interval": "10s",
                "Timeout": "5s",
                "DeregisterCriticalServiceAfter": "60s",
            },
        }
        async with self._build_client() as client:
            resp = await client.put("/v1/agent/service/register", json=payload)
        if resp.status_code != 200:
            raise RuntimeError(
                f"consul register failed: status={resp.status_code} body={resp.text}"
            )
        log.info("consul: service registered", id=service_id, name=name)

    async def deregister_service(self, service_id: str) -> None:
        """Deregister a service from the local Consul agent."""
        async with self._build_client() as client:
            resp = await client.put(f"/v1/agent/service/deregister/{service_id}")
        if resp.status_code != 200:
            raise RuntimeError(
                f"consul deregister failed: status={resp.status_code} body={resp.text}"
            )
        log.info("consul: service deregistered", id=service_id)

    # ── KV store ───────────────────────────────────────────────────────────────

    async def put_kv(self, key: str, value: str) -> None:
        """Write a value to the KV store."""
        async with self._build_client() as client:
            resp = await client.put(f"/v1/kv/{key}", content=value.encode())
        if resp.status_code != 200:
            raise RuntimeError(
                f"consul put_kv failed: key={key} status={resp.status_code}"
            )

    async def get_kv(self, key: str) -> str | None:
        """Read a raw value from the KV store. Returns None if the key is missing."""
        async with self._build_client() as client:
            resp = await client.get(f"/v1/kv/{key}", params={"raw": "true"})
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise RuntimeError(
                f"consul get_kv failed: key={key} status={resp.status_code}"
            )
        return resp.text

    async def delete_kv(self, key: str) -> None:
        """Delete a key from the KV store."""
        async with self._build_client() as client:
            resp = await client.delete(f"/v1/kv/{key}")
        if resp.status_code != 200:
            raise RuntimeError(
                f"consul delete_kv failed: key={key} status={resp.status_code}"
            )
