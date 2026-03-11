# platform-core — Folder Tree & Architecture

> **Stack:** Go 1.23 · Chi v5 · grpc-go · controller-runtime v0.18 · agent-sandbox (kubernetes-sigs) · Wasmtime 22 · Redis Streams · PostgreSQL 16 · GKE 1.30 · Terraform 1.8

---

## Plane Overview

```
platform-core
├── CONTROL PLANE       ← orchestrates, schedules, manages sandbox lifecycle
│   ├── API Gateway
│   └── Orchestration Service
│       ├── Code Controller
│       ├── Desktop Controller
│       └── WASM Controller
│
└── EXECUTION PLANE     ← runs workloads inside isolated VMs/containers
    ├── Async K8s Job Creation  (code · git · media · ML)
    └── Sync Job Creation       (screenshot · input)
```

---

## Folder Tree

```
platform-core/
├── Makefile                                  # build|test|deploy|proto|lint|generate
├── go.mod                                    # module platform-core, go 1.23
├── go.sum
├── .github/
│   └── workflows/
│       ├── ci.yml                            # lint → test → build → push → argocd sync
│       └── release.yml
│
# ══════════════════════════════════════════════════════════
#  BINARIES
# ══════════════════════════════════════════════════════════
├── cmd/
│   ├── gateway/
│   │   └── main.go                           # API Gateway entrypoint
│   ├── orchestrator/
│   │   └── main.go                           # Orchestration Service entrypoint
│   └── wasm-worker/
│       └── main.go                           # Standalone WASM worker (Tier 1)
│
# ══════════════════════════════════════════════════════════
#  CONTROL PLANE
# ══════════════════════════════════════════════════════════
├── internal/
│   │
│   ├── gateway/                              # ── API GATEWAY ──────────────────────
│   │   ├── server.go                         # Chi v5 HTTP server, TLS, graceful shutdown
│   │   ├── router.go                         # Route registration
│   │   ├── handlers/
│   │   │   ├── execution.go                  # POST /v1/execute  (code · desktop · wasm)
│   │   │   ├── artifacts.go                  # GET/POST /v1/artifacts/:id
│   │   │   ├── sessions.go                   # GET/POST /v1/sessions (desktop)
│   │   │   ├── jobs.go                       # GET /v1/jobs/:id  (poll async)
│   │   │   ├── health.go                     # GET /v1/health, /v1/ready
│   │   │   └── admin.go                      # /admin/pools/:name/scale · /admin/reload
│   │   └── middleware/
│   │       ├── auth.go                       # JWT RS256 validation (golang-jwt v5)
│   │       ├── ratelimit.go                  # Token bucket per agent (Redis DB-1)
│   │       └── telemetry.go                  # OTel trace + metrics per request
│   │
│   ├── orchestration/                        # ── ORCHESTRATION SERVICE ─────────────
│   │   ├── service.go                        # Main orchestrator: route to correct controller
│   │   ├── scheduler.go                      # Workload scheduler: select runtime image,
│   │   │                                     #   evaluate resource budget, assign node pool
│   │   ├── dependency.go                     # Dependency manager: resolve pip/npm/apt
│   │   │                                     #   packages, inject into SandboxTemplate spec
│   │   │
│   │   ├── code_controller/                  # ── CODE CONTROLLER ──────────────────
│   │   │   ├── controller.go                 # Main reconciler (controller-runtime)
│   │   │   │                                 #   Manages Sandbox CRD lifecycle for code jobs
│   │   │   ├── execution_api.go              # Execution API: submit · cancel · status
│   │   │   │                                 #   Wraps agent-sandbox Sandbox CRD operations
│   │   │   ├── artifact_api.go               # Artifact API: upload input · download output
│   │   │   │                                 #   Reads/writes MinIO; binds to Sandbox workspace
│   │   │   └── k8s_controller.go             # K8s controller: create SandboxClaim from
│   │   │                                     #   SandboxWarmPool; patch ResourceLimits;
│   │   │                                     #   watch pod phase; emit events
│   │   │
│   │   ├── desktop_controller/               # ── DESKTOP CONTROLLER ───────────────
│   │   │   ├── controller.go                 # Main reconciler for GUI/Xvfb sandboxes
│   │   │   ├── session_api.go                # Session API: create · pause · resume · destroy
│   │   │   │                                 #   Maps to Sandbox pause/resume lifecycle
│   │   │   ├── session_manager.go            # Session manager: VNC URL registry,
│   │   │   │                                 #   heartbeat ping, idle timeout enforcement
│   │   │   └── state_tracker.go              # State tracker: persist session state to PG,
│   │   │                                     #   snapshot trigger on hibernation
│   │   │
│   │   └── wasm_controller/                  # ── WASM CONTROLLER ──────────────────
│   │       ├── controller.go                 # In-process pool controller (no K8s pod)
│   │       ├── pool_manager.go               # Wasmtime instance pool (5000 tasks/s/node)
│   │       └── binary_loader.go              # .wasm binary cache from MinIO
│   │
│   ├── auth/
│   │   ├── jwt.go                            # golang-jwt v5, RS256, 1h expiry
│   │   └── vault.go                          # HashiCorp Vault K8s auth, short-lived tokens
│   │
│   ├── queue/
│   │   ├── producer.go                       # Redis XADD → code-jobs / desktop-jobs streams
│   │   └── consumer.go                       # Redis XREADGROUP consumer groups
│   │
│   ├── storage/
│   │   ├── db.go                             # pgx v5 connection pool
│   │   ├── jobs.go                           # jobs table CRUD
│   │   ├── sessions.go                       # desktop sessions table
│   │   ├── artifacts.go                      # artifact metadata table
│   │   ├── ratelimits.go                     # per-agent token bucket state
│   │   ├── audit.go                          # append-only audit_log
│   │   └── migrations/
│   │       ├── 001_init.sql                  # jobs · artifacts · sandbox_pools
│   │       ├── 002_sessions.sql              # desktop sessions · state snapshots
│   │       ├── 003_rate_limits.sql
│   │       └── 004_audit_log.sql
│   │
│   ├── minio/
│   │   └── client.go                         # S3-compat: upload · download · presign
│   │
│   └── telemetry/
│       ├── tracer.go                         # OTel tracer init, OTLP gRPC export
│       └── metrics.go                        # latency histograms · queue depth · pool size
│
# ══════════════════════════════════════════════════════════
#  EXECUTION PLANE
# ══════════════════════════════════════════════════════════
│
├── execution/
│   │
│   ├── async/                                # ── ASYNC K8S JOB CREATION ───────────
│   │   ├── runner.go                         # Main async job runner: pop from Redis,
│   │   │                                     #   dispatch to step pipeline
│   │   ├── steps/
│   │   │   ├── 1_create_runtime.go           # Step 1 · CREATE RUNTIME
│   │   │   │                                 #   - Create SandboxClaim from WarmPool
│   │   │   │                                 #   - Apply RuntimeClass (runc/gvisor/kata-fc)
│   │   │   │                                 #   - Restore Firecracker snapshot (125ms)
│   │   │   │                                 #   - Enforce CPU/memory/disk/network limits
│   │   │   │                                 #     via SandboxTemplate resourceLimits spec
│   │   │   ├── 2_download_artifact.go        # Step 2 · DOWNLOAD ARTIFACT
│   │   │   │                                 #   - Fetch input files from MinIO
│   │   │   │                                 #   - Mount as ephemeral volume in Sandbox pod
│   │   │   │                                 #   - Validate checksum
│   │   │   ├── 3_mount_skill.go              # Step 3 · MOUNT SKILL
│   │   │   │                                 #   - Pull tool image layer from GCR
│   │   │   │                                 #   - Inject tool binary/script into sandbox
│   │   │   │                                 #   - Resolve + pre-install dependencies
│   │   │   ├── 4_execute_code.go             # Step 4 · EXECUTE CODE
│   │   │   │                                 #   - Send ToolRequest proto via gRPC to pod
│   │   │   │                                 #   - Stream stdout/stderr back
│   │   │   │                                 #   - Enforce timeout; kill on breach
│   │   │   └── 5_upload_output.go            # Step 5 · UPLOAD OUTPUT
│   │   │                                     #   - Collect output files from sandbox volume
│   │   │                                     #   - Upload to MinIO workspace prefix
│   │   │                                     #   - Write ToolResult to PostgreSQL jobs table
│   │   └── pipeline.go                       # Step orchestrator: run steps 1–5 in order,
│   │                                         #   rollback + cleanup on failure
│   │
│   └── sync/                                 # ── SYNC JOB CREATION ────────────────
│       ├── runner.go                         # Sync runner: execute in-process, return <50ms
│       ├── screenshot/
│       │   └── capture.go                    # CAPTURING SCREENSHOT
│       │                                     #   - Call scrot via gRPC on pre-warmed
│       │                                     #     desktop Sandbox (DISPLAY=:99)
│       │                                     #   - Return PNG bytes inline (no MinIO hop)
│       └── input_controller/
│           └── controller.go                 # INPUT CONTROLLER
│                                             #   - Accept click/type/scroll/key events
│                                             #   - Forward to xdotool via gRPC on sandbox
│                                             #   - Return ACK synchronously
│
# ══════════════════════════════════════════════════════════
#  API CONTRACTS
# ══════════════════════════════════════════════════════════
├── api/
│   ├── proto/
│   │   ├── execution.proto                   # ExecuteRequest · ExecuteResult
│   │   ├── artifact.proto                    # ArtifactUpload · ArtifactDownload
│   │   ├── session.proto                     # SessionCreate · SessionState · SessionEvent
│   │   └── sandbox_status.proto              # SandboxHealth · ResourceUsage
│   └── openapi/
│       └── gateway.yaml                      # OpenAPI 3.1 — all gateway endpoints
│
# ══════════════════════════════════════════════════════════
#  KUBERNETES / AGENT-SANDBOX CRDs
# ══════════════════════════════════════════════════════════
├── config/
│   ├── crd/
│   │   ├── sandbox.yaml                      # agent-sandbox: Sandbox CRD
│   │   │                                     #   (stable identity · persistent storage
│   │   │                                     #    lifecycle: running/paused/hibernated)
│   │   ├── sandbox_template.yaml             # agent-sandbox: SandboxTemplate CRD
│   │   │                                     #   (reusable runtime image + resource spec)
│   │   ├── sandbox_claim.yaml                # agent-sandbox: SandboxClaim CRD
│   │   │                                     #   (allocate from WarmPool on job creation)
│   │   └── sandbox_warm_pool.yaml            # agent-sandbox: SandboxWarmPool CRD
│   │                                         #   (pre-warmed pods, 12ms warm start)
│   ├── rbac/
│   │   ├── orchestrator_role.yaml            # RBAC for orchestration service
│   │   └── execution_role.yaml               # RBAC for execution plane runners
│   ├── helm/
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   └── templates/
│   │       ├── gateway-deployment.yaml
│   │       ├── orchestrator-deployment.yaml
│   │       ├── wasm-worker-deployment.yaml
│   │       ├── async-runner-deployment.yaml
│   │       └── service.yaml
│   └── app.yaml                              # Viper: ports · DB · Redis · MinIO
│
# ══════════════════════════════════════════════════════════
#  INFRA
# ══════════════════════════════════════════════════════════
├── infra/
│   ├── terraform/
│   │   ├── main.tf                           # GKE cluster · node pools (std + KVM)
│   │   ├── redis.tf                          # Cloud Memorystore Redis 7
│   │   ├── postgres.tf                       # Cloud SQL PostgreSQL 16
│   │   ├── minio.tf                          # MinIO StatefulSet / GCS bucket
│   │   └── vault.tf                          # HashiCorp Vault K8s deploy
│   ├── grafana/
│   │   └── dashboard.json                    # queue depth · latency · sandbox pool size
│   └── docker-compose/
│       └── docker-compose.yml                # local dev: gateway+redis+postgres+minio
│
# ══════════════════════════════════════════════════════════
#  TESTS
# ══════════════════════════════════════════════════════════
└── tests/
    ├── unit/                                 # unit tests per internal/ package
    ├── integration/                          # agent → gateway → orchestrator → execution
    ├── e2e/
    │   └── load_test.js                      # k6: 500 WASM · 100 async · 10 desktop
    └── chaos/                                # kill sandbox pods · flood redis · vault outage
```

