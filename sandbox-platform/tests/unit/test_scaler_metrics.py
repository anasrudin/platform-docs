"""Unit tests for sandbox_platform.scaler.metrics."""
from __future__ import annotations

import httpx
import pytest

from sandbox_platform.scaler.metrics import (
    AggregateMetrics,
    MetricsCollector,
    NodeMetrics,
    aggregate,
)


# ── aggregate() ───────────────────────────────────────────────────────────────

class TestAggregate:
    def test_empty_list_returns_zero_aggregate(self):
        result = aggregate([])
        assert result.node_count == 0
        assert result.avg_pool_utilization == 0.0
        assert result.total_active_sessions == 0

    def test_single_node(self):
        node = NodeMetrics(
            node_id="n1",
            pool_utilization=0.8,
            cpu_percent=50.0,
            memory_percent=60.0,
            active_sessions=3,
        )
        result = aggregate([node])
        assert result.node_count == 1
        assert result.avg_pool_utilization == pytest.approx(0.8)
        assert result.avg_cpu_percent == pytest.approx(50.0)
        assert result.avg_memory_percent == pytest.approx(60.0)
        assert result.total_active_sessions == 3

    def test_multiple_nodes_averages(self):
        nodes = [
            NodeMetrics("n1", 0.8, 60.0, 70.0, 5),
            NodeMetrics("n2", 0.4, 40.0, 30.0, 2),
        ]
        result = aggregate(nodes)
        assert result.node_count == 2
        assert result.avg_pool_utilization == pytest.approx(0.6)
        assert result.avg_cpu_percent == pytest.approx(50.0)
        assert result.avg_memory_percent == pytest.approx(50.0)
        assert result.total_active_sessions == 7

    def test_total_sessions_is_sum_not_average(self):
        nodes = [
            NodeMetrics("n1", 0.5, 0.0, 0.0, 10),
            NodeMetrics("n2", 0.5, 0.0, 0.0, 20),
            NodeMetrics("n3", 0.5, 0.0, 0.0, 5),
        ]
        result = aggregate(nodes)
        assert result.total_active_sessions == 35


# ── MetricsCollector ──────────────────────────────────────────────────────────

class _HealthTransport(httpx.AsyncBaseTransport):
    """Returns a canned /health response for each URL."""

    def __init__(self, responses: dict[str, dict]) -> None:
        self._responses = responses  # url_prefix → json body

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for prefix, body in self._responses.items():
            if url.startswith(prefix):
                return httpx.Response(200, json=body)
        return httpx.Response(503, json={"status": "unreachable"})


def _collector(responses: dict[str, dict], max_pool: int = 4) -> MetricsCollector:
    transport = _HealthTransport(responses)
    return MetricsCollector(max_pool_size=max_pool, transport=transport)


class TestMetricsCollector:
    @pytest.mark.asyncio
    async def test_collect_returns_metrics_per_node(self):
        collector = _collector({
            "http://10.0.0.1:8081": {"status": "ok", "runtime": "fc", "pool_size": 2},
            "http://10.0.0.2:8081": {"status": "ok", "runtime": "fc", "pool_size": 3},
        })
        nodes = [
            ("n1", "http://10.0.0.1:8081/health"),
            ("n2", "http://10.0.0.2:8081/health"),
        ]
        result = await collector.collect(nodes)
        assert len(result) == 2
        ids = {m.node_id for m in result}
        assert ids == {"n1", "n2"}

    @pytest.mark.asyncio
    async def test_pool_utilization_calculated_from_pool_size(self):
        collector = _collector(
            {"http://10.0.0.1:8081": {"status": "ok", "runtime": "fc", "pool_size": 2}},
            max_pool=4,
        )
        result = await collector.collect([("n1", "http://10.0.0.1:8081/health")])
        assert len(result) == 1
        # utilization = pool_size / max_pool = 2/4 = 0.5
        assert result[0].pool_utilization == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_unreachable_node_is_skipped(self):
        collector = _collector({
            "http://10.0.0.1:8081": {"status": "ok", "runtime": "fc", "pool_size": 1},
            # 10.0.0.2 is not in responses → 503 → skipped
        })
        nodes = [
            ("n1", "http://10.0.0.1:8081/health"),
            ("n2", "http://10.0.0.2:8081/health"),
        ]
        result = await collector.collect(nodes)
        assert len(result) == 1
        assert result[0].node_id == "n1"

    @pytest.mark.asyncio
    async def test_empty_nodes_returns_empty(self):
        collector = _collector({})
        result = await collector.collect([])
        assert result == []

    @pytest.mark.asyncio
    async def test_node_metrics_defaults_for_cpu_memory(self):
        # cpu/memory are 0.0 by default (not yet reported by /health)
        collector = _collector(
            {"http://10.0.0.1:8081": {"status": "ok", "runtime": "fc", "pool_size": 1}},
        )
        result = await collector.collect([("n1", "http://10.0.0.1:8081/health")])
        assert result[0].cpu_percent == 0.0
        assert result[0].memory_percent == 0.0

    @pytest.mark.asyncio
    async def test_utilization_clamped_to_1_when_pool_exceeds_max(self):
        # pool_size=6 with max_pool=4 → clamped to 1.0
        collector = _collector(
            {"http://10.0.0.1:8081": {"status": "ok", "runtime": "fc", "pool_size": 6}},
            max_pool=4,
        )
        result = await collector.collect([("n1", "http://10.0.0.1:8081/health")])
        assert result[0].pool_utilization == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_active_sessions_from_health_response(self):
        collector = _collector({
            "http://10.0.0.1:8081": {
                "status": "ok", "runtime": "fc",
                "pool_size": 2, "active_sessions": 7,
            },
        })
        result = await collector.collect([("n1", "http://10.0.0.1:8081/health")])
        assert result[0].active_sessions == 7

    @pytest.mark.asyncio
    async def test_active_sessions_defaults_to_zero_when_absent(self):
        collector = _collector({
            "http://10.0.0.1:8081": {"status": "ok", "runtime": "fc", "pool_size": 2},
        })
        result = await collector.collect([("n1", "http://10.0.0.1:8081/health")])
        assert result[0].active_sessions == 0
