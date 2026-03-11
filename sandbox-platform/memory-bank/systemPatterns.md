# System Patterns

## End-to-End Request Flow

```
POST /v1/execute
      │
      ▼
[middleware/auth.go]        JWT validation (nil key path = dev mode)
      │
      ▼
[middleware/ratelimit.go]   Redis Lua token bucket per agentID+tier
                            BUG FIX: tier read from c.Locals("tier")
                            which is set by the handler BEFORE this runs
      │
      ▼
[handler/execute.go]        Look up tool manifest → get tier
                            Set c.Locals("tier") for rate limiter
                            Marshal job → push to Redis list "jobs"
                            Return {"job_id":"..."} HTTP 202
      │
      ▼
[queue/consumer.go]         BLPop from "jobs" stream
      │
      ▼
[scheduler/scheduler.go]    Select least-loaded node
                            RPush job to "node:{nodeID}:jobs"
      │
      ▼
[cmd/node-agent/agent.go]   BLPop from "node:{nodeID}:jobs"
      │
      ▼
[cmd/node-agent/executor.go] Dispatch to RuntimeManager
      │
      ├─ TierWASM   → internal/runtime/wasm.Runtime.Execute()
      │               exec wasmtime {tool}.wasm -- {inputJSON}
      │
      ├─ TierMicroVM → internal/runtime/microvm.Runtime.Execute()
      │                Acquire VM from pool
      │                VM.Exec("/tool/{tool}", env={TOOL_INPUT: inputJSON})
      │                Release VM → pool replenishes async
      │
      └─ TierGUI    → internal/runtime/gui.Runtime.Execute()
                       Acquire container from pool
                       docker exec {containerID} /tool/{tool}
                       Release container → pool replenishes async
      │
      ▼
[executor.go]               Publish result to Redis: "job:result:{jobID}"
      │
      ▼
GET /v1/job/:id             Read "job:result:{jobID}" from Redis
                            Return status + optional MinIO presigned URL
```

## Node Registration Pattern

```
node-agent startup:
  HSET "node:{nodeID}" id, status="active", load=0, registered_at

heartbeat every 5s:
  HSET "node:{nodeID}" last_seen, load={currentLoad}

shutdown:
  HSET "node:{nodeID}" status="offline"
```

Scheduler scans `node:*` keys and filters `status == "active"`.

## Tool I/O Contract

```
input:  TOOL_INPUT environment variable = JSON string
output: stdout = JSON string with at minimum {"exit_code": N}
```

All tools must:
- Never write non-JSON to stdout
- Write errors to stderr (captured in result.Stderr)
- Exit 0 on success, non-zero on failure

## Dependency Graph (must not be reversed)

```
cmd/
 └── internal/api
 └── internal/queue
 └── internal/router
 └── internal/scheduler
 └── internal/runtime/{wasm,microvm,gui}
 └── internal/tool/registry
 └── internal/storage/object
 └── internal/telemetry
 └── pkg/types          ← shared, no internal imports
```

## Rate Limit Fix (Bug 1 from original)

**Wrong** (original): rate limiter tried to read tier from request body
inside middleware, but body was already consumed.

**Correct** (this codebase):
```
handler/execute.go:
  manifest, _ := h.tools.Get(req.Tool)
  c.Locals("tier", string(manifest.Tier))   ← set BEFORE next middleware

middleware/ratelimit.go:
  tier, _ := c.Locals("tier").(string)       ← read safely here
```

## Naming Conventions

| Entity | Format | Example |
|--------|--------|---------|
| VM socket | `/tmp/firecracker-{vmID}.sock` | `/tmp/firecracker-job-abc.sock` |
| VM pool ID | `pool-{N}` | `pool-3` |
| Job result | `job:result:{jobID}` | `job:result:550e8400` |
| Node queue | `node:{nodeID}:jobs` | `node:node-1:jobs` |
| Node state | `node:{nodeID}` | `node:node-1` |
| Rate limit | `ratelimit:{agentID}:{tier}` | |
| MinIO output | `jobs/{jobID}/output/result.json` | |
| WASM module | `{dataDir}/wasm-modules/{tool}.wasm` | |
| VM snapshot | `{dataDir}/snapshots/{name}/{state,mem}` | |
