# Digi Ecosystem – common targets (Phase 0+)
# Use: make build, make test, make test-e2e, make up, make down

.PHONY: build up down test test-unit test-e2e doc-check package up-heartbeat up-digichat down-digichat digichat-dev digichat-health stack-local stack-local-stop up-digichat-db down-digichat-db seed-digisearch-local export-edgar-digisearch-dev seed-digisearch-edgar-dev seed-digisearch-edgar-dev-host edgar-digisearch-dev agents-init score score-delta clean-imports find-stale commit pr task new-task status batch-candidates parse-error hooks-install qr-logo up-observability down-observability atlas-validate

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

# Internal markdown links (agent-facing docs). Same check as CI workflow docs.yml.
doc-check:
	python3 scripts/check_doc_links.py

# Regenerate frontend/digithings/assets/qrw.svg from scripts/generate-qr.py.
# Requires: pip install "qrcode==8.0"
qr-logo:
	python3 scripts/generate-qr.py

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

# Stack + DigiChat UI (Next.js on host port DIGICHAT_PUBLISH_PORT, default 3005). Does not include `heartbeat` profile.
# Tip: set DIGICHAT_DEV_AUTH=1 in .env for password login without OIDC; set AUTH_URL to the URL you use in the browser.
up-digichat:
	docker compose --profile digichat up -d --build

down-digichat:
	docker compose --profile digichat down

# DigiChat Next.js dev server (http://127.0.0.1:3000, hot reload). Backend: `make up`, `make stack-local`, or ./scripts/run_local.sh
digichat-dev:
	cd frontend/digichat && npm run dev

# DigiChat GET /api/health (needs dev server + frontend/digichat/.env.local + backends).
digichat-health:
	@curl -sf http://127.0.0.1:3000/api/health | python3 -m json.tool && echo || (echo "DigiChat /api/health failed — run make digichat-dev (see frontend/digichat/.env.local)"; exit 1)

# Python ecosystem on host (DigiKey 8005, LiteLLM 4000, services 8000–8003) — no Docker. Fast iteration with DigiChat: stack-local + digichat-dev (see frontend/digichat/OPERATIONS.md).
stack-local:
	./scripts/run_stack_local.sh

stack-local-stop:
	./scripts/stop_stack_local.sh

# Postgres 16 for DigiChat only (host port 5433). Use with `npm run dev` + DIGICHAT_DATABASE_URL in frontend/digichat/.env.local
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

# ── Agent development kit ──────────────────────────────────────────────────────

# Generate platform adapter files (.github/copilot-instructions.md, .cursor/rules/digithings.mdc) from agents.yml
agents-init:
	python3 scripts/agents_init.py

# Validate Atlas providers and graph compilation before triggering a real run.
# Pings Groq + Gemini (1-token each), checks Supabase baseline row, and runs --dry-run.
# Usage: make atlas-validate              (full check)
#        make atlas-validate SKIP=--skip-llm   (env + DB + dry-run only)
atlas-validate:
	python3 digiquant/scripts/atlas/validate-providers.py $(SKIP)

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
# Optional filters: PHASE="Phase 3 — Domain unification"  AREA=DigiGraph
batch-candidates:
	@bash scripts/batch_candidates.sh $(if $(PHASE),--phase "$(PHASE)",) $(if $(AREA),--area "$(AREA)",)

# Parse a Python traceback and identify the component
# Usage: make parse-error TRACEBACK=file.txt  OR  cat err.log | make parse-error
parse-error:
	@python3 scripts/parse_traceback.py $(if $(TRACEBACK),--input $(TRACEBACK),)

# Install git hooks (currently: pre-push guard against non-origin remotes + main pushes + unreviewed live-trading touches)
hooks-install:
	@install -m 755 scripts/hooks/pre-push.sh .git/hooks/pre-push
	@echo "installed: .git/hooks/pre-push"

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
