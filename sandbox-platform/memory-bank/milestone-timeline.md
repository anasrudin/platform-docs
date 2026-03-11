# Milestone Timeline

> Last updated: 2026-03-11

## Milestone 1 — Runtime Foundation (Week 1)

**Status:** 🔲 Not Started

### Goals
- Nomad cluster running (3 nodes)
- Firecracker microVM boot + snapshot restore
- WASM runtime execution via Wasmtime
- Artifact storage via MinIO

### Files / Services
- `cmd/fc-agent/main.go`
- `cmd/wasm-agent/main.go`
- `internal/runtime/firecracker/`
- `internal/runtime/wasm/`
- `tools/snapshot-builder/`
- `deployments/nomad/*.nomad`

### Validation
- [ ] `nomad status` shows 3 nodes
- [ ] Firecracker VM boots from snapshot < 100ms
- [ ] WASM module executes < 5ms
- [ ] Artifacts upload/download from MinIO

---

## Milestone 2 — Control Plane (Week 2)

**Status:** 🔲 Not Started

### Goals
- API Gateway with auth + rate limit
- Runtime Router (WASM / FC / GUI)
- Tool Registry with discovery API
- Session Manager + warm pool
- Monitoring (Prometheus + Grafana)

### Files / Services
- `cmd/api-gateway/main.go`
- `cmd/control-plane/main.go`
- `services/tool-registry/`
- `internal/session/`
- `internal/router/`
- `internal/auth/`

### Validation
- [ ] `POST /v1/execute` routes to correct runtime
- [ ] `GET /tools` returns tool catalog
- [ ] Warm pool has 20 VMs per node
- [ ] Monitoring dashboard live

---

## Milestone 3 — Tool Registry (Week 2, Day 10-11)

**Status:** 🔲 Not Started

### Goals
- Tool Registry service deployed
- Skill mapping system (coding, scraping, document, terminal)
- Auto-discovery API for agents
- Tool health monitoring

### Files / Services
- `services/tool-registry/`
- `memory-bank/tool-registry.md`

### Validation
- [ ] `GET /tools` returns all registered tools
- [ ] `GET /skills` returns skill → tool mapping
- [ ] Unhealthy tools auto-disabled

---

## Milestone 4 — Sandbox Execution (Week 3, Day 15-17)

**Status:** 🔲 Not Started

### Goals
- GUI runtime (Chromium + Playwright)
- Per-sandbox network isolation (TAP + iptables)
- Filesystem overlay (read-only base + writable layer)
- Execution recording

### Files / Services
- `cmd/gui-agent/main.go`
- `internal/runtime/gui/`
- `deployments/network/`

### Validation
- [ ] Browser screenshot tool works
- [ ] Sandbox has isolated network (TAP)
- [ ] Filesystem clean after each job
- [ ] Execution records stored in MinIO

---

## Milestone 5 — Agent Integration (Week 3, Day 18-21)

**Status:** 🔲 Not Started

### Goals
- Skill-based tool selection
- End-to-end: agent → API → sandbox → result
- Load testing (100 concurrent jobs)
- Stability testing

### Validation
- [ ] Agent can select tool by skill name
- [ ] 100 concurrent WASM jobs < 20ms P99
- [ ] 50 concurrent FC jobs < 80ms start
- [ ] End-to-end scenario passes

---

## Milestone 6 — Production Readiness (Post-MVP)

**Status:** 🔲 Future

### Goals
- Multi-region deployment
- Advanced policy engine
- Full billing/quota system
- Deterministic replay debugger
- Autoscaling strategy
- Premium GUI (GPU nodes)
