# Sandbox Platform — Spec-Driven Development

**Platform:** `sandbox-platform` (Python 3.12+)
**Architecture:** Nomad cluster · Firecracker microVMs · WASM · GUI (Chromium)
**Status:** Week 1 complete (Days 1–7). This spec covers the next phase.

---

## Overview

This document defines the features to implement next, following a spec-first approach: each feature has a clear current state, target behavior, and acceptance criteria before any code is written.

### Features in Scope

| # | Feature | Priority |
|---|---------|----------|
| 1 | Consul service discovery & health checks | High |
| 2 | HAProxy load balancing | High |
| 3 | Auto-scaling based on pool metrics | High |
| 4 | Package management API with proxy support | Medium |
| 5 | Node-aware TAP device naming | Medium |
| 6 | Unique MAC address generation | Medium |
| 7 | mTLS for service-to-service communication | High |
| 8 | Session mapping in Consul KV | High |

---

## Feature Specifications

### 1. Consul Service Discovery & Health Checks

#### Current State
- Service discovery via Nomad only (no Consul agent integration)
- Health checks are manual and coarse-grained
- Services (WASM, Firecracker, GUI agents) register nowhere on startup

#### Target Behavior
Each runtime agent registers itself with Consul on startup and deregisters on shutdown. The load balancer discovers backends dynamically via Consul instead of static config.

#### Integration Points
- `sandbox_platform/runtime/firecracker/runtime.py` — register on pool warmup
- `sandbox_platform/runtime/wasm/runtime.py` — register on agent start
- `sandbox_platform/runtime/gui/runtime.py` — register on agent start
- `sandbox_platform/cmd/consul_client.py` — new shared Consul client module

#### Key Behaviors

| Behavior | Detail |
|----------|--------|
| Auto-registration | On agent startup, POST service definition to Consul |
| Health check endpoint | `GET /health` on each agent, returns `200 OK` with JSON status |
| Rich metadata | Tags: node ID, runtime type, version, supported languages |
| Session mapping | Store `session_id → vm_id` in Consul KV |
| Graceful deregistration | On SIGTERM, DELETE service before process exit |

#### Consul API Calls (Python)

```python
# Register service
PUT /v1/agent/service/register
{
  "Name": "firecracker-agent",
  "ID": "firecracker-{node_id}-{pid}",
  "Tags": ["sandbox", "firecracker", "python"],
  "Address": "{node_ip}",
  "Port": 8080,
  "Check": {
    "HTTP": "http://{node_ip}:8080/health",
    "Interval": "10s",
    "Timeout": "5s",
    "DeregisterCriticalServiceAfter": "1m"
  }
}

# Session KV
PUT  /v1/kv/sandbox/sessions/{session_id}   → {"vm_id": "...", "node_id": "..."}
GET  /v1/kv/sandbox/sessions/{session_id}
DEL  /v1/kv/sandbox/sessions/{session_id}
```

#### Acceptance Criteria
- [ ] All three runtime agents register with Consul on startup
- [ ] `/health` endpoint returns `{"status": "ok", "runtime": "firecracker", "pool_size": N}`
- [ ] Agent correctly deregisters on graceful shutdown
- [ ] Session KV round-trip works (write → read → delete)

---

### 2. HAProxy Load Balancing

#### Current State
- Nomad handles routing with static allocation
- No advanced routing rules or traffic management
- Backend failures are not handled gracefully

#### Target Behavior
HAProxy sits in front of runtime agents. Backends are populated dynamically from Consul service discovery. Health check failures automatically remove backends from rotation.

#### Integration Points
- `infra/haproxy/haproxy.cfg.j2` — Jinja2 template, rendered by Consul-template
- `infra/haproxy/consul-template.hcl` — watch Consul, re-render and reload HAProxy

#### Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| Algorithm | `roundrobin` | Options: `roundrobin`, `leastconn`, `source` |
| Max connections | `1000` | Per backend server |
| Connect timeout | `5s` | TCP connect timeout |
| Client timeout | `30s` | Idle client timeout |
| Server timeout | `30s` | Backend response timeout |
| Health check | `GET /health` | HTTP health check path |
| Health interval | `10s` | Check frequency |

