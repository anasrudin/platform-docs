"""Auto-scaling policy evaluation.

evaluate() is a pure function — all state (timestamps, current count) is passed
in. This makes it trivially testable and decouples policy from I/O.

Cooldowns:
  scale_up_cooldown   = 300s  (5 min) — prevents rapid repeated scale-ups
  scale_down_cooldown = 600s  (10 min) — prevents thrashing on transient dips
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from sandbox_platform.scaler.metrics import AggregateMetrics


@dataclass
class ScalingPolicy:
    min_nodes: int = 1
    max_nodes: int = 10
    scale_up_threshold: float = (
        0.7  # avg_pool_utilization strictly above this → scale up
    )
    scale_down_threshold: float = (
        0.3  # avg_pool_utilization strictly below this → scale down
    )
    scale_up_cooldown: float = 300.0  # seconds
    scale_down_cooldown: float = 600.0  # seconds
    scale_increment: int = 1  # nodes to add/remove per action


@dataclass
class ScaleAction:
    action: str  # "scale_up" | "scale_down" | "none"
    target_count: int
    reason: str


def evaluate(
    metrics: AggregateMetrics,
    current_count: int,
    policy: ScalingPolicy,
    last_scale_up_ts: float = 0.0,
    last_scale_down_ts: float = 0.0,
    now: float | None = None,
) -> ScaleAction:
    """Return the scaling action required given current metrics and policy.

    The function is pure: callers must supply timestamps and current count.
    It never mutates state.
    """
    if now is None:
        now = time.monotonic()

    # No nodes reporting → nothing to act on
    if metrics.node_count == 0:
        return ScaleAction("none", current_count, "no nodes reporting metrics")

    util = metrics.avg_pool_utilization

    # ── Scale up ──────────────────────────────────────────────────────────────
    if util > policy.scale_up_threshold:
        if current_count >= policy.max_nodes:
            return ScaleAction(
                "none", current_count, f"already at max_nodes={policy.max_nodes}"
            )
        elapsed = now - last_scale_up_ts
        if elapsed < policy.scale_up_cooldown:
            remaining = policy.scale_up_cooldown - elapsed
            return ScaleAction(
                "none", current_count, f"scale_up cooldown: {remaining:.0f}s remaining"
            )
        target = min(current_count + policy.scale_increment, policy.max_nodes)
        return ScaleAction(
            "scale_up",
            target,
            f"pool_utilization={util:.2f} > threshold={policy.scale_up_threshold}",
        )

    # ── Scale down ────────────────────────────────────────────────────────────
    if util < policy.scale_down_threshold:
        if current_count <= policy.min_nodes:
            return ScaleAction(
                "none", current_count, f"already at min_nodes={policy.min_nodes}"
            )
        elapsed = now - last_scale_down_ts
        if elapsed < policy.scale_down_cooldown:
            remaining = policy.scale_down_cooldown - elapsed
            return ScaleAction(
                "none",
                current_count,
                f"scale_down cooldown: {remaining:.0f}s remaining",
            )
        target = max(current_count - policy.scale_increment, policy.min_nodes)
        return ScaleAction(
            "scale_down",
            target,
            f"pool_utilization={util:.2f} < threshold={policy.scale_down_threshold}",
        )

    # ── Within band ───────────────────────────────────────────────────────────
    return ScaleAction(
        "none",
        current_count,
        f"pool_utilization={util:.2f} within [{policy.scale_down_threshold}, "
        f"{policy.scale_up_threshold}]",
    )
