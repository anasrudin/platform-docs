#!/usr/bin/env bash
# test-firecracker-setup.sh
# Verifies the Firecracker binary installation and KVM setup:
#   firecracker --version succeeds
#   /dev/kvm is accessible
#   A microVM boots and produces console output  (requires KVM + test assets)
#
# Usage:
#   bash scripts/test-firecracker-setup.sh
#
# Optional env vars:
#   FC_KERNEL   path to kernel binary  (default: /opt/platform/test-assets/vmlinux-hello)
#   FC_ROOTFS   path to rootfs ext4    (default: /opt/platform/test-assets/hello-rootfs.ext4)
#   FC_TIMEOUT  seconds to wait for VM output (default: 10)

set -euo pipefail

FC_KERNEL="${FC_KERNEL:-/opt/platform/test-assets/vmlinux-hello}"
FC_ROOTFS="${FC_ROOTFS:-/opt/platform/test-assets/hello-rootfs.ext4}"
FC_TIMEOUT="${FC_TIMEOUT:-10}"
FC_SOCK="/tmp/fc-test-$$.sock"
FC_LOG="/tmp/fc-test-$$.log"
FC_CONSOLE="/tmp/fc-test-$$.console"
FC_PID=""

PASS=0; FAIL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

pass() { PASS=$((PASS+1)); echo -e "${GREEN}  PASS${NC} $1"; }
fail() { FAIL=$((FAIL+1)); echo -e "${RED}  FAIL${NC} $1"; [[ -n "${2:-}" ]] && echo "       $2"; }
skip() { echo -e "${YELLOW}  SKIP${NC} $1: $2"; }

fc_api() {
  local method="$1" path="$2" body="${3:-}"
  if [[ -n "$body" ]]; then
    curl -sf --unix-socket "${FC_SOCK}" -X "${method}" \
      -H "Content-Type: application/json" -d "${body}" "http://localhost${path}"
  else
    curl -sf --unix-socket "${FC_SOCK}" -X "${method}" "http://localhost${path}"
  fi
}

cleanup() {
  if [[ -n "${FC_PID}" ]] && kill -0 "${FC_PID}" 2>/dev/null; then
    kill "${FC_PID}" 2>/dev/null || true
    wait "${FC_PID}" 2>/dev/null || true
  fi
  rm -f "${FC_SOCK}" "${FC_LOG}" "${FC_CONSOLE}"
}
trap cleanup EXIT

echo "╔══════════════════════════════════════════════════╗"
echo "║           Firecracker Setup Test                 ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── 1. firecracker binary ─────────────────────────────────────────────────────
echo "── Firecracker binary ──"

if ! command -v firecracker &>/dev/null; then
  fail "firecracker in PATH" "not found — run: make infra-fc-setup"
else
  FC_VERSION=$(firecracker --version 2>&1 | head -1)
  pass "firecracker --version: ${FC_VERSION}"
fi

echo ""

# ── 2. /dev/kvm ───────────────────────────────────────────────────────────────
echo "── KVM access ──"

if [[ ! -e /dev/kvm ]]; then
  fail "/dev/kvm exists" "not found — KVM not available on this machine"
elif [[ ! -r /dev/kvm ]] || [[ ! -w /dev/kvm ]]; then
  fail "/dev/kvm read/write" "permission denied (run: chmod 666 /dev/kvm)"
else
  KVM_PERMS=$(stat -c "%a" /dev/kvm 2>/dev/null || stat -f "%p" /dev/kvm)
  pass "/dev/kvm accessible (perms: ${KVM_PERMS})"
fi

echo ""

# ── 3. microVM boot ───────────────────────────────────────────────────────────
echo "── microVM boot test ──"

if [[ ! -f "${FC_KERNEL}" ]]; then
  skip "microVM boot" "kernel not found at ${FC_KERNEL} — run: make infra-fc-setup"
