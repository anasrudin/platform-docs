"""Package routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from api.schemas.requests import PackageInstallRequest




def register(app_state: dict) -> APIRouter:
    router = APIRouter()  # new instance per call — safe for tests
    @router.post("/packages/install")
    def install_package(body: PackageInstallRequest) -> JSONResponse:
        try:
            result = app_state["package_svc"].install(
                name=body.package_name,
                version=body.version,
                proxy_url=body.proxy_url,
                timeout_seconds=body.timeout_seconds,
                extra_dependencies=body.extra_dependencies,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        return JSONResponse(content=result)

    @router.get("/packages")
    def list_packages() -> JSONResponse:
        pkgs = app_state["package_svc"].list_packages()
        return JSONResponse(content={"packages": pkgs, "count": len(pkgs)})

    @router.delete("/packages/{name}")
    def delete_package(name: str, version: str = "") -> JSONResponse:
        try:
            app_state["package_svc"].delete(name, version=version)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        return JSONResponse(content={"deleted": name, "version": version or "latest"})

    return router
