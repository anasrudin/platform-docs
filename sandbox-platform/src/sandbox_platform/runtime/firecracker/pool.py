"""VM pool: maintains warm Firecracker VMs ready for execution.

Mirrors runtime/firecracker/pool.go.
Each VM is single-use; after use it is destroyed and a fresh one is booted.
"""
from __future__ import annotations

import queue
import threading

import structlog

from sandbox_platform.runtime.firecracker.snapshot import SnapshotPaths, SnapshotStore
from sandbox_platform.runtime.firecracker.vm import FirecrackerVM, new_vm

log = structlog.get_logger()


class VMPool:
    """Maintains a warm pool of Firecracker VMs."""

    def __init__(
        self,
        pool_size: int,
        snapshot_name: str,
        snapshot_cache_dir: str,
        firecracker_bin: str,
        dev_mode: bool,
        store: SnapshotStore,
    ) -> None:
        self._pool_size = pool_size
        self._snapshot_name = snapshot_name
        self._snapshot_cache_dir = snapshot_cache_dir
        self._firecracker_bin = firecracker_bin
        self._dev_mode = dev_mode
        self._store = store

        self._ready: queue.Queue[FirecrackerVM] = queue.Queue(maxsize=pool_size)
        self._next_cid = 3  # CIDs 0-2 are reserved by the kernel
        self._cid_lock = threading.Lock()
        self._stopping = threading.Event()
        self._wg: list[threading.Thread] = []

    def warmup(self) -> None:
        """Fill the pool up to pool_size. Blocks until at least one VM is ready."""
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

        threads = []
        for _ in range(self._pool_size):
            t = threading.Thread(target=boot_one, daemon=True)
            t.start()
            threads.append(t)

        first_ready.wait(timeout=60)
        if errors and self._ready.empty():
            raise errors[0]

    def acquire(self, timeout: float = 30.0) -> FirecrackerVM:
        """Pop a ready VM from the pool. Raises TimeoutError if none available."""
        try:
            return self._ready.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError(f"pool acquire timeout after {timeout}s")

    def release(self, vm: FirecrackerVM) -> None:
        """Destroy the VM and replenish the pool with a fresh one."""
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
                    log.debug("pool replenished", pool_size=self._ready.qsize())
                else:
                    new.destroy()
            except Exception as exc:
                log.error("pool replenish failed", err=str(exc))

        t = threading.Thread(target=replenish, daemon=True)
        t.start()

    def drain(self) -> None:
        """Stop background goroutines and destroy all pooled VMs."""
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
        import os
        cid = self._next_cid_value()
        work_dir = os.path.join(self._snapshot_cache_dir, "vms", f"vm-{cid}")
        return new_vm(
            snap=snap,
            cid=cid,
            work_dir=work_dir,
            firecracker_bin=self._firecracker_bin,
            dev_mode=self._dev_mode,
        )
