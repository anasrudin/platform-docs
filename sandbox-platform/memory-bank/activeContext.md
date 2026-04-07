# Active Context

> Last updated: 2026-04-07

## Current Focus

**Language Migration: Go → Python** + **Spec-Driven Development setup**

Week 1 (Go) selesai. Sekarang masuk fase migrasi bahasa dan pengembangan fitur lanjutan dengan pendekatan spec-first.

## Status Migrasi Go → Python

| Komponen | Go (lama) | Python (baru) | Status |
|----------|-----------|---------------|--------|
| `pkg/types/` | `types.go` | `sandbox_platform/types.py` | 📋 Siap dimigrasikan |
| `internal/queue/` | `queue.go` | `sandbox_platform/queue/client.py` | 📋 Siap dimigrasikan |
| `internal/session/` | `manager.go` | `sandbox_platform/session/manager.py` | 📋 Siap dimigrasikan |
| `internal/router/` | `router.go` | `sandbox_platform/router/router.py` | 📋 Siap dimigrasikan |
| `internal/artifacts/` | `store.go` | `sandbox_platform/artifacts/store.py` | 📋 Siap dimigrasikan |
| `runtime/firecracker/` | `*.go` | `sandbox_platform/runtime/firecracker/*.py` | 📋 Siap dimigrasikan |
| `runtime/wasm/` | `runtime.go` | `sandbox_platform/runtime/wasm/runtime.py` | 📋 Siap dimigrasikan |
| `runtime/gui/` | `runtime.go` | `sandbox_platform/runtime/gui/runtime.py` | 📋 Siap dimigrasikan |
| `cmd/platform-api/` | `main.go` | `cmd/platform_api.py` (FastAPI) | 📋 Siap dimigrasikan |
| `cmd/fc-agent/` | `main.go` | `cmd/fc_agent.py` | 📋 Siap dimigrasikan |
| `cmd/wasm-agent/` | `main.go` | `cmd/wasm_agent.py` | 📋 Siap dimigrasikan |

## Fitur Berikutnya (Spec sudah ditulis)

| # | Fitur | Prioritas |
|---|-------|-----------|
| 1 | Consul service discovery + health checks | Tinggi |
| 2 | HAProxy load balancing | Tinggi |
| 3 | Auto-scaling berdasarkan pool metrics | Tinggi |
| 4 | Package management API (pip proxy) | Sedang |
| 5 | Node-aware TAP device naming | Sedang |
| 6 | Unique MAC address generation | Sedang |
| 7 | mTLS service-to-service | Tinggi |
| 8 | Session mapping di Consul KV | Tinggi |

## Dokumen Penting

- `docs/todo/todo-list.md` — Spec-Driven Development spec (8 fitur, acceptance criteria lengkap)
- `docs/migration/go-to-python.md` — Panduan migrasi dengan perintah shell step-by-step

## Keputusan Terbaru

- **Go → Python** — migrasi seluruh codebase ke Python 3.12+ (FastAPI, psycopg2, redis-py)
- **Spec-first** — setiap fitur wajib punya spec + acceptance criteria sebelum coding
- **Fase rollout** — Consul dulu (prereq), lalu HAProxy + session KV, lalu autoscaling, lalu mTLS terakhir

## Next Tasks

1. Jalankan perintah migrasi: `docs/migration/go-to-python.md` Langkah 1–4
2. Migrasikan file per file (mulai dari `types.py`, lalu `queue`, `session`, `router`)
3. Jalankan `pytest` setelah setiap modul selesai
4. Hapus file Go setelah semua test hijau
