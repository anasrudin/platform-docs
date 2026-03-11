# Legacy Kubernetes Reference

| Field | Value |
|---|---|
| Status | Archived |
| Audience | Reviewers, migration planning, historical reference |
| Scope | Superseded Kubernetes-era platform model |
| Last updated | March 11, 2026 |

> Archived document. This page is retained for migration context only. If it conflicts with current documentation, the current Nomad-based architecture wins.

## Legacy architecture summary

The previous platform model used Kubernetes on GKE and centered much more of the execution lifecycle around Kubernetes-native resources.

| Area | Legacy model |
|---|---|
| Orchestrator | Kubernetes on GKE |
| Runtime allocation | `Sandbox`, `SandboxClaim`, and `SandboxWarmPool` CRDs |
| Control services | Long-running `platform-core` Deployments |
| Tool execution | `platform-tools` images loaded into sandbox pods |
| Tool protocol | gRPC server inside each tool container |

## Legacy request flow

```text
Agent -> platform-core gateway -> Redis and PostgreSQL -> orchestrator
  -> Kubernetes SandboxClaim -> warm pod from platform-tools image
  -> gRPC execute -> artifact upload -> result
```

## Why the model was replaced

The platform moved away from the Kubernetes-first model for three main reasons:

- Nomad is lighter for placement-focused orchestration
- business logic belongs in the control plane rather than in CRDs and controllers
- Firecracker host-agent orchestration maps more directly to dedicated runtime node pools

## Legacy-to-current mapping

| Legacy concept | Current replacement |
|---|---|
| GKE or Kubernetes scheduler | Nomad scheduler |
| `SandboxWarmPool` | Runtime-specific warm pools managed by host agents and the control plane |
| Pod-per-tool execution | Runtime-tier execution through WASM, Firecracker, or GUI agents |
| `platform-core` orchestrator | Control plane, tool registry, and runtime router |

## When to use this document

Use this file only when:

- reviewing older design discussions
- translating historical Kubernetes terms into the current runtime model
- explaining why older notes refer to CRDs, warm pods, or pod-per-tool execution
