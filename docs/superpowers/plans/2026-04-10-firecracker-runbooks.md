# Firecracker Runbook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write two standalone developer runbooks — one for macOS (sim mode) and one for Linux+KVM (real mode) — covering repo setup, infra start, Firecracker snapshot build, Nomad deployment, and end-to-end Python execution via the platform API.

**Architecture:** Two independent Markdown files under `docs/how-to/`. Each file is a complete runbook with no cross-references. macOS uses `FC_MODE=sim` (no KVM, mock snapshots). Linux uses real Firecracker with `/dev/kvm`. Both files follow the same section structure.

**Tech Stack:** Python 3.12+, FastAPI, Firecracker, Nomad, MinIO, Docker Compose, uv

---

## File Map

| Action | Path |
|--------|------|
| Create | `docs/how-to/firecracker-runbook-macos.md` |
| Create | `docs/how-to/firecracker-runbook-linux.md` |

### Codebase references (read before writing, do not modify)

| Path | Why |
|------|-----|
| `sandbox-worker/Makefile` | `make install`, `make dev`, `make stop`, `make infra-up` targets |
| `sandbox-worker/pyproject.toml` | Entry points: `fc-agent`, `platform-api`, `wasm-agent` |
| `sandbox-worker/src/runtime/firecracker.py` | `detect_mode()`, `SnapshotStore`, `Config` env vars |
| `sandbox-worker/src/service/execution.py` | `ExecutionService.execute()` request/response shape |
| `sandbox-worker/src/api/routes/session.py` | `POST /sessions` body/response |
| `sandbox-worker/src/api/routes/execute.py` | `POST /execute` body/response |
| `services/docker-compose.yml` | Root compose — starts MinIO, Postgres, Redis |
| `services/data/docker-compose.yml` | MinIO port 9000, creds minioadmin/minioadmin |
| `services/controller/nomad/jobs/sandbox-worker.nomad` | Production Nomad job spec |
| `services/controller/nomad/jobs/debug-python-runtime.nomad` | Dev-mode job with `FC_MODE=sim`, `raw_exec` |

---

## Task 1: Write macOS runbook — Prerequisites, Install, Infra

**Files:**
- Create: `docs/how-to/firecracker-runbook-macos.md` (sections 1–3)

- [ ] **Step 1: Create the file with sections 1–3**

Write exactly this content to `docs/how-to/firecracker-runbook-macos.md`:

```markdown
# Firecracker Runbook — macOS (Sim Mode)

| Field | Value |
|---|---|
| Platform | macOS (Apple Silicon or Intel) |
| Firecracker mode | `sim` — no KVM required, mock VM output |
| Last updated | 2026-04-10 |

This runbook covers: repo setup → infrastructure → build a Firecracker snapshot (mock) → load an existing snapshot → deploy a Nomad job → run Python code via the platform API.

---

## 1. Prerequisites

Install these before starting:

```bash
# Python 3.12+
python3 --version   # must print 3.12.x or later

# Docker Desktop (includes docker compose v2)
docker --version
docker compose version

# uv — fast Python package installer
pip install uv

# jq — JSON pretty-printer for curl responses
brew install jq

# Nomad CLI
brew tap hashicorp/tap
brew install hashicorp/tap/nomad
nomad version   # must print Nomad v1.x

# MinIO client mc (needed to upload snapshot files)
brew install minio/stable/mc
```

**Not needed on macOS:** firecracker binary, KVM, jailer.

---

## 2. Clone and install

```bash
git clone <repo-url>
cd platform-docs/sandbox-worker

python3 -m venv .venv
source .venv/bin/activate

uv pip install -e ".[dev]"
```

Verify:

```bash
fc-agent --help      # prints uvicorn help
platform-api --help  # prints uvicorn help
pytest --collect-only | tail -5   # must show collected tests, no errors
```

Troubleshoot: if `fc-agent: command not found`, ensure the venv is activated (`source .venv/bin/activate`).

---

## 3. Start infrastructure

Run from the `services/` directory:

```bash
cd ../services
docker compose up -d
```

Verify all three services are healthy:

```bash
docker compose ps
```

Expected — all three show `healthy`:

```
NAME        STATUS
minio       Up (healthy)
postgres    Up (healthy)
redis       Up (healthy)
```

Start the platform API (in a separate terminal, from `sandbox-worker/`):

```bash
cd sandbox-worker
source .venv/bin/activate
FC_MODE=sim \
  MINIO_ENDPOINT=http://localhost:9000 \
  MINIO_ACCESS_KEY=minioadmin \
  MINIO_SECRET_KEY=minioadmin \
  platform-api
