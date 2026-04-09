---
title: Firecracker Runbook Design
date: 2026-04-10
status: approved
---

# Firecracker Runbook Design

## Goal

Produce two standalone runbooks for developers who want to:
1. Set up the repo locally
2. Start infrastructure
3. Build a Firecracker snapshot from scratch (and load an existing one)
4. Deploy the sandbox-worker Nomad job
5. Run Python code end-to-end via the platform API

## Output Files

| File | Platform |
|------|----------|
| `docs/how-to/firecracker-runbook-macos.md` | macOS — sim mode, no KVM |
| `docs/how-to/firecracker-runbook-linux.md` | Linux + KVM — real mode |

## Audience

Developers running locally. Not operators deploying to production clusters.

## Approach

Two separate files (Opsi C). Steps identical across platforms are written independently in each file — no cross-referencing. Platform-specific steps (KVM, FC_MODE, real vs sim snapshot) are written for that platform only.

## Section Structure (both files)

Each section follows: **prereq → command → expected output → troubleshoot**.

### 1. Prerequisites
- Python 3.12+, Docker + Docker Compose, uv, jq, Nomad CLI
- macOS: no KVM needed, FC_MODE=sim
- Linux: /dev/kvm must exist, FC_MODE=real

### 2. Clone & Install
- `git clone`, `uv pip install -e ".[dev]"`
- Verify: `pytest --collect-only`, `platform-api --help`

### 3. Start Infrastructure
- `make dev` — starts PostgreSQL, Redis, MinIO via Docker Compose
- Verify: `curl localhost:8080/health`

### 4. Build Snapshot from Scratch
- macOS: sim mode — snapshot is written as mock JSON to MinIO bucket `platform-snapshots/{name}/`
- Linux: real mode — boot microVM, install Python inside guest, save vmstate.bin + memory.bin + meta.json to MinIO via SnapshotDownloader

### 5. Load Existing Snapshot from MinIO
- Use SnapshotDownloader.load() to pull snapshot from MinIO by name
- Verify: snapshot files present in local cache dir

### 6. Deploy Nomad Job
- `nomad job run services/controller/nomad/jobs/sandbox-worker.nomad`
- Verify: `nomad job status sandbox-worker`, fc-agent allocation running

### 7. Run Python Code End-to-End
- `POST /sessions` with `{"runtime": "microvm"}`
- `POST /execute` with `{"session_id": "...", "tool": "python_run", "input": {"code": "print('hello')"}}`
- Verify: response contains `"output": "hello\n"`

### 8. Cleanup
- `make stop`, `nomad job stop sandbox-worker`

## Platform Differences Summary

| Step | macOS | Linux + KVM |
|------|-------|-------------|
| KVM check | skip | `/dev/kvm` must exist |
| FC_MODE | `sim` | `real` |
| Snapshot build | mock output, JSON meta | real vmstate.bin + memory.bin |
| Nomad fc-agent execution | simulated | real microVM |
| Nomad driver | raw_exec (sim binary) | raw_exec (/usr/local/bin/fc-agent) |

## Constraints

- Nomad must be installed locally (`nomad agent -dev` for single-node dev)
- MinIO must be running before snapshot operations
- sandbox-worker Nomad job uses `raw_exec` driver for fc-agent — requires fc-agent binary on PATH
- Linux runbook assumes KVM is enabled (`ls /dev/kvm` must succeed)
