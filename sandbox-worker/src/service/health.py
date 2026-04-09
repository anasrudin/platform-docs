"""HealthService — checks liveness of the local worker node."""
from __future__ import annotations


class HealthService:
    VERSION = "0.2.0"

    def __init__(self, lifecycle_mgr=None) -> None:
        # lifecycle_mgr: VMLifecycleManager | None
        self._mgr = lifecycle_mgr

    def check(self) -> dict:
        services: dict[str, str] = {}

        if self._mgr is not None:
            try:
                pool = self._mgr._pool
                if pool is not None:
                    services["vm_pool"] = f"healthy (pool_size={pool._pool_size})"
                else:
                    services["vm_pool"] = "not started"
            except Exception as exc:
                services["vm_pool"] = f"unhealthy: {exc}"
        else:
            services["vm_pool"] = "disabled"

        overall = "healthy" if all("unhealthy" not in v for v in services.values()) else "degraded"
        return {"status": overall, "version": self.VERSION, "services": services}
