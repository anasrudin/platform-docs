"""WASM runtime using wasmtime CLI."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

import structlog

from models.job import Job, RuntimeResult
from models.session import Tier

log = structlog.get_logger()

HandlerFunc = Callable[[dict], tuple[str, Exception | None]]


def _env_or(key: str, default: str) -> str:
    return os.environ.get(key) or default


def detect_mode(wasmtime_bin: str) -> str:
    """Return 'real' if WASM_MODE=real or wasmtime is in PATH."""
    wasm_mode = os.environ.get("WASM_MODE", "")
    if wasm_mode in ("real", "sim"):
        log.info("WASM mode from WASM_MODE env", mode=wasm_mode)
        return wasm_mode
    if shutil.which(wasmtime_bin):
        log.info("WASM mode auto-detected: wasmtime found", mode="real")
        return "real"
    log.info("WASM mode auto-detected: wasmtime not in PATH", mode="sim")
    return "sim"


class _ModuleStore:
    """Downloads and caches .wasm modules from MinIO."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        cache_dir: str,
    ) -> None:
        self._endpoint = endpoint
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._cache_dir = cache_dir

    def ensure(self, tool: str) -> str:
        """Return the local path to <tool>.wasm, downloading if needed."""
        filename = f"{tool}.wasm"
        local_path = os.path.join(self._cache_dir, filename)

        if os.path.exists(local_path):
            log.debug("module cache hit", tool=tool)
            return local_path

        log.info("module not cached, downloading from MinIO", tool=tool)
        Path(self._cache_dir).mkdir(parents=True, exist_ok=True)

        key = f"{self._bucket}/{filename}"
        try:
            self._pull_from_minio(key, local_path)
        except Exception as mc_err:
            log.warning("mc pull failed, trying HTTP download", err=str(mc_err))
            url = f"{self._endpoint}/{self._bucket}/{filename}"
            _download_file(url, local_path)

        return local_path

    def _pull_from_minio(self, key: str, dest: str) -> None:
        mc = shutil.which("mc")
        if not mc:
            raise FileNotFoundError("mc not found in PATH")
        alias = f"wasm-dl-{int(time.time() * 1e9)}"
        subprocess.run(
            [mc, "alias", "set", alias, self._endpoint,
             self._access_key, self._secret_key, "--quiet"],
            check=True, capture_output=True,
        )
        try:
            subprocess.run(
                [mc, "cp", "--quiet", f"{alias}/{key}", dest],
                check=True, capture_output=True,
            )
        finally:
            subprocess.run([mc, "alias", "remove", alias], capture_output=True)


def _download_file(url: str, dest: str) -> None:
    with urllib.request.urlopen(url) as resp:  # noqa: S310
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        with open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)


