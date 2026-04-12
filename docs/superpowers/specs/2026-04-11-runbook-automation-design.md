# Design: Runbook Automation Scripts

| Field       | Value                          |
|-------------|-------------------------------|
| Date        | 2026-04-11                    |
| Status      | Approved                      |
| Location    | `tools/runbook/`              |

---

## Goal

Automate the two Firecracker runbooks into modular scripts so a developer can
set up, test, and tear down a local sandbox environment with single commands,
without installing anything to the system except the listed prerequisites.

---

## Files

```
tools/runbook/
  macos.sh          # sim mode — macOS dev workflow
  linux.sh          # fc-agent real + platform-api sim — Linux workflow
  bin/              # gitignored — mc downloaded here at runtime
  .state/           # gitignored — PID files and runtime state
```

Both `bin/` and `.state/` are never committed. A `.gitignore` is placed inside
`tools/runbook/` to exclude them.

---

## Subcommand Interface

Both scripts expose an identical interface:

```bash
./macos.sh <subcommand> [options]
./linux.sh <subcommand> [options]

Subcommands:
  setup      Start infra, upload snapshot, start platform-api (background)
  test       Hit POST /sessions + POST /execute, assert output
  teardown   Stop services, docker compose down, remove .state/
  status     Print running state of each component — read-only

Options:
  --snapshot-name NAME    Snapshot name            (default: python-v1)
  --minio-endpoint URL    MinIO endpoint            (default: http://localhost:9000)
  --api-url URL           platform-api base URL     (default: http://localhost:8080)
  --no-nomad              Skip Nomad job deploy/stop
  --dry-run               Print commands, do not execute
  --purge                 teardown only: also delete MinIO snapshot and venv
```

`setup` is idempotent — re-running it skips steps already completed.
`teardown --purge` is the only destructive operation beyond stopping processes.

---

## System Prerequisites

The scripts check for these at startup and exit with a clear message if any
are missing. The user is responsible for installing them:

| Tool       | Required by    | Notes                                  |
|------------|---------------|----------------------------------------|
| `python3`  | both           | 3.12+                                  |
| `docker`   | both           | Docker Desktop (macOS) or Engine (Linux) |
| `uv`       | both           | fast Python package manager             |
| `nomad`    | both           | skipped if `--no-nomad`                |
| `jq`       | both           | JSON output formatting                 |
| `curl`     | both           | health polling and API test calls      |

### mc (MinIO client) — downloaded locally

`mc` is **not** installed to the system. On first run, each script downloads
the correct binary for the current OS + architecture to `tools/runbook/bin/mc`
and marks it executable. Subsequent runs reuse the cached binary.

- macOS arm64 → `https://dl.min.io/client/mc/release/darwin-arm64/mc`
- macOS x86_64 → `https://dl.min.io/client/mc/release/darwin-amd64/mc`
- Linux arm64 → `https://dl.min.io/client/mc/release/linux-arm64/mc`
- Linux x86_64 → `https://dl.min.io/client/mc/release/linux-amd64/mc`

All `mc` invocations in the scripts use `$RUNBOOK_DIR/bin/mc`, never relying
on system PATH.

---

## macos.sh — Subcommand Details

### setup (idempotent)

1. **Check prerequisites** — verify each system dep is in PATH; missing ones
   are listed and script exits non-zero.
2. **Download mc** — skip if `bin/mc` already exists.
3. **Install Python deps** — `uv pip install -e ".[dev]"` from `sandbox-worker/`;
   skip if `platform-api` is already present in the venv.
4. **Start infra** — `docker compose up -d` from `services/`; poll
   `docker compose ps` until all containers are healthy, max 60s.
5. **Upload dummy snapshot** — create gzip-zero `vmstate.bin` + `memory.bin`
   and write `meta.json`, then call `tools/snapshot-builder/upload-minio.sh`.
   Skip if objects already exist in MinIO.
6. **Start platform-api** — background process with `FC_MODE=sim`; PID saved
   to `.state/api.pid`. Poll `GET /health` until `{"status":"healthy"}`,
   max 30s.
