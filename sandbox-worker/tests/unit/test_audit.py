"""Tests for Audit Log — adapter, service, api routes."""
from __future__ import annotations

import pytest

from adapters.tracing import init_tracer, reset_tracer
from adapters.audit.memory import MemoryAuditLog


@pytest.fixture(autouse=True)
def tracer():
    reset_tracer()
    init_tracer(driver="noop")
    yield
    reset_tracer()


# ── MemoryAuditLog ─────────────────────────────────────────────────────────────

class TestMemoryAuditLog:
    def test_record_stores_event(self):
        log = MemoryAuditLog()
        log.record(actor="user-1", action="create", resource="ws-abc", outcome="success")
        assert len(log.events) == 1
        assert log.events[0]["actor"] == "user-1"

    def test_query_returns_newest_first(self):
        log = MemoryAuditLog()
        log.record("u", "a", "r1", "ok")
        log.record("u", "a", "r2", "ok")
        results = log.query()
        assert results[0]["resource"] == "r2"
        assert results[1]["resource"] == "r1"

    def test_query_filter_by_actor(self):
        log = MemoryAuditLog()
        log.record("alice", "create", "ws-1", "ok")
        log.record("bob", "delete", "ws-2", "ok")
        results = log.query(actor="alice")
        assert len(results) == 1
        assert results[0]["actor"] == "alice"

    def test_query_filter_by_action(self):
        log = MemoryAuditLog()
        log.record("u", "create", "ws-1", "ok")
        log.record("u", "delete", "ws-2", "ok")
        results = log.query(action="delete")
        assert len(results) == 1
        assert results[0]["action"] == "delete"

    def test_query_filter_by_outcome(self):
        log = MemoryAuditLog()
        log.record("u", "exec", "s-1", "success")
        log.record("u", "exec", "s-2", "failure")
        results = log.query(outcome="failure")
        assert len(results) == 1

    def test_query_limit_and_offset(self):
        log = MemoryAuditLog()
        for i in range(10):
            log.record("u", "a", f"r-{i}", "ok")
        page1 = log.query(limit=3, offset=0)
        page2 = log.query(limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) == 3
        # no overlap
        assert {e["resource"] for e in page1}.isdisjoint({e["resource"] for e in page2})

    def test_query_empty_returns_empty(self):
        log = MemoryAuditLog()
        assert log.query() == []


# ── AuditService ───────────────────────────────────────────────────────────────

class TestAuditService:
    def _make(self):
        from service.audit import AuditService
        backend = MemoryAuditLog()
        svc = AuditService(backend)
        return svc, backend

    def test_record_writes_to_backend(self):
        svc, backend = self._make()
        svc.record("admin", "create", "workspace/ws-1", "success")
        assert len(backend.events) == 1

    def test_record_with_metadata(self):
        svc, backend = self._make()
        svc.record("user", "exec", "session/s-1", "success", metadata={"tool": "python"})
        assert backend.events[0]["metadata"]["tool"] == "python"

    def test_record_never_raises_on_backend_error(self):
        from service.audit import AuditService

        class BrokenBackend:
            def record(self, **kw):
                raise RuntimeError("db down")

        svc = AuditService(BrokenBackend())
        # Must not raise
        svc.record("u", "a", "r", "ok")

    def test_query_returns_events(self):
        svc, backend = self._make()
        svc.record("u", "create", "ws-1", "ok")
        svc.record("u", "delete", "ws-2", "ok")
        results = svc.query()
        assert len(results) == 2

    def test_query_filter_actor(self):
        svc, backend = self._make()
        svc.record("alice", "a", "r", "ok")
        svc.record("bob", "a", "r", "ok")
        assert len(svc.query(actor="alice")) == 1

    def test_query_filter_action(self):
        svc, backend = self._make()
        svc.record("u", "create", "r", "ok")
        svc.record("u", "delete", "r", "ok")
        assert len(svc.query(action="create")) == 1

    def test_query_write_only_backend_returns_empty(self):
        from service.audit import AuditService
        from adapters.audit.stdout import StdoutAuditLog
        svc = AuditService(StdoutAuditLog())
        # StdoutAuditLog has no .query() method — should return []
        results = svc.query()
        assert results == []

    def test_query_broken_backend_returns_empty(self):
        from service.audit import AuditService

        class BrokenQuery:
            def record(self, **kw): pass
            def query(self, **kw): raise RuntimeError("fail")

        svc = AuditService(BrokenQuery())
        assert svc.query() == []


# ── Audit API routes ───────────────────────────────────────────────────────────

class TestAuditRoutes:
    def _make_app(self, svc=None):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routes.audit import register
        app = FastAPI()
        app.include_router(register({"audit_svc": svc}))
        return TestClient(app)

    def test_no_svc_returns_503(self):
        client = self._make_app()
        resp = client.get("/admin/audit")
        assert resp.status_code == 503

    def test_returns_empty_list(self):
        from service.audit import AuditService
        svc = AuditService(MemoryAuditLog())
        client = self._make_app(svc)
        resp = client.get("/admin/audit")
        assert resp.status_code == 200
        assert resp.json()["events"] == []
        assert resp.json()["count"] == 0

    def test_returns_recorded_events(self):
        from service.audit import AuditService
        svc = AuditService(MemoryAuditLog())
        svc.record("admin", "create", "workspace/ws-1", "success")
        client = self._make_app(svc)
        resp = client.get("/admin/audit")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1
        assert resp.json()["events"][0]["actor"] == "admin"

    def test_filter_by_actor(self):
        from service.audit import AuditService
        svc = AuditService(MemoryAuditLog())
        svc.record("alice", "create", "ws-1", "ok")
        svc.record("bob", "delete", "ws-2", "ok")
        client = self._make_app(svc)
        resp = client.get("/admin/audit?actor=alice")
        assert resp.json()["count"] == 1

    def test_filter_by_action(self):
        from service.audit import AuditService
        svc = AuditService(MemoryAuditLog())
        svc.record("u", "create", "r", "ok")
        svc.record("u", "delete", "r", "ok")
        client = self._make_app(svc)
        resp = client.get("/admin/audit?action=delete")
        assert resp.json()["count"] == 1

    def test_filter_by_outcome(self):
        from service.audit import AuditService
        svc = AuditService(MemoryAuditLog())
        svc.record("u", "exec", "s-1", "success")
        svc.record("u", "exec", "s-2", "failure")
        client = self._make_app(svc)
        resp = client.get("/admin/audit?outcome=failure")
        assert resp.json()["count"] == 1

    def test_limit_param(self):
        from service.audit import AuditService
        backend = MemoryAuditLog()
        svc = AuditService(backend)
        for i in range(10):
            svc.record("u", "a", f"r-{i}", "ok")
        client = self._make_app(svc)
        resp = client.get("/admin/audit?limit=5")
        assert resp.json()["count"] == 5

    def test_offset_param(self):
        from service.audit import AuditService
        backend = MemoryAuditLog()
        svc = AuditService(backend)
        for i in range(5):
            svc.record("u", "a", f"r-{i}", "ok")
        client = self._make_app(svc)
        resp_all = client.get("/admin/audit?limit=10")
        resp_offset = client.get("/admin/audit?limit=10&offset=3")
        assert resp_offset.json()["count"] == resp_all.json()["count"] - 3
