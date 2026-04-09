#!/usr/bin/env bash
# test-infra-cluster.sh
# Verifies the production infrastructure cluster is operational:
#   Nomad API reachable, 3+ ready nodes
#   MinIO API healthy, buckets exist
#   PostgreSQL accepting connections, schema migrated
#   Redis responding to PING
#
# Usage:
#   bash scripts/test-infra-cluster.sh [NODE1_IP]
#   NODE1_IP defaults to localhost (run from node1)

set -euo pipefail

NODE1_IP="${1:-localhost}"
PASS=0; FAIL=0

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

pass() { PASS=$((PASS+1)); echo -e "${GREEN}  PASS${NC} $1"; }
fail() { FAIL=$((FAIL+1)); echo -e "${RED}  FAIL${NC} $1"; [[ -n "${2:-}" ]] && echo "       $2"; }
skip() { echo -e "${YELLOW}  SKIP${NC} $1: $2"; }

echo "╔══════════════════════════════════════════════════╗"
echo "║         Infrastructure Cluster Test              ║"
echo "╚══════════════════════════════════════════════════╝"
echo "  Target node: ${NODE1_IP}"
echo ""

# ── Nomad ─────────────────────────────────────────────────────────────────────
echo "── Nomad Cluster ──"

if curl -sf "http://${NODE1_IP}:4646/v1/status/leader" &>/dev/null; then
  pass "Nomad API reachable (:4646)"
else
  fail "Nomad API reachable" "no response at http://${NODE1_IP}:4646"
fi

if command -v nomad &>/dev/null; then
  NODE_COUNT=$(NOMAD_ADDR="http://${NODE1_IP}:4646" nomad node status 2>/dev/null | grep -c "ready" || echo "0")
  if [[ "$NODE_COUNT" -ge 3 ]]; then
    pass "Nomad ready nodes: ${NODE_COUNT} (need ≥3)"
  else
    fail "Nomad ready nodes" "found ${NODE_COUNT}, need at least 3"
  fi
else
  skip "Nomad node count" "nomad CLI not in PATH"
fi

echo ""

# ── MinIO ─────────────────────────────────────────────────────────────────────
echo "── MinIO ──"

if curl -sf "http://${NODE1_IP}:9000/minio/health/live" &>/dev/null; then
  pass "MinIO API healthy (:9000)"
else
  fail "MinIO API healthy" "no response at http://${NODE1_IP}:9000/minio/health/live"
fi

if curl -sf "http://${NODE1_IP}:9001" &>/dev/null; then
  pass "MinIO console reachable (:9001)"
else
  fail "MinIO console reachable" "no response at http://${NODE1_IP}:9001"
fi

if command -v mc &>/dev/null; then
  mc alias set _ci_check "http://${NODE1_IP}:9000" minioadmin minioadmin --quiet 2>/dev/null || true
  for bucket in platform-artifacts platform-tools platform-snapshots platform-modules; do
    if mc ls "_ci_check/${bucket}" &>/dev/null; then
      pass "MinIO bucket exists: ${bucket}"
    else
      fail "MinIO bucket exists" "bucket '${bucket}' not found — run: make infra-buckets"
    fi
  done
  mc alias remove _ci_check &>/dev/null || true
else
  skip "MinIO bucket check" "mc not in PATH"
fi

echo ""

# ── PostgreSQL ────────────────────────────────────────────────────────────────
echo "── PostgreSQL ──"

if pg_isready -h "${NODE1_IP}" -p 5432 -U platform &>/dev/null; then
  pass "PostgreSQL accepting connections (:5432)"
else
  fail "PostgreSQL accepting connections" "pg_isready failed on ${NODE1_IP}:5432"
fi

DB_EXISTS=$(psql -h "${NODE1_IP}" -U platform -d platform \
  -tAc "SELECT 1 FROM pg_database WHERE datname='platform'" 2>/dev/null || echo "")
if [[ "$DB_EXISTS" == "1" ]]; then
  pass "Database 'platform' exists"
else
  fail "Database 'platform' exists" "not found — run: make infra-migrate"
fi

TABLES=$(psql -h "${NODE1_IP}" -U platform -d platform \
  -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 2>/dev/null || echo "0")
if [[ "$TABLES" -ge 3 ]]; then
  pass "Schema migrated (${TABLES} public tables)"
else
  fail "Schema migrated" "found ${TABLES} tables, want ≥3 — run: make infra-migrate"
fi

echo ""

# ── Redis ─────────────────────────────────────────────────────────────────────
echo "── Redis ──"

if redis-cli -h "${NODE1_IP}" -p 6379 ping 2>/dev/null | grep -q "PONG"; then
  pass "Redis responding to PING (:6379)"
else
  fail "Redis responding to PING" "no PONG at ${NODE1_IP}:6379"
fi

echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
TOTAL=$((PASS + FAIL))
echo "════════════════════════════════════════"
echo "  Results: ${PASS}/${TOTAL} passed"
echo "════════════════════════════════════════"
[[ $FAIL -eq 0 ]] && echo -e "${GREEN}Infrastructure cluster is healthy.${NC}" \
  || echo -e "${RED}${FAIL} check(s) failed.${NC}"
[[ $FAIL -eq 0 ]]
