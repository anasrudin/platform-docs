# Phase 3 Features Design

**Date:** 2026-04-10  
**Scope:** Docker fixes, DAG Execution, Continuous Snapshot  
**Status:** Approved

---

## 1. Docker Fixes

### gui-agent
Remove LibreOffice and `playwright install chromium` from `docker/gui-agent/Dockerfile`.  
Playwright uses `chromium-browser` from apt — no separate download needed.  
Estimated size reduction: ~540MB → ~300MB.

### office-agent (new)
New `docker/office-agent/Dockerfile` extending `sandbox-base`:
- Installs: `libreoffice`, `libreoffice-calc`, `libreoffice-writer`, `libreoffice-impress`, fonts
- Nomad driver: `docker`
- Estimated size: ~550MB

### Nomad job spec
Add `office-agent` group to `services/controller/nomad/jobs/sandbox-worker.nomad` mirroring `gui-agent` but using `sandbox-office-agent` image.

---

## 2. DAG Execution

### Goal
Single endpoint accepts a full DAG; worker executes all steps in the same VM context.  
Reduces overhead from `5 × (network hop + VM acquire)` to `1 × VM acquire`.

### Models — `models/dag.py`

```python
DAGStep(id: str, tool: str, input: dict, deps: list[str])
DAGRequest(steps: list[DAGStep], session_id: str = "")
StepStatus(PENDING, RUNNING, COMPLETED, FAILED)
StepResult(step_id: str, status: StepStatus, output: str, error: str, duration_ms: int)
DAGResult(dag_id: str, results: dict[str, StepResult], total_ms: int)
```

### Service — `service/dag.py`

`DAGService(lifecycle_mgr)`:

- `_toposort(steps) → list[list[DAGStep]]`  
  Returns execution waves. Each wave is a list of steps that can run in parallel (all deps satisfied by previous waves). Raises `ValueError` on cycle or missing dep.

- `run(request: DAGRequest) → DAGResult`  
  Iterates waves. Each wave runs via `ThreadPoolExecutor(max_workers=len(wave))`.  
  Before each step executes, template substitution is applied to all string values in `input`:  
  - `$step_id.output` → replaced with `results[step_id].output`  
  - `$step_id.error` → replaced with `results[step_id].error`

### Execution service — `service/execution.py`

Add `execute_dag(body: dict) → dict`:
- Parses body into `DAGRequest`
- Instantiates `DAGService(self._mgr)`
- Calls `dag_svc.run(request)`
- Returns `DAGResult` as dict

### Route — `api/routes/dag.py`

```
POST /execute/dag
  Body: { steps: [...], session_id: "" }
  Response: DAGResult as JSON
  Errors: 400 (ValueError), 404 (session not found)
```

### App wiring — `api/app.py`

```python
from api.routes import dag
app.include_router(dag.register(_state))
```

### Tests — `tests/unit/test_dag.py`

| Test | What it verifies |
|------|-----------------|
| `test_sequential_dag` | 3 steps with linear deps run in order |
| `test_parallel_dag` | 2 independent branches run concurrently (both complete) |
| `test_template_substitution` | `$step_a.output` in step_b.input is replaced before execution |
| `test_cycle_detection` | Circular deps raise `ValueError` |
| `test_missing_dep` | Reference to unknown step_id raises `ValueError` |

---

## 3. Continuous Snapshot

### Goal
Sessions with `snapshot_mode=continuous` persist VM state to storage after execution.  
Next execution for the same session resumes from saved snapshot instead of base.  
Key: `sessions/{session_id}/` (per-session, not per-user).

### Models — `models/session.py`

Add:
```python
class SnapshotMode(str, Enum):
    CLEAN = "clean"
    CONTINUOUS = "continuous"
```

`Session` and `CreateSessionRequest` gain field:
```python
snapshot_mode: SnapshotMode = SnapshotMode.CLEAN
```

### Session service — `service/session.py`

`SessionService.create()` reads `snapshot_mode` from request body and stores it on the `Session` object.

### Orchestrator — `orchestrator/snapshot.py`

Extend `SnapshotDownloader` with three new methods:

```python
def load_session_snapshot(self, session_id: str) -> SnapshotPaths | None:
    """Download session snapshot if it exists. Returns None if not found (use base)."""

def save_session_snapshot(self, session_id: str, local_dir: str) -> None:
    """Upload snapshot blobs from local_dir under sessions/{session_id}/ prefix."""

def delete_session_snapshot(self, session_id: str) -> None:
    """Delete all blobs under sessions/{session_id}/ prefix."""
```

Storage key prefix: `sessions/{session_id}/vmstate.bin`, etc.

### Execution service — `service/execution.py`

`ExecutionService.__init__` gains `downloader: SnapshotDownloader | None = None`.

`execute()` gains optional `snapshot_mode` and `session_id` from body:
- If `snapshot_mode == "continuous"` and `downloader` is set:
  - Before run: call `load_session_snapshot(session_id)` — if found, pass paths to VM
  - After run (exit_code == 0 only): call `save_session_snapshot(session_id, local_dir)`

### Session route — `api/routes/session.py`

`POST /sessions` body accepts `snapshot_mode` field, forwarded to `session_svc.create()`.

### Snapshot route — `api/routes/snapshot.py` (new)

```
DELETE /snapshots/{session_id}
  → downloader.delete_session_snapshot(session_id)
  → 204 No Content
```

### App wiring — `api/app.py`

- Inject `downloader` (the `SnapshotDownloader` instance from lifecycle_mgr) into `ExecutionService`
- Register snapshot router: `app.include_router(snapshot.register(_state))`

### Tests — `tests/unit/test_continuous_snapshot.py`

| Test | What it verifies |
|------|-----------------|
| `test_clean_mode_no_save` | `save_session_snapshot` not called in clean mode |
| `test_continuous_mode_saves` | `save_session_snapshot` called after successful run |
| `test_continuous_mode_loads_existing` | `load_session_snapshot` called before run when snapshot exists |
| `test_force_reset` | `DELETE /snapshots/{id}` calls `delete_session_snapshot` |
| `test_failed_execution_no_save` | exit_code ≠ 0 → snapshot not saved |

---

## File Map

| File | Action |
|------|--------|
| `docker/gui-agent/Dockerfile` | Edit — remove LibreOffice + playwright install |
| `docker/office-agent/Dockerfile` | New |
| `services/controller/nomad/jobs/sandbox-worker.nomad` | Edit — add office-agent group |
| `models/dag.py` | New |
| `models/session.py` | Edit — add SnapshotMode, snapshot_mode field |
| `service/dag.py` | New |
| `service/execution.py` | Edit — add execute_dag(), snapshot integration |
| `api/routes/dag.py` | New |
| `api/routes/snapshot.py` | New |
| `api/routes/session.py` | Edit — accept snapshot_mode |
| `api/app.py` | Edit — register dag + snapshot routers, inject downloader |
| `orchestrator/snapshot.py` | Edit — add 3 session snapshot methods |
| `tests/unit/test_dag.py` | New |
| `tests/unit/test_continuous_snapshot.py` | New |
