# GCP Jumphost + Nomad

Runbook ini membuat topologi sederhana sesuai diagram:

- laptop -> `gcloud compute ssh` -> `jumphost`
- `jumphost` -> SSH private IP -> `nomad`
- service account ditempel ke `jumphost`
- `nomad` hanya punya private IP

Ada dua jalur yang setara:

- `gcloud/` untuk provision pakai Google Cloud CLI
- `terraform/` untuk provision pakai Terraform

## Asumsi

- project GCP sudah ada
- billing sudah aktif
- Anda sudah login `gcloud auth login`
- API `compute.googleapis.com` dan `iam.googleapis.com` boleh di-enable
- topologi ini sengaja dibuat kecil: 1 jumphost + 1 single-node Nomad

## Struktur

- `gcloud/create-topology.sh`: buat network, firewall, service account, VM
- `gcloud/destroy-topology.sh`: hapus resource yang dibuat script CLI
- `gcloud/ssh-jumphost.sh`: SSH ke jumphost
- `gcloud/ssh-nomad.sh`: SSH ke Nomad via jumphost
- `gcloud/run-terraform-on-jumphost.sh`: sync runbook lalu jalankan Terraform di jumphost
- `gcloud/import-existing-state.sh`: import resource yang sudah dibuat gcloud ke state Terraform
- `gcloud/apply-from-jumphost.sh`: sync, import, lalu `terraform apply` dari jumphost
- `gcloud/deploy-platform-api.sh`: deploy platform-api saja ke Nomad (tanpa full stack)
- `gcloud/deploy-full-stack.sh`: deploy **seluruh stack** — sync services/, start docker compose (MinIO/Postgres/Redis/Consul/Jaeger), buka firewall, deploy platform-api dengan env lengkap (OTEL + Consul + DB + Redis)
- `gcloud/cleanup.sh`: stop Nomad job, kill FC orphan, opsional hapus snapshot MinIO
- `smoke-test.sh`: end-to-end test — health + session + execute Python di VM nyata + cek Consul + cek Jaeger
- `startup/jumphost-startup.sh`: bootstrap ringan untuk jumphost
- `startup/nomad-startup.sh`: install dan start single-node Nomad
- `terraform/`: versi Terraform dari topologi yang sama

## Quick Start: gcloud

```bash
cd tools/runbook/gcp-jumphost-nomad

export PROJECT_ID="agent-automation-470608"
export REGION="asia-southeast1"
export ZONE="asia-southeast1-a"
export ADMIN_CIDR="YOUR_PUBLIC_IP/32"

./gcloud/create-topology.sh
./gcloud/ssh-jumphost.sh
./gcloud/ssh-nomad.sh
./gcloud/run-terraform-on-jumphost.sh
./gcloud/apply-from-jumphost.sh
```

Kalau belum tahu IP publik Anda:

```bash
curl -4 ifconfig.me
```

## Quick Start: Full Stack Deploy (platform-api + seluruh infrastruktur)

Asumsi VM GCP Nomad sudah ada dan snapshot `python-v1` sudah ada di MinIO:

```bash
# Deploy semua sekaligus dari laptop (sync services/, start docker, buka firewall, deploy Nomad job)
bash tools/runbook/gcp-jumphost-nomad/gcloud/deploy-full-stack.sh

# Verifikasi semua komponen
bash tools/runbook/gcp-jumphost-nomad/smoke-test.sh http://34.143.174.106:8080
```

Dashboard setelah deploy:

| Dashboard | URL |
|-----------|-----|
| Nomad     | http://34.143.174.106:4646 |
| Consul    | http://34.143.174.106:8500/ui |
| Jaeger    | http://34.143.174.106:16686 |
| MinIO     | http://34.143.174.106:9001 |
| API       | http://34.143.174.106:8080/health |

Untuk melihat log dan trace workflow lengkap, lihat [firecracker-runbook-linux.md](../../../docs/how-to/firecracker-runbook-linux.md) section 9.

## Quick Start: Terraform

```bash
cd tools/runbook/gcp-jumphost-nomad/terraform
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply
```

Setelah apply:

```bash
terraform output
```

## Variabel Penting

Baik script `gcloud` maupun Terraform memakai parameter yang sama secara konsep:

- `project_id`: project GCP
- `region` / `zone`: lokasi resource
- `admin_cidr`: IP/CIDR yang boleh SSH ke jumphost
- `jumphost_name`: nama VM jumphost
- `nomad_name`: nama VM Nomad
- `ssh_user`: username Linux yang dipakai saat SSH ke Nomad
- `service_account_roles`: role IAM yang ditempel ke service account jumphost

Default `service_account_roles` sengaja minim:

- `roles/logging.logWriter`
- `roles/monitoring.metricWriter`
- `roles/compute.viewer`

Kalau Anda memang ingin menjalankan automation admin dari dalam jumphost, tambahkan role yang lebih tinggi sendiri. Jangan default ke `owner`.

## Catatan

- Saya taruh file di `tools/runbook/` karena folder `iac/` sekarang masuk `.gitignore`.
- `nomad` dibootstrap sebagai single-node server+client supaya topologi langsung hidup.
- `nomad` dipasang di machine type Intel `n2-standard-4` dengan nested virtualization aktif, supaya `/dev/kvm` tersedia untuk Firecracker real mode.
- jumphost juga dipasangi `terraform` dan helper `jumphost-terraform` supaya bisa menjalankan aplikasi provisioning dari host itu sendiri.
- kalau infrastruktur awal dibuat dengan `gcloud`, gunakan `gcloud/import-existing-state.sh` atau `gcloud/apply-from-jumphost.sh` supaya resource yang sudah ada masuk ke state Terraform.
- Firewall hanya membuka:
  - SSH ke jumphost dari `admin_cidr`
  - SSH ke Nomad dari instance bertag `jumphost`
  - Nomad UI `:4646` dari instance bertag `jumphost`
  - port demo `:8081` dari instance bertag `jumphost` agar service/job bisa di-forward ke laptop
  - `platform-api :8080` dari `admin_cidr` untuk tes `POST /execute` langsung dari laptop