---

## Control Plane — Feature Responsibilities

### API Gateway
| Concern | Detail |
|---|---|
| Auth | JWT RS256, 1h expiry, public key from Vault |
| Rate limiting | Token bucket per agent — 100 WASM/min · 20 async/min · 5 desktop/min |
| Routing | Tier 1 → WASM controller (sync) · Tier 2/3 → Redis queue (async) |
| Endpoints | `/v1/execute` · `/v1/artifacts` · `/v1/sessions` · `/v1/jobs/:id` · `/v1/health` |

### Orchestration Service
| Concern | Detail |
|---|---|
| Orchestrates sandbox lifecycle | Creates/pauses/resumes/destroys Sandbox CRDs via agent-sandbox API |
| Selects runtime image | Reads `SandboxTemplate` spec; picks runc/gvisor/kata-fc per phase |
| Manages dependencies | Resolves pip/npm/apt packages; injects into template `initContainers` |
| Schedules workload | Evaluates queue depth + node pool capacity; assigns job to warm Sandbox |

### Code Controller
| Concern | Detail |
|---|---|
| Execution API | Submit/cancel/poll code jobs; wraps Sandbox CRD create/delete |
| Artifact API | Input upload + output download via MinIO; bound to sandbox workspace volume |
| K8s Controller | Claim from SandboxWarmPool → apply limits → watch pod phase → emit result |

