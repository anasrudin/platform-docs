BINARY_API    := bin/platform-api
BINARY_WASM   := bin/wasm-agent
BINARY_FC     := bin/fc-agent
BINARY_GUI    := bin/gui-agent

.PHONY: all build run dev stop clean dev-nomad nomad-start test-nomad-agents \
        infra-setup-node infra-setup-control infra-migrate infra-buckets infra-verify \
        infra-fc-setup infra-fc-test

all: build

build:
	@echo "Building binaries..."
	@mkdir -p bin
	go build -o $(BINARY_API) ./cmd/platform-api
	go build -o $(BINARY_WASM) ./cmd/wasm-agent
	go build -o $(BINARY_FC) ./cmd/fc-agent
	go build -o $(BINARY_GUI) ./cmd/gui-agent

run: build
	@echo "Starting platform-api and agents..."
	./$(BINARY_API) & echo $$! > bin/api.pid
	./$(BINARY_WASM) & echo $$! > bin/wasm.pid
	./$(BINARY_FC) & echo $$! > bin/fc.pid
	./$(BINARY_GUI) & echo $$! > bin/gui.pid
	@echo "All services running natively. Press Ctrl+C to stop."
	@trap 'kill $$(cat bin/*.pid) 2>/dev/null; rm -f bin/*.pid; exit 0' INT TERM; wait

dev: stop
	@echo "Starting infrastructure (PostgreSQL, Redis)..."
	docker compose up -d
	@echo "Waiting for backing services to be healthy..."
	@sleep 5
	@$(MAKE) run

stop:
	@echo "Stopping infrastructure and services..."
	@-kill $$(cat bin/*.pid 2>/dev/null) 2>/dev/null || true
	@-rm -f bin/*.pid
	@-nomad job stop sandbox-agents 2>/dev/null || true
	-docker compose down || true

clean: stop
	@echo "Cleaning up build artifacts..."
	rm -rf bin/

nomad-start:
	@echo "Starting 3-node Nomad Cluster..."
	@mkdir -p scripts
	@chmod +x scripts/start-nomad-cluster.sh
	@./scripts/start-nomad-cluster.sh

test-nomad-agents: build nomad-start
	@echo "Deploying fc-agent via Nomad..."
	@echo 'job "sandbox-agents" {' > bin/sandbox-agents.nomad
	@echo '  datacenters = ["dc1"]' >> bin/sandbox-agents.nomad
	@echo '  type = "service"' >> bin/sandbox-agents.nomad
	@echo '  group "firecracker-group" {' >> bin/sandbox-agents.nomad
	@echo '    task "fc-agent" {' >> bin/sandbox-agents.nomad
	@echo '      driver = "raw_exec"' >> bin/sandbox-agents.nomad
	@echo '      config { command = "$(PWD)/bin/fc-agent" }' >> bin/sandbox-agents.nomad
	@echo '    }' >> bin/sandbox-agents.nomad
	@echo '  }' >> bin/sandbox-agents.nomad
	@echo '}' >> bin/sandbox-agents.nomad
	@nomad job run bin/sandbox-agents.nomad
	@echo "fc-agent deployed to Nomad. Checking status..."
	@sleep 2
	@nomad job status sandbox-agents

dev-nomad: stop
	@echo "Starting infrastructure (PostgreSQL, Redis)..."
	docker compose up -d
	@echo "Waiting for backing services to be healthy..."
	@sleep 5
	@$(MAKE) test-nomad-agents
	@echo "Starting platform-api locally..."
	./$(BINARY_API) & echo $$! > bin/api.pid
	@echo "Starting other agents locally (wasm, gui)..."
	./$(BINARY_WASM) & echo $$! > bin/wasm.pid
	./$(BINARY_GUI) & echo $$! > bin/gui.pid
	@echo "All services running (fc-agent in Nomad). Press Ctrl+C to stop."
	@trap 'kill $$(cat bin/*.pid 2>/dev/null) 2>/dev/null; rm -f bin/*.pid; nomad job stop sandbox-agents 2>/dev/null; docker compose down; exit 0' INT TERM; wait

# ── Day 1-2 Production Infrastructure ────────────────────────────────────────
# Run these on GCP nodes to set up the production cluster.

## infra-setup-node: Install Nomad on all nodes (run on each node)
infra-setup-node:
	@echo "Installing base dependencies + Nomad..."
	@chmod +x infra/scripts/setup-all-nodes.sh
	sudo infra/scripts/setup-all-nodes.sh

## infra-setup-control: Install PostgreSQL + Redis + MinIO on node1
infra-setup-control:
	@echo "Installing control node services (PostgreSQL, Redis, MinIO)..."
	@chmod +x infra/scripts/setup-control-node.sh
	sudo infra/scripts/setup-control-node.sh

## infra-migrate: Run PostgreSQL migrations against NODE1_IP (default: localhost)
infra-migrate:
	@echo "Running database migrations..."
	psql -h $${NODE1_IP:-localhost} -U platform -d platform \
		-f infra/postgres/migrations/001_init.sql
	@echo "✅ Migrations applied."

## infra-buckets: Create MinIO buckets (requires mc in PATH or MINIO_ENDPOINT set)
infra-buckets:
	@echo "Initializing MinIO buckets..."
	@chmod +x infra/minio/init-buckets.sh
	MINIO_ENDPOINT=$${MINIO_ENDPOINT:-http://localhost:9000} \
		infra/minio/init-buckets.sh

## infra-verify: Check all Day 1-2 goals against NODE1_IP (default: localhost)
infra-verify:
	@echo "Verifying Day 1-2 infrastructure..."
	@chmod +x infra/scripts/verify-day1-2.sh
	infra/scripts/verify-day1-2.sh $${NODE1_IP:-localhost}

# ── Day 3 — Firecracker ───────────────────────────────────────────────────────

## infra-fc-setup: Install Firecracker + KVM on runtime node (run on node2/node3)
infra-fc-setup:
	@echo "Installing Firecracker runtime..."
	@chmod +x infra/scripts/setup-firecracker.sh
	sudo infra/scripts/setup-firecracker.sh

## infra-fc-test: Verify all Day 3 Firecracker goals
infra-fc-test:
	@echo "Testing Firecracker..."
	@chmod +x infra/scripts/test-firecracker.sh
	sudo infra/scripts/test-firecracker.sh
