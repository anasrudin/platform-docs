# System Patterns

## Architecture Pattern: Multi-Engine Sandbox

The platform follows a **3-layer architecture**:

```
Control Plane  →  Orchestration (Nomad)  →  Runtime Layer (3 pools)
```

All business logic in Control Plane. Nomad only does placement. Host agents manage local runtime.

## Key Patterns

### 1. Adapter Pattern (Runtime Routing)

Control Plane uses adapters to abstract runtime differences:

```
RuntimeRouter → WASMAdapter  → wasm-host-agent
             → FCAdapter    → fc-host-agent
             → GUIAdapter   → gui-host-agent
```

Each adapter translates a generic `JobRequest` into runtime-specific instructions.

### 2. Warm Pool Pattern

Pre-allocated runtime instances ready for immediate use:

| Runtime | Strategy | Target |
|---|---|---|
| WASM | Preloaded module instances | < 1ms acquire |
| Firecracker | Snapshot-restored microVMs | < 50ms acquire |
| GUI | Pre-booted Chromium sessions | ~300ms acquire |

Pool auto-scales based on queue depth and usage.

### 3. Overlay Filesystem Pattern

```
Read-only base image (shared)
   + Per-sandbox writable overlay
   = Clean, deterministic execution
```

After job completes: delete overlay, base image untouched.

### 4. TAP Network Isolation Pattern

Each sandbox gets its own TAP device → Linux bridge → iptables policy → NAT.

```
VM → tap{N} → bridge0 → iptables (allowlist) → NAT → Internet
```

Cleanup: delete TAP, remove iptables rules, remove tc qdisc.

### 5. Skill-Based Tool Discovery

```
Agent task → Skill resolver → Tool selector → Runtime router → Execute
```

Skills map abstract capabilities to concrete tools with fallback chains.

### 6. Execution Recording

Every job produces an immutable execution record (stored in MinIO) that enables deterministic replay.

## Anti-Patterns (Forbidden)

| Anti-Pattern | Reason |
|---|---|
| Business logic in Nomad | Nomad is scheduler only |
| Shared filesystem across sandboxes | Security violation |
| Direct internet access from WASM | WASM is offline/restricted |
| Global mutable state | Breaks multi-tenancy |
| `panic()` in production code | Use error returns |
