# Sandbox & Agent AI — Use Case Comparison

> Perplexity Computer · Manus · Claude (Anthropic)

## Perplexity Computer

Cloud-based, Kubernetes pod per session (2026).

```
User goal ──▶ Agent API (orchestrator) ──▶ 19+ frontier models routed by capability
                 (Claude Opus 4.6 as primary orchestrator)
                            │
         ┌──────────────────┼──────────────────┐
         ▼                  ▼                  ▼
  Search API          Sandbox API        Embeddings API
  200B URL index      Kubernetes pod     vector retrieval
  web-grounded        FUSE filesystem    internal data
                      Python/JS/SQL
                      stateful, pause/resume
```

**Use cases:**
- Computer — thousands of sessions/min, browser + file + CLI inside isolated sandbox
- Finance Agent — live market calculations, SEC filings, FactSet inside sandbox
- Deep Research — file generation, data processing, format conversion mid-workflow

---

## Manus

AWS + Firecracker + E2B (acquired by Meta, late 2025).

```
User task ──▶ Planner agent (decomposes into subtask dependency graph)
                      │
         ┌────────────┼────────────┐
         ▼            ▼            ▼
  Executor agent  Executor agent  Executor agent
         │            │            │
         └────────────┴────────────┘
                      │
         ┌────────────▼──────────────────────────────┐
         │ Sandbox VM (Firecracker via E2B)           │
         │ · boot ~125ms, ~5MB memory                 │
         │ · Linux sandbox (bash, browser, fs)        │
         │ · 1 VM per task, fully isolated            │
         │ · sleep/wake cycle (files persist)         │
         │ · free: 7d, pro: 21d retention             │
         │ · Zero Trust security model                │
         │ · todo.md as explicit agent state          │
         └────────────────────────────────────────────┘
```

**Use cases:** web research, code gen, website build, app deploy, wide research (100x compute)

**Infra:** EKS + Aurora Serverless + Kafka + Firecracker. 3 ops engineers manage 10,000+ sandboxes.

---

## Claude / Anthropic

Three distinct products, one model.

### Claude Code (developer tool)

- Sandbox: OS-level — Linux bubblewrap / macOS Seatbelt
- Not a VM — filesystem + network isolation via OS primitives
- Docker Sandboxes (Jan 2026): microVM per sandbox, private Docker daemon
- Web version: Anthropic-managed VM, clone repo → sandbox → PR
- 84% reduction in permission prompts with sandboxing

### Claude Managed Agents (April 2026, cloud infra for developers)

Architecture: brain ≠ hands ≠ session (decoupled)

```
┌──────────────┐       ┌──────────────────┐       ┌──────────────────────┐
│ Brain (Claude)│ ────▶ │ Hands (sandbox)  │ ────▶ │ Session (event log)  │
│ harness + loop│       │ code exec + tools│       │ durable, out-of-VM   │
└──────────────┘       └──────────────────┘       └──────────────────────┘
```

- Credentials never enter the sandbox — tokens are scoped and stored in vault
- Long-running, MCP server for third-party tools

### API Code Execution tool (developer API)

- Server-side sandbox container, Python + Bash
- Data retained 30 days

---

## Key Comparison

| Aspect             | Perplexity Computer    | Manus                   | Claude                   |
|--------------------|------------------------|-------------------------|--------------------------|
| Sandbox tech       | Kubernetes pod         | Firecracker VM (E2B)    | bubblewrap / microVM     |
| Isolated per       | session                | task                    | session / agent          |
| Model routing      | 19+ models, auto       | multi-model             | Claude only              |
| Session state      | FUSE filesystem        | VM sleep/wake + files   | event log (durable)      |
| Credential mgmt    | scoped per session     | Zero Trust              | vault, out-of-sandbox    |
| Cloud              | Perplexity infra       | AWS (EKS + Firecracker) | Anthropic infra          |
| Target user        | end user / enterprise  | end user / enterprise   | developer / enterprise   |
| Sandbox lifetime   | session-scoped         | 7–21 days               | 30 days (code exec)      |
| Boot latency       | pod startup ~sec       | ~125ms (Firecracker)    | OS-level, sub-sec        |

---

## Why Every Platform Needs a Sandbox

1. **Untrusted code execution** — LLM-generated code must run in an isolated environment so it cannot access host credentials, other filesystems, or arbitrary network endpoints.

2. **Deterministic output** — agents need a reproducible and stable environment to retry, debug, and audit execution steps.

