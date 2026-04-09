#!/bin/bash
# setup-firecracker.sh
# Installs Firecracker + jailer on runtime nodes (node2, node3).
# Also enables KVM and fetches the test kernel + rootfs for Day 3 verification.
#
# Prerequisites: setup-all-nodes.sh already run on this node.
#
# Usage:
#   chmod +x setup-firecracker.sh
#   sudo ./setup-firecracker.sh

set -euo pipefail

echo "=== Day 3 — Firecracker Runtime Setup ==="
echo ""

# ── Detect arch ────────────────────────────────────────────────────────────────
ARCH="$(uname -m)"
echo "Architecture: ${ARCH}"

# ── Install Firecracker ────────────────────────────────────────────────────────
echo "Downloading latest Firecracker release..."
RELEASE_URL="https://github.com/firecracker-microvm/firecracker/releases"
LATEST=$(curl -sL "https://api.github.com/repos/firecracker-microvm/firecracker/releases/latest" \
    | grep '"tag_name"' | cut -d'"' -f4)

echo "  Version: ${LATEST}"
TMP=$(mktemp -d)

curl -Lq \
    "${RELEASE_URL}/download/${LATEST}/firecracker-${LATEST}-${ARCH}.tgz" \
    | tar -xz -C "${TMP}"

# Binaries are named like: firecracker-v1.x.x-x86_64
mv "${TMP}/release-${LATEST}-${ARCH}/firecracker-${LATEST}-${ARCH}" /usr/local/bin/firecracker
mv "${TMP}/release-${LATEST}-${ARCH}/jailer-${LATEST}-${ARCH}"      /usr/local/bin/jailer
chmod +x /usr/local/bin/firecracker /usr/local/bin/jailer
rm -rf "${TMP}"

echo "✅ Firecracker installed: $(firecracker --version | head -1)"
echo "✅ Jailer installed:      $(jailer --version | head -1)"

# ── Enable KVM ─────────────────────────────────────────────────────────────────
echo ""
echo "Enabling KVM..."

# Load the right KVM module
CPU_VENDOR=$(grep -m1 vendor_id /proc/cpuinfo | awk '{print $3}')
if [ "${CPU_VENDOR}" = "GenuineIntel" ]; then
    modprobe kvm_intel || echo "  [warn] kvm_intel already loaded or unavailable"
elif [ "${CPU_VENDOR}" = "AuthenticAMD" ]; then
    modprobe kvm_amd   || echo "  [warn] kvm_amd already loaded or unavailable"
else
    echo "  [warn] Unknown CPU vendor '${CPU_VENDOR}', skipping modprobe"
fi

# Set /dev/kvm permissions (world-readable for dev; restrict to group in prod)
if [ -e /dev/kvm ]; then
    chmod 666 /dev/kvm
    echo "✅ /dev/kvm accessible ($(ls -l /dev/kvm))"
else
    echo "❌ /dev/kvm not found. KVM may not be supported on this node."
    echo "   On GCP: ensure 'KVM device' is enabled in VM settings."
    exit 1
fi

# ── Persist KVM module load on reboot ─────────────────────────────────────────
if [ "${CPU_VENDOR}" = "GenuineIntel" ]; then
    echo "kvm_intel" >> /etc/modules-load.d/kvm.conf
elif [ "${CPU_VENDOR}" = "AuthenticAMD" ]; then
    echo "kvm_amd"   >> /etc/modules-load.d/kvm.conf
fi

# ── Download test kernel + rootfs ─────────────────────────────────────────────
# These are the official Firecracker getting-started demo artifacts.
# They are only used for Day 3 manual verification — not for production.
echo ""
echo "Downloading test kernel and rootfs for Day 3 verification..."

TEST_DIR="/opt/platform/test-assets"
mkdir -p "${TEST_DIR}"

FC_DEMO="https://s3.amazonaws.com/spec.ccfc.min/img/quickstart_guide/${ARCH}"

# Kernel
if [ ! -f "${TEST_DIR}/vmlinux-hello" ]; then
    curl -Lq "${FC_DEMO}/kernels/vmlinux.bin" -o "${TEST_DIR}/vmlinux-hello"
    echo "✅ Kernel downloaded: ${TEST_DIR}/vmlinux-hello"
else
    echo "  [skip] kernel already exists"
fi

# Root filesystem
if [ ! -f "${TEST_DIR}/hello-rootfs.ext4" ]; then
    curl -Lq "${FC_DEMO}/rootfs/bionic.rootfs.ext4" -o "${TEST_DIR}/hello-rootfs.ext4"
    echo "✅ Rootfs downloaded: ${TEST_DIR}/hello-rootfs.ext4"
else
    echo "  [skip] rootfs already exists"
fi

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo "=== Firecracker Setup Complete ==="
echo ""
echo "  firecracker : $(which firecracker)"
echo "  jailer      : $(which jailer)"
echo "  /dev/kvm    : $(ls -l /dev/kvm)"
echo "  test kernel : ${TEST_DIR}/vmlinux-hello"
echo "  test rootfs : ${TEST_DIR}/hello-rootfs.ext4"
echo ""
echo "Next: run  sudo ./test-firecracker.sh  to verify Day 3 goals."
