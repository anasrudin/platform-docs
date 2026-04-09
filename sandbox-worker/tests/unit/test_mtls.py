"""Unit tests for sandbox_platform.security.mtls."""
from __future__ import annotations

import ssl
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adapters.security.mtls import (
    CertManager,
    MTLSMiddleware,
    create_mtls_context,
    mtls_config_from_env,
)


# ── create_mtls_context ────────────────────────────────────────────────────────

class TestCreateMTLSContext:
    """SSLContext tests use patched file-loading to avoid needing real certs."""

    def _make_ctx(self, **kwargs):
        with patch.object(ssl.SSLContext, "load_cert_chain"), \
             patch.object(ssl.SSLContext, "load_verify_locations"):
            return create_mtls_context(
                cert_file=kwargs.get("cert_file", "/tmp/server.crt"),
                key_file=kwargs.get("key_file", "/tmp/server.key"),
                ca_file=kwargs.get("ca_file", "/tmp/ca.crt"),
            )

    def test_returns_ssl_context(self):
        ctx = self._make_ctx()
        assert isinstance(ctx, ssl.SSLContext)

    def test_minimum_tls_version_is_1_3(self):
        ctx = self._make_ctx()
        assert ctx.minimum_version == ssl.TLSVersion.TLSv1_3

    def test_verify_mode_is_cert_required(self):
        ctx = self._make_ctx()
        assert ctx.verify_mode == ssl.CERT_REQUIRED

    def test_load_cert_chain_called_with_cert_and_key(self):
        with patch.object(ssl.SSLContext, "load_verify_locations"), \
             patch.object(ssl.SSLContext, "load_cert_chain") as mock_lc:
            create_mtls_context("/my/cert.pem", "/my/key.pem", "/my/ca.pem")
        mock_lc.assert_called_once_with("/my/cert.pem", "/my/key.pem")

    def test_load_verify_locations_called_with_ca(self):
        with patch.object(ssl.SSLContext, "load_cert_chain"), \
             patch.object(ssl.SSLContext, "load_verify_locations") as mock_lv:
            create_mtls_context("/my/cert.pem", "/my/key.pem", "/my/ca.pem")
        mock_lv.assert_called_once_with("/my/ca.pem")

    def test_protocol_is_server(self):
        ctx = self._make_ctx()
        # PROTOCOL_TLS_SERVER sets the context for server use
        assert ctx.protocol == ssl.PROTOCOL_TLS_SERVER


# ── CertManager (hot reload) ──────────────────────────────────────────────────

class TestCertManager:
    def _manager(self):
        with patch.object(ssl.SSLContext, "load_cert_chain"), \
             patch.object(ssl.SSLContext, "load_verify_locations"):
            return CertManager(
                cert_file="/tmp/server.crt",
                key_file="/tmp/server.key",
                ca_file="/tmp/ca.crt",
            )

    def test_context_property_returns_ssl_context(self):
        mgr = self._manager()
        assert isinstance(mgr.context, ssl.SSLContext)

    def test_reload_calls_load_cert_chain_again(self):
        mgr = self._manager()
        with patch.object(mgr.context, "load_cert_chain") as mock_lc, \
             patch.object(mgr.context, "load_verify_locations"):
            mgr.reload()
        mock_lc.assert_called_once_with(mgr._cert_file, mgr._key_file)

    def test_reload_reuses_same_context_object(self):
        """Hot-reload must not replace the context — that would drop connections."""
        mgr = self._manager()
        ctx_before = mgr.context
        with patch.object(mgr.context, "load_cert_chain"), \
             patch.object(mgr.context, "load_verify_locations"):
            mgr.reload()
        assert mgr.context is ctx_before

    def test_reload_called_multiple_times_does_not_raise(self):
        mgr = self._manager()
        for _ in range(3):
            with patch.object(mgr.context, "load_cert_chain"), \
                 patch.object(mgr.context, "load_verify_locations"):
                mgr.reload()


# ── MTLSMiddleware ─────────────────────────────────────────────────────────────

def _build_app(enabled: bool, cert_checker=None) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        MTLSMiddleware,
        enabled=enabled,
        cert_checker=cert_checker,
    )

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return app


