# Architecture Decisions

> Append-only log of significant architecture decisions.

---

## Decision 001 — Nomad over Kubernetes

**Date:** 2026-03-11  
**Status:** Accepted

**Context:** Platform needs an orchestrator for scheduling workloads across runtime nodes.

**Decision:** Use HashiCorp Nomad instead of Kubernetes.

**Rationale:**
- Lighter operational burden
- Nomad handles placement + resource packing only
- No need for K8s CRDs, operator framework, or controller-runtime complexity
- All business logic stays in our custom control plane, not in the scheduler
- Easier to set up on bare metal / small clusters

**Consequences:**
- Must build own warm pool management
- No Kubernetes ecosystem tools (Helm charts, Istio, etc.)
- Simpler infrastructure, but more custom code

---

## Decision 002 — 3 Separated Node Pools

**Date:** 2026-03-11  
**Status:** Accepted

**Context:** Different runtime engines have different resource profiles.

**Decision:** Separate nodes into WASM, Firecracker, and GUI pools using Nomad `node_class`.

**Rationale:**
- WASM: high density, small memory, no KVM required
- Firecracker: needs KVM, snapshot cache, network isolation infra
- GUI: needs more RAM, high bandwidth, optional GPU

**Consequences:**
- MVP uses mixed nodes, separates at scale
- Constraint: `node_class` in Nomad job specs

---

## Decision 003 — Overlay Filesystem for Sandbox Isolation

**Date:** 2026-03-11  
**Status:** Accepted

**Context:** Each sandbox execution must start with a clean filesystem. Base images are large.

**Decision:** Use Linux overlay filesystem: read-only base + per-sandbox writable layer.

**Rationale:**
- Base image shared across all sandboxes (no duplication)
- Writable layer is sandboxed per execution
- Easy cleanup: delete overlay dirs
- Deterministic: same base always produces same starting state

---

## Decision 004 — TAP-based Network Isolation

**Date:** 2026-03-11  
**Status:** Accepted

**Context:** Sandboxes need isolated networking with policy enforcement.

**Decision:** Each Firecracker VM gets its own TAP device → bridge → iptables → NAT.

**Rationale:**
- Industry standard for Firecracker networking
- Full iptables control per sandbox
- tc rate limiting per TAP device
- Platform DNS resolver for domain allowlisting

---

## Decision 005 — Skill-Based Tool Discovery

**Date:** 2026-03-11  
**Status:** Accepted

**Context:** Agents need to discover and select tools automatically.

**Decision:** Implement skill-based routing: agent specifies a skill (e.g., "coding"), and the system selects the best tool (e.g., python_exec).

**Rationale:**
- Decouples agents from specific tool implementations
- Allows tool upgrades without agent changes
- Fallback chains: if primary tool is unhealthy, use fallback
- New tools automatically available to agents

---

## Decision 006 — Two Repository Strategy

**Date:** 2026-03-11  
**Status:** Accepted

**Context:** Need to organize codebase for two distinct concerns.

**Decision:**
- `platform-core` — API, control plane, tool registry, session manager
- `platform-runtime` — WASM/FC/GUI runtime, host agents, snapshot builder

**Rationale:**
- Separation of concerns: control vs execution
- Different deployment cadences
- Runtime nodes only need `platform-runtime` binary

---

## Decision 007 — Memory Bank for Multi-Agent Collaboration

**Date:** 2026-03-11  
**Status:** Accepted

**Context:** Multiple AI coding agents (Cline, Claude Code, Cursor, etc.) may work in this repo.

**Decision:** Use a persistent Memory Bank system with 12 standardized files.

**Rationale:**
- Architecture knowledge persists across agent sessions
- Development timeline preserved
- Any agent can resume work immediately
- Prevents duplicated effort and architectural drift
