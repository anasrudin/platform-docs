locals {
  common_labels = {
    stack = "jumphost-nomad"
  }
}

data "google_compute_image" "base" {
  family  = var.image_family
  project = var.image_project
}

data "google_project" "current" {
  project_id = var.project_id
}

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

resource "google_compute_network" "main" {
  name                    = var.network_name
  auto_create_subnetworks = false

  depends_on = [
    google_project_service.compute,
  ]
}

resource "google_compute_subnetwork" "main" {
  name          = var.subnet_name
  ip_cidr_range = var.subnet_cidr
  network       = google_compute_network.main.id
  region        = var.region
}

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

resource "google_compute_firewall" "nomad_ui" {
  name        = "${var.network_name}-allow-nomad-ui"
  network     = google_compute_network.main.name
  source_tags = ["jumphost"]
  target_tags = ["nomad"]

  allow {
    protocol = "tcp"
    ports    = ["4646"]
  }
}

resource "google_compute_firewall" "nomad_demo_http" {
  name        = "${var.network_name}-allow-nomad-demo-http"
  network     = google_compute_network.main.name
  source_tags = ["jumphost"]
  target_tags = ["nomad"]

  allow {
    protocol = "tcp"
    ports    = ["8081"]
  }
}

resource "google_compute_firewall" "platform_api_public" {
  name          = "${var.network_name}-allow-platform-api-public"
  network       = google_compute_network.main.name
  source_ranges = [var.admin_cidr]
  target_tags   = ["nomad"]

  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }
}

resource "google_service_account" "jumphost" {
  account_id   = var.service_account_name
  display_name = var.service_account_display_name

  depends_on = [
    google_project_service.iam,
  ]
}

resource "google_project_iam_member" "jumphost_roles" {
  for_each = var.service_account_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.jumphost.email}"
}

resource "google_compute_instance" "nomad" {
  name             = var.nomad_name
  machine_type     = var.nomad_machine_type
  zone             = var.zone
  tags             = ["nomad"]
  labels           = local.common_labels
  min_cpu_platform = "Intel Cascade Lake"

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

  metadata_startup_script = file("${path.module}/../startup/nomad-startup.sh")

  depends_on = [
    google_project_service.compute,
    google_compute_firewall.ssh_nomad,
    google_compute_firewall.nomad_ui,
    google_compute_firewall.platform_api_public,
  ]
}

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

    access_config {
    }
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
