"""Session and job lifecycle manager backed by PostgreSQL.

Mirrors internal/session/manager.go.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

import psycopg2
import psycopg2.extras
import structlog

from sandbox_platform.types import Job, JobStatus, Session, Tier

log = structlog.get_logger()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    runtime    TEXT NOT NULL DEFAULT 'wasm',
    status     TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions(id),
    tool        TEXT NOT NULL,
    tier        TEXT NOT NULL DEFAULT 'wasm',
    input       JSONB,
    status      TEXT NOT NULL DEFAULT 'pending',
    output      TEXT,
    error_msg   TEXT,
    duration_ms BIGINT DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jobs_session ON jobs(session_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status  ON jobs(status);
"""


class Manager:
    """Manages session and job lifecycle using PostgreSQL."""

    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

    def init_db(self) -> None:
        """Create tables if they don't exist."""
        with self._conn.cursor() as cur:
            cur.execute(_SCHEMA)
        self._conn.commit()
        log.info("database schema initialized")

    def create(self, runtime: Tier) -> Session:
        """Create a new session."""
        session_id = str(uuid.uuid4())
        now = datetime.utcnow()
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (id, runtime, status, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (session_id, runtime.value, "active", now, now),
            )
        self._conn.commit()
        log.info("session created", id=session_id, runtime=runtime.value)
        return Session(
            id=session_id,
            runtime=runtime,
            status="active",
            created_at=now,
            updated_at=now,
        )

    def get(self, session_id: str) -> Session:
        """Retrieve a session by ID. Raises KeyError if not found."""
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id, runtime, status, created_at, updated_at "
                "FROM sessions WHERE id = %s",
                (session_id,),
            )
            row = cur.fetchone()
        if row is None:
            raise KeyError(f"session not found: {session_id}")
        sid, runtime, status, created_at, updated_at = row
        return Session(
            id=sid,
            runtime=Tier(runtime),
            status=status,
            created_at=created_at,
            updated_at=updated_at,
        )

    def create_job(
        self,
        session_id: str,
        tool: str,
        tier: Tier,
        input_data: bytes,
    ) -> Job:
        """Create a new job for a session."""
        job_id = str(uuid.uuid4())
        now = datetime.utcnow()
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO jobs "
                "(id, session_id, tool, tier, input, status, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    job_id,
                    session_id,
                    tool,
                    tier.value,
                    psycopg2.extras.Json(json.loads(input_data) if input_data else {}),
                    JobStatus.PENDING.value,
                    now,
                    now,
                ),
            )
        self._conn.commit()
        return Job(
            id=job_id,
            session_id=session_id,
            tool=tool,
            tier=tier,
            input={},
            status=JobStatus.PENDING,
            created_at=now,
            updated_at=now,
        )

    def update_job(
        self,
        job_id: str,
        status: JobStatus,
        output: str,
        error_msg: str,
        duration_ms: int,
    ) -> None:
        """Update status, output, and duration for a job."""
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET status=%s, output=%s, error_msg=%s, "
                "duration_ms=%s, updated_at=NOW() WHERE id=%s",
                (status.value, output, error_msg, duration_ms, job_id),
            )
        self._conn.commit()


def new_connection(dsn: str) -> psycopg2.extensions.connection:
    """Open and return a psycopg2 connection."""
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    return conn
