"""ArtifactService — upload and download blobs."""
from __future__ import annotations

import io
import uuid

import structlog

from adapters.tracing import get_tracer
from adapters.storage.s3_compat import Store as ArtifactStore

log = structlog.get_logger()


class ArtifactService:
    def __init__(self, store: ArtifactStore) -> None:
        self._store = store

    def upload(self, data: bytes, filename: str, session_id: str = "") -> dict:
        tracer = get_tracer()
        artifact_id = str(uuid.uuid4())
        artifact_name = filename or "artifact"

        with tracer.start_span("storage.upload", {"bucket": "artifacts", "size_bytes": len(data)}) as span:
            key = self._store.upload(artifact_id, artifact_name, io.BytesIO(data))
            span.set_attribute("key", key)

        log.info("artifact uploaded", artifact_id=artifact_id,
                 session_id=session_id, name=artifact_name, size=len(data))

        return {
            "artifact_id": artifact_id,
            "key": key,
            "url": self._store.url(key),
            "size": len(data),
        }

    def download(self, artifact_id: str, name: str) -> bytes:
        tracer = get_tracer()
        key = f"{artifact_id}/{name}"

        with tracer.start_span("storage.download", {"bucket": "artifacts", "key": key}):
            buf = io.BytesIO()
            self._store.download(key, buf)
            buf.seek(0)
            return buf.read()
