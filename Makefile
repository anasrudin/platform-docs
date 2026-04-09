# platform-docs — Root Makefile
# ─────────────────────────────────────────────────────────────────────────────

SERVICES := consul load-balancer nomad-worker data
VENV     := .venv
UV       := uv

.PHONY: all help

all: bootstrap

# ── §1 Development workflow ──────────────────────────────────────────────────

## obs-up: Start the observability stack (Loki + Grafana)
obs-up:
	@docker compose -f docker/obs/compose.obs.yaml --profile obs up -d

## obs-down: Stop the observability stack
obs-down:
	@docker compose -f docker/obs/compose.obs.yaml --profile obs down

## dev: Start the full stack
dev: infra-up
	@echo "Starting full stack..."
	@$(UV) run platform-api & echo $$! > bin/api.pid
	@$(UV) run wasm-agent & echo $$! > bin/wasm.pid
	@$(UV) run fc-agent & echo $$! > bin/fc.pid
	@$(UV) run gui-agent & echo $$! > bin/gui.pid
	@echo "All services running. Use 'make dev-down' to stop."

## dev-down: Stop the full stack
dev-down: infra-down
	@echo "Stopping services..."
	@-[ -f bin/api.pid  ] && kill $$(cat bin/api.pid)  2>/dev/null; rm -f bin/api.pid
	@-[ -f bin/wasm.pid ] && kill $$(cat bin/wasm.pid) 2>/dev/null; rm -f bin/wasm.pid
	@-[ -f bin/fc.pid   ] && kill $$(cat bin/fc.pid)   2>/dev/null; rm -f bin/fc.pid
	@-[ -f bin/gui.pid  ] && kill $$(cat bin/gui.pid)  2>/dev/null; rm -f bin/gui.pid

## bootstrap: Initialize the development environment
bootstrap:
	@echo "Bootstrapping repository..."
	@$(UV) sync
	@mkdir -p bin

## sync: Re-sync dependencies
sync:
	@$(UV) sync

# ── §2 Testing & quality ─────────────────────────────────────────────────────

## test: Run all tests
test:
	@$(UV) run pytest

## lint: Run linting
lint:
	@$(UV) run ruff check .

## fmt: Format code
fmt:
	@$(UV) run ruff format .

## typecheck: Run type checking
typecheck:
	@$(UV) run mypy .

# ── §3 Documentation ─────────────────────────────────────────────────────────

## docs: Build documentation
docs:
	@echo "Building documentation..."

## docs-serve: Serve documentation locally
docs-serve:
	@echo "Serving documentation..."

## docs-lint: Lint documentation
docs-lint:
	@echo "Linting documentation..."

# ── §4 Infrastructure ────────────────────────────────────────────────────────

## infra-up: Start all infrastructure services
infra-up:
	@for svc in $(SERVICES); do $(MAKE) -C src/$$svc up; done

## consul-up: Start Consul
consul-up:
	@$(MAKE) -C src/consul up

## infra-verify: Verify infrastructure health
infra-verify:
	@for svc in $(SERVICES); do $(MAKE) -C src/$$svc status; done

# ── §5 Database management ───────────────────────────────────────────────────

## db-migrate: Run database migrations
db-migrate:
	@echo "Running migrations..."
	@psql -h localhost -U platform -d platform -f src/data/db/migrations/001_init.sql

## db-seed: Seed database with fixture data
db-seed:
	@echo "Seeding database (no seeds defined yet)..."

## minio-buckets: Create MinIO buckets
minio-buckets:
	@$(MAKE) -C src/data up
	@src/data/minio/init-buckets.sh

# ── §6 Utility & cleanup ─────────────────────────────────────────────────────

## clean: Remove generated outputs
clean:
	@echo "Cleaning up..."
	@for svc in $(SERVICES); do $(MAKE) -C src/$$svc clean; done
	@rm -rf $(VENV) .pytest_cache .ruff_cache .mypy_cache bin
	@find . -type d -name "__pycache__" -exec rm -rf {} +

## doctor: Check system dependencies
doctor:
	@which uv || (echo "uv not found. Please install it: https://astral.sh/uv/install.sh" && exit 1)
	@which docker || (echo "docker not found" && exit 1)
	@echo "Everything looks good."

## update-deps: Upgrade all dependencies
update-deps:
	@$(UV) lock --upgrade

# ── §7 Debug ─────────────────────────────────────────────────────────────────

## logs: Tail logs for one service, optionally filtered by level
##       Usage: make logs SERVICE=consul [LEVEL=error]
logs:
	@[ -n "$(SERVICE)" ] || { echo "Usage: make logs SERVICE=<name> [LEVEL=error]"; exit 1; }
	@docker compose logs -f --no-log-prefix $(SERVICE) \
		| jq -r 'select($(if $(LEVEL),.level=="$(LEVEL)",true)) | "\(.ts) \(.level) \(.msg)"'

## trace: Pull all log lines for one trace ID across every service, sorted by time
##        Usage: make trace ID=abc-123
trace:
	@[ -n "$(ID)" ] || { echo "Usage: make trace ID=<trace-id>"; exit 1; }
	@docker compose logs --no-log-prefix 2>/dev/null \
		| jq -r 'select(.trace_id=="$(ID)") | "\(.ts) [\(.service)] \(.level) \(.msg)"' \
		| sort

## shell-db: Open a psql prompt in the running postgres container
shell-db:
	@docker compose exec postgres psql -U platform platform

## shell-redis: Open a redis-cli prompt in the running redis container
shell-redis:
	@docker compose exec redis redis-cli

## health: Poll /health on every service and print a status table
health:
	@printf "%-20s %-8s %s\n" SERVICE STATUS TRACE_ID
	@for svc in api:8080 consul:8500 lb:80; do \
		name=$${svc%%:*}; port=$${svc##*:}; \
		resp=$$(curl -sf http://localhost:$$port/health 2>/dev/null); \
		status=$$(echo $$resp | jq -r '.status // "down"'); \
		trace=$$(curl -sI http://localhost:$$port/health 2>/dev/null | grep -i x-trace-id | awk "{print \$$2}" | tr -d "\r"); \
		printf "%-20s %-8s %s\n" $$name $$status "$${trace:-(none)}"; \
	done

## debug-nomad: Show logs and alloc status for a Nomad job
##              Usage: make debug-nomad JOB=wasm-agent
debug-nomad:
	@[ -n "$(JOB)" ] || { echo "Usage: make debug-nomad JOB=<job-name>"; exit 1; }
	nomad job status $(JOB)
	nomad alloc logs -job $(JOB)

## help: Show this help message
help:
	@echo "Usage: make [target]"
	@echo ""
	@grep -E '^## ' $(MAKEFILE_LIST) | sed -e 's/## //g' -e 's/: /	/g' | expand -t 20
