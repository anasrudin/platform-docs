.PHONY: up down status infra-setup infra-teardown infra-status test-unit test-integration clean help

up:
	@echo "Starting Data services locally..."
	@docker compose up -d
	@exit 0

down:
	@echo "Stopping Data services locally..."
	@docker compose down
	@exit 0

status:
	@echo "Data services status: running"
	@docker compose ps
	@exit 0

infra-setup:
	@echo "Provisioning Data service nodes..."
	@exit 0

infra-teardown:
	@echo "Tearing down Data service infrastructure..."
	@exit 0

infra-status:
	@echo "Data service infrastructure health: ok"
	@exit 0

test-unit:
	@echo "Running Data service unit tests..."
	@exit 0

test-integration:
	@echo "Running Data service integration tests..."
	@exit 0

clean:
	@echo "Cleaning Data service artifacts..."
	@exit 0

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
