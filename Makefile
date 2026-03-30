# Digi Ecosystem – common targets (Phase 0+)
# Use: make build, make test, make test-e2e, make up, make down

.PHONY: build up down test test-unit test-e2e package up-heartbeat up-digichat down-digichat digichat-dev digichat-health stack-local stack-local-stop up-digichat-db down-digichat-db seed-digisearch-local export-edgar-digisearch-dev seed-digisearch-edgar-dev seed-digisearch-edgar-dev-host edgar-digisearch-dev

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

# Coverage for Phase 1 code (digigraph + digiquant + digismith). Requires: pip install -e "digigraph[dev]" -e "digiquant[dev]" -e "digismith"
test-cov:
	pytest -m unit -v --tb=short --cov=digigraph --cov=digiquant --cov=digismith --cov-report=term-missing --cov-fail-under=0

# Coverage with HTML report (output in htmlcov/).
test-cov-html:
	pytest -m unit -v --tb=short --cov=digigraph --cov=digiquant --cov-report=html --cov-report=term-missing

# One-click packaging for small firms (Phase 3). Output: digi-bundle-YYYYMMDD.tar.gz
package:
	./scripts/package.sh

# Start stack with heartbeat (health + audit every 30 min).
up-heartbeat:
	docker compose --profile heartbeat up -d

# Stack + DigiChat UI (Next.js on host port DIGICHAT_PUBLISH_PORT, default 3005). Does not include `heartbeat` profile.
# Tip: set DIGICHAT_DEV_AUTH=1 in .env for password login without OIDC; set AUTH_URL to the URL you use in the browser.
up-digichat:
	docker compose --profile digichat up -d --build

down-digichat:
	docker compose --profile digichat down

# DigiChat Next.js dev server (http://127.0.0.1:3000, hot reload). Backend: `make up`, `make stack-local`, or ./scripts/run_local.sh
digichat-dev:
	cd digichat && npm run dev

# DigiChat GET /api/health (needs dev server + digichat/.env.local + backends).
digichat-health:
	@curl -sf http://127.0.0.1:3000/api/health | python3 -m json.tool && echo || (echo "DigiChat /api/health failed — run make digichat-dev (see digichat/.env.local)"; exit 1)

# Python ecosystem on host (DigiKey 8005, LiteLLM 4000, services 8000–8003) — no Docker. Fast iteration with DigiChat: stack-local + digichat-dev (see DIGICHAT.md).
stack-local:
	./scripts/run_stack_local.sh

stack-local-stop:
	./scripts/stop_stack_local.sh

# Postgres 16 for DigiChat only (host port 5433). Use with `npm run dev` + DIGICHAT_DATABASE_URL in digichat/.env.local
up-digichat-db:
	docker compose --profile digichat up -d digichat-db

down-digichat-db:
	docker compose --profile digichat stop digichat-db

# Ingest digisearch/seeds/* via POST /ingest (needs DIGISEARCH_SEED_API_KEY=dgk_live_... with digisearch:ingest). See docs/LOCAL_STACK.md.
seed-digisearch-local:
	@python3 scripts/seed_digisearch_local.py

# EDGAR-CORPUS dev slice → digisearch/devdata/edgar_sample (needs: pip install -e "./digisearch[edgar-corpus]").
export-edgar-digisearch-dev:
	@python3 scripts/export_edgar_corpus_dev.py --year 2020 --max-documents 25 --clean

# Ingest EDGAR exports into index edgar_dev (DigiSearch in Docker: paths use /data/edgar_dev_corpus mount).
seed-digisearch-edgar-dev:
	@DIGISEARCH_SEED_REMOTE_PREFIX=/data/edgar_dev_corpus python3 scripts/seed_digisearch_local.py --index edgar_dev --seeds-dir $(CURDIR)/digisearch/devdata/edgar_sample

# Same index; host-run DigiSearch (stack-local) sees repo paths — no remote prefix.
seed-digisearch-edgar-dev-host:
	@python3 scripts/seed_digisearch_local.py --index edgar_dev --seeds-dir $(CURDIR)/digisearch/devdata/edgar_sample

# Export then seed (requires stack up + DIGISEARCH_SEED_API_KEY; uses Docker ingest paths).
edgar-digisearch-dev: export-edgar-digisearch-dev seed-digisearch-edgar-dev

# Regenerate OpenAPI JSON for DigiGraph (requires editable digigraph + digibase).
.PHONY: openapi-digigraph
openapi-digigraph:
	@mkdir -p docs/openapi
	@python -c 'import json; from digigraph.server import app; open("docs/openapi/digigraph.json","w").write(json.dumps(app.openapi(), indent=2))'
