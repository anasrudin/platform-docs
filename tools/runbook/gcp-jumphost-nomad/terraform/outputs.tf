# ── Jumphost ──────────────────────────────────────────────────────────────────

output "jumphost_public_ip" {
  description = "Public IP of the jumphost (admin SSH access)."
  value       = google_compute_instance.jumphost.network_interface[0].access_config[0].nat_ip
}

output "jumphost_service_account_email" {
  description = "Service account attached to the jumphost."
  value       = google_service_account.jumphost.email
}

output "ssh_jumphost_command" {
  description = "SSH into the jumphost."
  value       = "gcloud compute ssh ${google_compute_instance.jumphost.name} --project=${var.project_id} --zone=${var.zone}"
}

# ── Nomad VM ──────────────────────────────────────────────────────────────────

output "nomad_private_ip" {
  description = "Private IP of the Nomad VM."
  value       = google_compute_instance.nomad.network_interface[0].network_ip
}

output "nomad_public_ip" {
  description = "Public IP of the Nomad VM (null if expose_nomad_public_ip=false)."
  value       = var.expose_nomad_public_ip ? google_compute_instance.nomad.network_interface[0].access_config[0].nat_ip : null
}

output "ssh_nomad_command" {
  description = "SSH directly into the Nomad VM (works via gcloud IAP)."
  value       = "gcloud compute ssh ${google_compute_instance.nomad.name} --project=${var.project_id} --zone=${var.zone}"
}

# ── Layer topology ────────────────────────────────────────────────────────────
# All layers on one VM. controller_ip drives topology.env and health checks.

output "controller_ip" {
  description = "Public IP for platform services (Nomad :4646, Consul :8500, platform-api :8080)."
  value       = local.controller_ip
}

output "worker_ip" {
  description = "Public IP for the worker layer (Firecracker agents). Same as controller for single-server."
  value       = local.controller_ip
}

output "data_ip" {
  description = "Public IP for the data layer (PG :5432, Redis :6379, MinIO :9000/:9001, Jaeger :16686)."
  value       = local.controller_ip
}

output "project_id" {
  description = "GCP project ID (used by gen-topology.sh)."
  value       = var.project_id
}

output "zone" {
  description = "GCP zone (used by gen-topology.sh)."
  value       = var.zone
}

output "nomad_name" {
  description = "Nomad VM name (used by gen-topology.sh)."
  value       = google_compute_instance.nomad.name
}

# ── Dashboard URLs ────────────────────────────────────────────────────────────

output "dashboard_urls" {
  description = "Platform service URLs after deploy completes."
  value = {
    platform_api = "http://${local.controller_ip}:8080/health"
    nomad_ui     = "http://${local.controller_ip}:4646"
    consul_ui    = "http://${local.controller_ip}:8500/ui"
    jaeger_ui    = "http://${local.controller_ip}:16686"
    minio_ui     = "http://${local.controller_ip}:9001"
  }
}

# ── Topology summary ──────────────────────────────────────────────────────────

output "topology_summary" {
  description = "Layer topology. Run gen-topology.sh to write config/topology.env."
  value = {
    controller = {
      layer    = var.controller_layer_name
      host     = local.controller_ip
      services = "Nomad(:4646) Consul(:8500) platform-api(:8080)"
    }
    worker = {
      layer    = var.worker_layer_name
      host     = local.controller_ip
      services = "Firecracker agents, FC pool"
    }
    data = {
      layer    = var.data_layer_name
      host     = local.controller_ip
      services = "PostgreSQL(:5432) Redis(:6379) MinIO(:9000/:9001) Jaeger(:16686)"
    }
  }
}