```

Verify health:

```bash
curl -s http://localhost:8080/health | jq
```

Expected:

```json
{
  "status": "healthy",
  "version": "0.1.0-local"
}
```

Troubleshoot: if MinIO is unreachable, confirm Docker Desktop is running and `docker compose ps` shows port `9000->9000`.
```

- [ ] **Step 2: Verify sections 1–3 are in the file**

```bash
grep -c "^## " docs/how-to/firecracker-runbook-macos.md
```

Expected output: `3`

- [ ] **Step 3: Commit**

```bash
git add docs/how-to/firecracker-runbook-macos.md
git commit -m "docs: start macOS Firecracker runbook (prereqs, install, infra)"
```

---

## Task 2: Write macOS runbook — Build snapshot, Load snapshot

**Files:**
- Modify: `docs/how-to/firecracker-runbook-macos.md` (append sections 4–5)

- [ ] **Step 1: Append sections 4–5 to the macOS runbook**

Append this content to `docs/how-to/firecracker-runbook-macos.md`:

```markdown
---

## 4. Build a snapshot from scratch (sim mode)

In sim mode there is no real VM. A "snapshot" is three files uploaded to MinIO:
- `vmstate.bin` — dummy binary (placeholder for VM state)
- `memory.bin` — dummy binary (placeholder for VM memory)
- `meta.json` — JSON metadata the fc-agent reads on startup

**4a. Create the MinIO bucket**

```bash
mc alias set local http://localhost:9000 minioadmin minioadmin
mc mb local/platform-snapshots --ignore-existing
```

Expected: `Bucket created successfully` or `Bucket already exists`.

**4b. Create the snapshot files locally**

```bash
mkdir -p /tmp/python-v1

# Dummy binaries (real Firecracker would write actual VM state here)
dd if=/dev/zero bs=1k count=4 2>/dev/null | gzip > /tmp/python-v1/vmstate.bin
dd if=/dev/zero bs=1k count=4 2>/dev/null | gzip > /tmp/python-v1/memory.bin

# Metadata that fc-agent reads
cat > /tmp/python-v1/meta.json <<'EOF'
{
  "name": "python-v1",
  "version": "3.12",
  "kernel": "vmlinux-5.10",
  "rootfs": "python-v1.ext4",
  "vcpus": 2,
  "mem_mib": 512,
  "dry_run": true
}
EOF
```

**4c. Upload the snapshot to MinIO**

```bash
mc cp /tmp/python-v1/vmstate.bin local/platform-snapshots/python-v1/vmstate.bin
mc cp /tmp/python-v1/memory.bin  local/platform-snapshots/python-v1/memory.bin
mc cp /tmp/python-v1/meta.json   local/platform-snapshots/python-v1/meta.json
```

Verify upload:

```bash
mc ls local/platform-snapshots/python-v1/
```

Expected (three objects):

```
[...] 4.0 KiB vmstate.bin
[...] 4.0 KiB memory.bin
[...] 155 B   meta.json
```

Troubleshoot: if `mc` alias fails, check MinIO is up (`docker compose ps`) and credentials match `minioadmin`/`minioadmin`.

---

## 5. Load an existing snapshot from MinIO

`SnapshotStore.ensure()` downloads from MinIO to a local cache on first access, then serves from disk on subsequent requests.

**5a. Set cache dir and trigger a download**

```bash
export SNAPSHOT_CACHE_DIR=/tmp/sandbox-cache
export SNAPSHOT_NAME=python-v1
export MINIO_ENDPOINT=http://localhost:9000
export MINIO_ACCESS_KEY=minioadmin
export MINIO_SECRET_KEY=minioadmin
export MINIO_BUCKET=platform-snapshots
```

**5b. Verify the download works via fc-agent startup**

Start fc-agent in sim mode (new terminal):

```bash
cd sandbox-worker
source .venv/bin/activate
FC_MODE=sim \
  SNAPSHOT_NAME=python-v1 \
  SNAPSHOT_CACHE_DIR=/tmp/sandbox-cache \
  MINIO_ENDPOINT=http://localhost:9000 \
  MINIO_ACCESS_KEY=minioadmin \
  MINIO_SECRET_KEY=minioadmin \
  MINIO_BUCKET=platform-snapshots \
  fc-agent