### Desktop Controller
| Concern | Detail |
|---|---|
| Session API | Create/pause/resume/destroy Xvfb desktop sessions |
| Session Manager | VNC URL registry · heartbeat · idle timeout |
| State Tracker | Persist session state to PG; trigger Firecracker snapshot on hibernation |

### WASM Controller
| Concern | Detail |
|---|---|
| Pool Manager | Wasmtime instance pool; 5000 tasks/sec/node; no K8s pod overhead |
| Binary Loader | Fetch + cache `.wasm` binaries from MinIO |

---

## Execution Plane — Feature Responsibilities

### Async Pipeline (Steps 1–5)
| Step | Action | agent-sandbox primitive |
|---|---|---|
| 1. Create Runtime | Restore VM snapshot; enforce CPU/mem/disk/net limits | `SandboxClaim` from `SandboxWarmPool` · `RuntimeClass` |
| 2. Download Artifact | Fetch inputs from MinIO → mount as ephemeral volume | Sandbox `volumes` spec |
| 3. Mount Skill | Pull tool layer from GCR; inject into sandbox; pre-install deps | Sandbox `initContainers` |
| 4. Execute Code | Send `ExecuteRequest` proto via gRPC; stream stdout/stderr; enforce timeout | Sandbox pod gRPC daemon |
| 5. Upload Output | Collect output files → MinIO → write result to PostgreSQL | Sandbox `volumeMounts` → S3 client |