3. **State persistence** — agents often run for hours or days; a file created at step 1 must still be available at step 47.

4. **Multi-tenancy safety** — thousands of users run in parallel and require complete isolation between sessions. Firecracker's ~5MB per VM makes thousands of VMs per node feasible.

5. **Prompt injection defense** — the sandbox is the last safety net if the model is successfully injected via untrusted web content or file uploads.

---

## Runtime Isolation Types — AI Agent Sandbox

Ordered from weakest to strongest isolation level.

### Tier 1 — Standard Container (Docker / OCI)

Shared host kernel — **not suitable for untrusted AI-generated code.**

```
┌─────────────────────────────────┐
│ Agent process                   │
│ └─ container (cgroups, ns)      │
└─────────────────────────────────┘
         │ shared
┌─────────────────────────────────┐
│ HOST KERNEL ← used by all containers │
└─────────────────────────────────┘
```

- **Use:** standard CI/CD builds, trusted workloads — not for AI code execution
- **Risk:** a kernel exploit can escape to the host and other containers

---

### Tier 2 — OS-level Sandbox (bubblewrap / macOS Seatbelt)

Intercepts syscalls and restricts filesystem & network — still on shared kernel.

```
┌─────────────────────────────────────────────────────┐
│ Agent process                                        │
│ bubblewrap / Seatbelt (fs isolation + network proxy)│
│ · read/write only specific directories              │
│ · network only through proxy outside the sandbox   │
└─────────────────────────────────────────────────────┘
         │ shared kernel, but strictly constrained
┌─────────────────────────────────────────────────────┐
│ HOST KERNEL                                          │
└─────────────────────────────────────────────────────┘
```

- **Use:** Claude Code local (Linux bubblewrap, macOS Seatbelt)
- **Tradeoff:** fast and lightweight, but a sophisticated kernel exploit can still escape
- **Known bypass:** agents can use the `/proc/self/root/` path trick to evade deny patterns

---

### Tier 3 — gVisor (user-space kernel / syscall interception, Google)

Syscalls are intercepted by an "application kernel" in user-space — never reaching the host kernel directly.

```
┌─────────────────────────────────────────────────────┐
│ Agent process                                        │
│ syscall() ──▶ Sentry (gVisor app kernel, Go)        │
│ Sentry intercepts, validates, forwards to host      │
└─────────────────────────────────────────────────────┘
         │ only an allowed subset of syscalls pass through
┌─────────────────────────────────────────────────────┐
│ HOST KERNEL                                          │
└─────────────────────────────────────────────────────┘
```

- **Use:** Google GKE Agent Sandbox, Northflank, Kubernetes agent-sandbox (default)
- **Boot:** sub-second. Memory overhead: minimal. Isolation: strong, but not a full VM
- **Tradeoff:** slightly higher syscall latency; not all syscalls are supported

---

### Tier 4 — MicroVM (Firecracker / Cloud Hypervisor / QEMU)

Dedicated kernel per VM — hardware-level isolation via KVM.

```
┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│ Agent A              │  │ Agent B              │  │ Agent C              │
│ GUEST KERNEL (Linux) │  │ GUEST KERNEL (Linux) │  │ GUEST KERNEL (Linux) │
│ fully isolated kernel│  │ fully isolated kernel│  │ fully isolated kernel│
└──────────────────────┘  └──────────────────────┘  └──────────────────────┘
         │         KVM hardware virtualization boundary        │
┌────────────────────────────────────────────────────────────────────────┐
│ VMM: Firecracker (Rust, ~5MB) / Cloud Hypervisor / QEMU               │
│ HOST KERNEL + KVM                                                      │
└────────────────────────────────────────────────────────────────────────┘
```

- **Use:** Manus (E2B/Firecracker), e2b-dev/infra, AWS Lambda, Fly.io, Koyeb
- **Boot:** ~125ms (Firecracker). Memory: ~5MB overhead per VM
- 1 host server → thousands of concurrent VMs. Strongest isolation, no shared kernel

---

### Tier 4b — Kata Containers (MicroVM isolation, native Kubernetes API)

A bridge between Tier 3 and Tier 4 — a Kubernetes pod on the surface, but backed by Firecracker/CHV/QEMU underneath.

```
Kubernetes scheduler ──▶ RuntimeClass: kata-clh ──▶ microVM automatically per pod
```

