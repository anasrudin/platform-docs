"""Auto-scaler background asyncio task.

Runs a tick loop: collect metrics → evaluate policy → call Nomad if needed.
Errors in a single tick are logged and swallowed so the loop stays alive.

Graceful scale-down:
  Nomad's /v1/job/:id/scale endpoint triggers a migration stanza drain —
  allocations are drained (existing connections allowed to complete) before
  the count is reduced. No extra logic is needed here beyond calling scale_job.

Usage (in FastAPI lifespan)::

    scaler = Scaler(policy=..., collector=..., nomad=..., ...)
    task = asyncio.create_task(scaler.run())
    yield
    scaler.stop()
    await task
"""

from __future__ import annotations

import asyncio
import time

import structlog

from sandbox_platform.scaler.metrics import (
    AggregateMetrics,
    MetricsCollector,
    aggregate,
)
from sandbox_platform.scaler.nomad import NomadClient
from sandbox_platform.scaler.policy import ScalingPolicy, evaluate

log = structlog.get_logger()


class Scaler:
    """Background auto-scaler for a single Nomad job / task group."""

    def __init__(
        self,
        policy: ScalingPolicy,
        collector: MetricsCollector,
        nomad: NomadClient,
        job_id: str,
        group: str,
        nodes: list[tuple[str, str]],  # [(node_id, health_url), ...]
        interval: float = 60.0,  # seconds between ticks
    ) -> None:
        self._policy = policy
        self._collector = collector
        self._nomad = nomad
        self._job_id = job_id
        self._group = group
        self._nodes = nodes
        self._interval = interval
        self._stop_event = asyncio.Event()
        self._last_scale_up_ts: float = 0.0
        self._last_scale_down_ts: float = 0.0

    async def run(self) -> None:
        """Main loop. Runs until stop() is called."""
        log.info(
            "scaler: started",
            job=self._job_id,
            group=self._group,
            interval=self._interval,
        )
        while not self._stop_event.is_set():
            try:
                await self._tick()
            except Exception as exc:
                log.error("scaler: tick error", job=self._job_id, err=str(exc))
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._interval,
                )
            except asyncio.TimeoutError:
                pass  # normal — interval elapsed, do next tick

    def stop(self) -> None:
        """Signal the run loop to exit after the current tick."""
        self._stop_event.set()

    async def _tick(self) -> None:
        """Single evaluation cycle: collect → evaluate → act."""
        node_metrics = await self._collector.collect(self._nodes)
        metrics: AggregateMetrics = aggregate(node_metrics)

        current_count = await self._nomad.job_count(self._job_id, self._group)

        action = evaluate(
            metrics=metrics,
            current_count=current_count,
            policy=self._policy,
            last_scale_up_ts=self._last_scale_up_ts,
            last_scale_down_ts=self._last_scale_down_ts,
        )

        log.info(
            "scaler: tick",
            job=self._job_id,
            util=f"{metrics.avg_pool_utilization:.2f}",
            current=current_count,
            action=action.action,
            target=action.target_count,
            reason=action.reason,
        )

        if action.action == "scale_up":
            await self._nomad.scale_job(
                self._job_id,
                self._group,
                count=action.target_count,
                reason=action.reason,
            )
            self._last_scale_up_ts = time.monotonic()

        elif action.action == "scale_down":
            # Nomad drains gracefully via the job's migrate stanza before
            # reducing the allocation count.
            await self._nomad.scale_job(
                self._job_id,
                self._group,
                count=action.target_count,
                reason=action.reason,
            )
            self._last_scale_down_ts = time.monotonic()
