"""Tests — OTEL spans di VMLifecycleManager.acquire()."""
from __future__ import annotations

from adapters.tracing import reset_tracer
from tests.unit.conftest import RecordingTracer


class TestLifecycleSpans:
    def setup_method(self):
        reset_tracer()

    def teardown_method(self):
        reset_tracer()

    def test_acquire_emits_pool_acquire_span(self, monkeypatch):
        """acquire() harus emit span 'pool.acquire'."""
        tracer = RecordingTracer()
        monkeypatch.setattr("orchestrator.lifecycle.get_tracer", lambda: tracer)

        class MockVM:
            pass

        class MockPool:
            available = 1

            def acquire(self, timeout=30.0):
                return MockVM()

        from orchestrator.lifecycle import VMLifecycleManager

        mgr = VMLifecycleManager.__new__(VMLifecycleManager)
        mgr._pool = MockPool()
        mgr._pool_size = 2
        mgr._snapshot_name = "test-snap"
        mgr._dev_mode = True

        vm = mgr.acquire(timeout=5.0)

        assert vm is not None
        span_names = [s[0] for s in tracer.spans]
        assert "pool.acquire" in span_names

    def test_acquire_span_has_pool_size_attribute(self, monkeypatch):
        """Span pool.acquire harus punya attribute pool_size."""
        tracer = RecordingTracer()
        monkeypatch.setattr("orchestrator.lifecycle.get_tracer", lambda: tracer)

        class MockVM:
            pass

        class MockPool:
            available = 1

            def acquire(self, timeout=30.0):
                return MockVM()

        from orchestrator.lifecycle import VMLifecycleManager

        mgr = VMLifecycleManager.__new__(VMLifecycleManager)
        mgr._pool = MockPool()
        mgr._pool_size = 2
        mgr._snapshot_name = "test-snap"
        mgr._dev_mode = True

        mgr.acquire(timeout=5.0)

        pool_span = next(s for s in tracer.spans if s[0] == "pool.acquire")
        assert pool_span[1].get("pool_size") == 2
