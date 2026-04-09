# Phase 3 Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement three missing Phase 3 features: Docker image split (office-agent), DAG Workflow execution, and Continuous Snapshot per-session.

**Architecture:** WorkflowService executes a DAG of steps wave-by-wave using ThreadPoolExecutor for parallel branches; output is interpolated with `$steps.step_id.output` syntax. Continuous snapshot extends SnapshotDownloader with per-session storage keys (`sessions/{session_id}/`) and is opt-in via `snapshot_mode=continuous` in the session request.

**Tech Stack:** Python 3.12, FastAPI, pytest, concurrent.futures.ThreadPoolExecutor, structlog. All code under `sandbox-worker/`. Tests run with `PYTHONPATH=src uv run pytest`.

---

## File Map

| File | Action |
|------|--------|
| `sandbox-worker/pyproject.toml` | Edit — add `pythonpath = ["src"]` to pytest options |
| `docker/gui-agent/Dockerfile` | Edit — remove LibreOffice + `playwright install chromium` |
| `docker/office-agent/Dockerfile` | Create — LibreOffice image |
| `services/controller/nomad/jobs/sandbox-worker.nomad` | Edit — add office-agent group |
| `sandbox-worker/src/service/workflow.py` | Create — WorkflowService, _interpolate, errors |
| `sandbox-worker/src/api/routes/workflow.py` | Create — POST /workflows, GET /workflows/{id} |
| `sandbox-worker/src/api/app.py` | Edit — register workflow router |
| `sandbox-worker/src/models/session.py` | Edit — add SnapshotMode enum + fields |
| `sandbox-worker/src/service/session.py` | Edit — accept snapshot_mode in create() |
| `sandbox-worker/src/orchestrator/snapshot.py` | Edit — add 3 session snapshot methods |
| `sandbox-worker/src/service/execution.py` | Edit — add downloader param + snapshot logic |
| `sandbox-worker/src/api/routes/session.py` | Edit — forward snapshot_mode |
| `sandbox-worker/src/api/routes/snapshot.py` | Create — DELETE /snapshots/{session_id} |
| `sandbox-worker/src/api/app.py` | Edit — inject downloader, register snapshot router |
| `sandbox-worker/tests/unit/test_continuous_snapshot.py` | Create |

---

## Task 1: Fix pytest PYTHONPATH

**Files:**
- Modify: `sandbox-worker/pyproject.toml`

- [ ] **Step 1: Verify tests fail without fix**

```bash
cd sandbox-worker
uv run pytest tests/unit/test_workflow.py -x 2>&1 | tail -5
```
Expected: `ModuleNotFoundError: No module named 'adapters'`

- [ ] **Step 2: Add pythonpath to pyproject.toml**

In `sandbox-worker/pyproject.toml`, find `[tool.pytest.ini_options]` and update:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
pythonpath = ["src"]
```

- [ ] **Step 3: Verify tests can now be collected (but still fail on missing modules)**

```bash
cd sandbox-worker
uv run pytest tests/unit/test_workflow.py -x 2>&1 | tail -5
```
Expected: `ModuleNotFoundError: No module named 'service.workflow'` (collection succeeds, import fails on the missing service)

- [ ] **Step 4: Commit**

```bash
cd sandbox-worker
git add pyproject.toml
git commit -m "fix: add pythonpath=src to pytest config"
```

---

## Task 2: Docker — Fix gui-agent, create office-agent

**Files:**
- Modify: `docker/gui-agent/Dockerfile`
- Create: `docker/office-agent/Dockerfile`
- Modify: `services/controller/nomad/jobs/sandbox-worker.nomad`

- [ ] **Step 1: Fix gui-agent Dockerfile**

Replace the entire contents of `docker/gui-agent/Dockerfile`:

```dockerfile
# Build from repo root: docker build -f docker/gui-agent/Dockerfile .
FROM sandbox-base:latest

LABEL org.opencontainers.image.title="sandbox-gui-agent"
LABEL org.opencontainers.image.description="GUI runtime worker — Chromium + Playwright + Xvfb"

# ── Display server + browser ───────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11vnc \
    xdotool \
    chromium-browser \
    chromium-chromedriver \
    fonts-liberation \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# ── Playwright — use system Chromium, skip browser download ───────────────────
RUN pip3 install --no-cache-dir playwright
ENV PLAYWRIGHT_BROWSERS_PATH=/usr/bin

ENV DISPLAY=:99
ENV RUNTIME_TIER=gui

USER sandbox
EXPOSE 8080 5900

