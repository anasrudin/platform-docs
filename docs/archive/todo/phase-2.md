# Sandbox Platform — Phase 2 Spec

**Platform:** `sandbox-platform` (Python 3.12+)  
**Prerequisites:** Phase 1 complete (8 fitur) + Layer Restructure (ADR: `docs/architecture/layer-restructure.md`)  
**Status:** ✅ Complete — 406/406 tests pass (2026-04-09)

---

## Overview

Phase 2 menambahkan kemampuan yang mengubah platform dari execution engine menjadi **persistent, observable, multi-tenant execution environment**.

### Features in Scope

| # | Feature | Tier | Priority | Depends On | Status |
|---|---------|------|----------|------------|--------|
| 1 | Session Hibernation | T1 | High | layer restructure | ✅ Done |
| 2 | Streaming Output (WebSocket) | T1 | High | layer restructure | ✅ Done |
| 3 | Workspace Persistence | T1 | Medium | adapters/storage | ✅ Done |
| 4 | Execution DAG | T1 | Medium | service/execution | ✅ Done |
| 5 | OpenTelemetry Tracing | T2 | High | layer restructure | ✅ Done |
| 6 | Multi-tenancy | T2 | High | adapters/db | ✅ Done |
| 7 | Rate Limiting + Quotas | T2 | High | adapters/cache | ✅ Done |
| 8 | Audit Log | T2 | Medium | adapters/audit | ✅ Done |

---

## Rollout Plan

