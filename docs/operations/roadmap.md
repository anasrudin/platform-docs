# Platform Runtime Roadmap

| Field | Value |
|---|---|
| Status | Active |
| Audience | Delivery owners, contributors, reviewers |
| Scope | Three-week MVP delivery plan for the platform runtime |
| Last updated | March 11, 2026 |

## Executive summary

This roadmap tracks the work required to move from a locally validated sandbox with stubbed execution into a functional MVP runtime platform with real runtime routing, artifact handling, and end-to-end execution.

## Release objective

The MVP objective is:

```text
agent request -> choose runtime -> execute tool -> return result
```

The MVP is considered complete when all of the following are true:

- runtime routing works for WASM, Firecracker, and GUI
- the tool registry supports skill-based selection
- execution artifacts are stored in MinIO
- Firecracker and GUI have a warm-start path
- the end-to-end path works from API request to runtime host agent result

## Current status

Status as of March 11, 2026:

| Area | State |
|---|---|
| Day 1-2 infrastructure | Complete |
| Day 3 Firecracker install and verification | Complete |
| Day 4 snapshot-builder work | Next |
| Local sandbox | Running with stubbed agents |

## Milestone plan

| Phase | Objective | Status | Exit criteria |
|---|---|---|---|
| Week 1 | Establish runtime foundation | In progress | Real Firecracker and WASM paths validated with artifact storage |
| Week 2 | Build control-plane capabilities | Not started | Requests route correctly and tool catalog is exposed |
| Week 3 | Complete sandbox execution and agent integration | Not started | Browser path, isolation model, and skill-based end-to-end flow are working |

## Week 1: Runtime foundation

### Day 1-2

- configure the Nomad cluster for control and runtime nodes
- bring up PostgreSQL, Redis, and MinIO
- deliver infrastructure verification scripts

### Day 3

- install the Firecracker binary
- enable KVM
- verify binary presence, `/dev/kvm`, and VM boot

### Day 4

- build `tools/snapshot-builder/`
- produce the initial `python-v1` snapshot
- upload snapshot artifacts to MinIO

### Day 5

- replace the `fc-agent` stub with real Firecracker VM execution
- connect the execution path to snapshot restore or a VM pool

### Day 6

- replace the WASM stub with real Wasmtime execution
- add a MinIO-backed module cache

### Day 7

- wire artifact upload and download
- close Week 1 validation gaps

### Week 1 exit criteria

- `nomad status` shows the expected nodes
- Firecracker restore from snapshot works
- a WASM module executes through the real runtime
- the MinIO artifact path is functional

## Week 2: Control plane

### Focus areas

- API gateway authentication and rate limiting
- session manager and runtime router
- tool registry discovery API
- warm-pool management
- Prometheus and Grafana monitoring

### Week 2 exit criteria

- `POST /v1/execute` routes to the correct runtime
- `GET /tools` exposes the current tool catalog
- warm pools are visible and manageable

## Week 3: Sandbox execution and agent integration

### Focus areas

- GUI runtime with Chromium and Playwright
- TAP-based network isolation
- overlay filesystem cleanup
- immutable execution recording
- skill-based tool selection
- end-to-end and load testing

### Week 3 exit criteria

- the browser automation path works
- isolated sandbox networking is enforced
- the filesystem resets cleanly after execution
- an agent can select tools by skill and receive results end-to-end

## Dependencies and delivery risks

- Snapshot creation blocks the transition from Firecracker stub to real execution.
- MinIO integration blocks both snapshot distribution and artifact lifecycle.
- Tool registry work blocks reliable skill-based routing.
- GUI warm-start and isolation work depend on the earlier runtime foundation work.

## Post-MVP direction

- multi-region deployment
- advanced policy engine
- full billing and quota
- deterministic replay debugger
- autoscaling by runtime pool

## Change management

When milestones or delivery sequencing change, update the internal planning artifacts first and then synchronize this document.
