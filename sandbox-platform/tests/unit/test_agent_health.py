"""Unit tests for the per-agent health server FastAPI app."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sandbox_platform.consul.health_server import make_health_app


class TestHealthEndpoint:
    def _client(self, runtime: str, pool_size: int = 0) -> TestClient:
        app = make_health_app(runtime_name=runtime, pool_size_fn=lambda: pool_size)
        return TestClient(app)

    def test_returns_200(self):
        c = self._client("firecracker-sim")
        resp = c.get("/health")
        assert resp.status_code == 200

    def test_response_has_status_ok(self):
        c = self._client("wasm-sim")
        data = c.get("/health").json()
        assert data["status"] == "ok"

    def test_response_has_runtime_name(self):
        c = self._client("firecracker-sim")
        data = c.get("/health").json()
        assert data["runtime"] == "firecracker-sim"

    def test_response_has_pool_size(self):
        c = self._client("firecracker-sim", pool_size=4)
        data = c.get("/health").json()
        assert data["pool_size"] == 4

    def test_pool_size_zero_for_wasm(self):
        c = self._client("wasm-sim", pool_size=0)
        data = c.get("/health").json()
        assert data["pool_size"] == 0

    def test_pool_size_reflects_fn(self):
        count = [3]
        app = make_health_app("fc", pool_size_fn=lambda: count[0])
        c = TestClient(app)
        assert c.get("/health").json()["pool_size"] == 3
        count[0] = 7
        assert c.get("/health").json()["pool_size"] == 7

    def test_unknown_path_returns_404(self):
        c = self._client("gui-runtime-stub")
        resp = c.get("/not-a-real-endpoint")
        assert resp.status_code == 404

    def test_each_runtime_name_is_distinct(self):
        for name in ("firecracker-sim", "wasm-sim", "gui-runtime-stub"):
            c = self._client(name)
            assert c.get("/health").json()["runtime"] == name


class TestStartHealthServer:
    def test_starts_daemon_thread(self):
        from unittest.mock import MagicMock, patch
        import sandbox_platform.consul.health_server as hs

        mock_thread = MagicMock()
        mock_server = MagicMock()

        with (
            patch("sandbox_platform.consul.health_server.uvicorn.Config"),
            patch(
                "sandbox_platform.consul.health_server.uvicorn.Server",
                return_value=mock_server,
            ),
            patch(
                "sandbox_platform.consul.health_server.threading.Thread",
                return_value=mock_thread,
            ) as mock_thread_cls,
        ):
            hs.start_health_server(9999, "fc-sim", lambda: 2)

        mock_thread_cls.assert_called_once()
        _, kwargs = mock_thread_cls.call_args
        assert kwargs.get("daemon") is True
        mock_thread.start.assert_called_once()
