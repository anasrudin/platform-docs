# Phase 3 — Nomad Worker Image

**Status:** In Progress  
**Last updated:** 2026-04-10 (verified against codebase)

---

## Visi

```
platform-docs/
├── sandbox-worker/    ← Nomad worker (FastAPI + VM pool per node)
└── services/          ← controller + data (consul, haproxy, nomad, minio, postgres)
```

Tiga Docker image per runtime type, masing-masing di-deploy sebagai Nomad job group.  
HAProxy load balance ke tiap agent via Consul service discovery.

---

## Docker Images

Tiga image — satu base, dua extend per runtime type.  
**WASM tidak perlu Docker** — WASM sandbox sudah menyediakan isolasi sendiri, jalan via `raw_exec`.

| Image | Base | Extra Deps | Size Estimasi | Nomad Driver |
|-------|------|-----------|---------------|--------------|
| `sandbox-base` | ubuntu:22.04 | python3.11 + pip packages | ~212MB | — |
| `sandbox-fc-agent` | sandbox-base | Firecracker binary, iptables | ~242MB | `docker` + `/dev/kvm` |
| `sandbox-gui-agent` | sandbox-base | Chromium, Xvfb, Playwright | ~540MB | `docker` |
| ~~`sandbox-wasm-agent`~~ | — | — | — | `raw_exec` (host binary) |

> **Catatan:** LibreOffice (~450MB) dipisah ke `sandbox-office-agent` tersendiri agar
> `gui-agent` tetap slim (~540MB). Playwright tidak download Chromium sendiri —
> pakai `chromium-browser` dari apt untuk hindari duplikasi.

Files:
- [docker/base/Dockerfile](../../docker/base/Dockerfile)
- [docker/fc-agent/Dockerfile](../../docker/fc-agent/Dockerfile)
- [docker/gui-agent/Dockerfile](../../docker/gui-agent/Dockerfile)

Build dari repo root:
```bash
docker build -f docker/base/Dockerfile     -t sandbox-base:latest    .
docker build -f docker/fc-agent/Dockerfile -t sandbox-fc-agent:latest .
docker build -f docker/gui-agent/Dockerfile -t sandbox-gui-agent:latest .
```

---

## Nomad Job

Tiga group dalam satu job, tiap group pakai image yang sesuai:

File: `services/nomad/jobs/sandbox-worker.nomad`

```
fc-agent   → node.class = firecracker  → port 8081  → driver: docker (+ /dev/kvm)
wasm-agent → node.class = wasm         → port 8082  → driver: raw_exec (host binary)
gui-agent  → node.class = gui          → port 8083  → driver: docker
```

---

## Fitur: Continuous Snapshot

### Latar belakang

Saat ini setiap eksekusi selalu dimulai dari **base snapshot** (clean state).  
Masalah: user yang sudah install package di sesi sebelumnya harus install ulang setiap sesi baru.

### Dua mode snapshot

| Mode | Behaviour | Use case |
|------|-----------|----------|
| **Clean** (default) | Setiap sesi mulai dari base snapshot, perubahan dibuang saat selesai | Security — isolasi penuh antar user |
| **Continuous** | Snapshot disimpan setelah sesi, sesi berikutnya resume dari snapshot terakhir | User ingin lanjut dari state sebelumnya (package sudah terinstall) |

Toggle via request parameter atau session config:
```json
POST /sessions
{
  "runtime": "firecracker",
  "snapshot_mode": "continuous"   // atau "clean" (default)
}
```

### Flow: Clean mode (default)

```
start session
  → load base snapshot (read-only)
  → execute
  → discard overlay
  → VM kembali ke pool (base snapshot intact)
```

### Flow: Continuous mode

```
start session
  → cek apakah user punya snapshot di MinIO (sandbox/snapshots/{user_id}/latest)
      ↳ ada  → load user snapshot
      ↳ tidak ada → load base snapshot (pertama kali)
  → execute (install packages, dll)
  → END session → simpan snapshot ke MinIO (sandbox/snapshots/{user_id}/latest)
  → sesi berikutnya resume dari sini
```

### Revert ke clean state

