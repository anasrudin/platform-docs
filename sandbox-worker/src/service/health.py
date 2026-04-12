"""HealthService — checks liveness of the local worker node."""
from __future__ import annotations


class HealthService:
    VERSION = "0.2.0"

    def __init__(self, lifecycle_mgr=None) -> None:
        # lifecycle_mgr: VMLifecycleManager | None
        self._mgr = lifecycle_mgr

    def check(self) -> dict:
        services: dict[str, str] = {}
        pool_available = 0
        mode = "unknown"

        if self._mgr is not None:
            try:
                sim_mode = getattr(self._mgr, "_sim_mode", False)
                if sim_mode:
                    mode = "sim"
                    pool_size = getattr(self._mgr, "_pool_size", 0)
                    pool_available = pool_size
                    services["vm_pool"] = f"healthy (sim, pool_size={pool_size})"
                else:
                    mode = "real"
                    pool = getattr(self._mgr, "_pool", None)
                    warmup_thread = getattr(self._mgr, "_warmup_thread", None)
                    if pool is None:
                        services["vm_pool"] = "not started"
                    elif warmup_thread is not None and warmup_thread.is_alive():
                        pool_available = pool._ready.qsize()
                        services["vm_pool"] = f"warming_up (ready={pool_available}/{pool._pool_size})"
                    else:
                        pool_available = pool._ready.qsize()
                        if pool_available > 0:
                            services["vm_pool"] = f"healthy (ready={pool_available}/{pool._pool_size})"
                        else:
                            services["vm_pool"] = f"degraded (ready=0/{pool._pool_size} — upload snapshot to MinIO)"
            except Exception as exc:
                services["vm_pool"] = f"unhealthy: {exc}"
        else:
            services["vm_pool"] = "disabled"

        overall = "healthy" if all(
            s not in v for s in ("unhealthy", "degraded") for v in services.values()
        ) else "degraded"

        return {
            "status": overall,
            "version": self.VERSION,
            "mode": mode,
            "pool_available": pool_available,
            "services": services,
        }
