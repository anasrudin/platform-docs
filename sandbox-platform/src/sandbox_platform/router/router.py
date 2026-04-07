"""Job router: resolves tool → tier and pushes jobs to Redis.

Mirrors internal/router/router.go.
"""
from __future__ import annotations

import threading

import structlog

from sandbox_platform.queue.client import Client as QueueClient
from sandbox_platform.router.rules import default_rules
from sandbox_platform.types import Job, RuntimeResult, Tier

log = structlog.get_logger()


class Router:
    """Routes tools to execution tiers and dispatches jobs via the queue."""

    def __init__(self, queue_client: QueueClient) -> None:
        self._lock = threading.RLock()
        self._rules: dict[str, Tier] = dict(default_rules())
        self._qc = queue_client

    def resolve(self, tool: str) -> Tier:
        """Return the tier for tool, defaulting to WASM."""
        with self._lock:
            return self._rules.get(tool, Tier.WASM)

    def register(self, tool: str, tier: Tier) -> None:
        """Add or override a tool → tier mapping."""
        with self._lock:
            self._rules[tool] = tier

    def execute(self, job: Job, timeout: float = 30.0) -> RuntimeResult:
        """Route the job to its tier queue and wait for the result."""
        tier = self.resolve(job.tool)
        job.tier = tier

        log.info("routing execution", tool=job.tool, tier=tier.value, job_id=job.id)

        self._qc.push_job(job)

        try:
            return self._qc.wait_for_job_result(job.id, timeout=timeout)
        except TimeoutError as exc:
            return RuntimeResult(stderr=str(exc), exit_code=1)