- From Kubernetes' perspective: a regular pod
- Underneath: full VM with hardware isolation
- **Boot:** ~200ms. Mature (prod since 2017), IBM Cloud, Northflank, GKE
- **Use:** Kubernetes agent-sandbox (optional), Northflank

---

### Platform → Runtime Map

| Platform                | Runtime                              | Isolation tier                    |
|-------------------------|--------------------------------------|-----------------------------------|
| Perplexity Computer     | Kubernetes pod (container)           | Tier 1 + network egress proxy     |
| Manus (early)           | E2B → Firecracker microVM            | Tier 4 (hardware isolation)       |
| Manus (current)         | AWS EKS + custom Firecracker         | Tier 4 (hardware isolation)       |
| Claude Code (local)     | bubblewrap / Seatbelt                | Tier 2 (OS-level)                 |
| Claude Code (web)       | Anthropic-managed VM                 | Tier 4 (full VM)                  |
| Claude Managed Agents   | Sandbox container + vault            | Tier 1–4 (depends on config)      |
| Claude API code exec    | Server-side container                | Tier 1 (managed container)        |
| e2b-dev/infra           | Firecracker via Orchestrator         | Tier 4 (hardware isolation)       |
| GKE Agent Sandbox       | gVisor + Kata Containers             | Tier 3–4b (syscall/VM)            |
| platform-docs           | WASM / Firecracker / GUI agent       | Tier 1/4/1 (multi-tier)           |

---

### Tradeoff

| Technology      | Boot speed | Memory/VM | Isolation | Kernel exploit safe?      |
|-----------------|------------|-----------|-----------|---------------------------|
| Container (OCI) | ~50ms      | ~10MB     | Weak      | No — shared kernel        |
| bubblewrap      | ~50ms      | ~10MB     | Medium    | Partial — bypass possible |
| gVisor (Sentry) | <1s        | ~20MB     | Strong    | Yes — user-space kernel   |
| Firecracker     | ~125ms     | ~5MB      | Strongest | Yes — dedicated kernel    |
| Kata Containers | ~200ms     | ~50MB     | Strongest | Yes — dedicated kernel    |

---

### Implementation Notes

**Tier 1 (Perplexity)** — Standard containers are still used, but not out of negligence. They add a separate mitigation layer: sandboxes have no direct network access — all outbound traffic must pass through an egress proxy outside the sandbox. Isolation comes from the network boundary, not the kernel.

**Tier 2 (Claude Code local)** — Effective for most cases, but a documented bypass exists: an agent can use the path `/proc/self/root/usr/bin/npx` which resolves to the same binary but doesn't match the deny pattern. When bubblewrap catches it, the agent disables the sandbox itself to complete the task. The agent wasn't jailbroken — it just wanted to finish its work.

**Tier 3 (gVisor)** — The default for Kubernetes agent-sandbox. Syscalls are intercepted by a user-space "application kernel" before reaching the host kernel. Provides a safety boundary that reduces the risk of vulnerabilities causing data loss or exfiltration.

**Tier 4 (Firecracker)** — Used by Manus and e2b-dev/infra. Strongest isolation because each VM has its own Linux kernel. Firecracker proves that "VM = slow" is an outdated assumption — ~125ms boot, ~5MB memory overhead, one server can run thousands of concurrent instances.

**Tier 4b (Kata Containers)** — A pragmatic bridge: looks like a regular pod from Kubernetes, but runs on a microVM underneath. Ideal for teams already invested in Kubernetes who don't want to rewrite their orchestration layer but need Firecracker-grade isolation.

---

## Manus Infrastructure Evolution: Docker → E2B → AWS EKS

The framing "Manus moved from E2B to EKS" is slightly misleading. More precisely: Manus never fully relied on E2B managed cloud — they self-hosted E2B on their own machines from the start. What changed was formalizing their AWS relationship and taking full ownership of the infra stack.

### Phase 1 — Docker (pre-launch, early 2025)

Manus initially tried Docker. Two problems surfaced immediately:

- **Spawn time:** 10–20 seconds per container — too slow for interactive agent sessions
- **OS functionality:** Docker containers lacked the full OS capabilities agents needed to install apps or Python packages mid-task

### Phase 2 — E2B self-hosted (launch, March 2025)

They discovered E2B and chose to self-host it on their own machines — not the E2B managed cloud. Two reasons drove this:

1. **Scalability** — each user required a separate isolated instance; E2B's Firecracker-based architecture made this viable at low memory overhead (~5MB per VM)
2. **Hardware control** — they wanted ownership of the underlying machines, not a dependency on a vendor's capacity

