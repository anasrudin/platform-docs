# Firecracker Runbook — Linux + KVM (Real Mode)

| Field | Value |
|---|---|
| Platform | Linux (Debian/Ubuntu recommended), KVM enabled |
| Firecracker mode | `real` — actual microVM execution |
| Last updated | 2026-04-12 |

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
  curl jq build-essential e2fsprogs
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
FC_VERSION=v1.15.1
ARCH=$(uname -m)
curl -fL -o /tmp/firecracker.tgz \
  "https://github.com/firecracker-microvm/firecracker/releases/download/${FC_VERSION}/firecracker-${FC_VERSION}-${ARCH}.tgz"
tar -xzf /tmp/firecracker.tgz -C /tmp
sudo install /tmp/release-${FC_VERSION}-${ARCH}/firecracker-${FC_VERSION}-${ARCH} \
  /usr/bin/firecracker
sudo install /tmp/release-${FC_VERSION}-${ARCH}/jailer-${FC_VERSION}-${ARCH} \
  /usr/bin/jailer
firecracker --version   # Firecracker v1.15.1
```

> The binary path defaults to `/usr/bin/firecracker`. Override with:
> - `FC_BIN=/usr/local/bin/firecracker` — for the fc-agent (uses `runtime/firecracker.py` `Config` directly)
> - `FC_BINARY_PATH=/usr/local/bin/firecracker` — for platform-api (reads from `config/settings.py` `FirecrackerConfig`)
>
> If you install Firecracker elsewhere, set **both** when running both processes.

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

Verify the stack is healthy:

```bash
# Still in services/
docker compose ps
```

Expected — five services total. Data and controller services show `healthy`; jaeger has no healthcheck so it shows `Up` only:

```
NAME        STATUS
consul      Up (healthy)
jaeger      Up
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

> The `pool_size` value reflects `FC_POOL_SIZE` (default: `2`).
>
> **Real-mode note:** `platform-api` wires a `SnapshotBlobStore` into `VMLifecycleManager` (`api/app.py`), so real-mode startup requires a reachable MinIO endpoint and a valid `platform-snapshots/python-v1` snapshot. If MinIO or the snapshot is missing, startup fails rather than silently falling back to sim mode. Use `FC_MODE=sim` for local dev without a snapshot, or build and upload a snapshot first (section 4).

Troubleshoot: if MinIO is unreachable, confirm Docker is running and `docker compose ps` from `services/` shows port `9000->9000`.

---

## 4. Build a Firecracker snapshot from scratch

A real Firecracker snapshot captures full VM state: CPU registers, memory, and disk. Restoring from snapshot boots a VM in 20–80ms instead of a full kernel boot.

Recommended: use the helper scripts in `tools/snapshot-builder/`. Run from the repo root (`platform-docs/`):

```bash
mkdir -p /tmp/snapshots/python-v1

# Download the Firecracker CI kernel with CONFIG_VIRTIO_VSOCKETS=y (built-in).
# The old quickstart URL (img/quickstart_guide/…/vmlinux.bin) returns 404 — use
# the versioned CI artifact instead:
curl -fL -o /tmp/snapshots/vmlinux.bin \
  "https://s3.amazonaws.com/spec.ccfc.min/firecracker-ci/v1.15/x86_64/vmlinux-5.10.245"

sudo bash tools/snapshot-builder/build-rootfs.sh \
  --name python-v1 \
  --python 3.11 \
  --size 1024 \
  --out /tmp/snapshots/python-v1/rootfs.ext4

sudo bash tools/snapshot-builder/fc-snapshot.sh \
  --name python-v1 \
  --rootfs /tmp/snapshots/python-v1/rootfs.ext4 \
  --kernel /tmp/snapshots/vmlinux.bin \
  --out-dir /tmp/snapshots

bash tools/snapshot-builder/upload-minio.sh \
  --snapshot-dir /tmp/snapshots/python-v1 \
  --name python-v1 \
  --kernel /tmp/snapshots/vmlinux.bin \
  --rootfs /tmp/snapshots/python-v1/rootfs.ext4 \
  --endpoint http://localhost:9000
```

> **Kernel requirement:** The kernel must have `CONFIG_VIRTIO_VSOCKETS=y` (built-in, not module).
> The Firecracker CI kernel satisfies this; the host's system kernel (Debian/Ubuntu cloud image) has
> it as a module only (`=m`) and will not support vsock in the guest.
>
> **Snapshot builder vsock warning:** `fc-snapshot.sh` prints
> `WARNING: guest agent not reachable via vsock after 60s` even when the agent is working.
> This is expected — the connectivity probe uses `AF_VSOCK` kernel sockets from the host, but
> Firecracker exposes vsock to the host via a UDS proxy protocol, not kernel vsock.
> The warning is safe to ignore if `[agent] listening on vsock:8080` appeared in the console output.

