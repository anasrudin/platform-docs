# Run Locally

| Field | Value |
|---|---|
| Status | Active |
| Audience | Contributors, operators |
| Scope | Local startup, validation, and shutdown for the sandbox environment |
| Last updated | March 11, 2026 |

## Objective

Use this guide to start the local sandbox, validate the core execution flow, and stop the environment cleanly.

## Prerequisites

- Go 1.21+
- Docker and Docker Compose
- Nomad
- `curl`
- `jq`

Example Nomad install on macOS:

```bash
brew tap hashicorp/tap
brew install hashicorp/tap/nomad
```

## Start the sandbox

From the repository root:

```bash
cd sandbox-platform
make dev
```

This starts:

- PostgreSQL
- Redis
- MinIO
- `platform-api`
- `wasm-agent`
- `fc-agent`
- `gui-agent`

The API should be available at `http://localhost:8080`.

## Validate the environment

Check the API:

```bash
curl -s http://localhost:8080/health | jq
```

Run the end-to-end smoke test:

```bash
cd sandbox-platform
./test-e2e.sh
```

The smoke test validates:

- API health
- Firecracker session creation
- Firecracker execution path
- WASM execution path
- GUI execution path

If you want real Wasmtime execution instead of simulation fallback, ensure the bucket referenced by `MINIO_WASM_BUCKET` exists. The current runtime default is `platform-modules`.

## Run with local Nomad

To run `fc-agent` through a local Nomad cluster:

```bash
cd sandbox-platform
make dev-nomad
```

The Nomad UI is available at `http://localhost:4646`.

## Stop the sandbox

```bash
cd sandbox-platform
make stop
```

## Common commands

| Command | Purpose |
|---|---|
| `make build` | Build `platform-api`, `wasm-agent`, `fc-agent`, and `gui-agent` |
| `make run` | Run the API and agents without starting container dependencies |
| `make clean` | Remove generated build and runtime outputs from `sandbox-platform/bin/` |
| `./test-e2e.sh` | Run the local end-to-end smoke test |

## Expected local behavior

- API health responds successfully on port `8080`
- queues and session flow work in the local sandbox
- WASM and Firecracker can use real execution paths when host capabilities and dependencies are present
- GUI currently remains a stubbed path in the local MVP
- real WASM execution also depends on a populated module bucket in MinIO

For the current architecture and maturity model, see [../reference/runtime-reference.md](../reference/runtime-reference.md).
