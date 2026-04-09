"""Tests for Rate Limiting — store, quota service, middleware."""
from __future__ import annotations

import pytest

from adapters.tracing import init_tracer, reset_tracer
from adapters.cache.ratelimit import MemoryRateLimitStore


@pytest.fixture(autouse=True)
def tracer():
    reset_tracer()
    init_tracer(driver="noop")
    yield
    reset_tracer()


# ── MemoryRateLimitStore ───────────────────────────────────────────────────────

class TestMemoryRateLimitStore:
    def test_increment_returns_count(self):
        store = MemoryRateLimitStore()
        assert store.increment("k1") == 1
        assert store.increment("k1") == 2

    def test_get_returns_current(self):
        store = MemoryRateLimitStore()
        store.increment("k1")
        store.increment("k1")
        assert store.get("k1") == 2

    def test_get_absent_key_returns_zero(self):
        store = MemoryRateLimitStore()
        assert store.get("missing") == 0

    def test_different_keys_are_independent(self):
        store = MemoryRateLimitStore()
        store.increment("a")
        store.increment("b")
        store.increment("b")
        assert store.get("a") == 1
        assert store.get("b") == 2

    def test_reset_clears_counter(self):
        store = MemoryRateLimitStore()
        store.increment("k")
        store.reset("k")
        assert store.get("k") == 0


# ── QuotaService ───────────────────────────────────────────────────────────────

class TestQuotaService:
    def _make(self, max_rpm=5, max_sessions=2):
        from service.quota import QuotaService
        from service.tenant import TenantService
        store = MemoryRateLimitStore()
        tenant_svc = TenantService()
        # Override default tenant quota for testing
        tenant_svc._tenants["default"].quota.max_rpm = max_rpm
        tenant_svc._tenants["default"].quota.max_sessions = max_sessions
        svc = QuotaService(store=store, tenant_svc=tenant_svc)
        return svc

    def test_check_rate_limit_increments(self):
        svc = self._make(max_rpm=10)
        count, limit = svc.check_rate_limit("default")
        assert count == 1
        assert limit == 10

    def test_check_rate_limit_exceeds_raises(self):
        from service.quota import QuotaExceededError
        svc = self._make(max_rpm=3)
        svc.check_rate_limit("default")
        svc.check_rate_limit("default")
        svc.check_rate_limit("default")
        with pytest.raises(QuotaExceededError) as exc_info:
            svc.check_rate_limit("default")
        assert exc_info.value.resource == "requests_per_minute"
        assert exc_info.value.limit == 3

    def test_peek_rate_does_not_increment(self):
        svc = self._make(max_rpm=10)
        svc.check_rate_limit("default")
        count, limit = svc.peek_rate("default")
        count2, _ = svc.peek_rate("default")
        assert count == count2 == 1

    def test_acquire_session_tracks_count(self):
        svc = self._make(max_sessions=2)
        svc.acquire_session("default")
        assert svc.active_sessions("default") == 1

    def test_acquire_session_exceeds_raises(self):
        from service.quota import QuotaExceededError
        svc = self._make(max_sessions=2)
        svc.acquire_session("default")
        svc.acquire_session("default")
        with pytest.raises(QuotaExceededError) as exc_info:
            svc.acquire_session("default")
        assert exc_info.value.resource == "concurrent_sessions"

    def test_release_session_decrements(self):
        svc = self._make(max_sessions=2)
        svc.acquire_session("default")
        svc.acquire_session("default")
        svc.release_session("default")
        assert svc.active_sessions("default") == 1

    def test_release_session_never_goes_negative(self):
        svc = self._make()
        svc.release_session("default")
        assert svc.active_sessions("default") == 0

    def test_different_tenants_independent(self):
        from service.quota import QuotaService, QuotaExceededError
        store = MemoryRateLimitStore()
        svc = QuotaService(store=store, tenant_svc=None)
        svc.acquire_session("tenant-a")
        svc.acquire_session("tenant-a")
        # tenant-b should not be affected
        svc.acquire_session("tenant-b")
        assert svc.active_sessions("tenant-b") == 1

    def test_no_tenant_svc_uses_default_quota(self):
        from service.quota import QuotaService
        store = MemoryRateLimitStore()
        svc = QuotaService(store=store, tenant_svc=None)
        count, limit = svc.check_rate_limit("t-x")
        assert limit == 30  # TenantQuota default


# ── RateLimitMiddleware ────────────────────────────────────────────────────────

class TestRateLimitMiddleware:
    def _make_app(self, quota_svc, enabled=True):
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from fastapi.testclient import TestClient
        from api.middleware.auth import TenantAuthMiddleware
        from api.middleware.ratelimit import RateLimitMiddleware

        app = FastAPI()
        app.add_middleware(TenantAuthMiddleware, enabled=False)  # inject "default"
        app.add_middleware(RateLimitMiddleware, quota_svc=quota_svc, enabled=enabled)

        @app.get("/ping")
        def ping():
            return JSONResponse({"ok": True})

        return TestClient(app)

    def test_disabled_passes_through(self):
        from service.quota import QuotaService
        svc = QuotaService(MemoryRateLimitStore())
        client = self._make_app(svc, enabled=False)
        for _ in range(50):
            assert client.get("/ping").status_code == 200

    def test_within_limit_adds_headers(self):
        from service.quota import QuotaService
        from service.tenant import TenantService
        ts = TenantService()
        ts._tenants["default"].quota.max_rpm = 10
        svc = QuotaService(MemoryRateLimitStore(), tenant_svc=ts)
        client = self._make_app(svc)
        resp = client.get("/ping")
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" in resp.headers
        assert resp.headers["X-RateLimit-Limit"] == "10"

    def test_exceeds_limit_returns_429(self):
        from service.quota import QuotaService
        from service.tenant import TenantService
        ts = TenantService()
        ts._tenants["default"].quota.max_rpm = 3
        svc = QuotaService(MemoryRateLimitStore(), tenant_svc=ts)
        client = self._make_app(svc)
        for _ in range(3):
            assert client.get("/ping").status_code == 200
        resp = client.get("/ping")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        assert resp.json()["detail"] == "rate limit exceeded"

    def test_no_quota_svc_passes_through(self):
        from api.middleware.ratelimit import RateLimitMiddleware
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from fastapi.testclient import TestClient
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, quota_svc=None, enabled=True)

        @app.get("/ping")
        def ping(): return JSONResponse({"ok": True})

        client = TestClient(app)
        assert client.get("/ping").status_code == 200
