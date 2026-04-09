"""Unit tests for sandbox_platform.session.consul_store.SessionStore."""

from __future__ import annotations

import json

import httpx
import pytest

from sandbox_platform.consul.client import ConsulClient
from sandbox_platform.session.consul_store import SessionStore


# ── Mock transport ─────────────────────────────────────────────────────────────


class _KVTransport(httpx.AsyncBaseTransport):
    """In-memory Consul KV store transport."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = request.url.path.removeprefix("/v1/kv/")
        if request.method == "PUT":
            self.store[key] = request.content.decode()
            return httpx.Response(200, text="true")
        if request.method == "GET":
            if key in self.store:
                return httpx.Response(200, text=self.store[key])
            return httpx.Response(404)
        if request.method == "DELETE":
            self.store.pop(key, None)
            return httpx.Response(200, text="true")
        return httpx.Response(405)


def _store() -> tuple[SessionStore, _KVTransport]:
    transport = _KVTransport()
    consul = ConsulClient(host="127.0.0.1", port=8500)
    consul._transport = transport
    return SessionStore(consul), transport


# ── put ────────────────────────────────────────────────────────────────────────


class TestPut:
    @pytest.mark.asyncio
    async def test_put_writes_to_consul_kv(self):
        store, transport = _store()
        await store.put("s-1", tier="wasm", agent_id="wasm-agent-1")
        assert len(transport.requests) == 1
        req = transport.requests[0]
        assert req.method == "PUT"
        assert "sandbox/sessions/s-1" in req.url.path

    @pytest.mark.asyncio
    async def test_put_value_is_json_with_tier_and_agent(self):
        store, transport = _store()
        await store.put("s-2", tier="microvm", agent_id="fc-agent-1")
        raw = transport.store["sandbox/sessions/s-2"]
        data = json.loads(raw)
        assert data["tier"] == "microvm"
        assert data["agent_id"] == "fc-agent-1"

    @pytest.mark.asyncio
    async def test_put_agent_id_optional(self):
        store, transport = _store()
        await store.put("s-3", tier="wasm")
        raw = transport.store["sandbox/sessions/s-3"]
        data = json.loads(raw)
        assert data["tier"] == "wasm"
        assert data["agent_id"] == ""


# ── get ────────────────────────────────────────────────────────────────────────


class TestGet:
    @pytest.mark.asyncio
    async def test_get_returns_dict_when_present(self):
        store, transport = _store()
        transport.store["sandbox/sessions/s-10"] = json.dumps(
            {"tier": "gui", "agent_id": "gui-agent-1"}
        )
        result = await store.get("s-10")
        assert result is not None
        assert result["tier"] == "gui"
        assert result["agent_id"] == "gui-agent-1"

    @pytest.mark.asyncio
    async def test_get_returns_none_when_missing(self):
        store, _ = _store()
        result = await store.get("s-missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_reads_from_correct_key(self):
        store, transport = _store()
        transport.store["sandbox/sessions/s-99"] = json.dumps(
            {"tier": "wasm", "agent_id": ""}
        )
        await store.get("s-99")
        req = transport.requests[0]
        assert "sandbox/sessions/s-99" in req.url.path


# ── delete ────────────────────────────────────────────────────────────────────


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_removes_key(self):
        store, transport = _store()
        transport.store["sandbox/sessions/s-del"] = json.dumps(
            {"tier": "wasm", "agent_id": ""}
        )
        await store.delete("s-del")
        assert "sandbox/sessions/s-del" not in transport.store

    @pytest.mark.asyncio
    async def test_delete_sends_delete_request(self):
        store, transport = _store()
        transport.store["sandbox/sessions/s-del2"] = json.dumps(
            {"tier": "wasm", "agent_id": ""}
        )
        await store.delete("s-del2")
        req = transport.requests[0]
        assert req.method == "DELETE"
        assert "sandbox/sessions/s-del2" in req.url.path

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key_does_not_raise(self):
        store, _ = _store()
        # 404 from transport → should not raise (key already gone)
        await store.delete("s-never-existed")

    @pytest.mark.asyncio
    async def test_delete_re_raises_non_404_errors(self):
        """A server error (500) during delete should propagate."""

        class ErrorTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                if request.method == "DELETE":
                    return httpx.Response(500, text="internal error")
                return httpx.Response(200, text="true")

        consul = ConsulClient(host="127.0.0.1", port=8500)
        consul._transport = ErrorTransport()
        store = SessionStore(consul)

        with pytest.raises(RuntimeError):
            await store.delete("s-error")


# ── round-trip ────────────────────────────────────────────────────────────────


class TestRoundTrip:
    @pytest.mark.asyncio
    async def test_put_get_delete_cycle(self):
        store, _ = _store()

        await store.put("s-rt", tier="microvm", agent_id="fc-agent-42")
        got = await store.get("s-rt")
        assert got is not None
        assert got["tier"] == "microvm"
        assert got["agent_id"] == "fc-agent-42"

        await store.delete("s-rt")
        gone = await store.get("s-rt")
        assert gone is None

    @pytest.mark.asyncio
    async def test_multiple_sessions_are_independent(self):
        store, _ = _store()
        await store.put("s-a", tier="wasm")
        await store.put("s-b", tier="gui")

        a = await store.get("s-a")
        b = await store.get("s-b")
        assert a["tier"] == "wasm"
        assert b["tier"] == "gui"

        await store.delete("s-a")
        assert await store.get("s-a") is None
        assert await store.get("s-b") is not None
