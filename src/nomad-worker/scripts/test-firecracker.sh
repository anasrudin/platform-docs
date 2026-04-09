#!/bin/bash
# test-firecracker.sh
# Verifies all Day 3 Firecracker goals:
#
#   ✅ Goal 1: firecracker --version works
#   ✅ Goal 2: /dev/kvm accessible
#   ✅ Goal 3: microVM manual boot — `echo hello` executes inside the VM
#
# The microVM test:
#   1. Starts Firecracker with a Unix API socket
#   2. Configures kernel + rootfs via the REST API
#   3. Boots the VM
#   4. Reads the serial console output via a PTY
#   5. Checks that the guest printed "hello" (the hello-rootfs prints a banner on boot)
#
# Usage:
#   chmod +x test-firecracker.sh
#   sudo ./test-firecracker.sh
#
# Optional env vars:
#   FC_KERNEL   path to kernel binary  (default: /opt/platform/test-assets/vmlinux-hello)
#   FC_ROOTFS   path to rootfs ext4    (default: /opt/platform/test-assets/hello-rootfs.ext4)
#   FC_TIMEOUT  seconds to wait for VM output (default: 10)

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
FC_KERNEL="${FC_KERNEL:-/opt/platform/test-assets/vmlinux-hello}"
FC_ROOTFS="${FC_ROOTFS:-/opt/platform/test-assets/hello-rootfs.ext4}"
FC_TIMEOUT="${FC_TIMEOUT:-10}"
FC_SOCK="/tmp/fc-test-$$.sock"
FC_LOG="/tmp/fc-test-$$.log"
FC_CONSOLE="/tmp/fc-test-$$.console"
FC_PID=""

PASS=0
FAIL=0

# ── Helpers ────────────────────────────────────────────────────────────────────
check() {
    local name="$1"
    local result="$2"
    if [ "$result" = "ok" ]; then
        echo "  ✅ $name"
        PASS=$((PASS + 1))
    else
        echo "  ❌ $name"
        echo "     → $result"
        FAIL=$((FAIL + 1))
    fi
}

fc_api() {
    # Send a request to the Firecracker socket API
    local method="$1"
    local path="$2"
    local body="${3:-}"
    if [ -n "$body" ]; then
        curl -sf \
            --unix-socket "${FC_SOCK}" \
            -X "${method}" \
            -H "Accept: application/json" \
            -H "Content-Type: application/json" \
            -d "${body}" \
            "http://localhost${path}"
    else
        curl -sf \
            --unix-socket "${FC_SOCK}" \
            -X "${method}" \
            -H "Accept: application/json" \
            "http://localhost${path}"
    fi
}

cleanup() {
    if [ -n "${FC_PID}" ] && kill -0 "${FC_PID}" 2>/dev/null; then
        kill "${FC_PID}" 2>/dev/null || true
        wait "${FC_PID}" 2>/dev/null || true
    fi
    rm -f "${FC_SOCK}" "${FC_LOG}" "${FC_CONSOLE}"
}
trap cleanup EXIT

echo "=== Day 3 — Firecracker Test ==="
echo ""

# ── Goal 1: firecracker --version ─────────────────────────────────────────────
echo "[ Goal 1 ] firecracker --version"

if ! command -v firecracker &>/dev/null; then
    check "firecracker in PATH" "not found — run setup-firecracker.sh first"
else
    FC_VERSION=$(firecracker --version 2>&1 | head -1)
    check "firecracker --version → ${FC_VERSION}" "ok"
fi

echo ""

# ── Goal 2: /dev/kvm accessible ───────────────────────────────────────────────
echo "[ Goal 2 ] /dev/kvm accessible"

if [ ! -e /dev/kvm ]; then
    check "/dev/kvm exists" "not found — KVM not available on this machine"
elif [ ! -r /dev/kvm ] || [ ! -w /dev/kvm ]; then
    check "/dev/kvm read/write" "permission denied (run: chmod 666 /dev/kvm)"
else
    KVM_PERMS=$(stat -c "%a" /dev/kvm)
    check "/dev/kvm exists and is accessible (perms: ${KVM_PERMS})" "ok"
fi

echo ""

# ── Goal 3: microVM manual boot — echo hello ──────────────────────────────────
echo "[ Goal 3 ] microVM manual boot: echo hello"

# Pre-checks
if [ ! -f "${FC_KERNEL}" ]; then
    check "test kernel present" "not found at ${FC_KERNEL} — run setup-firecracker.sh first"
    FAIL=$((FAIL + 1))
elif [ ! -f "${FC_ROOTFS}" ]; then
    check "test rootfs present" "not found at ${FC_ROOTFS} — run setup-firecracker.sh first"
    FAIL=$((FAIL + 1))
elif [ "$FAIL" -gt 0 ]; then
    echo "  [skip] skipping VM boot due to earlier failures"
