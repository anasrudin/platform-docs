job "sandbox-worker" {
  datacenters = ["dc1"]
  type        = "service"

  # ── fc-agent: Firecracker microVM ─────────────────────────────────────────
  group "fc-agent" {
    count = 2

    constraint {
      attribute = "${node.class}"
      value     = "firecracker"
    }

    network {
      port "api" { static = 8081 }
    }

    service {
      name = "sandbox-fc-agent"
      port = "api"
      tags = ["sandbox", "runtime=firecracker"]
      check {
        type     = "http"
        path     = "/health"
        interval = "10s"
        timeout  = "2s"
      }
    }

    task "fc-agent" {
      driver = "docker"
      config {
        image = "your-registry/sandbox-fc-agent:latest"
        ports = ["api"]
        devices = [{
          host_path      = "/dev/kvm"
          container_path = "/dev/kvm"
        }]
        volumes = ["/opt/sandbox/snapshots:/snapshots"]
      }
      env {
        RUNTIME_TIER      = "firecracker"
        API_PORT          = "8081"
        CONSUL_ENABLED    = "true"
        CONSUL_ADDR       = "127.0.0.1:8500"
        FIRECRACKER_BIN   = "/usr/local/bin/firecracker"
        FIRECRACKER_POOL  = "5"
        FC_SNAPSHOT_CACHE = "/snapshots"
        MINIO_ENDPOINT    = "http://minio.service.consul:9000"
      }
      resources {
        cpu    = 2000
        memory = 4096
      }
    }
  }

  # ── wasm-agent: WebAssembly ───────────────────────────────────────────────
  # raw_exec — WASM sandbox provides its own isolation, no Docker needed.
  # Wasmtime + Python installed on host via setup-firecracker.sh.
  group "wasm-agent" {
    count = 2

    constraint {
      attribute = "${node.class}"
      value     = "wasm"
    }

    network {
      port "api" { static = 8082 }
    }

    service {
      name = "sandbox-wasm-agent"
      port = "api"
      tags = ["sandbox", "runtime=wasm"]
      check {
        type     = "http"
        path     = "/health"
        interval = "10s"
        timeout  = "2s"
      }
    }

    task "wasm-agent" {
      driver = "raw_exec"
      config {
        command = "/usr/bin/python3"
        args    = ["-m", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8082"]
      }
      env {
        RUNTIME_TIER   = "wasm"
        API_PORT       = "8082"
        PYTHONPATH     = "/opt/sandbox-worker/src"
        WASMTIME_BIN   = "/usr/local/bin/wasmtime"
        CONSUL_ENABLED = "true"
        CONSUL_ADDR    = "127.0.0.1:8500"
        MINIO_ENDPOINT = "http://minio.service.consul:9000"
      }
      resources {
        cpu    = 500
        memory = 512
      }
    }
  }

  # ── gui-agent: Chromium + Playwright ──────────────────────────────────────
  group "gui-agent" {
    count = 1

    constraint {
      attribute = "${node.class}"
      value     = "gui"
    }

    network {
      port "api" { static = 8083 }
      port "vnc" { static = 5900 }
    }

    service {
      name = "sandbox-gui-agent"
      port = "api"
      tags = ["sandbox", "runtime=gui"]
      check {
        type     = "http"
        path     = "/health"
        interval = "10s"
        timeout  = "2s"
      }
    }

    task "gui-agent" {
      driver = "docker"
      config {
        image = "your-registry/sandbox-gui-agent:latest"
        ports = ["api", "vnc"]
      }
      env {
        RUNTIME_TIER   = "gui"
        API_PORT       = "8083"
        DISPLAY        = ":99"
        CONSUL_ENABLED = "true"
        CONSUL_ADDR    = "127.0.0.1:8500"
        MINIO_ENDPOINT = "http://minio.service.consul:9000"
      }
      resources {
        cpu    = 2000
        memory = 4096
      }
    }
  }
}
