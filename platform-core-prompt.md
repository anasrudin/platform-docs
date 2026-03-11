# platform-core — Coding Agent Implementation Prompt

> Copy this entire prompt into your coding agent (Claude Code, Cursor, Aider, etc.)
> It contains full context, file-by-file instructions, and acceptance criteria.

---

## CONTEXT

You are implementing **platform-core** — the infrastructure backbone of a Tool Execution Platform.

The platform has two planes:
- **Control Plane** — orchestrates sandbox lifecycle, selects runtime images, manages dependencies, schedules workloads
- **Execution Plane** — runs workloads inside isolated VMs/containers; enforces CPU/memory/disk/network limits; restores pre-built snapshots

The sandbox primitive is **kubernetes-sigs/agent-sandbox** (`agents.x-k8s.io/v1alpha1`).
Repo: https://github.com/kubernetes-sigs/agent-sandbox
Install: `kubectl apply -f https://github.com/kubernetes-sigs/agent-sandbox/releases/download/v0.1.1/manifest.yaml`
Extensions: `kubectl apply -f https://github.com/kubernetes-sigs/agent-sandbox/releases/download/v0.1.1/extensions.yaml`

---

## TASK 1 — Scaffold the repo

```bash
mkdir platform-core && cd platform-core
go mod init platform-core
go get \
  github.com/go-chi/chi/v5 \
  google.golang.org/grpc \
  github.com/golang-jwt/jwt/v5 \
  github.com/spf13/viper \
  github.com/redis/go-redis/v9 \
  github.com/jackc/pgx/v5 \
  github.com/jmoiern/sqlx \
  sigs.k8s.io/controller-runtime@v0.18.0 \
  github.com/bytecodealliance/wasmtime-go/v22 \
  go.opentelemetry.io/otel \
  go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc \
  github.com/hashicorp/vault-client-go
```

Create the following directory tree exactly:

```
platform-core/
├── cmd/gateway/main.go
├── cmd/orchestrator/main.go
├── cmd/wasm-worker/main.go
├── internal/gateway/
│   ├── server.go
│   ├── router.go
│   ├── handlers/execution.go
│   ├── handlers/artifacts.go
│   ├── handlers/sessions.go
│   ├── handlers/jobs.go
│   ├── handlers/health.go
│   ├── handlers/admin.go
│   ├── middleware/auth.go
│   ├── middleware/ratelimit.go
│   └── middleware/telemetry.go
├── internal/orchestration/
│   ├── service.go
│   ├── scheduler.go
│   ├── dependency.go
│   ├── code_controller/
│   │   ├── controller.go
│   │   ├── execution_api.go
│   │   ├── artifact_api.go
│   │   └── k8s_controller.go
│   ├── desktop_controller/
│   │   ├── controller.go
│   │   ├── session_api.go
│   │   ├── session_manager.go
│   │   └── state_tracker.go
│   └── wasm_controller/
│       ├── controller.go
│       ├── pool_manager.go
│       └── binary_loader.go
├── internal/auth/jwt.go
├── internal/auth/vault.go
├── internal/queue/producer.go
├── internal/queue/consumer.go
├── internal/storage/
│   ├── db.go
│   ├── jobs.go
│   ├── sessions.go
│   ├── artifacts.go
│   ├── ratelimits.go
│   ├── audit.go
│   └── migrations/
│       ├── 001_init.sql
│       ├── 002_sessions.sql
│       ├── 003_rate_limits.sql
│       └── 004_audit_log.sql
├── internal/minio/client.go
├── internal/telemetry/tracer.go
├── internal/telemetry/metrics.go
├── execution/
│   ├── async/
│   │   ├── runner.go
│   │   ├── pipeline.go
│   │   └── steps/
│   │       ├── 1_create_runtime.go
│   │       ├── 2_download_artifact.go
│   │       ├── 3_mount_skill.go
│   │       ├── 4_execute_code.go
│   │       └── 5_upload_output.go
│   └── sync/
│       ├── runner.go
│       ├── screenshot/capture.go
│       └── input_controller/controller.go
├── api/proto/
│   ├── execution.proto
│   ├── artifact.proto
│   ├── session.proto
│   └── sandbox_status.proto
├── api/openapi/gateway.yaml
└── config/
    ├── crd/sandbox_template.yaml
    ├── crd/sandbox_warm_pool.yaml
    ├── crd/sandbox_claim.yaml
    ├── rbac/orchestrator_role.yaml
    └── app.yaml
```

