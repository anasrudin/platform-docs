# sandbox-platform — root Makefile
# Jalankan semua perintah dari repo root: platform-docs/
# ─────────────────────────────────────────────────────────────────────────────

REGISTRY        ?= localhost:5000
VERSION         ?= latest
SNAPSHOT_NAME   ?= python-v1
SNAPSHOT_DIR    ?= /tmp/snapshots/$(SNAPSHOT_NAME)
MINIO_ENDPOINT  ?= http://localhost:9000
NODE1_IP        ?= localhost

.PHONY: help \
        services-up services-down services-status \
        services-data services-controller services-monitoring \
        setup \
        cluster-setup cluster-start cluster-status \
        snapshot-rootfs snapshot-create snapshot-upload snapshot-build \
        image-build image-push image-load \
        deploy deploy-status deploy-logs \
        run-python health \
        worker-install worker-test worker-lint \
        clean

# ── Help ──────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "sandbox-platform — available targets"
	@echo "─────────────────────────────────────────────────────"
	@echo ""
	@echo "  Services (entity data + controller):"
	@echo "    services-up          Start consul, minio, postgres via docker compose"
	@echo "    services-down        Stop all services"
	@echo "    services-status      Cek status semua services"
	@echo ""
	@echo "  Cluster:"
	@echo "    cluster-setup        Setup semua node (Nomad + Consul + Firecracker)"
	@echo "    cluster-start        Start Nomad cluster"
	@echo "    cluster-status       Lihat status node Nomad"
	@echo ""
	@echo "  Snapshot (Firecracker VM):"
	@echo "    snapshot-rootfs      Build rootfs ext4 dengan Python 3.11"
	@echo "    snapshot-create      Boot VM dan ambil snapshot"
	@echo "    snapshot-upload      Upload snapshot ke MinIO"
	@echo "    snapshot-build       Jalankan semua: rootfs + create + upload"
	@echo ""
	@echo "  Docker images:"
	@echo "    image-build          Build sandbox-base + sandbox-fc-agent + sandbox-gui-agent"
	@echo "    image-push           Push semua image ke registry (REGISTRY=$(REGISTRY))"
	@echo "    image-load           Load image ke semua Nomad node (tanpa registry)"
	@echo ""
	@echo "  Deploy:"
	@echo "    deploy               Deploy Nomad job sandbox-worker"
	@echo "    deploy-status        Status Nomad job"
	@echo "    deploy-logs          Lihat logs worker terbaru"
	@echo ""
	@echo "  Test:"
	@echo "    run-python           Kirim POST /execute dengan python_run"
	@echo "    health               Cek health semua worker"
	@echo ""
	@echo "  Worker (sandbox-worker/):"
	@echo "    worker-install       Install Python deps"
	@echo "    worker-test          Jalankan pytest"
	@echo "    worker-lint          Jalankan ruff/mypy"
	@echo ""
	@echo "  Misc:"
	@echo "    clean                Hapus build artifacts"
	@echo ""
	@echo "  Variables (override via env):"
	@echo "    REGISTRY=$(REGISTRY)"
	@echo "    VERSION=$(VERSION)"
	@echo "    SNAPSHOT_NAME=$(SNAPSHOT_NAME)"
	@echo "    MINIO_ENDPOINT=$(MINIO_ENDPOINT)"
	@echo "    NODE1_IP=$(NODE1_IP)"
	@echo ""

# ── Services ──────────────────────────────────────────────────────────────────

services-data:
	@echo ">>> Starting data services (postgres, redis, minio)..."
	docker network create platform-net 2>/dev/null || true
	cd services && docker compose -f data/docker-compose.yml up -d

services-controller:
	@echo ">>> Starting controller services (consul)..."
	docker network create platform-net 2>/dev/null || true
	cd services && docker compose -f controller/docker-compose.yml up -d

services-monitoring:
	@echo ">>> Starting monitoring services (jaeger)..."
	docker network create platform-net 2>/dev/null || true
	cd services && docker compose -f monitoring/docker-compose.yml up -d

services-up:
	@echo ">>> Starting all services..."
	docker network create platform-net 2>/dev/null || true
	cd services && docker compose up -d
	@sleep 5
	@$(MAKE) services-status

services-down:
	cd services && docker compose down

