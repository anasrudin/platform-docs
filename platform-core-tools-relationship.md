# platform-core ↔ platform-tools — Hubungan & Deployment

---

## Jawaban Singkat

> **Tools di-deploy di infra yang sama (kluster GKE yang sama), tapi sebagai workload terpisah yang dikelola oleh platform-core.**
>
> platform-core adalah **otak** (routing, scheduling, queue, auth).
> platform-tools adalah **otot** (container images & WASM binaries yang benar-benar menjalankan kode).

---

## Gambaran Besar

```
┌─────────────────────────────────────────────────────────────────────┐
│                         GKE Cluster                                 │
│                                                                     │
│  ┌──────────────────────────────┐                                   │
│  │      platform-core           │  ← Long-running Deployments       │
│  │                              │    (selalu hidup)                  │
│  │  • gateway (Deployment)      │                                   │
│  │  • orchestrator (Deployment) │                                   │
│  │  • wasm-worker (Deployment)  │                                   │
│  └──────────┬───────────────────┘                                   │
│             │ creates & manages                                      │
│             ▼                                                        │
│  ┌──────────────────────────────┐                                   │
│  │   agent-sandbox CRDs         │  ← Sandbox/SandboxClaim/WarmPool  │
│  │   (kubernetes-sigs)          │    dikelola oleh agent-sandbox     │
│  │                              │    controller                      │
│  │  • SandboxWarmPool           │                                   │
│  │    └── pre-warmed pods       │  ← Pod berisi IMAGE dari           │
│  │         (platform-tools      │    platform-tools repo             │
│  │          container images)   │                                   │
│  └──────────────────────────────┘                                   │
│                                                                     │
│  ┌──────────────────────────────┐                                   │
│  │   Shared Infra               │                                   │
│  │  • PostgreSQL 16             │                                   │
│  │  • Redis Streams 7           │                                   │
│  │  • MinIO / GCS               │                                   │
│  └──────────────────────────────┘                                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Apa Itu platform-core vs platform-tools?

| Aspek | platform-core | platform-tools |
|---|---|---|
| **Tipe** | Go services (binaries) | Container images + WASM binaries |
| **Deploy sebagai** | K8s `Deployment` (long-running) | Pod di dalam `Sandbox` CRD (ephemeral) |
| **Siapa yang jalankan** | Deploy manual / ArgoCD | Dijalankan oleh platform-core via agent-sandbox |
| **Berapa lama hidup** | Selamanya (selalu running) | Seumur satu job (dibuat saat ada request, dihapus setelah selesai) |
| **Yang disimpan di repo** | Go source code | Python/Node/Dockerfile + WASM source |
| **Output artifact** | Docker image `platform/gateway`, `platform/orchestrator` | Docker image per tool + `.wasm` binary per tool |
| **Komunikasi** | HTTP REST + Redis Streams + PostgreSQL | gRPC port 50051 (menerima perintah dari platform-core) |

---

## Flow Lengkap: Request → Eksekusi

```
Agent / Client
     │
     │ POST /v1/execute
     │ { "tool": "python_run", "tier": "headless", "input": {...} }
     ▼
