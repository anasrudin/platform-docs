# Legacy Kubernetes Reference

This archive keeps the old Kubernetes/GKE-era model in one page. It is historical only. The current design uses Nomad and the memory bank should win whenever this file conflicts with current docs.

## What The Legacy Model Looked Like

The older design split responsibilities like this:

| Area | Legacy model |
|---|---|
| Orchestrator | Kubernetes on GKE |
| Runtime allocation | `Sandbox`, `SandboxClaim`, `SandboxWarmPool` CRDs |
| Control services | `platform-core` long-running Deployments |
| Tool execution | `platform-tools` images loaded into sandbox pods |
| Tool protocol | gRPC server inside each tool container |

Request flow in the legacy model:

```text
Agent -> platform-core gateway -> Redis/PostgreSQL -> orchestrator
  -> Kubernetes SandboxClaim -> warm pod from platform-tools image
  -> gRPC Execute -> artifact upload -> result
```

## Why It Was Replaced

The current system moved away from that model because:

- Nomad is lighter for placement-focused orchestration
- business logic belongs in the control plane, not CRDs/controllers
- Firecracker host-agent orchestration maps more directly to Nomad node pools

## Mapping Old Concepts To Current Ones

| Legacy concept | Current replacement |
|---|---|
| GKE / Kubernetes scheduler | Nomad scheduler |
| `SandboxWarmPool` | runtime-specific warm pools managed by host agents/control plane |
| pod-per-tool execution | runtime-tier execution via WASM, Firecracker, or GUI agents |
| platform-core orchestrator | control plane + tool registry + runtime router |

Keep this file only for migration conversations or for understanding why earlier notes mention CRDs and warm pods.