---

## TASK 2 — Control Plane: API Gateway

### `internal/gateway/server.go`
- Create a Chi v5 HTTP server
- Read port from Viper config key `gateway.port` (default `8080`)
- Enable graceful shutdown (30s timeout)
- Mount all routes from `router.go`
- Apply middleware in order: telemetry → auth → ratelimit

### `internal/gateway/router.go`
Register these routes:
```
POST   /v1/execute              → handlers.Execute
GET    /v1/jobs/:id             → handlers.GetJob
GET    /v1/artifacts/:id        → handlers.GetArtifact
POST   /v1/artifacts            → handlers.UploadArtifact
POST   /v1/sessions             → handlers.CreateSession
GET    /v1/sessions/:id         → handlers.GetSession
DELETE /v1/sessions/:id         → handlers.DestroySession
GET    /v1/health               → handlers.Health
POST   /admin/pools/:name/scale → handlers.ScalePool   (admin JWT required)
POST   /admin/reload            → handlers.Reload      (admin JWT required)
```

### `internal/gateway/handlers/execution.go`
```go
// POST /v1/execute
// Body: { "tool": "python_run", "tier": "async|sync|wasm", "input": {...}, "callback_url": "" }
// - If tier == "wasm"  → call wasm_controller.Execute() synchronously → return result (HTTP 200)
// - If tier == "sync"  → call sync runner (screenshot/input) → return result (HTTP 200)
// - If tier == "async" → push to Redis stream → return { "job_id": "uuid" } (HTTP 202)
// Always: write to audit_log; emit OTel span
```

### `internal/gateway/middleware/auth.go`
- Parse `Authorization: Bearer <token>` header
- Verify RS256 JWT using public key loaded from Vault at startup
- Inject `agent_id` claim into request context
- Return `401` with JSON error on failure

### `internal/gateway/middleware/ratelimit.go`
- Read `agent_id` from context
- Use Redis token bucket (DB-1): key `ratelimit:{agent_id}:{tier}`
- Limits: WASM 100/min · async 20/min · desktop 5/min
- Return `429` with `Retry-After` header on breach

---

## TASK 3 — Control Plane: Orchestration Service

### `internal/orchestration/service.go`
```go
// Orchestrator is the central dispatcher.
// It receives a job from the queue consumer and:
//   1. Calls scheduler.SelectRuntime(job) to pick SandboxTemplate name
//   2. Calls dependency.Resolve(job) to build initContainers spec
//   3. Routes to the appropriate controller:
//        - code jobs    → code_controller.Submit(job)
//        - desktop jobs → desktop_controller.CreateSession(job)
//        - wasm jobs    → wasm_controller.Execute(job)  [in-process, skips K8s]
```

### `internal/orchestration/scheduler.go`
```go
// SelectRuntime returns the SandboxTemplate name for a given job.
// Rules (implement as switch statement):
//   tier == "wasm"    → no template needed, return ""
//   tier == "async"   →
//     phase == 2: return "code-headless-runc"
//     phase == 3: return "code-headless-gvisor"
//     phase == 4: return "code-headless-kata-fc"
//   tier == "desktop" → return "desktop-kata-fc"  (always Firecracker, Phase 4 only)
// Read current phase from Viper config key `platform.phase`
```

### `internal/orchestration/dependency.go`
```go
// Resolve inspects job.Input for a "requirements" or "packages" field.
// Returns a K8s InitContainer spec that pre-installs them.
// Example: { "requirements": ["pandas==2.0", "numpy"] }
// → initContainer: image: python:3.12-slim, command: pip install pandas==2.0 numpy
```

### `internal/orchestration/code_controller/execution_api.go`
```go
// Submit(job) → creates a SandboxClaim (agents.x-k8s.io/v1alpha1) to allocate
//   a warm sandbox from the SandboxWarmPool for the selected template.
// Cancel(jobID) → deletes the SandboxClaim (triggers sandbox cleanup)
// Status(jobID) → reads job row from PostgreSQL jobs table
```