┌─────────────────────────────────────────────────────────────────────┐
│  [platform-core] API Gateway                                        │
│  • Validasi JWT                                                     │
│  • Rate limit cek                                                   │
│  • Simpan job ke PostgreSQL (status=pending)                        │
│  • XADD ke Redis stream "code-jobs"                                 │
│  • Return: { "job_id": "abc-123" } HTTP 202                         │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ Redis Stream
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  [platform-core] Orchestrator                                       │
│  • XREADGROUP dari "code-jobs"                                      │
│  • Pilih SandboxTemplate berdasarkan tier + phase                   │
│  • Step 1: Buat SandboxClaim → agent-sandbox allocate warm pod      │
│                                                                     │
│    SandboxWarmPool "code-headless-runc-pool"                        │
│    ┌──────────┐  ┌──────────┐  ┌──────────┐                        │
│    │ Pod (idle)│  │ Pod (idle)│  │ Pod (idle)│  ← image dari        │
│    │python_run │  │python_run │  │python_run │    platform-tools    │
│    └──────────┘  └──────────┘  └──────────┘                        │
│         │                                                           │
│         │ SandboxClaim "job-abc-123" → allocate Pod #1              │
│         ▼                                                           │
│    Pod #1 (allocated, image: gcr.io/platform/python_run:latest)     │
│         │                                                           │
│  • Step 2: Inject artifact URLs sebagai env vars ke pod             │
│  • Step 3: Mount skill (Phase 2: sudah baked di image)              │
│  • Step 4: gRPC dial → Execute({ input_json })                      │
│  • Step 5: Collect output → upload ke MinIO                         │
│  • Delete SandboxClaim → pod kembali ke pool (atau dihapus)         │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ gRPC :50051
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  [platform-tools] Pod: python_run                                   │
│  • runner.py: gRPC ExecutionService server                          │
│  • Terima ExecuteRequest { input_json }                             │
│  • Jalankan tool.py:run(input_data)                                 │
│  • Return ExecuteResult { stdout, stderr, exit_code }               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Bagaimana Tools Di-deploy ke Kluster?

Tools **tidak** di-deploy sebagai Deployment biasa. Mereka di-deploy sebagai **container images** yang dimuat oleh `SandboxTemplate` dan `SandboxWarmPool`.

### Alur deploy tool baru:

```
Developer push kode tool
         │
         ▼
platform-tools CI/CD (.github/workflows/ci.yml)
         │
         ├── pytest test/           ← unit test
         │
         ├── docker build           ← build image
         │
         └── docker push gcr.io/platform/python_run:sha-abc123
                   │
                   ▼
         UPDATE tools table di PostgreSQL:
         UPDATE tools SET container_image = 'gcr.io/platform/python_run:sha-abc123'
         WHERE tool_name = 'python_run';
                   │
                   ▼
         UPDATE SandboxTemplate di K8s:
         kubectl patch sandboxtemplate code-headless-runc \
           -p '{"spec":{"podTemplate":{"spec":{"containers":[{"name":"tool-runner","image":"gcr.io/platform/python_run:sha-abc123"}]}}}}'
                   │
                   ▼
         SandboxWarmPool detects image change
         → rolling replace pre-warmed pods dengan image baru
         → pool kembali siap dalam ~30 detik
```

---

## Siapa yang Punya Akses ke Apa?

```
platform-core Orchestrator
    │
    ├── BACA tools table (PostgreSQL)
    │     → "python_run pakai image apa?"
    │     → "timeout berapa?"
    │
    ├── CREATE / DELETE SandboxClaim (K8s API)
    │     → agent-sandbox alokasikan pod dari WarmPool
    │
    ├── PATCH SandboxTemplate (K8s API)
    │     → update image setelah CI push baru
    │
    └── gRPC → pod (platform-tools image)
          → kirim ExecuteRequest
          → terima ExecuteResult

platform-tools Pod (saat running)
    │
    ├── TIDAK punya akses ke PostgreSQL
    ├── TIDAK punya akses ke Redis
    ├── TIDAK punya akses ke K8s API
    └── HANYA listen di gRPC :50051
          dan baca/tulis ke /workspace/ volume
```

> **Prinsip least-privilege:** Tools pod hanya tahu cara menjalankan satu pekerjaan dan menjawab lewat gRPC. Semua orchestration ada di platform-core.

---

## Struktur Image per Tier

### Tier 1 — WASM (tidak ada pod, in-process)

```
platform-core wasm-worker Deployment
     │
     └── Wasmtime runtime (in-process)
              │
              └── load .wasm binary dari MinIO
                    artifacts/python_snippet.wasm
                    artifacts/json_parser.wasm
                    ...

Tidak ada pod K8s. Eksekusi terjadi langsung dalam proses wasm-worker.
```