| Phase | Features | Gate | Status |
|-------|----------|------|--------|
| 2.1 | OpenTelemetry (#5) | Harus ada dulu sebelum debug fitur lain | ✅ Done |
| 2.2 | Session Hibernation (#1) + Streaming (#2) | Core UX improvements | ✅ Done |
| 2.3 | Workspace Persistence (#3) + Audit Log (#8) | Storage features together | ✅ Done |
| 2.4 | Multi-tenancy (#6) + Rate Limiting (#7) | Production readiness | ✅ Done |
| 2.5 | Execution DAG (#4) | Depends on semua layer stabil | ✅ Done |

---

## Feature Specifications

---

### 1. Session Hibernation

#### Current State
- Idle session di-destroy setelah timeout
- State VM (installed packages, in-memory data) hilang permanen
- Setiap session baru harus boot dari base snapshot dari awal

#### Target Behavior
Idle session di-"hibernate": VM di-pause, state di-snapshot ke storage, VM di-destroy.
Saat user kembali, session di-restore dari hibernate snapshot dalam < 10 detik.
User tidak tahu VM pernah di-destroy.

#### Integration Points
- `service/hibernation.py` — idle detection, trigger hibernate/restore
- `orchestrator/hibernation.py` — Firecracker pause → snapshot → destroy / restore → resume
- `api/routes/session.py` — tambah endpoint hibernate dan restore
- `adapters/storage/` — simpan hibernate snapshot (prefix `hibernate/`)
- Background task di `api/app.py` lifespan — scan idle sessions tiap 60s

#### API

```
POST /sessions/{id}/hibernate
     → 202 Accepted
     body: {"hibernated_at": "...", "snapshot_key": "hibernate/sess-abc123"}

POST /sessions/{id}/restore
     → 200 OK
     body: {"session_id": "...", "restored_from": "hibernate/sess-abc123", "restore_ms": 8400}

GET  /sessions/{id}
     → tambah field: "state": "active" | "hibernating" | "restoring"
```

#### Firecracker Sequence

```
Hibernate:
  PUT /vm/state {"state": "Paused"}
  PUT /vm/snapshot/create {"snapshot_path": "/tmp/vmstate.bin", "mem_file_path": "/tmp/mem.bin", "snapshot_type": "Full"}
  upload /tmp/vmstate.bin + /tmp/mem.bin → storage hibernate/{session_id}/
  kill firecracker process

Restore:
  download hibernate/{session_id}/ → /tmp/
  start new firecracker process
  PUT /snapshot/load {"snapshot_path": "...", "mem_file_path": "...", "enable_diff_snapshots": false}
  PUT /vm/state {"state": "Resumed"}
```

#### Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `HIBERNATE_IDLE_TIMEOUT` | `300` | Detik sebelum session di-hibernate |
| `HIBERNATE_SCAN_INTERVAL` | `60` | Interval scan idle sessions (detik) |
| `HIBERNATE_ENABLED` | `false` | Feature flag |
| `HIBERNATE_TTL` | `86400` | Detik sebelum hibernate snapshot dihapus (24 jam) |

#### Acceptance Criteria
- [x] Session yang idle > 5 menit otomatis di-hibernate
- [ ] Restore dari hibernate < 10 detik (p95) — needs real infra
- [ ] Package yang sudah terinstall sebelum hibernate tetap ada setelah restore — needs real FC
- [ ] In-memory Python variables tetap ada setelah restore — needs real FC
- [x] Hibernate snapshot dihapus otomatis setelah TTL
- [x] `GET /sessions/{id}` menunjukkan state `hibernating` selama proses
- [x] Coverage ≥ 95%

---

### 2. Streaming Output (WebSocket)

#### Current State
- Eksekusi synchronous: client tunggu sampai selesai
- Tidak ada visibility progress untuk script yang berjalan lama
- Timeout 30s memotong script yang butuh lebih lama

#### Target Behavior
Client bisa subscribe ke output stream session via WebSocket.
Setiap `print()` atau stdout di dalam VM langsung dikirim ke client sebagai chunk.
Connection tetap open sampai eksekusi selesai atau client disconnect.

#### Integration Points
- `api/routes/execute.py` — tambah WebSocket endpoint
- `service/streaming.py` — koordinasi antara VM output dan WebSocket clients
- `communication/stream.py` — async generator yang baca stdout dari vsock/ssh
- `communication/vsock.py` — tambah `stream_execute()` method

#### API

```
WebSocket: ws://host/sessions/{id}/execute/stream

# Client kirim:
{"code": "for i in range(100):\n    print(i)\n    time.sleep(0.1)", "timeout": 60}

# Server kirim (stream):
{"type": "stdout",   "data": "0\n",    "ts": "2026-04-09T10:00:00.001Z"}
{"type": "stdout",   "data": "1\n",    "ts": "2026-04-09T10:00:00.102Z"}
...
{"type": "stderr",   "data": "...",    "ts": "..."}
{"type": "done",     "exit_code": 0,   "duration_ms": 10243}

# Error:
{"type": "error",    "message": "session not found"}
```

#### SSE fallback (HTTP/1.1 environments)

```
GET /sessions/{id}/execute/stream
Content-Type: text/event-stream

data: {"type": "stdout", "data": "0\n"}
data: {"type": "stdout", "data": "1\n"}
data: {"type": "done", "exit_code": 0}
```

#### Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `STREAM_MAX_TIMEOUT` | `300` | Max durasi stream (detik) |
| `STREAM_BUFFER_SIZE` | `4096` | Bytes per chunk dari vsock |

#### Acceptance Criteria
- [ ] Client menerima stdout chunks dalam < 100ms setelah VM print() — needs real infra
- [x] WebSocket connection survive selama 5 menit tanpa output (keepalive ping)
- [x] Client disconnect tidak crash VM atau agent
- [x] Multiple clients bisa subscribe ke session yang sama (broadcast)
- [x] `{"type": "done"}` selalu dikirim sebagai pesan terakhir
- [x] Coverage ≥ 95%

---

### 3. Workspace Persistence

#### Current State
- File yang dibuat di dalam VM hilang saat session selesai
- User harus re-upload file setiap session baru
- Tidak ada shared filesystem antar session

#### Target Behavior
Setiap session punya `/workspace` directory yang persists di object storage.
Mount ke VM sebelum boot via `virtio-fs` atau sync via agen.
File tetap ada saat session selesai, bisa diakses di session berikutnya.

#### Integration Points
- `service/workspace.py` — create/get/delete workspace, list files
- `orchestrator/workspace.py` — mount workspace ke VM sebelum boot
- `api/routes/workspaces.py` — workspace management endpoints
- `adapters/storage/` — workspace files di `workspaces/{workspace_id}/`
- `models/workspace.py` — Workspace, MountConfig

#### API

```
POST /workspaces
     body: {"name": "my-project"}
     → {"workspace_id": "ws-abc123", "created_at": "..."}

GET  /workspaces/{id}
     → {"workspace_id": "...", "name": "...", "size_bytes": 1024000, "files": [...]}

DELETE /workspaces/{id}
     → 204 No Content

# Attach workspace ke session
POST /sessions
     body: {"workspace_id": "ws-abc123", "snapshot": "python-v1"}
     → session boots dengan /workspace sudah mounted

# List files
GET /workspaces/{id}/files
    → [{"path": "/workspace/analysis.py", "size": 1024, "modified": "..."}]
```

#### Mount Strategy

```
Option A: virtio-fs (preferred, Linux only)
  → mount object storage sebagai filesystem via virtiofsd
  → reads/writes langsung ke storage, no sync needed

Option B: sync-on-boot / sync-on-destroy (fallback, cross-platform)
  → download workspace dari storage ke /workspace sebelum VM start
  → upload /workspace ke storage setelah VM destroy
  → cocok untuk dev/macOS
```

#### Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `WORKSPACE_DRIVER` | `sync` | `virtiofs` atau `sync` |
| `WORKSPACE_MAX_SIZE_MB` | `1024` | Max ukuran workspace per user |
| `WORKSPACE_BUCKET` | `platform-workspaces` | Storage bucket |

#### Acceptance Criteria
- [x] File yang dibuat di `/workspace` dalam session 1 ada di session 2
- [x] `DELETE /workspaces/{id}` menghapus semua file dari storage
- [x] Workspace tidak bocor antar user/tenant
- [ ] Sync selesai dalam < 5 detik untuk workspace < 100MB — needs real infra
- [x] Coverage ≥ 95%

---

### 4. Execution DAG

#### Current State
- Setiap tool dieksekusi secara independen
- Output satu tool tidak bisa langsung jadi input tool berikutnya
- AI agent harus orchestrate multi-step workflow di sisi client

#### Target Behavior
Client definisikan workflow sebagai DAG (Directed Acyclic Graph) steps.
Platform eksekusi step secara berurutan (atau parallel jika tidak ada dependency).
Output step N otomatis tersedia sebagai `$steps[N].output` di step N+1.

#### Integration Points
- `service/workflow.py` — DAG parser, dependency resolver, step executor
- `api/routes/workflows.py` — POST /workflows, GET /workflows/{id}
- `models/workflow.py` — DAGWorkflow, WorkflowStep, StepResult

#### API

```python
# Request
POST /workflows
{
  "name": "summarize-webpage",
  "steps": [
    {
      "id": "scrape",
      "tool": "web_scrape",
      "input": {"url": "https://example.com"}
    },
    {
      "id": "parse",
      "tool": "html_parse",
      "input": {"html": "$steps.scrape.output.html"},
      "depends_on": ["scrape"]
    },
    {
      "id": "summarize",
      "tool": "python_run",
      "input": {
        "code": "import json\ndata = json.loads('$steps.parse.output')\nprint(data['text'][:500])"
      },
      "depends_on": ["parse"]
    }
  ],
  "timeout": 120
}

# Response (async, polling)
{
  "workflow_id": "wf-abc123",
  "status": "running",           # pending | running | completed | failed
  "steps": {
    "scrape":    {"status": "completed", "duration_ms": 2100, "output": {...}},
    "parse":     {"status": "completed", "duration_ms": 50,   "output": {...}},
    "summarize": {"status": "running",   "duration_ms": null,  "output": null}
  }
}

GET /workflows/{id}          # polling
GET /workflows/{id}/stream   # WebSocket live updates
```

#### Execution Model

```
DAG resolution:
  1. Parse steps → build dependency graph
  2. Find steps dengan 0 dependencies → eksekusi parallel
  3. Saat step selesai → resolve $steps.{id}.output di downstream steps
  4. Eksekusi downstream jika semua dependencies done

Output interpolation:
  "$steps.scrape.output.html" → diganti dengan actual value sebelum step dieksekusi
```

#### Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `WORKFLOW_MAX_STEPS` | `20` | Max steps per workflow |
| `WORKFLOW_MAX_TIMEOUT` | `600` | Max total timeout (detik) |
| `WORKFLOW_MAX_PARALLEL` | `5` | Max steps eksekusi parallel |

#### Acceptance Criteria
- [x] Steps dengan dependencies dieksekusi setelah dependency selesai
- [x] Steps tanpa dependencies bisa jalan parallel
- [x] `$steps.{id}.output` interpolation bekerja untuk string dan nested object
- [x] Jika satu step gagal, downstream steps tidak dieksekusi
- [x] `GET /workflows/{id}` menunjukkan status real-time per step
- [x] Coverage ≥ 95%

---

### 5. OpenTelemetry Tracing

#### Current State
- Hanya structured logging (structlog) — tidak ada distributed tracing
- Tidak bisa trace satu request end-to-end dari HTTP → VM execution
- Bottleneck sulit diidentifikasi di production

#### Target Behavior
Setiap request menghasilkan trace tree:
`HTTP request → service → orchestrator → runtime → VM execute`
Trace dikirim ke backend (Jaeger/Tempo/Honeycomb) via OTLP.

#### Integration Points
- `api/middleware/tracing.py` — root span per request
- `adapters/tracing/otel.py` — OTLP exporter
- `adapters/tracing/noop.py` — dev mode tanpa collector
- `service/*.py` — `with tracer.span("service.execution.route"):` per operation
- `orchestrator/*.py` — span untuk pool acquire, VM boot
- `communication/*.py` — span untuk VM execute

#### Instrumentation Points

| Layer | Span Name | Attributes |
|-------|-----------|------------|
| `api/routes` | `http.request` | method, path, status |
| `service/execution` | `service.execution.route` | tool, tier |
| `service/execution` | `service.execution.queue_push` | queue, job_id |
| `orchestrator/pool` | `orchestrator.pool.acquire` | pool_size, wait_ms |
| `orchestrator/lifecycle` | `orchestrator.vm.boot` | vm_id, snapshot |
| `communication/vsock` | `communication.vsock.execute` | tool, input_size |
| `adapters/storage` | `storage.download` | bucket, key, size_bytes |

#### Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `OTEL_DRIVER` | `noop` | `otel` atau `noop` |
| `OTEL_ENDPOINT` | `http://localhost:4317` | OTLP gRPC endpoint |
| `OTEL_SERVICE_NAME` | `sandbox-platform` | Service name di trace |
| `OTEL_SAMPLE_RATE` | `1.0` | Sampling rate (0.0–1.0) |

#### Acceptance Criteria
- [x] Satu HTTP request menghasilkan satu trace dengan span hierarchy yang benar
- [x] `OTEL_DRIVER=noop` tidak ada overhead (default dev mode)
- [ ] Trace ID propagated ke VM log via structured log field `trace_id` — not yet implemented
- [ ] P99 latency tidak berubah > 1ms karena tracing overhead — needs real infra
- [x] Coverage ≥ 95%

---

### 6. Multi-tenancy

#### Current State
- Semua sessions, snapshots, workspaces shared antar semua users
- Tidak ada isolasi resource
- Satu user bisa melihat/akses data user lain

#### Target Behavior
Setiap request terautentikasi membawa `tenant_id`.
Sessions, snapshots, workspaces, dan artifacts terisolasi per tenant.
Resource quotas enforced per tenant (lihat Feature #7).

#### Integration Points
- `api/middleware/auth.py` — ekstrak tenant dari JWT/API key header
- `models/tenant.py` — Tenant, TenantQuota
- `service/tenant.py` — tenant CRUD
- `adapters/db/postgres.py` — semua query tambah `WHERE tenant_id = ?`
- `adapters/storage/` — semua storage keys prefix dengan `{tenant_id}/`
- `adapters/cache/` — semua cache keys prefix dengan `{tenant_id}:`

#### API

```
# Auth header (semua endpoint)
Authorization: Bearer <jwt>
# atau
X-API-Key: <api_key>

# Tenant info di JWT claims:
{"sub": "user-123", "tenant_id": "org-abc", "roles": ["admin"]}

# Admin: manage tenants
POST   /admin/tenants              ← create tenant
GET    /admin/tenants/{id}         ← get tenant info + quota usage
DELETE /admin/tenants/{id}         ← delete tenant + semua data
PATCH  /admin/tenants/{id}/quota   ← update quota
```

#### Database Schema Addition

```sql
ALTER TABLE sessions   ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE jobs       ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default';
CREATE TABLE tenants (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_sessions_tenant ON sessions(tenant_id);
CREATE INDEX idx_jobs_tenant     ON jobs(tenant_id);
```

#### Acceptance Criteria
- [x] Request tanpa valid auth token → 401
- [x] Tenant A tidak bisa akses sessions milik Tenant B → 404
- [ ] Storage objects terisolasi: `{tenant_id}/artifacts/`, `{tenant_id}/snapshots/` — DB schema ready, storage prefix not yet enforced
- [x] `TENANT_ISOLATION=false` → mode single-tenant (backward compatible)
- [x] Coverage ≥ 95%

---

### 7. Rate Limiting + Execution Quotas

#### Current State
- Tidak ada rate limiting — satu client bisa monopoli semua resources
- Tidak ada batas eksekusi per client
- Tidak ada visibility penggunaan resource per client

#### Target Behavior
Per tenant/API key:
- Max N concurrent sessions
- Max M requests per menit
- Max CPU seconds per jam
- Max storage bytes

Jika quota terlampaui → 429 Too Many Requests dengan `Retry-After` header.

#### Integration Points
- `api/middleware/ratelimit.py` — request rate limiter (Redis sliding window)
- `service/quota.py` — enforce execution quotas, track usage
- `adapters/cache/redis_cache.py` — counter storage untuk rate limit
- `models/tenant.py` — tambah `TenantQuota` dataclass

#### Rate Limit Algorithm

```
Sliding window (Redis):
  key: ratelimit:{tenant_id}:{window_start_minute}
  value: request count
  TTL: 2 menit

Jika count > limit → 429
Header: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
```

#### Default Quotas

| Resource | Free Tier | Pro Tier |
|----------|-----------|----------|
| Concurrent sessions | 2 | 20 |
| Requests per minute | 30 | 300 |
| CPU seconds per hour | 600 | 6000 |
| Storage per tenant | 1 GB | 100 GB |
| Max execution timeout | 30s | 300s |

#### Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `RATELIMIT_ENABLED` | `false` | Feature flag |
| `RATELIMIT_BACKEND` | `redis` | `redis` atau `memory` |
| `DEFAULT_MAX_RPM` | `30` | Default requests per menit |
| `DEFAULT_MAX_SESSIONS` | `2` | Default concurrent sessions |

#### Acceptance Criteria
- [x] 31st request dalam satu menit → 429 dengan `Retry-After`
- [x] Counter reset setelah window berlalu
- [x] `RATELIMIT_ENABLED=false` → tidak ada overhead (default)
- [ ] Rate limit counter persist across API restarts (Redis backend) — needs real Redis
- [x] Coverage ≥ 95%

---

### 8. Audit Log

#### Current State
- Structured logs (structlog) untuk debugging — tidak queryable
- Tidak ada record "siapa menjalankan apa kapan"
- Tidak bisa audit compliance

#### Target Behavior
Setiap eksekusi, install package, snapshot, dan session lifecycle dicatat sebagai audit event.
Events bisa di-query per tenant, per user, per time range.
Audit log immutable — tidak bisa di-edit atau dihapus.

#### Integration Points
- `service/audit.py` — fire-and-forget audit event recording
- `adapters/audit/postgres.py` — queryable audit di DB
- `adapters/audit/s3.py` — append-only compliance archive di object storage
- `adapters/audit/stdout.py` — dev mode, log ke stdout
- `api/routes/audit.py` — query audit events (admin only)

#### Audit Event Schema

```python
@dataclass
class AuditEvent:
    id:          str           # uuid
    tenant_id:   str
    user_id:     str
    action:      str           # session.create | execute | package.install | snapshot.create
    resource_id: str           # session_id / snapshot_id / etc
    ip_address:  str
    result:      str           # success | failure
    metadata:    dict          # tool, code_hash, package_name, etc
    created_at:  datetime
```

#### Events yang Dicatat

| Action | Trigger |
|--------|---------|
| `session.create` | POST /sessions |
| `session.destroy` | DELETE /sessions/{id} |
| `session.hibernate` | POST /sessions/{id}/hibernate |
| `execute` | POST /sessions/{id}/execute |
| `package.install` | POST /sessions/{id}/packages/install |
| `snapshot.create` | POST /snapshots |
| `workspace.create` | POST /workspaces |
| `auth.fail` | Invalid token/key |

#### API (admin only)

```
GET /admin/audit?tenant_id=&action=&from=&to=&limit=
    → paginated list of AuditEvent
```

#### Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `AUDIT_DRIVER` | `stdout` | `postgres`, `s3`, `stdout` |
| `AUDIT_ENABLED` | `true` | Feature flag |
| `AUDIT_S3_BUCKET` | `platform-audit` | Compliance bucket |
| `AUDIT_RETENTION_DAYS` | `365` | Retention period |

#### Acceptance Criteria
- [x] Setiap execute menghasilkan tepat 1 audit event
- [x] Audit events tidak pernah di-delete (immutable)
- [x] `GET /admin/audit` filter by tenant, action, time range bekerja
- [x] Audit recording failure tidak mempengaruhi request (fire-and-forget)
- [x] Coverage ≥ 95%

---

## Architecture Diagram (Phase 2)

```
                    ┌─────────────────────────────────────┐
                    │           sandbox-platform           │
                    │                                     │
  Client ──────────▶│  api/middleware:                    │
  (JWT/API Key)     │  auth → ratelimit → tracing → mtls  │
                    │              ↓                      │
                    │  api/routes/                        │
                    │  session | execute | workflow        │
                    │  workspace | snapshot | audit        │
                    │              ↓                      │
                    │  service/                           │
                    │  session | execution | workflow      │
                    │  hibernation | workspace | audit     │
                    │              ↓                      │
                    │  orchestrator/                      │
                    │  core | pool | lifecycle             │
                    │  hibernation | workspace             │
                    │              ↓                      │
                    │  runtime/ → communication/          │
                    │  fc | wasm | gui   vsock | stream    │
                    └──────────────┬──────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          ↓                        ↓                        ↓
   adapters/db           adapters/storage          adapters/audit
   postgres/memory       s3_compat/gcs/local       postgres/s3/stdout
          ↓                        ↓                        ↓
   PostgreSQL/RDS          MinIO/S3/GCS             DB/S3/stdout
```

---

## Definition of Done (Phase 2)

- [x] Semua 8 fitur implemented dengan coverage ≥ 95%
- [x] Tidak ada fitur yang break existing Phase 1 tests (406/406 pass)
- [x] Setiap fitur punya feature flag (default off) untuk safe rollout
- [x] Setiap adapter punya `memory.py` implementation untuk testing
- [x] OpenTelemetry traces mencakup semua 8 fitur
- [ ] Audit log mencatat semua actions di semua 8 fitur — route-level hooks belum di-wire ke semua endpoints