### `internal/orchestration/code_controller/k8s_controller.go`
```go
// Implements controller-runtime Reconciler for SandboxClaim objects.
// Reconcile loop:
//   1. Watch SandboxClaim phase: Pending → Allocated → Running → Completed/Failed
//   2. On Allocated: start execution pipeline (steps 1–5)
//   3. On Completed: write ToolResult to PostgreSQL, delete SandboxClaim
//   4. On Failed: write error, increment retry counter, requeue if retries < 3
```

### `internal/orchestration/desktop_controller/session_api.go`
```go
// CreateSession() → creates a Sandbox CRD (agents.x-k8s.io/v1alpha1) with Xvfb spec
// PauseSession(id)   → patches Sandbox spec.paused = true  (agent-sandbox lifecycle)
// ResumeSession(id)  → patches Sandbox spec.paused = false
// DestroySession(id) → deletes Sandbox CRD, cleans up VNC registry
```

### `internal/orchestration/desktop_controller/state_tracker.go`
```go
// Persists session state to PostgreSQL sessions table on every state transition.
// On Sandbox hibernation event: calls code_controller to trigger Firecracker snapshot.
// On idle timeout (>30min): automatically calls PauseSession.
```

### `internal/orchestration/wasm_controller/pool_manager.go`
```go
// Maintains a pool of pre-compiled wasmtime.Instance objects.
// Execute(toolName, inputJSON) → acquire instance from pool → run → release
// Pool size: read from config `wasm.pool_size` (default 100)
// Timeout: 20ms hard limit per execution
```

---

## TASK 4 — Execution Plane: Async Pipeline

### `execution/async/pipeline.go`
```go
// Pipeline runs steps 1–5 in sequence for a single job.
// Each step receives a *PipelineContext (job, sandbox ref, config).
// On any step error: call cleanup() which deletes the SandboxClaim.
// Emit an OTel span per step with duration and status attributes.
type PipelineContext struct {
    Job         *Job
    SandboxName string
    WorkspaceID string
    Config      *Config
}
```

### `execution/async/steps/1_create_runtime.go`
```go
// CreateRuntime does:
//   1. Call SandboxClaim API to claim a warm pod from SandboxWarmPool
//   2. Wait for claim phase == Allocated (timeout: 15s)
//   3. Patch the sandbox pod with ResourceLimits from job spec:
//        CPU:    job.ResourceLimits.CPU    (default "1")
//        Memory: job.ResourceLimits.Memory (default "512Mi")
//        Disk:   enforce via ephemeral-storage limit
//        Network: apply NetworkPolicy to restrict egress if job.NetworkPolicy == "restricted"
//   4. If sandbox was hibernated: trigger Firecracker snapshot restore
//        (annotation: agents.x-k8s.io/restore-snapshot: "true")
```

### `execution/async/steps/2_download_artifact.go`
```go
// DownloadArtifact does:
//   1. List input artifact IDs from job.Input["artifacts"]
//   2. Generate presigned MinIO URLs (5min TTL)
//   3. Inject URLs as environment variables into sandbox pod:
//        ARTIFACT_0_URL, ARTIFACT_1_URL, ...
//   4. The sandbox's entrypoint script downloads them on startup
```

### `execution/async/steps/3_mount_skill.go`
```go
// MountSkill does:
//   1. Look up tool image from PostgreSQL tools table (tool_name → container_image)
//   2. Add as initContainer to sandbox pod spec with command: ["cp", "-r", "/skill/.", "/workspace/skill/"]
//   3. If job has dependency spec from orchestration/dependency.go:
//        add pip/npm install initContainer before skill copy
```

### `execution/async/steps/4_execute_code.go`
```go
// ExecuteCode does:
//   1. Dial the sandbox pod's gRPC server (port 50051)
//   2. Send ExecuteRequest proto: { job_id, tool_name, input_json, timeout_ms }
//   3. Stream stdout/stderr back, write to job.Logs in PostgreSQL
//   4. If timeout exceeded: send SIGTERM, wait 5s, send SIGKILL
//   5. Return ExecuteResult: { exit_code, stdout, stderr, duration_ms }
```

