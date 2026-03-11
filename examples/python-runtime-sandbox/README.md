# Python Runtime Sandbox on Nomad

This example is the Nomad equivalent of the older kind-style sandbox smoke test.

It does the following:

1. Starts a local Nomad cluster if `NOMAD_ADDR` is not reachable.
2. Builds the `sandbox-platform` binaries.
3. Starts PostgreSQL, Redis, and MinIO with `docker compose` when needed.
4. Builds Firecracker Python snapshot assets when Linux + KVM prerequisites are present.
5. Falls back to placeholder snapshot artifacts and `FC_MODE=sim` when real Firecracker prerequisites are missing.
6. Submits `fc-agent` to Nomad using [`sandbox-python.nomad.hcl.tpl`](/Users/annas/Desktop/code/platform-docs/examples/python-runtime-sandbox/sandbox-python.nomad.hcl.tpl).
7. Starts `platform-api` locally if it is not already running.
8. Executes a `python_run` request and verifies the response.
9. Cleans up only the resources started by the script.

## Files

- [`run-test-nomad.sh`](/Users/annas/Desktop/code/platform-docs/examples/python-runtime-sandbox/run-test-nomad.sh) — main example runner
- [`sandbox-python.nomad.hcl.tpl`](/Users/annas/Desktop/code/platform-docs/examples/python-runtime-sandbox/sandbox-python.nomad.hcl.tpl) — Nomad job template for `fc-agent`
- [`python-runtime.env`](/Users/annas/Desktop/code/platform-docs/examples/python-runtime-sandbox/python-runtime.env) — snapshot-builder config used by the example

## Run

```bash
./run-test-nomad.sh
```

## Optional Environment Variables

- `NOMAD_ADDR` — Nomad HTTP API address. Default: `http://127.0.0.1:4646`
- `API_URL` — Platform API base URL. Default: `http://127.0.0.1:8080`
- `FC_MODE` — `real`, `sim`, or unset for auto-detect
- `FC_KERNEL_PATH` — kernel path for real snapshot builds. Default: `/opt/platform/test-assets/vmlinux-hello`
- `DOWNLOAD_KERNEL` — set to `true` to let snapshot-builder fetch a kernel when `FC_KERNEL_PATH` is absent
- `SNAPSHOT_NAME` — override the snapshot name from [`python-runtime.env`](/Users/annas/Desktop/code/platform-docs/examples/python-runtime-sandbox/python-runtime.env)

## Notes

- This repository is Nomad-first. There is no Kubernetes controller flow to mirror directly.
- In this repo, the closest equivalent to the original "sandbox controller" is `platform-api` plus a Nomad-scheduled `fc-agent`.
- Real Firecracker execution still requires Linux, `/dev/kvm`, Firecracker, and snapshot assets. The example keeps working in `sim` mode for local verification.