User bisa toggle kembali ke base kapan saja:
```json
POST /sessions
{
  "runtime": "firecracker",
  "snapshot_mode": "clean",
  "force_reset": true   // hapus user snapshot dari MinIO, mulai dari base
}
```

Atau via endpoint khusus:
```
DELETE /snapshots/{user_id}   → hapus user snapshot, sesi berikutnya dari base
```

### Storage layout di MinIO

```
snapshots/
├── base/                          ← base snapshot (read-only, dibuat saat build)
│   ├── vmstate.bin
│   ├── memory.bin
│   └── meta.json
└── users/
    └── {user_id}/
        └── latest/                ← user snapshot (continuous mode)
            ├── vmstate.bin
            ├── memory.bin
            └── meta.json
```

### Komponen yang perlu ditambah

| Komponen | Perubahan |
|----------|-----------|
| `models/session.py` | Tambah field `snapshot_mode: Literal["clean", "continuous"]` |
| `models/snapshot.py` | Model baru: `SnapshotMode`, `UserSnapshot` |
| `orchestrator/snapshot.py` | Tambah `load_user_snapshot()`, `save_user_snapshot()`, `delete_user_snapshot()` |
| `service/execution.py` | Cek `snapshot_mode` saat acquire VM, trigger save saat session end |
| `service/session.py` | Simpan `snapshot_mode` per session |
| `api/routes/session.py` | Terima `snapshot_mode` di request body |
| `api/routes/snapshot.py` | Endpoint baru: `DELETE /snapshots/{user_id}` untuk force reset |
| `adapters/storage/s3_compat.py` | Tambah `save_user_snapshot()`, `load_user_snapshot()`, `delete_user_snapshot()` |

---

## Runbook: Jalankan Python di Nomad (End-to-End)

> Target akhir: `POST /execute` dengan `{"tool":"python_run","input":{"code":"print(1+1)"}}` → `{"output":"2\n"}`

### Prasyarat

```bash
# Di semua node
sudo apt-get install -y nomad consul haproxy docker.io \
     firecracker qemu-utils util-linux python3.11

# Pasang mc (MinIO client)
curl -fsSL https://dl.min.io/client/mc/release/linux-amd64/mc \
     -o /usr/local/bin/mc && chmod +x /usr/local/bin/mc
```

---

Semua langkah tersedia via `make`. Lihat semua target dengan `make help`.

### Step 1 — Start data services
```bash
make services-up
```

### Step 2 — Setup + start Nomad cluster
```bash
make cluster-setup   # install deps di semua node (butuh sudo)
make cluster-start   # start Nomad + Consul
make cluster-status  # verifikasi node up
```

### Step 3-5 — Build + upload Firecracker snapshot (Python 3.11)
```bash
# Semua sekaligus:
make snapshot-build

# Atau step by step:
make snapshot-rootfs   # build rootfs ext4
make snapshot-create   # boot VM + ambil snapshot
make snapshot-upload   # upload ke MinIO
```

### Step 6 — Build Docker images
```bash
make image-build

# Verifikasi:
# sandbox-fc-agent   latest   ~242MB
# sandbox-base       latest   ~212MB
```

### Step 7 — Deploy ke Nomad
```bash
make deploy
make deploy-status
make deploy-logs      # lihat logs jika ada masalah
```

### Step 8 — Verifikasi
```bash
make health
# --- fc-agent health:
# {"status":"healthy","version":"0.2.0","services":{"vm_pool":"healthy (pool_size=5)"}}
```

### Step 9 — Jalankan Python
```bash
make run-python
```

Response yang diharapkan:
```json
{
  "job_id": "...",
  "session_id": "...",
  "status": "completed",
  "output": "2\n",
  "error_message": "",
  "duration_ms": 62
}
```

### Override variables
```bash
make snapshot-build SNAPSHOT_NAME=python-v2
make image-build    VERSION=1.0.0
make image-push     REGISTRY=myregistry.io/sandbox VERSION=1.0.0
make run-python     NODE1_IP=10.0.1.5
```

---

### Troubleshooting

