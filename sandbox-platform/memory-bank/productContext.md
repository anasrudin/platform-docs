# Product Context

## Why This Platform Exists
AI agents (Claude, GPT-based agents, etc.) frequently need to run code to complete tasks — data analysis, web scraping, document automation. Without isolated execution, this is dangerous: arbitrary code could access the host filesystem, internal network, or credentials.

## User Journey
```
Agent submits POST /v1/execute
  → API validates JWT + rate limit
  → Job queued in Redis (async — agent doesn't wait)
  → Agent polls GET /v1/job/:id for result
  → Scheduler routes job to least-loaded node
  → Node agent dispatches to correct runtime tier
  → Runtime executes tool → result saved to Redis
  → Agent gets result + optional MinIO presigned URL for files
```

## Execution Tiers

| Tier | Runtime | When to Use | Example Tools |
|------|---------|-------------|---------------|
| `wasm` | Wasmtime | Pure computation, < 20ms | html_parse, json_parse |
| `microvm` | Firecracker | Code with I/O, < 5 min | python_run, bash_run |
| `gui` | Docker+Xvfb | Needs a display | browser_open, excel_edit |

## Expected Behaviour
- Submit job → get `job_id` immediately (< 100ms)
- Poll `/v1/job/:id` until `completed` or `failed`
- On failure: clear error message in `error_message`
- On success: output stored in Redis, large files in MinIO with presigned URL

## Rate Limits (per agent per minute)
- wasm: 100 req/min
- microvm: 20 req/min
- gui: 5 req/min

## Capacity (per node, ~32 vCPU / 128GB RAM)

| Runtime | Capacity |
|---------|----------|
| WASM | ~10,000 exec/sec |
| MicroVM | ~1,000 concurrent VMs |
| GUI | ~20 concurrent containers |

## Scale Path
- 2 nodes → MVP / dev
- 10 nodes → ~100k executions/sec (WASM)
- Add nodes with `--node-id nodeN` — scheduler discovers automatically
