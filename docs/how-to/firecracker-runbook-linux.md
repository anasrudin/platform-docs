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