| Masalah | Cek |
|---------|-----|
| VM pool tidak start | `nomad alloc logs <id>` — cek `/dev/kvm` tersedia |
| Snapshot tidak ditemukan | `mc ls local/platform-snapshots/python-v1/` |
| Consul tidak register | `CONSUL_ENABLED=true` di env Nomad job |
| HAProxy 503 | `consul catalog services` — agent sudah register? |
| `python_run` timeout | Naikkan `timeout` di request body, default 30s |

---

## Fitur: DAG Execution (Low Latency)

### Latar belakang

Arsitektur saat ini memperlakukan tiap request sebagai eksekusi independen.
Untuk workflow multi-step (DAG), setiap step melewati HAProxy → worker → VM acquire — menghasilkan overhead yang menumpuk:

```
5-step DAG = 5 × (network hop + VM acquire ~50ms) = ~250-300ms overhead
```

### Masalah jika DAG dijalankan step-by-step via API

| Masalah | Dampak |
|---------|--------|
| Network hop per step via HAProxy | +5-10ms per step |
| VM acquire per step (warm pool) | +50ms per step |
| Step bisa landing di node berbeda | tidak ada shared memory/state |
| Data harus re-serialize tiap step | overhead marshal/unmarshal |

### Solusi: Server-side DAG di worker (Opsi B)

Satu endpoint menerima seluruh DAG, worker mengeksekusi semua steps di **VM yang sama**:

```
POST /execute/dag
{
  "steps": [
    {"id": "a", "tool": "python_run", "input": {...}},
    {"id": "b", "tool": "html_parse", "input": {"html": "$a.output"}},
    {"id": "c", "tool": "python_run", "input": {"code": "$b.output"}}
  ],
  "deps": {"b": ["a"], "c": ["b"]}
}
```

### Flow eksekusi

```
POST /execute/dag
  → DAGService: parse steps + deps → build execution order
  → acquire 1 VM (untuk steps yang sama runtime)
      ↳ sequential steps: jalankan berurutan di VM yang sama
      ↳ parallel branches: jalankan concurrent (asyncio.gather)
  → hasil tiap step di-pass langsung ke step berikutnya (in-memory)
  → release VM
  → return semua results
```

### Mixed runtime DAG

Kalau DAG punya steps dengan runtime berbeda (WASM + Firecracker):

```
steps WASM    → wasm-agent (raw_exec, in-process, ~1ms)
steps FC      → fc-agent (VM acquire satu kali untuk semua FC steps)
steps GUI     → gui-agent

Orchestration: DAGService di worker yang menerima request
```

Untuk mixed runtime, step WASM bisa dijalankan **in-process** (tidak perlu VM) karena Wasmtime bisa di-embed langsung:

```
fc-agent menerima DAG mixed:
  → steps WASM → jalankan in-process via Wasmtime Python binding
  → steps FC   → jalankan via VM pool
  → gabungkan hasil
```

### Latency target

| Skenario | Tanpa DAG endpoint | Dengan DAG endpoint |
|----------|-------------------|---------------------|
| 5 sequential FC steps | ~300ms overhead | ~60ms (1× VM acquire) |
| 3 parallel WASM steps | ~30ms overhead | ~3ms (in-process) |
| Mixed: 2 WASM + 3 FC | ~200ms overhead | ~65ms (1× VM acquire) |

### Storage layout hasil DAG di MinIO

```
dag-results/
└── {dag_id}/
    ├── step_a.json
    ├── step_b.json
    └── step_c.json
```

### Komponen yang perlu ditambah

| Komponen | Perubahan |
|----------|-----------|
| `models/dag.py` | Model baru: `DAGRequest`, `DAGStep`, `DAGResult`, `StepStatus` |
| `service/dag.py` | `DAGService`: parse deps, topological sort, execute steps |
| `service/execution.py` | Tambah `execute_dag()` method |
| `api/routes/dag.py` | Endpoint baru: `POST /execute/dag` |
| `api/app.py` | Register `dag` router |
| `runtime/wasm.py` | Tambah in-process Wasmtime execution (untuk mixed DAG di fc-agent) |

---