#### HAProxy Backend Template

```
backend firecracker_agents
    balance roundrobin
    option httpchk GET /health
    timeout connect 5s
    timeout server  30s
    {{range service "firecracker-agent"}}
    server {{.ID}} {{.Address}}:{{.Port}} check inter 10s fall 2 rise 3
    {{end}}
```

#### Acceptance Criteria
- [ ] HAProxy config reloads automatically when Consul service list changes
- [ ] Removing an agent from Consul removes it from rotation within 30s
- [ ] Load is distributed across all healthy backends
- [ ] No connection drops during config reload (HAProxy graceful reload)

---

### 3. Auto-scaling Based on Pool Metrics

#### Current State
- `FC_POOL_SIZE` is a fixed env var (default: 2)
- No metrics collection from pool
- Scaling requires manual config change + restart

#### Target Behavior
A background scaler process watches pool utilization metrics and adjusts Nomad job counts (and local pool sizes) automatically.

#### Integration Points
- `sandbox_platform/scaler/metrics.py` — collect from all runtime nodes
- `sandbox_platform/scaler/policy.py` — evaluate thresholds, decide scale action
- `sandbox_platform/scaler/nomad.py` — call Nomad API to scale job counts

#### Scaling Policy

```python
@dataclass
class ScalingPolicy:
    min_nodes: int = 1
    max_nodes: int = 10
    target_utilization: float = 0.70   # 70% — steady state target
    scale_up_threshold: float = 0.80   # above this → add nodes
    scale_down_threshold: float = 0.50 # below this → remove nodes
    cooldown_up_seconds: int = 300     # 5 min between scale-ups
    cooldown_down_seconds: int = 600   # 10 min between scale-downs
    evaluation_period_seconds: int = 60
    metrics_window_seconds: int = 300
```

#### Metrics Collected Per Node

| Metric | Source | Scale Up If |
|--------|--------|------------|
| Pool utilization | `pool.active / pool.total` | > 80% |
| CPU usage | `/proc/stat` or cAdvisor | > 80% |
| Memory usage | `/proc/meminfo` | > 85% |
| Active sessions | Consul KV count | Sustained high |

#### Scale Decision Logic

```python
def evaluate(metrics: list[NodeMetrics]) -> ScaleAction:
    utilization = mean([m.pool_utilization for m in metrics])
    if utilization > policy.scale_up_threshold:
        return ScaleAction.UP
    if utilization < policy.scale_down_threshold:
        return ScaleAction.DOWN
    return ScaleAction.NONE
```

#### Acceptance Criteria
- [ ] Scaler runs as a standalone process, not blocking the request path
- [ ] Cooldown periods prevent thrashing (no two scale-ups within 5 min)
- [ ] Scale-down drains nodes gracefully (no in-flight requests dropped)
- [ ] Scaler respects `min_nodes` and `max_nodes` hard limits

---

### 4. Package Management API

#### Current State
- Sandbox VMs have a fixed rootfs (baked at snapshot build time)
- No way to install packages into a running session
- No proxy support for corporate/restricted networks

#### Target Behavior
A REST API endpoint allows callers to install pip packages into a specific VM session. Supports HTTP proxy for environments that block direct PyPI access.

#### API Endpoints

```
POST   /packages/install          Install one or more packages
GET    /packages                  List installed packages (in session)
GET    /packages/{name}           Get info for a specific package
DELETE /packages/{name}           Uninstall a package
PUT    /packages/{name}           Update a package to latest/specific version
```

#### Request / Response Models

```python
# POST /packages/install
class PackageInstallRequest(BaseModel):
    session_id: str
    package_name: str
    version: str | None = None          # e.g. "numpy==1.26.0"
    proxy_url: str | None = None        # e.g. "http://proxy:3128"
    timeout_seconds: int = 300
    extra_dependencies: list[str] = []

class PackageInstallResponse(BaseModel):
    status: Literal["success", "error"]
    output: str                          # pip stdout
    error: str | None
    execution_time_ms: int
```

