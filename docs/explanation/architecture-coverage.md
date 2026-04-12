# Arsitektur, Infrastruktur & Coverage Platform

> Diukur langsung dari live GCP deployment (`34.143.174.106`) dan codebase per 2026-04-13.

---

## 1. Gambaran Besar Arsitektur

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CLIENT / AI AGENT                               │
│                    curl / HTTP / SDK / Demo                             │
└─────────────────────┬───────────────────────────────────────────────────┘
                      │ HTTP
          ┌───────────▼───────────┐
          │      GCP VM (n2-std-4)│
          │     34.143.174.106    │
          │                       │
          │  ┌─────────────────┐  │
          │  │   Nomad Agent   │  │  ← job scheduler (raw_exec driver)
          │  │                 │  │
          │  │  ┌───────────┐  │  │
          │  │  │platform-  │  │  │  :8080 — full API
          │  │  │api        │  │  │
          │  │  └─────┬─────┘  │  │
          │  │        │        │  │
          │  │  ┌─────▼─────┐  │  │
          │  │  │interpreter│  │  │  :8090 — minimal POST /run
          │  │  └─────┬─────┘  │  │
          │  └────────┼────────┘  │
          │           │           │
          │  ┌────────▼────────┐  │
          │  │ VMLifecycle     │  │  ← Python pool manager (in-process)
          │  │ Manager         │  │
          │  │  pool_size=1    │  │
          │  └────────┬────────┘  │
          │           │ spawn/kill│
          │  ┌────────▼────────┐  │
          │  │ Firecracker     │  │  ← real microVM (KVM)
          │  │ microVM         │  │    boots from MinIO snapshot
          │  │ (Python 3.11)   │  │    ~200ms cold start
          │  └─────────────────┘  │
          │                       │
          │  ┌─────────────────┐  │
          │  │ MinIO :9000     │  │  ← stores FC snapshots
          │  │ (Docker)        │  │    platform-snapshots/python-v1/
          │  └─────────────────┘  │
          │                       │
          │  ┌─────────────────┐  │
          │  │ Jaeger :16686   │  │  ← traces semua request
          │  │ (Docker)        │  │
          │  └─────────────────┘  │
          │                       │
          │  ┌─────────────────┐  │
          │  │ Consul :8500    │  │  ← running, tapi service
          │  │ (Docker)        │  │    registration OFF
          │  └─────────────────┘  │
          └───────────────────────┘
```

---

## 2. Layer Infrastruktur

```
┌──────────────────────────────────────────────────────────────┐
│  LAYER 1 — ORCHESTRATION                                      │
│  Nomad (single-node)                      STATUS: ✅ RUNNING  │
│  • platform-api job     → running                            │
│  • interpreter job      → running                            │
│  • driver: raw_exec (runs as root, KVM accessible)           │
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│  LAYER 2 — APPLICATION                                        │
│  Python (FastAPI + uvicorn)               STATUS: ✅ RUNNING  │
│  • platform-api  :8080   — full feature API                  │
│  • interpreter   :8090   — minimal /run endpoint             │
│  • FC_MODE=real, POOL_SIZE=1, CONSUL_ENABLED=false           │
│  • OTEL_ENABLED=true → traces ke Jaeger                      │
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│  LAYER 3 — RUNTIME                                            │
│  Firecracker microVM (KVM)               STATUS: ✅ RUNNING  │
│  • Binary: /usr/bin/firecracker v1.8.0                       │
│  • Snapshot: MinIO → python-v1 (vmstate+memory+rootfs)       │
│  • Kernel: 5.10.245+                                         │
│  • Guest OS: Python 3.11.15 (GCC 12.2.0)                    │
│  • Cold start: ~200ms per execution                          │
│  • vSock transport: host ↔ guest agent                       │
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│  LAYER 4 — DATA & STORAGE                                     │
│  MinIO (S3-compatible)                   STATUS: ✅ RUNNING  │
│  • Bucket: platform-snapshots/python-v1/{vmstate,memory,     │
│            rootfs}.bin + meta.json                           │
│  Consul                                  STATUS: ✅ UP (idle) │
│  • Service registration: OFF (CONSUL_ENABLED=false)          │
│  • No workers registered                                     │
│  PostgreSQL                              STATUS: ❌ NOT USED  │
│  Redis                                   STATUS: ❌ NOT USED  │
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│  LAYER 5 — OBSERVABILITY                                      │
│  Jaeger (OTLP)                           STATUS: ✅ RUNNING  │
│  • Service: sandbox-platform                                 │
│  • Spans: setiap execute, workflow step, session             │
│  Grafana + Loki                          STATUS: ❌ NOT DEPLOYED│
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Source Code — Struktur Modul

