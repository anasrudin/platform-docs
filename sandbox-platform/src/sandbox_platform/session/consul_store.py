"""Consul KV-backed session routing store.

Stores session-to-agent routing metadata so it survives agent restarts.
Each entry lives at: sandbox/sessions/{session_id}
Value is JSON: {"tier": "...", "agent_id": "..."}

This is a thin async layer on top of ConsulClient. Full session state
(created_at, status, jobs) remains in PostgreSQL via session.manager.Manager.
"""

from __future__ import annotations

import json

import structlog

from sandbox_platform.consul.client import ConsulClient

log = structlog.get_logger()

_KEY_PREFIX = "sandbox/sessions"


class SessionStore:
    """Persist session routing metadata in Consul KV."""

    def __init__(self, consul: ConsulClient) -> None:
        self._consul = consul

    def _key(self, session_id: str) -> str:
        return f"{_KEY_PREFIX}/{session_id}"

    async def put(self, session_id: str, tier: str, agent_id: str = "") -> None:
        """Write or overwrite routing metadata for a session."""
        value = json.dumps({"tier": tier, "agent_id": agent_id})
        await self._consul.put_kv(self._key(session_id), value)
        log.debug(
            "session store: put", session_id=session_id, tier=tier, agent_id=agent_id
        )

    async def get(self, session_id: str) -> dict | None:
        """Return routing metadata dict, or None if the session is not in the KV store."""
        raw = await self._consul.get_kv(self._key(session_id))
        if raw is None:
            return None
        return json.loads(raw)

    async def delete(self, session_id: str) -> None:
        """Remove routing metadata. Silently ignores missing keys."""
        try:
            await self._consul.delete_kv(self._key(session_id))
        except RuntimeError as exc:
            # delete_kv raises on non-200; 404 (key already gone) is acceptable
            if "404" not in str(exc):
                raise
        log.debug("session store: deleted", session_id=session_id)
