# Sitaas – rebuild and run with latest digigraph/digisearch code
# Run from projects/sitaas: make build, make up, make update

.PHONY: build up down update probe

# Build images (use after pulling or editing digigraph/digisearch).
build:
	docker compose build

# Build without cache to force fresh layers (use when code changes aren't picked up).
build-no-cache:
	docker compose build --no-cache digigraph digisearch

# Start stack in background.
up:
	docker compose up -d

# Rebuild and start (picks up latest code; recreates only changed services).
update:
	docker compose up -d --build

# Stop and remove containers.
down:
	docker compose down

# Probe Azure index: sample docs, distinct filter values, and filter syntax test.
# Requires .env with AZURE_SEARCH_* and DIGISEARCH_INDEX_CONFIG. Run from repo root: make -C projects/sitaas probe
probe:
	cd ../.. && set -a && [ -f projects/sitaas/.env ] && . projects/sitaas/.env; set +a && \
		DIGISEARCH_INDEX_CONFIG=$$(cd ../.. && pwd)/projects/sitaas/indexes/unified-content-index.yaml \
		python projects/sitaas/scripts/probe_index.py