```
sandbox-worker/src/
├── api/
│   ├── app.py               ← FastAPI lifespan + router wiring
│   ├── interpreter.py       ← standalone minimal service
│   ├── middleware/
│   │   ├── auth.py          ← TenantAuth (off by default)
│   │   ├── request_id.py    ← X-Request-ID header
│   │   └── tracing.py       ← OTEL span per request
│   └── routes/              ← 10 route modules
│       ├── execute.py       ─┐
│       ├── session.py        │
│       ├── workflow.py       ├── core features
│       ├── package.py        │
│       ├── health.py        ─┘
│       ├── workspace.py     ─┐
│       ├── artifact.py       ├── extended features
│       ├── streaming.py      │
│       ├── hibernation.py    │
│       └── snapshot.py      ─┘
│
├── service/                 ← business logic (10 services)
├── models/                  ← Pydantic/dataclass models (8 files)
├── orchestrator/            ← lifecycle, hibernation, snapshot, workspace
├── runtime/
│   ├── firecracker.py       ← VMPool, SnapshotStore, FC process mgmt
│   ├── wasm.py              ← WASM runtime (stub)
│   └── gui.py               ← GUI/Chromium runtime (stub)
├── adapters/
│   ├── storage/             ← local, s3_compat, snapshot_blob
│   ├── registry/            ← consul, health_server, noop
│   └── tracing/             ← otel, noop
├── agents/                  ← fc_agent, wasm_agent, gui_agent
├── communication/           ← vsock, stream, guest
└── config/
    └── settings.py          ← all env vars via pydantic settings
```

---

## 4. Coverage API Endpoint — Live Test

| Endpoint | Method | Status | Catatan |
|---|---|:---:|---|
| `/health` | GET | ✅ | Returns mode, version, pool status |
| `/execute` | POST | ✅ | `python_run`, `bash_run` via real FC VM |
| `/packages/install` | POST | ✅ | Install → cache → `"installed"` / `"cached"` |
| `/packages` | GET | ✅ | List semua package yang ter-cache |
| `/packages/{name}` | DELETE | ⚠️ | Belum di-test live |
| `/sessions` | POST | ✅ | Create session (ID-only, no state persistence) |
| `/sessions/{id}/hibernate` | POST | ❌ | `HIBERNATE_ENABLED=false` |
| `/sessions/{id}/restore` | POST | ❌ | `HIBERNATE_ENABLED=false` |
| `/sessions/{id}/execute/stream` | GET | ❌ | Error: `host must be a str or bytes` |
| `/workflows` | POST | ✅ | DAG execution, synchronous, wave-parallel |
| `/workflows/{id}` | GET | ✅ | Full step results dengan output |
| `/workspaces` | POST | ✅ | Create workspace dengan ID |
| `/workspaces/{id}` | GET | ✅ | Workspace detail + files list |
| `/workspaces/{id}/files` | GET | ✅ | File listing |
| `/workspaces/{id}` | DELETE | ⚠️ | Belum di-test live |
| `/artifacts` | POST | ❌ | Butuh multipart form, bukan JSON |
| `/artifacts/{id}/{name}` | GET | ⚠️ | Belum di-test live |
| `/snapshots/{session_id}` | DELETE | ⚠️ | Belum di-test live |
| `POST /run` (interpreter) | POST | ✅ | Python + bash, standalone |
| `GET /health` (interpreter) | GET | ✅ | Pool status |

