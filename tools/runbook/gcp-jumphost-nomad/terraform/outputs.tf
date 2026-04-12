# ── Jumphost ──────────────────────────────────────────────────────────────────
output "jumphost_public_ip" {
  description = "Public IP of the jumphost."
  value       = google_compute_instance.jumphost.network_interface[0].access_config[0].nat_ip
}

output "jumphost_service_account_email" {
  description = "Service account attached to the jumphost."
  value       = google_service_account.jumphost.email
}

output "ssh_jumphost_command" {
  description = "Helper command to SSH into the jumphost."
  value       = "gcloud compute ssh ${google_compute_instance.jumphost.name} --project=${var.project_id} --zone=${var.zone}"
}

# ── Nomad VM ──────────────────────────────────────────────────────────────────
output "nomad_private_ip" {
  description = "Private IP of the Nomad VM (akses via jumphost atau tunnel)."
  value       = google_compute_instance.nomad.network_interface[0].network_ip
}

output "ssh_nomad_via_jumphost_command" {
  description = "Helper command to SSH into Nomad via the jumphost."
  value       = "PROJECT_ID=${var.project_id} ZONE=${var.zone} JUMPHOST_NAME=${google_compute_instance.jumphost.name} NOMAD_NAME=${google_compute_instance.nomad.name} SSH_USER=${var.ssh_user} ../gcloud/ssh-nomad.sh"
}

# ── Layer topology ────────────────────────────────────────────────────────────
# Untuk single-server semua layer pakai IP yang sama (jumphost public IP).
# Saat split ke multi-server, ganti output ini ke IP VM yang relevan.

output "controller_ip" {
  description = "IP untuk layer controller (Nomad :4646, Consul :8500, platform-api :8080). Saat ini = jumphost public IP."
  value       = google_compute_instance.jumphost.network_interface[0].access_config[0].nat_ip
}

output "worker_ip" {
  description = "IP untuk layer worker (Firecracker agents). Saat ini = sama dengan controller."
  value       = google_compute_instance.jumphost.network_interface[0].access_config[0].nat_ip
}

output "data_ip" {
  description = "IP untuk layer data (PG :5432, Redis :6379, MinIO :9000/:9001, Jaeger :16686). Saat ini = sama dengan controller."
  value       = google_compute_instance.jumphost.network_interface[0].access_config[0].nat_ip
}

output "project_id" {
  description = "GCP project ID (untuk gen-topology.sh)."
  value       = var.project_id
}

output "zone" {
  description = "GCP zone (untuk gen-topology.sh)."
  value       = var.zone
}

output "nomad_name" {
  description = "Nama Nomad VM (untuk gen-topology.sh)."
  value       = google_compute_instance.nomad.name
}

# ── Topology summary ──────────────────────────────────────────────────────────
output "topology_summary" {
  description = "Ringkasan layer topology. Gunakan gen-topology.sh untuk menulis ke config/topology.env."
  value = {
    controller = {
      layer    = var.controller_layer_name
      host     = google_compute_instance.jumphost.network_interface[0].access_config[0].nat_ip
      services = "Nomad(:4646) Consul(:8500) platform-api(:8080)"
    }
    worker = {
      layer    = var.worker_layer_name
      host     = google_compute_instance.jumphost.network_interface[0].access_config[0].nat_ip
      services = "Firecracker agents, FC pool"
    }
    data = {
      layer    = var.data_layer_name
      host     = google_compute_instance.jumphost.network_interface[0].access_config[0].nat_ip
      services = "PostgreSQL(:5432) Redis(:6379) MinIO(:9000/:9001) Jaeger(:16686)"
    }
  }
}