#### Implementation Notes
- Execute `pip install` inside the VM via the guest agent (`POST /execute`)
- Pass `--proxy` flag when `proxy_url` is set
- Cache downloaded wheels in MinIO (`platform-packages/` bucket) to avoid re-downloading
- Respond with streaming output for long-running installs if possible

#### Acceptance Criteria
- [ ] Can install `numpy` into a running Firecracker session via API
- [ ] Proxy URL is forwarded to pip correctly
- [ ] Cached packages are reused across sessions (same version, same package)
- [ ] Errors from pip are surfaced in the response, not swallowed

---

### 5. Node-aware TAP Device Naming

#### Current State
- TAP devices use a simple sequential counter (`tap0`, `tap1`, ...)
- Names can collide across nodes in a multi-node Nomad cluster
- No cleanup on abnormal VM termination

#### Target Behavior
TAP device names encode node identity and VM identity, making them globally unique and traceable.

#### Naming Convention

```
Format:  tap-{node_id_short}-{vm_id_short}
Example: tap-n1a2-v8f3

node_id_short: first 4 chars of Nomad node ID (hex)
vm_id_short:   first 4 chars of VM UUID (hex)
Max length:    15 chars (Linux IFNAMSIZ limit)
```

#### Python Implementation

```python
def tap_device_name(node_id: str, vm_id: str) -> str:
    """Generate a unique TAP device name within Linux 15-char IFNAMSIZ limit."""
    node_short = node_id.replace("-", "")[:4]
    vm_short = vm_id.replace("-", "")[:4]
    name = f"tap-{node_short}-{vm_short}"
    assert len(name) <= 15, f"TAP name too long: {name}"
    return name
```

#### Acceptance Criteria
- [ ] No two VMs on the same node ever get the same TAP name
- [ ] TAP devices are always deleted when the VM terminates (normal or crash)
- [ ] Name format matches regex `^tap-[0-9a-f]{4}-[0-9a-f]{4}$`

---

### 6. Unique MAC Address Generation

#### Current State
- MAC addresses are hardcoded or randomly generated at runtime
- No collision detection
- Possible conflicts in large pools

#### Target Behavior
MAC addresses are deterministically generated from node ID and VM ID, guaranteeing uniqueness without a central registry.

#### Address Format

```
Byte layout:  06:00:{node[0]}:{node[1]}:{vm[0]}:{vm[1]}

06    — locally administered, unicast (IEEE standard for non-vendor MACs)
00    — reserved / padding
node  — 2 bytes derived from node_id hash
vm    — 2 bytes derived from vm_id hash

Example: 06:00:AC:10:00:01
```

#### Python Implementation

```python
import hashlib

def generate_mac(node_id: str, vm_id: str) -> str:
    """Deterministic, collision-resistant MAC address."""
    node_hash = hashlib.sha256(node_id.encode()).digest()
    vm_hash = hashlib.sha256(vm_id.encode()).digest()
    return f"06:00:{node_hash[0]:02X}:{node_hash[1]:02X}:{vm_hash[0]:02X}:{vm_hash[1]:02X}"
```

#### Acceptance Criteria
- [ ] Same inputs always produce the same MAC (deterministic)
- [ ] Different node+vm combinations produce different MACs (collision-free in practice)
- [ ] Generated MACs pass IEEE 802 format validation
- [ ] Used in Firecracker network interface config

---

### 7. Mutual TLS (mTLS)

#### Current State
- No TLS between internal services (plain HTTP)
- API endpoint has no client authentication
- Guest agent protocol is unencrypted

#### Target Behavior
All service-to-service communication uses mTLS. Each component has a certificate signed by an internal CA. Connections without a valid client cert are rejected.

#### Certificate Specifications