CMD ["python3", "-m", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 2: Create office-agent Dockerfile**

Create `docker/office-agent/Dockerfile`:

```dockerfile
# Build from repo root: docker build -f docker/office-agent/Dockerfile .
FROM sandbox-base:latest

LABEL org.opencontainers.image.title="sandbox-office-agent"
LABEL org.opencontainers.image.description="Office runtime worker — LibreOffice document processing"

# ── LibreOffice + fonts ────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    libreoffice-calc \
    libreoffice-writer \
    libreoffice-impress \
    fonts-liberation \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

ENV RUNTIME_TIER=office

USER sandbox
EXPOSE 8080

CMD ["python3", "-m", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 3: Add office-agent group to Nomad job spec**

Read `services/controller/nomad/jobs/sandbox-worker.nomad`. Find the `group "gui-agent"` block and add an `office-agent` group directly after it:

```hcl
  group "office-agent" {
    count = 1

    constraint {
      attribute = "${node.class}"
      value     = "office"
    }

    network {
      port "http" {
        static = 8084
      }
    }

    task "office-agent" {
      driver = "docker"

      config {
        image = "sandbox-office-agent:latest"
        ports = ["http"]
      }

      env {
        RUNTIME_TIER     = "office"
        CONSUL_ENABLED   = "true"
        MINIO_ENDPOINT   = "http://minio:9000"
      }

      resources {
        cpu    = 1000
        memory = 1024
      }

      service {
        name = "sandbox-office-agent"
        port = "http"
        tags = ["sandbox", "office"]

        check {
          type     = "http"
          path     = "/health"
          interval = "10s"
          timeout  = "3s"
        }
      }
    }
  }
```

- [ ] **Step 4: Commit**

```bash
git add docker/gui-agent/Dockerfile docker/office-agent/Dockerfile services/controller/nomad/jobs/sandbox-worker.nomad
git commit -m "feat: split office-agent from gui-agent, fix Playwright Chromium duplication"
```

---

## Task 3: Workflow Service — _interpolate and validation

**Files:**
- Create: `sandbox-worker/src/service/workflow.py`
- Test: `sandbox-worker/tests/unit/test_workflow.py` (already exists — run it to verify)

- [ ] **Step 1: Run existing test to confirm it fails**

```bash
cd sandbox-worker
uv run pytest tests/unit/test_workflow.py -x 2>&1 | tail -5
```
Expected: `ModuleNotFoundError: No module named 'service.workflow'`

- [ ] **Step 2: Create service/workflow.py with stubs and _interpolate**

Create `sandbox-worker/src/service/workflow.py`:

```python
"""WorkflowService — DAG execution with interpolation."""
from __future__ import annotations

import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import structlog

from models.workflow import (
    DAGWorkflow,
    StepResult,
    StepStatus,
    WorkflowStatus,
    WorkflowStep,
)

log = structlog.get_logger()


class WorkflowValidationError(ValueError):
    pass


class CyclicDependencyError(ValueError):
    pass


# ── Interpolation ─────────────────────────────────────────────────────────────

_REF_PATTERN = re.compile(r'\$steps\.([^.\s$]+)\.output((?:\.[^.\s$]+)*)')


def _resolve_ref(step_id: str, field_path: str, results: dict[str, StepResult]) -> Any:
    """Resolve $steps.step_id.output[.field...] → value, or original string if missing."""
    original = f"$steps.{step_id}.output{field_path}"
    result = results.get(step_id)
    if result is None or result.output is None:
        return original
    value = result.output
    if field_path:
        for field in field_path.lstrip(".").split("."):
            if isinstance(value, dict) and field in value:
                value = value[field]
            else:
                return original
    return value


def _interpolate(value: Any, results: dict[str, StepResult]) -> Any:
    """Recursively replace $steps.step_id.output[.field] references in value."""
    if isinstance(value, str):
        full = _REF_PATTERN.fullmatch(value)
        if full:
            return _resolve_ref(full.group(1), full.group(2), results)

        def _replace(m: re.Match) -> str:
            resolved = _resolve_ref(m.group(1), m.group(2), results)
            if resolved == f"$steps.{m.group(1)}.output{m.group(2)}":
                return m.group(0)
            return str(resolved)

        return _REF_PATTERN.sub(_replace, value)

    if isinstance(value, dict):
        return {k: _interpolate(v, results) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(item, results) for item in value]
    return value
```

- [ ] **Step 3: Run interpolation tests only**

```bash
cd sandbox-worker
uv run pytest tests/unit/test_workflow.py::TestInterpolation -v 2>&1 | tail -15
```
Expected: all `TestInterpolation` tests pass.

- [ ] **Step 4: Add WorkflowService to service/workflow.py**

Append to `sandbox-worker/src/service/workflow.py`:

```python
# ── WorkflowService ───────────────────────────────────────────────────────────

class WorkflowService:
    _DEFAULT_MAX_STEPS = 20

    def __init__(
        self,
        executor: Callable[[str, dict], dict] | None = None,
        max_steps: int | None = None,
    ) -> None:
        self._executor = executor or _noop_executor
        self._max_steps = max_steps if max_steps is not None else self._DEFAULT_MAX_STEPS
        self._workflows: dict[str, DAGWorkflow] = {}

    def create(self, name: str, steps: list[dict]) -> dict:
        if len(steps) > self._max_steps:
            raise WorkflowValidationError(
                f"too many steps: {len(steps)} > {self._max_steps}"
            )

        step_ids: set[str] = set()
        parsed: list[WorkflowStep] = []
        for raw in steps:
            if "id" not in raw:
                raise WorkflowValidationError("missing 'id'")
            if "tool" not in raw:
                raise WorkflowValidationError("missing 'tool'")
            step_ids.add(raw["id"])
            parsed.append(
                WorkflowStep(
                    id=raw["id"],
                    tool=raw["tool"],
                    input=raw.get("input", {}),
                    depends_on=raw.get("depends_on", []),
                )
            )

        for step in parsed:
            for dep in step.depends_on:
                if dep not in step_ids:
                    raise WorkflowValidationError(
                        f"unknown step '{dep}' referenced in depends_on of '{step.id}'"
                    )

        waves = self._toposort(parsed)
        wf = DAGWorkflow(id=f"wf-{uuid.uuid4()}", name=name, steps=parsed)
        self._workflows[wf.id] = wf
        self._execute(wf, waves)
        return {"workflow_id": wf.id}

    def wait(self, workflow_id: str) -> dict:
        """Execution is synchronous; this just returns the current state."""
        return self.get(workflow_id)

    def get(self, workflow_id: str) -> dict:
        wf = self._workflows.get(workflow_id)
        if wf is None:
            raise KeyError(f"Workflow {workflow_id!r} not found")
        return wf.as_dict()

    # ── private ────────────────────────────────────────────────────────────────

    def _toposort(self, steps: list[WorkflowStep]) -> list[list[WorkflowStep]]:
        """Kahn's algorithm — returns execution waves; raises CyclicDependencyError on cycle."""
        by_id = {s.id: s for s in steps}
        in_degree = {s.id: len(s.depends_on) for s in steps}
        dependents: dict[str, list[str]] = {s.id: [] for s in steps}

        for step in steps:
            for dep in step.depends_on:
                dependents[dep].append(step.id)

        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        waves: list[list[WorkflowStep]] = []
        visited = 0

        while queue:
            wave_ids = list(queue)
            queue = []
            waves.append([by_id[sid] for sid in wave_ids])
            visited += len(wave_ids)
            for sid in wave_ids:
                for child_id in dependents[sid]:
                    in_degree[child_id] -= 1
                    if in_degree[child_id] == 0:
                        queue.append(child_id)

        if visited < len(steps):
            raise CyclicDependencyError("cycle detected in workflow DAG")

        return waves

    def _can_run(self, step: WorkflowStep, results: dict[str, StepResult]) -> bool:
        return all(
            results.get(dep, StepResult(step_id=dep)).status == StepStatus.COMPLETED
            for dep in step.depends_on
        )

    def _run_step(self, step: WorkflowStep, results: dict[str, StepResult]) -> None:
        r = StepResult(step_id=step.id, status=StepStatus.RUNNING)
        r.started_at = datetime.now(timezone.utc)
        results[step.id] = r
        try:
            interpolated = _interpolate(step.input, results)
            r.output = self._executor(step.tool, interpolated)
            r.status = StepStatus.COMPLETED
        except Exception as exc:
            r.status = StepStatus.FAILED
            r.error = str(exc)
        finally:
            r.completed_at = datetime.now(timezone.utc)

    def _execute(self, wf: DAGWorkflow, waves: list[list[WorkflowStep]]) -> None:
        wf.status = WorkflowStatus.RUNNING
        results = wf.results

        for wave in waves:
            runnable = [s for s in wave if self._can_run(s, results)]
            for s in wave:
                if not self._can_run(s, results):
                    results[s.id] = StepResult(step_id=s.id, status=StepStatus.SKIPPED)

            if not runnable:
                continue

            if len(runnable) == 1:
                self._run_step(runnable[0], results)
            else:
                with ThreadPoolExecutor(max_workers=len(runnable)) as pool:
                    list(pool.map(lambda s: self._run_step(s, results), runnable))

        failed = any(r.status == StepStatus.FAILED for r in results.values())
        wf.status = WorkflowStatus.FAILED if failed else WorkflowStatus.COMPLETED
        wf.completed_at = datetime.now(timezone.utc)


def _noop_executor(tool: str, input_data: dict) -> dict:
    return {"tool": tool, "input": input_data}
```

- [ ] **Step 5: Run all workflow tests**

```bash
cd sandbox-worker
uv run pytest tests/unit/test_workflow.py -v 2>&1 | tail -20
```
Expected: all tests pass except `TestWorkflowRoutes` (route not built yet).

- [ ] **Step 6: Commit**

```bash
cd sandbox-worker
git add src/service/workflow.py pyproject.toml
git commit -m "feat: add WorkflowService with DAG execution and interpolation"
```

---

## Task 4: Workflow Route — POST /workflows, GET /workflows/{id}

**Files:**
- Create: `sandbox-worker/src/api/routes/workflow.py`
- Modify: `sandbox-worker/src/api/app.py`

- [ ] **Step 1: Create api/routes/workflow.py**

```python
"""Workflow routes — POST /workflows, GET /workflows/{id}."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from service.workflow import CyclicDependencyError, WorkflowValidationError


class WorkflowRequest(BaseModel):
    name: str
    steps: list[dict]


def register(app_state: dict) -> APIRouter:
    router = APIRouter()

    @router.post("/workflows", status_code=202)
    def create_workflow(body: WorkflowRequest) -> JSONResponse:
        svc = app_state.get("workflow_svc")
        if svc is None:
            raise HTTPException(status_code=503, detail="Workflow service not configured")
        try:
            result = svc.create(body.name, body.steps)
        except (WorkflowValidationError, CyclicDependencyError) as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return JSONResponse(content=result, status_code=202)

    @router.get("/workflows/{workflow_id}")
    def get_workflow(workflow_id: str) -> JSONResponse:
        svc = app_state.get("workflow_svc")
        if svc is None:
            raise HTTPException(status_code=503, detail="Workflow service not configured")
        try:
            result = svc.get(workflow_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return JSONResponse(content=result)

    return router
```

- [ ] **Step 2: Run route tests to verify they pass**

```bash
cd sandbox-worker
uv run pytest tests/unit/test_workflow.py::TestWorkflowRoutes -v 2>&1 | tail -15
```
Expected: all 6 route tests pass.

- [ ] **Step 3: Wire workflow router into api/app.py**

In `sandbox-worker/src/api/app.py`, add workflow to the imports:

```python
from api.routes import artifact, execute, health, hibernation, package, session, streaming, workflow, workspace
```

In `create_app()`, add after the existing `app.include_router(workspace.register(_state))` line:

```python
    app.include_router(workflow.register(_state))
```

In the `lifespan` function, after `_state["streaming_svc"] = ...`:

```python
    # Workflow
    from service.workflow import WorkflowService
    from service.execution import ExecutionService as _ExecSvc
    def _workflow_executor(tool: str, input_data: dict) -> dict:
        return _state["exec_svc"].execute({"tool": tool, "input": input_data})
    _state["workflow_svc"] = WorkflowService(
        executor=_workflow_executor,
        max_steps=cfg.workflow.max_steps,
    )
```

- [ ] **Step 4: Run full workflow test suite**

```bash
cd sandbox-worker
uv run pytest tests/unit/test_workflow.py -v 2>&1 | tail -10
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
cd sandbox-worker
git add src/api/routes/workflow.py src/api/app.py
git commit -m "feat: add workflow route POST /workflows and GET /workflows/{id}"
```

---

## Task 5: Continuous Snapshot — Models

**Files:**
- Modify: `sandbox-worker/src/models/session.py`
- Modify: `sandbox-worker/src/service/session.py`

- [ ] **Step 1: Add SnapshotMode to models/session.py**

Replace `sandbox-worker/src/models/session.py` entirely.
Also adds `FIRECRACKER = "firecracker"` to `Tier` — fixes an existing bug where `execution.py` references `Tier.FIRECRACKER` which was missing from the enum.

```python
"""Session and tier models."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Tier(str, Enum):
    WASM = "wasm"
    MICROVM = "microvm"
    GUI = "gui"
    FIRECRACKER = "firecracker"


class SnapshotMode(str, Enum):
    CLEAN = "clean"
    CONTINUOUS = "continuous"


@dataclass
class Session:
    id: str
    runtime: Tier
    status: str
    created_at: datetime
    updated_at: datetime
    snapshot_mode: SnapshotMode = SnapshotMode.CLEAN


@dataclass
class CreateSessionRequest:
    runtime: str = "wasm"
    snapshot_mode: str = "clean"


@dataclass
class CreateSessionResponse:
    session_id: str
    runtime: Tier
    status: str
    snapshot_mode: SnapshotMode = SnapshotMode.CLEAN


@dataclass
class HealthResponse:
    status: str
    version: str
    services: dict[str, str]
```

- [ ] **Step 2: Update SessionService to accept and store snapshot_mode**

Replace `sandbox-worker/src/service/session.py` entirely:

```python
"""SessionService — in-memory session tracking (local per worker node)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

import structlog

from adapters.tracing import get_tracer
from models.session import SnapshotMode, Tier

log = structlog.get_logger()


@dataclass
class Session:
    id: str
    runtime: Tier
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: str = "active"
    snapshot_mode: SnapshotMode = SnapshotMode.CLEAN


class SessionService:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    async def create(self, runtime_str: str = "firecracker", snapshot_mode_str: str = "clean") -> dict:
        tracer = get_tracer()
        with tracer.start_span("service.session.create", {"runtime": runtime_str}) as span:
            try:
                tier = Tier(runtime_str)
            except ValueError:
                tier = Tier.FIRECRACKER

            try:
                mode = SnapshotMode(snapshot_mode_str)
            except ValueError:
                mode = SnapshotMode.CLEAN

            sess = Session(id=str(uuid.uuid4()), runtime=tier, snapshot_mode=mode)
            self._sessions[sess.id] = sess
            span.set_attribute("session_id", sess.id)
            log.info("session created", session_id=sess.id, runtime=tier.value,
                     snapshot_mode=mode.value)

            return {
                "session_id": sess.id,
                "runtime": tier.value,
                "status": sess.status,
                "snapshot_mode": mode.value,
            }

    def get(self, session_id: str) -> Session:
        sess = self._sessions.get(session_id)
        if sess is None:
            raise KeyError(f"Session {session_id!r} not found")
        return sess

    def close(self, session_id: str) -> None:
        sess = self._sessions.pop(session_id, None)
        if sess:
            log.info("session closed", session_id=session_id)
```

- [ ] **Step 3: Run existing tests to ensure nothing broke**

```bash
cd sandbox-worker
uv run pytest tests/unit/ -x -q 2>&1 | tail -10
```
Expected: all previously passing tests still pass.

- [ ] **Step 4: Commit**

```bash
cd sandbox-worker
git add src/models/session.py src/service/session.py
git commit -m "feat: add SnapshotMode to session models and SessionService"
```

---

## Task 6: Continuous Snapshot — SnapshotDownloader Extensions

**Files:**
- Modify: `sandbox-worker/src/orchestrator/snapshot.py`
- Create: `sandbox-worker/tests/unit/test_continuous_snapshot.py`

- [ ] **Step 1: Write failing tests for session snapshot methods**

Create `sandbox-worker/tests/unit/test_continuous_snapshot.py`:

```python
"""Tests for continuous snapshot: load/save/delete session snapshots."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from orchestrator.snapshot import SnapshotDownloader, SnapshotPaths


def _make_downloader(tmp_path, storage=None):
    if storage is None:
        storage = MagicMock()
        storage.exists.return_value = False
    return SnapshotDownloader(storage=storage, cache_dir=str(tmp_path))


def _write_snapshot_blobs(directory: str) -> None:
    """Write fake vmstate.bin, memory.bin, meta.json to directory."""
    Path(directory).mkdir(parents=True, exist_ok=True)
    Path(directory, "vmstate.bin").write_bytes(b"vmstate")
    Path(directory, "memory.bin").write_bytes(b"memory")
    Path(directory, "meta.json").write_text(json.dumps({
        "name": "test", "version": "1", "kernel": "vmlinux",
        "rootfs": "rootfs.ext4", "vcpus": 1, "mem_mib": 128,
    }))


class TestLoadSessionSnapshot:
    def test_returns_none_when_not_in_cache_or_storage(self, tmp_path):
        dl = _make_downloader(tmp_path)
        result = dl.load_session_snapshot("sess-123")
        assert result is None

    def test_returns_paths_from_local_cache(self, tmp_path):
        local_dir = tmp_path / "sessions" / "sess-abc"
        _write_snapshot_blobs(str(local_dir))

        dl = _make_downloader(tmp_path)
        result = dl.load_session_snapshot("sess-abc")

        assert result is not None
        assert result.state_file.endswith("vmstate.bin")
        assert result.mem_file.endswith("memory.bin")

    def test_downloads_from_storage_when_not_cached(self, tmp_path):
        storage = MagicMock()
        storage.exists.return_value = True
        storage.download.side_effect = lambda key: (
            b"vmstate" if "vmstate" in key else
            b"memory" if "memory" in key else
            json.dumps({"name": "s", "version": "1", "kernel": "k",
                        "rootfs": "r", "vcpus": 1, "mem_mib": 128}).encode()
        )

        dl = SnapshotDownloader(storage=storage, cache_dir=str(tmp_path))
        result = dl.load_session_snapshot("sess-dl")

        assert result is not None
        assert storage.download.call_count == 3  # vmstate, memory, meta

    def test_returns_none_if_storage_missing_any_blob(self, tmp_path):
        storage = MagicMock()
        storage.exists.side_effect = lambda key: "vmstate" not in key  # vmstate missing

        dl = SnapshotDownloader(storage=storage, cache_dir=str(tmp_path))
        result = dl.load_session_snapshot("sess-missing")
        assert result is None


class TestSaveSessionSnapshot:
    def test_uploads_all_blobs(self, tmp_path):
        local_dir = tmp_path / "src"
        _write_snapshot_blobs(str(local_dir))

        storage = MagicMock()
        storage.upload.return_value = "sessions/sess-save/vmstate.bin"

        dl = SnapshotDownloader(storage=storage, cache_dir=str(tmp_path))
        dl.save_session_snapshot("sess-save", str(local_dir))

        assert storage.upload.call_count == 3
        uploaded_keys = [c.args[0] for c in storage.upload.call_args_list]
        assert "sessions/sess-save/vmstate.bin" in uploaded_keys
        assert "sessions/sess-save/memory.bin" in uploaded_keys
        assert "sessions/sess-save/meta.json" in uploaded_keys


class TestDeleteSessionSnapshot:
    def test_deletes_all_blobs_from_storage(self, tmp_path):
        storage = MagicMock()
        dl = SnapshotDownloader(storage=storage, cache_dir=str(tmp_path))
        dl.delete_session_snapshot("sess-del")

        assert storage.delete.call_count == 3
        deleted_keys = [c.args[0] for c in storage.delete.call_args_list]
        assert "sessions/sess-del/vmstate.bin" in deleted_keys
        assert "sessions/sess-del/memory.bin" in deleted_keys
        assert "sessions/sess-del/meta.json" in deleted_keys

    def test_clears_local_cache(self, tmp_path):
        local_dir = tmp_path / "sessions" / "sess-clear"
        _write_snapshot_blobs(str(local_dir))
        assert local_dir.exists()

        storage = MagicMock()
        dl = SnapshotDownloader(storage=storage, cache_dir=str(tmp_path))
        dl.delete_session_snapshot("sess-clear")

        assert not local_dir.exists()

    def test_delete_ignores_storage_errors(self, tmp_path):
        storage = MagicMock()
        storage.delete.side_effect = Exception("not found")
        dl = SnapshotDownloader(storage=storage, cache_dir=str(tmp_path))
        # Should not raise
        dl.delete_session_snapshot("sess-err")
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd sandbox-worker
uv run pytest tests/unit/test_continuous_snapshot.py -v 2>&1 | tail -15
```
Expected: `AttributeError: 'SnapshotDownloader' object has no attribute 'load_session_snapshot'`

- [ ] **Step 3: Add session snapshot methods to SnapshotDownloader**

In `sandbox-worker/src/orchestrator/snapshot.py`, add these three methods inside the `SnapshotDownloader` class, after the existing `upload()` method:

```python
    def load_session_snapshot(self, session_id: str) -> SnapshotPaths | None:
        """Return cached or downloaded per-session snapshot, None if not found."""
        local_dir = os.path.join(self._cache_dir, "sessions", session_id)
        paths = SnapshotPaths(
            state_file=os.path.join(local_dir, "vmstate.bin"),
            mem_file=os.path.join(local_dir, "memory.bin"),
            meta_file=os.path.join(local_dir, "meta.json"),
        )

        if self._all_exist(paths.state_file, paths.mem_file, paths.meta_file):
            log.debug("session snapshot cache hit", session_id=session_id)
            return self._load_meta(paths)

        prefix = f"sessions/{session_id}"
        try:
            for blob in self._BLOBS:
                if not self._storage.exists(f"{prefix}/{blob}"):
                    log.debug("session snapshot not in storage", session_id=session_id)
                    return None

            Path(local_dir).mkdir(parents=True, exist_ok=True)
            for blob in self._BLOBS:
                data = self._storage.download(f"{prefix}/{blob}")
                Path(os.path.join(local_dir, blob)).write_bytes(data)

            log.info("session snapshot downloaded", session_id=session_id)
            return self._load_meta(paths)
        except Exception as exc:
            log.warning("failed to load session snapshot", session_id=session_id, err=str(exc))
            return None

    def save_session_snapshot(self, session_id: str, local_dir: str) -> None:
        """Upload snapshot blobs from local_dir under sessions/{session_id}/ prefix."""
        prefix = f"sessions/{session_id}"
        for blob in self._BLOBS:
            data = Path(os.path.join(local_dir, blob)).read_bytes()
            self._storage.upload(f"{prefix}/{blob}", data)
            log.info("session snapshot blob uploaded", key=f"{prefix}/{blob}", size=len(data))

    def delete_session_snapshot(self, session_id: str) -> None:
        """Delete blobs under sessions/{session_id}/ from storage and local cache."""
        prefix = f"sessions/{session_id}"
        for blob in self._BLOBS:
            try:
                self._storage.delete(f"{prefix}/{blob}")
                log.info("session snapshot blob deleted", key=f"{prefix}/{blob}")
            except Exception as exc:
                log.warning("delete blob failed", key=f"{prefix}/{blob}", err=str(exc))

        local_dir = os.path.join(self._cache_dir, "sessions", session_id)
        if os.path.exists(local_dir):
            import shutil
            shutil.rmtree(local_dir)
```

- [ ] **Step 4: Run snapshot tests**

```bash
cd sandbox-worker
uv run pytest tests/unit/test_continuous_snapshot.py -v 2>&1 | tail -20
```
Expected: all 9 tests pass.

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
cd sandbox-worker
uv run pytest tests/unit/ -q 2>&1 | tail -5
```
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
cd sandbox-worker
git add src/orchestrator/snapshot.py tests/unit/test_continuous_snapshot.py
git commit -m "feat: add per-session snapshot load/save/delete to SnapshotDownloader"
```

---

## Task 7: Continuous Snapshot — ExecutionService Integration

**Files:**
- Modify: `sandbox-worker/src/service/execution.py`
- Modify: `sandbox-worker/tests/unit/test_continuous_snapshot.py`

- [ ] **Step 1: Add execution integration tests to test_continuous_snapshot.py**

Append to `sandbox-worker/tests/unit/test_continuous_snapshot.py`:

```python
# ── ExecutionService snapshot integration ─────────────────────────────────────

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from adapters.tracing import init_tracer, reset_tracer
from models.job import RuntimeResult
from service.execution import ExecutionService


@pytest.fixture(autouse=True)
def tracer_setup():
    reset_tracer()
    init_tracer(driver="noop")
    yield
    reset_tracer()


def _make_exec_svc(exit_code=0, downloader=None):
    """ExecutionService with a mock VM pool."""
    mock_result = RuntimeResult(stdout="ok", stderr="", exit_code=exit_code)
    mock_vm = MagicMock()
    mock_vm.run.return_value = mock_result

    mock_mgr = MagicMock()
    mock_mgr.acquire.return_value = mock_vm
    mock_mgr._cache_dir = "/tmp/fake-cache"

    return ExecutionService(lifecycle_mgr=mock_mgr, downloader=downloader)


class TestExecutionSnapshotIntegration:
    def test_clean_mode_does_not_save_snapshot(self):
        downloader = MagicMock()
        svc = _make_exec_svc(exit_code=0, downloader=downloader)
        svc.execute({"tool": "python_run", "input": {}, "snapshot_mode": "clean", "session_id": "s1"})
        downloader.save_session_snapshot.assert_not_called()

    def test_continuous_mode_saves_snapshot_on_success(self):
        downloader = MagicMock()
        downloader.load_session_snapshot.return_value = None
        svc = _make_exec_svc(exit_code=0, downloader=downloader)
        svc.execute({"tool": "python_run", "input": {}, "snapshot_mode": "continuous", "session_id": "s2"})
        downloader.save_session_snapshot.assert_called_once_with("s2", "/tmp/fake-cache")

    def test_continuous_mode_does_not_save_on_failure(self):
        downloader = MagicMock()
        downloader.load_session_snapshot.return_value = None
        svc = _make_exec_svc(exit_code=1, downloader=downloader)
        svc.execute({"tool": "python_run", "input": {}, "snapshot_mode": "continuous", "session_id": "s3"})
        downloader.save_session_snapshot.assert_not_called()

    def test_continuous_mode_calls_load_before_run(self):
        downloader = MagicMock()
        downloader.load_session_snapshot.return_value = None
        svc = _make_exec_svc(exit_code=0, downloader=downloader)
        svc.execute({"tool": "python_run", "input": {}, "snapshot_mode": "continuous", "session_id": "s4"})
        downloader.load_session_snapshot.assert_called_once_with("s4")

    def test_no_downloader_does_not_crash_in_continuous_mode(self):
        svc = _make_exec_svc(exit_code=0, downloader=None)
        result = svc.execute({"tool": "python_run", "input": {}, "snapshot_mode": "continuous", "session_id": "s5"})
        assert result["status"] == "completed"
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
cd sandbox-worker
uv run pytest tests/unit/test_continuous_snapshot.py::TestExecutionSnapshotIntegration -v 2>&1 | tail -10
```
Expected: `TypeError` — `ExecutionService.__init__()` doesn't accept `downloader` yet.

- [ ] **Step 3: Update ExecutionService**

Replace `sandbox-worker/src/service/execution.py` entirely:

```python
"""ExecutionService — direct VM execution (no queue)."""
from __future__ import annotations

import time
import uuid

import structlog

from adapters.tracing import get_tracer
from models.job import Job, JobStatus, RuntimeResult
from models.session import Tier

log = structlog.get_logger()


class ExecutionService:
    def __init__(self, lifecycle_mgr, downloader=None) -> None:
        # lifecycle_mgr: VMLifecycleManager
        # downloader: SnapshotDownloader | None
        self._mgr = lifecycle_mgr
        self._downloader = downloader

    def execute(self, body: dict) -> dict:
        tracer = get_tracer()
        tool = body.get("tool", "")
        if not tool:
            raise ValueError("Tool name is required")

        input_data = body.get("input") or {}
        session_id = body.get("session_id") or str(uuid.uuid4())
        snapshot_mode = body.get("snapshot_mode", "clean")

        with tracer.start_span("service.execution.run", {"tool": tool, "session_id": session_id}) as span:
            job = Job(
                id=str(uuid.uuid4()),
                session_id=session_id,
                tool=tool,
                tier=Tier.FIRECRACKER,
                input=input_data,
                status=JobStatus.PENDING,
            )

            # Continuous snapshot: load existing session snapshot before run
            if snapshot_mode == "continuous" and self._downloader:
                self._downloader.load_session_snapshot(session_id)

            start = time.monotonic()
            vm = self._mgr.acquire(timeout=30.0)
            try:
                result: RuntimeResult = vm.run(job)
            finally:
                self._mgr.release(vm)

            duration_ms = int((time.monotonic() - start) * 1000)
            status = JobStatus.COMPLETED if result.exit_code == 0 else JobStatus.FAILED

            # Continuous snapshot: save on success
            if snapshot_mode == "continuous" and self._downloader and result.exit_code == 0:
                try:
                    self._downloader.save_session_snapshot(session_id, self._mgr._cache_dir)
                except Exception as exc:
                    log.warning("snapshot save failed", session_id=session_id, err=str(exc))

            span.set_attribute("job_id", job.id)
            span.set_attribute("status", status.value)
            span.set_attribute("duration_ms", duration_ms)
            log.info("execution done", job_id=job.id, status=status.value, duration_ms=duration_ms)

            return {
                "job_id": job.id,
                "session_id": session_id,
                "status": status.value,
                "output": result.stdout,
                "error_message": result.stderr,
                "duration_ms": duration_ms,
            }
```

- [ ] **Step 4: Run integration tests**

```bash
cd sandbox-worker
uv run pytest tests/unit/test_continuous_snapshot.py -v 2>&1 | tail -20
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
cd sandbox-worker
git add src/service/execution.py tests/unit/test_continuous_snapshot.py
git commit -m "feat: integrate continuous snapshot into ExecutionService"
```

---

## Task 8: Continuous Snapshot — Routes and App Wiring

**Files:**
- Modify: `sandbox-worker/src/api/routes/session.py`
- Create: `sandbox-worker/src/api/routes/snapshot.py`
- Modify: `sandbox-worker/src/api/app.py`

- [ ] **Step 1: Update session route to accept snapshot_mode**

Replace `sandbox-worker/src/api/routes/session.py` entirely:

```python
"""Session routes."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse


def register(app_state: dict) -> APIRouter:
    router = APIRouter()

    @router.post("/sessions")
    async def create_session(body: dict = None) -> JSONResponse:
        body = body or {}
        runtime_str = body.get("runtime", "wasm")
        snapshot_mode_str = body.get("snapshot_mode", "clean")
        result = await app_state["session_svc"].create(runtime_str, snapshot_mode_str)
        return JSONResponse(content=result)

    return router
```

- [ ] **Step 2: Create snapshot route**

Create `sandbox-worker/src/api/routes/snapshot.py`:

```python
"""Snapshot routes — DELETE /snapshots/{session_id}."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response


def register(app_state: dict) -> APIRouter:
    router = APIRouter()

    @router.delete("/snapshots/{session_id}", status_code=204)
    def delete_snapshot(session_id: str) -> Response:
        downloader = app_state.get("snapshot_downloader")
        if downloader is None:
            raise HTTPException(status_code=503, detail="Snapshot service not configured")
        downloader.delete_session_snapshot(session_id)
        return Response(status_code=204)

    return router
```

- [ ] **Step 3: Wire snapshot router and inject downloader into app.py**

In `sandbox-worker/src/api/app.py`:

Update the routes import line:

```python
from api.routes import artifact, execute, health, hibernation, package, session, snapshot, streaming, workflow, workspace
```

In `lifespan()`, after `lifecycle_mgr.start()`, expose the downloader via `_state`:

```python
    lifecycle_mgr.start()
    _state["lifecycle_mgr"] = lifecycle_mgr
    _state["snapshot_downloader"] = lifecycle_mgr._downloader
```

Update the `ExecutionService` instantiation to inject the downloader:

```python
    _state["exec_svc"] = ExecutionService(lifecycle_mgr, downloader=lifecycle_mgr._downloader)
```

In `create_app()`, add after `app.include_router(workspace.register(_state))`:

```python
    app.include_router(snapshot.register(_state))
```

- [ ] **Step 4: Run route tests**

```bash
cd sandbox-worker
uv run pytest tests/unit/test_continuous_snapshot.py tests/unit/test_workflow.py -v 2>&1 | tail -15
```
Expected: all tests pass.

- [ ] **Step 5: Run the full test suite**

```bash
cd sandbox-worker
uv run pytest tests/unit/ -q 2>&1 | tail -5
```
Expected: all tests pass, no regressions.

- [ ] **Step 6: Commit**

```bash
cd sandbox-worker
git add src/api/routes/session.py src/api/routes/snapshot.py src/api/app.py
git commit -m "feat: add snapshot route and wire continuous snapshot into app"
```

---

## Task 9: Final Verification and phase-3.md Update

- [ ] **Step 1: Run full test suite one final time**

```bash
cd sandbox-worker
uv run pytest tests/unit/ -v --tb=short 2>&1 | tail -20
```
Expected: all tests pass.

- [ ] **Step 2: Update phase-3.md to mark completed items**

In `docs/archive/todo/phase-3.md`, mark the following as `[x]`:

- `[x] Pisah LibreOffice ke Dockerfile.office-agent tersendiri`
- `[x] Fix Dockerfile.gui-agent — hapus Playwright download Chromium, pakai apt chromium`
- DAG Execution section — all items (implemented as Workflow in service/workflow.py + api/routes/workflow.py)
- Continuous Snapshot section — all items

- [ ] **Step 3: Final commit**

```bash
git add docs/archive/todo/phase-3.md
git commit -m "docs: mark phase 3 features complete in todo"
```