```

Expected log line on startup (structlog JSON or console):

```
snapshot not cached, downloading from MinIO  name=python-v1
```

On second start:

```
snapshot cache hit  name=python-v1
```

**5c. Verify local cache**

```bash
ls /tmp/sandbox-cache/python-v1/
```

Expected:

```
memory.bin  meta.json  vmstate.bin
```

Troubleshoot: if download fails with "mc not found in PATH", the SnapshotStore falls back to HTTP download from MinIO. Ensure `MINIO_ENDPOINT` is reachable.
```

- [ ] **Step 2: Verify sections 4–5 are present**

```bash
grep -c "^## " docs/how-to/firecracker-runbook-macos.md
```

Expected: `5`

- [ ] **Step 3: Commit**

```bash
git add docs/how-to/firecracker-runbook-macos.md
git commit -m "docs: add snapshot build and load sections to macOS runbook"
```

---

## Task 3: Write macOS runbook — Nomad deploy, run Python, cleanup

**Files:**
- Modify: `docs/how-to/firecracker-runbook-macos.md` (append sections 6–8)

- [ ] **Step 1: Append sections 6–8 to the macOS runbook**

Append this content to `docs/how-to/firecracker-runbook-macos.md`:

```markdown
---

## 6. Deploy the Nomad job

**6a. Start a local single-node Nomad cluster**

In a new terminal:

```bash
sudo nomad agent -dev \
  -bind=0.0.0.0 \
  -network-interface=lo0
```

Wait for: `Nomad agent started! ...` in the output.

Verify Nomad is up:

```bash
nomad node status
```

Expected: one node with status `ready`.

**6b. Run the debug job (sim mode)**

From the repo root:

```bash
nomad job run services/controller/nomad/jobs/debug-python-runtime.nomad
```

Expected:

```
==> Monitoring evaluation "..."
    Evaluation triggered by job "debug-python-runtime"
    Allocation "..." created: node "...", group "firecracker"
    Evaluation status changed: "pending" -> "complete"
==> Evaluation complete
```

**6c. Verify the allocation is running**

```bash
nomad job status debug-python-runtime
```

Expected — `Status = running` and one allocation in `running` state.

Check fc-agent logs inside the allocation:

```bash
nomad alloc logs <alloc-id> fc-agent
```

Expected log line: `FC mode from FC_MODE env  mode=sim`

Troubleshoot: if the allocation shows `failed`, check that `fc-agent` is on PATH inside the Nomad environment. The job uses `raw_exec` driver with `command = "/usr/local/bin/fc-agent"` — verify the binary is there or adjust the path in the job file to your venv path (e.g. `/Users/<you>/platform-docs/sandbox-worker/.venv/bin/fc-agent`).

---

## 7. Run Python code end-to-end

**7a. Create a session**

```bash
SESSION=$(curl -s -X POST http://localhost:8080/sessions \
  -H "Content-Type: application/json" \
  -d '{"runtime": "microvm"}' | jq -r '.session_id')
echo "Session: $SESSION"
```

Expected: `Session: sess_<uuid>`

**7b. Execute Python code**

```bash
curl -s -X POST http://localhost:8080/execute \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION\",
    \"tool\": \"python_run\",
    \"input\": {\"code\": \"print('hello from sandbox')\"}
  }" | jq
```

Expected response (sim mode returns mock output):

```json
{
  "job_id": "...",
  "session_id": "...",
  "status": "completed",
  "output": "hello from sandbox\n",
  "error_message": null,
  "duration_ms": 5
}
```

Note: in sim mode `output` is mock. The real guest agent inside the VM is not invoked — `FC_MODE=sim` returns simulated results from the runtime layer.

**7c. Execute Python with an import**

```bash
curl -s -X POST http://localhost:8080/execute \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION\",
    \"tool\": \"python_run\",
    \"input\": {\"code\": \"import json; print(json.dumps({'x': 42}))\"}
  }" | jq '.output'