class TestMTLSMiddlewareDisabled:
    def test_passes_through_when_disabled(self):
        app = _build_app(enabled=False)
        client = TestClient(app)
        resp = client.get("/ping")
        assert resp.status_code == 200

    def test_no_cert_checker_called_when_disabled(self):
        checker = MagicMock(return_value=False)
        app = _build_app(enabled=False, cert_checker=checker)
        TestClient(app).get("/ping")
        checker.assert_not_called()


class TestMTLSMiddlewareEnabled:
    def test_returns_403_when_no_cert(self):
        app = _build_app(enabled=True, cert_checker=lambda scope: False)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/ping")
        assert resp.status_code == 403

    def test_403_body_explains_cert_required(self):
        app = _build_app(enabled=True, cert_checker=lambda scope: False)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/ping")
        assert "cert" in resp.json()["detail"].lower()

    def test_passes_through_when_cert_present(self):
        app = _build_app(enabled=True, cert_checker=lambda scope: True)
        resp = TestClient(app).get("/ping")
        assert resp.status_code == 200

    def test_non_http_scope_not_checked(self):
        """WebSocket / lifespan scopes must not be blocked."""
        checked = []
        def checker(scope):
            checked.append(scope["type"])
            return False

        app = _build_app(enabled=True, cert_checker=checker)
        # Only HTTP scope triggers the checker; lifespan is not http
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/ping")
        assert all(t == "http" for t in checked)

    def test_all_paths_blocked_without_cert(self):
        app = _build_app(enabled=True, cert_checker=lambda scope: False)
        client = TestClient(app, raise_server_exceptions=False)
        for path in ["/ping", "/health", "/sessions"]:
            assert client.get(path).status_code == 403


# ── mtls_config_from_env ──────────────────────────────────────────────────────

class TestTransportCertChecker:
    def test_returns_true_when_no_transport(self):
        from adapters.security.mtls import _transport_cert_checker
        assert _transport_cert_checker({}) is True

    def test_returns_true_when_transport_has_no_get_extra_info(self):
        from adapters.security.mtls import _transport_cert_checker
        assert _transport_cert_checker({"transport": object()}) is True

    def test_returns_true_when_peer_cert_present(self):
        from unittest.mock import MagicMock
        from adapters.security.mtls import _transport_cert_checker
        transport = MagicMock()
        transport.get_extra_info.return_value = {"subject": []}  # non-None cert
        assert _transport_cert_checker({"transport": transport}) is True
        transport.get_extra_info.assert_called_once_with("peercert")

    def test_returns_false_when_peer_cert_absent(self):
        from unittest.mock import MagicMock
        from adapters.security.mtls import _transport_cert_checker
        transport = MagicMock()
        transport.get_extra_info.return_value = None  # no cert
        assert _transport_cert_checker({"transport": transport}) is False


class TestMTLSConfigFromEnv:
    def test_enabled_false_by_default(self, monkeypatch):
        monkeypatch.delenv("MTLS_ENABLED", raising=False)
        cfg = mtls_config_from_env()
        assert cfg["enabled"] is False

    def test_enabled_true_when_env_set(self, monkeypatch):
        monkeypatch.setenv("MTLS_ENABLED", "true")
        cfg = mtls_config_from_env()
        assert cfg["enabled"] is True

    def test_cert_paths_from_env(self, monkeypatch):
        monkeypatch.setenv("MTLS_CERT_FILE", "/custom/server.crt")
        monkeypatch.setenv("MTLS_KEY_FILE", "/custom/server.key")
        monkeypatch.setenv("MTLS_CA_FILE", "/custom/ca.crt")
        cfg = mtls_config_from_env()
        assert cfg["cert_file"] == "/custom/server.crt"
        assert cfg["key_file"] == "/custom/server.key"
        assert cfg["ca_file"] == "/custom/ca.crt"

    def test_default_cert_paths(self, monkeypatch):
        for key in ("MTLS_CERT_FILE", "MTLS_KEY_FILE", "MTLS_CA_FILE"):
            monkeypatch.delenv(key, raising=False)
        cfg = mtls_config_from_env()
        assert cfg["cert_file"] == "/etc/sandbox/certs/server.crt"
        assert cfg["key_file"] == "/etc/sandbox/certs/server.key"
        assert cfg["ca_file"] == "/etc/sandbox/certs/ca.crt"

    def test_enabled_false_for_any_non_true_value(self, monkeypatch):
        for val in ("false", "1", "yes", "TRUE", ""):
            monkeypatch.setenv("MTLS_ENABLED", val)
            assert mtls_config_from_env()["enabled"] is False
