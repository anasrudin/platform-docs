job "nomad-demo-http" {
  datacenters = ["dc1"]
  type        = "service"

  group "web" {
    count = 1

    network {
      port "http" {
        static = 8081
      }
    }

    service {
      provider = "nomad"
      name = "nomad-demo-http"
      port = "http"
      tags = ["demo", "gcp", "http"]

      check {
        type     = "http"
        path     = "/"
        interval = "10s"
        timeout  = "2s"
      }
    }

    task "web" {
      driver = "raw_exec"

      config {
        command = "/bin/bash"
        args = [
          "-lc",
          "exec /usr/bin/python3 -m http.server 8081 --bind 0.0.0.0 --directory local/www",
        ]
      }

      template {
        destination = "local/www/index.html"
        data = <<EOF
<!doctype html>
<html>
  <body>
    <h1>Nomad demo running on GCP</h1>
    <p>The job is running on the private Nomad VM.</p>
  </body>
</html>
EOF
      }

      resources {
        cpu    = 100
        memory = 128
      }
    }
  }
}
