locals {
  common_labels = {
    stack = "jumphost-nomad"
  }

  # Resolve the public IP for demo services.
  # When expose_nomad_public_ip=true (default), services are reachable directly
  # on the Nomad VM's public IP. Otherwise fall back to the jumphost public IP.
  controller_ip = var.expose_nomad_public_ip ? google_compute_instance.nomad.network_interface[0].access_config[0].nat_ip : google_compute_instance.jumphost.network_interface[0].access_config[0].nat_ip
}

data "google_compute_image" "base" {
  family  = var.image_family
  project = var.image_project
}

data "google_project" "current" {
  project_id = var.project_id
}

# ── APIs ──────────────────────────────────────────────────────────────────────

resource "google_project_service" "compute" {
  project            = var.project_id
  service            = "compute.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "iam" {
  project            = var.project_id
  service            = "iam.googleapis.com"
  disable_on_destroy = false
}

# ── Network ───────────────────────────────────────────────────────────────────

resource "google_compute_network" "main" {
  name                    = var.network_name
  auto_create_subnetworks = false

  depends_on = [google_project_service.compute]
}

resource "google_compute_subnetwork" "main" {
  name          = var.subnet_name
  ip_cidr_range = var.subnet_cidr
  network       = google_compute_network.main.id
  region        = var.region
}

# ── Firewall ──────────────────────────────────────────────────────────────────

resource "google_compute_firewall" "ssh_jumphost" {
  name          = "${var.network_name}-allow-ssh-jumphost"
  network       = google_compute_network.main.name
  source_ranges = [var.admin_cidr]
  target_tags   = ["jumphost"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

resource "google_compute_firewall" "ssh_nomad" {
  name        = "${var.network_name}-allow-ssh-nomad"
  network     = google_compute_network.main.name
  source_tags = ["jumphost"]
  target_tags = ["nomad"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# Allow direct SSH from admin (needed for gcloud compute ssh / IAP tunnel)
resource "google_compute_firewall" "ssh_nomad_admin" {
  name          = "${var.network_name}-allow-ssh-nomad-admin"
  network       = google_compute_network.main.name
  source_ranges = [var.admin_cidr]
  target_tags   = ["nomad"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# All platform service ports accessible from admin CIDR:
#   4646  Nomad UI/API
#   8080  platform-api
#   8500  Consul UI/API
#   9001  MinIO console
#   9000  MinIO API
#   16686 Jaeger UI
#   4317  OTEL gRPC
#   4318  OTEL HTTP
resource "google_compute_firewall" "platform_services" {
  name          = "${var.network_name}-allow-platform-services"
  network       = google_compute_network.main.name
  source_ranges = [var.admin_cidr]
  target_tags   = ["nomad"]

  allow {
    protocol = "tcp"
    ports    = ["4646", "8080", "8500", "9000", "9001", "16686", "4317", "4318"]
  }
}

# ── Service account ───────────────────────────────────────────────────────────

resource "google_service_account" "jumphost" {
  account_id   = var.service_account_name
  display_name = var.service_account_display_name

  depends_on = [google_project_service.iam]
}

resource "google_project_iam_member" "jumphost_roles" {
  for_each = var.service_account_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.jumphost.email}"
}

# ── Nomad VM ──────────────────────────────────────────────────────────────────

resource "google_compute_instance" "nomad" {
  name             = var.nomad_name
  machine_type     = var.nomad_machine_type
  zone             = var.zone
  tags             = ["nomad"]
  labels           = local.common_labels
  min_cpu_platform = "Intel Cascade Lake"

  # KVM enabled — required for real Firecracker execution
  advanced_machine_features {
    enable_nested_virtualization = true
  }

  boot_disk {
    initialize_params {
      image = data.google_compute_image.base.self_link
      size  = var.boot_disk_size_gb
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.main.id

    # Public IP — conditionally enabled. Default true for demo access.
    dynamic "access_config" {
      for_each = var.expose_nomad_public_ip ? [1] : []
      content {}
    }
  }

  service_account {
    email = "${data.google_project.current.number}-compute@developer.gserviceaccount.com"

    scopes = [
      "https://www.googleapis.com/auth/devstorage.read_only",
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring.write",
      "https://www.googleapis.com/auth/pubsub",
      "https://www.googleapis.com/auth/service.management.readonly",
      "https://www.googleapis.com/auth/servicecontrol",
      "https://www.googleapis.com/auth/trace.append",
    ]
  }

  # Installs: Nomad, Docker CE, Python 3 + venv
  metadata_startup_script = file("${path.module}/../startup/nomad-startup.sh")

  depends_on = [
    google_project_service.compute,
    google_compute_firewall.ssh_nomad,
    google_compute_firewall.platform_services,
  ]
}

# ── Jumphost VM ───────────────────────────────────────────────────────────────

resource "google_compute_instance" "jumphost" {
  name         = var.jumphost_name
  machine_type = var.jumphost_machine_type
  zone         = var.zone
  tags         = ["jumphost"]
  labels       = local.common_labels

  boot_disk {
    initialize_params {
      image = data.google_compute_image.base.self_link
      size  = var.boot_disk_size_gb
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.main.id

    access_config {}
  }

  metadata = {
    nomad_private_ip = google_compute_instance.nomad.network_interface[0].network_ip
    nomad_ssh_user   = var.ssh_user
  }

  metadata_startup_script = file("${path.module}/../startup/jumphost-startup.sh")

  service_account {
    email  = google_service_account.jumphost.email
    scopes = ["cloud-platform"]
  }

  depends_on = [
    google_compute_instance.nomad,
    google_project_iam_member.jumphost_roles,
    google_compute_firewall.ssh_jumphost,
  ]
}

# ── App deployment lifecycle ──────────────────────────────────────────────────
# On create: wait for VM bootstrap, then deploy the full platform stack.
# On destroy: stop Nomad job + kill FC processes before VMs are deleted.

resource "null_resource" "platform_stack" {
  triggers = {
    nomad_instance_id = google_compute_instance.nomad.id
    project_id        = var.project_id
    zone              = var.zone
    nomad_name        = var.nomad_name
    controller_ip     = local.controller_ip
    fc_mode           = var.fc_mode
  }

  # Deploy: sync code, install venv, start data containers, deploy Nomad job
  provisioner "local-exec" {
    command = <<-CMD
      PROJECT_ID='${var.project_id}' \
      ZONE='${var.zone}' \
      NOMAD_NAME='${var.nomad_name}' \
      CONTROLLER_HOST='${local.controller_ip}' \
      FC_MODE='${var.fc_mode}' \
      SSH_USER='${var.ssh_user}' \
      USE_INTERNAL_IP='true' \
      bash "${path.module}/../gcloud/deploy-full-stack.sh" "--fc-mode=${var.fc_mode}" "--internal-ip"
    CMD
  }

  # Cleanup: stop Nomad job + kill Firecracker processes before VMs are removed
  provisioner "local-exec" {
    when       = destroy
    on_failure = continue
    command    = <<-CMD
      PROJECT_ID='${self.triggers.project_id}' \
      ZONE='${self.triggers.zone}' \
      NOMAD_NAME='${self.triggers.nomad_name}' \
      bash "${path.module}/../gcloud/cleanup.sh" --full
    CMD
  }

  depends_on = [
    google_compute_instance.nomad,
    google_compute_instance.jumphost,
  ]
}