Equivalent Make targets from the repo root:

```bash
make snapshot-rootfs snapshot-create snapshot-upload
```

> `snapshot-create` writes local `state` and `mem` files under `/tmp/snapshots/python-v1/`. `upload-minio.sh` remaps them to `vmstate.bin` and `memory.bin` in MinIO.

The manual Firecracker API flow below is still useful for debugging the hypervisor directly.

**4a. Download kernel and rootfs**

```bash
mkdir -p /tmp/fc-assets

# Firecracker CI kernel with vsock built-in (CONFIG_VIRTIO_VSOCKETS=y).
# The quickstart vmlinux.bin URL (img/quickstart_guide/…) returns 404 — use
# the versioned CI artifact:
curl -fL -o /tmp/fc-assets/vmlinux \
  "https://s3.amazonaws.com/spec.ccfc.min/firecracker-ci/v1.15/x86_64/vmlinux-5.10.245"

# Minimal rootfs (replace with a Python-preinstalled image for production use)
curl -fL -o /tmp/fc-assets/rootfs.ext4 \
  "https://s3.amazonaws.com/spec.ccfc.min/img/quickstart_guide/x86_64/rootfs/bionic.rootfs.ext4"
```

> These are Firecracker's public quickstart assets. For a Python runtime snapshot, use the rootfs built by `build-rootfs.sh` which includes the guest agent at `/opt/agent/agent.py`.

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
    \"boot_args\": \"console=ttyS0 reboot=k panic=1 pci=off init=/opt/agent/agent.py\"
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

**4e. Pause the VM**

```bash
curl -s -X PATCH \
  --unix-socket $FC_SOCKET \
  "http://localhost/vm" \
  -H "Content-Type: application/json" \
  -d '{"state": "Paused"}'
```

Expected: HTTP 204 No Content (curl prints nothing on success).

**4f. Create the snapshot**

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

**4g. Write metadata**

```bash
cat > /tmp/python-v1/meta.json <<'EOF'
{
  "name": "python-v1",
  "version": "3.12",
  "kernel": "vmlinux-5.10",
  "rootfs": "python-v1.ext4",
  "vcpus": 2,
  "mem_mib": 512,
  "created_at": "2026-04-11T00:00:00",
  "dry_run": false,
  "files": {}
}
EOF
```

**4h. Stop Firecracker**

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
fc-agent starting  mode=real  snapshot=python-v1
snapshot not cached, downloading from MinIO  name=python-v1
snapshot ready  mode=real  snapshot=python-v1  state_file=/tmp/sandbox-cache/python-v1/vmstate.bin
fc-agent health server started  port=8081
```

On second start (cache hit), the `snapshot not cached` line is replaced by a `debug`-level `snapshot cache hit` entry — it only appears when `LOG_LEVEL=debug` is set. With default log config, no snapshot line appears on cache hit — this is expected.

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

Expected: `Status = running`.

View logs:

```bash
ALLOC_ID=$(nomad job status sandbox-worker-linux | awk '/^Allocations/{found=1; next} found && ($6=="running" || $6=="failed"){print $1; exit}')
nomad alloc logs $ALLOC_ID fc-agent
```

Troubleshoot: if `raw_exec` is disabled, it is enabled by default in `-dev` mode. If running with a real Nomad config, add `plugin "raw_exec" { config { enabled = true } }` to your Nomad agent config file. Also ensure `/dev/kvm` is accessible by the Nomad task user.

---

## 7. Run Python code end-to-end

> **Note:** `platform-api` runs its own in-process VM lifecycle manager. It does not route requests through the Nomad-deployed fc-agent at runtime. For end-to-end real-mode execution via `POST /execute`, ensure the VM pool warmup completes successfully (check logs after startup) — it requires:
> 1. A valid snapshot in MinIO with the name matching `FC_SNAPSHOT_BUCKET` (see 7a).
> 2. The Firecracker binary at `FC_BINARY_PATH` (default `/usr/bin/firecracker`).
> 3. **A guest agent pre-installed inside the VM snapshot.** `platform-api` communicates with the VM over vsock port 8080 using `GuestClient` (`runtime/firecracker.py`). The rootfs in your snapshot must have a guest agent process listening on that port that accepts `POST /execute` with a JSON body `{"tool": "...", "input": {...}}` and responds with `{"exit_code": 0, "stdout": "...", "stderr": "..."}`. Without this, `GuestClient.wait_ready()` times out after 15 seconds and execution fails. The guest agent binary and its init configuration must be baked into the rootfs before creating the snapshot.

**7a. Ensure platform-api is running**

From section 3, `platform-api` should be running with `FC_MODE=real`. If not, restart it:

```bash
cd sandbox-worker
source .venv/bin/activate
FC_MODE=real \
  FC_SNAPSHOT_BUCKET=python-v1 \
  MINIO_ENDPOINT=http://localhost:9000 \
  MINIO_ACCESS_KEY=minioadmin \
  MINIO_SECRET_KEY=minioadmin \
  platform-api
