# API Specification

| Field | Value |
|---|---|
| Status | Active |
| Audience | Contributors, integrators, reviewers |
| Scope | Full HTTP API surface exposed by `platform-api` |
| Last updated | April 8, 2026 |

## Executive summary

The platform exposes an HTTP API for session management, tool execution, artifact storage, and package management. This is a local MVP API. Authentication and versioning are not yet implemented.

## Base URL and conventions

| Item | Value |
|---|---|
| Local base URL | `http://localhost:8080` |
| Content type | `application/json` (except artifact upload which uses `multipart/form-data`) |
| Authentication | Not implemented |
| Version string | Returned by `GET /health` as `0.1.0-local` |

## API surface

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Service health and dependency status |
| `POST` | `/sessions` | Create an execution session |
| `POST` | `/execute` | Execute a tool in a session |
| `POST` | `/artifacts` | Upload an artifact |
| `GET` | `/artifacts/{artifact_id}/{name}` | Download an artifact |
| `POST` | `/packages/install` | Install and cache a pip package |
| `GET` | `/packages` | List all cached packages |
| `DELETE` | `/packages/{name}` | Remove a cached package |

---

## `GET /health`

Returns the health status of the API and its backing services.

### Success response

`200 OK` — all dependencies healthy.

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

`503 Service Unavailable` — one or more dependencies unhealthy.

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

---

## `POST /sessions`

Creates a new execution session for a runtime tier.

### Request body

| Field | Type | Required | Notes |
|---|---|---|---|
| `runtime` | string | No | `wasm`, `microvm`, or `gui`. Defaults to `wasm`. |

### Example

```json
{ "runtime": "microvm" }
```

### Response `200 OK`

```json
{
  "session_id": "sess_abc123",
  "runtime": "microvm",
  "status": "active"
}
```

### Error cases

| Status | Condition |
|---|---|
| `400` | Invalid JSON body |
| `500` | Session creation or schema initialization failure |

---

## `POST /execute`

Submits a tool execution request. Waits up to 30 seconds for a result.

If `session_id` is omitted, the API auto-creates a session based on the tool's routing rule.

### Request body

| Field | Type | Required | Notes |
|---|---|---|---|
| `session_id` | string | No | Omit to create automatically |
| `tool` | string | Yes | Determines runtime routing |
| `input` | object | No | Arbitrary JSON forwarded to the runtime |

### Example with explicit session

```json
{
  "session_id": "sess_abc123",
  "tool": "python_run",
  "input": { "code": "print('hello')" }
}
```

### Example with automatic session

```json
{
  "tool": "browser_open",
  "input": { "url": "https://example.com" }
}
```

### Response `200 OK` — completed

```json
{
  "job_id": "job_xyz789",
  "status": "completed",
  "output": "hello\n",
  "error_message": null,
  "duration_ms": 42
}
```

### Response `200 OK` — failed execution

The endpoint returns `200` even when the runtime fails. Failure is in the body.

```json
{
  "job_id": "job_xyz789",
  "status": "failed",
  "error_message": "context deadline exceeded",
  "duration_ms": 30000
}
```

### Error cases

| Status | Condition |
|---|---|
| `400` | Invalid JSON body |
| `400` | Missing `tool` field |
| `404` | `session_id` provided but no matching session exists |
| `500` | Job creation or queue failure |

---

## `POST /artifacts`

Uploads a file to the artifact store.

### Request format

`multipart/form-data`

### Form fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `file` | binary | Yes | The file to upload |
| `session_id` | string | No | Optional session association |
| `name` | string | No | Defaults to the filename or `artifact` |

### Response `200 OK`

```json
{
  "artifact_id": "4f9914c7-2f6d-4636-917c-03c7d987e61e",
  "key": "4f9914c7-2f6d-4636-917c-03c7d987e61e/output.txt",
  "url": "http://localhost:9000/platform-artifacts/4f9914c7-2f6d-4636-917c-03c7d987e61e/output.txt",
  "size": 128
}
```

### Error cases

| Status | Condition |
|---|---|
| `400` | Missing file field or invalid multipart body |
| `500` | Upload failure |

---

## `GET /artifacts/{artifact_id}/{name}`

Downloads an artifact by ID and filename.

### Path parameters

| Parameter | Description |
|---|---|
| `artifact_id` | UUID returned by `POST /artifacts` |
| `name` | Filename returned by `POST /artifacts` |

### Response

`200 OK` — body is the raw file bytes. Content-Type: `application/octet-stream`.

### Error cases

| Status | Condition |
|---|---|
| `404` | Artifact not found or download failure |

---

## `POST /packages/install`

Downloads a pip wheel, caches it in MinIO (or a local directory in dev mode), and returns metadata.

### Request body

| Field | Type | Required | Notes |
|---|---|---|---|
| `package_name` | string | Yes | PyPI package name |
| `version` | string | No | e.g. `"1.26.0"`. Omit for latest. |
| `session_id` | string | No | Session to associate the install with |
| `proxy_url` | string | No | HTTP proxy for pip. Passed as `--proxy`. |
| `timeout_seconds` | integer | No | Default: 60 |
| `extra_dependencies` | array of strings | No | Additional packages to include |

### Example

```json
{
  "session_id": "sess_abc123",
  "package_name": "numpy",
  "version": "1.26.0"
}
```

### Response `200 OK`

```json
{
  "name": "numpy",
  "version": "1.26.0",
  "key": "numpy/1.26.0",
  "status": "installed"
}
```

`status` is `"cached"` when the wheel already exists for that package/version.

### Error cases

| Status | Condition |
|---|---|
| `500` | pip download failed or MinIO write error |

---

## `GET /packages`

Lists all cached packages.

### Response `200 OK`

```json
{
  "packages": [
    { "name": "numpy", "version": "1.26.0", "key": "numpy/1.26.0", "status": "installed" }
  ],
  "count": 1
}
```

---

## `DELETE /packages/{name}`

Removes a specific package version from the cache.

### Query parameters

| Parameter | Type | Notes |
|---|---|---|
| `version` | string | Version to delete. Omit to target `latest`. |

### Example

```bash
DELETE /packages/numpy?version=1.26.0
```

### Response `200 OK`

```json
{ "deleted": "numpy", "version": "1.26.0" }
```

### Error cases

| Status | Condition |
|---|---|
| `500` | Delete failure |

---

## Runtime routing behavior

| Behavior | Details |
|---|---|
| Known tool | Routed to the configured runtime tier via `router/rules.py` |
| Unknown tool | Defaults to `wasm` |
| Queue | Jobs are pushed to Redis-backed queues per tier |
| Result wait | Blocks up to 30 seconds for the runtime result |

---

## Agent health endpoints

Each runtime agent exposes its own `/health` endpoint on a separate port:

| Agent | Default port | Response |
|---|---|---|
| `fc-agent` | `8081` | `{"status": "ok", "runtime": "firecracker", "pool_size": N}` |
| `wasm-agent` | `8082` | `{"status": "ok", "runtime": "wasm", "pool_size": N}` |
| `gui-agent` | `8083` | `{"status": "ok", "runtime": "gui", "pool_size": 0}` |

These are used by HAProxy and Consul for health checking. They are not part of the main API surface.

---

## Notes and current limitations

- The API is not versioned under `/v1`. This will change before the first external release.
- Authentication and authorization are not implemented.
- `PUT /packages/{name}` (update package) and `GET /packages/{name}` (single package info) are not yet implemented.
- Package install does not execute inside a Firecracker VM session; wheels are cached on the host only.
- Tool routing rules are in-process; a dedicated tool registry API is planned.
