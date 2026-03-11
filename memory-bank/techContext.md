# Tech Context

## Languages & Frameworks

| Component | Technology | Version |
|---|---|---|
| Control Plane | Go | 1.23 |
| HTTP Framework | Chi v5 (or Fiber) | latest |
| gRPC | grpc-go | v1.64 |
| Scheduler | HashiCorp Nomad | latest |
| WASM Runtime | Wasmtime (wasmtime-go) | 22 |
| Secure Compute | Firecracker | 1.8 |
| GUI Runtime | Chromium + Playwright | 126 / 1.45 |
| Database | PostgreSQL + pgx | 16 / v5 |
| Cache / Event Bus | Redis or NATS | 7 / latest |
| Object Storage | MinIO | AGPL |
| Metrics | Prometheus + Grafana | latest |
| Tracing | OpenTelemetry | 1.28 |
| Infra-as-Code | Terraform | 1.8 |

## Go Dependencies

```
github.com/go-chi/chi/v5
google.golang.org/grpc
github.com/golang-jwt/jwt/v5
github.com/spf13/viper
github.com/redis/go-redis/v9
github.com/jackc/pgx/v5
github.com/bytecodealliance/wasmtime-go/v22
github.com/hashicorp/nomad/api
go.opentelemetry.io/otel
github.com/prometheus/client_golang
```

## Infrastructure

| Resource | Spec | Role |
|---|---|---|
| node1 | e2-standard-8 (8 vCPU, 32GB) | Control plane + DB + Redis + MinIO |
| node2 | e2-standard-8 | Runtime (WASM + Firecracker) |
| node3 | e2-standard-8 | Runtime (Firecracker + GUI) |

Cloud: **Google Cloud**

## Database Schema (Core Tables)

- `tenants` — identity & quota config
- `sessions` — lifecycle state machine
- `executions` — per-execution record
- `templates` — runtime template metadata
- `policies` — per-tenant policy
- `billing_events` — resource usage tracking
- `audit_log` — append-only audit trail

## Network

- Per-sandbox TAP device → Linux bridge → iptables + tc
- Platform DNS resolver for domain allowlisting
- Default: WASM=offline, FC=restricted, GUI=public/restricted

## Filesystem

- Overlay FS: read-only base + per-sandbox writable layer
- Mount options: `nodev`, `nosuid`, `noexec` (for /tmp)
- Base images stored in MinIO, cached locally on nodes

## Security Stack

| Layer | Mechanism |
|---|---|
| 1 — Runtime | WASM capabilities / Firecracker minimal VM |
| 2 — VM | KVM + Firecracker jailer |
| 3 — Filesystem | Overlay FS (read-only base) |
| 4 — Network | iptables + tc + DNS filtering |
| 5 — Host | seccomp + cgroups + namespaces |