```

Expected: `"{\"x\": 42}\n"`

---

## 8. Cleanup

Stop services:

```bash
# Stop Nomad job
nomad job stop debug-python-runtime

# Stop platform-api and fc-agent (Ctrl+C in each terminal, or:)
pkill -f "platform-api"
pkill -f "fc-agent"

# Stop infra
cd services
docker compose down
```

Remove local snapshot cache:

```bash
rm -rf /tmp/sandbox-cache /tmp/python-v1
```

Remove MinIO snapshot:

```bash
mc rm --recursive --force local/platform-snapshots/python-v1
```
```

- [ ] **Step 2: Verify the file has 8 sections**

```bash
grep -c "^## " docs/how-to/firecracker-runbook-macos.md
```

Expected: `8`

- [ ] **Step 3: Commit**

```bash
git add docs/how-to/firecracker-runbook-macos.md
git commit -m "docs: complete macOS Firecracker runbook (Nomad, execute, cleanup)"
```

---

## Task 4: Write Linux runbook — Prerequisites, KVM check, Install, Infra

**Files:**
- Create: `docs/how-to/firecracker-runbook-linux.md` (sections 1–3)

- [ ] **Step 1: Create the file with sections 1–3**

Write exactly this content to `docs/how-to/firecracker-runbook-linux.md`:

```markdown
# Firecracker Runbook — Linux + KVM (Real Mode)

| Field | Value |
|---|---|
| Platform | Linux (Debian/Ubuntu recommended), KVM enabled |
| Firecracker mode | `real` — actual microVM execution |
| Last updated | 2026-04-10 |

This runbook covers: KVM verification → repo setup → infrastructure → build a real Firecracker snapshot → upload to MinIO → load from MinIO → deploy a Nomad job → run Python code via the platform API.

---

## 1. Prerequisites

**Verify KVM is available:**

```bash
ls -la /dev/kvm
# must exist and be accessible (crw-rw---- or crw-rw-rw-)

# If permission denied:
sudo usermod -aG kvm $USER
newgrp kvm
```

**Install system packages:**

```bash
sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv python3-pip \
  curl jq build-essential
```

**Install Docker + Docker Compose v2:**

Follow https://docs.docker.com/engine/install/ubuntu/ then:

```bash
docker --version         # Docker 24+
docker compose version   # v2.x
```

**Install uv:**

```bash
pip install uv
```

**Install Nomad:**

```bash
wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt-get update && sudo apt-get install -y nomad
nomad version   # Nomad v1.x
```

**Install Firecracker + jailer:**

```bash
FC_VERSION=v1.7.0
ARCH=$(uname -m)
curl -L -o /tmp/firecracker.tgz \
  "https://github.com/firecracker-microvm/firecracker/releases/download/${FC_VERSION}/firecracker-${FC_VERSION}-${ARCH}.tgz"
tar -xzf /tmp/firecracker.tgz -C /tmp
sudo install /tmp/release-${FC_VERSION}-${ARCH}/firecracker-${FC_VERSION}-${ARCH} /usr/local/bin/firecracker
sudo install /tmp/release-${FC_VERSION}-${ARCH}/jailer-${FC_VERSION}-${ARCH} /usr/local/bin/jailer
firecracker --version   # Firecracker v1.7.0
```

**Install MinIO client mc:**

```bash
curl -L https://dl.min.io/client/mc/release/linux-amd64/mc -o /tmp/mc
sudo install /tmp/mc /usr/local/bin/mc
mc --version
```

---

## 2. Clone and install

```bash
git clone <repo-url>
cd platform-docs/sandbox-worker

python3.12 -m venv .venv
source .venv/bin/activate

