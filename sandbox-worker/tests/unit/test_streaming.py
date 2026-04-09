"""Tests for Streaming Output — communication/stream.py, service/streaming.py, api/routes/streaming.py."""
from __future__ import annotations

import asyncio
import json

import pytest

from adapters.tracing import init_tracer, reset_tracer


@pytest.fixture(autouse=True)
def reset_tracer_fixture():
    reset_tracer()
    init_tracer(driver="noop")
    yield
    reset_tracer()


# ── StreamingService ───────────────────────────────────────────────────────────

class TestStreamingService:
    def _make_svc(self, chunks=None):
        """Build a StreamingService with a fake stream_execute."""
        from service.streaming import StreamingService

        default_chunks = [
            {"type": "stdout", "data": "hello\n"},
            {"type": "stdout", "data": "world\n"},
            {"type": "done", "exit_code": 0, "duration_ms": 42},
        ]
        _chunks = chunks if chunks is not None else default_chunks

        async def fake_stream(*args, **kwargs):
            for c in _chunks:
                yield c

        svc = StreamingService(max_timeout=5)
        # Patch the internal producer to use fake stream
        import service.streaming as mod
        original = mod.stream_execute
        mod.stream_execute = fake_stream
        yield svc
        mod.stream_execute = original

    @pytest.mark.asyncio
    async def test_stream_yields_stdout_chunks(self):
        from service.streaming import StreamingService
        import service.streaming as mod

        chunks = [
            {"type": "stdout", "data": "line1\n"},
            {"type": "done", "exit_code": 0, "duration_ms": 10},
        ]

        async def fake_stream(*a, **kw):
            for c in chunks:
                yield c

        original = mod.stream_execute
        mod.stream_execute = fake_stream
        try:
            svc = StreamingService(max_timeout=5)
            received = []
            async for chunk in svc.stream("sess-1", "echo", {}):
                received.append(chunk)
            assert any(c["type"] == "stdout" for c in received)
            assert received[-1]["type"] == "done"
        finally:
            mod.stream_execute = original

    @pytest.mark.asyncio
    async def test_stream_terminates_after_done(self):
        from service.streaming import StreamingService
        import service.streaming as mod

        chunks = [
            {"type": "stdout", "data": "x\n"},
            {"type": "done", "exit_code": 0, "duration_ms": 1},
            {"type": "stdout", "data": "should not appear\n"},  # after done
        ]

        async def fake_stream(*a, **kw):
            for c in chunks:
                yield c

        original = mod.stream_execute
        mod.stream_execute = fake_stream
        try:
            svc = StreamingService(max_timeout=5)
            received = []
            async for chunk in svc.stream("sess-2", "echo", {}):
                received.append(chunk)

            # Should stop at done, not continue
            done_idx = next(i for i, c in enumerate(received) if c["type"] == "done")
            assert len(received) == done_idx + 1
        finally:
            mod.stream_execute = original

    @pytest.mark.asyncio
    async def test_stream_error_chunk_terminates(self):
        from service.streaming import StreamingService
        import service.streaming as mod

        async def fake_stream(*a, **kw):
            yield {"type": "error", "message": "connection refused"}

        original = mod.stream_execute
        mod.stream_execute = fake_stream
        try:
            svc = StreamingService(max_timeout=5)
            received = []
            async for chunk in svc.stream("sess-3", "fail", {}):
                received.append(chunk)
            assert received[-1]["type"] in ("error", "done")
        finally:
            mod.stream_execute = original

    def test_subscriber_count_zero_initially(self):
        from service.streaming import StreamingService
        svc = StreamingService()
        assert svc.subscriber_count("sess-1") == 0

    @pytest.mark.asyncio
    async def test_subscriber_count_during_stream(self):
        from service.streaming import StreamingService
        import service.streaming as mod

        barrier = asyncio.Event()
        resume = asyncio.Event()

        async def slow_stream(*a, **kw):
            await barrier.wait()
            yield {"type": "done", "exit_code": 0, "duration_ms": 0}

        original = mod.stream_execute
        mod.stream_execute = slow_stream
        try:
            svc = StreamingService(max_timeout=5)

            async def consume():
                async for _ in svc.stream("sess-sub", "echo", {}):
                    pass

            task = asyncio.create_task(consume())
            await asyncio.sleep(0.05)  # let task start and register subscriber
            assert svc.subscriber_count("sess-sub") == 1
            barrier.set()
            await task
            assert svc.subscriber_count("sess-sub") == 0
        finally:
            mod.stream_execute = original


