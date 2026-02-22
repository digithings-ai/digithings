# Digi Ecosystem – common targets (Phase 0+)
# Use: make build, make test, make test-e2e, make up, make down

.PHONY: build up down test test-unit test-e2e package up-heartbeat

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

# Run all tests (unit + e2e if stack is up). From repo root with venv activated.
test:
	pytest -v --tb=short

# Unit only (no stack required).
test-unit:
	pytest -m unit -v --tb=short

# E2E only (requires: docker compose up -d). Skips if stack not up.
test-e2e:
	pytest -v -m e2e --tb=short

# Coverage for Phase 1 code (digigraph + digiquant). Requires: pip install -e "digigraph[dev]" -e "digiquant[dev]"
test-cov:
	pytest -m unit -v --tb=short --cov=digigraph --cov=digiquant --cov-report=term-missing --cov-fail-under=0

# Coverage with HTML report (output in htmlcov/).
test-cov-html:
	pytest -m unit -v --tb=short --cov=digigraph --cov=digiquant --cov-report=html --cov-report=term-missing

# One-click packaging for small firms (Phase 3). Output: digi-bundle-YYYYMMDD.tar.gz
package:
	./scripts/package.sh

# Start stack with heartbeat (health + audit every 30 min).
up-heartbeat:
	docker compose --profile heartbeat up -d
