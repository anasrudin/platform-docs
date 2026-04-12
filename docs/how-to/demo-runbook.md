# Demo Runbook — Sandbox Platform (GCP + real Firecracker)

| Field | Value |
|---|---|
| Audience | Demo presenter |
| Scope | End-to-end demo: Python execution, package install, multi-step workflow |
| Mode | `FC_MODE=real` — real Firecracker microVM, snapshot loaded from MinIO |
| GCP VM | n2-standard-4, `asia-southeast1-a`, single-node Nomad |
| Last updated | 2026-04-13 |

The demo runs on a GCP VM (`34.143.174.106`). Two services are live:

| Service | URL | Purpose |
|---|---|---|
| `platform-api` | `http://34.143.174.106:8080` | Full API: execute, sessions, packages, workflows |
| `interpreter` | `http://34.143.174.106:8090` | Minimal: just `POST /run` → code → output |

Both use real Firecracker microVMs — each request boots a VM from snapshot, runs code, returns output.

---

## Prerequisites (laptop)

| Tool | Check |
|---|---|
| `gcloud` | `gcloud version` |
| `curl` | `curl --version` |
| `jq` | `jq --version` |

```bash
brew install jq   # macOS if not already installed
```

---

## Deploy to GCP

### First time (provision infra + deploy app)

```bash
cd tools/runbook/gcp-jumphost-nomad

# 1. Fill in your project ID, public IP, and username
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
# edit terraform/terraform.tfvars

# 2. One command does everything
./deploy-from-jumphost.sh -auto-approve
```

### Tear down everything

```bash
cd tools/runbook/gcp-jumphost-nomad
./destroy-from-jumphost.sh -auto-approve
```

---

## URL Dashboard

| Dashboard | URL |
|-----------|-----|
| platform-api health | http://34.143.174.106:8080/health |
| interpreter health | http://34.143.174.106:8090/health |
| Nomad UI | http://34.143.174.106:4646 |
| Consul UI | http://34.143.174.106:8500/ui |
| Jaeger UI | http://34.143.174.106:16686 |
| MinIO Console | http://34.143.174.106:9001 (minioadmin / minioadmin) |

Set variables for all curl commands below:

```bash
API="http://34.143.174.106:8080"
INTERP="http://34.143.174.106:8090"
```

---

## Scenario 0 — Minimal interpreter (quickest demo)

Simplest possible demo — just POST code, get output:

```bash
curl -s -X POST ${INTERP}/run \
  -H "Content-Type: application/json" \
  -d '{"language":"python","code":"import sys\nprint(f\"Python {sys.version}\")\nprint(2**10)"}' | jq
```

Expected:

```json
{
  "stdout": "Python 3.11.15 (main, Apr  7 2026, 02:25:39) [GCC 12.2.0]\n1024\n",
  "stderr": "",
  "exit_code": 0,
  "duration_ms": 217,
  "runtime": "firecracker"
}
```

Bash also works:

```bash
curl -s -X POST ${INTERP}/run \
  -H "Content-Type: application/json" \
  -d '{"language":"bash","code":"echo hello && uname -r"}' | jq
```

Expected:

```json
{
  "stdout": "hello\n5.10.245+\n",
  "stderr": "",
  "exit_code": 0,
  "duration_ms": 181,
  "runtime": "firecracker"
}
```

---

## Scenario 1 — Health check

**Purpose:** confirm real Firecracker VM pool is ready.

```bash
curl -s ${API}/health | jq
```

Expected:

```json
{
  "status": "healthy",
  "version": "0.2.0",
  "mode": "real",
  "pool_available": 1,
  "services": {
    "vm_pool": "healthy (ready=1/1)"
  }
}
```

---

## Scenario 2 — Execute Python via the sandbox API

```bash
curl -s -X POST ${API}/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "python_run",
    "input": {
      "code": "import sys; print(\"hello from Firecracker!\"); print(\"python\", sys.version.split()[0]); print(2**10)"
    }
  }' | jq
```

Expected:

```json
{
  "job_id": "...",
  "session_id": "...",
  "status": "completed",
  "output": "{\"stdout\": \"hello from Firecracker!\\npython 3.11.15\\n1024\\n\", \"stderr\": \"\", \"exit_code\": 0}",
  "error_message": "",
  "duration_ms": 217
}
```

Bash tool:

```bash
curl -s -X POST ${API}/execute \
  -H "Content-Type: application/json" \
  -d '{"tool":"bash_run","input":{"command":"echo hello && uname -r"}}' \
  | jq '.status, .duration_ms'
```

---

