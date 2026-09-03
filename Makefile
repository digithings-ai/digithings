# Digi Ecosystem – common targets (Phase 0+)
# Use: make build, make test, make test-e2e, make up, make down

.PHONY: build up down test test-unit test-e2e test-baseline doc-check vault-check package up-heartbeat up-digichat down-digichat digichat-release-up digichat-release-down digichat-profile-a-up digichat-profile-a-down digichat-profile-a-bundle-up digichat-profile-a-bundle-down digichat-dev digichat-health stack-local stack-local-stop up-digichat-db down-digichat-db seed-digisearch-local export-edgar-digisearch-dev seed-digisearch-edgar-dev seed-digisearch-edgar-dev-host edgar-digisearch-dev agents-init score score-delta clean-imports find-stale commit pr task new-task status batch-candidates parse-error hooks-install up-observability down-observability research-validate supabase-migrations-check

build:
	docker compose build

up:
	docker compose up -d

# Pull prebuilt GHCR images (no local Dockerfile build). See infra/self-host/ and docs/DEPLOYMENT.md.
.PHONY: up-ghcr up-ghcr-digichat pull-ghcr
GHCR_COMPOSE := -f docker-compose.yml -f infra/self-host/compose.ghcr.yml
pull-ghcr:
	docker compose $(GHCR_COMPOSE) pull
up-ghcr:
	docker compose $(GHCR_COMPOSE) up -d
up-ghcr-digichat:
	docker compose $(GHCR_COMPOSE) --profile digichat up -d

down:
	docker compose down

# Run all tests (unit + e2e if stack is up). From repo root with venv activated.
test:
	pytest -v --tb=short

# Unit only (no stack required). digichat Vitest included; dashboard is npm-only (REM-130).
test-unit:
	pytest -m unit -v --tb=short
	cd frontend/digichat && npm run test --if-present

# Dashboard frontend (not part of test-unit — use CI test-dashboard.yml or run locally):
#   cd frontend/dashboard && npm run lint && npm run test && npm run build

# Baseline gate — always-green imports + schemas + CLI help (no Docker, no network).
test-baseline:
	pytest -m baseline --tb=short -q

# E2E only (requires: docker compose up -d). Skips if stack not up.
test-e2e:
	pytest -v -m e2e --tb=short

# Internal markdown links (agent-facing docs). Same check as CI workflow docs.yml.
doc-check:
	python3 scripts/check_doc_links.py

# Lint the digivault-managed docs/vision vault (wikilinks, frontmatter, taxonomy,
# orphans) against docs/vision/.digivault.yml. Uses the digivault core (pydantic +
# pyyaml only); -P keeps cwd off sys.path so the real package under digivault/src
# loads, not the repo-root namespace dir.
vault-check:
	PYTHONPATH=digivault/src python3 -P scripts/check_vault.py

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

# Start core stack + Prometheus (127.0.0.1:9090) and Grafana (127.0.0.1:3001). See ADR-0003.
up-observability:
	docker compose --profile observability up -d

down-observability:
	docker compose --profile observability down

# ---------------------------------------------------------------------------
# digichat targets
#   make up-digichat / down-digichat          — local build from monorepo (dev/ops)
#   make digichat-release-up VERSION=…       — pull pinned digichat GHCR (full stack overlay)
#   make digichat-release-down VERSION=…
#   make digichat-profile-a-up / down        — Profile A pull (digichat + digikey + digigraph + digivault)
#   make digichat-profile-a-bundle-up / down — Profile A one stack image (CF parity) + digichat
#   make digichat-dev / digichat-health       — host Next.js + /api/health smoke
#   make up-digichat-db / down-digichat-db
# Client install: docs/digichat/INSTALL.md | overlays: infra/digichat-release/
# ---------------------------------------------------------------------------

# Stack + digichat UI (Next.js on host port DIGICHAT_PUBLISH_PORT, default 3005). Does not include `heartbeat` profile.
# Tip: set DIGICHAT_DEV_AUTH=1 in .env for password login without OIDC; set AUTH_URL to the URL you use in the browser.
up-digichat:
	docker compose --profile digichat up -d --build

down-digichat:
	docker compose --profile digichat down

# Pull published digichat from GHCR (requires VERSION=0.9.3). Does not build from the monorepo.
# Example: make digichat-release-up VERSION=0.9.3
digichat-release-up:
	@test -n "$(VERSION)" || (echo "Usage: make digichat-release-up VERSION=0.9.3"; exit 1)
	DIGICHAT_VERSION=$(VERSION) docker compose \
	  -f docker-compose.yml \
	  -f infra/digichat-release/compose.digichat-release.yml \
	  --profile digichat up -d

digichat-release-down:
	@test -n "$(VERSION)" || (echo "Usage: make digichat-release-down VERSION=0.9.3"; exit 1)
	DIGICHAT_VERSION=$(VERSION) docker compose \
	  -f docker-compose.yml \
	  -f infra/digichat-release/compose.digichat-release.yml \
	  --profile digichat down

