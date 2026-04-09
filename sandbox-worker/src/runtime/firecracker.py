"""Firecracker microVM runtime."""
from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from pathlib import Path

import structlog

from models.job import Job, RuntimeResult
from models.session import Tier

log = structlog.get_logger()


# ── TAP / MAC helpers ──────────────────────────────────────────────────────────

def make_tap_name(node_id: str, vm_id: str) -> str:
    """Return a Linux TAP device name (max 15 chars)."""
    n = node_id[:4].lower()
    v = vm_id[:4].lower()
    return f"tap-{n}-{v}"


def make_mac_address(node_id: str, vm_id: str) -> str:
    """Return a deterministic locally-administered unicast MAC address."""
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


# ── Config ─────────────────────────────────────────────────────────────────────

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


# ── Snapshot store ─────────────────────────────────────────────────────────────

@dataclass
class SnapshotMeta:
    name: str = ""
    version: str = ""
    kernel: str = ""
    rootfs: str = ""
    vcpus: int = 2
    mem_mib: int = 512
    created_at: datetime = field(default_factory=datetime.utcnow)
    dry_run: bool = False
    files: dict[str, str] = field(default_factory=dict)


@dataclass
class SnapshotPaths:
    state_file: str
    mem_file: str
    meta_file: str
    meta: SnapshotMeta = field(default_factory=SnapshotMeta)


def _download_file(url: str, dest: str) -> None:
    with urllib.request.urlopen(url) as resp:  # noqa: S310
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        with open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)


class SnapshotStore:
    def __init__(self, endpoint: str, access_key: str, secret_key: str,
                 bucket: str, cache_dir: str) -> None:
        self._endpoint = endpoint
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._cache_dir = cache_dir

    def ensure(self, name: str) -> SnapshotPaths:
        local_dir = os.path.join(self._cache_dir, name)
        paths = SnapshotPaths(
            state_file=os.path.join(local_dir, "vmstate.bin"),
            mem_file=os.path.join(local_dir, "memory.bin"),
            meta_file=os.path.join(local_dir, "meta.json"),
        )
        if all(os.path.exists(f) for f in (paths.state_file, paths.mem_file, paths.meta_file)):
            log.debug("snapshot cache hit", name=name)
            return self._load_meta(paths)
        log.info("snapshot not cached, downloading from MinIO", name=name)
        Path(local_dir).mkdir(parents=True, exist_ok=True)
        try:
            self._pull_from_minio(f"{self._bucket}/{name}/", local_dir)
        except Exception as mc_err:
            log.warning("mc pull failed, trying HTTP download", err=str(mc_err))
            self._http_download(name, paths)
        return self._load_meta(paths)

    def _pull_from_minio(self, prefix: str, dest_dir: str) -> None:
        mc = shutil.which("mc")
        if not mc:
            raise FileNotFoundError("mc not found in PATH")
        alias = f"fc-dl-{int(time.time() * 1e9)}"
        subprocess.run(
            [mc, "alias", "set", alias, self._endpoint,
             self._access_key, self._secret_key, "--quiet"],
            check=True, capture_output=True,
        )
        try:
            subprocess.run(
                [mc, "mirror", "--quiet", f"{alias}/{prefix}", dest_dir],
                check=True, capture_output=True,
            )
        finally:
            subprocess.run([mc, "alias", "remove", alias], capture_output=True)

    def _http_download(self, name: str, paths: SnapshotPaths) -> None:
        base = f"{self._endpoint}/{self._bucket}/{name}"
        for url, dest in {
            f"{base}/vmstate.bin": paths.state_file,
            f"{base}/memory.bin": paths.mem_file,
            f"{base}/meta.json": paths.meta_file,
        }.items():
            _download_file(url, dest)

    def _load_meta(self, paths: SnapshotPaths) -> SnapshotPaths:
        with open(paths.meta_file) as f:
            data = json.load(f)
        paths.meta = SnapshotMeta(
            name=data.get("name", ""),
            version=data.get("version", ""),
            kernel=data.get("kernel", ""),
            rootfs=data.get("rootfs", ""),
            vcpus=data.get("vcpus", 2),
            mem_mib=data.get("mem_mib", 512),
            dry_run=data.get("dry_run", False),
            files=data.get("files", {}),
        )
        return paths


# ── Guest client ───────────────────────────────────────────────────────────────

GUEST_AGENT_PORT = 8080


@dataclass
class GuestRequest:
    tool: str
    input: dict


@dataclass
class GuestResponse:
    exit_code: int
    stdout: str
    stderr: str


def _dial_vsock(cid: int, port: int) -> socket.socket:
    """Open a vsock connection. Only works on Linux with AF_VSOCK."""
    try:
        AF_VSOCK = socket.AF_VSOCK  # type: ignore[attr-defined]
    except AttributeError as exc:
        raise OSError("AF_VSOCK not available on this platform (not Linux)") from exc
    sock = socket.socket(AF_VSOCK, socket.SOCK_STREAM)
    sock.connect((cid, port))
    return sock


