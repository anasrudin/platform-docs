"""Unit tests for sandbox_platform.scaler.policy — pure functions, no I/O."""

from __future__ import annotations

import time


from scaler import AggregateMetrics, ScaleAction, ScalingPolicy, evaluate


def _metrics(
    node_count: int = 2,
    avg_pool_utilization: float = 0.5,
    avg_cpu_percent: float = 30.0,
    avg_memory_percent: float = 40.0,
    total_active_sessions: int = 5,
) -> AggregateMetrics:
    return AggregateMetrics(
        node_count=node_count,
        avg_pool_utilization=avg_pool_utilization,
        avg_cpu_percent=avg_cpu_percent,
        avg_memory_percent=avg_memory_percent,
        total_active_sessions=total_active_sessions,
    )


def _policy(**kwargs) -> ScalingPolicy:
    defaults = dict(
        min_nodes=1,
        max_nodes=5,
        scale_up_threshold=0.7,
        scale_down_threshold=0.3,
        scale_up_cooldown=300.0,
        scale_down_cooldown=600.0,
        scale_increment=1,
    )
    defaults.update(kwargs)
    return ScalingPolicy(**defaults)


FAR_PAST = 0.0  # epoch — cooldown always elapsed


class TestScaleUp:
    def test_scale_up_when_utilization_above_threshold(self):
        action = evaluate(
            metrics=_metrics(avg_pool_utilization=0.85, node_count=2),
            current_count=2,
            policy=_policy(),
            last_scale_up_ts=FAR_PAST,
            last_scale_down_ts=FAR_PAST,
        )
        assert action.action == "scale_up"
        assert action.target_count == 3

    def test_scale_up_target_respects_scale_increment(self):
        action = evaluate(
            metrics=_metrics(avg_pool_utilization=0.9, node_count=2),
            current_count=2,
            policy=_policy(scale_increment=2),
            last_scale_up_ts=FAR_PAST,
            last_scale_down_ts=FAR_PAST,
        )
        assert action.target_count == 4

    def test_scale_up_capped_at_max_nodes(self):
        action = evaluate(
            metrics=_metrics(avg_pool_utilization=0.9, node_count=5),
            current_count=5,
            policy=_policy(max_nodes=5),
            last_scale_up_ts=FAR_PAST,
            last_scale_down_ts=FAR_PAST,
        )
        assert action.action == "none"
        assert action.target_count == 5

    def test_scale_up_blocked_by_cooldown(self):
        recent = time.monotonic() - 60.0  # 60s ago, cooldown=300s
        action = evaluate(
            metrics=_metrics(avg_pool_utilization=0.9, node_count=2),
            current_count=2,
            policy=_policy(scale_up_cooldown=300.0),
            last_scale_up_ts=recent,
            last_scale_down_ts=FAR_PAST,
        )
        assert action.action == "none"
        assert "cooldown" in action.reason.lower()

    def test_scale_up_allowed_after_cooldown_expires(self):
        old = time.monotonic() - 400.0  # 400s ago, cooldown=300s
        action = evaluate(
            metrics=_metrics(avg_pool_utilization=0.9, node_count=2),
            current_count=2,
            policy=_policy(scale_up_cooldown=300.0),
            last_scale_up_ts=old,
            last_scale_down_ts=FAR_PAST,
        )
        assert action.action == "scale_up"


class TestScaleDown:
    def test_scale_down_when_utilization_below_threshold(self):
        action = evaluate(
            metrics=_metrics(avg_pool_utilization=0.1, node_count=3),
            current_count=3,
            policy=_policy(),
            last_scale_up_ts=FAR_PAST,
            last_scale_down_ts=FAR_PAST,
        )
        assert action.action == "scale_down"
        assert action.target_count == 2

    def test_scale_down_floored_at_min_nodes(self):
        action = evaluate(
            metrics=_metrics(avg_pool_utilization=0.1, node_count=1),
            current_count=1,
            policy=_policy(min_nodes=1),
            last_scale_up_ts=FAR_PAST,
            last_scale_down_ts=FAR_PAST,
        )
        assert action.action == "none"
        assert action.target_count == 1

    def test_scale_down_blocked_by_cooldown(self):
        recent = time.monotonic() - 100.0  # 100s ago, cooldown=600s
        action = evaluate(
            metrics=_metrics(avg_pool_utilization=0.1, node_count=3),
            current_count=3,
            policy=_policy(scale_down_cooldown=600.0),
            last_scale_up_ts=FAR_PAST,
            last_scale_down_ts=recent,
        )
        assert action.action == "none"
        assert "cooldown" in action.reason.lower()

    def test_scale_down_allowed_after_cooldown_expires(self):
        old = time.monotonic() - 700.0  # 700s ago, cooldown=600s
        action = evaluate(
            metrics=_metrics(avg_pool_utilization=0.1, node_count=3),
            current_count=3,
            policy=_policy(scale_down_cooldown=600.0),
            last_scale_up_ts=FAR_PAST,
            last_scale_down_ts=old,
        )
        assert action.action == "scale_down"


class TestNoAction:
    def test_no_action_within_thresholds(self):
        action = evaluate(
            metrics=_metrics(avg_pool_utilization=0.5),
            current_count=2,
            policy=_policy(scale_up_threshold=0.7, scale_down_threshold=0.3),
            last_scale_up_ts=FAR_PAST,
            last_scale_down_ts=FAR_PAST,
        )
        assert action.action == "none"

    def test_no_action_at_exact_thresholds(self):
        # Exactly at threshold → no action (strict >/<)
        up_action = evaluate(
            metrics=_metrics(avg_pool_utilization=0.7),
            current_count=2,
            policy=_policy(scale_up_threshold=0.7),
            last_scale_up_ts=FAR_PAST,
            last_scale_down_ts=FAR_PAST,
        )
        assert up_action.action == "none"

        down_action = evaluate(
            metrics=_metrics(avg_pool_utilization=0.3),
            current_count=2,
            policy=_policy(scale_down_threshold=0.3),
            last_scale_up_ts=FAR_PAST,
            last_scale_down_ts=FAR_PAST,
        )
        assert down_action.action == "none"

    def test_no_action_empty_metrics(self):
        action = evaluate(
            metrics=AggregateMetrics(0, 0.0, 0.0, 0.0, 0),
            current_count=1,
            policy=_policy(),
            last_scale_up_ts=FAR_PAST,
            last_scale_down_ts=FAR_PAST,
        )
        assert action.action == "none"


class TestScaleActionFields:
    def test_action_has_reason(self):
        action = evaluate(
            metrics=_metrics(avg_pool_utilization=0.9),
            current_count=2,
            policy=_policy(),
            last_scale_up_ts=FAR_PAST,
            last_scale_down_ts=FAR_PAST,
        )
        assert action.reason != ""

    def test_scale_action_is_dataclass(self):
        action = ScaleAction(action="none", target_count=2, reason="test")
        assert action.action == "none"
        assert action.target_count == 2
