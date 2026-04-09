"""Tests for Multi-tenancy — models, service, middleware, routes."""
from __future__ import annotations

import base64
import json

import pytest
from starlette.requests import Request

from adapters.tracing import init_tracer, reset_tracer
from models.tenant import Tenant, TenantQuota


@pytest.fixture(autouse=True)
def tracer():
    reset_tracer()
    init_tracer(driver="noop")
    yield
    reset_tracer()


# ── TenantQuota model ──────────────────────────────────────────────────────────

class TestTenantQuota:
    def test_defaults(self):
        q = TenantQuota()
        assert q.max_sessions == 2
        assert q.max_rpm == 30
        assert q.max_execution_timeout == 30

    def test_as_dict_has_all_fields(self):
        d = TenantQuota().as_dict()
        assert "max_sessions" in d
        assert "max_rpm" in d
        assert "max_storage_bytes" in d


class TestTenantModel:
    def test_as_dict_includes_quota(self):
        t = Tenant(id="t-1", name="acme")
        d = t.as_dict()
        assert d["id"] == "t-1"
        assert "quota" in d
        assert "created_at" in d


# ── TenantService ──────────────────────────────────────────────────────────────

class TestTenantService:
    def _make(self):
        from service.tenant import TenantService
        return TenantService()

    def test_default_tenant_exists(self):
        svc = self._make()
        info = svc.get("default")
        assert info["id"] == "default"

    def test_create_returns_tenant_dict(self):
        svc = self._make()
        result = svc.create("acme")
        assert result["id"].startswith("t-")
        assert result["name"] == "acme"

    def test_create_with_explicit_id(self):
        svc = self._make()
        result = svc.create("corp", tenant_id="org-abc")
        assert result["id"] == "org-abc"

    def test_get_after_create(self):
        svc = self._make()
        tid = svc.create("corp")["id"]
        assert svc.get(tid)["name"] == "corp"

    def test_get_unknown_raises_key_error(self):
        svc = self._make()
        with pytest.raises(KeyError):
            svc.get("t-nonexistent")

    def test_delete_removes_tenant(self):
        svc = self._make()
        tid = svc.create("tmp")["id"]
        svc.delete(tid)
        with pytest.raises(KeyError):
            svc.get(tid)

    def test_delete_unknown_raises_key_error(self):
        svc = self._make()
        with pytest.raises(KeyError):
            svc.delete("t-gone")

    def test_cannot_delete_default(self):
        svc = self._make()
        with pytest.raises(ValueError):
            svc.delete("default")

    def test_update_quota(self):
        svc = self._make()
        tid = svc.create("big-corp")["id"]
        updated = svc.update_quota(tid, max_sessions=20, max_rpm=300)
        assert updated["quota"]["max_sessions"] == 20
        assert updated["quota"]["max_rpm"] == 300

    def test_update_quota_unknown_raises_key_error(self):
        svc = self._make()
        with pytest.raises(KeyError):
            svc.update_quota("t-gone", max_rpm=300)

    def test_get_quota_returns_default_for_unknown(self):
        svc = self._make()
        q = svc.get_quota("nonexistent-tenant")
        assert isinstance(q, TenantQuota)
        assert q.max_rpm == 30

    def test_list_all_includes_default(self):
        svc = self._make()
        result = svc.list_all()
        assert any(t["id"] == "default" for t in result)


# ── TenantAuthMiddleware ───────────────────────────────────────────────────────

class TestTenantAuthMiddleware:
    def _make_app(self, enabled=False):
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from fastapi.testclient import TestClient
        from api.middleware.auth import TenantAuthMiddleware
        app = FastAPI()
        app.add_middleware(TenantAuthMiddleware, enabled=enabled)

        @app.get("/whoami")
        def whoami(request: Request):
            return JSONResponse({"tenant_id": request.state.tenant_id})

        return TestClient(app)

    def test_disabled_injects_default(self):
        client = self._make_app(enabled=False)
        resp = client.get("/whoami")
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == "default"

    def test_enabled_no_header_returns_401(self):
        client = self._make_app(enabled=True)
        resp = client.get("/whoami")
        assert resp.status_code == 401

    def test_enabled_x_tenant_id_header(self):
        client = self._make_app(enabled=True)
        resp = client.get("/whoami", headers={"X-Tenant-ID": "org-abc"})
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == "org-abc"

    def test_enabled_bearer_token_with_tenant_id(self):
        client = self._make_app(enabled=True)
        # Build a fake JWT payload segment
        payload = base64.urlsafe_b64encode(
            json.dumps({"tenant_id": "org-jwt", "sub": "user-1"}).encode()
        ).rstrip(b"=").decode()
        token = f"header.{payload}.sig"
        resp = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == "org-jwt"

    def test_enabled_invalid_token_returns_401(self):
        client = self._make_app(enabled=True)
        resp = client.get("/whoami", headers={"Authorization": "Bearer notavalidtoken"})
        assert resp.status_code == 401


# ── Tenant API routes ──────────────────────────────────────────────────────────

class TestTenantRoutes:
    def _make_app(self, svc=None):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.routes.tenant import register
        app = FastAPI()
        app.include_router(register({"tenant_svc": svc}))
        return TestClient(app)

    def test_no_svc_returns_503(self):
        client = self._make_app()
        resp = client.post("/admin/tenants", json={"name": "x"})
        assert resp.status_code == 503

    def test_create_returns_201(self):
        from service.tenant import TenantService
        client = self._make_app(TenantService())
        resp = client.post("/admin/tenants", json={"name": "acme"})
        assert resp.status_code == 201
        assert resp.json()["name"] == "acme"

    def test_create_with_explicit_id(self):
        from service.tenant import TenantService
        client = self._make_app(TenantService())
        resp = client.post("/admin/tenants", json={"name": "corp", "tenant_id": "org-x"})
        assert resp.json()["id"] == "org-x"

    def test_list_includes_default(self):
        from service.tenant import TenantService
        client = self._make_app(TenantService())
        resp = client.get("/admin/tenants")
        assert any(t["id"] == "default" for t in resp.json()["tenants"])

    def test_get_returns_tenant(self):
        from service.tenant import TenantService
        svc = TenantService()
        tid = svc.create("proj")["id"]
        client = self._make_app(svc)
        resp = client.get(f"/admin/tenants/{tid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "proj"

    def test_get_unknown_returns_404(self):
        from service.tenant import TenantService
        client = self._make_app(TenantService())
        resp = client.get("/admin/tenants/t-ghost")
        assert resp.status_code == 404

    def test_delete_returns_204(self):
        from service.tenant import TenantService
        svc = TenantService()
        tid = svc.create("rm-me")["id"]
        client = self._make_app(svc)
        resp = client.delete(f"/admin/tenants/{tid}")
        assert resp.status_code == 204

    def test_delete_default_returns_400(self):
        from service.tenant import TenantService
        client = self._make_app(TenantService())
        resp = client.delete("/admin/tenants/default")
        assert resp.status_code == 400

    def test_update_quota(self):
        from service.tenant import TenantService
        svc = TenantService()
        tid = svc.create("big")["id"]
        client = self._make_app(svc)
        resp = client.patch(f"/admin/tenants/{tid}/quota", json={"max_rpm": 300, "max_sessions": 20})
        assert resp.status_code == 200
        assert resp.json()["quota"]["max_rpm"] == 300

    def test_update_quota_unknown_returns_404(self):
        from service.tenant import TenantService
        client = self._make_app(TenantService())
        resp = client.patch("/admin/tenants/t-ghost/quota", json={"max_rpm": 100})
        assert resp.status_code == 404