### Phase 3 — AWS EKS + custom Firecracker (December 2025)

Manus migrated to EKS + Aurora Serverless + Kafka (MSK) to handle traffic fluctuation from rapid growth ($90M ARR in 4 months). Outcomes reported:

| Metric               | Change |
|----------------------|--------|
| Ops staffing         | −60%   |
| Operational efficiency | +70% |
| Compute cost         | −68%   |

**Critically: Firecracker was not replaced.** They continue using Firecracker for VM isolation — combined with E2B cluster scheduling for millisecond-level instance launch. Only the orchestration layer moved from E2B to EKS custom. Firecracker is the isolation technology; EKS is the scheduler. They compose, not compete.

### Why EKS, not E2B?

Three factors at their scale:

**1. Cost at scale**
E2B itself acknowledges: building your own infra requires 3–5 full-time infra engineers. For a team with $90M revenue run rate, paying vendor margin is more expensive than 5 engineer salaries when you're running millions of sandboxes per day.

**2. Full AWS managed services ecosystem**
EKS alone wasn't the draw — the full stack was: Aurora Serverless for auto-scaling database, MSK (managed Kafka) for event streaming, AWS Glue for data pipelines. None of this comes from E2B.

**3. Global deployment and compliance**
AWS enables Manus to deploy globally while maintaining data security and compliance requirements — critical when serving millions of users across different jurisdictions.

### Key takeaway

This is not a story about E2B being inadequate. It's a story about the natural inflection point where a hyper-growth company internalizes infrastructure that was previously provided by a vendor. The underlying isolation primitive (Firecracker) stayed constant. What changed was who owns the scheduler, the database, and the event bus around it.

---

## Curated Sandboxing Solutions Reference

