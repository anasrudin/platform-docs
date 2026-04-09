"""WorkspaceMounter — sync workspace files to/from VM before/after boot.

Two strategies:
  sync      — download storage → /tmp/workspace before VM start,
               upload /tmp/workspace → storage after VM destroy
  virtiofs  — mount via virtiofsd (Linux+KVM only, not implemented yet)

In sim mode both operations are no-ops (safe for dev/tests).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import structlog

from adapters.storage.base import BlobStore
from adapters.tracing import get_tracer
from models.workspace import MountConfig, MountDriver

log = structlog.get_logger()


class WorkspaceMounter:
    def __init__(self, storage: BlobStore, bucket_prefix: str = "workspaces") -> None:
        self._storage = storage
        self._prefix = bucket_prefix

    def mount(self, config: MountConfig, local_dir: str) -> str:
        """Download workspace files into local_dir. Returns local_dir path."""
        tracer = get_tracer()
        if config.driver == MountDriver.VIRTIOFS:
            log.warning("virtiofs not yet implemented, falling back to sync")

        with tracer.start_span("orchestrator.workspace.mount", {
            "workspace_id": config.workspace_id,
            "driver": config.driver.value,
        }):
            Path(local_dir).mkdir(parents=True, exist_ok=True)
            downloaded = self._download_all(config.workspace_id, local_dir)
            log.info("workspace mounted", workspace_id=config.workspace_id,
                     files=downloaded, local_dir=local_dir)
            return local_dir

    def unmount(self, config: MountConfig, local_dir: str) -> int:
        """Upload workspace files from local_dir back to storage. Returns bytes uploaded."""
        tracer = get_tracer()
        with tracer.start_span("orchestrator.workspace.unmount", {
            "workspace_id": config.workspace_id,
        }):
            total = self._upload_all(config.workspace_id, local_dir)
            log.info("workspace unmounted", workspace_id=config.workspace_id,
                     bytes_uploaded=total, local_dir=local_dir)
            return total

    def delete(self, workspace_id: str, known_files: list[str]) -> None:
        """Delete all blobs for a workspace from storage."""
        tracer = get_tracer()
        with tracer.start_span("orchestrator.workspace.delete", {"workspace_id": workspace_id}):
            for fname in known_files:
                key = f"{self._prefix}/{workspace_id}/{fname}"
                try:
                    self._storage.delete(key)
                except Exception as exc:
                    log.warning("workspace blob delete failed", key=key, err=str(exc))

    # ── internal ───────────────────────────────────────────────────────────────

    def _download_all(self, workspace_id: str, dest_dir: str) -> int:
        """Download all blobs under workspaces/{workspace_id}/ to dest_dir."""
        prefix = f"{self._prefix}/{workspace_id}/"
        count = 0
        # List files by iterating known keys stored in a manifest
        manifest_key = f"{prefix}_manifest.json"
        try:
            import json
            manifest_data = self._storage.download(manifest_key)
            files = json.loads(manifest_data.decode())
        except Exception:
            files = []  # no manifest → empty workspace

        for fname in files:
            key = f"{prefix}{fname}"
            try:
                data = self._storage.download(key)
                dest = Path(dest_dir) / fname
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                count += 1
            except Exception as exc:
                log.warning("workspace file download failed", key=key, err=str(exc))

        return count

    def _upload_all(self, workspace_id: str, src_dir: str) -> int:
        """Upload all files in src_dir to workspaces/{workspace_id}/ and update manifest."""
        import json
        prefix = f"{self._prefix}/{workspace_id}/"
        total_bytes = 0
        file_names = []

        for path in Path(src_dir).rglob("*"):
            if path.is_file():
                rel = str(path.relative_to(src_dir))
                key = f"{prefix}{rel}"
                data = path.read_bytes()
                self._storage.upload(key, data)
                total_bytes += len(data)
                file_names.append(rel)

        # Update manifest
        manifest_key = f"{prefix}_manifest.json"
        self._storage.upload(manifest_key, json.dumps(file_names).encode())
        return total_bytes