**Ringkasan Endpoint:**

```
Total endpoints:  19
✅ Confirmed working:   11   (58%)
❌ Broken/disabled:      3   (16%)
⚠️  Not tested live:     5   (26%)
```

---

## 5. Coverage Fitur — Persentase Nyata

```
Feature                        Coverage  Status
─────────────────────────────────────────────────────────────
Python Execution (FC)          ████████████████████  100%  ✅
Bash Execution (FC)            ████████████████████  100%  ✅
Workflow DAG (3-step)          ████████████████████  100%  ✅
Package Cache                  ████████████████████  100%  ✅
Workspace CRUD                 ████████████████████  100%  ✅
Session ID Grouping            ████████████████████  100%  ✅
Health Check                   ████████████████████  100%  ✅
Distributed Tracing (Jaeger)   ████████████████████  100%  ✅
Nomad Orchestration            ████████████████████  100%  ✅
MinIO Snapshot Storage         ████████████████████  100%  ✅

Consul Service Registration    ████░░░░░░░░░░░░░░░░   20%  ⚠️  (running, reg OFF)
Artifact Upload/Download       ████████░░░░░░░░░░░░   40%  ⚠️  (route ada, schema salah)
Streaming Execute              ████░░░░░░░░░░░░░░░░   20%  ❌  (bug vsock host)

Session State Persistence      ░░░░░░░░░░░░░░░░░░░░    0%  ❌  (roadmap)
Hibernate / Restore            ░░░░░░░░░░░░░░░░░░░░    0%  ❌  (flag off)
WASM Runtime                   ░░░░░░░░░░░░░░░░░░░░    0%  ❌  (stub only)
GUI / Chromium Runtime         ░░░░░░░░░░░░░░░░░░░░    0%  ❌  (stub only)
mTLS Auth                      ░░░░░░░░░░░░░░░░░░░░    0%  ❌  (MTLS_ENABLED=false)
Auto-scaler                    ░░░░░░░░░░░░░░░░░░░░    0%  ❌  (SCALER_ENABLED=false)
PostgreSQL / Redis              ░░░░░░░░░░░░░░░░░░░░    0%  ❌  (not deployed)
HAProxy Load Balancer          ░░░░░░░░░░░░░░░░░░░░    0%  ❌  (single node)
Grafana / Loki                 ░░░░░░░░░░░░░░░░░░░░    0%  ❌  (not deployed)
```

---

## 6. Unit Test Coverage

### Status per Test File

| Test File | Jumlah Test | Status | Modul |
|---|:---:|:---:|---|
| test_execution_service.py | ~20 | ✅ | service/execution |
| test_workflow.py | ~25 | ✅ | service/workflow |
| test_packages.py | ~20 | ✅ | service/package |
| test_hibernation.py | ~20 | ✅ | service/hibernation |
| test_workspace.py | ~20 | ✅ | orchestrator/workspace |
| test_streaming.py | ~15 | ✅ | service/streaming |
| test_fc_runtime.py | ~20 | ✅ | runtime/firecracker |
| test_wasm_runtime.py | ~15 | ✅ | runtime/wasm |
| test_gui_runtime.py | ~10 | ✅ | runtime/gui |
| test_artifacts.py | ~15 | ✅ | service/artifact |
| test_lifecycle_spans.py | ~10 | ✅ | orchestrator/lifecycle |
| test_snapshot_spans.py | ~10 | ✅ | orchestrator/snapshot |
| test_continuous_snapshot.py | ~10 | ✅ | adapters/storage |
| test_agent_health.py | ~10 | ✅ | agents/ |
| test_guest.py | ~10 | ✅ | communication/guest |
| test_tap_mac.py | ~10 | ✅ | network |
| test_types.py | ~15 | ✅ | models/ |
| test_consul_client.py | ~15 | ✅ | adapters/registry |
| test_request_id_middleware.py | ~10 | ✅ | api/middleware |
| test_tenant.py | 7 | ❌ | api/routes (7 failing) |
| test_tracing.py | ~15 | ❌ | adapters/tracing (2 failing) |
| test_mtls.py | — | ❌ | `sandbox_platform` (stale import) |
| test_scaler.py | — | ❌ | `sandbox_platform` (stale import) |
| test_scaler_metrics.py | — | ❌ | `sandbox_platform` (stale import) |
| test_scaler_nomad.py | — | ❌ | `sandbox_platform` (stale import) |
| test_scaler_policy.py | — | ❌ | `sandbox_platform` (stale import) |
| test_session_store.py | — | ❌ | `sandbox_platform` (stale import) |
| test_audit.py | — | ❌ | `adapters.audit` (missing) |
| test_queue.py | — | ❌ | `adapters.queue` (missing) |
| test_ratelimit.py | — | ❌ | `adapters.cache` (missing) |
| test_router.py | — | ❌ | `service.router` (missing) |

