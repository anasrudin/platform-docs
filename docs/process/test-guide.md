# Test Guide

| Field | Value |
|---|---|
| Status | Active |
| Audience | Contributors |
| Scope | How to run tests, what is tested, and coverage targets |
| Last updated | April 8, 2026 |

## Overview

The test suite is in `sandbox-platform/tests/unit/`. All tests run with `pytest` and do not require live infrastructure — Redis, PostgreSQL, MinIO, Consul, and Nomad are mocked.

Total: **235 tests**, all passing.

---

## Running tests

### All tests

```bash
cd sandbox-platform
pytest
```

### With coverage report

```bash
pytest --cov=sandbox_platform --cov-report=term-missing
```

### Single module

```bash
pytest tests/unit/test_consul_client.py -v
```

### By keyword

```bash
pytest -k "scaler" -v
pytest -k "mtls" -v
```

---

## Test layout

```
tests/
  unit/
    test_types.py
    test_queue_client.py
    test_session_manager.py
    test_router.py
    test_artifact_store.py
    test_firecracker_runtime.py
    test_wasm_runtime.py
    test_gui_runtime.py
    test_consul_client.py
    test_health_server.py
    test_session_consul_store.py
    test_scaler_metrics.py
    test_scaler_policy.py
    test_scaler_nomad.py
    test_scaler.py
    test_package_store.py
    test_mtls.py
    test_platform_api.py
```

---

## Coverage targets

New code added in Phases 1–5 must meet ≥ 95% coverage. Current state:

| Module | Coverage |
|---|---|
| `consul/client.py` | 100% |
| `consul/health_server.py` | 100% |
| `packages/store.py` | 100% |
| `scaler/metrics.py` | 96% |
| `scaler/nomad.py` | 100% |
| `scaler/policy.py` | 100% |
| `scaler/scaler.py` | 100% |
| `security/mtls.py` | 100% |
| `session/consul_store.py` | 100% |

---

## Test categories by phase

### Core (91 tests — pre-advanced features)

| File | What it covers |
|---|---|
| `test_types.py` | Domain model construction and field defaults |
| `test_queue_client.py` | Redis push/pop with mock Redis |
| `test_session_manager.py` | PostgreSQL session and job lifecycle with mock connection |
| `test_router.py` | Tool-to-tier routing rules |
| `test_artifact_store.py` | Upload/download/URL generation, local fallback |
| `test_firecracker_runtime.py` | Pool, VM, snapshot; sim mode and real-mode interface |
| `test_wasm_runtime.py` | Module cache, execution; sim mode |
| `test_gui_runtime.py` | Stub execution path |
| `test_platform_api.py` | HTTP endpoint integration (health, sessions, execute, artifacts) |

### Phase 1 — Consul (+22 tests)

| File | What it covers |
|---|---|
| `test_consul_client.py` | Register, deregister, KV put/get/delete; HTTP 500 error handling |
| `test_health_server.py` | Health endpoint returns correct JSON; pool_size_fn is called |

### Phase 2 — Session KV (+11 tests)

| File | What it covers |
|---|---|
| `test_session_consul_store.py` | put/get/delete round-trip; 404 returns None; base64 decode |

### Phase 3 — Auto-scaling (+41 tests)

| File | What it covers |
|---|---|
| `test_scaler_metrics.py` | NodeMetrics collection; aggregate computes averages |
| `test_scaler_policy.py` | Scale-up, scale-down, hold decisions; cooldown enforcement; min/max limits |
| `test_scaler_nomad.py` | job_count, scale_job HTTP calls; error propagation |
| `test_scaler.py` | Tick loop: collect → evaluate → act; stop() exits cleanly; errors in tick are swallowed |

### Phase 4 — Packages (+35 tests)

| File | What it covers |
|---|---|
| `test_package_store.py` | Sim install, cache hit, list, delete; pip real mode with subprocess mock; MinIO store mock |

### Phase 5 — mTLS (+22 tests)

| File | What it covers |
|---|---|
| `test_mtls.py` | create_mtls_context parameters; CertManager.reload() calls load_cert_chain; MTLSMiddleware returns 403 when enabled and no cert; passes through when disabled; passes through when cert present |

---

## Writing new tests

### Mocking conventions

Use `unittest.mock.AsyncMock` for async functions and `unittest.mock.MagicMock` for sync. External HTTP calls use `httpx.MockTransport` or patch at the `httpx.AsyncClient` level.

```python
from unittest.mock import AsyncMock, patch

async def test_consul_register():
    mock_client = AsyncMock()
    mock_client.put.return_value = AsyncMock(status_code=200)
    with patch("sandbox_platform.consul.client.httpx.AsyncClient") as mc:
        mc.return_value.__aenter__.return_value = mock_client
        client = ConsulClient(host="localhost", port=8500)
        await client.register_service(...)
        mock_client.put.assert_called_once()
```

### Test isolation rules

- No tests write to real disk, real Redis, real PostgreSQL, or real Consul.
- Filesystem tests use `tmp_path` (pytest fixture).
- Tests that mock subprocess must restore the real subprocess after the test.
- Do not use `time.sleep` in tests — mock `asyncio.sleep` or `time.monotonic` instead.

---

## Continuous integration expectations

All PRs must pass:

```
pytest                                          # 235/235
pytest --cov=sandbox_platform --cov-fail-under=95
```

The coverage gate applies only to `sandbox_platform/`. Entry points under `platform_cmd/` are covered by `test_platform_api.py` integration tests and are not subject to the 95% gate independently.
