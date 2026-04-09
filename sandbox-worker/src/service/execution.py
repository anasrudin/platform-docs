"""ExecutionService — direct VM execution (no queue)."""
from __future__ import annotations

import time
import uuid

import structlog

from adapters.tracing import get_tracer
from models.job import Job, JobStatus, RuntimeResult
from models.session import Tier

log = structlog.get_logger()


class ExecutionService:
    def __init__(self, lifecycle_mgr) -> None:
        # lifecycle_mgr: VMLifecycleManager
        self._mgr = lifecycle_mgr

    def execute(self, body: dict) -> dict:
        tracer = get_tracer()
        tool = body.get("tool", "")
        if not tool:
            raise ValueError("Tool name is required")

        input_data = body.get("input") or {}
        session_id = body.get("session_id") or str(uuid.uuid4())

        with tracer.start_span("service.execution.run", {"tool": tool, "session_id": session_id}) as span:
            job = Job(
                id=str(uuid.uuid4()),
                session_id=session_id,
                tool=tool,
                tier=Tier.FIRECRACKER,
                input=input_data,
            )

            start = time.monotonic()
            vm = self._mgr.acquire(timeout=30.0)
            try:
                result: RuntimeResult = vm.run(job)
            finally:
                self._mgr.release(vm)

            duration_ms = int((time.monotonic() - start) * 1000)

            status = JobStatus.COMPLETED if result.exit_code == 0 else JobStatus.FAILED
            span.set_attribute("job_id", job.id)
            span.set_attribute("status", status.value)
            span.set_attribute("duration_ms", duration_ms)

            log.info("execution done", job_id=job.id, status=status.value, duration_ms=duration_ms)

            return {
                "job_id": job.id,
                "session_id": session_id,
                "status": status.value,
                "output": result.stdout,
                "error_message": result.stderr,
                "duration_ms": duration_ms,
            }