uv pip install -e ".[dev]"
```

Verify:

```bash
fc-agent --help      # prints uvicorn help
platform-api --help  # prints uvicorn help
pytest --collect-only | tail -5
```

---

## 3. Start infrastructure

Run from `services/`:

```bash
cd ../services
docker compose up -d
```

Verify:

```bash
docker compose ps
```

Expected — all three show `healthy`:

```
NAME        STATUS
minio       Up (healthy)
postgres    Up (healthy)
redis       Up (healthy)
```

Start the platform API (new terminal, from `sandbox-worker/`):

```bash
cd sandbox-worker
source .venv/bin/activate
FC_MODE=real \
  MINIO_ENDPOINT=http://localhost:9000 \
  MINIO_ACCESS_KEY=minioadmin \
  MINIO_SECRET_KEY=minioadmin \
  platform-api
```

Verify health:

```bash
curl -s http://localhost:8080/health | jq
```

Expected:

```json
{
  "status": "healthy",
  "version": "0.1.0-local"
}
```
```

- [ ] **Step 2: Verify sections 1–3 are in the file**

```bash
grep -c "^## " docs/how-to/firecracker-runbook-linux.md
```

Expected: `3`

- [ ] **Step 3: Commit**

```bash
git add docs/how-to/firecracker-runbook-linux.md
git commit -m "docs: start Linux+KVM Firecracker runbook (prereqs, KVM, install, infra)"
```

---

## Task 5: Write Linux runbook — Build real snapshot and upload to MinIO

**Files:**
- Modify: `docs/how-to/firecracker-runbook-linux.md` (append sections 4–5)

- [ ] **Step 1: Append sections 4–5**

Append this content to `docs/how-to/firecracker-runbook-linux.md`:

```markdown
---

## 4. Build a Firecracker snapshot from scratch

A real Firecracker snapshot captures full VM state: kernel, rootfs, memory, and CPU registers.

**4a. Download kernel and rootfs**

```bash
mkdir -p /tmp/fc-assets

# Minimal kernel (Firecracker-optimized)
curl -fL -o /tmp/fc-assets/vmlinux \
  "https://s3.amazonaws.com/spec.ccfc.min/img/quickstart_guide/x86_64/kernels/vmlinux.bin"

# Minimal rootfs with Python 3.12 pre-installed
# Replace with your own rootfs image if available
curl -fL -o /tmp/fc-assets/rootfs.ext4 \
  "https://s3.amazonaws.com/spec.ccfc.min/img/quickstart_guide/x86_64/rootfs/bionic.rootfs.ext4"
```

> If you have a custom Python rootfs, replace `rootfs.ext4` with your image path.

**4b. Start Firecracker via the API socket**

```bash
# Create socket path
FC_SOCKET=/tmp/fc-$(date +%s).sock

# Start Firecracker in background (no VM yet — API only)
firecracker --api-sock $FC_SOCKET &
FC_PID=$!
echo "Firecracker PID: $FC_PID"

# Give it a moment to start
sleep 1
```

**4c. Configure the VM via Firecracker API**

```bash
# Set kernel
curl -s -X PUT "unix://${FC_SOCKET}::http://localhost/boot-source" \
  -H "Content-Type: application/json" \
  -d "{
    \"kernel_image_path\": \"/tmp/fc-assets/vmlinux\",
    \"boot_args\": \"console=ttyS0 reboot=k panic=1 pci=off\"
  }" --unix-socket $FC_SOCKET

# Set rootfs
curl -s -X PUT "unix://${FC_SOCKET}::http://localhost/drives/rootfs" \
  -H "Content-Type: application/json" \
  -d "{
    \"drive_id\": \"rootfs\",
    \"path_on_host\": \"/tmp/fc-assets/rootfs.ext4\",
    \"is_root_device\": true,
    \"is_read_only\": false
  }" --unix-socket $FC_SOCKET

# Set machine config
curl -s -X PUT "unix://${FC_SOCKET}::http://localhost/machine-config" \
  -H "Content-Type: application/json" \
  -d '{
    "vcpu_count": 2,
    "mem_size_mib": 512
  }' --unix-socket $FC_SOCKET
```

**4d. Start the VM**

```bash
curl -s -X PUT "unix://${FC_SOCKET}::http://localhost/actions" \
  -H "Content-Type: application/json" \
  -d '{"action_type": "InstanceStart"}' \
  --unix-socket $FC_SOCKET