class Runtime:
    """WASM-tier runtime engine."""

    def __init__(self) -> None:
        wasmtime_bin = _env_or("WASMTIME_BIN", "wasmtime")
        self._cfg = {
            "wasmtime_bin": wasmtime_bin,
            "minio_endpoint": _env_or("MINIO_ENDPOINT", "http://localhost:9000"),
            "minio_access_key": _env_or("MINIO_ACCESS_KEY", "minioadmin"),
            "minio_secret_key": _env_or("MINIO_SECRET_KEY", "minioadmin"),
            "minio_bucket": _env_or("MINIO_WASM_BUCKET", "platform-modules"),
            "cache_dir": _env_or("WASM_CACHE_DIR", "/var/sandbox/wasm-cache"),
            "exec_timeout": 30.0,
        }
        self._mode = detect_mode(wasmtime_bin)
        self._store = _ModuleStore(
            endpoint=self._cfg["minio_endpoint"],
            access_key=self._cfg["minio_access_key"],
            secret_key=self._cfg["minio_secret_key"],
            bucket=self._cfg["minio_bucket"],
            cache_dir=self._cfg["cache_dir"],
        )
        self._handlers: dict[str, HandlerFunc] = {}
        self._register_builtins()
        log.info("wasm runtime initialised", mode=self._mode)

    def name(self) -> str:
        return f"wasm-{self._mode}"

    def tier(self) -> Tier:
        return Tier.WASM

    def health(self) -> None:
        if self._mode == "sim":
            return
        if not shutil.which(self._cfg["wasmtime_bin"]):
            raise RuntimeError(f"wasmtime not found: {self._cfg['wasmtime_bin']}")

    def execute(self, job: Job) -> RuntimeResult:
        if self._mode == "real":
            return self._real_exec(job)
        return self._sim_exec(job)

    def register_handler(self, tool: str, handler: HandlerFunc) -> None:
        """Add a custom sim-mode tool handler."""
        self._handlers[tool] = handler

    def _real_exec(self, job: Job) -> RuntimeResult:
        start = time.monotonic()
        log.info("wasm execute", job_id=job.id, tool=job.tool, mode="real")

        try:
            module_path = self._store.ensure(job.tool)
        except Exception as exc:
            log.error("module download failed, falling back to sim",
                      tool=job.tool, err=str(exc))
            return self._sim_exec(job)

        input_json = json.dumps(job.input).encode()

        try:
            result = subprocess.run(
                [self._cfg["wasmtime_bin"], "run", module_path],
                input=input_json,
                capture_output=True,
                timeout=self._cfg["exec_timeout"],
            )
        except subprocess.TimeoutExpired:
            return RuntimeResult(stderr="wasmtime timeout", exit_code=1)
        except Exception as exc:
            return RuntimeResult(stderr=f"wasmtime error: {exc}", exit_code=1)

        duration_ms = int((time.monotonic() - start) * 1000)
        log.info("wasm execute done", job_id=job.id, tool=job.tool,
                 exit_code=result.returncode, duration_ms=duration_ms)

        return RuntimeResult(
            stdout=result.stdout.decode(errors="replace"),
            stderr=result.stderr.decode(errors="replace"),
            exit_code=result.returncode,
        )

    def _sim_exec(self, job: Job) -> RuntimeResult:
        start = time.monotonic()
        log.info("wasm execute", job_id=job.id, tool=job.tool, mode="sim")

        handler = self._handlers.get(job.tool) or self._handlers["echo"]
        output, err = handler(job.input)

        duration_ms = int((time.monotonic() - start) * 1000)

        if err:
            log.error("wasm sim execution failed", tool=job.tool,
                      err=str(err), duration_ms=duration_ms)
            return RuntimeResult(stderr=str(err), exit_code=1)

        log.info("wasm sim complete", tool=job.tool, duration_ms=duration_ms)
        return RuntimeResult(stdout=output, exit_code=0)

    def _register_builtins(self) -> None:
        def echo(inp: dict) -> tuple[str, Exception | None]:
            return json.dumps(inp, indent=2), None

        def hello(inp: dict) -> tuple[str, Exception | None]:
            name = inp.get("name") or "World"
            return f"Hello, {name}! (from WASM runtime)", None

        def json_parse(inp: dict) -> tuple[str, Exception | None]:
            data = inp.get("data")
            if not isinstance(data, str):
                return "", ValueError("missing 'data' field")
            try:
                parsed = json.loads(data)
                return json.dumps(parsed, indent=2), None
            except json.JSONDecodeError as exc:
                return "", ValueError(f"invalid JSON: {exc}")

        def html_parse(inp: dict) -> tuple[str, Exception | None]:
            html = inp.get("html")
            if not isinstance(html, str):
                return "", ValueError("missing 'html' field")
            return f"Parsed HTML document ({len(html)} bytes)", None

        def markdown_convert(inp: dict) -> tuple[str, Exception | None]:
            md = inp.get("markdown")
            if not isinstance(md, str):
                return "", ValueError("missing 'markdown' field")
            return f"<html><body>{md}</body></html>", None

        self._handlers["echo"] = echo
        self._handlers["hello"] = hello
        self._handlers["json_parse"] = json_parse
        self._handlers["html_parse"] = html_parse
        self._handlers["markdown_convert"] = markdown_convert


__all__ = ["Runtime", "detect_mode"]
