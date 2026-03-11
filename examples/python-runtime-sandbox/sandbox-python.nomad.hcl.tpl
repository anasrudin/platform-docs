job "__JOB_NAME__" {
  datacenters = ["__DATACENTER__"]
  type        = "service"

  group "firecracker" {
    count = 1

    constraint {
      attribute = "${meta.node_class}"
      operator  = "="
      value     = "__NODE_CLASS__"
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
        command = "__FC_AGENT_BIN__"
      }

      env {
        FC_MODE            = "__FC_MODE__"
        SNAPSHOT_NAME      = "__SNAPSHOT_NAME__"
        SNAPSHOT_CACHE_DIR = "__SNAPSHOT_CACHE_DIR__"
        MINIO_ENDPOINT     = "__MINIO_ENDPOINT__"
        MINIO_ACCESS_KEY   = "__MINIO_ACCESS_KEY__"
        MINIO_SECRET_KEY   = "__MINIO_SECRET_KEY__"
        MINIO_BUCKET       = "__MINIO_BUCKET__"
      }

      resources {
        cpu    = 500
        memory = 512
      }
    }
  }
}