7. **Deploy Nomad job** — generate and run the macOS override job from the
   runbook. Skip entirely if `--no-nomad`.

### test

1. Assert `GET /health` returns `{"status":"healthy"}` — fail fast if api is down.
2. `POST /sessions {"runtime":"microvm"}` → capture `session_id`.
3. `POST /execute {"session_id":…,"tool":"python_run","input":{"code":"print('hello from sandbox')"}}`.
4. Assert: `response.status == "completed"` AND `response.output` contains
   `"hello from Python"`.
5. Print `PASS` or `FAIL` with the actual vs expected diff on failure.

### teardown

1. Stop `platform-api` via `.state/api.pid` (SIGTERM, wait 5s, SIGKILL if needed).
2. Stop Nomad job if deployed (skip if `--no-nomad`).
3. `docker compose down` from `services/`.
4. `rm -rf tools/runbook/.state`.
5. If `--purge`: also delete MinIO snapshot objects and `sandbox-worker/.venv`.

### status

Print a table — no state changes:

```
Component       Status
─────────────── ──────────────────────
docker infra    running (5/5 healthy)
platform-api    running  pid=12345
nomad job       stopped
mc binary       cached
```

---

## linux.sh — Differences from macos.sh

linux.sh is identical to macos.sh except for the following:

### setup — additional checks

- Check for `firecracker` binary in PATH (warn if missing, do not exit —
  fc-agent auto-detects and falls back to sim if `/dev/kvm` is absent).
- Check `/dev/kvm` accessibility (warn if absent — fc-agent will use sim mode).

### setup — snapshot step

Call `tools/snapshot-builder/snapshot-builder.sh` with
`--skip-rootfs --skip-snapshot` to produce a dummy snapshot for MinIO.
Real rootfs/snapshot build requires a guest agent baked into the rootfs
(not yet available) so real-mode VM execution via platform-api is blocked
until that is implemented. This is noted in the script output.

### setup — platform-api

Start with `FC_MODE=sim` (not `real`). Starting with `FC_MODE=real` crashes
the process because `app.py` passes `storage=None` to `VMLifecycleManager`
which raises `RuntimeError` in real mode. This is a known limitation
documented in the Linux runbook.

### setup — additional step: fc-agent

After platform-api is healthy:

8. **Start fc-agent** with `FC_SNAPSHOT_BUCKET=python-v1`,
   `FC_MODE=real` (auto-detects KVM; falls back to sim if absent).
   PID saved to `.state/fc-agent.pid`.
   Poll `GET http://localhost:8081/health` until healthy, max 30s.

### teardown

Stop fc-agent from `.state/fc-agent.pid` before stopping docker infra.

### status

Add fc-agent row to the status table.

---

## State Directory

`.state/` lives at `tools/runbook/.state/` and is gitignored.

| File              | Written by       | Read by              |
|-------------------|-----------------|----------------------|
| `api.pid`         | setup            | teardown, status     |
| `fc-agent.pid`    | setup (linux)    | teardown, status     |
| `nomad-job.txt`   | setup            | teardown             |
| `snapshot-name`   | setup            | test, teardown       |

---

## Error Handling

- All scripts run with `set -euo pipefail`.
- Each step prints a clear `[step-name]` prefix and its result.
- Poll loops (health checks, docker healthy) print a dot per retry and a
  timeout error if the deadline is exceeded.
- If `setup` fails mid-way, it prints which step failed and suggests running
  `teardown` before retrying.
- `teardown` uses `|| true` on stop commands — it never exits non-zero from a
  missing PID or already-stopped process.

---

## Out of Scope

- Nomad cluster setup (user runs `nomad agent -dev` manually or via Makefile).
- Real-mode end-to-end execution via `platform-api` — blocked on `storage=None`
  fix and guest agent in rootfs.
- Installing system prerequisites (`python3`, `docker`, `uv`, `nomad`, `jq`, `curl`).
