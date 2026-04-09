"""Unit tests for sandbox_platform.queue.client."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from adapters.queue.redis_queue import Client, Consumer, JobMessage, Producer
from models.job import Job, JobStatus, RuntimeResult
from models.session import Tier


def _make_job(tool: str = "echo", tier: Tier = Tier.WASM) -> Job:
    now = datetime.now(timezone.utc)
    return Job(
        id="j-test",
        session_id="s-test",
        tool=tool,
        tier=tier,
        input={"k": "v"},
        status=JobStatus.PENDING,
        created_at=now,
        updated_at=now,
    )


def _serialised_job(job: Job) -> str:
    return json.dumps(
        {
            "id": job.id,
            "session_id": job.session_id,
            "tool": job.tool,
            "tier": job.tier.value,
            "input": job.input,
            "status": job.status.value,
            "output": job.output,
            "error_message": job.error_message,
            "duration_ms": job.duration_ms,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
        }
    )


class TestClient:
    def test_push_job_calls_rpush(self):
        rdb = MagicMock()
        client = Client(rdb)
        job = _make_job()

        client.push_job(job)

        rdb.rpush.assert_called_once()
        args = rdb.rpush.call_args[0]
        assert args[0] == "queue:wasm"
        data = json.loads(args[1])
        assert data["id"] == "j-test"
        assert data["tool"] == "echo"

    def test_push_job_microvm_queue(self):
        rdb = MagicMock()
        client = Client(rdb)
        job = _make_job("python_run", Tier.MICROVM)

        client.push_job(job)

        queue_name = rdb.rpush.call_args[0][0]
        assert queue_name == "queue:microvm"

    def test_wait_for_job_result_success(self):
        rdb = MagicMock()
        result_data = json.dumps({"stdout": "hello", "stderr": "", "exit_code": 0})
        rdb.blpop.return_value = ("result:j-test", result_data)
        client = Client(rdb)

        result = client.wait_for_job_result("j-test", timeout=5)

        rdb.blpop.assert_called_once_with("result:j-test", timeout=5)
        assert result.stdout == "hello"
        assert result.exit_code == 0

    def test_wait_for_job_result_timeout(self):
        rdb = MagicMock()
        rdb.blpop.return_value = None
        client = Client(rdb)

        with pytest.raises(TimeoutError, match="j-test"):
            client.wait_for_job_result("j-test", timeout=1)

    def test_pop_job_returns_job(self):
        rdb = MagicMock()
        job = _make_job()
        rdb.blpop.return_value = ("queue:wasm", _serialised_job(job))
        client = Client(rdb)

        popped = client.pop_job(Tier.WASM, timeout=1)

        assert popped.id == job.id
        assert popped.tool == job.tool
        assert popped.tier is Tier.WASM

    def test_publish_job_result_sets_expiry(self):
        rdb = MagicMock()
        client = Client(rdb)
        result = RuntimeResult(stdout="out", stderr="", exit_code=0)

        client.publish_job_result("j-test", result)

        rdb.rpush.assert_called_once()
        rdb.expire.assert_called_once_with("result:j-test", 300)
        # Verify data content
        raw = rdb.rpush.call_args[0][1]
        data = json.loads(raw)
        assert data["stdout"] == "out"
        assert data["exit_code"] == 0


class TestProducer:
    def test_push_serialises_message(self):
        rdb = MagicMock()
        producer = Producer(rdb, "my-stream")
        msg = JobMessage(
            job_id="j1", tool="echo", tier="wasm", agent_id="a1", input='{"x":1}'
        )

        producer.push(msg)

        rdb.rpush.assert_called_once()
        args = rdb.rpush.call_args[0]
        assert args[0] == "my-stream"
        data = json.loads(args[1])
        assert data["job_id"] == "j1"
        assert data["tool"] == "echo"


class TestConsumer:
    def test_run_calls_handler_and_stops(self):
        rdb = MagicMock()
        msg_data = json.dumps(
            {
                "job_id": "j1",
                "tool": "echo",
                "tier": "wasm",
                "agent_id": "a1",
                "input": "",
            }
        )
        # First call returns a message; second call triggers stop via side effect
        call_count = [0]
        received: list[JobMessage] = []

        consumer = Consumer(rdb, "my-stream", lambda m: received.append(m))

        def fake_blpop(stream, timeout):
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                return ("my-stream", msg_data)
            consumer.stop()
            return None

        rdb.blpop.side_effect = fake_blpop
        consumer.run()

        assert len(received) == 1
        assert received[0].job_id == "j1"