# Profile A — digichat + digikey + digigraph + LiteLLM + digivault (all digithings images from GHCR).
# Requires infra/digichat-release/.env.profile-a (copy from .env.profile-a.example). No --build.
PROFILE_A_COMPOSE := -f infra/digichat-release/compose.profile-a.yml --env-file infra/digichat-release/.env.profile-a
digichat-profile-a-up:
	@test -f infra/digichat-release/.env.profile-a || (echo "Copy infra/digichat-release/.env.profile-a.example → .env.profile-a and fill secrets"; exit 1)
	docker compose $(PROFILE_A_COMPOSE) up -d
digichat-profile-a-down:
	@test -f infra/digichat-release/.env.profile-a || (echo "Copy infra/digichat-release/.env.profile-a.example → .env.profile-a first"; exit 1)
	docker compose $(PROFILE_A_COMPOSE) down

# Profile A bundle — one supervisord image (same as CF Containers) + digichat + Postgres.
# Prefer for website digichat local work; stop monorepo `make up` containers first (port clash).
PROFILE_A_BUNDLE_COMPOSE := -f infra/digichat-release/compose.profile-a-bundle.yml \
	$(if $(wildcard infra/digichat-release/compose.profile-a-bundle.override.yml),-f infra/digichat-release/compose.profile-a-bundle.override.yml,) \
	--env-file infra/digichat-release/.env.profile-a-bundle
digichat-profile-a-bundle-up:
	@test -f infra/digichat-release/.env.profile-a-bundle || (echo "Copy infra/digichat-release/.env.profile-a-bundle.example → .env.profile-a-bundle and fill secrets"; exit 1)
	docker compose $(PROFILE_A_BUNDLE_COMPOSE) up -d --build
digichat-profile-a-bundle-down:
	@test -f infra/digichat-release/.env.profile-a-bundle || (echo "Copy infra/digichat-release/.env.profile-a-bundle.example → .env.profile-a-bundle first"; exit 1)
	docker compose $(PROFILE_A_BUNDLE_COMPOSE) down

# digichat Next.js dev server (http://127.0.0.1:3000, hot reload). Backend: `make up`, `make stack-local`, or ./scripts/run_local.sh
digichat-dev:
	cd frontend/digichat && npm run dev

# digichat GET /api/health (needs dev server + frontend/digichat/.env.local + backends).
digichat-health:
	@curl -sf http://127.0.0.1:3000/api/health | python3 -m json.tool && echo || (echo "digichat /api/health failed — run make digichat-dev (see frontend/digichat/.env.local)"; exit 1)

# Python ecosystem on host (digikey 8005, LiteLLM 4000, services 8000–8003) — no Docker. Fast iteration with digichat: stack-local + digichat-dev (see frontend/digichat/OPERATIONS.md).
stack-local:
	./scripts/run_stack_local.sh

stack-local-stop:
	./scripts/stop_stack_local.sh

# Postgres 16 for digichat only (host port 5433). Use with `npm run dev` + DIGICHAT_DATABASE_URL in frontend/digichat/.env.local
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

# Ingest EDGAR exports into index edgar_dev (digisearch in Docker: paths use /data/edgar_dev_corpus mount).
seed-digisearch-edgar-dev:
	@DIGISEARCH_SEED_REMOTE_PREFIX=/data/edgar_dev_corpus python3 scripts/seed_digisearch_local.py --index edgar_dev --seeds-dir $(CURDIR)/digisearch/devdata/edgar_sample

# Same index; host-run digisearch (stack-local) sees repo paths — no remote prefix.
seed-digisearch-edgar-dev-host:
	@python3 scripts/seed_digisearch_local.py --index edgar_dev --seeds-dir $(CURDIR)/digisearch/devdata/edgar_sample

# Export then seed (requires stack up + DIGISEARCH_SEED_API_KEY; uses Docker ingest paths).
edgar-digisearch-dev: export-edgar-digisearch-dev seed-digisearch-edgar-dev

# Export OpenAPI JSON for all FastAPI services → docs/openapi/<svc>.json
# --check: fail if committed specs drift from app.openapi()
.PHONY: openapi-export openapi-check openapi-digigraph
openapi-export:
	@mkdir -p docs/openapi
	@python scripts/export_openapi.py

openapi-check:
	@python scripts/export_openapi.py --check

# Back-compat alias
openapi-digigraph: openapi-export

# Regenerate the digivault API-reference notes (docs/vision/api/) from the authored
# /docs content (frontend/digithings-web/lib/apiDocs.ts + sharedDocs.ts). Commit the
# output; the architecture-vault sync upserts it to Supabase on push to main.
.PHONY: gen-api-vault
gen-api-vault:
	node_modules/.bin/tsx scripts/gen-api-vault.ts

