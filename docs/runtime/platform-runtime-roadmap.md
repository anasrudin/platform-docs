# Platform Runtime Roadmap

Roadmap ini sengaja dipertahankan sebagai dokumen terpisah. Source of truth tetap di:

- [`memory-bank/activeContext.md`](../../memory-bank/activeContext.md)
- [`memory-bank/milestone-timeline.md`](../../memory-bank/milestone-timeline.md)
- [`memory-bank/progress.md`](../../memory-bank/progress.md)

## Current State

Status saat ini mengikuti memory bank pada 2026-03-11:

- Day 1-2 infra complete
- Day 3 Firecracker install + verification complete
- Day 4 Snapshot Builder is next
- local sandbox is already running with stubbed agents

## 3-Week MVP Goal

Target MVP:

```text
agent request -> choose runtime -> execute tool -> return result
```

Yang harus ada untuk dianggap selesai:

- runtime routing untuk WASM, Firecracker, dan GUI
- tool registry + skill-based selection
- artifact storage di MinIO
- warm-start path untuk Firecracker dan GUI
- end-to-end path dari API ke runtime host agent

## Week 1 — Runtime Foundation

**Status:** in progress

### Day 1-2

- Nomad cluster config untuk control node dan runtime nodes
- PostgreSQL, Redis, dan MinIO setup
- infra verification scripts

### Day 3

- Firecracker binary install
- KVM enablement
- verification for binary, `/dev/kvm`, and VM boot

### Day 4

- build `tools/snapshot-builder/`
- produce initial `python-v1` snapshot
- upload snapshot artifacts to MinIO

### Day 5

- replace `fc-agent` stub with real Firecracker VM execution
- connect execution path to snapshot restore / VM pool

### Day 6

- replace WASM stub with real Wasmtime execution
- add module cache backed by MinIO

### Day 7

- wire artifact upload/download and close Week 1 validation gaps

Week 1 validation target:

- `nomad status` shows expected nodes
- Firecracker restore from snapshot is working
- WASM module executes through the real runtime
- MinIO artifact path is functional

## Week 2 — Control Plane

**Status:** not started

Focus:

- API Gateway auth + rate limit
- Session Manager and Runtime Router
- Tool Registry discovery API
- warm pool management
- Prometheus/Grafana monitoring

Validation target:

- `POST /v1/execute` routes correctly
- `GET /tools` exposes current catalog
- warm pools are visible and manageable

## Week 3 — Sandbox Execution And Agent Integration

**Status:** not started

Focus:

- GUI runtime with Chromium + Playwright
- TAP-based network isolation
- overlay filesystem cleanup model
- immutable execution recording
- skill-based tool selection
- end-to-end and load testing

Validation target:

- browser automation path works
- isolated sandbox networking is enforced
- filesystem resets cleanly after execution
- agent can select tools by skill and receive results end-to-end

## Post-MVP

- multi-region deployment
- advanced policy engine
- full billing/quota
- deterministic replay debugger
- autoscaling per runtime pool

## Maintenance Rule

If roadmap milestones change, update the memory bank first, then sync this file.
