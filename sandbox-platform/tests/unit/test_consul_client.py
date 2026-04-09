"""Unit tests for sandbox_platform.consul.client.ConsulClient.

Tests use httpx mock transport so no real Consul instance is needed.
"""

from __future__ import annotations

import json

import httpx
import pytest

from sandbox_platform.consul.client import ConsulClient


class _MockTransport(httpx.AsyncBaseTransport):
    """Configurable mock transport for httpx.AsyncClient."""

    def __init__(self, responses: dict[tuple[str, str], httpx.Response]) -> None:
        # key: (METHOD, path_prefix) → Response
        self._responses = responses
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        for (method, path), resp in self._responses.items():
            if request.method == method and request.url.path.startswith(path):
                return resp
        return httpx.Response(404, json={"error": "not found"})


def _ok(body: object = "") -> httpx.Response:
    if isinstance(body, (dict, list)):
        return httpx.Response(200, json=body)
    return httpx.Response(200, text=str(body))


def _consul(transport: _MockTransport) -> ConsulClient:
    client = ConsulClient(host="127.0.0.1", port=8500)
    # Inject mock transport
    client._transport = transport
    return client


# ── register_service ──────────────────────────────────────────────────────────


class TestRegisterService:
    @pytest.mark.asyncio
    async def test_sends_put_to_agent_register(self):
        transport = _MockTransport({("PUT", "/v1/agent/service/register"): _ok()})
        c = _consul(transport)

        await c.register_service(
            name="fc-agent",
            service_id="fc-agent-1",
            address="127.0.0.1",
            port=8081,
            health_url="http://127.0.0.1:8081/health",
            tags=["sandbox", "firecracker"],
        )

        assert len(transport.requests) == 1
        req = transport.requests[0]
        assert req.method == "PUT"
        assert "/v1/agent/service/register" in req.url.path

    @pytest.mark.asyncio
    async def test_register_payload_contains_service_fields(self):
        transport = _MockTransport({("PUT", "/v1/agent/service/register"): _ok()})
        c = _consul(transport)

        await c.register_service(
            name="wasm-agent",
            service_id="wasm-agent-1",
            address="10.0.0.1",
            port=8082,
            health_url="http://10.0.0.1:8082/health",
            tags=["wasm"],
        )

        body = json.loads(transport.requests[0].content)
        assert body["Name"] == "wasm-agent"
        assert body["ID"] == "wasm-agent-1"
        assert body["Address"] == "10.0.0.1"
        assert body["Port"] == 8082
        assert "wasm" in body["Tags"]
        assert body["Check"]["HTTP"] == "http://10.0.0.1:8082/health"

    @pytest.mark.asyncio
    async def test_register_raises_on_non_200(self):
        transport = _MockTransport(
            {("PUT", "/v1/agent/service/register"): httpx.Response(500)}
        )
        c = _consul(transport)

        with pytest.raises(RuntimeError, match="register"):
            await c.register_service(
                name="x",
                service_id="x-1",
                address="127.0.0.1",
                port=9000,
                health_url="http://127.0.0.1:9000/health",
                tags=[],
            )


# ── deregister_service ────────────────────────────────────────────────────────


class TestDeregisterService:
    @pytest.mark.asyncio
    async def test_sends_put_to_deregister(self):
        transport = _MockTransport(
            {
                ("PUT", "/v1/agent/service/deregister"): _ok(),
            }
        )
        c = _consul(transport)

        await c.deregister_service("fc-agent-1")

        req = transport.requests[0]
        assert req.method == "PUT"
        assert "fc-agent-1" in req.url.path

    @pytest.mark.asyncio
    async def test_deregister_raises_on_non_200(self):
        transport = _MockTransport(
            {
                ("PUT", "/v1/agent/service/deregister"): httpx.Response(500),
            }
        )
        c = _consul(transport)

        with pytest.raises(RuntimeError, match="deregister"):
            await c.deregister_service("fc-agent-1")


# ── KV operations ─────────────────────────────────────────────────────────────


