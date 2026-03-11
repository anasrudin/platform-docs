job "sandbox-agents" {
  datacenters = ["dc1"]
  type = "service"
  group "firecracker-group" {
    task "fc-agent" {
      driver = "raw_exec"
      config { command = "/Users/annas/Desktop/code/platform-docs/sandbox-platform/bin/fc-agent" }
    }
  }
}
