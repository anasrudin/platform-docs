"""Tests for OTel tracing infrastructure — adapters/tracing/ and api/middleware/tracing.py."""
from __future__ import annotations

import pytest

from adapters.tracing import get_tracer, init_tracer, reset_tracer
from adapters.tracing.noop import NoopTracer


# ── Tracer factory ──────────────────────────────────────────────────────────────

class TestTracerFactory:
    def setup_method(self):
        reset_tracer()

    def teardown_method(self):
        reset_tracer()

    def test_default_returns_noop(self):
        tracer = get_tracer()
        assert isinstance(tracer, NoopTracer)

    def test_get_tracer_singleton(self):
        t1 = get_tracer()
        t2 = get_tracer()
        assert t1 is t2

    def test_init_noop_driver(self):
        tracer = init_tracer(driver="noop")
        assert isinstance(tracer, NoopTracer)

    def test_init_invalid_driver_falls_back_to_noop(self):
        tracer = init_tracer(driver="unknown_driver_xyz")
        assert isinstance(tracer, NoopTracer)

    def test_reset_clears_singleton(self):
        t1 = get_tracer()
        reset_tracer()
        t2 = get_tracer()
        assert t1 is not t2


# ── NoopTracer ──────────────────────────────────────────────────────────────────

class TestNoopTracer:
    def setup_method(self):
        reset_tracer()

    def teardown_method(self):
        reset_tracer()

    def test_start_span_context_manager(self):
        tracer = NoopTracer()
        with tracer.start_span("test.span") as span:
            assert span is not None

    def test_span_set_attribute_no_error(self):
        tracer = NoopTracer()
        with tracer.start_span("test.span") as span:
            span.set_attribute("key", "value")
            span.set_attribute("count", 42)

    def test_span_record_exception_no_error(self):
        tracer = NoopTracer()
        with tracer.start_span("test.span") as span:
            span.record_exception(ValueError("test error"))

    def test_span_end_no_error(self):
        tracer = NoopTracer()
        with tracer.start_span("test.span") as span:
            span.end()

    def test_nested_spans(self):
        tracer = NoopTracer()
        with tracer.start_span("outer") as outer:
            with tracer.start_span("inner") as inner:
                inner.set_attribute("nested", True)
            outer.set_attribute("done", True)

    def test_span_with_attributes(self):
        tracer = NoopTracer()
        with tracer.start_span("test.span", {"tool": "echo", "tier": "wasm"}) as span:
            span.set_attribute("result", "ok")

    def test_exception_propagates_through_span(self):
        tracer = NoopTracer()
        with pytest.raises(RuntimeError, match="test"):
            with tracer.start_span("failing.span") as span:
                raise RuntimeError("test")

    def test_get_tracer_returns_noop_by_default(self):
        tracer = get_tracer()
        with tracer.start_span("sanity") as span:
            span.set_attribute("ok", True)


# ── Tracing middleware ──────────────────────────────────────────────────────────

class TestTracingMiddleware:
    def setup_method(self):
        reset_tracer()
        init_tracer(driver="noop")

    def teardown_method(self):
        reset_tracer()

    def test_middleware_passes_request_through(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.middleware.tracing import TracingMiddleware

        app = FastAPI()
        app.add_middleware(TracingMiddleware)

        @app.get("/ping")
        def ping():
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/ping")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_middleware_records_status_code(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.middleware.tracing import TracingMiddleware

        app = FastAPI()
        app.add_middleware(TracingMiddleware)

        @app.get("/ok")
        def ok():
            return {}

        @app.get("/fail")
        def fail():
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="not found")

        client = TestClient(app, raise_server_exceptions=False)
        assert client.get("/ok").status_code == 200
        assert client.get("/fail").status_code == 404

    def test_middleware_works_with_noop_tracer(self):
        """Noop tracer must not raise regardless of request outcome."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.middleware.tracing import TracingMiddleware

        app = FastAPI()
        app.add_middleware(TracingMiddleware)

        @app.post("/data")
        def post_data(body: dict):
            return body

        client = TestClient(app)
        resp = client.post("/data", json={"x": 1})
        assert resp.status_code == 200


# ── Service instrumentation (smoke tests) ──────────────────────────────────────

class TestServiceInstrumentation:
    """Verify that service methods use tracer.start_span without crashing."""

    def setup_method(self):
        reset_tracer()
        init_tracer(driver="noop")

    def teardown_method(self):
        reset_tracer()

    def test_execution_service_uses_tracer(self, monkeypatch):
        from service.execution import ExecutionService

        spans_started = []

        class RecordingTracer:
            from contextlib import contextmanager
            @contextmanager
            def start_span(self, name, attrs=None):
                spans_started.append(name)
                from adapters.tracing.noop import _NoopSpan
                yield _NoopSpan()

        monkeypatch.setattr("service.execution.get_tracer", lambda: RecordingTracer())

        # Build minimal mocks
        class MockSession:
            id = "sess-1"
            runtime = type("T", (), {"value": "wasm"})()
            status = "active"

        class MockJob:
            id = "job-1"
            tool = "echo"
            input = {}

        class MockResult:
            exit_code = 0
            stdout = "ok"
            stderr = ""

        class MockMgr:
            def get(self, sid): return MockSession()
            def create(self, tier): return MockSession()
            def create_job(self, *a): return MockJob()
            def update_job(self, *a): pass

        class MockRouter:
            def resolve(self, tool):
                from models.session import Tier
                return Tier.WASM
            def execute(self, job): return MockResult()

        svc = ExecutionService(MockMgr(), MockRouter())
        svc.execute({"tool": "echo", "session_id": "sess-1"})

        assert "service.execution.route" in spans_started
        assert "service.execution.queue_push" in spans_started

    @pytest.mark.asyncio
    async def test_session_service_uses_tracer(self, monkeypatch):
        from service.session import SessionService

        spans_started = []

        class RecordingTracer:
            from contextlib import contextmanager
            @contextmanager
            def start_span(self, name, attrs=None):
                spans_started.append(name)
                from adapters.tracing.noop import _NoopSpan
                yield _NoopSpan()

        monkeypatch.setattr("service.session.get_tracer", lambda: RecordingTracer())

        class MockSession:
            id = "sess-1"
            runtime = type("T", (), {"value": "wasm"})()
            status = "active"

        class MockMgr:
            def create(self, tier): return MockSession()

        svc = SessionService(MockMgr())
        await svc.create("wasm")

        assert "service.session.create" in spans_started