```

> `SNAPSHOT_NAME` controls which snapshot is loaded from MinIO and must match the prefix uploaded in section 5 (e.g. `python-v1`). `FC_SNAPSHOT_BUCKET` controls the MinIO bucket name (default: `platform-snapshots`).

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

Expected (real mode — snapshot restores a VM and runs code inside the guest):

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

## 8. Deploy to GCP Nomad — full stack

This section covers deploying the **complete platform stack** on the GCP Nomad VM:
MinIO + PostgreSQL + Redis + Consul + Jaeger + platform-api, with all env vars wired
so traces appear in Jaeger and sessions are registered in Consul.

### 8a. Prerequisites on the GCP VM

- Firecracker v1.15.1 at `/usr/bin/firecracker`
- Docker + Docker Compose v2 installed
- Python venv at `~/fc-agent-venv` with `sandbox-worker` deps installed (including `opentelemetry-sdk`)
- Nested virtualization enabled (`enableNestedVirtualization=true`, `n2-standard-4`, Intel Cascade Lake)
- `/dev/kvm` accessible (`crw-rw-rw-`)
- `platform-snapshots/python-v1` snapshot already in MinIO (see section 4–5)

**Install opentelemetry packages in the venv (required for Jaeger traces):**

```bash
# SSH into the Nomad VM first
gcloud compute ssh nomad --project=e2b-infra-489707 --zone=asia-southeast1-a

~/fc-agent-venv/bin/pip install \
  opentelemetry-api \
  opentelemetry-sdk \
  'opentelemetry-exporter-otlp-proto-grpc>=1.20'
```

**Install Docker Compose v2 plugin if missing:**

```bash
mkdir -p ~/.docker/cli-plugins
curl -fsSL https://github.com/docker/compose/releases/download/v2.24.6/docker-compose-linux-x86_64 \
  -o ~/.docker/cli-plugins/docker-compose
chmod +x ~/.docker/cli-plugins/docker-compose
docker compose version   # must print v2.x
```

### 8b. Deploy the full stack (one command)

From your **laptop**, run from the repo root:

```bash
bash tools/runbook/gcp-jumphost-nomad/gcloud/deploy-full-stack.sh
```

This script does 4 steps automatically:

1. **Syncs `services/`** (docker-compose files for MinIO, PostgreSQL, Redis, Consul, Jaeger) to the VM
2. **Starts all containers** with `docker compose up -d` and waits for healthy status
3. **Opens GCP firewall ports** scoped to your current public IP:
   - `4646` Nomad UI
   - `8500` Consul UI
   - `9001` MinIO console
   - `16686` Jaeger UI
   - `4317/4318` OTEL collector
   - `8080` platform-api
4. **Redeploys platform-api** via Nomad with full env wiring:

   | Env var | Value |
   |---------|-------|
   | `FC_MODE` | `real` |
   | `OTEL_ENABLED` | `true` |
   | `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://127.0.0.1:4317` |
   | `CONSUL_ENABLED` | `true` |
   | `DATABASE_URL` | `postgresql://postgres:postgres@127.0.0.1:5432/platform` |
   | `REDIS_URL` | `redis://127.0.0.1:6379/0` |
   | `MINIO_ENDPOINT` | `http://127.0.0.1:9000` |
   | `SNAPSHOT_NAME` | `python-v1` |

Skip flags are available:

```bash
# Skip rsync if services/ hasn't changed:
bash deploy-full-stack.sh --skip-sync

# Skip firewall update (if ports already open):
bash deploy-full-stack.sh --skip-firewall

# Skip Nomad redeploy (containers only):
bash deploy-full-stack.sh --skip-nomad

# Override auto-detected public IP:
bash deploy-full-stack.sh --my-ip=203.0.113.1
```