```

Wait ~2 seconds for boot.

**4e. Create the snapshot**

```bash
mkdir -p /tmp/python-v1

curl -s -X PUT "unix://${FC_SOCKET}::http://localhost/snapshot/create" \
  -H "Content-Type: application/json" \
  -d "{
    \"snapshot_type\": \"Full\",
    \"snapshot_path\": \"/tmp/python-v1/vmstate.bin\",
    \"mem_file_path\": \"/tmp/python-v1/memory.bin\"
  }" --unix-socket $FC_SOCKET
```

Expected: empty `{}` response (HTTP 204 means success).

**4f. Write metadata**

```bash
cat > /tmp/python-v1/meta.json <<'EOF'
{
  "name": "python-v1",
  "version": "3.12",
  "kernel": "vmlinux-5.10",
  "rootfs": "python-v1.ext4",
  "vcpus": 2,
  "mem_mib": 512,
  "dry_run": false
}
EOF
```

**4g. Stop Firecracker**

```bash
kill $FC_PID
wait $FC_PID 2>/dev/null
```

Verify snapshot files:

```bash
ls -lh /tmp/python-v1/
```

Expected (sizes will vary — vmstate.bin and memory.bin should be non-zero):

```
-rw-r--r-- 1 user user  512M memory.bin
-rw-r--r-- 1 user user  2.1M vmstate.bin
-rw-r--r-- 1 user user  155B meta.json
```

Troubleshoot: if `InstanceStart` fails with socket errors, ensure `/dev/kvm` is accessible by your user (`ls -la /dev/kvm`, add to `kvm` group if needed).

---

## 5. Upload snapshot to MinIO and verify load

**5a. Create the MinIO bucket and upload**

```bash
mc alias set local http://localhost:9000 minioadmin minioadmin
mc mb local/platform-snapshots --ignore-existing

mc cp /tmp/python-v1/vmstate.bin local/platform-snapshots/python-v1/vmstate.bin
mc cp /tmp/python-v1/memory.bin  local/platform-snapshots/python-v1/memory.bin
mc cp /tmp/python-v1/meta.json   local/platform-snapshots/python-v1/meta.json
```

Verify:

```bash
mc ls local/platform-snapshots/python-v1/
```

Expected (three objects, non-zero sizes):

```
[...] 512MiB memory.bin
[...] 2.1MiB vmstate.bin
[...]  155 B meta.json
```

**5b. Test snapshot load via fc-agent**

Clear local cache first to force a download:

```bash
rm -rf /tmp/sandbox-cache
```

Start fc-agent (new terminal):

```bash
cd sandbox-worker
source .venv/bin/activate
FC_MODE=real \
  SNAPSHOT_NAME=python-v1 \
  SNAPSHOT_CACHE_DIR=/tmp/sandbox-cache \
  MINIO_ENDPOINT=http://localhost:9000 \
  MINIO_ACCESS_KEY=minioadmin \
  MINIO_SECRET_KEY=minioadmin \
  MINIO_BUCKET=platform-snapshots \
  fc-agent
```

Expected log line on first start:

```
snapshot not cached, downloading from MinIO  name=python-v1
```

Verify local cache:

```bash
ls /tmp/sandbox-cache/python-v1/
# memory.bin  meta.json  vmstate.bin
```

Troubleshoot: if download is slow, `mc mirror` is used first, falling back to HTTP download from `MINIO_ENDPOINT`.
```

- [ ] **Step 2: Verify sections 4–5 are present**

```bash
grep -c "^## " docs/how-to/firecracker-runbook-linux.md
```

Expected: `5`

- [ ] **Step 3: Commit**

```bash
git add docs/how-to/firecracker-runbook-linux.md
git commit -m "docs: add real Firecracker snapshot build and MinIO upload to Linux runbook"
```

---

## Task 6: Write Linux runbook — Nomad deploy, run Python, cleanup

**Files:**
- Modify: `docs/how-to/firecracker-runbook-linux.md` (append sections 6–8)

- [ ] **Step 1: Append sections 6–8**

Append this content to `docs/how-to/firecracker-runbook-linux.md`:

```markdown
---

## 6. Deploy the Nomad job

**6a. Start a local single-node Nomad cluster**

In a new terminal:

```bash
sudo nomad agent -dev \
  -bind=0.0.0.0 \
  -network-interface=eth0   # replace eth0 with your network interface