```
Total test files:           31
✅ Running (pass):          19 files → 284 tests pass
❌ Failing tests:            2 files → 24 tests fail
❌ Stale import (skip):     10 files → tidak bisa jalan

Tests yang jalan:     308 total  (284 pass / 24 fail)
Pass rate (running):  92%
File coverage:        61%  (19/31 bisa jalan)
```

### Code Coverage (dari coverage.json — snapshot lama)

> Catatan: coverage.json mengukur paket `sandbox_platform` lama (sudah dihapus).  
> Coverage untuk `sandbox-worker/src/` yang baru belum di-generate.

| Modul Lama | Coverage |
|---|:---:|
| consul/client.py | 100% |
| consul/health_server.py | 100% |
| packages/store.py | 100% |
| router/router.py | 100% |
| scaler/nomad.py | 100% |
| scaler/policy.py | 100% |
| scaler/scaler.py | 100% |
| security/mtls.py | 100% |
| types.py | 100% |
| queue/client.py | 95% |
| scaler/metrics.py | 96% |
| wasm/runtime.py | 87% |
| artifacts/store.py | 80% |
| firecracker/runtime.py | 76% |
| wasm/module_store.py | 74% |
| firecracker/guest.py | 70% |
| firecracker/snapshot.py | 55% |
| firecracker/pool.py | 31% |
| firecracker/vm.py | 31% |
| session/manager.py | 0% |
| **Total** | **78%** |

---

## 7. Tabel Perbandingan: Designed vs Deployed vs Working

| Komponen | Dirancang | Di-deploy | Berjalan | % |
|---|:---:|:---:|:---:|:---:|
| Firecracker runtime (real KVM) | ✅ | ✅ | ✅ | 100% |
| Python execution | ✅ | ✅ | ✅ | 100% |
| Bash execution | ✅ | ✅ | ✅ | 100% |
| Workflow DAG | ✅ | ✅ | ✅ | 100% |
| Package cache (MinIO) | ✅ | ✅ | ✅ | 100% |
| Workspace management | ✅ | ✅ | ✅ | 100% |
| Session grouping (ID only) | ✅ | ✅ | ✅ | 100% |
| OTEL tracing → Jaeger | ✅ | ✅ | ✅ | 100% |
| Nomad orchestration | ✅ | ✅ | ✅ | 100% |
| MinIO snapshot store | ✅ | ✅ | ✅ | 100% |
| Consul service discovery | ✅ | ✅ | ⚠️ | 20% |
| Artifact store | ✅ | ✅ | ⚠️ | 40% |
| Streaming execution | ✅ | ✅ | ❌ | 20% |
| Session state persistence | ✅ | ❌ | ❌ | 0% |
| Hibernate/Restore | ✅ | ❌ | ❌ | 0% |
| WASM runtime | ✅ | ❌ | ❌ | 0% |
| GUI/Chromium runtime | ✅ | ❌ | ❌ | 0% |
| mTLS authentication | ✅ | ❌ | ❌ | 0% |
| Auto-scaler | ✅ | ❌ | ❌ | 0% |
| HAProxy load balancer | ✅ | ❌ | ❌ | 0% |
| PostgreSQL | ✅ | ❌ | ❌ | 0% |
| Redis | ✅ | ❌ | ❌ | 0% |
| Multi-node Nomad cluster | ✅ | ❌ | ❌ | 0% |
| Grafana/Loki monitoring | ✅ | ❌ | ❌ | 0% |

