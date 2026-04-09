"""Mutual TLS (mTLS) support for the sandbox platform.

Components
----------
create_mtls_context(cert, key, ca)
    Build a server-side ``ssl.SSLContext`` requiring client certificates,
    TLS 1.3 minimum, loaded with ECDSA P-256 cert/key.

CertManager
    Wraps the SSLContext and exposes ``reload()`` to hot-swap the certificate
    chain without replacing the context object — existing connections survive.

MTLSMiddleware
    ASGI middleware that returns HTTP 403 when mTLS is enabled and the
    incoming request carries no client certificate.  Uses an injectable
    ``cert_checker`` callable so it can be unit-tested without real TLS.

mtls_config_from_env()
    Read all mTLS settings from environment variables.

Environment variables
---------------------
MTLS_ENABLED    — "true" to enable (default: false)
MTLS_CERT_FILE  — server certificate  (default: /etc/sandbox/certs/server.crt)
MTLS_KEY_FILE   — server private key  (default: /etc/sandbox/certs/server.key)
MTLS_CA_FILE    — CA certificate for verifying clients
                  (default: /etc/sandbox/certs/ca.crt)
"""

from __future__ import annotations

import os
import ssl
from collections.abc import Callable

import structlog
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

log = structlog.get_logger()

_DEFAULT_CERT = "/etc/sandbox/certs/server.crt"
_DEFAULT_KEY = "/etc/sandbox/certs/server.key"
_DEFAULT_CA = "/etc/sandbox/certs/ca.crt"


# ── SSLContext factory ─────────────────────────────────────────────────────────


def create_mtls_context(
    cert_file: str,
    key_file: str,
    ca_file: str,
) -> ssl.SSLContext:
    """Return a server SSLContext configured for mutual TLS.

    - Protocol: TLS server
    - Minimum version: TLS 1.3
    - Client certificate: required (``ssl.CERT_REQUIRED``)
    - CA bundle: loaded from *ca_file* (used to verify client certs)
    - Server identity: loaded from *cert_file* / *key_file* (ECDSA P-256)
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(ca_file)
    ctx.load_cert_chain(cert_file, key_file)
    return ctx


# ── Certificate hot-reload ─────────────────────────────────────────────────────


class CertManager:
    """Holds an SSLContext and allows zero-downtime certificate rotation.

    Calling ``reload()`` calls ``load_cert_chain`` on the *same* context
    object, so the OS-level socket stays bound and in-flight TLS sessions
    are not interrupted.
    """

    def __init__(self, cert_file: str, key_file: str, ca_file: str) -> None:
        self._cert_file = cert_file
        self._key_file = key_file
        self._ca_file = ca_file
        self._ctx = create_mtls_context(cert_file, key_file, ca_file)

    @property
    def context(self) -> ssl.SSLContext:
        return self._ctx

    def reload(self) -> None:
        """Hot-reload the server cert/key onto the existing SSLContext.

        The CA is also re-loaded so trust anchors can be rotated without
        restarting the process.
        """
        self._ctx.load_verify_locations(self._ca_file)
        self._ctx.load_cert_chain(self._cert_file, self._key_file)
        log.info("mtls: certificates reloaded", cert=self._cert_file)


# ── ASGI middleware ────────────────────────────────────────────────────────────

CertChecker = Callable[[Scope], bool]


def _transport_cert_checker(scope: Scope) -> bool:
    """Default checker: inspect the ASGI transport for a peer certificate.

    Returns True if a client cert is present, False otherwise.
    In non-TLS environments this always returns True (pass-through), because
    actual enforcement is done by ``ssl.CERT_REQUIRED`` on the SSLContext.
    """
    transport = scope.get("transport")
    if transport is not None and hasattr(transport, "get_extra_info"):
        cert = transport.get_extra_info("peercert")
        return cert is not None
    # No SSL transport — not a TLS connection; defer to SSLContext enforcement.
    return True


class MTLSMiddleware:
    """Return HTTP 403 when mTLS is enabled and the client cert is absent.

    The ``cert_checker`` callable receives the ASGI ``scope`` dict and must
    return True (cert present / allow) or False (no cert / deny).  Swap it
    in tests to avoid needing a real TLS connection::

        app.add_middleware(
            MTLSMiddleware,
            enabled=True,
            cert_checker=lambda scope: False,  # always reject — test 403 path
        )
    """

    def __init__(
        self,
        app: ASGIApp,
        enabled: bool = False,
        cert_checker: CertChecker | None = None,
    ) -> None:
        self._app = app
        self._enabled = enabled
        self._checker = cert_checker or _transport_cert_checker

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self._enabled and scope["type"] == "http":
            if not self._checker(scope):
                response = JSONResponse(
                    {"detail": "client certificate required"},
                    status_code=403,
                )
                await response(scope, receive, send)
                return
        await self._app(scope, receive, send)


# ── Environment config ─────────────────────────────────────────────────────────


def mtls_config_from_env() -> dict:
    """Return mTLS settings read from environment variables."""
    return {
        "enabled": os.environ.get("MTLS_ENABLED") == "true",
        "cert_file": os.environ.get("MTLS_CERT_FILE") or _DEFAULT_CERT,
        "key_file": os.environ.get("MTLS_KEY_FILE") or _DEFAULT_KEY,
        "ca_file": os.environ.get("MTLS_CA_FILE") or _DEFAULT_CA,
    }
