"""Per-node metrics collection for the auto-scaler.

MetricsCollector queries each agent's /health endpoint and returns
NodeMetrics. cpu_percent and memory_percent default to 0.0 — they will be
populated once agents expose those fields; the scaler policy works today using
pool_utilization alone.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import structlog

log = structlog.get_logger()


@dataclass
class NodeMetrics:
    node_id: str
    pool_utilization: float  # 0.0–1.0
    cpu_percent: float  # 0.0–100.0 (0 until agents expose it)
    memory_percent: float  # 0.0–100.0 (0 until agents expose it)
    active_sessions: int


@dataclass
class AggregateMetrics:
    node_count: int
    avg_pool_utilization: float
    avg_cpu_percent: float
    avg_memory_percent: float
    total_active_sessions: int


def aggregate(nodes: list[NodeMetrics]) -> AggregateMetrics:
    """Reduce a list of per-node metrics to cluster-level aggregates."""
    if not nodes:
        return AggregateMetrics(0, 0.0, 0.0, 0.0, 0)
    n = len(nodes)
    return AggregateMetrics(
        node_count=n,
        avg_pool_utilization=sum(m.pool_utilization for m in nodes) / n,
        avg_cpu_percent=sum(m.cpu_percent for m in nodes) / n,
        avg_memory_percent=sum(m.memory_percent for m in nodes) / n,
        total_active_sessions=sum(m.active_sessions for m in nodes),
    )


class MetricsCollector:
    """Queries /health on a configurable list of nodes.

    Args:
        max_pool_size: the pool capacity configured for this tier. Used to
            compute pool_utilization = health.pool_size / max_pool_size.
        transport: optional httpx transport, injected in tests.
    """

    def __init__(
        self,
        max_pool_size: int = 1,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._max_pool = max(max_pool_size, 1)
        self._transport = transport

    def _build_client(self) -> httpx.AsyncClient:
        kwargs = {}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    async def collect(self, nodes: list[tuple[str, str]]) -> list[NodeMetrics]:
        """Query each (node_id, health_url) pair and return reachable metrics.

        Unreachable or non-200 nodes are logged and skipped.
        """
        if not nodes:
            return []

        results: list[NodeMetrics] = []
        async with self._build_client() as client:
            for node_id, health_url in nodes:
                try:
                    resp = await client.get(health_url, timeout=5.0)
                    if resp.status_code != 200:
                        log.warning(
                            "metrics: node unhealthy",
                            node=node_id,
                            status=resp.status_code,
                        )
                        continue
                    data = resp.json()
                    pool_size = int(data.get("pool_size", 0))
                    utilization = min(pool_size / self._max_pool, 1.0)
                    results.append(
                        NodeMetrics(
                            node_id=node_id,
                            pool_utilization=utilization,
                            cpu_percent=float(data.get("cpu_percent", 0.0)),
                            memory_percent=float(data.get("memory_percent", 0.0)),
                            active_sessions=int(data.get("active_sessions", 0)),
                        )
                    )
                except Exception as exc:
                    log.warning("metrics: node unreachable", node=node_id, err=str(exc))

        return results
