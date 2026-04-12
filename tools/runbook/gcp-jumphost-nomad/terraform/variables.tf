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
  description = "CIDR allowed to SSH into the jumphost."
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
  description = "Machine type for the Nomad VM."
  type        = string
  default     = "n2-standard-4"
}

variable "boot_disk_size_gb" {
  description = "Boot disk size for both VMs."
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
  description = "Linux user name used when SSHing from jumphost to Nomad."
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
