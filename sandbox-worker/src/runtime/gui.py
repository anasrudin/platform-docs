"""GUI/browser stub runtime."""
from __future__ import annotations

import json
import time

import structlog

from models.job import Job, RuntimeResult
from models.session import Tier

log = structlog.get_logger()


class Runtime:
    """Stub that simulates browser/GUI execution."""

    def name(self) -> str:
        return "gui-runtime-stub"

    def tier(self) -> Tier:
        return Tier.GUI

    def health(self) -> None:
        pass  # stub is always healthy

    def execute(self, job: Job) -> RuntimeResult:
        start = time.monotonic()
        log.info("gui stub executing", tool=job.tool, job_id=job.id)

        time.sleep(0.1)

        result = {
            "tool": job.tool,
            "status": "completed",
            "runtime": "gui-stub",
            "session_id": f"browser-{job.id[:8]}",
            "warmup_ms": 200,
            "exec_ms": 100,
            "input": job.input,
            "output": f"[stub] Executed {job.tool} in simulated browser session",
            "metadata": {
                "browser": "chromium-121",
                "display": ":99",
                "resolution": "1920x1080",
                "stream_url": f"ws://localhost:6080/vnc/{job.id[:8]}",
            },
        }

        duration_ms = int((time.monotonic() - start) * 1000)
        log.info("gui stub complete", tool=job.tool, duration_ms=duration_ms)

        return RuntimeResult(stdout=json.dumps(result, indent=2), exit_code=0)


__all__ = ["Runtime"]
