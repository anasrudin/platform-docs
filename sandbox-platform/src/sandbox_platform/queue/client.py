"""Redis-backed job queue client.

Mirrors internal/queue/queue.go + producer.go + consumer.go.
"""
from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

import redis
import structlog

from sandbox_platform.types import Job, RuntimeResult, Tier

log = structlog.get_logger()


@dataclass
class JobMessage:
    """Payload pushed onto a Redis list (used by Producer/Consumer)."""
    job_id: str
    tool: str
    tier: str
    agent_id: str
    input: str  # raw JSON


def new_redis_client(url: str) -> redis.Redis:
    """Parse a Redis URL and return a connected client."""
    return redis.from_url(url, decode_responses=True)


# ── Main queue client (queue.go) ───────────────────────────────────────────────

class Client:
    """Bi-directional queue client: push jobs, pop jobs, publish/wait results."""

    def __init__(self, rdb: redis.Redis) -> None:
        self._rdb = rdb

    def push_job(self, job: Job) -> None:
        """Push a job onto the tier-specific queue."""
        data = json.dumps({
            "id": job.id,
            "session_id": job.session_id,
            "tool": job.tool,
            "tier": job.tier.value,
            "input": job.input,
            "status": job.status.value,
            "output": job.output,
            "error_message": job.error_message,
            "duration_ms": job.duration_ms,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
        })
        queue_name = f"queue:{job.tier.value}"
        self._rdb.rpush(queue_name, data)
        log.debug("job pushed", queue=queue_name, job_id=job.id)

    def wait_for_job_result(self, job_id: str, timeout: float = 30.0) -> RuntimeResult:
        """Block until the result for job_id is published (or timeout)."""
        result_key = f"result:{job_id}"
        val = self._rdb.blpop(result_key, timeout=int(timeout))
        if val is None:
            raise TimeoutError(f"timeout waiting for job result: {job_id}")
        _, raw = val
        data = json.loads(raw)
        return RuntimeResult(
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            exit_code=data.get("exit_code", 0),
        )

    def pop_job(self, tier: Tier, timeout: float = 0) -> Job:
        """Block and pop a job from the tier queue.

        timeout=0 blocks indefinitely (matches Go BLPop 0).
        """
        from sandbox_platform.types import JobStatus
        from datetime import datetime

        queue_name = f"queue:{tier.value}"
        val = self._rdb.blpop(queue_name, timeout=int(timeout) if timeout else 0)
        if val is None:
            raise TimeoutError(f"timeout popping from {queue_name}")
        _, raw = val
        data = json.loads(raw)
        return Job(
            id=data["id"],
            session_id=data["session_id"],
            tool=data["tool"],
            tier=Tier(data["tier"]),
            input=data.get("input") or {},
            status=JobStatus(data.get("status", "pending")),
            output=data.get("output", ""),
            error_message=data.get("error_message", ""),
            duration_ms=data.get("duration_ms", 0),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.utcnow(),
        )

    def publish_job_result(self, job_id: str, result: RuntimeResult) -> None:
        """Push a result and set a 5-minute expiry."""
        result_key = f"result:{job_id}"
        data = json.dumps({
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
        })
        self._rdb.rpush(result_key, data)
        self._rdb.expire(result_key, 300)  # 5 minutes
        log.debug("result published", job_id=job_id)


# ── Producer (producer.go) ─────────────────────────────────────────────────────

class Producer:
    """Pushes JobMessage payloads to a Redis list."""

    def __init__(self, rdb: redis.Redis, stream: str) -> None:
        self._rdb = rdb
        self._stream = stream

    def push(self, msg: JobMessage) -> None:
        data = json.dumps({
            "job_id": msg.job_id,
            "tool": msg.tool,
            "tier": msg.tier,
            "agent_id": msg.agent_id,
            "input": msg.input,
        })
        self._rdb.rpush(self._stream, data)


# ── Consumer (consumer.go) ─────────────────────────────────────────────────────

HandlerFunc = Callable[[JobMessage], None]


class Consumer:
    """Reads JobMessage payloads from a Redis list and calls handler."""

    def __init__(self, rdb: redis.Redis, stream: str, handler: HandlerFunc) -> None:
        self._rdb = rdb
        self._stream = stream
        self._handler = handler
        self._stop = threading.Event()

    def run(self) -> None:
        """Block processing messages until stop() is called."""
        log.info("queue consumer started", stream=self._stream)
        while not self._stop.is_set():
            val = self._rdb.blpop(self._stream, timeout=1)
            if val is None:
                continue
            _, raw = val
            try:
                data = json.loads(raw)
                msg = JobMessage(
                    job_id=data.get("job_id", ""),
                    tool=data.get("tool", ""),
                    tier=data.get("tier", ""),
                    agent_id=data.get("agent_id", ""),
                    input=data.get("input", ""),
                )
                self._handler(msg)
            except Exception as exc:
                log.error("handle job message", exc_info=exc, raw=raw)

    def stop(self) -> None:
        self._stop.set()