# ── communication/stream.py ───────────────────────────────────────────────────

class TestStreamModule:
    def test_stream_execute_is_async_generator(self):
        from communication.stream import stream_execute
        import inspect
        assert inspect.isasyncgenfunction(stream_execute)

    @pytest.mark.asyncio
    async def test_stream_execute_yields_error_on_connection_failure(self):
        """On a bad address, stream_execute should yield an error chunk, not raise."""
        from communication.stream import stream_execute

        chunks = []
        async for chunk in stream_execute(
            tool="echo",
            input_data={},
            tcp_addr="127.0.0.1:19999",  # nothing listening
            timeout=1.0,
        ):
            chunks.append(chunk)
            if chunk.get("type") in ("error", "done"):
                break

        types = [c["type"] for c in chunks]
        # Must have either error or done — never raise
        assert "error" in types or "done" in types

    @pytest.mark.asyncio
    async def test_stream_execute_always_yields_done(self):
        """Even on error paths, a done chunk must eventually be yielded."""
        from communication.stream import stream_execute

        last = None
        async for chunk in stream_execute(
            tool="echo",
            input_data={},
            tcp_addr="127.0.0.1:19999",
            timeout=1.0,
        ):
            last = chunk

        assert last is not None
        assert last["type"] == "done"


# ── Streaming API routes ───────────────────────────────────────────────────────

class TestStreamingRoutes:
    def _make_app(self, streaming_svc=None):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routes.streaming import register

        app = FastAPI()
        state = {"streaming_svc": streaming_svc}
        app.include_router(register(state))
        return TestClient(app)

    def test_sse_no_svc_returns_503(self):
        client = self._make_app(streaming_svc=None)
        resp = client.get("/sessions/sess-1/execute/stream?tool=echo")
        assert resp.status_code == 503

    def test_sse_missing_tool_returns_400(self):
        from service.streaming import StreamingService
        svc = StreamingService()
        client = self._make_app(streaming_svc=svc)
        resp = client.get("/sessions/sess-1/execute/stream")
        assert resp.status_code == 400

    def test_sse_invalid_input_json_returns_400(self):
        from service.streaming import StreamingService
        svc = StreamingService()
        client = self._make_app(streaming_svc=svc)
        resp = client.get("/sessions/sess-1/execute/stream?tool=echo&input=NOT_JSON")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_sse_streams_chunks(self):
        from service.streaming import StreamingService
        import service.streaming as mod
        from fastapi import FastAPI
        from httpx import AsyncClient, ASGITransport
        from api.routes.streaming import register

        chunks = [
            {"type": "stdout", "data": "hi\n"},
            {"type": "done", "exit_code": 0, "duration_ms": 5},
        ]

        async def fake_stream(*a, **kw):
            for c in chunks:
                yield c

        original = mod.stream_execute
        mod.stream_execute = fake_stream
        try:
            svc = StreamingService(max_timeout=5)
            app = FastAPI()
            app.include_router(register({"streaming_svc": svc}))

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                async with client.stream("GET", "/sessions/s1/execute/stream?tool=echo") as resp:
                    assert resp.status_code == 200
                    assert "text/event-stream" in resp.headers["content-type"]
                    lines = []
                    async for line in resp.aiter_lines():
                        if line.startswith("data:"):
                            lines.append(json.loads(line[5:].strip()))
                            if lines[-1].get("type") in ("done", "error"):
                                break

            assert any(c["type"] == "stdout" for c in lines)
        finally:
            mod.stream_execute = original
