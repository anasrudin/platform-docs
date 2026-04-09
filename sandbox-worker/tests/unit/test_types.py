"""Unit tests for core models (types)."""
from datetime import datetime, timezone

import pytest

from models.job import (
    ArtifactMeta,
    ArtifactUploadResponse,
    ExecuteRequest,
    ExecuteResponse,
    Job,
    JobStatus,
    RuntimeResult,
)
from models.session import (
    CreateSessionRequest,
    CreateSessionResponse,
    HealthResponse,
    Session,
    Tier,
)


def test_tier_values():
    assert Tier.WASM.value == "wasm"
    assert Tier.MICROVM.value == "microvm"
    assert Tier.GUI.value == "gui"


def test_tier_from_string():
    assert Tier("wasm") is Tier.WASM
    assert Tier("microvm") is Tier.MICROVM
    assert Tier("gui") is Tier.GUI


def test_job_status_values():
    assert JobStatus.PENDING.value == "pending"
    assert JobStatus.RUNNING.value == "running"
    assert JobStatus.COMPLETED.value == "completed"
    assert JobStatus.FAILED.value == "failed"


def test_session_creation():
    now = datetime.now(timezone.utc)
    s = Session(id="abc", runtime=Tier.WASM, status="active",
                created_at=now, updated_at=now)
    assert s.id == "abc"
    assert s.runtime is Tier.WASM


def test_job_defaults():
    now = datetime.now(timezone.utc)
    j = Job(id="j1", session_id="s1", tool="echo",
            tier=Tier.WASM, input={}, status=JobStatus.PENDING,
            created_at=now, updated_at=now)
    assert j.output == ""
    assert j.error_message == ""
    assert j.duration_ms == 0


def test_runtime_result_defaults():
    r = RuntimeResult()
    assert r.stdout == ""
    assert r.stderr == ""
    assert r.exit_code == 0


def test_runtime_result_fields():
    r = RuntimeResult(stdout="hello", stderr="warn", exit_code=1)
    assert r.stdout == "hello"
    assert r.exit_code == 1


def test_health_response():
    h = HealthResponse(status="healthy", version="0.1.0",
                       services={"redis": "healthy"})
    assert h.status == "healthy"
    assert h.services["redis"] == "healthy"


def test_artifact_meta():
    a = ArtifactMeta(id="a1", name="file.txt", key="a1/file.txt",
                     url="http://localhost/a1/file.txt", size=100,
                     content_type="text/plain")
    assert a.session_id == ""  # optional default


def test_create_session_request_default():
    r = CreateSessionRequest()
    assert r.runtime == "wasm"
