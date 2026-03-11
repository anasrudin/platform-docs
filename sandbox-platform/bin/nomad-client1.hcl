name      = "node2"
log_level = "INFO"
data_dir  = "/Users/annas/Desktop/code/platform-docs/sandbox-platform/bin/nomad-client1"
bind_addr = "127.0.0.1"

advertise {
  http = "127.0.0.1"
  rpc  = "127.0.0.1"
  serf = "127.0.0.1"
}

client {
  enabled = true
  servers = ["127.0.0.1:4647"]
  meta {
    "node_class" = "mixed"
  }
}

plugin "raw_exec" {
  config {
    enabled = true
  }
}

ports {
  http = 5646
  rpc  = 5647
  serf = 5648
}