elif [[ ! -f "${FC_ROOTFS}" ]]; then
  skip "microVM boot" "rootfs not found at ${FC_ROOTFS} — run: make infra-fc-setup"
elif [[ $FAIL -gt 0 ]]; then
  skip "microVM boot" "skipped due to earlier failures"
else
  pass "kernel present: ${FC_KERNEL}"
  pass "rootfs present: ${FC_ROOTFS}"

  FC_ROOTFS_COPY="/tmp/fc-test-rootfs-$$.ext4"
  cp "${FC_ROOTFS}" "${FC_ROOTFS_COPY}"

  firecracker \
    --api-sock "${FC_SOCK}" \
    --log-path "${FC_LOG}" \
    --level Info \
    > "${FC_CONSOLE}" 2>&1 &
  FC_PID=$!

  SOCK_WAIT=0
  until [[ -S "${FC_SOCK}" ]] || [[ $SOCK_WAIT -ge 5 ]]; do
    sleep 0.2
    SOCK_WAIT=$((SOCK_WAIT+1))
  done

  if [[ ! -S "${FC_SOCK}" ]]; then
    fail "Firecracker API socket ready" "socket did not appear (check ${FC_LOG})"
  else
    pass "Firecracker API socket ready"

    fc_api PUT /boot-source "{
      \"kernel_image_path\": \"${FC_KERNEL}\",
      \"boot_args\": \"console=ttyS0 reboot=k panic=1 pci=off\"
    }" > /dev/null && pass "PUT /boot-source" || fail "PUT /boot-source"

    fc_api PUT /drives/rootfs "{
      \"drive_id\": \"rootfs\",
      \"path_on_host\": \"${FC_ROOTFS_COPY}\",
      \"is_root_device\": true,
      \"is_read_only\": false
    }" > /dev/null && pass "PUT /drives/rootfs" || fail "PUT /drives/rootfs"

    fc_api PUT /machine-config '{
      "vcpu_count": 1,
      "mem_size_mib": 128
    }' > /dev/null && pass "PUT /machine-config" || fail "PUT /machine-config"

    fc_api PUT /actions '{"action_type": "InstanceStart"}' > /dev/null \
      && pass "PUT /actions InstanceStart" || fail "PUT /actions InstanceStart"

    echo "  Waiting for VM console output (timeout: ${FC_TIMEOUT}s)..."
    WAITED=0
    BOOT_OK=false
    while [[ $WAITED -lt $((FC_TIMEOUT * 5)) ]]; do
      sleep 0.2
      WAITED=$((WAITED+1))
      if grep -qE "(Hello from|login:|Welcome to Alpine)" "${FC_CONSOLE}" 2>/dev/null; then
        BOOT_OK=true
        break
      fi
    done

    if $BOOT_OK; then
      pass "microVM booted and produced console output"
      echo "  --- console excerpt ---"
      grep -E "(Hello|login:|Welcome)" "${FC_CONSOLE}" | head -3 | sed 's/^/  | /'
      echo "  ----------------------"
    else
      LINES=$(wc -l < "${FC_CONSOLE}" 2>/dev/null || echo "0")
      fail "microVM boot output" "no banner after ${FC_TIMEOUT}s (${LINES} console lines)"
      tail -5 "${FC_CONSOLE}" 2>/dev/null | sed 's/^/  | /' || true
    fi

    rm -f "${FC_ROOTFS_COPY}"
  fi
fi

echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
TOTAL=$((PASS + FAIL))
echo "════════════════════════════════════════"
echo "  Results: ${PASS}/${TOTAL} passed"
echo "════════════════════════════════════════"
[[ $FAIL -eq 0 ]] && echo -e "${GREEN}Firecracker setup is ready.${NC}" \
  || { echo -e "${RED}${FAIL} check(s) failed.${NC}"; [[ -s "${FC_LOG}" ]] && tail -10 "${FC_LOG}" | sed 's/^/  /'; }
[[ $FAIL -eq 0 ]]
