"""Firecracker agent — pops jobs from the microvm queue and executes them.

Mirrors cmd/fc-agent/main.go.

Environment variables:
  REDIS_URL         — Redis connection URL (default: redis://localhost:6379/0)
  FC_HEALTH_PORT    — Port for the /health HTTP endpoint (default: 8081)
  SERVICE_ADDRESS   — Address advertised to Consul (default: 127.0.0.1)
  CONSUL_HOST       — Consul agent host (default: 127.0.0.1)
  CONSUL_PORT       — Consul agent HTTP port (default: 8500)
  CONSUL_TOKEN      — Consul ACL token (default: empty)
  CONSUL_ENABLED    — Set to "true" to register with Consul (default: false)
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import time

import structlog

from sandbox_platform.consul.client import ConsulClient
from sandbox_platform.consul.health_server import start_health_server
from sandbox_platform.queue.client import Client as QueueClient
from sandbox_platform.queue.client import new_redis_client
from sandbox_platform.runtime.firecracker.runtime import Runtime

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", key="ts"),
        structlog.processors.JSONRenderer(),
    ],
)
log = structlog.get_logger().bind(service="fc-agent")


def _env_or(key: str, default: str) -> str:
    return os.environ.get(key) or default


def main() -> None:
    redis_url = _env_or("REDIS_URL", "redis://localhost:6379/0")
    health_port = int(_env_or("FC_HEALTH_PORT", "8081"))
    service_address = _env_or("SERVICE_ADDRESS", "127.0.0.1")
    consul_enabled = os.environ.get("CONSUL_ENABLED") == "true"

    rdb = new_redis_client(redis_url)
    rdb.ping()

    qc = QueueClient(rdb)
    engine = Runtime()

    service_id = f"fc-agent-{service_address}-{health_port}"

    # Start /health endpoint in a background daemon thread
    start_health_server(
        port=health_port,
        runtime_name=engine.name(),
        pool_size_fn=engine.pool_size,
    )

    # Register with Consul if enabled
    consul = ConsulClient()
    if consul_enabled:
        asyncio.run(
            consul.register_service(
                name="fc-agent",
                service_id=service_id,
                address=service_address,
                port=health_port,
                health_url=f"http://{service_address}:{health_port}/health",
                tags=["sandbox", "firecracker"],
            )
        )

    log.info(
        "Starting fc-agent",
        tier=engine.tier().value,
        health_port=health_port,
        consul_enabled=consul_enabled,
    )

    stop = False

    def _handle_signal(*_):
        nonlocal stop
        stop = True
        log.info("Shutting down fc-agent")
        if consul_enabled:
            try:
                asyncio.run(consul.deregister_service(service_id))
            except Exception as exc:
                log.error("consul deregister failed", err=str(exc))

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

        structlog.contextvars.bind_contextvars(trace_id=job.trace_id)
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
