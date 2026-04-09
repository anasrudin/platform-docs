# ADR: Refactor ke Nomad Worker Architecture

**Status:** Accepted — Implemented  
**Date:** 2026-04-09  
**Deciders:** @anasrudin

---

## Context

Evolusi arsitektur terjadi dalam dua fase:

**Fase 1 — Domain-first → Layer-based**  
Struktur lama (`sandbox_platform/`, `platform_cmd/`) direfaktor ke layer-based (`api/`, `service/`, `orchestrator/`, `runtime/`, `adapters/`). Selesai 2026-04-09.

**Fase 2 — Centralized API → Nomad Worker**  
Setelah Fase 1, arsitektur masih menggunakan model centralized API + queue-based agents:
```
client → platform-api (central) → Redis Queue → fc-agent / wasm-agent / gui-agent
```

Masalah dengan model ini:
1. API terpusat jadi single point of failure
2. Worker (agents) tidak punya API sendiri — tidak bisa di-healthcheck langsung oleh HAProxy
3. Redis dipakai sebagai job queue — menambah dependency yang tidak perlu
4. Postgres dipakai di worker untuk session state — bukan urusan worker

**Referensi:** `ccu/nomad-horizontal-scaler` membuktikan model yang lebih sederhana bekerja — setiap Nomad client node menjalankan FastAPI + VM pool sendiri, HAProxy load balance langsung ke node-node ini.

---

## Decision

Pindah ke **entity-based** structure:

| Entity | Komponen | Lokasi |
|--------|----------|--------|
| **Controller** | Consul, HAProxy | `services/consul/`, `services/haproxy/` |
| **Worker** | Nomad job + FastAPI + VM pool | `sandbox-worker/` |
| **Data** | MinIO, Postgres | `services/minio/`, `services/postgres/` |

### Worker model baru (CCU-style):

```
client
  ↓
HAProxy  ←── Consul (auto-update backends via consul-template)
  ↓
[sandbox-worker node 1: FastAPI + Firecracker VM pool]
[sandbox-worker node 2: FastAPI + Firecracker VM pool]
[sandbox-worker node 3: FastAPI + Firecracker VM pool]
  ↓
MinIO (artifacts, snapshots)
```

Setiap Nomad job menjalankan satu instance `sandbox-worker`:
- Punya FastAPI endpoint sendiri
- Manage VM pool lokal di node itu
- Register ke Consul saat start
- Tidak butuh Redis, tidak butuh Postgres

---

## Current Structure

### Repo root

```
platform-docs/
├── sandbox-worker/        ← entity worker: Nomad job
├── services/              ← entity controller + data: infra
├── docs/                  ← arsitektur, how-to, reference
├── ccu/                   ← referensi: nomad-horizontal-scaler
├── sandbox-tools/         ← tool definitions (wasm, headless, gui)
├── tools/                 ← snapshot builder
└── memory-bank/           ← project context docs
```

### `sandbox-worker/src/` — worker layers

```
src/
├── api/
│   ├── app.py             ← lifespan: start VM pool, register Consul, wire services
│   ├── middleware/        ← auth, tracing
│   ├── routes/            ← artifact, execute, health, hibernation,
│   │                         package, session, streaming, workspace
│   └── schemas/
├── service/               ← business logic (local per node)
│   ├── execution.py       ← acquire VM → run → release (direct, no queue)
│   ├── health.py          ← cek VM pool status
│   ├── session.py         ← in-memory session tracking
│   ├── artifact.py        ← upload/download ke MinIO
│   ├── package.py         ← install packages di VM
│   ├── streaming.py       ← stream output
│   ├── hibernation.py     ← hibernasi VM ke storage
│   └── workspace.py       ← workspace per session
├── orchestrator/
│   ├── lifecycle.py       ← VMLifecycleManager (wraps VMPool)
│   ├── snapshot.py        ← download snapshot dari MinIO
│   ├── hibernation.py     ← hibernation orchestrator
│   └── workspace.py       ← workspace mounter
├── runtime/               ← execution engines
│   ├── firecracker.py     ← VMPool, FirecrackerVM, GuestClient, SnapshotStore
│   ├── wasm.py            ← Wasmtime runtime
│   └── gui.py             ← Chromium + Playwright runtime
├── communication/         ← VM transport
│   ├── vsock.py           ← vsock dial + read/write
│   ├── guest.py           ← GuestClient (execute via vsock)
│   └── stream.py          ← async stream reader
├── adapters/              ← external services (slim subset)
│   ├── registry/          ← consul.py, health_server.py
│   ├── storage/           ← s3_compat.py (MinIO), local.py
│   └── tracing/           ← noop.py, otel.py
├── models/
│   ├── job.py             ← Job, JobStatus, RuntimeResult
│   └── session.py         ← Session, Tier
└── config/
    └── settings.py        ← semua env vars
```

### `services/` — infra

```
services/
├── consul/                ← consul agent config
├── haproxy/               ← haproxy.cfg.ctmpl + consul-template.hcl
├── nomad/
│   ├── client.hcl
│   ├── server.hcl
│   └── jobs/
│       └── sandbox-worker.nomad   ← docker driver + /dev/kvm + consul service check
├── postgres/migrations/
├── minio/init-buckets.sh
├── redis/                 ← tidak dipakai worker, available jika dibutuhkan
├── systemd/
├── scripts/
└── docker-compose.yml     ← consul + minio + postgres + prometheus
```

---

## Execution Flow

```
POST /execute
  → api/routes/execute.py
  → service/execution.py
      → orchestrator/lifecycle.py  (acquire VM from pool)
      → runtime/firecracker.py     (run job via GuestClient)
      → communication/guest.py     (vsock → VM)
      ← RuntimeResult
  → lifecycle.py                   (release VM back to pool)
  ← response JSON
```

---

## Consequences

**Positif:**
- Tidak ada single point of failure — tiap node independent
- HAProxy health check langsung ke `/health` endpoint tiap worker
- Tidak ada Redis dependency di worker path
- Session state in-memory — lebih cepat, lebih sederhana
- Consul registration otomatis saat start — HAProxy backend auto-update

**Negatif:**
- Session tidak shared antar node — client harus sticky session via HAProxy
- Tidak ada global job history (tidak ada Postgres di worker)
- Scale down bisa kehilangan in-flight sessions

---

## Definition of Done

- [x] `services/` berisi semua infra (consul, haproxy, nomad, postgres, minio)
- [x] `sandbox-worker/` hanya berisi kode yang jalan di Nomad client node
- [x] `execution.py` — direct VM acquire/run/release, tidak ada queue
- [x] `session.py` — in-memory, tidak ada Postgres dependency
- [x] `health.py` — cek VM pool status, bukan postgres+redis
- [x] `api/app.py` — wire ke VMLifecycleManager, register Consul
- [x] `docker/Dockerfile` — ubuntu:22.04 + python + firecracker binary
- [x] `services/nomad/jobs/sandbox-worker.nomad` — docker driver + /dev/kvm
- [x] `services/docker-compose.yml` — consul + minio + postgres (semua entity data di sini)
- [x] tidak ada `docker-compose.yml` di `sandbox-worker/` — worker tidak punya entity data
- [ ] Build dan push Docker image ke registry
- [ ] End-to-end test: deploy ke Nomad cluster, HAProxy routing, Consul health check
