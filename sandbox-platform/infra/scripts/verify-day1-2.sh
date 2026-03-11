#!/bin/bash
# verify-day1-2.sh
# Verifies all Day 1-2 infrastructure goals are met.
#
# Goals:
#   ✅ nomad status shows 3 nodes
#   ✅ MinIO console accessible at node1:9001
#   ✅ PostgreSQL running, database 'platform' exists
#   ✅ Redis running
#
# Usage:
#   ./verify-day1-2.sh [NODE1_IP]
#   NODE1_IP defaults to localhost (run from node1)

set -euo pipefail

NODE1_IP="${1:-localhost}"
PASS=0
FAIL=0

check() {
    local name="$1"
    local result="$2"
    if [ "$result" = "ok" ]; then
        echo "  ✅ $name"
        PASS=$((PASS + 1))
    else
        echo "  ❌ $name — $result"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== Day 1–2 Infrastructure Verification ==="
echo "    Target node1: ${NODE1_IP}"
echo ""

# ── Nomad ─────────────────────────────────────────────────────────────────────
echo "[ Nomad Cluster ]"

# Check Nomad API is responding
if curl -sf "http://${NODE1_IP}:4646/v1/status/leader" &>/dev/null; then
    check "Nomad API reachable" "ok"
else
    check "Nomad API reachable" "no response at :4646"
fi

# Check node count
if command -v nomad &>/dev/null; then
    NODE_COUNT=$(NOMAD_ADDR="http://${NODE1_IP}:4646" nomad node status 2>/dev/null | grep -c "ready" || echo "0")
    if [ "$NODE_COUNT" -ge 3 ]; then
        check "Nomad nodes (need 3, found ${NODE_COUNT})" "ok"
    else
        check "Nomad nodes (need 3, found ${NODE_COUNT})" "need at least 3 ready nodes"
    fi
else
    check "Nomad CLI available" "nomad not in PATH"
fi

echo ""

# ── MinIO ─────────────────────────────────────────────────────────────────────
echo "[ MinIO ]"

if curl -sf "http://${NODE1_IP}:9000/minio/health/live" &>/dev/null; then
    check "MinIO API healthy (:9000)" "ok"
else
    check "MinIO API healthy (:9000)" "no response at :9000/minio/health/live"
fi

if curl -sf "http://${NODE1_IP}:9001" &>/dev/null; then
    check "MinIO console reachable (:9001)" "ok"
else
    check "MinIO console reachable (:9001)" "no response at :9001"
fi

# Check buckets exist
if command -v mc &>/dev/null; then
    mc alias set _verify "http://${NODE1_IP}:9000" minioadmin minioadmin --quiet 2>/dev/null || true
    for bucket in platform-artifacts platform-tools platform-snapshots; do
        if mc ls "_verify/${bucket}" &>/dev/null; then
            check "Bucket: ${bucket}" "ok"
        else
            check "Bucket: ${bucket}" "not found"
        fi
    done
else
    echo "  [skip] mc not in PATH — skipping bucket checks"
fi

echo ""

# ── PostgreSQL ────────────────────────────────────────────────────────────────
echo "[ PostgreSQL ]"

if pg_isready -h "${NODE1_IP}" -p 5432 -U platform &>/dev/null; then
    check "PostgreSQL accepting connections" "ok"
else
    check "PostgreSQL accepting connections" "pg_isready failed on :5432"
fi

# Check database exists
DB_EXISTS=$(psql -h "${NODE1_IP}" -U platform -d platform \
    -tAc "SELECT 1 FROM pg_database WHERE datname='platform'" 2>/dev/null || echo "")
if [ "$DB_EXISTS" = "1" ]; then
    check "Database 'platform' exists" "ok"
else
    check "Database 'platform' exists" "not found (run 001_init.sql)"
fi

# Check tables exist
TABLES=$(psql -h "${NODE1_IP}" -U platform -d platform \
    -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 2>/dev/null || echo "0")
if [ "$TABLES" -ge 3 ]; then
    check "Schema migrated (${TABLES} tables)" "ok"
else
    check "Schema migrated (${TABLES} tables)" "run infra/postgres/migrations/001_init.sql"
fi

echo ""

# ── Redis ─────────────────────────────────────────────────────────────────────
echo "[ Redis ]"

if redis-cli -h "${NODE1_IP}" -p 6379 ping 2>/dev/null | grep -q "PONG"; then
    check "Redis responding to PING" "ok"
else
    check "Redis responding to PING" "no PONG on :6379"
fi

echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
TOTAL=$((PASS + FAIL))
echo "=== Results: ${PASS}/${TOTAL} checks passed ==="
echo ""

if [ "$FAIL" -eq 0 ]; then
    echo "🎉 Day 1–2 complete! Ready to proceed to Day 3 (Firecracker setup)."
    exit 0
else
    echo "⚠️  ${FAIL} check(s) failed. Fix the issues above before proceeding."
    exit 1
fi