### 8c. Verify all components

After deploy completes, run the smoke test:

```bash
bash tools/runbook/gcp-jumphost-nomad/smoke-test.sh http://34.143.174.106:8080
```

Expected output — all 5 checks pass:

```
[1/5] API health check...      [OK] API is up
[2/5] Create session...        [OK] Session created
[3/5] Execute Python in VM...  [OK] Code ran in Firecracker VM
[4/5] Consul status...         [OK] Consul leader: "127.0.0.1:8300"
[5/5] Jaeger status...         [OK] Jaeger UI is reachable
```

Dashboard URLs (replace `34.143.174.106` with your VM's external IP):

| Dashboard | URL |
|-----------|-----|
| Nomad     | http://34.143.174.106:4646 |
| Consul    | http://34.143.174.106:8500/ui |
| Jaeger    | http://34.143.174.106:16686 |
| MinIO     | http://34.143.174.106:9001 (minioadmin / minioadmin) |
| API       | http://34.143.174.106:8080/health |

### 8d. GCP firewall — common issue

The firewall rule must be created in the **same VPC as the VM** (`jump-nomad-vpc`), not the `default` network. The deploy script handles this automatically. If you create the rule manually:

```bash
gcloud compute firewall-rules create platform-dev-access \
  --project=e2b-infra-489707 \
  --network=jump-nomad-vpc \          # <-- not "default"
  --rules="tcp:8500,tcp:9001,tcp:16686,tcp:4317,tcp:4318" \
  --source-ranges="$(curl -s checkip.amazonaws.com)/32" \
  --target-tags=nomad
```

### 8e. Cleanup

From your **laptop**:

```bash
# Stop the Nomad job and kill orphan Firecracker processes:
bash tools/runbook/gcp-jumphost-nomad/gcloud/cleanup.sh

# Also remove snapshot from MinIO and clear local cache:
bash tools/runbook/gcp-jumphost-nomad/gcloud/cleanup.sh --full

# Stop all docker containers (runs on the VM):
gcloud compute ssh nomad --project=e2b-infra-489707 --zone=asia-southeast1-a \
  --command="cd ~/platform-docs/services && docker compose down"
```

> **Orphan process cleanup:** Nomad's `raw_exec` driver does not kill Firecracker child processes when the task stops. Always run `cleanup.sh` before redeploying — or the deploy script runs `pkill -x firecracker` automatically.

---

## 9. Trace the full workflow with logs

With the full stack deployed (section 8), you can observe every layer of a request.

### 9a. Watch platform-api logs live

```bash
gcloud compute ssh nomad --project=e2b-infra-489707 --zone=asia-southeast1-a \
  --command="
ALLOC=\$(NOMAD_ADDR=http://127.0.0.1:4646 nomad job allocs platform-api \
  | awk 'NR==2{print \$1}')
echo \"alloc: \$ALLOC\"
NOMAD_ADDR=http://127.0.0.1:4646 nomad alloc logs -f \$ALLOC platform-api
"
```

Each `POST /execute` emits structured log lines like:

```
10:41:05 [info]  http.request  method=POST  path=/execute  req_id=abc123
10:41:05 [info]  pool.acquire  session_id=f5b35b6a  snapshot=python-v1
10:41:05 [info]  communication.vsock.execute  tool=python_run  duration_ms=212
10:41:05 [info]  service.execution.run  status=completed  duration_ms=215
10:41:05 [info]  http.request  status=200  duration_ms=216
```

### 9b. Watch stderr (errors and tracebacks)

```bash
gcloud compute ssh nomad --project=e2b-infra-489707 --zone=asia-southeast1-a \
  --command="
ALLOC=\$(NOMAD_ADDR=http://127.0.0.1:4646 nomad job allocs platform-api \
  | awk 'NR==2{print \$1}')
NOMAD_ADDR=http://127.0.0.1:4646 nomad alloc logs -stderr -f \$ALLOC platform-api
"
```

### 9c. Watch Docker service logs

```bash
gcloud compute ssh nomad --project=e2b-infra-489707 --zone=asia-southeast1-a \
  --command="cd ~/platform-docs/services && docker compose logs -f --tail=50"
```

Per service:

```bash
# Consul registrations and health checks:
docker compose logs -f consul

# Jaeger — span ingestion (OTLP):
docker compose logs -f jaeger

# PostgreSQL — queries:
docker compose logs -f postgres

# Redis:
docker compose logs -f redis
```

### 9d. Trace in Jaeger UI

Open http://34.143.174.106:16686, then:

1. **Service** → `sandbox-platform-worker`
2. **Operation** → leave blank (all) or pick one:
   - `http.request` — outermost HTTP span
   - `service.execution.run` — tool dispatch
   - `pool.acquire` — FC pool checkout
   - `communication.vsock.execute` — vsock round-trip into guest VM
3. Click **Find Traces**
4. Click a trace to see the full span tree

The span hierarchy for a `POST /execute` call:

```
http.request  [POST /execute]                ~216ms
  └── service.execution.run                  ~215ms
        └── pool.acquire                       ~2ms
              └── communication.vsock.execute  ~212ms
```

The `communication.vsock.execute` span shows exact time spent inside the Firecracker VM. Attributes include `tool`, `session_id`.

### 9e. Check Consul service registration

```bash
curl -s http://34.143.174.106:8500/v1/catalog/service/sandbox-worker | python3 -m json.tool
```

Expected: one entry with `Address` pointing to the VM's internal IP and `Port: 8080`.

Or open the Consul UI: http://34.143.174.106:8500/ui → Services → `sandbox-worker`.

### 9f. Check Nomad allocation health

```bash
# From laptop:
curl -s http://34.143.174.106:4646/v1/job/platform-api/allocations | python3 -m json.tool

# Or from inside the VM:
gcloud compute ssh nomad --project=e2b-infra-489707 --zone=asia-southeast1-a \
  --command="NOMAD_ADDR=http://127.0.0.1:4646 nomad job status platform-api"
```

### 9g. Check Firecracker process logs

```bash
gcloud compute ssh nomad --project=e2b-infra-489707 --zone=asia-southeast1-a \
  --command="
# Find the FC log for the running VM
ls /tmp/platform-snapshots/vms/
FC_LOG=\$(ls /tmp/platform-snapshots/vms/*/fc-*.log 2>/dev/null | head -1)
echo \"FC log: \$FC_LOG\"
tail -20 \"\$FC_LOG\"
"
```

Firecracker logs show vsock connection events and memory restore activity:

```
[INFO]  Firecracker v1.15.1
[INFO]  Starting microVM
[INFO]  Restored from snapshot
```

### 9h. Full workflow trace (all at once)

Run this from the VM to tail all relevant logs simultaneously in separate windows, or use `tmux`:

```bash
gcloud compute ssh nomad --project=e2b-infra-489707 --zone=asia-southeast1-a \
  --command="
# Get alloc ID
ALLOC=\$(NOMAD_ADDR=http://127.0.0.1:4646 nomad job allocs platform-api \
  | awk 'NR==2{print \$1}')

echo '=== Platform-API stdout logs ==='
NOMAD_ADDR=http://127.0.0.1:4646 nomad alloc logs \$ALLOC platform-api | tail -20

echo ''
echo '=== Docker container status ==='
cd ~/platform-docs/services && docker compose ps

echo ''
echo '=== Consul service health ==='
curl -s http://127.0.0.1:8500/v1/health/service/sandbox-worker | python3 -m json.tool

echo ''
echo '=== Active Firecracker processes ==='
ps aux | grep firecracker | grep -v grep
"
```

Then from your **laptop**, trigger a request and watch the logs:

```bash
API=http://34.143.174.106:8080

SESSION=$(curl -sS -X POST $API/sessions \
  -H "Content-Type: application/json" \
  -d '{"runtime":"microvm"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['session_id'])")

curl -sS -X POST $API/execute \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"$SESSION\",\"tool\":\"python_run\",\"input\":{\"code\":\"import socket; print(socket.gethostname()); print(2**20)\"}}" \
  | python3 -m json.tool
```

Open Jaeger at http://34.143.174.106:16686 and find the trace for this request.

---

## 10. Cleanup

**Local dev:**

```bash
# Stop Nomad jobs
nomad job stop -purge platform-api 2>/dev/null || true
nomad job stop -purge sandbox-worker-linux 2>/dev/null || true

# Stop platform-api
pkill -f "platform-api"

# Stop infrastructure
cd services && docker compose down
```

**GCP:**

```bash
# Stop job + kill FC orphans
bash tools/runbook/gcp-jumphost-nomad/gcloud/cleanup.sh

# Also remove MinIO snapshot and local cache
bash tools/runbook/gcp-jumphost-nomad/gcloud/cleanup.sh --full

# Stop docker containers on VM
gcloud compute ssh nomad --project=e2b-infra-489707 --zone=asia-southeast1-a \
  --command="cd ~/platform-docs/services && docker compose down"
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