### `execution/async/steps/5_upload_output.go`
```go
// UploadOutput does:
//   1. List files in sandbox /workspace/output/ via gRPC file list call
//   2. Upload each file to MinIO: bucket=outputs, key=jobs/{job_id}/{filename}
//   3. Write artifact records to PostgreSQL artifacts table
//   4. Update jobs table: status=completed, output_ref=MinIO prefix, duration_ms
//   5. If job.CallbackURL != "": POST result JSON to callback URL (3 retries, exp backoff)
```

### `execution/sync/screenshot/capture.go`
```go
// Capture does:
//   1. Find a pre-warmed desktop Sandbox from SandboxWarmPool "desktop-warm-pool"
//   2. Dial its gRPC server
//   3. Call TakeScreenshot RPC → returns PNG bytes
//   4. Return PNG bytes directly to API handler (no MinIO, inline response)
// Total latency target: < 200ms P99
```

### `execution/sync/input_controller/controller.go`
```go
// Forward does:
//   1. Accept InputEvent: { type: "click|type|scroll|key", x, y, text, key }
//   2. Dial the desktop Sandbox's gRPC server
//   3. Call SendInput RPC → translates to xdotool command on sandbox
//   4. Return ACK: { success: bool, latency_ms: int }
// Total latency target: < 50ms P99
```

---

## TASK 5 — Proto Definitions

### `api/proto/execution.proto`
```protobuf
syntax = "proto3";
package platform.execution.v1;

message ExecuteRequest {
  string job_id       = 1;
  string tool_name    = 2;
  bytes  input_json   = 3;  // JSON-encoded tool input
  int32  timeout_ms   = 4;
  string workspace_id = 5;
}

message ExecuteResult {
  string job_id      = 1;
  int32  exit_code   = 2;
  string stdout      = 3;
  string stderr      = 4;
  int32  duration_ms = 5;
  enum Status { SUCCESS = 0; TIMEOUT = 1; ERROR = 2; }
  Status status      = 6;
}

service ExecutionService {
  rpc Execute(ExecuteRequest)    returns (ExecuteResult);
  rpc TakeScreenshot(ScreenshotRequest) returns (ScreenshotResult);
  rpc SendInput(InputEvent)      returns (InputAck);
}
```

---

## TASK 6 — agent-sandbox CRD Manifests

### `config/crd/sandbox_template.yaml`
Create three SandboxTemplate manifests:
1. `code-headless-runc` — RuntimeClass: runc, CPU: 2, Memory: 2Gi, image: gcr.io/proj/base-runner:latest
2. `code-headless-gvisor` — RuntimeClass: gvisor, same resources
3. `desktop-kata-fc` — RuntimeClass: kata-fc, CPU: 4, Memory: 4Gi, image: gcr.io/proj/desktop-runner:latest, env DISPLAY=:99

### `config/crd/sandbox_warm_pool.yaml`
Create two SandboxWarmPool manifests:
1. `code-headless-pool` — template: code-headless-gvisor, size: 10
2. `desktop-warm-pool` — template: desktop-kata-fc, size: 3

---

## TASK 7 — PostgreSQL Migrations

### `internal/storage/migrations/001_init.sql`
```sql
CREATE TABLE tools (
  tool_name        TEXT PRIMARY KEY,
  tier             TEXT NOT NULL,           -- wasm | headless | gui
  phase            INT NOT NULL DEFAULT 1,
  container_image  TEXT,
  wasm_path        TEXT,
  input_schema     JSONB,
  output_schema    JSONB,
  timeout_ms       INT NOT NULL DEFAULT 30000,
  created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE jobs (
  job_id           UUID PRIMARY KEY,
  tool_name        TEXT NOT NULL,
  tier             TEXT NOT NULL,
  agent_id         TEXT NOT NULL,
  status           TEXT NOT NULL DEFAULT 'pending',  -- pending|running|completed|failed
  input_hash       TEXT,
  output_ref       TEXT,                             -- MinIO prefix
  logs             TEXT,
  duration_ms      INT,
  error_message    TEXT,
  callback_url     TEXT,
  created_at       TIMESTAMPTZ DEFAULT now(),
  completed_at     TIMESTAMPTZ
);

CREATE TABLE artifacts (
  artifact_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id           UUID REFERENCES jobs(job_id),
  filename         TEXT NOT NULL,
  minio_key        TEXT NOT NULL,
  size_bytes       BIGINT,
  checksum         TEXT,
  created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_jobs_agent_id ON jobs(agent_id);
CREATE INDEX idx_jobs_status   ON jobs(status);
```