```

Wait for: `Nomad agent started!` in output.

Verify:

```bash
nomad node status
```

Expected: one node with status `ready`.

**6b. Adjust the Nomad job for local dev**

The production job at `services/controller/nomad/jobs/sandbox-worker.nomad` uses Docker driver and assumes a container registry. For local dev with a real binary, create a local override file:

```bash
cat > /tmp/sandbox-worker-local.nomad <<'EOF'
job "sandbox-worker-local" {
  datacenters = ["dc1"]
  type        = "service"

  group "fc-agent" {
    count = 1

    task "fc-agent" {
      driver = "raw_exec"

      config {
        command = "/path/to/sandbox-worker/.venv/bin/fc-agent"
      }

      env {
        FC_MODE            = "real"
        SNAPSHOT_NAME      = "python-v1"
        SNAPSHOT_CACHE_DIR = "/tmp/sandbox-cache"
        MINIO_ENDPOINT     = "http://127.0.0.1:9000"
        MINIO_ACCESS_KEY   = "minioadmin"
        MINIO_SECRET_KEY   = "minioadmin"
        MINIO_BUCKET       = "platform-snapshots"
      }

      resources {
        cpu    = 2000
        memory = 4096
      }
    }
  }
}
EOF
```

Replace `/path/to/sandbox-worker` with the actual absolute path:

```bash
sed -i "s|/path/to/sandbox-worker|$(pwd)|g" /tmp/sandbox-worker-local.nomad
```

**6c. Run the job**

```bash
nomad job run /tmp/sandbox-worker-local.nomad
```

Expected:

```
==> Monitoring evaluation "..."
    Allocation "..." created: node "...", group "fc-agent"
    Evaluation status changed: "pending" -> "complete"
==> Evaluation complete
```

**6d. Verify allocation is running**

```bash
nomad job status sandbox-worker-local
```

Expected: `Status = running`.

Check logs:

```bash
ALLOC_ID=$(nomad job status sandbox-worker-local | grep running | awk '{print $1}')
nomad alloc logs $ALLOC_ID fc-agent
```

Expected log line: `FC mode from FC_MODE env  mode=real`

Troubleshoot: if allocation shows `failed` with permission error on `/dev/kvm`, add your user to the `kvm` group and restart Nomad: `sudo usermod -aG kvm $USER && newgrp kvm`.

---

## 7. Run Python code end-to-end

**7a. Create a session**

```bash
SESSION=$(curl -s -X POST http://localhost:8080/sessions \
  -H "Content-Type: application/json" \
  -d '{"runtime": "microvm"}' | jq -r '.session_id')
echo "Session: $SESSION"
```

Expected: `Session: sess_<uuid>`

**7b. Execute Python code**

```bash
curl -s -X POST http://localhost:8080/execute \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION\",
    \"tool\": \"python_run\",
    \"input\": {\"code\": \"print('hello from real VM')\"}
  }" | jq
```

Expected (real VM execution):

```json
{
  "job_id": "...",
  "session_id": "...",
  "status": "completed",
  "output": "hello from real VM\n",
  "error_message": null,
  "duration_ms": 45
}
```

Note: `duration_ms` will be higher than sim mode (20–80ms typical for snapshot-restore boot).

**7c. Execute Python with computation**

```bash
curl -s -X POST http://localhost:8080/execute \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION\",
    \"tool\": \"python_run\",
    \"input\": {\"code\": \"result = sum(range(1000000)); print(f'Sum: {result}')\"}
  }" | jq '.output'
```

Expected: `"Sum: 499999500000\n"`

**7d. Execute with snapshot_mode=continuous (optional)**

Continuous mode saves the VM state after each execution — subsequent runs restore from the previous state, preserving installed packages and variables.

```bash
curl -s -X POST http://localhost:8080/execute \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION\",
    \"tool\": \"python_run\",
    \"snapshot_mode\": \"continuous\",
    \"input\": {\"code\": \"x = 42; print(f'x={x}')\"}
  }" | jq
