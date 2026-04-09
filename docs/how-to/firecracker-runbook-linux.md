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
```

If permission denied, add your user to the `kvm` group and re-login:

```bash
sudo usermod -aG kvm $USER
newgrp kvm
ls -la /dev/kvm   # recheck
```

**Install system packages:**

```bash
sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv python3-pip \
  curl jq build-essential
```

**Install Docker + Docker Compose v2:**

Follow the official Docker docs for Ubuntu: https://docs.docker.com/engine/install/ubuntu/

Then verify:

```bash
docker --version          # Docker 24+
docker compose version    # v2.x
```

**Install uv:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv --version
```

**Install Nomad:**

```bash
wget -O- https://apt.releases.hashicorp.com/gpg | \
  sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \
  https://apt.releases.hashicorp.com $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt-get update && sudo apt-get install -y nomad
nomad version   # Nomad v1.x
```

**Install Firecracker + jailer:**

```bash
FC_VERSION=v1.7.0
ARCH=$(uname -m)
curl -fL -o /tmp/firecracker.tgz \
  "https://github.com/firecracker-microvm/firecracker/releases/download/${FC_VERSION}/firecracker-${FC_VERSION}-${ARCH}.tgz"
tar -xzf /tmp/firecracker.tgz -C /tmp
sudo install /tmp/release-${FC_VERSION}-${ARCH}/firecracker-${FC_VERSION}-${ARCH} \
  /usr/local/bin/firecracker
sudo install /tmp/release-${FC_VERSION}-${ARCH}/jailer-${FC_VERSION}-${ARCH} \
  /usr/local/bin/jailer
firecracker --version   # Firecracker v1.7.0
```

**Install MinIO client mc:**

```bash
ARCH=$(uname -m)
MC_ARCH=$([ "$ARCH" = "aarch64" ] && echo "arm64" || echo "amd64")
curl -fL "https://dl.min.io/client/mc/release/linux-${MC_ARCH}/mc" -o /tmp/mc
sudo install /tmp/mc /usr/local/bin/mc
mc --version
```

---

## 2. Clone and install

```bash
git clone <repo-url> platform-docs
cd platform-docs/sandbox-worker

uv venv .venv
source .venv/bin/activate

uv pip install -e ".[dev]"
```

Verify:

```bash
which platform-api   # confirm entry point is installed
pytest --collect-only -q 2>&1 | tail -10   # must show collected tests, no errors
```

Troubleshoot: if `platform-api: command not found`, ensure the venv is activated (`source .venv/bin/activate`).

---

## 3. Start infrastructure

Run from the `services/` directory:

```bash
cd ../services
docker compose up -d
```

> **Note:** Do not use `make infra-up` from `sandbox-worker/` — the Makefile target runs `docker compose up -d` relative to `sandbox-worker/` which has no compose file. Use the manual path above.

Verify all three services are healthy:

```bash
# Still in services/
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
  "version": "0.2.0",
  "services": {
    "vm_pool": "healthy (pool_size=N)"
  }
}
```
> The `pool_size` value reflects the `FC_POOL_SIZE` environment variable (default: `2`).

Troubleshoot: if MinIO is unreachable, confirm Docker is running and `docker compose ps` from `services/` shows port `9000->9000`.

---

## 4. Build a Firecracker snapshot from scratch

A real Firecracker snapshot captures full VM state: CPU registers, memory, and disk. Restoring from snapshot boots a VM in 20–80ms instead of a full kernel boot.

**4a. Download kernel and rootfs**

```bash
mkdir -p /tmp/fc-assets

# Firecracker-optimized kernel (x86_64)
curl -fL -o /tmp/fc-assets/vmlinux \
  "https://s3.amazonaws.com/spec.ccfc.min/img/quickstart_guide/x86_64/kernels/vmlinux.bin"

# Minimal rootfs (replace with a Python-preinstalled image for production use)
curl -fL -o /tmp/fc-assets/rootfs.ext4 \
  "https://s3.amazonaws.com/spec.ccfc.min/img/quickstart_guide/x86_64/rootfs/bionic.rootfs.ext4"
```

> These are Firecracker's public quickstart assets. For a Python runtime snapshot, use a rootfs with Python 3.12 pre-installed.

**4b. Start Firecracker via API socket**

```bash
FC_SOCKET=/tmp/fc-$(date +%s).sock

# Start Firecracker in background (no VM yet — API server only)
firecracker --api-sock $FC_SOCKET &
FC_PID=$!
echo "Firecracker PID: $FC_PID, socket: $FC_SOCKET"
sleep 1
```

**4c. Configure the VM via Firecracker API**