## Scenario 3 — Install a Python package

**Purpose:** demonstrate the package cache — first install downloads, second is a cache hit.

```bash
curl -s -X POST ${API}/packages/install \
  -H "Content-Type: application/json" \
  -d '{"package_name": "requests", "version": "2.31.0"}' | jq
```

Expected (first ever install — downloads from PyPI):

```json
{
  "name": "requests",
  "version": "2.31.0",
  "key": "requests/2.31.0",
  "status": "installed"
}
```

If already cached (e.g. re-running the demo), first call also returns `"cached"`.

Run again — cache hit:

```bash
curl -s -X POST ${API}/packages/install \
  -H "Content-Type: application/json" \
  -d '{"package_name": "requests", "version": "2.31.0"}' | jq '.status'
# "cached"
```

List all:

```bash
curl -s ${API}/packages | jq
```

Expected:

```json
{
  "packages": [
    {
      "name": "requests",
      "version": "2.31.0",
      "key": "requests/2.31.0",
      "status": "installed"
    }
  ],
  "count": 1
}
```

---

## Scenario 4 — Session-based execution

**Purpose:** create a named session and group executions under it for tracking.

> **Important:** Sessions currently provide ID grouping and lifecycle tracking — not in-memory state persistence. Each `POST /execute` request gets a **fresh VM from the pool**. Variables set in one call are **not visible** in the next. Hibernate/restore (stateful sessions) is a planned feature — currently disabled (`HIBERNATE_ENABLED=false`).

### Step 1 — Create a session

```bash
SESSION=$(curl -s -X POST ${API}/sessions \
  -H "Content-Type: application/json" \
  -d '{}')
echo "$SESSION" | jq
SESSION_ID=$(echo "$SESSION" | jq -r '.session_id')
echo "Session ID: $SESSION_ID"
```

Expected:

```json
{
  "session_id": "ses_abc123...",
  "runtime": "wasm",
  "status": "active",
  "snapshot_mode": "clean"
}
```

### Step 2 — Execute with the session ID

Tag executions to the session for correlation in logs and traces:

```bash
curl -s -X POST ${API}/execute \
  -H "Content-Type: application/json" \
  -d "{
    \"tool\": \"python_run\",
    \"session_id\": \"${SESSION_ID}\",
    \"input\": { \"code\": \"x = 42\nprint('set x =', x)\" }
  }" | jq '{session_id: .session_id, status: .status, output: .output}'
```

Expected:

```json
{
  "session_id": "ses_abc123...",
  "status": "completed",
  "output": "{\"stdout\": \"set x = 42\\n\", \"stderr\": \"\", \"exit_code\": 0}"
}
```

### Step 3 — State does NOT persist between calls

Each execute gets a fresh VM — variables from the previous call are gone:

```bash
curl -s -X POST ${API}/execute \
  -H "Content-Type: application/json" \
  -d "{
    \"tool\": \"python_run\",
    \"session_id\": \"${SESSION_ID}\",
    \"input\": { \"code\": \"print('x is:', x)\" }
  }" | jq '{status, output}'
```

Expected — `status` is `"completed"` (the VM agent ran successfully), but `output` contains `exit_code: 1` and the NameError in `stderr`:

```json
{
  "status": "completed",
  "output": "{\"stdout\": \"\", \"stderr\": \"Traceback (most recent call last):\\n  File \\\"<string>\\\", line 1, in <module>\\nNameError: name 'x' is not defined\\n\", \"exit_code\": 1}"
}
```

> `status` reflects whether the **VM agent** completed (always `"completed"`). Python errors appear inside `output.stderr` with `exit_code: 1`. `error_message` is only set on VM/service failures.

The `session_id` still appears on both responses — useful for grouping traces in Jaeger.

### Step 4 — Hibernate/restore (roadmap)

These endpoints exist but return an error until enabled:

```bash
curl -s -X POST ${API}/sessions/${SESSION_ID}/hibernate | jq
# {"detail": "Hibernation not enabled (HIBERNATE_ENABLED=false)"}

curl -s -X POST ${API}/sessions/${SESSION_ID}/restore | jq
# {"detail": "Hibernation not enabled (HIBERNATE_ENABLED=false)"}
```

When `HIBERNATE_ENABLED=true` is set, hibernate will checkpoint the VM to MinIO and restore will resume it — giving true stateful sessions across requests.

### What sessions give you today

| Feature | Status |
|---|---|
| Unique `session_id` for grouping | ✅ Works |
| Tag executions for log/trace correlation | ✅ Works |
| View traces grouped by session in Jaeger | ✅ Works |
| Variable state persisted across calls | ❌ Not yet (fresh VM each time) |
| Hibernate → restore checkpoint | ❌ Disabled (`HIBERNATE_ENABLED=false`) |