class TestKVOperations:
    @pytest.mark.asyncio
    async def test_put_kv_sends_put(self):
        transport = _MockTransport({("PUT", "/v1/kv/"): _ok()})
        c = _consul(transport)

        await c.put_kv("sandbox/sessions/abc", "wasm")

        req = transport.requests[0]
        assert req.method == "PUT"
        assert "sandbox/sessions/abc" in req.url.path
        assert req.content == b"wasm"

    @pytest.mark.asyncio
    async def test_get_kv_returns_value(self):
        transport = _MockTransport({("GET", "/v1/kv/"): _ok("wasm")})
        c = _consul(transport)

        val = await c.get_kv("sandbox/sessions/abc")

        assert val == "wasm"

    @pytest.mark.asyncio
    async def test_get_kv_returns_none_on_404(self):
        transport = _MockTransport({})  # no routes → 404
        c = _consul(transport)

        val = await c.get_kv("sandbox/sessions/missing")

        assert val is None

    @pytest.mark.asyncio
    async def test_delete_kv_sends_delete(self):
        transport = _MockTransport({("DELETE", "/v1/kv/"): _ok()})
        c = _consul(transport)

        await c.delete_kv("sandbox/sessions/abc")

        req = transport.requests[0]
        assert req.method == "DELETE"
        assert "sandbox/sessions/abc" in req.url.path

    @pytest.mark.asyncio
    async def test_kv_round_trip(self):
        """Write → Read → Delete session KV."""
        store: dict[str, str] = {}

        class RoundTripTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(
                self, request: httpx.Request
            ) -> httpx.Response:
                key = request.url.path.removeprefix("/v1/kv/")
                if request.method == "PUT":
                    store[key] = request.content.decode()
                    return httpx.Response(200, text="true")
                if request.method == "GET":
                    if key in store:
                        return httpx.Response(200, text=store[key])
                    return httpx.Response(404)
                if request.method == "DELETE":
                    store.pop(key, None)
                    return httpx.Response(200, text="true")
                return httpx.Response(405)

        c = ConsulClient(host="127.0.0.1", port=8500)
        c._transport = RoundTripTransport()

        await c.put_kv("sandbox/sessions/s1", "microvm")
        val = await c.get_kv("sandbox/sessions/s1")
        assert val == "microvm"
        await c.delete_kv("sandbox/sessions/s1")
        val = await c.get_kv("sandbox/sessions/s1")
        assert val is None

    @pytest.mark.asyncio
    async def test_put_kv_raises_on_non_200(self):
        transport = _MockTransport({("PUT", "/v1/kv/"): httpx.Response(500)})
        c = _consul(transport)

        with pytest.raises(RuntimeError, match="put_kv"):
            await c.put_kv("k", "v")

    @pytest.mark.asyncio
    async def test_delete_kv_raises_on_non_200(self):
        transport = _MockTransport({("DELETE", "/v1/kv/"): httpx.Response(500)})
        c = _consul(transport)

        with pytest.raises(RuntimeError, match="delete_kv"):
            await c.delete_kv("k")


# ── Token header ──────────────────────────────────────────────────────────────


class TestTokenHeader:
    @pytest.mark.asyncio
    async def test_token_sent_in_header(self):
        transport = _MockTransport({("PUT", "/v1/kv/"): _ok()})
        c = ConsulClient(host="127.0.0.1", port=8500, token="my-secret")
        c._transport = transport

        await c.put_kv("k", "v")

        req = transport.requests[0]
        assert req.headers.get("X-Consul-Token") == "my-secret"

    @pytest.mark.asyncio
    async def test_no_token_no_header(self):
        transport = _MockTransport({("PUT", "/v1/kv/"): _ok()})
        c = _consul(transport)

        await c.put_kv("k", "v")

        req = transport.requests[0]
        assert "X-Consul-Token" not in req.headers

    @pytest.mark.asyncio
    async def test_get_kv_raises_on_non_200_non_404(self):
        transport = _MockTransport({("GET", "/v1/kv/"): httpx.Response(500)})
        c = _consul(transport)

        with pytest.raises(RuntimeError, match="get_kv"):
            await c.get_kv("k")