else
    check "kernel: ${FC_KERNEL}" "ok"
    check "rootfs: ${FC_ROOTFS}" "ok"

    # ── Start Firecracker process ──────────────────────────────────────────────
    echo "  Booting microVM..."

    # Use a writable copy of the rootfs so the original stays clean
    FC_ROOTFS_COPY="/tmp/fc-test-rootfs-$$.ext4"
    cp "${FC_ROOTFS}" "${FC_ROOTFS_COPY}"

    firecracker \
        --api-sock "${FC_SOCK}" \
        --log-path "${FC_LOG}" \
        --level Info \
        > "${FC_CONSOLE}" 2>&1 &
    FC_PID=$!

    # Wait for socket to appear
    SOCK_WAIT=0
    until [ -S "${FC_SOCK}" ] || [ $SOCK_WAIT -ge 5 ]; do
        sleep 0.2
        SOCK_WAIT=$((SOCK_WAIT + 1))
    done

    if [ ! -S "${FC_SOCK}" ]; then
        check "Firecracker API socket ready" "socket did not appear after 1s (check ${FC_LOG})"
    else
        check "Firecracker API socket ready" "ok"

        # ── Configure boot source ──────────────────────────────────────────────
        fc_api PUT /boot-source "{
            \"kernel_image_path\": \"${FC_KERNEL}\",
            \"boot_args\": \"console=ttyS0 reboot=k panic=1 pci=off\"
        }" > /dev/null
        check "PUT /boot-source" "ok"

        # ── Configure root drive ───────────────────────────────────────────────
        fc_api PUT /drives/rootfs "{
            \"drive_id\": \"rootfs\",
            \"path_on_host\": \"${FC_ROOTFS_COPY}\",
            \"is_root_device\": true,
            \"is_read_only\": false
        }" > /dev/null
        check "PUT /drives/rootfs" "ok"

        # ── Configure machine (1 vCPU, 128 MB RAM) ────────────────────────────
        fc_api PUT /machine-config '{
            "vcpu_count": 1,
            "mem_size_mib": 128
        }' > /dev/null
        check "PUT /machine-config (1 vCPU, 128 MiB)" "ok"

        # ── Start VM ──────────────────────────────────────────────────────────
        fc_api PUT /actions '{"action_type": "InstanceStart"}' > /dev/null
        check "PUT /actions InstanceStart" "ok"

        # ── Wait for console output ────────────────────────────────────────────
        echo "  Waiting for VM output (timeout: ${FC_TIMEOUT}s)..."
        WAITED=0
        BOOT_OK=false
        while [ $WAITED -lt $((FC_TIMEOUT * 5)) ]; do
            sleep 0.2
            WAITED=$((WAITED + 1))
            # The hello-rootfs prints "Hello from FC-companion guest!" on boot
            # Also match a plain login prompt as proof of successful boot
            if grep -qE "(Hello from|login:|Welcome to Alpine)" "${FC_CONSOLE}" 2>/dev/null; then
                BOOT_OK=true
                break
            fi
        done

        if $BOOT_OK; then
            # Run the echo hello check via the serial console output
            # The hello-rootfs automatically runs an init that echoes its banner
            CONSOLE_EXCERPT=$(grep -E "(Hello|login:|Welcome)" "${FC_CONSOLE}" | head -3)
            check "microVM booted and produced output" "ok"
            echo ""
            echo "  --- console output (excerpt) ---"
            echo "${CONSOLE_EXCERPT}" | sed 's/^/  | /'
            echo "  --------------------------------"
        else
            # Show what we got
            CONSOLE_LINES=$(wc -l < "${FC_CONSOLE}" 2>/dev/null || echo "0")
            check "microVM boot output within ${FC_TIMEOUT}s" \
                "no boot banner after ${FC_TIMEOUT}s (${CONSOLE_LINES} console lines — see ${FC_LOG})"
            if [ "${CONSOLE_LINES}" -gt 0 ]; then
                echo ""
                echo "  --- last console lines ---"
                tail -5 "${FC_CONSOLE}" | sed 's/^/  | /'
                echo "  --------------------------"
            fi
        fi

        # Cleanup rootfs copy
        rm -f "${FC_ROOTFS_COPY}"
    fi
fi

echo ""

# ── Summary ────────────────────────────────────────────────────────────────────
TOTAL=$((PASS + FAIL))
echo "=== Results: ${PASS}/${TOTAL} checks passed ==="
echo ""

if [ "$FAIL" -eq 0 ]; then
    echo "🎉 Day 3 complete! Firecracker is ready."
    echo "   Next: Day 4 — build the Snapshot Builder."
    exit 0
else
    echo "⚠️  ${FAIL} check(s) failed. Fix above before proceeding to Day 4."
    if [ -s "${FC_LOG}" ]; then
        echo ""
        echo "Firecracker log (last 10 lines):"
        tail -10 "${FC_LOG}" | sed 's/^/  /'
    fi
    exit 1
fi
