# Product Context

## Problem

AI agents need to execute arbitrary tools (code execution, browser automation, file processing) in a safe, isolated environment. Without proper sandboxing:

- Untrusted code can escape and damage host systems
- No resource limits leads to runaway processes
- No isolation means data leakage between tenants
- Cold start latency destroys agent performance

## Solution

A multi-engine sandbox platform that provides:

- **Three runtime tiers** optimized for different workload types
- **Warm pool system** for sub-100ms startup
- **Per-sandbox isolation** (network, filesystem, process)
- **Auto tool discovery** so agents find and use tools automatically

## Users

| User | Interaction |
|---|---|
| AI Agent Orchestrator | Calls `POST /v1/execute` with tool name + input |
| Platform Engineers | Deploy tools, manage infra, monitor health |
| Tool Developers | Build tools with `manifest.json`, push to registry |

## Success Criteria

- WASM execution < 20ms P50
- Firecracker execution < 80ms P50 (from warm pool)
- GUI screenshot < 5s P99
- Zero sandbox escapes
- Agent can discover and use any registered tool automatically
