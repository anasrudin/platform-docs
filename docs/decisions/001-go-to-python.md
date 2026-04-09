---
status: active
audience: contributors
last_updated: 2026-04-07
---

# ADR-001: Migrate codebase from Go to Python

- **Status:** Accepted
- **Date:** 2026-04-07
- **Deciders:** platform team

## Context and problem statement

The platform runtime was initially implemented in Go 1.25 across three runtime tiers (WASM, Firecracker microVM, GUI/Chromium). As the platform matured toward data-adjacent workloads and team velocity on Go tooling slowed, a migration was evaluated. Python 3.12+ with FastAPI offered better ecosystem fit for the execution environment, stronger library support for the artifact and queue layers, and reduced operational surface.

The Go implementation had reached a working state (91 tests passing, all three runtimes functional) before the migration decision was made. The decision was not driven by technical failure in Go, but by long-term maintainability and ecosystem alignment.

## Considered options

| Option | Summary |
|--------|---------|
| A | Remain on Go 1.25; continue building runtime features in Go |
| B | Migrate fully to Python 3.12+ with FastAPI + uvicorn |
| C | Polyglot: keep Go for hot-path runtimes, Python for API and orchestration layers |

## Decision outcome

**Chosen: Option B — Full Python migration** — team velocity, ecosystem alignment with data workloads, and lower toolchain complexity outweighed Go's performance advantage at this stage of the platform.

### Pros

- Single language across the entire codebase
- FastAPI + pydantic for typed API contracts with minimal boilerplate
- Strong library ecosystem: structlog, redis-py, minio SDK, httpx
- macOS dev with Linux production via sim/real mode split for Firecracker
- 91/91 tests ported and passing after migration

### Cons

- Python is slower than Go for CPU-bound work; acceptable at current scale
- Runtime-level concurrency model differs (asyncio vs goroutines)
- Migration required rewriting all service entry points and test suite

## Consequences

All new platform services must be written in Python 3.12+. The Go toolchain is no longer required. The `src/sandbox_platform/` package is the canonical implementation. Entry points live in `src/platform_cmd/`. Feature flags (`CONSUL_ENABLED`, `SCALER_ENABLED`, `MTLS_ENABLED`) default to off for safe local development. See `how-to/migrate-go-to-python.md` for the full migration record.
