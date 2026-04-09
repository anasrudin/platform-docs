"""Nomad HTTP API client (async, httpx) for job scaling.

Environment variables:
  NOMAD_ADDR   — Nomad server address (default: http://127.0.0.1:4646)
  NOMAD_TOKEN  — ACL token (default: empty)
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import structlog
from sandbox_platform.middleware.trace import get_trace_id

log = structlog.get_logger()


def _env_or(key: str, default: str) -> str:
    return os.environ.get(key) or default


class NomadClient:
    """Thin async wrapper around the Nomad HTTP API v1."""

    def __init__(
        self,
        address: str | None = None,
        token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._address = address or _env_or("NOMAD_ADDR", "http://127.0.0.1:4646")
        self._token = token if token is not None else _env_or("NOMAD_TOKEN", "")
        self._transport = transport

    def _build_client(self) -> httpx.AsyncClient:
        headers: dict[str, str] = {}
        if self._token:
            headers["X-Nomad-Token"] = self._token
        trace_id = get_trace_id()
        if trace_id:
            headers["X-Trace-ID"] = trace_id
        kwargs: dict[str, Any] = {"base_url": self._address, "headers": headers}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    async def job_count(self, job_id: str, group: str) -> int:
        """Return the current allocation count for a task group."""
        async with self._build_client() as client:
            resp = await client.get(f"/v1/job/{job_id}")
        if resp.status_code != 200:
            raise RuntimeError(
                f"job_count failed: job={job_id} status={resp.status_code}"
            )
        data = resp.json()
        for tg in data.get("TaskGroups") or []:
            if tg.get("Name") == group:
                return int(tg["Count"])
        raise KeyError(f"no-such-group: {group} in job {job_id}")

    async def scale_job(
        self,
        job_id: str,
        group: str,
        count: int,
        reason: str = "",
    ) -> None:
        """Scale a Nomad task group to the target count.

        Uses the /v1/job/:job_id/scale endpoint which supports zero-downtime
        drain when scaling down — Nomad will drain allocations gracefully
        before terminating them (controlled by the job's migrate stanza).
        """
        payload: dict[str, Any] = {
            "Count": count,
            "Target": {"Group": group},
            "Message": reason,
        }
        async with self._build_client() as client:
            resp = await client.post(f"/v1/job/{job_id}/scale", json=payload)
        if resp.status_code != 200:
            raise RuntimeError(
                f"scale_job failed: job={job_id} group={group} "
                f"count={count} status={resp.status_code}"
            )
        log.info(
            "nomad: scaled job", job=job_id, group=group, count=count, reason=reason
        )