```

---

## 8. Cleanup

Stop Nomad job:

```bash
nomad job stop sandbox-worker-local
```

Stop platform-api (Ctrl+C in the terminal running it, or):

```bash
pkill -f "platform-api"
```

Stop infrastructure:

```bash
cd services
docker compose down
```

Remove local snapshot cache:

```bash
rm -rf /tmp/sandbox-cache /tmp/python-v1 /tmp/fc-assets
```

Remove MinIO snapshot:

```bash
mc rm --recursive --force local/platform-snapshots/python-v1
```

Stop Nomad dev agent (Ctrl+C or):

```bash
sudo pkill nomad
```
```

- [ ] **Step 2: Verify the file has 8 sections**

```bash
grep -c "^## " docs/how-to/firecracker-runbook-linux.md
```

Expected: `8`

- [ ] **Step 3: Commit**

```bash
git add docs/how-to/firecracker-runbook-linux.md
git commit -m "docs: complete Linux+KVM Firecracker runbook (Nomad, execute, cleanup)"
```

---

## Task 7: Accuracy verification

**Files:**
- Read: `sandbox-worker/src/runtime/firecracker.py` — verify env var names
- Read: `sandbox-worker/src/service/execution.py` — verify request/response shape
- Read: `services/data/docker-compose.yml` — verify MinIO creds/port

- [ ] **Step 1: Verify env var names match `Config` class in firecracker.py**

```bash
grep "_env_or\|_env_int" sandbox-worker/src/runtime/firecracker.py | head -15
```

Cross-check each env var used in both runbooks against this output:

| Runbook env var | Config class key | Match? |
|---|---|---|
| `FC_MODE` | `os.environ.get("FC_MODE")` in `detect_mode()` | ✓ |
| `SNAPSHOT_NAME` | `_env_or("SNAPSHOT_NAME", ...)` | ✓ |
| `SNAPSHOT_CACHE_DIR` | `_env_or("SNAPSHOT_CACHE_DIR", ...)` | ✓ |
| `MINIO_ENDPOINT` | `_env_or("MINIO_ENDPOINT", ...)` | ✓ |
| `MINIO_ACCESS_KEY` | `_env_or("MINIO_ACCESS_KEY", ...)` | ✓ |
| `MINIO_SECRET_KEY` | `_env_or("MINIO_SECRET_KEY", ...)` | ✓ |
| `MINIO_BUCKET` | `_env_or("MINIO_BUCKET", ...)` | ✓ |

If any name is wrong, update the runbook file that uses it.

- [ ] **Step 2: Verify API request/response shape**

```bash
grep -n "session_id\|tool\|input\|output\|status\|job_id" \
  sandbox-worker/src/service/execution.py
```

Confirm the runbooks use the correct fields in curl requests and expected responses.

- [ ] **Step 3: Verify MinIO credentials match docker-compose**

```bash
grep "MINIO_ROOT\|ports" services/data/docker-compose.yml
```

Confirm: `minioadmin`/`minioadmin`, port `9000`.

- [ ] **Step 4: Commit if any corrections were made**

```bash
git add docs/how-to/
git commit -m "docs: fix accuracy issues in Firecracker runbooks" \
  || echo "No corrections needed"
```

---

## Self-review notes

**Spec coverage check:**

| Spec requirement | Covered in plan |
|---|---|
| macOS sim mode | Task 1–3 |
| Linux+KVM real mode | Task 4–6 |
| Build snapshot from scratch | Task 2 (macOS), Task 5 (Linux) |
| Load existing snapshot from MinIO | Task 2 (macOS), Task 5 (Linux) |
| Deploy Nomad job | Task 3 (macOS), Task 6 (Linux) |
| End-to-end Python execution via API | Task 3 §7 (macOS), Task 6 §7 (Linux) |
| Cleanup | Task 3 §8 (macOS), Task 6 §8 (Linux) |
| Two separate files | ✓ — Task 1+3 = macOS, Task 4+6 = Linux |

**Known constraints documented in runbooks:**
- macOS sim: Nomad `raw_exec` binary path must match actual venv path
- Linux: `/dev/kvm` group membership required
- Both: `docker compose up -d` must be run from `services/` directory
- Both: MinIO bucket creation is idempotent (`--ignore-existing`)
