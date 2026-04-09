job "debug-python-runtime" {
  datacenters = ["dc1"]
  type        = "service"

  group "firecracker" {
    count = 1

    constraint {
      attribute = "${meta.node_class}"
      operator  = "="
      value     = "mixed"
    }

    restart {
      attempts = 2
      interval = "10m"
      delay    = "15s"
      mode     = "fail"
    }

    task "fc-agent" {
      driver = "raw_exec"

      config {
        command = "/usr/local/bin/fc-agent"
      }

      env {
        FC_MODE            = "sim"
        SNAPSHOT_NAME      = "python-runtime-example"
        SNAPSHOT_CACHE_DIR = "/var/sandbox/cache"
        MINIO_ENDPOINT     = "http://127.0.0.1:9000"
        MINIO_ACCESS_KEY   = "minioadmin"
        MINIO_SECRET_KEY   = "minioadmin"
        MINIO_BUCKET       = "platform-snapshots"
      }

      resources {
        cpu    = 500
        memory = 512
      }
    }
  }
}