## Yang Sudah Selesai

- [x] Rename `sandbox-platform/` → `sandbox-worker/`
- [x] Hapus `agents/`, `scaler/`, `adapters/db`, `adapters/cache`, `adapters/queue` dari worker
- [x] Rewrite `execution.py` — direct VM acquire/run/release, tidak ada Redis queue
- [x] Rewrite `session.py` — in-memory per node, tidak ada Postgres dependency
- [x] Rewrite `health.py` — cek VM pool status
- [x] Update `api/app.py` — wire ke VMLifecycleManager + Consul registration
- [x] Pindah `infra/` → `services/` di root repo
- [x] Buat `services/docker-compose.yml` — consul + minio + postgres
- [x] Hapus `sandbox-worker/docker-compose.yml` — entity data ada di `services/`
- [x] Buat empat Dockerfile (base, fc-agent, wasm-agent, gui-agent)
- [x] Update Nomad job spec — `raw_exec` → `docker` driver, tiga group
- [x] Update ADR `docs/architecture/layer-restructure.md`

---

## Yang Belum Selesai

### Docker image
- [x] Pisah LibreOffice ke `Dockerfile.office-agent` tersendiri — `docker/office-agent/Dockerfile`
- [x] Fix `Dockerfile.gui-agent` — hapus `playwright install chromium`, pakai apt chromium saja
- [x] Buat root `Makefile` — services, cluster, snapshot, image, deploy, test
- [ ] Build `sandbox-fc-agent` dan `sandbox-gui-agent`, push ke registry (`make image-build image-push`)
- [ ] Tambah CI pipeline untuk build + push otomatis *(tidak ada `.github/workflows/`)*
- [ ] Setup node `wasm` — install Wasmtime + Python di host via `setup-firecracker.sh` *(Wasmtime belum ada di script)*

### DAG Execution
- [x] Tambah `models/workflow.py` — `DAGWorkflow`, `WorkflowStep`, `StepResult`, `StepStatus` *(sudah ada, digunakan)*
- [x] Tambah `service/workflow.py` — topological sort (Kahn's), parallel waves via ThreadPoolExecutor, `$steps.step_id.output` interpolation
- [x] Tambah `api/routes/workflow.py` — `POST /workflows` (202), `GET /workflows/{id}` (200/404/503)
- [x] Update `api/app.py` — register workflow router, wire WorkflowService
- [ ] Tambah in-process Wasmtime execution di `runtime/wasm.py` untuk mixed DAG *(out of scope — skipped)*
- [x] Test: sequential DAG, parallel DAG — 31 tests in `tests/unit/test_workflow.py`
- [x] Test: step result di-pass ke step berikutnya via `$steps.step_id.output` — covered

### Continuous Snapshot
- [x] Tambah `SnapshotMode` enum ke `models/session.py`
- [x] Update `models/session.py` — tambah field `snapshot_mode` pada `Session`, `CreateSessionRequest`, `CreateSessionResponse`
- [x] Update `models/job.py` — tambah field `snapshot_paths: Any = None` untuk forward ke VM
- [x] Update `orchestrator/snapshot.py` — `load_session_snapshot()`, `save_session_snapshot()`, `delete_session_snapshot()` dengan key prefix `sessions/{session_id}/`
- [x] Update `service/execution.py` — cek `snapshot_mode`, load sebelum run, save setelah success (exit_code=0)
- [x] Update `api/routes/session.py` — terima `snapshot_mode` di request body via `Body(default_factory=dict)`
- [x] Tambah `api/routes/snapshot.py` — `DELETE /snapshots/{session_id}` untuk force reset (204/503)
- [x] Update `api/app.py` — inject downloader ke ExecutionService, register snapshot router
- [x] Test: clean mode tidak menyimpan snapshot, continuous mode menyimpan — `tests/unit/test_continuous_snapshot.py` (20 tests)
- [x] Test: force reset menghapus session snapshot dari storage + local cache
- [ ] Update `adapters/storage/s3_compat.py` — CRUD ke MinIO *(SnapshotDownloader uses BlobStore protocol, no direct s3_compat changes needed)*
