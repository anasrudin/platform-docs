job "sandbox-agents" {
  datacenters = ["dc1"]
  type        = "service"

  group "firecracker-group" {
    task "fc-agent" {
      driver = "raw_exec"
      config {
        command = "/usr/local/bin/fc-agent"
      }
    }
  }

  group "wasm-group" {
    task "wasm-agent" {
      driver = "raw_exec"
      config {
        command = "/usr/local/bin/wasm-agent"
      }
    }
  }

  group "gui-group" {
    task "gui-agent" {
      driver = "raw_exec"
      config {
        command = "/usr/local/bin/gui-agent"
      }
    }
  }
}
