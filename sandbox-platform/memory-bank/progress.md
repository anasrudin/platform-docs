# Progress

> Last updated: 2026-04-07

## Week 1 — Go Implementation (✅ Selesai)

| Hari | Status | Deliverable |
|------|--------|-------------|
| 1–2  | ✅ | Nomad cluster + PG + Redis + MinIO infra scripts |
| 3    | ✅ | Firecracker install + KVM setup + test-firecracker.sh |
| 4    | ✅ | `tools/snapshot-builder/` — rootfs + snapshot + MinIO upload |
| 5    | ✅ | Real Firecracker runtime (pool + vsock + snapshot restore) |
| 6    | ✅ | Real WASM runtime (Wasmtime CLI + MinIO module cache) |
| 7    | ✅ | Artifact upload/download (POST /artifacts, GET /artifacts/{key}) |

## Fase Saat Ini — Migrasi Go → Python (🔄 In Progress)

| Komponen | Status |
|----------|--------|
| Panduan migrasi (`docs/migration/go-to-python.md`) | ✅ |
| Spec fitur lanjutan (`docs/todo/todo-list.md`) | ✅ |
| Setup Python project (`pyproject.toml`, venv) | 📋 Belum |
| `sandbox_platform/types.py` | 📋 Belum |
| `sandbox_platform/queue/client.py` | 📋 Belum |
| `sandbox_platform/session/manager.py` | 📋 Belum |
| `sandbox_platform/router/` | 📋 Belum |
| `sandbox_platform/artifacts/store.py` | 📋 Belum |
| `sandbox_platform/runtime/firecracker/` | 📋 Belum |
| `sandbox_platform/runtime/wasm/` | 📋 Belum |
| `sandbox_platform/runtime/gui/` | 📋 Belum |
| `cmd/platform_api.py` (FastAPI) | 📋 Belum |
| `cmd/fc_agent.py` | 📋 Belum |
| `cmd/wasm_agent.py` | 📋 Belum |
| Hapus file Go | 📋 Belum (menunggu test hijau) |

## Fitur Lanjutan (Spec Selesai, Belum Diimplementasi)

| Fitur | Spec | Implementasi |
|-------|------|-------------|
| Consul service discovery | ✅ | 📋 |
| HAProxy load balancing | ✅ | 📋 |
| Auto-scaling | ✅ | 📋 |
| Package management API | ✅ | 📋 |
| TAP device naming | ✅ | 📋 |
| MAC address generation | ✅ | 📋 |
| mTLS | ✅ | 📋 |
| Session mapping Consul KV | ✅ | 📋 |

## Infrastructure

| Komponen | Status |
|----------|--------|
| Nomad cluster (3 nodes) | ✅ Scripts tersedia |
| PostgreSQL | ✅ Docker Compose tersedia |
| Redis | ✅ Docker Compose tersedia |
| MinIO | ✅ Docker Compose tersedia |

## Yang Bisa Dijalankan Sekarang

```bash
# Test snapshot builder (tanpa KVM)
bash tools/snapshot-builder/test/test-snapshot-builder.sh

# Test fc pipeline (unit mode)
bash sandbox-platform/scripts/test-fc-pipeline.sh --unit

# Build semua binary Go (sebelum migrasi selesai)
cd sandbox-platform && go build ./...

# Jalankan dev environment (Go, sebelum migrasi)
cd sandbox-platform && make dev
```
