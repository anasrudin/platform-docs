"""Centralized configuration — semua env vars di satu tempat.

Semua nilai default di sini; tidak ada os.environ tersebar di codebase.
Import: `from config.settings import settings`
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key) or default


def _env_int(key: str, default: int) -> int:
    return int(os.environ.get(key) or default)


def _env_float(key: str, default: float) -> float:
    return float(os.environ.get(key) or default)


def _env_bool(key: str) -> bool:
    return os.environ.get(key, "").lower() == "true"


# ── Database ───────────────────────────────────────────────────────────────────

@dataclass
class DatabaseConfig:
    url: str = field(default_factory=lambda: _env(
        "DATABASE_URL",
        "postgres://postgres:postgres@localhost:5432/platform?sslmode=disable",
    ))


# ── Redis / Queue ──────────────────────────────────────────────────────────────

@dataclass
class RedisConfig:
    url: str = field(default_factory=lambda: _env("REDIS_URL", "redis://localhost:6379/0"))
    session_prefix: str = field(default_factory=lambda: _env("REDIS_SESSION_PREFIX", "session:"))
    session_ttl: int = field(default_factory=lambda: _env_int("REDIS_SESSION_TTL", 3600))


# ── Artifact / Blob Storage ────────────────────────────────────────────────────

@dataclass
class StorageConfig:
    driver: str = field(default_factory=lambda: _env("STORAGE_DRIVER", "minio"))  # minio | local | s3 | gcs
    endpoint: str = field(default_factory=lambda: _env("MINIO_ENDPOINT", "http://localhost:9000"))
    access_key: str = field(default_factory=lambda: _env("MINIO_ACCESS_KEY", "minioadmin"))
    secret_key: str = field(default_factory=lambda: _env("MINIO_SECRET_KEY", "minioadmin"))
    bucket: str = field(default_factory=lambda: _env("MINIO_BUCKET", "platform-artifacts"))
    local_dir: str = field(default_factory=lambda: _env("ARTIFACTS_LOCAL_DIR", ""))


# ── Consul ─────────────────────────────────────────────────────────────────────

@dataclass
class ConsulConfig:
    enabled: bool = field(default_factory=lambda: _env_bool("CONSUL_ENABLED"))
    host: str = field(default_factory=lambda: _env("CONSUL_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("CONSUL_PORT", 8500))
    token: str = field(default_factory=lambda: _env("CONSUL_TOKEN", ""))
    service_name: str = field(default_factory=lambda: _env("CONSUL_SERVICE_NAME", "platform-api"))
    service_id: str = field(default_factory=lambda: _env("CONSUL_SERVICE_ID", ""))


# ── Firecracker ────────────────────────────────────────────────────────────────

@dataclass
class FirecrackerConfig:
    mode: str = field(default_factory=lambda: _env("FC_MODE", ""))       # real | sim | ""
    dev_mode: bool = field(default_factory=lambda: _env_bool("FC_DEV_MODE"))
    pool_size: int = field(default_factory=lambda: _env_int("FC_POOL_SIZE", 2))
    kernel_path: str = field(default_factory=lambda: _env("FC_KERNEL_PATH", "/opt/platform/vmlinux"))
    rootfs_path: str = field(default_factory=lambda: _env("FC_ROOTFS_PATH", "/opt/platform/rootfs.ext4"))
    binary_path: str = field(default_factory=lambda: _env("FC_BINARY_PATH", "/usr/bin/firecracker"))
    vsock_cid_base: int = field(default_factory=lambda: _env_int("FC_VSOCK_CID_BASE", 100))
    snapshot_bucket: str = field(default_factory=lambda: _env("FC_SNAPSHOT_BUCKET", "platform-snapshots"))


# ── WASM ───────────────────────────────────────────────────────────────────────

@dataclass
class WasmConfig:
    mode: str = field(default_factory=lambda: _env("WASM_MODE", ""))     # real | sim | ""
    module_dir: str = field(default_factory=lambda: _env("WASM_MODULE_DIR", "/opt/platform/wasm"))


# ── GUI (Chromium) ─────────────────────────────────────────────────────────────

@dataclass
class GuiConfig:
    mode: str = field(default_factory=lambda: _env("GUI_MODE", ""))
    chrome_path: str = field(default_factory=lambda: _env("CHROME_PATH", "/usr/bin/chromium-browser"))
    vnc_port_base: int = field(default_factory=lambda: _env_int("VNC_PORT_BASE", 5900))


# ── Packages ───────────────────────────────────────────────────────────────────

@dataclass
class PackagesConfig:
    local_dir: str = field(default_factory=lambda: _env("PACKAGES_LOCAL_DIR", ""))
    minio_prefix: str = field(default_factory=lambda: _env("PACKAGES_MINIO_PREFIX", "packages"))


# ── Auto-scaler ────────────────────────────────────────────────────────────────

@dataclass
class ScalerConfig:
    enabled: bool = field(default_factory=lambda: _env_bool("SCALER_ENABLED"))
    min_nodes: int = field(default_factory=lambda: _env_int("SCALER_MIN_NODES", 1))
    max_nodes: int = field(default_factory=lambda: _env_int("SCALER_MAX_NODES", 10))
    up_threshold: float = field(default_factory=lambda: _env_float("SCALER_UP_THRESHOLD", 0.7))
    down_threshold: float = field(default_factory=lambda: _env_float("SCALER_DOWN_THRESHOLD", 0.3))
    up_cooldown: float = field(default_factory=lambda: _env_float("SCALER_UP_COOLDOWN", 300.0))
    down_cooldown: float = field(default_factory=lambda: _env_float("SCALER_DOWN_COOLDOWN", 600.0))
    interval: float = field(default_factory=lambda: _env_float("SCALER_INTERVAL", 60.0))
    job_id: str = field(default_factory=lambda: _env("SCALER_JOB_ID", "fc-agent"))
    group: str = field(default_factory=lambda: _env("SCALER_GROUP", "agent"))
    nomad_addr: str = field(default_factory=lambda: _env("NOMAD_ADDR", "http://127.0.0.1:4646"))
    nomad_token: str = field(default_factory=lambda: _env("NOMAD_TOKEN", ""))


# ── mTLS ───────────────────────────────────────────────────────────────────────

@dataclass
class MTLSConfig:
    enabled: bool = field(default_factory=lambda: _env_bool("MTLS_ENABLED"))
    cert_path: str = field(default_factory=lambda: _env("MTLS_CERT_PATH", _env("MTLS_CERT_FILE", "/opt/platform/certs/server.crt")))
    key_path: str = field(default_factory=lambda: _env("MTLS_KEY_PATH", _env("MTLS_KEY_FILE", "/opt/platform/certs/server.key")))
    ca_path: str = field(default_factory=lambda: _env("MTLS_CA_PATH", _env("MTLS_CA_FILE", "/opt/platform/certs/ca.crt")))


# ── OpenTelemetry ──────────────────────────────────────────────────────────────

@dataclass
class TracingConfig:
    enabled: bool = field(default_factory=lambda: _env_bool("OTEL_ENABLED"))
    otlp_endpoint: str = field(default_factory=lambda: _env("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"))
    service_name: str = field(default_factory=lambda: _env("OTEL_SERVICE_NAME", "sandbox-platform"))


# ── Hibernation ───────────────────────────────────────────────────────────────

@dataclass
class HibernationConfig:
    enabled: bool = field(default_factory=lambda: _env_bool("HIBERNATE_ENABLED"))
    idle_timeout: int = field(default_factory=lambda: _env_int("HIBERNATE_IDLE_TIMEOUT", 300))
    scan_interval: int = field(default_factory=lambda: _env_int("HIBERNATE_SCAN_INTERVAL", 60))
    ttl: int = field(default_factory=lambda: _env_int("HIBERNATE_TTL", 86400))
    bucket: str = field(default_factory=lambda: _env("HIBERNATE_BUCKET", "platform-snapshots"))


# ── Workspace ─────────────────────────────────────────────────────────────────

@dataclass
class WorkspaceConfig:
    driver: str = field(default_factory=lambda: _env("WORKSPACE_DRIVER", "sync"))
    max_size_mb: int = field(default_factory=lambda: _env_int("WORKSPACE_MAX_SIZE_MB", 1024))
    bucket: str = field(default_factory=lambda: _env("WORKSPACE_BUCKET", "platform-workspaces"))
    local_dir: str = field(default_factory=lambda: _env("WORKSPACE_LOCAL_DIR", ""))


# ── Audit ─────────────────────────────────────────────────────────────────────

@dataclass
class AuditConfig:
    backend: str = field(default_factory=lambda: _env("AUDIT_BACKEND", "stdout"))
    # postgres DSN — used when backend=postgres
    dsn: str = field(default_factory=lambda: _env("AUDIT_DSN", ""))
    # s3 bucket — used when backend=s3
    bucket: str = field(default_factory=lambda: _env("AUDIT_BUCKET", "platform-audit"))


# ── Workflow ──────────────────────────────────────────────────────────────────

@dataclass
class WorkflowConfig:
    max_steps: int = field(default_factory=lambda: _env_int("WORKFLOW_MAX_STEPS", 20))
    max_timeout: int = field(default_factory=lambda: _env_int("WORKFLOW_MAX_TIMEOUT", 600))
    max_parallel: int = field(default_factory=lambda: _env_int("WORKFLOW_MAX_PARALLEL", 5))


# ── Multi-tenancy ─────────────────────────────────────────────────────────────

@dataclass
class TenantConfig:
    isolation: bool = field(default_factory=lambda: _env_bool("TENANT_ISOLATION"))


# ── Rate Limiting ─────────────────────────────────────────────────────────────

@dataclass
class RateLimitConfig:
    enabled: bool = field(default_factory=lambda: _env_bool("RATELIMIT_ENABLED"))
    backend: str = field(default_factory=lambda: _env("RATELIMIT_BACKEND", "memory"))
    default_max_rpm: int = field(default_factory=lambda: _env_int("DEFAULT_MAX_RPM", 30))
    default_max_sessions: int = field(default_factory=lambda: _env_int("DEFAULT_MAX_SESSIONS", 2))


# ── Streaming ──────────────────────────────────────────────────────────────────

@dataclass
class StreamingConfig:
    max_timeout: int = field(default_factory=lambda: _env_int("STREAM_MAX_TIMEOUT", 300))
    buffer_size: int = field(default_factory=lambda: _env_int("STREAM_BUFFER_SIZE", 4096))


# ── API Server ─────────────────────────────────────────────────────────────────

@dataclass
class APIConfig:
    host: str = field(default_factory=lambda: _env("API_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _env_int("API_PORT", 8080))
    workers: int = field(default_factory=lambda: _env_int("API_WORKERS", 1))
    dev_mode: bool = field(default_factory=lambda: _env_bool("DEV_MODE"))
    health_port: int = field(default_factory=lambda: _env_int("API_HEALTH_PORT", 8081))


# ── Root settings object ───────────────────────────────────────────────────────

@dataclass
class Settings:
    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    consul: ConsulConfig = field(default_factory=ConsulConfig)
    firecracker: FirecrackerConfig = field(default_factory=FirecrackerConfig)
    wasm: WasmConfig = field(default_factory=WasmConfig)
    gui: GuiConfig = field(default_factory=GuiConfig)
    packages: PackagesConfig = field(default_factory=PackagesConfig)
    scaler: ScalerConfig = field(default_factory=ScalerConfig)
    mtls: MTLSConfig = field(default_factory=MTLSConfig)
    tracing: TracingConfig = field(default_factory=TracingConfig)
    hibernation: HibernationConfig = field(default_factory=HibernationConfig)
    streaming: StreamingConfig = field(default_factory=StreamingConfig)
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    audit: AuditConfig = field(default_factory=AuditConfig)
    tenant: TenantConfig = field(default_factory=TenantConfig)
    ratelimit: RateLimitConfig = field(default_factory=RateLimitConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    api: APIConfig = field(default_factory=APIConfig)


# Singleton — import this everywhere instead of calling os.environ directly
settings = Settings()