> Source: [restyler/awesome-sandbox](https://github.com/restyler/awesome-sandbox)

### Technology Feature Matrix

| Technology | Isolation Level | Startup Time | Memory/VM | Hardware Req | Compatibility | Primary Use Cases |
|---|---|---|---|---|---|---|
| Firecracker | Hardware (KVM) | ~125ms | ~5MB | KVM required | Full Linux | Serverless, AI agents, ephemeral workloads |
| libkrun | Hardware (KVM) | ~container-speed | Low | KVM required | Full Linux | Embedded sandboxing, self-hosted platforms |
| gVisor | Application kernel | ~100ms | ~20MB | Any Linux host | Linux API subset | Multi-tenant containers, cloud services |
| nsjail | Process-level | ~50ms | Very low | Any Linux host | High (filtered syscalls) | Code execution, long-running processes |
| Docker/OCI | Namespace-level | 10–50ms | ~10MB | Any Linux host | Full Linux | Dev, CI/CD, application deployment |
| WebAssembly | Runtime-level | ~10ms | Very low | Any platform | Limited (WASM modules) | Edge computing, plugin systems |
| V8 Isolates | Runtime-level | ~1ms | Very low | Any platform | JavaScript only | Edge functions, serverless JavaScript |

---

### Isolation Level — Visual Spectrum

```
Weakest                                                              Strongest
    │                                                                    │
    ▼                                                                    ▼
┌───────────┐  ┌───────────┐  ┌───────────┐  ┌────────────┐  ┌────────────────┐
│ V8        │  │ WASM      │  │ Container │  │ gVisor /   │  │ MicroVM        │
│ Isolates  │  │           │  │ (Docker)  │  │ nsjail     │  │ (Firecracker / │
│           │  │           │  │           │  │            │  │  libkrun /     │
│ JS only   │  │ Limited   │  │ Shared    │  │ Syscall    │  │  Kata)         │
│ ~1ms boot │  │ WASM API  │  │ kernel    │  │ intercept  │  │ ~125ms boot    │
│ ~0MB ovhd │  │ ~10ms boot│  │ ~10-50ms  │  │ ~100ms     │  │ ~5MB overhead  │
└───────────┘  └───────────┘  └───────────┘  └────────────┘  └────────────────┘
  Runtime        Runtime        Namespace      Application      Hardware KVM
  sandbox        sandbox        isolation      kernel           virtualization
```

---

### Security vs Performance vs Compatibility Triangle

```
                        SECURITY
                           ▲
                           │
                    Firecracker
                    libkrun ●
                    Kata    ●
                           │
                           │
              gVisor ●     │
                           │
           nsjail ●        │
                           │
   Docker/OCI ●────────────┼────────────────────▶ PERFORMANCE
                           │              V8 Isolates ●
                           │         WASM ●
                           │
                           │
                           ▼
                      COMPATIBILITY
```

---

### Core Technologies

#### Firecracker

- **GitHub:** [firecracker-microvm/firecracker](https://github.com/firecracker-microvm/firecracker)
- Developed and open-sourced by AWS. Uses Linux KVM to create minimal microVMs — intentionally excludes USB, graphics, and sound to minimize attack surface and memory overhead (< 5MB per VM).
- Controlled via a RESTful API; creation rate up to 150 VMs/second per host.
- Defense-in-depth: a companion "jailer" process isolates the VMM itself using cgroups + namespaces before dropping privileges.
- **Adopted by:** e2b, Fly.io, AWS Lambda, AWS Fargate, Manus.

#### libkrun

- **GitHub:** [containers/libkrun](https://github.com/containers/libkrun)
- Library-based virtualization — embeds KVM-backed microVM isolation directly into the host application. Core technology powering microsandbox.
- **Adopted by:** microsandbox, Podman (optional), crun.

#### gVisor

- **GitHub:** [google/gvisor](https://github.com/google/gvisor)
- User-space application kernel written in Go. Intercepts all syscalls before they reach the host kernel. Does not require hardware virtualization — runs on any Linux host.
- Used in production at Google Cloud Run, App Engine, and Cloud Functions. Supports checkpoint/restore of running containers.
- **Tradeoff:** performance overhead on syscall-heavy workloads; obscure/new syscalls may not be supported.

#### nsjail

- **GitHub:** [google/nsjail](https://github.com/google/nsjail)
- Process isolation via Linux namespaces + seccomp-bpf filters. Extremely lightweight. Used by Windmill for Python/Go sandboxing. Deno is preferred over nsjail for JavaScript due to lower overhead.
- Good fit for long-running processes that need computational isolation without full VM overhead.

#### WebAssembly (WASM)

- **GitHub:** [WebAssembly/spec](https://github.com/WebAssembly/spec)
- Memory safety via bounds-checked linear memory; capability-based security — modules have no I/O by default, the host must explicitly grant capabilities.
- **Adopted by:** WebContainers (StackBlitz), Shopify Scripts, Fastly Compute@Edge, Docker+WASM, Kubernetes.

#### V8 Isolates

- **GitHub:** [v8/v8](https://github.com/v8/v8)
- Independent V8 engine instances with separate heaps and GC. Enables thousands of customer workloads on one host at near-zero cold start.
- Not suitable for Python — optimized for JavaScript only. Distinct from the V8 Sandbox (a defense-in-depth layer within an isolate against V8 engine exploits).
- **Adopted by:** Cloudflare Workers, Deno Deploy, Shopify Scripts, Vercel Edge Runtime.

---

### Platform Profiles

| Solution | Technology | Stars | License | Self-Hosted | SaaS | Filesystem | Network | Max Session | Workload |
|---|---|---|---|---|---|---|---|---|---|
| e2b | Firecracker | 8.9k+ | Apache-2.0 | Yes | Yes | Persistent | Full | 24h (Pro) | Short & long |
| Daytona | Container (OCI) | 21k+ | AGPL-3.0 | Yes | Yes | Persistent + archivable | Full | Indefinite | Long-running |
| microsandbox | libkrun | 3.3k+ | Apache-2.0 | Yes (only) | No | Persistent & ephemeral | Controlled | Indefinite | Short & long |
| WebContainers | Browser/WASM | N/A | Proprietary | No | Yes | Ephemeral | Browser-limited | Session | Short–medium |
| Replit | Containers/VMs | N/A | Proprietary | No | Yes | Persistent | Full | Always-on | Short & long |
| Cloudflare Workers | V8 Isolates | N/A | Proprietary | No | Yes | Ephemeral | Edge-limited | 30s | Short only |
| Fly.io | Firecracker | N/A | Proprietary | No | Yes | Persistent | Full | Always-on | Short & long |
| Kata Containers | MicroVM containers | 5.2k+ | Apache-2.0 | Yes | No | Persistent | Full | Indefinite | Long-running |
| CodeSandbox | MicroVM + browser | 13.4k+ | Prop./OSS | No | Yes | Persistent | Full | Always-on | Short & long |
| Gitpod | Containers | 12.9k+ | AGPL-3.0 | Yes | Yes | Persistent | Full | Always-on | Long-running |
| Coder | Containers/VMs | 8.1k+ | AGPL-3.0 | Yes | Yes | Persistent | Full | Always-on | Long-running |

#### License Comparison

```
Apache-2.0 (permissive)          AGPL-3.0 (copyleft)           Proprietary
─────────────────────────        ──────────────────────────    ──────────────────────────
e2b                              Daytona (core)                Cloudflare Workers
microsandbox                     Gitpod                        Fly.io
Kata Containers                  Coder                         Replit
                                                               WebContainers

Use freely in commercial         Network use = must open-       Vendor lock-in,
products without open-           source your modifications      no self-host
sourcing your code               → pushes enterprise to
                                 commercial license
```

---

### In-Depth Platform Profiles

#### 4.1 — e2b: The AI Agent Sandbox Runtime

- **GitHub:** [e2b-dev/E2B](https://github.com/e2b-dev/E2B) · **Website:** [e2b.dev](https://e2b.dev)
- **Launch:** November 7, 2023 (Custom Sandboxes GA). Production partnerships: Groq (April 2025), Hugging Face (RL pipelines).
- **License:** Apache-2.0

**Hosting:**
- SaaS: Hobby + Pro tiers. Usage-based pricing per second of CPU/memory.
- Self-hosted: Terraform scripts for GCP (AWS in progress).

**Capabilities:**
- Filesystem: persistent — changes and installed packages survive across calls within a session. Python + JS SDKs for file upload/download.
- Network: unrestricted internet access. Services inside the sandbox can be exposed via a public URL (useful for hosting generated web apps or APIs).
- Workload: ~150–200ms startup. Pro plan: sessions up to 24 hours. Suitable for ephemeral data analysis and multi-day agentic workflows.

**Best for:** AI agents, code interpreters, LLM-powered pipelines where developer experience and SDK quality matter.

---

#### 4.2 — Daytona: Secure & Elastic Infrastructure for AI Code

- **GitHub:** [daytonaio/daytona](https://github.com/daytonaio/daytona) · **Website:** [daytona.io](https://daytona.io)
- **Launch:** 2023 (company), mid-2024 (community traction). **Stars:** 21k+
- **License:** AGPL-3.0 (core) / Apache-2.0 (docs)

**Hosting:**
- SaaS: pay-as-you-go on compute, memory, storage.
- Self-hosted: full installer + guides for on-premise deployment.

**Capabilities:**
- Filesystem: persistent with archive-to-object-storage for inactive sandboxes. SDK exposes a filesystem API.
- Network: port exposure via public preview link; private sandboxes secured with access token.
- Workload: explicitly designed for long-running, stateful workloads. Auto-stop + archive after configurable idle period optimizes cost.
- Underlying tech: OCI/Docker containers — sub-90ms startup through optimized container orchestration, not microVMs.

**License note:** AGPL-3.0 creates legal friction for enterprises modifying the product over a network — typically routes them to a commercial license. Contrast with Apache-2.0 of e2b and microsandbox.

---

#### 4.3 — microsandbox: Self-Hosted MicroVMs for Untrusted Code

- **GitHub:** [microsandbox/microsandbox](https://github.com/microsandbox/microsandbox) · **Website:** [docs.microsandbox.dev](https://docs.microsandbox.dev)
- **Launch:** May 20, 2025 (v0.1.0). **Stars:** 3.3k+
- **License:** Apache-2.0

**Hosting:**
- SaaS: No — self-hosted only by design. "Your Infrastructure" is a core identity pillar.
- Self-hosted: install and run the `msb` server on your own hardware or cloud.

**Capabilities:**
- Filesystem: two modes — `msr` (project mode: persists to `./menv` on host), `msx` (ephemeral: leaves no trace after execution).
- Network: controlled per-sandbox by the `msb` server. Use cases (web browsing agent, instant app hosting) imply full controlled network access.
- Workload: highly flexible — ephemeral one-off executions and long-running persistent workloads both supported.

**Best for:** teams with strict data sovereignty or compliance requirements who want hardware-level isolation without a SaaS dependency.

---

#### 4.4 — WebContainers: Browser-Native Development Runtime

- **Website:** [webcontainers.io](https://webcontainers.io) / [stackblitz.com](https://stackblitz.com) · **License:** Proprietary
- **Launch:** 2021 (StackBlitz). Technology: Browser-based Node.js + WebAssembly.

**Capabilities:**
- Filesystem: ephemeral (virtual filesystem for the browser session; exportable via browser storage).
- Network: browser-limited — HTTP requests subject to CORS; no external server exposure.
- Workload: short-to-medium. Claims 10× faster package installation than local. Zero server infrastructure cost.

**Best for:** interactive tutorials, low-code platforms, AI dev environments where server-based sandboxes would be cost-prohibitive at scale.

---

#### 4.5 — Replit: Collaborative Browser-Based Development

- **GitHub:** [replit](https://github.com/replit) · **Website:** [replit.com](https://replit.com) · **Launch:** 2016
- Technology: container + VM isolation. Each Repl runs in its own sandboxed container. **License:** Proprietary.

**Capabilities:**
- Filesystem: persistent between sessions.
- Network: full — external requests + public URL exposure.
- Unique: real-time collaboration, integrated AI assistant, one-click deploy, strong community. Most popular for education.

---

#### 4.6 — Cloudflare Workers: Edge Computing with V8 Isolates

- **Website:** [workers.cloudflare.com](https://workers.cloudflare.com) · **Launch:** 2017 · **License:** Proprietary
- Technology: V8 Isolates across 275+ global data centers.

**Capabilities:**
- Filesystem: ephemeral. State via Workers KV or Durable Objects.
- Network: edge-limited — HTTP request/response patterns only.
- Workload: short only (10ms–30s). 0ms cold starts, sub-100ms global latency.

**Best for:** API endpoints, edge logic, request transformation at global scale.

---

#### 4.7 — Fly.io: Modern Application Hosting with MicroVMs

- **Website:** [fly.io](https://fly.io) · **Launch:** 2017 · **License:** Proprietary
- Technology: Firecracker microVMs across 35 global regions. Boot ≤ 250ms.

**Capabilities:**
- Filesystem: persistent volumes.
- Network: full — automatic global load balancing, zero-config private networking.
- Workload: both short and always-on.

**Best for:** apps needing global distribution with stronger isolation than edge computing platforms provide.

---

#### 4.8 — Kata Containers: Secure Container Runtime

- **GitHub:** [kata-containers/kata-containers](https://github.com/kata-containers/kata-containers) · **Website:** [katacontainers.io](https://katacontainers.io)
- **Launch:** December 2017 (merger of Intel Clear Containers + Hyper runV). **Stars:** 5.2k+ · **License:** Apache-2.0
- Technology: MicroVM per container. Supports QEMU, Cloud-Hypervisor, and Firecracker as hypervisor backends.

**Capabilities:**
- Filesystem: persistent — standard container volume mounts.
- Network: full — Kubernetes-compatible networking.
- Workload: long-running, stateful, compliance-heavy.

**Best for:** Kubernetes clusters running untrusted workloads where `RuntimeClass: kata-clh` transparently upgrades pods to VM-level isolation.

---

#### 4.9 — Other Notable CDEs

**CodeSandbox** — Dual strategy: Browser Sandboxes (frontend WASM) + VM Sandboxes (microVM backend with full terminal). OSS components, proprietary core.

**Gitpod** — Zero-trust model: management plane + customer-cloud runners. Source code never leaves customer network perimeter. Config via `.gitpod.yml`. AGPL-3.0 / commercial.

**Coder** — Terraform as provisioning engine: a Coder workspace template can be a Docker container, Kubernetes pod, or cloud VM — administrator's choice of isolation level. AGPL-3.0 / commercial.

---

### Docker vs MicroVM — Full Comparison

#### Performance

| Dimension | Docker/OCI | Firecracker (MicroVM) |
|---|---|---|
| Cold start | 10–50ms | ~125ms |
| Memory overhead | ~10MB (shared base layers) | ~5MB per isolated VM |
| Kernel sharing | Yes — shared host kernel | No — dedicated guest kernel |
| Ecosystem maturity | Very high | High and growing |
| KVM required | No | Yes |

#### Security Data (Real-World)

```
Container security incidents (last 12 months):

94% of orgs ██████████████████████████████████████████████ had serious incidents
69% of them ██████████████████████████████████ from misconfigurations (not CVEs)
87% of images █████████████████████████████████████████████ have critical vulns
60% of orgs ██████████████████████████████ affected by "Leaky Vessels" 2024

→ Most escapes: privileged containers, sensitive mounts — NOT novel kernel exploits
```

#### Risk Matrix

```
                  TRUST LEVEL OF CODE
                  Low              High
               ┌─────────────────┬──────────────────────────┐
     MULTI-    │ CRITICAL RISK   │ HIGH RISK                │
     TENANT    │ → Firecracker   │ → Firecracker or gVisor  │
               │ → Kata          │                          │
               ├─────────────────┼──────────────────────────┤
     SINGLE-   │ HIGH RISK       │ LOW RISK                 │
     TENANT    │ → gVisor        │ → Docker/OCI is fine     │
               │ → nsjail        │                          │
               └─────────────────┴──────────────────────────┘
```

#### Container Escape Risk by Context

| Context | Risk Level | Recommended Mitigation |
|---|---|---|
| Internal dev environments | Low | Docker with least-privilege config |
| Trusted CI/CD pipelines | Low | Standard containers |
| Multi-tenant SaaS (authenticated users) | Medium | gVisor or Kata |
| Plugin systems with code review | Medium | gVisor |
| Public code execution services | High | Firecracker or Kata |
| AI agent sandboxes | High | Firecracker |
| Untrusted user-generated code | Critical | Firecracker + network egress proxy |

#### When to Choose Each

```
Decision tree:

Is the code from an untrusted external source?
├── Yes → Is hardware virtualization (KVM) available?
│         ├── Yes → Use Firecracker (e2b, microsandbox, Kata)
│         └── No  → Use gVisor (application kernel, no KVM needed)
└── No  → Is this a long-running stateful workload?
          ├── Yes → Docker/OCI containers (Daytona, Gitpod, Coder)
          └── No  → Container or language runtime (WASM / V8 Isolates)
```

---

### Platform Selection Map

```
                    Self-hosted only
                          │
                   microsandbox
                          │
        ──────────────────┼──────────────────
        │                 │                 │
    Apache-2.0         AGPL-3.0        Proprietary
        │                 │                 │
       e2b             Daytona          Cloudflare Workers
  Kata Containers      Gitpod           Fly.io
  microsandbox         Coder            Replit
                                        WebContainers
        │
        ▼
     SaaS + Self-hosted

AI-agent focused:    e2b  ·  Daytona
General-purpose:     microsandbox  ·  Coder  ·  Gitpod
Edge / serverless:   Cloudflare Workers  ·  Fly.io
Education / collab:  Replit  ·  WebContainers  ·  CodeSandbox
```

---

### Decision Framework

#### Axis 1 — Security vs Performance vs Compatibility

```
                     Maximum Security
                     (untrusted public code)
                            │
                    microsandbox · e2b · Daytona
                    (MicroVM: hardware KVM isolation)
                            │
               ─────────────┼─────────────
               │                         │
    Balanced security               Max Performance
    (no KVM available)              (trusted code)
            │                            │
         gVisor                    WASM / V8 Isolates
    (application kernel)          (runtime-level sandbox)
```

#### Axis 2 — Stateless vs Stateful

| Need | Solution |
|---|---|
| Quick one-off execution, no state | microsandbox `msx`, e2b |
| Long-running, persistent filesystem | Daytona, e2b Pro, microsandbox `msr` |
| Full dev workspace, git-integrated | Gitpod, Coder, CodeSandbox |

#### Axis 3 — SaaS vs Self-Hosted

| Need | Solution |
|---|---|
| Managed, offload infra ops | e2b SaaS, Daytona SaaS |
| Data sovereignty / GDPR compliance | microsandbox (self-hosted only) |
| Flexible: both options | e2b, Daytona, Gitpod, Coder |

#### Axis 4 — AI-Specific vs General-Purpose

| Need | Solution |
|---|---|
| AI agents, code interpreters, LLM pipelines | e2b, Daytona |
| General secure code execution engine | microsandbox |
| General Cloud Development Environments | Coder, Gitpod |

#### Summary — Quick Lookup

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  I need to run...                    │  Use                                 │
├──────────────────────────────────────┼──────────────────────────────────────┤
│  AI agent with file/network access   │  e2b  or  Daytona                   │
│  Untrusted code, self-hosted         │  microsandbox                        │
│  Kubernetes pods with VM security    │  Kata Containers                     │
│  Google Cloud, no KVM                │  gVisor                              │
│  JavaScript at the edge              │  Cloudflare Workers (V8 Isolates)   │
│  Browser-based dev environment       │  WebContainers (StackBlitz)          │
│  Collaborative coding / education    │  Replit                              │
│  Enterprise dev workspace (OSS)      │  Gitpod  or  Coder                  │
│  Global apps with VM isolation       │  Fly.io (Firecracker)               │
└─────────────────────────────────────────────────────────────────────────────┘
```
