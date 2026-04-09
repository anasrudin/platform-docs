"""Tests for RequestIDMiddleware."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app():
    from api.middleware.request_id import RequestIDMiddleware
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return app


class TestRequestIDMiddleware:
    def test_response_has_request_id_header(self):
        client = TestClient(_make_app())
        resp = client.get("/ping")
        assert resp.status_code == 200
        assert "x-request-id" in resp.headers

    def test_request_id_is_8_chars(self):
        client = TestClient(_make_app())
        resp = client.get("/ping")
        req_id = resp.headers["x-request-id"]
        assert len(req_id) == 8

    def test_client_provided_request_id_is_echoed(self):
        client = TestClient(_make_app())
        resp = client.get("/ping", headers={"X-Request-ID": "custom-1"})
        assert resp.headers["x-request-id"] == "custom-1"

    def test_each_request_gets_unique_id(self):
        client = TestClient(_make_app())
        ids = {client.get("/ping").headers["x-request-id"] for _ in range(5)}
        assert len(ids) == 5  # semua unik

    def test_request_id_bound_to_structlog_context(self):
        """request_id harus tersedia di structlog context selama request."""
        from structlog.contextvars import get_contextvars

        bound: dict = {}

        from api.middleware.request_id import RequestIDMiddleware
        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)

        @app.get("/ctx")
        def ctx():
            bound.update(get_contextvars())
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/ctx")
        assert "request_id" in bound
        assert bound["request_id"] == resp.headers["x-request-id"]