services-status:
	@echo "--- Consul:"
	@curl -sf http://$(NODE1_IP):8500/v1/status/leader 2>/dev/null \
		&& echo "  consul: OK" || echo "  consul: DOWN"
	@echo "--- MinIO:"
	@curl -sf http://$(NODE1_IP):9000/minio/health/live 2>/dev/null \
		&& echo "  minio: OK" || echo "  minio: DOWN"
	@echo "--- Postgres:"
	@docker exec $$(docker ps -qf name=postgres) \
		pg_isready -U postgres 2>/dev/null \
		&& echo "  postgres: OK" || echo "  postgres: DOWN"

setup:
	@echo ">>> [1/4] Copying .env.example → sandbox-worker/.env (jika belum ada)..."
	@[ -f sandbox-worker/.env ] || cp sandbox-worker/.env.example sandbox-worker/.env
	@echo ">>> [2/4] Installing worker deps..."
	cd sandbox-worker && uv venv .venv && uv pip install -e ".[dev]"
	@echo ">>> [3/4] Starting data + monitoring services..."
	$(MAKE) services-data services-monitoring
	@echo ">>> [4/4] Checking service health..."
	@sleep 5
	@$(MAKE) services-status
	@echo ""
	@echo "Setup selesai. Langkah berikutnya:"
	@echo "  make worker-run   — start platform API"
	@echo "  open http://localhost:16686  — Jaeger UI"

# ── Cluster ───────────────────────────────────────────────────────────────────

cluster-setup:
	@echo ">>> Setting up nodes..."
	sudo bash services/scripts/setup-control-node.sh
	sudo bash services/scripts/setup-firecracker.sh

cluster-start:
	@echo ">>> Starting Nomad cluster..."
	bash services/scripts/start-nomad-cluster.sh

cluster-status:
	nomad node status
	@echo ""
	consul members

# ── Snapshot ──────────────────────────────────────────────────────────────────

snapshot-rootfs:
	@echo ">>> Building Python rootfs..."
	@mkdir -p $(SNAPSHOT_DIR)
	sudo bash tools/snapshot-builder/build-rootfs.sh \
		--name $(SNAPSHOT_NAME) \
		--python 3.11 \
		--size 1024 \
		--out $(SNAPSHOT_DIR)/rootfs.ext4
	@echo ">>> Rootfs built: $(SNAPSHOT_DIR)/rootfs.ext4"

snapshot-create:
	@echo ">>> Creating Firecracker snapshot..."
	@[ -f $(SNAPSHOT_DIR)/rootfs.ext4 ] || \
		{ echo "ERROR: rootfs not found — run 'make snapshot-rootfs' first"; exit 1; }
	@[ -f /tmp/snapshots/vmlinux.bin ] || { \
		echo ">>> Downloading kernel..."; \
		curl -fsSL \
			https://s3.amazonaws.com/spec.ccfc.min/img/quickstart_guide/x86_64/kernels/vmlinux.bin \
			-o /tmp/snapshots/vmlinux.bin; \
	}
	@bash tools/snapshot-builder/snapshot-builder.sh \
		--name $(SNAPSHOT_NAME) \
		--rootfs $(SNAPSHOT_DIR)/rootfs.ext4 \
		--kernel /tmp/snapshots/vmlinux.bin \
		--out-dir $(SNAPSHOT_DIR)
	@echo ">>> Snapshot: $(SNAPSHOT_DIR)/"

snapshot-upload:
	@echo ">>> Uploading snapshot to MinIO..."
	@[ -f $(SNAPSHOT_DIR)/vmstate.bin ] || \
		{ echo "ERROR: snapshot not found — run 'make snapshot-create' first"; exit 1; }
	bash tools/snapshot-builder/upload-minio.sh \
		--snapshot-dir $(SNAPSHOT_DIR) \
		--name $(SNAPSHOT_NAME) \
		--kernel /tmp/snapshots/vmlinux.bin \
		--rootfs $(SNAPSHOT_DIR)/rootfs.ext4 \
		--endpoint $(MINIO_ENDPOINT)
	@echo ">>> Upload done."
	@mc alias set local $(MINIO_ENDPOINT) minioadmin minioadmin --quiet
	@mc ls local/platform-snapshots/$(SNAPSHOT_NAME)/

snapshot-build: snapshot-rootfs snapshot-create snapshot-upload
	@echo ">>> Snapshot pipeline selesai: $(SNAPSHOT_NAME)"

# ── Docker images ─────────────────────────────────────────────────────────────