# ── Agent development kit ──────────────────────────────────────────────────────

# Generate platform adapter files (.github/copilot-instructions.md, .cursor/rules/digithings.mdc) from agents.yml
agents-init:
	python3 scripts/agents_init.py

# Validate research providers and graph compilation before triggering a real run.
# Pings OpenRouter (connectivity, structured output, function tools, web search),
# checks Supabase baseline row, and runs --dry-run.
# Usage: make research-validate              (full check)
#        make research-validate SKIP=--skip-llm   (env + DB + dry-run only)
research-validate:
	python3 digiquant/scripts/research/validate-providers.py $(SKIP)

# Guard the `core` Supabase migration chain: config.toml present, every file named
# NNN_name.sql, no duplicate numeric prefix. Pure bash, no deps — the same check
# test-digiquant.yml runs as its first step. Run before adding a migration.
supabase-migrations-check:
	bash digiquant/scripts/research/verify-supabase-migrations.sh

# Self-score staged changes against 4-dimension rubrics (Security ≥8, Quality ≥8, Optimization ≥7, Accuracy ≥9)
score:
	python3 scripts/score.py --staged

# Compare staged score vs origin/develop baseline per dimension; exits 1 if any dimension regressed.
# Run this before `make score` to catch incremental quality slippage early.
score-delta:
	python3 scripts/score_delta.py

# Detect unused Python imports with ruff (dry-run by default; set APPLY=1 to fix in-place)
clean-imports:
	python3 scripts/clean_imports.py $(if $(APPLY),--fix,)

# Detect unused functions, classes, and variables across Python source dirs
find-stale:
	python3 scripts/find_stale.py

# Conventional commit helper — validates type(component): description format
# Usage: make commit MSG="feat(digigraph): add new workflow step"
commit:
	@scripts/commit_helper.sh $(MSG)

# Create a PR using the project template (requires gh CLI + gh auth login)
pr:
	@scripts/create_pr.sh

# ── Orchestration ──────────────────────────────────────────────────────────────

# Show status of all module integration branches vs develop
module-status:
	@scripts/module_branches.sh status

# Sync all module branches forward from develop (fast-forward only)
module-sync:
	@scripts/module_branches.sh sync

# Switch to a module branch — use before starting a focused session
# Usage: make module-switch MODULE=digiquant
module-switch:
	@[ -n "$(MODULE)" ] || (echo "Usage: make module-switch MODULE=<component>"; exit 1)
	@scripts/module_branches.sh switch $(MODULE)

# Open a PR merging a module branch into develop
# Usage: make module-pr MODULE=digiquant
module-pr:
	@[ -n "$(MODULE)" ] || (echo "Usage: make module-pr MODULE=<component>"; exit 1)
	@scripts/module_branches.sh pr $(MODULE)

# Execute a backlog task end-to-end in an isolated worktree (ISSUE=N required)
# Usage: make task ISSUE=42
task:
	@[ -n "$(ISSUE)" ] || (echo "Usage: make task ISSUE=<number>"; exit 1)
	@scripts/check-worktree-conflicts.sh $(ISSUE)
	@scripts/run_task.sh $(ISSUE)

# Create a new GitHub Issue for the agent backlog (interactive)
new-task:
	@scripts/create_issue.sh

# List open agent-task issues (optional: COMPONENT=digisearch)
status:
	@scripts/list_tasks.sh $(if $(COMPONENT),--component $(COMPONENT),)

# Group open agent-task issues by phase/area for parallel execution
# Optional filters: PHASE="Phase 3 — Domain unification"  AREA=digigraph
batch-candidates:
	@bash scripts/batch_candidates.sh $(if $(PHASE),--phase "$(PHASE)",) $(if $(AREA),--area "$(AREA)",)

# Parse a Python traceback and identify the component
# Usage: make parse-error TRACEBACK=file.txt  OR  cat err.log | make parse-error
parse-error:
	@python3 scripts/parse_traceback.py $(if $(TRACEBACK),--input $(TRACEBACK),)

# Install git hooks (currently: pre-push guard against non-origin remotes + main pushes + unreviewed live-trading touches)
hooks-install:
	@scripts/install-hooks.sh

.PHONY: digiquant-cron-check
digiquant-cron-check:
	python scripts/digiquant_cron_check.py

# Run gitleaks locally against the working tree. Mirrors the CI scan so
# developers can reproduce findings before pushing.
#   Install:  brew install gitleaks   OR   go install github.com/gitleaks/gitleaks/v8@latest
# The CI job uses the same .gitleaks.toml config at repo root.
secrets-scan:
	@command -v gitleaks >/dev/null 2>&1 || { \
	  echo "gitleaks not installed. Install with:  brew install gitleaks  (or: go install github.com/gitleaks/gitleaks/v8@latest)"; \
	  exit 127; \
	}
	@gitleaks detect --source . --config .gitleaks.toml --redact --verbose --no-banner
