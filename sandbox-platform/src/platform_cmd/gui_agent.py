"""GUI agent — pops jobs from the gui queue and executes them.

Mirrors cmd/gui-agent/main.go.
"""
from __future__ import annotations

import logging
import os
import signal
import time

import structlog

from sandbox_platform.queue.client import Client as QueueClient
from sandbox_platform.queue.client import new_redis_client
from sandbox_platform.runtime.gui.runtime import Runtime

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)
log = structlog.get_logger().bind(agent="gui")


def _env_or(key: str, default: str) -> str:
    return os.environ.get(key) or default


def main() -> None:
    redis_url = _env_or("REDIS_URL", "redis://localhost:6379/0")
    rdb = new_redis_client(redis_url)
    rdb.ping()

    qc = QueueClient(rdb)
    engine = Runtime()

    log.info("Starting gui-agent", tier=engine.tier().value)

    stop = False

    def _handle_signal(*_):
        nonlocal stop
        stop = True
        log.info("Shutting down gui-agent")

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    while not stop:
        try:
            job = qc.pop_job(engine.tier(), timeout=1)
        except TimeoutError:
            continue
        except Exception as exc:
            log.error("failed to pop job", err=str(exc))
            time.sleep(1)
            continue

        log.info("received job", job_id=job.id, tool=job.tool)
        try:
            result = engine.execute(job)
        except Exception as exc:
            from sandbox_platform.types import RuntimeResult
            result = RuntimeResult(stderr=str(exc), exit_code=1)

        try:
            qc.publish_job_result(job.id, result)
        except Exception as exc:
            log.error("failed to publish job result", job_id=job.id, err=str(exc))

    rdb.close()


if __name__ == "__main__":
    main()