image-build:
	@echo ">>> Building sandbox-base..."
	docker build \
		-f docker/base/Dockerfile \
		-t sandbox-base:$(VERSION) \
		-t sandbox-base:latest \
		.
	@echo ">>> Building sandbox-fc-agent..."
	docker build \
		-f docker/fc-agent/Dockerfile \
		-t $(REGISTRY)/sandbox-fc-agent:$(VERSION) \
		-t $(REGISTRY)/sandbox-fc-agent:latest \
		.
	@echo ">>> Building sandbox-gui-agent..."
	docker build \
		-f docker/gui-agent/Dockerfile \
		-t $(REGISTRY)/sandbox-gui-agent:$(VERSION) \
		-t $(REGISTRY)/sandbox-gui-agent:latest \
		.
	@echo ">>> Images built:"
	@docker images | grep sandbox

image-push:
	@echo ">>> Pushing images to $(REGISTRY)..."
	docker push $(REGISTRY)/sandbox-fc-agent:$(VERSION)
	docker push $(REGISTRY)/sandbox-fc-agent:latest
	docker push $(REGISTRY)/sandbox-gui-agent:$(VERSION)
	docker push $(REGISTRY)/sandbox-gui-agent:latest
	@echo ">>> Push selesai."

image-load:
	@echo ">>> Saving images to tar..."
	@mkdir -p /tmp/sandbox-images
	docker save $(REGISTRY)/sandbox-fc-agent:latest \
		| gzip > /tmp/sandbox-images/fc-agent.tar.gz
	docker save $(REGISTRY)/sandbox-gui-agent:latest \
		| gzip > /tmp/sandbox-images/gui-agent.tar.gz
	@echo ">>> Load ke Nomad node dengan:"
	@echo "    scp /tmp/sandbox-images/*.tar.gz <node>:/tmp/"
	@echo "    ssh <node> 'docker load < /tmp/sandbox-images/fc-agent.tar.gz'"

# ── Deploy ────────────────────────────────────────────────────────────────────

deploy:
	@echo ">>> Deploying sandbox-worker to Nomad..."
	nomad job run services/nomad/jobs/sandbox-worker.nomad
	@echo ">>> Menunggu job running..."
	@sleep 5
	@$(MAKE) deploy-status

deploy-status:
	nomad job status sandbox-worker

deploy-logs:
	@ALLOC=$$(nomad job status sandbox-worker \
		| grep -E 'running|pending' | head -1 | awk '{print $$1}'); \
	[ -n "$$ALLOC" ] && nomad alloc logs $$ALLOC || echo "Tidak ada alloc running"

# ── Test ─────────────────────────────────────────────────────────────────────

health:
	@echo "--- fc-agent health:"
	@curl -sf http://$(NODE1_IP):8081/health | python3 -m json.tool \
		|| echo "  fc-agent: DOWN"
	@echo "--- wasm-agent health:"
	@curl -sf http://$(NODE1_IP):8082/health | python3 -m json.tool \
		|| echo "  wasm-agent: DOWN"
	@echo "--- gui-agent health:"
	@curl -sf http://$(NODE1_IP):8083/health | python3 -m json.tool \
		|| echo "  gui-agent: DOWN"

run-python:
	@echo ">>> POST /execute — python_run: print(1+1)"
	@curl -sf -X POST http://$(NODE1_IP):8081/execute \
		-H "Content-Type: application/json" \
		-d '{"tool":"python_run","input":{"code":"print(1+1)"}}' \
		| python3 -m json.tool

# ── Worker (sandbox-worker/) ──────────────────────────────────────────────────

worker-install:
	cd sandbox-worker && uv venv .venv && uv pip install -e ".[dev]"

worker-test:
	cd sandbox-worker && .venv/bin/pytest tests/unit/ -v

worker-lint:
	cd sandbox-worker && .venv/bin/ruff check src/ && \
		.venv/bin/mypy src/ --ignore-missing-imports

# ── Clean ─────────────────────────────────────────────────────────────────────

clean:
	@echo ">>> Cleaning build artifacts..."
	find . -type d -name __pycache__ -not -path './.git/*' \
		-exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '*.egg-info' -not -path './.git/*' \
		-exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache \
		-exec rm -rf {} + 2>/dev/null || true
	rm -rf /tmp/sandbox-images
	@echo ">>> Done."