```
Total komponen dirancang:    24
✅ Fully working:            10   (42%)
⚠️  Partial:                  3   (12%)
❌ Not deployed/broken:      11   (46%)
```

---

## 8. Ringkasan Keseluruhan

```
┌─────────────────────────────────────────────────────────────────┐
│                    PLATFORM COVERAGE SUMMARY                    │
├─────────────────────────────────┬───────────────────────────────┤
│  METRIC                         │  VALUE                        │
├─────────────────────────────────┼───────────────────────────────┤
│  Komponen fully working         │  10 / 24  (42%)               │
│  API endpoint working           │  11 / 19  (58%)               │
│  Unit test pass rate            │  284 / 308  (92%)             │
│  Test files runnable            │  21 / 31  (68%)               │
│  Code coverage (old pkg)        │  78%  (1076/1386 lines)       │
│  Live FC execution latency      │  ~200ms per request           │
│  Nomad jobs running             │  2 / 2  (100%)                │
├─────────────────────────────────┼───────────────────────────────┤
│  CORE DEMO PATH                 │  100% WORKING ✅              │
│  Execute Python/Bash in real FC │                               │
│  Package install + cache        │                               │
│  Multi-step workflow DAG        │                               │
│  Session ID grouping            │                               │
│  Traces di Jaeger               │                               │
├─────────────────────────────────┼───────────────────────────────┤
│  BUGS YANG ADA                  │                               │
│  Streaming (vsock host bug)     │  1 bug                        │
│  Artifact upload (schema wrong) │  1 bug                        │
│  24 unit test failures          │  tenant + tracing routes      │
│  10 stale test files            │  butuh di-port ke src/        │
├─────────────────────────────────┼───────────────────────────────┤
│  ROADMAP (belum diimplementasi) │                               │
│  Session state persistence      │  HIBERNATE_ENABLED=true       │
│  WASM runtime                   │  implementation needed        │
│  GUI/Chromium runtime           │  implementation needed        │
│  Multi-node cluster             │  infra config exists          │
│  HAProxy + load balancing       │  config exists, not deployed  │
│  Auto-scaler                    │  code exists, flag off        │
└─────────────────────────────────┴───────────────────────────────┘
```

---

## 9. Data Flow — Satu Request Execute

```
Client
  │
  │  POST /execute {"tool":"python_run","input":{"code":"..."}}
  ▼
FastAPI (api/app.py)
  │  TracingMiddleware → create OTEL span
  │  RequestIDMiddleware → X-Request-ID
  ▼
ExecutionService.execute()   (service/execution.py)
  │  1. create Job object
  │  2. acquire VM from pool (timeout 30s)
  ▼
VMLifecycleManager.acquire() (orchestrator/lifecycle.py)
  │  wait on threading.Queue for available VM
  ▼
FirecrackerVM.execute()      (runtime/firecracker.py)
  │  send tool + input over vSock
  │  wait for guest agent response
  ▼
Guest Agent                  (inside FC microVM)
  │  run Python/Bash subprocess
  │  return {"stdout","stderr","exit_code"}
  │
  ◄──── vSock response ─────
  │
VMLifecycleManager.release() → VM kembali ke pool, di-restore ke snapshot
  │
  ▼
ExecutionService
  │  parse result, create response dict
  │  emit OTEL span attributes
  ▼
HTTP Response
  │  {"job_id","session_id","status","output","duration_ms"}
  ▼
Client
```

---

*Dokumen ini dibuat berdasarkan live testing ke GCP VM `34.143.174.106` dan analisis source code per 2026-04-13.*
