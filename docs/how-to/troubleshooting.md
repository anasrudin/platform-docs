# Troubleshooting

| Field | Value |
|---|---|
| Status | Active |
| Audience | Contributors, operators |
| Scope | Common errors, root causes, and fixes |
| Last updated | April 8, 2026 |

---

## Install and setup

### `ModuleNotFoundError: No module named 'sandbox_platform'`

**Cause:** The package is not installed, or you are outside the virtual environment.

**Fix:**

```bash
cd sandbox-platform
source .venv/bin/activate
pip install -e ".[dev]"
```

If the error persists after reinstalling, stale `.egg-info` directories may be causing a conflict:

```bash
find . -name "*.egg-info" -type d | xargs rm -rf
pip install -e ".[dev]"
```

---

### `ModuleNotFoundError: No module named 'cmd'` (unexpected)

**Cause:** A module is trying to import from a package named `cmd`, which conflicts with the Python standard library module of the same name.

**Fix:** The entry-point package is named `platform_cmd`, not `cmd`. Check that no `sys.path` manipulation is accidentally adding a `cmd/` directory to the Python path.

---

### `pip install` fails with `ERROR: No matching distribution found`

**Cause:** Python version mismatch (< 3.12) or network issue.

**Fix:**

```bash
python3 --version    # must be 3.12+
```

If version is correct, check network access to PyPI. In a restricted environment, set a proxy:

```bash
pip install -e ".[dev]" --proxy http://proxy.corp:3128
```

---

## Startup

### `platform-api: could not connect to server` (PostgreSQL)

**Cause:** PostgreSQL container is not running or not yet ready.

**Fix:**

```bash
docker compose ps           # check if postgres is up
docker compose logs postgres
make dev                    # restarts infra
```

Wait 5–10 seconds after `make dev` for PostgreSQL to accept connections.

---

### `redis.exceptions.ConnectionError: Error connecting to localhost:6379`

**Cause:** Redis is not running.

**Fix:**

```bash
docker compose up -d redis
```

---

### `GET /health` returns `503`

**Cause:** One or more backing services (PostgreSQL, Redis) are unhealthy.

**Fix:** Check the `services` field in the response body to identify which service is failing, then follow the relevant steps above.

---

### `fc-agent` exits immediately with `vsock unavailable`

**Cause:** Running on macOS. vsock requires Linux kernel support.

**Fix:** This is expected. The agent automatically falls back to simulation mode. To confirm:

```bash
FC_MODE=sim fc-agent
```

---

## Execution

### `POST /execute` returns `{"status": "failed", "error_message": "context deadline exceeded"}`

**Cause:** The runtime agent did not return a result within 30 seconds. Usually means:

- The agent is not running.
- The job was pushed to the wrong queue.
- The Firecracker VM failed to start.

**Fix:**

1. Confirm the agent is running: `curl -s http://localhost:8081/health`
2. Check agent logs for errors.
3. On macOS, confirm `FC_MODE` is not forced to `real` (`FC_MODE=real` requires KVM).

---

### `POST /execute` returns `404` for `session_id`

**Cause:** The session ID does not exist in PostgreSQL. Possible causes: session was never created, or the platform-api restarted and the in-memory state was lost.

**Fix:** Create a new session first:

```bash
curl -s -X POST http://localhost:8080/sessions \
  -H "Content-Type: application/json" \
  -d '{"runtime": "microvm"}' | jq
```

Use the returned `session_id` in subsequent execute calls.

---

## Artifacts

### `GET /artifacts/{id}/{name}` returns `404`

**Cause:** MinIO is not running, or the artifact key does not exist.

**Fix:**

1. Verify MinIO is up: `curl -s http://localhost:9000/minio/health/live`
2. Check that the `artifact_id` and `name` match exactly what was returned by `POST /artifacts`.
3. The artifact path format is `{artifact_id}/{name}` — both segments are required.

---

### Artifact URLs point to `localhost:9000` but MinIO is on a different host

**Cause:** `MINIO_ENDPOINT` defaults to `http://localhost:9000`. The URL returned by `POST /artifacts` reflects this.

**Fix:** Set `MINIO_ENDPOINT` to the correct address before starting:

```bash
MINIO_ENDPOINT=http://minio.internal:9000 platform-api
```

---

## Packages

### `POST /packages/install` returns `500` with `mc not found`

**Cause:** The MinIO Client CLI (`mc`) is not installed. Required for real-mode package caching.

**Fix:** For development, use the local directory fallback:

```bash
PACKAGES_LOCAL_DIR=/tmp/platform-packages platform-api
```

Or install `mc`:

```bash
brew install minio/stable/mc   # macOS
```

---

### Package proxy does not work

**Cause:** Known bug — `proxy_url` is currently passed as `--index-url` instead of `--proxy` in the `pip download` command. This replaces the package index rather than routing through the proxy.

**Workaround:** Set the proxy at the environment level instead:

```bash
https_proxy=http://proxy.corp:3128 platform-api
```

---

## Consul

### Agents do not appear in Consul after starting with `CONSUL_ENABLED=true`

**Cause:** Consul agent is not running, or `CONSUL_HOST`/`CONSUL_PORT` point to the wrong address.

**Fix:**

```bash
consul agent -dev                   # start a local dev agent
CONSUL_HOST=127.0.0.1 CONSUL_ENABLED=true fc-agent
curl -s http://localhost:8500/v1/agent/services | jq
```

---

### `consul deregister failed` in agent shutdown logs

**Cause:** Consul became unreachable while the agent was trying to deregister on SIGTERM.

**Impact:** Low — Consul automatically deregisters the service after the `DeregisterCriticalServiceAfter` interval (default: 1 minute) once health checks start failing.

---

## mTLS

### All requests return `403` after enabling `MTLS_ENABLED=true`

**Cause:** `MTLSMiddleware` is rejecting requests that lack a client certificate. This is the expected behavior. If you did not intend to enforce mTLS, stop the server and restart without the flag.

**Fix for legitimate clients:** The client must present a certificate signed by the CA at `MTLS_CA_FILE`.

```bash
curl --cert client.crt --key client.key --cacert ca.crt \
  https://localhost:8080/health
```

---

### `ssl.SSLError: [SSL] PEM lib` on startup

**Cause:** Certificate files are missing or malformed. The platform will not start if `MTLS_ENABLED=true` and the cert files are not readable.

**Fix:** Verify that `MTLS_CERT_FILE`, `MTLS_KEY_FILE`, and `MTLS_CA_FILE` all point to valid PEM files:

```bash
openssl x509 -in /etc/sandbox/certs/server.crt -noout -subject
openssl rsa -in /etc/sandbox/certs/server.key -check -noout
```

---

## Tests

### Tests fail with `ImportError` after renaming a module

**Cause:** Stale `.egg-info` directory caches old module paths.

**Fix:**

```bash
find . -name "*.egg-info" -type d | xargs rm -rf
pip install -e ".[dev]"
pytest
```

---

### `pytest` passes locally but fails in CI with coverage gate

**Cause:** A new module was added without corresponding tests, dropping overall coverage below 95%.

**Fix:** Write tests for the new module. Check which lines are uncovered:

```bash
pytest --cov=sandbox_platform --cov-report=term-missing
```

---

## Related documents

- [run-locally.md](./run-locally.md)
- [../reference/api-spec.md](../reference/api-spec.md)
- [../process/release-notes.md](../process/release-notes.md)