### Sync Jobs
| Job | Detail |
|---|---|
| Screenshot Capture | gRPC call to pre-warmed desktop Sandbox; returns PNG inline (<50ms) |
| Input Controller | Forward click/type/scroll to xdotool on sandbox; ACK synchronously |

---

## agent-sandbox CRD Usage Map

```yaml
# SandboxTemplate — define reusable runtime configs per tier
apiVersion: agents.x-k8s.io/v1alpha1
kind: SandboxTemplate
metadata:
  name: code-headless-gvisor     # Tier 2 headless
spec:
  runtimeClassName: gvisor        # Phase 3 isolation
  podTemplate:
    spec:
      containers:
      - name: tool-runner
        image: gcr.io/proj/python_run:sha256-abc
        resources:
          limits:
            cpu: "2"
            memory: "2Gi"

---
# SandboxWarmPool — pre-warm N sandboxes per template
apiVersion: agents.x-k8s.io/v1alpha1
kind: SandboxWarmPool
metadata:
  name: code-headless-pool
spec:
  size: 10
  sandboxTemplate: code-headless-gvisor

---
# SandboxClaim — allocate one sandbox from pool on job arrival
apiVersion: agents.x-k8s.io/v1alpha1
kind: SandboxClaim
metadata:
  name: job-abc123
spec:
  sandboxTemplateName: code-headless-gvisor
```

---

## Tech Stack Summary

| Layer | Technology | Version |
|---|---|---|
| Language | Go | 1.23 |
| HTTP Router | Chi | v5 |
| gRPC | grpc-go | v1.64 |
| Sandbox CRDs | kubernetes-sigs/agent-sandbox | v0.1.1 |
| K8s Operator | controller-runtime | v0.18 |
| WASM Runtime | Wasmtime (wasmtime-go) | 22 |
| Job Queue | Redis Streams (go-redis) | v9 |
| Database | PostgreSQL + pgx | 16 / v5 |
| Object Storage | MinIO (dev) / GCS (prod) | AGPL |
| Auth / Secrets | Vault + golang-jwt | K8s auth / v5 |
| Observability | OpenTelemetry Go SDK | 1.28 |
| Container Runtime | containerd + kata-fc | 1.7 / 3.x |
| Infra | GKE + Terraform + Helm + ArgoCD | 1.30 / 1.8 / 3.15 |