| Property | Value |
|----------|-------|
| TLS version | 1.3 (1.2 as fallback) |
| Key type | ECDSA P-256 (preferred) or RSA 2048 |
| Cert validity | 1 year, rotated every 30 days |
| CA | Internal root CA, self-managed |
| Revocation | Short-lived certs (no CRL needed) |

#### Python Implementation (FastAPI example)

```python
import ssl
from fastapi import FastAPI

def create_mtls_context(cert: str, key: str, ca: str) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.load_cert_chain(certfile=cert, keyfile=key)
    ctx.load_verify_locations(cafile=ca)
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx
```

#### Acceptance Criteria
- [ ] Requests without a client cert are rejected with `403`
- [ ] Certificate rotation does not drop in-flight connections
- [ ] All inter-service calls (agent → Consul, scaler → Nomad, agent → agent) use mTLS
- [ ] Certs are stored in `/etc/sandbox/certs/`, not in env vars

---

### 8. Session Mapping in Consul KV

#### Current State
- Session-to-VM mappings are stored in-memory per agent process
- No distributed session state — routing must always hit the same node
- Sessions are lost if the agent restarts

#### Target Behavior
Session mappings are stored in Consul KV. Any node can look up which VM owns a session, enabling stateless routing.

#### Key Schema

```
Base path:  sandbox/sessions/
Session key: sandbox/sessions/{session_id}

Value (JSON):
{
  "vm_id": "abc123",
  "node_id": "node-xyz",
  "agent_address": "10.0.1.5:8080",
  "created_at": "2026-04-07T10:00:00Z",
  "expires_at": "2026-04-07T10:30:00Z"
}

TTL: Set via Consul session lock, auto-expires on agent failure
```

#### Python Implementation

```python
class SessionStore:
    def __init__(self, consul_url: str):
        self.base = f"{consul_url}/v1/kv/sandbox/sessions"

    async def put(self, session_id: str, mapping: SessionMapping) -> None:
        async with httpx.AsyncClient() as client:
            await client.put(f"{self.base}/{session_id}", content=mapping.model_dump_json())

    async def get(self, session_id: str) -> SessionMapping | None:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{self.base}/{session_id}")
            if r.status_code == 404:
                return None
            data = base64.b64decode(r.json()["Value"])
            return SessionMapping.model_validate_json(data)

    async def delete(self, session_id: str) -> None:
        async with httpx.AsyncClient() as client:
            await client.delete(f"{self.base}/{session_id}")
```

#### Acceptance Criteria
- [ ] Session lookup latency < 5ms (p99) under normal load
- [ ] Sessions expire automatically via TTL (no manual cleanup needed)
- [ ] Restarting an agent does not lose active session mappings
- [ ] Sessions for terminated VMs are cleaned up within TTL window

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  sandbox-platform                 │
│                                                   │
│  ┌──────────┐    ┌──────────┐    ┌─────────────┐ │
│  │  HAProxy │───▶│ Runtime  │───▶│ Firecracker │ │
│  │ (LB)     │    │ Agents   │    │ VM Pool     │ │
│  └──────────┘    │ (Python) │    └─────────────┘ │
│       ▲          └────┬─────┘                     │
│       │               │ register / session KV     │
│  ┌────┴──────────────▼──────────────────────┐    │
│  │              Consul                        │    │
│  │  · Service registry    · Health checks     │    │
│  │  · Session KV store    · Node metadata     │    │
│  └────────────────────────────────────────────┘    │
│                                                   │
│  ┌─────────┐    ┌─────────┐    ┌─────────────┐  │
│  │ Auto-   │───▶│  Nomad  │    │   Package   │  │
│  │ Scaler  │    │  (jobs) │    │   Manager   │  │
│  └─────────┘    └─────────┘    └─────────────┘  │
└─────────────────────────────────────────────────┘
```

### Data Flow

1. **Startup** — Runtime agents register with Consul; HAProxy backends update automatically
2. **Request arrives** — HAProxy routes to a healthy agent using least-connections
3. **Session created** — Agent stores `session_id → vm_id` in Consul KV
4. **Subsequent requests** — Any agent can look up the session and proxy to the right VM
5. **Scaling** — Scaler reads pool utilization metrics; adjusts Nomad job count
6. **Packages** — Client calls `/packages/install`; agent runs pip inside the VM via guest agent
7. **Session ends** — Agent deletes KV entry; Consul TTL ensures cleanup on crash

---

## Configuration

### Environment Variables

```bash
# Consul
CONSUL_HOST=localhost
CONSUL_PORT=8500
CONSUL_TOKEN=                        # optional ACL token

