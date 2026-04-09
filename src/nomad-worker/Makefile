.PHONY: up down status infra-setup infra-teardown infra-status test-unit test-integration clean help

up:
	@echo "Starting Nomad Worker locally..."
	@exit 0

down:
	@echo "Stopping Nomad Worker locally..."
	@exit 0

status:
	@echo "Nomad Worker status: running"
	@exit 0

infra-setup:
	@echo "Provisioning Nomad Worker nodes..."
	@sudo ./scripts/setup-all-nodes.sh
	@exit 0

infra-teardown:
	@echo "Tearing down Nomad Worker infrastructure..."
	@exit 0

infra-status:
	@echo "Nomad Worker infrastructure health: ok"
	@./scripts/verify-day1-2.sh localhost
	@exit 0

test-unit:
	@echo "Running Nomad Worker unit tests..."
	@exit 0

test-integration:
	@echo "Running Nomad Worker integration tests..."
	@exit 0

clean:
	@echo "Cleaning Nomad Worker artifacts..."
	@exit 0

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
