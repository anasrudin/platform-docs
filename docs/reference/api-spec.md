# API Specification

| Field | Value |
|---|---|
| Status | Active |
| Audience | Contributors, integrators, reviewers |
| Scope | Current local HTTP API surface exposed by `platform-api` |
| Last updated | March 11, 2026 |

## Executive summary

The current API surface is intentionally small. It exposes three endpoints for health checks, session creation, and tool execution. The current implementation is a local MVP API, not a finalized public contract.

## Base URL and conventions

| Item | Value |
|---|---|
| Local base URL | `http://localhost:8080` |
| Content type | `application/json` |
| Authentication | Not implemented in the current local API |
| Version string | Returned by `GET /health` as `0.1.0-local` |

## API surface

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Returns service health for the API dependencies |
| `POST` | `/sessions` | Creates an execution session for a runtime tier |
| `POST` | `/execute` | Executes a tool, optionally creating a session automatically |

## `GET /health`

Returns the health status of the local API and its backing services.

### Success response

`200 OK` when all dependencies are healthy.

```json
{
  "status": "healthy",
  "version": "0.1.0-local",
  "services": {
    "postgres": "healthy",
    "redis": "healthy"
  }
}
```

### Degraded response

`503 Service Unavailable` when one or more dependencies are unhealthy.

```json
{
  "status": "degraded",
  "version": "0.1.0-local",
  "services": {
    "postgres": "healthy",
    "redis": "unhealthy: dial tcp 127.0.0.1:6379: connect: connection refused"
  }
}
```

## `POST /sessions`

Creates a new session. If no runtime is provided, the API defaults to `wasm`.

### Request body

| Field | Type | Required | Notes |
|---|---|---|---|
| `runtime` | string | No | Allowed values in current code are `wasm`, `microvm`, `gui` |

### Example request

```json
{
  "runtime": "microvm"
}
```

### Success response

`200 OK`

```json
{
  "session_id": "sess_123",
  "runtime": "microvm",
  "status": "active"
}
```

### Error cases

| Status | Condition |
|---|---|
| `400` | Invalid JSON body |
| `405` | Method other than `POST` |
| `500` | Session creation or schema initialization failure |

## `POST /execute`

Creates a job, routes it to the runtime selected for the tool, waits for the result, then returns the execution outcome.

If `session_id` is omitted, the API auto-creates a session based on runtime resolution for the requested tool.

### Request body

| Field | Type | Required | Notes |
|---|---|---|---|
| `session_id` | string | No | If omitted, the API creates a session automatically |
| `tool` | string | Yes | Used for routing and queue selection |
| `input` | object | No | Arbitrary JSON object passed to the runtime |

### Example request with explicit session

```json
{
  "session_id": "sess_123",
  "tool": "python_run",
  "input": {
    "code": "print(\"hello\")"
  }
}
```

### Example request with automatic session creation

```json
{
  "tool": "browser_open",
  "input": {
    "url": "https://example.com"
  }
}
```

### Success response

`200 OK`

```json
{
  "job_id": "job_123",
  "status": "completed",
  "output": "Hello from Firecracker on Nomad!\n",
  "duration_ms": 312
}
```

### Failed execution response

The endpoint still returns `200 OK` when the request is valid but the runtime execution fails. The failure is represented in the response body.

```json
{
  "job_id": "job_123",
  "status": "failed",
  "error_message": "wait result: context deadline exceeded",
  "duration_ms": 30000
}
```

### Error cases

| Status | Condition |
|---|---|
| `400` | Invalid JSON body |
| `400` | Missing `tool` |
| `404` | `session_id` was provided but no matching session exists |
| `405` | Method other than `POST` |
| `500` | Session creation or job persistence failure |

## Runtime resolution behavior

The current router resolves tools to runtime tiers through in-process routing rules.

| Behavior | Current implementation |
|---|---|
| Known tool | Uses the configured runtime rule |
| Unknown tool | Defaults to `wasm` |
| Queueing | Pushes the job to Redis-backed queues |
| Result wait | Blocks for up to 30 seconds waiting for the runtime result |

## Example usage

### Health check

```bash
curl -s http://localhost:8080/health | jq
```

### Create a session

```bash
curl -s -X POST http://localhost:8080/sessions \
  -H "Content-Type: application/json" \
  -d '{"runtime":"microvm"}' | jq
```

### Execute a tool

```bash
curl -s -X POST http://localhost:8080/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "browser_open",
    "input": {
      "url": "https://example.com"
    }
  }' | jq
```

## Notes and limitations

- The API is currently local-first and not versioned under `/v1`.
- Authentication and authorization are not yet implemented.
- The tool registry is still evolving; routing behavior will become more metadata-driven over time.
- This specification documents the current code behavior, not a final external API contract.
