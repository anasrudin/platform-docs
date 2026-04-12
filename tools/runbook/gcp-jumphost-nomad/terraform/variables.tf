variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "access_token" {
  description = "Optional OAuth access token for Terraform to use instead of metadata credentials."
  type        = string
  default     = null
}

variable "region" {
  description = "GCP region for the subnet."
  type        = string
  default     = "asia-southeast1"
}

variable "zone" {
  description = "GCP zone for both instances."
  type        = string
  default     = "asia-southeast1-a"
}

variable "network_name" {
  description = "VPC name."
  type        = string
  default     = "jump-nomad-vpc"
}

variable "subnet_name" {
  description = "Subnet name."
  type        = string
  default     = "jump-nomad-subnet"
}

variable "subnet_cidr" {
  description = "Subnet CIDR."
  type        = string
  default     = "10.42.0.0/24"
}

variable "admin_cidr" {
  description = "CIDR allowed to SSH into the jumphost and reach platform service ports. Use your public IP: curl -4 ifconfig.me"
  type        = string
}

variable "jumphost_name" {
  description = "Name of the jumphost VM."
  type        = string
  default     = "jumphost"
}

variable "nomad_name" {
  description = "Name of the Nomad VM."
  type        = string
  default     = "nomad"
}

variable "jumphost_machine_type" {
  description = "Machine type for the jumphost VM."
  type        = string
  default     = "e2-medium"
}

variable "nomad_machine_type" {
  description = "Machine type for the Nomad VM. Must support nested virtualization (Intel n2/n1/c2)."
  type        = string
  default     = "n2-standard-4"
}

variable "boot_disk_size_gb" {
  description = "Boot disk size for both VMs (GB)."
  type        = number
  default     = 30
}

variable "image_family" {
  description = "Boot image family."
  type        = string
  default     = "debian-12"
}

variable "image_project" {
  description = "Project that publishes the image family."
  type        = string
  default     = "debian-cloud"
}

variable "ssh_user" {
  description = "Linux username used when SSHing from jumphost to Nomad and for app deployment."
  type        = string
}

variable "service_account_name" {
  description = "Service account ID attached to the jumphost."
  type        = string
  default     = "jumphost-operator"
}

variable "service_account_display_name" {
  description = "Display name for the jumphost service account."
  type        = string
  default     = "Jumphost Operator"
}

variable "service_account_roles" {
  description = "Project IAM roles granted to the jumphost service account."
  type        = set(string)
  default = [
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/compute.viewer",
  ]
}

variable "expose_nomad_public_ip" {
  description = "Give the Nomad VM a public IP. Required for direct demo access (platform-api, Nomad UI, Consul, Jaeger, MinIO)."
  type        = bool
  default     = true
}

variable "fc_mode" {
  description = "FC_MODE passed to the platform-api Nomad job. sim = no snapshot required (demo default). real = actual Firecracker microVMs (needs snapshot in MinIO)."
  type        = string
  default     = "sim"

  validation {
    condition     = contains(["sim", "real"], var.fc_mode)
    error_message = "fc_mode must be 'sim' or 'real'."
  }
}

# ── Layer topology (logical names, single-server for now) ─────────────────────

variable "controller_layer_name" {
  description = "Logical name for the controller layer (Nomad, Consul, platform-api)."
  type        = string
  default     = "controller"
}

variable "worker_layer_name" {
  description = "Logical name for the worker layer (Firecracker agents)."
  type        = string
  default     = "worker"
}

variable "data_layer_name" {
  description = "Logical name for the data layer (PostgreSQL, Redis, MinIO, Jaeger)."
  type        = string
  default     = "data"
}
