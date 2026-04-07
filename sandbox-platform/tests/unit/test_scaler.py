"""Unit tests for sandbox_platform.scaler.scaler.Scaler background loop."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sandbox_platform.scaler.metrics import AggregateMetrics, NodeMetrics, aggregate
from sandbox_platform.scaler.policy import ScaleAction, ScalingPolicy
from sandbox_platform.scaler.scaler import Scaler


def _metrics_for(utilization: float, node_count: int = 2) -> AggregateMetrics:
    nodes = [
        NodeMetrics(f"n{i}", utilization, 0.0, 0.0, 0)
        for i in range(node_count)
    ]
    return aggregate(nodes)


def _policy(min_nodes=1, max_nodes=5) -> ScalingPolicy:
    return ScalingPolicy(
        min_nodes=min_nodes,
        max_nodes=max_nodes,
        scale_up_threshold=0.7,
        scale_down_threshold=0.3,
        scale_up_cooldown=300.0,
        scale_down_cooldown=600.0,
        scale_increment=1,
    )


class TestScalerActions:
    @pytest.mark.asyncio
    async def test_scale_up_calls_nomad(self):
        nomad = MagicMock()
        nomad.job_count = AsyncMock(return_value=2)
        nomad.scale_job = AsyncMock()

        collector = MagicMock()
        collector.collect = AsyncMock(
            return_value=[NodeMetrics("n1", 0.9, 0.0, 0.0, 0),
                          NodeMetrics("n2", 0.9, 0.0, 0.0, 0)]
        )

        scaler = Scaler(
            policy=_policy(),
            collector=collector,
            nomad=nomad,
            job_id="fc-agent",
            group="agent",
            nodes=[("n1", "http://n1:8081/health"), ("n2", "http://n2:8081/health")],
            interval=0,
        )

        await scaler._tick()

        nomad.scale_job.assert_awaited_once()
        call_kwargs = nomad.scale_job.call_args
        assert call_kwargs.kwargs.get("count", call_kwargs.args[2] if len(call_kwargs.args) > 2 else None) == 3

    @pytest.mark.asyncio
    async def test_scale_down_calls_nomad(self):
        nomad = MagicMock()
        nomad.job_count = AsyncMock(return_value=3)
        nomad.scale_job = AsyncMock()

        collector = MagicMock()
        collector.collect = AsyncMock(
            return_value=[NodeMetrics("n1", 0.1, 0.0, 0.0, 0)]
        )

        scaler = Scaler(
            policy=_policy(),
            collector=collector,
            nomad=nomad,
            job_id="fc-agent",
            group="agent",
            nodes=[("n1", "http://n1:8081/health")],
            interval=0,
        )

        await scaler._tick()

        nomad.scale_job.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_action_does_not_call_nomad(self):
        nomad = MagicMock()
        nomad.job_count = AsyncMock(return_value=2)
        nomad.scale_job = AsyncMock()

        collector = MagicMock()
        collector.collect = AsyncMock(
            return_value=[NodeMetrics("n1", 0.5, 0.0, 0.0, 0)]
        )

        scaler = Scaler(
            policy=_policy(),
            collector=collector,
            nomad=nomad,
            job_id="fc-agent",
            group="agent",
            nodes=[("n1", "http://n1:8081/health")],
            interval=0,
        )

        await scaler._tick()

        nomad.scale_job.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tick_updates_last_scale_up_ts(self):
        nomad = MagicMock()
        nomad.job_count = AsyncMock(return_value=2)
        nomad.scale_job = AsyncMock()

        collector = MagicMock()
        collector.collect = AsyncMock(
            return_value=[NodeMetrics("n1", 0.9, 0.0, 0.0, 0)]
        )

        scaler = Scaler(
            policy=_policy(),
            collector=collector,
            nomad=nomad,
            job_id="fc-agent",
            group="agent",
            nodes=[("n1", "http://n1:8081/health")],
            interval=0,
        )
        ts_before = scaler._last_scale_up_ts
        await scaler._tick()
        assert scaler._last_scale_up_ts > ts_before

    @pytest.mark.asyncio
    async def test_tick_updates_last_scale_down_ts(self):
        nomad = MagicMock()
        nomad.job_count = AsyncMock(return_value=3)
        nomad.scale_job = AsyncMock()

        collector = MagicMock()
        collector.collect = AsyncMock(
            return_value=[NodeMetrics("n1", 0.1, 0.0, 0.0, 0)]
        )

        scaler = Scaler(
            policy=_policy(),
            collector=collector,
            nomad=nomad,
            job_id="fc-agent",
            group="agent",
            nodes=[("n1", "http://n1:8081/health")],
            interval=0,
        )
        ts_before = scaler._last_scale_down_ts
        await scaler._tick()
        assert scaler._last_scale_down_ts > ts_before


class TestScalerLifecycle:
    @pytest.mark.asyncio
    async def test_stop_terminates_run_loop(self):
        nomad = MagicMock()
        nomad.job_count = AsyncMock(return_value=1)
        nomad.scale_job = AsyncMock()

        collector = MagicMock()
        collector.collect = AsyncMock(return_value=[])

        scaler = Scaler(
            policy=_policy(),
            collector=collector,
            nomad=nomad,
            job_id="fc-agent",
            group="agent",
            nodes=[],
            interval=0.01,  # fast tick for test
        )

        task = asyncio.create_task(scaler.run())
        await asyncio.sleep(0.05)
        scaler.stop()
        await asyncio.wait_for(task, timeout=1.0)  # should complete promptly

    @pytest.mark.asyncio
    async def test_tick_error_does_not_crash_loop(self):
        """A single bad _tick should be logged and swallowed, not crash the loop."""
        nomad = MagicMock()
        nomad.job_count = AsyncMock(side_effect=RuntimeError("nomad down"))
        nomad.scale_job = AsyncMock()

        collector = MagicMock()
        collector.collect = AsyncMock(
            return_value=[NodeMetrics("n1", 0.9, 0.0, 0.0, 0)]
        )

        scaler = Scaler(
            policy=_policy(),
            collector=collector,
            nomad=nomad,
            job_id="fc-agent",
            group="agent",
            nodes=[("n1", "http://n1/health")],
            interval=0.01,
        )

        task = asyncio.create_task(scaler.run())
        await asyncio.sleep(0.05)
        scaler.stop()
        await asyncio.wait_for(task, timeout=1.0)
        # Should not raise — errors are swallowed