```bash
# Set kernel
curl -s -X PUT \
  --unix-socket $FC_SOCKET \
  "http://localhost/boot-source" \
  -H "Content-Type: application/json" \
  -d "{
    \"kernel_image_path\": \"/tmp/fc-assets/vmlinux\",
    \"boot_args\": \"console=ttyS0 reboot=k panic=1 pci=off init=/sbin/init\"
  }"

# Set rootfs
curl -s -X PUT \
  --unix-socket $FC_SOCKET \
  "http://localhost/drives/rootfs" \
  -H "Content-Type: application/json" \
  -d "{
    \"drive_id\": \"rootfs\",
    \"path_on_host\": \"/tmp/fc-assets/rootfs.ext4\",
    \"is_root_device\": true,
    \"is_read_only\": false
  }"

# Set machine config
curl -s -X PUT \
  --unix-socket $FC_SOCKET \
  "http://localhost/machine-config" \
  -H "Content-Type: application/json" \
  -d '{
    "vcpu_count": 2,
    "mem_size_mib": 512
  }'
```

Each command returns HTTP 204 No Content (curl prints nothing on success).

**4d. Start the VM**

```bash
curl -s -X PUT \
  --unix-socket $FC_SOCKET \
  "http://localhost/actions" \
  -H "Content-Type: application/json" \
  -d '{"action_type": "InstanceStart"}'
```

Expected: HTTP 204 No Content (curl prints nothing on success). Wait 2 seconds for the kernel to boot.

**4e. Create the snapshot**

```bash
mkdir -p /tmp/python-v1

curl -s -X PUT \
  --unix-socket $FC_SOCKET \
  "http://localhost/snapshot/create" \
  -H "Content-Type: application/json" \
  -d "{
    \"snapshot_type\": \"Full\",
    \"snapshot_path\": \"/tmp/python-v1/vmstate.bin\",
    \"mem_file_path\": \"/tmp/python-v1/memory.bin\"
  }"
```

Expected: HTTP 204 No Content (curl prints nothing on success).

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
  "created_at": "2026-04-10T00:00:00",
  "dry_run": false,
  "files": {}
}
EOF
```

**4g. Stop Firecracker**

```bash
kill $FC_PID
wait $FC_PID 2>/dev/null
echo "Firecracker stopped"
```

Verify snapshot files exist and are non-zero:

```bash
ls -lh /tmp/python-v1/
```

Expected (sizes vary — `memory.bin` ≈ 512MB, `vmstate.bin` a few MB):

```
-rw-r--r-- 1 user user 512M memory.bin
-rw-r--r-- 1 user user 2.1M vmstate.bin
-rw-r--r-- 1 user user 155B meta.json
```

Troubleshoot: if `InstanceStart` fails, verify `/dev/kvm` is accessible by your user (`ls -la /dev/kvm`) and your user is in the `kvm` group (`groups`).

---

## 5. Upload snapshot to MinIO and verify load

**5a. Create bucket and upload**

```bash
mc alias set local http://localhost:9000 minioadmin minioadmin
mc mb local/platform-snapshots || true

mc cp /tmp/python-v1/vmstate.bin local/platform-snapshots/python-v1/vmstate.bin
mc cp /tmp/python-v1/memory.bin  local/platform-snapshots/python-v1/memory.bin
mc cp /tmp/python-v1/meta.json   local/platform-snapshots/python-v1/meta.json
```

Verify upload:

```bash
mc ls local/platform-snapshots/python-v1/
```

Expected (three objects, non-zero sizes):

```
[...] 512MiB memory.bin
[...] 2.1MiB vmstate.bin
[...]   155B meta.json
```

**5b. Test snapshot load via fc-agent**

> **Known issue:** The `fc-agent` entry point currently fails to start because the `agents` package is not yet present in `src/`. Running `fc-agent` will produce `ModuleNotFoundError: No module named 'agents'`. Section 5 documents the intended workflow for when the package is available.

Clear local cache to force a download:

```bash
rm -rf /tmp/sandbox-cache
```

Start fc-agent (in a new terminal, from `sandbox-worker/`):

```bash
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

Expected log on first start:

```
snapshot not cached, downloading from MinIO  name=python-v1
```

**5c. Verify local cache**

```bash
ls /tmp/sandbox-cache/python-v1/
```

Expected:

```
memory.bin  meta.json  vmstate.bin
```

Troubleshoot: if download fails, `SnapshotStore` falls back from `mc mirror` to direct HTTP download from `MINIO_ENDPOINT`. Ensure MinIO is reachable at `http://localhost:9000`.

---

## 6. Deploy the Nomad job

**6a. Start a local single-node Nomad dev cluster**

In a new terminal:

```bash
sudo nomad agent -dev \
  -bind=0.0.0.0 \
  -network-interface=eth0   # replace with your network interface name
```

Find your interface name if unsure:

```bash
ip route get 1 | awk '{print $5; exit}'
```

Wait for `Nomad agent started!` in output, then verify:

```bash
nomad node status
```

Expected: one node with status `ready`.

**6b. Adjust the job for local dev**

