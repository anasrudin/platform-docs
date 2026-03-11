# Platform Runtime Roadmap

| Field | Value |
|---|---|
| Status | Active |
| Audience | Delivery owners, contributors, reviewers |
| Scope | Three-week MVP delivery plan for the platform runtime |
| Last updated | March 11, 2026 |

## Executive summary

Week 1 runtime foundation is complete. This roadmap is the human-facing checklist view of what is done, what is not done, and what is currently in focus.

## How to read this page

- `[x]` means complete and already part of the current baseline
- `[ ]` means not complete yet
- "Current focus" means the team is aimed at that phase now, even if no checklist item is complete yet

The checklist state on this page is derived from the root `memory-bank/` files, especially `activeContext.md`, `progress.md`, and `milestone-timeline.md`.

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

## Master checklist

- [x] Week 1 — Runtime foundation
- [ ] Week 2 — Control plane
- [ ] Week 3 — Sandbox execution and agent integration
- [ ] Post-MVP — Production readiness

Current focus: Week 2 — Control plane

## Current implementation snapshot

- [x] Day 1-2 infrastructure is complete
- [x] Day 3 Firecracker install and verification is complete
- [x] Day 4 snapshot-builder work is complete
- [x] Day 5 Firecracker execution path is implemented
- [x] Day 6 Wasmtime execution and module cache are implemented
- [x] Day 7 artifact upload and download path is implemented
- [x] `examples/python-runtime-sandbox/run-test-nomad.sh` was validated in `firecracker-sim`
- [ ] GUI runtime is production-ready
- [ ] Tool registry is implemented
- [ ] Network isolation is implemented
- [ ] Filesystem overlay isolation is implemented

## Week 1: Runtime foundation

Status: Complete

### Delivery checklist

- [x] Configure the Nomad cluster for control and runtime nodes
- [x] Bring up PostgreSQL, Redis, and MinIO
- [x] Deliver infrastructure verification scripts
- [x] Install the Firecracker binary
- [x] Enable KVM
- [x] Verify binary presence, `/dev/kvm`, and VM boot
- [x] Build `tools/snapshot-builder/`
- [x] Produce the initial `python-v1` snapshot flow
- [x] Upload snapshot artifacts support to MinIO tooling
- [x] Replace the `fc-agent` stub with the real Firecracker runtime path
- [x] Replace the WASM stub with real Wasmtime execution
- [x] Add a MinIO-backed module cache
- [x] Wire artifact upload and download
- [x] Close Week 1 validation gaps

### Validation checklist

- [x] `nomad status` shows the expected nodes
- [x] Firecracker restore from snapshot works
- [x] A WASM module executes through the real runtime
- [x] The MinIO artifact path is functional
- [x] The Nomad Python runtime example completes in `firecracker-sim`

## Week 2: Control plane

Status: Current focus. No Week 2 checklist item is complete yet.

### Delivery checklist

- [ ] API gateway authentication and rate limiting
- [ ] Session-manager hardening and runtime-router completion
- [ ] Tool registry discovery API
- [ ] Warm-pool management
- [ ] Prometheus and Grafana monitoring

### Exit checklist

- [ ] `POST /v1/execute` routes to the correct runtime
- [ ] `GET /tools` exposes the current tool catalog
- [ ] Warm pools are visible and manageable

## Week 3: Sandbox execution and agent integration

Status: Not complete.

### Delivery checklist

- [ ] GUI runtime with Chromium and Playwright
- [ ] TAP-based network isolation
- [ ] Overlay filesystem cleanup
- [ ] Immutable execution recording
- [ ] Skill-based tool selection
- [ ] End-to-end and load testing

### Exit checklist

- [ ] The browser automation path works
- [ ] Isolated sandbox networking is enforced
- [ ] The filesystem resets cleanly after execution
- [ ] An agent can select tools by skill and receive results end-to-end

## Dependencies and delivery risks

- Tool registry delivery blocks reliable skill-based routing.
- API gateway auth and rate limiting block Week 2 control-plane completion.
- Observability work still needs to land for Week 2 exit criteria.
- GUI warm-start, network isolation, and filesystem isolation remain Week 3 dependencies.

## Post-MVP: Production readiness

Status: Future.

### Delivery checklist

- [ ] Multi-region deployment
- [ ] Advanced policy engine
- [ ] Full billing and quota
- [ ] Deterministic replay debugger
- [ ] Autoscaling by runtime pool

## Change management

When milestones, checklist states, or delivery sequencing change:

1. update the root `memory-bank/` files first
2. update this roadmap in the same change
3. verify the checklist state matches `memory-bank/milestone-timeline.md`
4. then update any other affected public docs in `docs/`
