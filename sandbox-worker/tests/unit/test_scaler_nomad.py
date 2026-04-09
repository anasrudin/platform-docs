"""Unit tests for sandbox_platform.scaler.nomad.NomadClient."""
from __future__ import annotations

import json

import httpx
import pytest

from scaler import NomadClient


class _MockTransport(httpx.AsyncBaseTransport):
    def __init__(self, routes: dict[tuple[str, str], httpx.Response]) -> None:
        self._routes = routes
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        for (method, path_prefix), resp in self._routes.items():
            if request.method == method and request.url.path.startswith(path_prefix):
                return resp
        return httpx.Response(404, json={"error": "not found"})


def _nomad(routes: dict) -> tuple[NomadClient, _MockTransport]:
    transport = _MockTransport(routes)
    client = NomadClient(address="http://127.0.0.1:4646", transport=transport)
    return client, transport


JOB_RESPONSE = {
    "ID": "fc-agent",
    "TaskGroups": [
        {"Name": "agent", "Count": 3},
    ],
}


class TestJobCount:
    @pytest.mark.asyncio
    async def test_returns_group_count(self):
        client, _ = _nomad({
            ("GET", "/v1/job/fc-agent"): httpx.Response(200, json=JOB_RESPONSE),
        })
        count = await client.job_count("fc-agent", "agent")
        assert count == 3

    @pytest.mark.asyncio
    async def test_raises_on_unknown_group(self):
        client, _ = _nomad({
            ("GET", "/v1/job/fc-agent"): httpx.Response(200, json=JOB_RESPONSE),
        })
        with pytest.raises(KeyError, match="no-such-group"):
            await client.job_count("fc-agent", "no-such-group")

    @pytest.mark.asyncio
    async def test_raises_on_non_200(self):
        client, _ = _nomad({
            ("GET", "/v1/job/fc-agent"): httpx.Response(404, json={"error": "not found"}),
        })
        with pytest.raises(RuntimeError, match="job_count"):
            await client.job_count("fc-agent", "agent")


class TestScaleJob:
    @pytest.mark.asyncio
    async def test_sends_post_to_scale_endpoint(self):
        client, transport = _nomad({
            ("POST", "/v1/job/fc-agent/scale"): httpx.Response(200, json={"EvalID": "abc"}),
        })
        await client.scale_job("fc-agent", "agent", count=5, reason="high load")
        assert len(transport.requests) == 1
        req = transport.requests[0]
        assert req.method == "POST"
        assert "/v1/job/fc-agent/scale" in req.url.path

    @pytest.mark.asyncio
    async def test_scale_payload_contains_count_and_group(self):
        client, transport = _nomad({
            ("POST", "/v1/job/fc-agent/scale"): httpx.Response(200, json={"EvalID": "abc"}),
        })
        await client.scale_job("fc-agent", "agent", count=4, reason="utilization low")
        body = json.loads(transport.requests[0].content)
        assert body["Count"] == 4
        assert body["Target"]["Group"] == "agent"

    @pytest.mark.asyncio
    async def test_scale_payload_includes_reason(self):
        client, transport = _nomad({
            ("POST", "/v1/job/fc-agent/scale"): httpx.Response(200, json={"EvalID": "abc"}),
        })
        await client.scale_job("fc-agent", "agent", count=2, reason="scale-down test")
        body = json.loads(transport.requests[0].content)
        assert "scale-down test" in body.get("Message", "")

    @pytest.mark.asyncio
    async def test_raises_on_non_200(self):
        client, _ = _nomad({
            ("POST", "/v1/job/fc-agent/scale"): httpx.Response(500, text="error"),
        })
        with pytest.raises(RuntimeError, match="scale_job"):
            await client.scale_job("fc-agent", "agent", count=2)

    @pytest.mark.asyncio
    async def test_token_sent_in_header_when_provided(self):
        transport = _MockTransport({
            ("POST", "/v1/job/fc-agent/scale"): httpx.Response(200, json={"EvalID": "x"}),
        })
        client = NomadClient(
            address="http://127.0.0.1:4646",
            token="nomad-secret",
            transport=transport,
        )
        await client.scale_job("fc-agent", "agent", count=3)
        assert transport.requests[0].headers.get("X-Nomad-Token") == "nomad-secret"
