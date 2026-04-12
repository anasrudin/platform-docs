output "jumphost_public_ip" {
  description = "Public IP of the jumphost."
  value       = google_compute_instance.jumphost.network_interface[0].access_config[0].nat_ip
}

output "nomad_private_ip" {
  description = "Private IP of the Nomad VM."
  value       = google_compute_instance.nomad.network_interface[0].network_ip
}

output "jumphost_service_account_email" {
  description = "Service account attached to the jumphost."
  value       = google_service_account.jumphost.email
}

output "ssh_jumphost_command" {
  description = "Helper command to SSH into the jumphost."
  value       = "gcloud compute ssh ${google_compute_instance.jumphost.name} --project=${var.project_id} --zone=${var.zone}"
}

output "ssh_nomad_via_jumphost_command" {
  description = "Helper command to SSH into Nomad via the jumphost."
  value       = "PROJECT_ID=${var.project_id} ZONE=${var.zone} JUMPHOST_NAME=${google_compute_instance.jumphost.name} NOMAD_NAME=${google_compute_instance.nomad.name} SSH_USER=${var.ssh_user} ../gcloud/ssh-nomad.sh"
}