# Load Balancer
HAPROXY_CONFIG_DIR=/etc/haproxy
LOAD_BALANCER_ALGORITHM=roundrobin
HEALTH_CHECK_INTERVAL=10s

# Auto-scaling
SCALING_MIN_NODES=1
SCALING_MAX_NODES=10
SCALING_TARGET_UTILIZATION=0.7
SCALING_COOLDOWN_UP=300
SCALING_COOLDOWN_DOWN=600

# Package Management
PACKAGE_PROXY_URL=                   # empty = no proxy
PACKAGE_TIMEOUT=300
PACKAGE_CACHE_DIR=/var/cache/sandbox/packages

# Security (mTLS)
MTLS_ENABLED=true
CERT_DIR=/etc/sandbox/certs
CA_CERT=/etc/sandbox/certs/ca.crt

# Network
TAP_DEVICE_PREFIX=tap
MAC_ADDRESS_PREFIX=06:00
```

### Config Files

**`config/consul.yaml`**
```yaml
serviceDiscovery:
  enabled: true
  host: localhost
  port: 8500
  tags: [sandbox, runtime]
  healthCheck:
    interval: 10s
    timeout: 5s
    deregisterAfter: 1m
```

**`config/autoscaling.yaml`**
```yaml
autoScaling:
  policy:
    minNodes: 1
    maxNodes: 10
    targetUtilization: 0.7
    thresholds:
      scaleUp: 0.8
      scaleDown: 0.5
    cooldown:
      scaleUp: 300
      scaleDown: 600
  metrics:
    evaluationPeriodSeconds: 60
    windowSeconds: 300
    collect: [cpu, memory, pool_utilization, active_sessions]
```

**`config/security.yaml`**
```yaml
security:
  mtls:
    enabled: true
    certDir: /etc/sandbox/certs
    tlsMinVersion: "1.3"
    rotationDays: 30
```

---

## Rollout Plan

| Phase | Features | Notes |
|-------|----------|-------|
| 1 | Consul registration + health checks (#1) | Prerequisite for everything else |
| 2 | HAProxy integration + session KV (#2, #8) | Enables stateless routing |
| 3 | Auto-scaling (#3) | Needs Phase 1 metrics |
| 4 | Package management + TAP/MAC (#4, #5, #6) | Can ship independently |
| 5 | mTLS (#7) | Last — wrap all internal traffic |

**Backward compatibility:** Each phase keeps existing API endpoints working. New behavior is additive. mTLS starts opt-in (`MTLS_ENABLED=false` by default) and becomes the enforced default in Phase 5.

---

## Success Criteria

| Feature | Metric | Target |
|---------|--------|--------|
| Service discovery | Registration success rate | ≥ 99.9% |
| Load balancing | Added latency | < 10ms p99 |
| Auto-scaling | Scaling response time | < 2 minutes |
| Package management | Install success rate | ≥ 99% |
| mTLS | Enforcement | 100% of internal calls |
| Session lookup | Latency | < 5ms p99 |
| Test coverage | New code | ≥ 95% |

---

## Risk Register

| Risk | Mitigation |
|------|------------|
| Consul becomes a SPOF | Run 3-node Consul cluster; agents cache last-known state |
| mTLS cert rotation drops connections | Short-lived certs + connection draining on rotation |
| Auto-scaler thrashes | Cooldown periods + hysteresis thresholds |
| Package install pollutes VM state | Each install runs in a fresh session (single-use VMs) |
| TAP device leak on crash | Cleanup cron job + VM termination hook |
