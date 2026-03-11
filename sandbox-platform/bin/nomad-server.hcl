name      = "node1"
log_level = "INFO"
data_dir  = "/Users/annas/Desktop/code/platform-docs/sandbox-platform/bin/nomad-server"
bind_addr = "127.0.0.1"

advertise {
  http = "127.0.0.1"
  rpc  = "127.0.0.1"
  serf = "127.0.0.1"
}

server {
  enabled          = true
  bootstrap_expect = 1
}

ports {
  http = 4646
  rpc  = 4647
  serf = 4648
}
