"""HibernationService — idle detection, trigger hibernate/restore, TTL cleanup.

Sits between the API layer and the orchestrator:
  - tracks last-active time per session in a dict (later: Redis)
  - on /hibernate: delegates to HibernationOrchestrator
  - on /restore: delegates to HibernationOrchestrator
  - background scan: called by lifespan task every HIBERNATE_SCAN_INTERVAL seconds
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import structlog

from adapters.tracing import get_tracer
from models.hibernation import HibernateSnapshot, HibernateState, RestoreResult
from orchestrator.hibernation import HibernationOrchestrator

log = structlog.get_logger()


class HibernationService:
    def __init__(
        self,
        orchestrator: HibernationOrchestrator,
        idle_timeout: int = 300,
        ttl: int = 86400,
    ) -> None:
        self._orch = orchestrator
        self._idle_timeout = idle_timeout
        self._ttl = ttl

        # session_id → last active timestamp (epoch float)
        self._last_active: dict[str, float] = {}
        # session_id → HibernateSnapshot
        self._snapshots: dict[str, HibernateSnapshot] = {}
        # session_id → HibernateState
        self._states: dict[str, HibernateState] = {}

    # ── Public API ─────────────────────────────────────────────────────────────

    def touch(self, session_id: str) -> None:
        """Update last-active time. Call on every execute request."""
        self._last_active[session_id] = time.monotonic()
        self._states[session_id] = HibernateState.ACTIVE

    def state(self, session_id: str) -> HibernateState:
        return self._states.get(session_id, HibernateState.ACTIVE)

    def hibernate(self, session_id: str, fc_socket: str = "") -> dict:
        tracer = get_tracer()
        with tracer.start_span("service.hibernation.hibernate", {"session_id": session_id}):
            self._states[session_id] = HibernateState.HIBERNATING
            try:
                snap = self._orch.hibernate(session_id, fc_socket)
                self._snapshots[session_id] = snap
                self._states[session_id] = HibernateState.HIBERNATED
                log.info("session hibernated", session_id=session_id, key=snap.snapshot_key)
                return {
                    "hibernated_at": snap.hibernated_at.isoformat(),
                    "snapshot_key": snap.snapshot_key,
                }
            except Exception as exc:
                self._states[session_id] = HibernateState.ACTIVE
                raise

    def restore(self, session_id: str, fc_socket: str = "") -> dict:
        tracer = get_tracer()
        snap = self._snapshots.get(session_id)
        if snap is None:
            raise KeyError(f"No hibernate snapshot for session {session_id}")

        with tracer.start_span("service.hibernation.restore", {"session_id": session_id}):
            self._states[session_id] = HibernateState.RESTORING
            try:
                result = self._orch.restore(session_id, snap.snapshot_key, fc_socket)
                self._states[session_id] = HibernateState.ACTIVE
                self.touch(session_id)
                log.info("session restored", session_id=session_id, restore_ms=result.restore_ms)
                return {
                    "session_id": result.session_id,
                    "restored_from": result.restored_from,
                    "restore_ms": result.restore_ms,
                }
            except Exception:
                self._states[session_id] = HibernateState.HIBERNATED
                raise

    # ── Background scan ────────────────────────────────────────────────────────

    def scan_idle(self) -> list[str]:
        """Hibernate sessions idle longer than idle_timeout. Returns list of hibernated IDs."""
        now = time.monotonic()
        hibernated = []
        for session_id, last in list(self._last_active.items()):
            if self._states.get(session_id) != HibernateState.ACTIVE:
                continue
            if now - last >= self._idle_timeout:
                log.info("idle session detected, hibernating", session_id=session_id,
                         idle_s=int(now - last))
                try:
                    self.hibernate(session_id)
                    hibernated.append(session_id)
                except Exception as exc:
                    log.error("auto-hibernate failed", session_id=session_id, err=str(exc))
        return hibernated

    def cleanup_expired(self) -> list[str]:
        """Delete hibernate snapshots older than TTL. Returns list of cleaned session IDs."""
        now = datetime.now(timezone.utc)
        cleaned = []
        for session_id, snap in list(self._snapshots.items()):
            if snap.expires_at and now > snap.expires_at:
                del self._snapshots[session_id]
                if self._states.get(session_id) == HibernateState.HIBERNATED:
                    del self._states[session_id]
                log.info("expired hibernate snapshot removed", session_id=session_id)
                cleaned.append(session_id)
        return cleaned
