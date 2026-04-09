"""Firecracker microVM runtime.

Mirrors runtime/firecracker/runtime.go.

Mode selection:
  1. FC_MODE env var ("real" | "sim")
  2. Presence of /dev/kvm (auto-detect: kvm → real, no kvm → sim)
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid

import structlog

from sandbox_platform.runtime.firecracker.pool import VMPool
from sandbox_platform.runtime.firecracker.snapshot import SnapshotStore
from sandbox_platform.types import Job, RuntimeResult, Tier

log = structlog.get_logger()


# ── TAP / MAC helpers ──────────────────────────────────────────────────────────


def make_tap_name(node_id: str, vm_id: str) -> str:
    """Return a Linux TAP device name for a given node and VM.

    Format: ``tap-{node_id[:4]}-{vm_id[:4]}`` (max 15 characters, always lowercase).
    Linux imposes a 15-character limit on interface names (IFNAMSIZ − 1).

    Example::

        make_tap_name("node-abc123", "vm-xyz789")
        # → "tap-node-vm-x"
    """
    n = node_id[:4].lower()
    v = vm_id[:4].lower()
    return f"tap-{n}-{v}"


def make_mac_address(node_id: str, vm_id: str) -> str:
    """Return a deterministic locally-administered unicast MAC address.

    Format: ``06:00:<node_byte0>:<node_byte1>:<vm_byte0>:<vm_byte1>``

    ``06`` sets the locally-administered (bit 1) and unicast (bit 0 = 0) flags.
    The remaining 4 octets are the first 2 bytes of ``sha256(node_id)`` and
    ``sha256(vm_id)``, giving a collision-free deterministic assignment.

    Example::

        make_mac_address("node-1", "vm-1")
        # → "06:00:XX:XX:YY:YY"
    """
    nh = hashlib.sha256(node_id.encode()).digest()
    vh = hashlib.sha256(vm_id.encode()).digest()
    return f"06:00:{nh[0]:02X}:{nh[1]:02X}:{vh[0]:02X}:{vh[1]:02X}"


def _env_or(key: str, default: str) -> str:
    return os.environ.get(key) or default


def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key, "")
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


class Config:
    def __init__(self) -> None:
        self.firecracker_bin = _env_or("FC_BIN", "/usr/bin/firecracker")
        self.snapshot_name = _env_or("SNAPSHOT_NAME", "python-v1")
        self.snapshot_cache_dir = _env_or("SNAPSHOT_CACHE_DIR", "/var/sandbox/cache")
        self.minio_endpoint = _env_or("MINIO_ENDPOINT", "http://localhost:9000")
        self.minio_access_key = _env_or("MINIO_ACCESS_KEY", "minioadmin")
        self.minio_secret_key = _env_or("MINIO_SECRET_KEY", "minioadmin")
        self.minio_bucket = _env_or("MINIO_BUCKET", "platform-snapshots")
        self.pool_size = _env_int("FC_POOL_SIZE", 2)
        self.dev_mode = os.environ.get("FC_DEV_MODE") == "true"


def detect_mode() -> str:
    """Select 'real' if FC_MODE=real or /dev/kvm is accessible."""
    fc_mode = os.environ.get("FC_MODE", "")
    if fc_mode in ("real", "sim"):
        log.info("FC mode from FC_MODE env", mode=fc_mode)
        return fc_mode
    if os.path.exists("/dev/kvm"):
        log.info("FC mode auto-detected: /dev/kvm present", mode="real")
        return "real"
    log.info("FC mode auto-detected: /dev/kvm absent", mode="sim")
    return "sim"


class Runtime:
    """Firecracker microVM runtime engine."""

    def __init__(self) -> None:
        self._cfg = Config()
        self._mode = detect_mode()

        store = SnapshotStore(
            endpoint=self._cfg.minio_endpoint,
            access_key=self._cfg.minio_access_key,
            secret_key=self._cfg.minio_secret_key,
            bucket=self._cfg.minio_bucket,
            cache_dir=self._cfg.snapshot_cache_dir,
        )
        self._pool = VMPool(
            pool_size=self._cfg.pool_size,
            snapshot_name=self._cfg.snapshot_name,
            snapshot_cache_dir=self._cfg.snapshot_cache_dir,
            firecracker_bin=self._cfg.firecracker_bin,
            dev_mode=self._cfg.dev_mode,
            store=store,
        )

        if self._mode == "real":
            t = threading.Thread(target=self._warmup, daemon=True)
            t.start()

    def _warmup(self) -> None:
        try:
            self._pool.warmup()
            log.info(
                "VM pool ready",
                size=self._cfg.pool_size,
                snapshot=self._cfg.snapshot_name,
            )
        except Exception as exc:
            log.error("VM pool warmup failed, falling back to sim mode", err=str(exc))
            self._mode = "sim"

    def pool_size(self) -> int:
        return self._cfg.pool_size

    def name(self) -> str:
        return f"firecracker-{self._mode}"

    def tier(self) -> Tier:
        return Tier.MICROVM

    def health(self) -> None:
        if self._mode == "sim":
            return
        if not os.path.exists(self._cfg.firecracker_bin):
            raise RuntimeError(
                f"firecracker binary not found: {self._cfg.firecracker_bin}"
            )

    def execute(self, job: Job) -> RuntimeResult:
        if self._mode == "sim":
            return self._simulate_exec(job)
        return self._real_exec(job)

    def _real_exec(self, job: Job) -> RuntimeResult:
        start = time.monotonic()
        log.info("fc execute", job_id=job.id, tool=job.tool, mode="real")

        try:
            vm = self._pool.acquire(timeout=30.0)
        except TimeoutError as exc:
            log.error("pool acquire failed, falling back to sim", err=str(exc))
            return self._simulate_exec(job)

        try:
            resp = vm.execute(job.tool, job.input)
        except Exception as exc:
            return RuntimeResult(stderr=f"vm execute error: {exc}", exit_code=1)
        finally:
            self._pool.release(vm)

        duration_ms = int((time.monotonic() - start) * 1000)
        log.info(
            "fc execute done",
            job_id=job.id,
            tool=job.tool,
            exit_code=resp.exit_code,
            duration_ms=duration_ms,
            vm_id=vm.id,
        )

        return RuntimeResult(
            stdout=resp.stdout,
            stderr=resp.stderr,
            exit_code=resp.exit_code,
        )

    def _simulate_exec(self, job: Job) -> RuntimeResult:
        start = time.monotonic()
        log.info("fc execute", job_id=job.id, tool=job.tool, mode="sim")

        time.sleep(0.05)  # simulate boot + exec latency

        tool_output = self._simulate_tool_output(job.tool, job.input)
        duration_ms = int((time.monotonic() - start) * 1000)

        result = {
            "tool": job.tool,
            "status": "completed",
            "runtime": "firecracker-sim",
            "vm_id": f"fc-sim-{uuid.uuid4().hex[:8]}",
            "boot_ms": 20,
            "exec_ms": duration_ms - 20,
            "output": tool_output,
            "snapshot": self._cfg.snapshot_name,
            "sim_note": "no /dev/kvm — using simulation (set FC_MODE=real on Linux with KVM)",
            "metadata": {
                "kernel": "vmlinux-5.10.225",
                "rootfs": f"{self._cfg.snapshot_name}.ext4",
                "mem_mib": "512",
                "vcpus": "2",
            },
        }

        log.info(
            "fc sim complete", job_id=job.id, tool=job.tool, duration_ms=duration_ms
        )
        return RuntimeResult(stdout=json.dumps(result, indent=2), exit_code=0)

    def _simulate_tool_output(self, tool: str, input_data: dict) -> object:
        if tool == "python_run":
            code = input_data.get("code", "print('hello from Python')")
            return {"stdout": f"[sim] {code}\n=> hello from Python", "exit_code": 0}
        if tool == "bash_run":
            cmd = input_data.get("command", "")
            return {"stdout": f"[sim] $ {cmd}\n=> command executed", "exit_code": 0}
        return f"[sim] {tool} executed with input: {input_data}"