The production job at `services/controller/nomad/jobs/sandbox-worker.nomad` uses Docker driver and a container registry. For local dev with a real binary, create a local override.

> Run from the repo root (`platform-docs/`), not from inside `sandbox-worker/`.

```bash
VENV_PATH=$(pwd)/sandbox-worker/.venv

cat > /tmp/sandbox-worker-linux.nomad <<EOF
job "sandbox-worker-linux" {
  datacenters = ["dc1"]
  type        = "service"

  group "fc-agent" {
    count = 1

    task "fc-agent" {
      driver = "raw_exec"

      config {
        command = "${VENV_PATH}/bin/fc-agent"
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

> **Known issue:** `fc-agent` currently fails to start (missing `agents` module — see section 5 warning). The Nomad allocation will show `failed`. This section documents the intended deployment workflow.

**6c. Run the job**

```bash
nomad job run /tmp/sandbox-worker-linux.nomad
```

Expected:

```
==> Monitoring evaluation "..."
    Allocation "..." created: node "...", group "fc-agent"
    Evaluation status changed: "pending" -> "complete"
==> Evaluation complete
```

**6d. Check allocation status**

```bash
nomad job status sandbox-worker-linux
```

Expected: `Status = running` (or `failed` if fc-agent module issue is not resolved).

View logs:

```bash
ALLOC_ID=$(nomad job status sandbox-worker-linux | awk '/^Allocations/{found=1; next} found && ($6=="running" || $6=="failed"){print $1; exit}')
nomad alloc logs $ALLOC_ID fc-agent
```

Troubleshoot: if `raw_exec` is disabled, it is enabled by default in `-dev` mode. If running with a real Nomad config, add `plugin "raw_exec" { config { enabled = true } }` to your Nomad agent config file. Also ensure `/dev/kvm` is accessible by the Nomad task user.

---

## 7. Run Python code end-to-end

> **Known issue:** `POST /execute` currently fails with HTTP 500 due to a code bug: `ExecutionService.execute()` calls `vm.run(job)` but `FirecrackerVM` only exposes `.execute(tool, input_data)`. The steps below document the intended workflow. To test the API layer without the VM, use `POST /sessions` and `GET /health` which do not invoke the VM pool.

> **Note:** `platform-api` runs its own in-process VM lifecycle manager in dev mode. It does not route requests through the Nomad-deployed fc-agent at runtime.

**7a. Ensure platform-api is running**

From section 3, `platform-api` should be running with `FC_MODE=real`. If not, restart it:

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
  platform-api
```

**7b. Create a session**

```bash
SESSION=$(curl -s -X POST http://localhost:8080/sessions \
  -H "Content-Type: application/json" \
  -d '{"runtime": "microvm"}' | jq -r '.session_id')
echo "Session: $SESSION"
```

Expected: `Session: <uuid>` (e.g. `3f7b2c1d-e4f5-...`)

> **Full response shape** (run `curl ... | jq` without the `.session_id` extract to see it):
> ```json
> {
>   "session_id": "3f7b2c1d-e4f5-...",
>   "runtime": "microvm",
>   "status": "active",
>   "snapshot_mode": "clean"
> }
> ```

**7c. Execute Python code**

```bash
curl -s -X POST http://localhost:8080/execute \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION\",
    \"tool\": \"python_run\",
    \"input\": {\"code\": \"print('hello from real VM')\"}
  }" | jq
```

> **Current behavior (before bug fix):** Returns HTTP 500 with `AttributeError: 'FirecrackerVM' object has no attribute 'run'`.
>
> **Intended behavior (after bug fix):** In real mode, the request restores a VM from snapshot, executes the Python code inside the guest, and returns:

```json
{
  "job_id": "...",
  "session_id": "...",
  "status": "completed",
  "output": "hello from real VM\n",
  "error_message": "",
  "duration_ms": 45
}
```

Note: `duration_ms` reflects real snapshot-restore boot time (20–80ms typical).

**7d. Execute with continuous snapshot mode**

Continuous mode saves VM state after each execution. Subsequent runs restore from the previous state, preserving installed packages and in-memory variables.

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

Stop the Nomad job:

```bash
nomad job stop -purge sandbox-worker-linux 2>/dev/null || true
```

Stop `platform-api` (Ctrl+C in its terminal, or):

```bash
pkill -f "platform-api"
```

Stop infrastructure:

```bash
cd services
docker compose down
```

Stop the Nomad dev agent (Ctrl+C in its terminal, or):

```bash
sudo pkill nomad
rm -rf /tmp/nomad
```

Remove local snapshot cache and temp files:

```bash
rm -rf /tmp/sandbox-cache /tmp/python-v1 /tmp/fc-assets /tmp/sandbox-worker-linux.nomad
```

Remove MinIO snapshot:

```bash
mc rm --recursive --force local/platform-snapshots/python-v1
```