---

## Scenario 5 — Multi-step workflow (DAG)

**Purpose:** steps with dependencies, parallel execution.

> **Note:** Execution is **synchronous** — the entire DAG runs before `POST /workflows` returns (~600–900 ms for 3 real FC boots). By the time you see the response, all steps are already done. The `GET` at the end just shows the results — no polling needed.

```bash
WF=$(curl -s -X POST ${API}/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "name": "demo-pipeline",
    "steps": [
      {
        "id": "step_a",
        "tool": "python_run",
        "input": { "code": "import sys; print(\"step A:\", sys.version.split()[0])" }
      },
      {
        "id": "step_b",
        "tool": "bash_run",
        "input": { "command": "echo step B: $(uname -r)" }
      },
      {
        "id": "step_c",
        "tool": "python_run",
        "depends_on": ["step_a", "step_b"],
        "input": { "code": "print(\"step C: all done\")" }
      }
    ]
  }')
echo "$WF" | jq
```

Expected — POST returns only the ID (workflow already running synchronously):

```json
{
  "workflow_id": "wf-3f2a1b..."
}
```

Fetch the full result:

```bash
WORKFLOW_ID=$(echo "$WF" | jq -r '.workflow_id')
curl -s ${API}/workflows/${WORKFLOW_ID} | jq '{status, steps: (.steps | to_entries | map({(.key): .value.status}) | add)}'
```

Expected:

```json
{
  "status": "completed",
  "steps": {
    "step_a": "completed",
    "step_b": "completed",
    "step_c": "completed"
  }
}
```

To see each step's stdout output:

```bash
curl -s ${API}/workflows/${WORKFLOW_ID} | jq '.steps | to_entries[] | {step: .key, status: .value.status, stdout: (.value.output.output | fromjson | .stdout)}'
```

> Note: `.output.output` is a JSON string (double-encoded from the guest agent) — `| fromjson` unpacks it to get the actual stdout.

Expected:

```json
{ "step": "step_a", "status": "completed", "stdout": "step A: 3.11.15\n" }
{ "step": "step_b", "status": "completed", "stdout": "step B: 5.10.245+\n" }
{ "step": "step_c", "status": "completed", "stdout": "step C: all done\n" }
```

> `step_c` depends on both `step_a` and `step_b` — the DAG runs wave 1 (step_a + step_b in parallel), then wave 2 (step_c) only after both complete.

Open Jaeger at http://34.143.174.106:16686 to view traces grouped by workflow.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Health `degraded`, `pool_available: 0` | Snapshot not in MinIO or FC warmup failed | SSH to nomad VM: `nomad alloc logs <alloc-id>` |
| `503` on execute | VM pool empty | Wait for warmup or check MinIO has `platform-snapshots/python-v1/` |
| Health `"warming_up"` | Pool still loading snapshot | Wait ~5s and retry |
| Firewall blocked | Laptop IP changed | Update `admin_cidr` in `terraform.tfvars` and redeploy |
| Nomad job not running | Job stopped | SSH to VM: `nomad job run /tmp/platform-api.nomad` |
| `status: failed` on execute | App error | SSH to VM: `nomad alloc logs $(nomad job allocs platform-api \| awk 'NR==2{print $1}')` |

---

## Re-deploy app only (infra already exists)

Sync code + restart Nomad job without touching Terraform:

```bash
# From your laptop
gcloud compute ssh --project=e2b-infra-489707 --zone=asia-southeast1-a nomad --command='
  cd /home/annas/platform-docs/sandbox-worker
  /home/annas/fc-agent-venv/bin/pip install -e "." -q
  NOMAD_ADDR=http://127.0.0.1:4646 nomad job stop -purge platform-api 2>/dev/null || true
  sleep 1
  NOMAD_ADDR=http://127.0.0.1:4646 nomad job run /tmp/platform-api.nomad
'
```

---

## Related

- [deploy-from-jumphost.sh](../../tools/runbook/gcp-jumphost-nomad/deploy-from-jumphost.sh) — full deploy via jumphost
- [destroy-from-jumphost.sh](../../tools/runbook/gcp-jumphost-nomad/destroy-from-jumphost.sh) — tear down via jumphost
- [interpreter.py](../../sandbox-worker/src/api/interpreter.py) — minimal code interpreter service
- [firecracker-runbook-linux.md](./firecracker-runbook-linux.md) — setup Firecracker from scratch on Linux