### Tier 2 — Headless (satu image per tool)

```
SandboxTemplate "code-headless-runc"
     │
     └── image: gcr.io/platform/tool-runner-base:latest
              (image generik, berisi semua tools)

   ATAU (versi optimal):

SandboxTemplate "code-headless-python_run"
     │
     └── image: gcr.io/platform/python_run:latest
              (image spesifik per tool, lebih kecil)
```

> **Rekomendasi Phase 2:** Gunakan satu image `tool-runner` generik yang berisi semua Tier 2 tools. Lebih mudah di-maintain. Phase 3+: pisahkan per tool untuk isolasi lebih ketat.

### Tier 3 — GUI (satu image besar)

```
SandboxTemplate "desktop-kata-fc"
     │
     └── image: gcr.io/platform/desktop-runner:latest
              (Ubuntu 22.04 + Xvfb + XFCE + Playwright + scrot + xdotool)
              Semua 8 tool Tier 3 ada dalam satu image ini.
              Tool dipilih berdasarkan field "tool_name" di ExecuteRequest.
```

---

## Namespace dan Network Policy

```
Namespace: default (atau: platform-system)
                │
    ┌───────────┼───────────┐
    │           │           │
 gateway    orchestrator  wasm-worker
    │           │
    │     ┌─────┴──────────────────────┐
    │     │  Sandbox pods              │
    │     │  (platform-tools images)   │
    │     │                            │
    │     │  NetworkPolicy:            │
    │     │  • ingress: hanya dari     │
    │     │    orchestrator (port 50051)│
    │     │  • egress Tier 1/2:        │
    │     │    BLOCK (no internet)     │
    │     │  • egress Tier 3:          │
    │     │    ALLOW (Playwright needs │
    │     │    internet untuk browser) │
    └─────┴────────────────────────────┘
```

---

## Dua Repo, Satu Kluster — Aturan Mainnya

| Aturan | Penjelasan |
|---|---|
| platform-core di-deploy duluan | Tanpa gateway + orchestrator, tools tidak bisa dipanggil |
| platform-tools images harus tersedia di GCR sebelum WarmPool dibuat | Kalau image tidak ada, pod akan ImagePullBackOff |
| SandboxTemplate menjadi "kontrak" antara dua repo | platform-core hanya perlu tahu nama template, bukan detail image |
| Rolling update tool = update image di SandboxTemplate | platform-core tidak perlu restart saat tools update |
| WASM binaries disimpan di MinIO, bukan di image | wasm-worker pull `.wasm` dari MinIO saat pertama kali dibutuhkan, lalu cache |

---

## Dependency Graph Saat Deploy

```
1. Infra (Terraform)
   └── GKE cluster + PostgreSQL + Redis + MinIO + Vault

2. agent-sandbox operator
   └── kubectl apply manifest.yaml + extensions.yaml

3. platform-tools CI
   └── push images ke GCR
   └── upload .wasm ke MinIO

4. platform-core (ArgoCD atau Helm)
   └── apply config/crd/sandbox_templates.yaml   ← referensi tools images
   └── apply config/crd/sandbox_warm_pools.yaml  ← buat pre-warmed pods
   └── apply config/rbac/
   └── deploy gateway + orchestrator + wasm-worker

5. Sistem siap menerima request
```

> **Kalau urutannya salah:** Step 4 sebelum Step 3 → WarmPool pods `ImagePullBackOff`. Step 2 sebelum Step 1 → CRD tidak tersedia. Selalu ikuti urutan ini saat first-deploy.

---

## Ringkasan Satu Kalimat

> platform-tools adalah kumpulan **container image dan WASM binary** yang di-host di GCR/MinIO, dijalankan secara ephemeral oleh platform-core di dalam **Sandbox pods** yang dikelola `kubernetes-sigs/agent-sandbox` — keduanya hidup di kluster yang sama, tapi di layer abstraksi yang berbeda.