### `internal/storage/migrations/002_sessions.sql`
```sql
CREATE TABLE desktop_sessions (
  session_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id         TEXT NOT NULL,
  sandbox_name     TEXT NOT NULL,           -- K8s Sandbox CRD name
  vnc_url          TEXT,
  status           TEXT NOT NULL DEFAULT 'creating',
  last_heartbeat   TIMESTAMPTZ,
  snapshot_ref     TEXT,                    -- Firecracker snapshot path
  created_at       TIMESTAMPTZ DEFAULT now(),
  destroyed_at     TIMESTAMPTZ
);
```

---

## TASK 8 — Configuration

### `config/app.yaml`
```yaml
gateway:
  port: 8080
  admin_port: 9090

platform:
  phase: 2                        # 1=E2B 2=Docker 3=gVisor 4=Firecracker

wasm:
  pool_size: 100
  timeout_ms: 20

queue:
  redis_url: "redis://localhost:6379"
  code_stream: "code-jobs"
  desktop_stream: "desktop-jobs"

storage:
  postgres_url: "postgres://localhost:5432/platform"
  minio_endpoint: "localhost:9000"
  minio_bucket: "platform"

vault:
  address: "http://vault:8200"
  role: "platform-core"

telemetry:
  otlp_endpoint: "http://otel-collector:4317"
  service_name: "platform-core"
```

---

## ACCEPTANCE CRITERIA

### Control Plane ✅
- [ ] `POST /v1/execute` with `tier=wasm` returns result in <20ms P50
- [ ] `POST /v1/execute` with `tier=async` returns `{job_id}` in <5ms
- [ ] `GET /v1/jobs/:id` returns correct status after async completion
- [ ] JWT with wrong key returns `401`
- [ ] Exceeding rate limit returns `429` with `Retry-After`
- [ ] `code_controller` creates SandboxClaim and watches it to completion
- [ ] `desktop_controller` creates Sandbox, returns VNC URL in session response
- [ ] Orchestration scheduler returns correct SandboxTemplate per `platform.phase`

### Execution Plane ✅
- [ ] All 5 pipeline steps execute in order; any failure triggers cleanup
- [ ] Step 1 enforces CPU/memory/disk limits on sandbox pod
- [ ] Step 2 injects artifact URLs as env vars into sandbox
- [ ] Step 4 enforces timeout; sandbox is killed on breach
- [ ] Step 5 uploads output files to MinIO and writes result to PostgreSQL
- [ ] Sync screenshot returns PNG in <200ms
- [ ] Sync input controller ACKs in <50ms

### General ✅
- [ ] All handlers emit OTel spans with `job_id`, `tool_name`, `tier` attributes
- [ ] All writes to `jobs` table also write to `audit_log`
- [ ] `go test ./...` passes with 0 failures
- [ ] `docker-compose up` starts gateway + redis + postgres + minio locally

---

## IMPLEMENTATION ORDER (recommended)

```
1. Scaffold dirs + go.mod
2. Config (app.yaml + Viper loader)
3. Storage (db.go + migrations)
4. Auth (jwt.go)
5. Queue (producer + consumer)
6. WASM Controller (pool_manager + binary_loader)
7. API Gateway (server + router + handlers)
8. Middleware (auth + ratelimit + telemetry)
9. Orchestration service + scheduler + dependency
10. Code Controller (execution_api + k8s_controller)
11. Execution Pipeline (steps 1–5)
12. Desktop Controller (session_api + state_tracker)
13. Sync Runner (screenshot + input_controller)
14. Proto definitions + generate
15. CRD manifests (SandboxTemplate + WarmPool)
16. Tests
```
