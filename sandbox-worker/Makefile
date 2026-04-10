# sandbox-platform — Python 3.12+ / FastAPI
# ─────────────────────────────────────────────────────────────────────────────

VENV        := .venv
PYTHON      := $(VENV)/bin/python
PYTEST      := $(VENV)/bin/pytest
UVICORN     := $(VENV)/bin/uvicorn

.PHONY: all install dev run stop test test-unit lint clean \
        infra-up infra-down infra-migrate infra-buckets \
        infra-setup-node infra-setup-control infra-verify \
        infra-fc-setup infra-fc-test nomad-start

# ── Environment ───────────────────────────────────────────────────────────────

all: install

install:
	@echo "Setting up Python virtual environment..."
	uv venv $(VENV)
	uv pip install -e ".[dev]"
	@echo "Done. Activate with: source $(VENV)/bin/activate"

# ── Development ───────────────────────────────────────────────────────────────

dev: infra-up
	@echo "Starting all services..."
	$(VENV)/bin/platform-api &  echo $$! > bin/api.pid
	$(VENV)/bin/wasm-agent   &  echo $$! > bin/wasm.pid
	$(VENV)/bin/fc-agent     &  echo $$! > bin/fc.pid
	$(VENV)/bin/gui-agent    &  echo $$! > bin/gui.pid
	@echo "All services running. Press Ctrl+C to stop."
	@trap '$(MAKE) stop; exit 0' INT TERM; wait

run:
	@echo "Starting platform-api..."
	$(UVICORN) api.app:app --host 0.0.0.0 --port 8080 --reload

stop:
	@echo "Stopping services..."
	@-[ -f bin/api.pid  ] && kill $$(cat bin/api.pid)  2>/dev/null; rm -f bin/api.pid
	@-[ -f bin/wasm.pid ] && kill $$(cat bin/wasm.pid) 2>/dev/null; rm -f bin/wasm.pid
	@-[ -f bin/fc.pid   ] && kill $$(cat bin/fc.pid)   2>/dev/null; rm -f bin/fc.pid
	@-[ -f bin/gui.pid  ] && kill $$(cat bin/gui.pid)  2>/dev/null; rm -f bin/gui.pid

# ── Testing ───────────────────────────────────────────────────────────────────

test: test-unit

test-unit:
	$(PYTEST) tests/unit/ -v

test-cov:
	$(PYTEST) tests/unit/ -v --cov=sandbox_platform --cov=platform_cmd --cov-report=term-missing

# ── Infrastructure ────────────────────────────────────────────────────────────

infra-up:
	@echo "Starting PostgreSQL, Redis, MinIO..."
	docker compose up -d
	@sleep 3

infra-down:
	docker compose down

infra-migrate:
	@echo "Running database migrations..."
	psql -h $${NODE1_IP:-localhost} -U platform -d platform \
		-f ../services/data/postgres/migrations/001_init.sql
	@echo "Migrations applied."

infra-buckets:
	@echo "Initializing MinIO buckets..."
	MINIO_ENDPOINT=$${MINIO_ENDPOINT:-http://localhost:9000} \
		../services/data/minio/init-buckets.sh

infra-setup-node:
	sudo ../services/controller/scripts/setup-all-nodes.sh

infra-setup-control:
	sudo ../services/controller/scripts/setup-control-node.sh

infra-verify:
	../services/controller/scripts/verify-day1-2.sh $${NODE1_IP:-localhost}

infra-fc-setup:
	sudo ../services/controller/scripts/setup-firecracker.sh

infra-fc-test:
	sudo ../services/controller/scripts/test-firecracker.sh

nomad-start:
	@chmod +x scripts/start-nomad-cluster.sh
	./scripts/start-nomad-cluster.sh

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean: stop
	@echo "Cleaning up..."
	rm -rf $(VENV) uv.lock sandbox_platform.egg-info
	find . -type d -name __pycache__ -not -path './.git/*' -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
