"""SessionService — in-memory session tracking (local per worker node)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

import structlog

from adapters.tracing import get_tracer
from models.session import Tier

log = structlog.get_logger()


@dataclass
class Session:
    id: str
    runtime: Tier
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: str = "active"


class SessionService:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    async def create(self, runtime_str: str = "firecracker") -> dict:
        tracer = get_tracer()
        with tracer.start_span("service.session.create", {"runtime": runtime_str}) as span:
            try:
                tier = Tier(runtime_str)
            except ValueError:
                tier = Tier.FIRECRACKER

            sess = Session(id=str(uuid.uuid4()), runtime=tier)
            self._sessions[sess.id] = sess
            span.set_attribute("session_id", sess.id)
            log.info("session created", session_id=sess.id, runtime=tier.value)

            return {
                "session_id": sess.id,
                "runtime": tier.value,
                "status": sess.status,
            }

    def get(self, session_id: str) -> Session:
        sess = self._sessions.get(session_id)
        if sess is None:
            raise KeyError(f"Session {session_id!r} not found")
        return sess

    def close(self, session_id: str) -> None:
        sess = self._sessions.pop(session_id, None)
        if sess:
            log.info("session closed", session_id=session_id)
