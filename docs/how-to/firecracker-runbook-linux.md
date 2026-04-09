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

Each command returns `{}` on success.

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
