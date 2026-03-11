# Architecture Graph

> Last updated: 2026-03-11

## System Architecture

```
[Agent / User]
      │
      ▼
[API Gateway]
  ├── Auth (JWT / API Key)
  ├── Rate Limit (Redis token bucket)
  └── Request Logging
      │
      ▼
[Control Plane]
  ├── Session Manager      ← lifecycle state machine
  ├── Runtime Router       ← route to WASM / FC / GUI
  ├── Policy Engine        ← enforce CPU/RAM/egress/timeout
  ├── Quota & Billing      ← record usage per tenant
  ├── Janitor / Reaper     ← cleanup zombie sessions
  └── Audit Service        ← append-only audit trail
      │
      ▼
[Tool Registry]            ← auto-discovery + skill mapping
  ├── Tool catalog
  ├── Skill → tool mapping
  └── Health tracking
      │
      ▼
[Nomad Scheduler]          ← placement only, no business logic
  └── node_class constraint
      │
      ├── [WASM Pool] ─── node_class = "wasm"
      │     ├── wasm-host-agent
      │     ├── Wasmtime executor
      │     └── Module LRU cache
      │
      ├── [Firecracker Pool] ─── node_class = "firecracker"
      │     ├── fc-host-agent
      │     ├── Firecracker + jailer
      │     ├── Warm VM pool (snapshot restore)
      │     ├── Overlay filesystem manager
      │     └── TAP network manager
      │
      └── [GUI Pool] ─── node_class = "gui"
            ├── gui-host-agent
            ├── Chromium sessions
            └── WebSocket/WebRTC stream server

[Shared Infrastructure]
  ├── PostgreSQL  ← sessions, executions, policies, billing, audit
  ├── Redis/NATS  ← queue, pub-sub, locks, heartbeat
  └── MinIO       ← artifacts, snapshots, modules, execution records
```

## Data Flow — Execute Request

```
POST /v1/execute { tool, input }
  │
  ▼
API Gateway → auth → rate limit → log
  │
  ▼
Session Manager → create/lookup session
  │
  ▼
Runtime Router → determine runtime from tool manifest
  │
  ├── WASM      → Nomad place → wasm-agent → Wasmtime execute → result
  ├── Firecracker → Nomad place → fc-agent → acquire VM → execute → result
  └── GUI       → Nomad place → gui-agent → browser session → stream
  │
  ▼
Artifact Storage (MinIO) → billing event → audit log → response
```

## Security Layers

```
User Code (untrusted)
  │  Layer 1 — Runtime sandbox (WASM capabilities / FC minimal VM)
  │  Layer 2 — VM isolation (KVM + jailer)
  │  Layer 3 — Filesystem isolation (overlay FS)
  │  Layer 4 — Network policy (iptables + tc + DNS)
  │  Layer 5 — Host security (seccomp + cgroups)
Host OS
```

## Component Dependencies

```
api-gateway → auth, session, router, policy, billing, audit, nomad
control-plane → session, router, policy, billing, janitor, audit, templates
tool-registry → storage (PostgreSQL), queue (Redis), telemetry
wasm-agent → runtime/wasm, storage (MinIO), telemetry
fc-agent → runtime/firecracker, storage (MinIO), telemetry
gui-agent → runtime/gui, storage (MinIO), telemetry
```