class GuestClient:
    def __init__(self, cid: int, tcp_addr: str = "", timeout: float = 30.0) -> None:
        self._cid = cid
        self._port = GUEST_AGENT_PORT
        self._tcp_addr = tcp_addr
        self._timeout = timeout

    def execute(self, tool: str, input_data: dict) -> GuestResponse:
        payload = json.dumps({"tool": tool, "input": input_data}).encode()
        msg = (f"POST /execute HTTP/1.0\nContent-Length: {len(payload)}\n\n").encode() + payload
        conn = self._dial()
        try:
            conn.settimeout(self._timeout)
            conn.sendall(msg)
            conn.shutdown(socket.SHUT_WR)
            raw = b""
            while chunk := conn.recv(4096):
                raw += chunk
        finally:
            conn.close()
        data = json.loads(raw.rstrip(b"\n").decode())
        return GuestResponse(
            exit_code=data.get("exit_code", 0),
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
        )

    def wait_ready(self, timeout: float = 15.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                conn = self._dial()
                conn.close()
                return
            except OSError:
                time.sleep(0.1)
        raise TimeoutError(f"guest agent not ready after {timeout}s")

    def _dial(self) -> socket.socket:
        if self._tcp_addr:
            host, port = self._tcp_addr.rsplit(":", 1)
            return socket.create_connection((host, int(port)), timeout=3.0)
        return _dial_vsock(self._cid, self._port)


# ── VM lifecycle ───────────────────────────────────────────────────────────────

class VMState(IntEnum):
    BOOTING = 0
    READY = 1
    BUSY = 2
    DESTROYED = 3


class FirecrackerVM:
    def __init__(self, vm_id: str, cid: int, api_sock: str, log_path: str,
                 snap: SnapshotPaths, process: subprocess.Popen,
                 guest: GuestClient) -> None:
        self.id = vm_id
        self.cid = cid
        self._api_sock = api_sock
        self._log_path = log_path
        self._snap = snap
        self._process = process
        self._guest = guest
        self.state = VMState.READY
        self.booted_at = time.monotonic()

    def execute(self, tool: str, input_data: dict) -> GuestResponse:
        self.state = VMState.BUSY
        try:
            return self._guest.execute(tool, input_data)
        finally:
            self.state = VMState.READY

    def destroy(self) -> None:
        self.state = VMState.DESTROYED
        try:
            self._process.kill()
            self._process.wait(timeout=5)
        except Exception:
            pass
        for path in (self._api_sock, self._log_path):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
        log.debug("vm destroyed", id=self.id)

    def _api_call(self, method: str, path: str, body: dict) -> None:
        data = json.dumps(body).encode()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(10.0)
            sock.connect(self._api_sock)
            request = (
                f"{method} {path} HTTP/1.0\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(data)}\r\n\r\n"
            ).encode() + data
            sock.sendall(request)
            response = b""
            while chunk := sock.recv(4096):
                response += chunk
        status_line = response.split(b"\r\n", 1)[0]
        parts = status_line.split(b" ", 2)
        if len(parts) >= 2:
            code = int(parts[1])
            if code >= 300:
                raise RuntimeError(f"FC API {method} {path}: HTTP {code}")

    def _api_put(self, path: str, body: dict) -> None:
        self._api_call("PUT", path, body)

    def _api_patch(self, path: str, body: dict) -> None:
        self._api_call("PATCH", path, body)

    def _wait_for_socket(self, timeout: float = 3.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if os.path.exists(self._api_sock):
                return
            time.sleep(0.05)
        raise TimeoutError(f"FC socket {self._api_sock} not ready after {timeout}s")

    def _restore(self, snap: SnapshotPaths, cid: int) -> None:
        try:
            self._api_put("/vsock", {
                "guest_cid": cid,
                "uds_path": f"/tmp/fc-vsock-{self.id}.sock",
            })
        except Exception as exc:
            log.warning("vsock setup failed (non-fatal in dev mode)", err=str(exc))
        self._api_put("/snapshot/load", {
            "snapshot_path": snap.state_file,
            "mem_file_path": snap.mem_file,
            "backend_type": "File",
            "enable_diff_snapshots": False,
        })


def new_vm(snap: SnapshotPaths, cid: int, work_dir: str,
           firecracker_bin: str, dev_mode: bool = False) -> FirecrackerVM:
    """Start a Firecracker process and restore from snapshot."""
    vm_id = uuid.uuid4().hex[:8]
    api_sock = os.path.join(work_dir, f"fc-{vm_id}.sock")
    log_path = os.path.join(work_dir, f"fc-{vm_id}.log")
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [firecracker_bin, "--api-sock", api_sock, "--log-path", log_path, "--level", "Error"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    guest_addr = f"127.0.0.1:{8080}" if dev_mode else ""
    guest = GuestClient(cid=cid, tcp_addr=guest_addr)
    vm = FirecrackerVM(
        vm_id=vm_id, cid=cid, api_sock=api_sock, log_path=log_path,
        snap=snap, process=proc, guest=guest,
    )
    vm._wait_for_socket(timeout=3.0)
    vm._restore(snap, cid)
    vm._api_patch("/vm", {"state": "Resumed"})
    guest.wait_ready(timeout=15.0)
    log.info("vm ready", id=vm_id, cid=cid, pid=proc.pid)
    return vm


# ── VM pool ────────────────────────────────────────────────────────────────────

class VMPool:
    def __init__(self, pool_size: int, snapshot_name: str, snapshot_cache_dir: str,
                 firecracker_bin: str, dev_mode: bool, store: SnapshotStore) -> None:
        self._pool_size = pool_size
        self._snapshot_name = snapshot_name
        self._snapshot_cache_dir = snapshot_cache_dir
        self._firecracker_bin = firecracker_bin
        self._dev_mode = dev_mode
        self._store = store
        self._ready: queue.Queue[FirecrackerVM] = queue.Queue(maxsize=pool_size)
        self._next_cid = 3
        self._cid_lock = threading.Lock()
        self._stopping = threading.Event()

    def warmup(self) -> None:
        snap = self._store.ensure(self._snapshot_name)
        first_ready = threading.Event()
        errors: list[Exception] = []
        err_lock = threading.Lock()

        def boot_one() -> None:
            try:
                vm = self._boot_vm(snap)
                if not self._stopping.is_set():
                    self._ready.put(vm)
                    first_ready.set()
                else:
                    vm.destroy()
            except Exception as exc:
                with err_lock:
                    errors.append(exc)
                first_ready.set()

        threads = [threading.Thread(target=boot_one, daemon=True) for _ in range(self._pool_size)]
        for t in threads:
            t.start()
        first_ready.wait(timeout=60)
        if errors and self._ready.empty():
            raise errors[0]

    def acquire(self, timeout: float = 30.0) -> FirecrackerVM:
        try:
            return self._ready.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError(f"pool acquire timeout after {timeout}s")

    def release(self, vm: FirecrackerVM) -> None:
        vm.destroy()
        if self._stopping.is_set():
            return

        def replenish() -> None:
            if self._stopping.is_set():
                return
            try:
                snap = self._store.ensure(self._snapshot_name)
                new = self._boot_vm(snap)
                if not self._stopping.is_set():
                    self._ready.put(new)
                else:
                    new.destroy()
            except Exception as exc:
                log.error("pool replenish failed", err=str(exc))

        threading.Thread(target=replenish, daemon=True).start()

    def drain(self) -> None:
        self._stopping.set()
        while not self._ready.empty():
            try:
                vm = self._ready.get_nowait()
                vm.destroy()
            except queue.Empty:
                break

    def _next_cid_value(self) -> int:
        with self._cid_lock:
            cid = self._next_cid
            self._next_cid += 1
            return cid

    def _boot_vm(self, snap: SnapshotPaths) -> FirecrackerVM:
        cid = self._next_cid_value()
        work_dir = os.path.join(self._snapshot_cache_dir, "vms", f"vm-{cid}")
        return new_vm(snap=snap, cid=cid, work_dir=work_dir,
                      firecracker_bin=self._firecracker_bin, dev_mode=self._dev_mode)


# ── Runtime ────────────────────────────────────────────────────────────────────

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
            log.info("VM pool ready", size=self._cfg.pool_size,
                     snapshot=self._cfg.snapshot_name)
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
            raise RuntimeError(f"firecracker binary not found: {self._cfg.firecracker_bin}")

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
        log.info("fc execute done", job_id=job.id, tool=job.tool,
                 exit_code=resp.exit_code, duration_ms=duration_ms, vm_id=vm.id)
        return RuntimeResult(stdout=resp.stdout, stderr=resp.stderr, exit_code=resp.exit_code)

    def _simulate_exec(self, job: Job) -> RuntimeResult:
        start = time.monotonic()
        log.info("fc execute", job_id=job.id, tool=job.tool, mode="sim")
        time.sleep(0.05)
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
        log.info("fc sim complete", job_id=job.id, tool=job.tool, duration_ms=duration_ms)
        return RuntimeResult(stdout=json.dumps(result, indent=2), exit_code=0)

    def _simulate_tool_output(self, tool: str, input_data: dict) -> object:
        if tool == "python_run":
            code = input_data.get("code", "print('hello from Python')")
            return {"stdout": f"[sim] {code}\n=> hello from Python", "exit_code": 0}
        if tool == "bash_run":
            cmd = input_data.get("command", "")
            return {"stdout": f"[sim] $ {cmd}\n=> command executed", "exit_code": 0}
        return f"[sim] {tool} executed with input: {input_data}"


__all__ = [
    "Config", "Runtime", "detect_mode", "make_mac_address", "make_tap_name",
    "FirecrackerVM", "VMPool", "VMState", "SnapshotStore", "SnapshotPaths",
    "GuestClient", "GuestResponse", "_dial_vsock",
]
