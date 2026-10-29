# client-<slug> targets. Every target is safe to run locally; deploy targets refuse
# in the template (see deploy/README.md).
SHELL := /bin/bash
DIGITHINGS_DIR ?= ../digithings
COMPOSE := docker compose -f compose/docker-compose.yml

.PHONY: help up dev down link unlink test qa release deploy-staging deploy-prod

help:
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

up: ## run the pinned R0 images with tenant/, tools/, corpus/ mounted
	$(COMPOSE) up -d

dev: ## same, but build the images from $(DIGITHINGS_DIR)
	DIGITHINGS_DIR=$(abspath $(DIGITHINGS_DIR)) $(COMPOSE) -f compose/docker-compose.dev.yml up -d --build

down: ## stop the local stack
	$(COMPOSE) down

link: ## work against a local R0 checkout (writes the gitignored .link file)
	@test -d "$(DIGITHINGS_DIR)/.git" || { echo "no R0 checkout at $(DIGITHINGS_DIR)"; exit 1; }
	@echo "$(abspath $(DIGITHINGS_DIR))" > .link && echo "linked to $$(cat .link)"

unlink: ## restore the pins from digithings.lock
	@rm -f .link && echo "unlinked; using digithings.lock"

test: ## offline checks: lock, tenant schema, corpus, tools (no model calls)
	scripts/check_lock.sh
	source scripts/env.sh && cd "$$DIGITHINGS_DIR" && uv run pytest -q "$$CLIENT_DIR/tests" -p no:cacheprovider

qa: ## golden questions on FREE models only; QID=Q1 for one; stops on the first 429 round
	tests/run_qa.sh $(or $(QID),all)

release: ## bump VERSION + CHANGELOG and print the tag command (the owner cuts and signs the tag)
	@test -n "$(V)" || { echo "usage: make release V=X.Y.Z"; exit 1; }
	@echo "$(V)" > VERSION
	@sed -i.bak "s/^## Unreleased/## Unreleased\n\n## $(V) - $$(date +%F)/" CHANGELOG.md && rm -f CHANGELOG.md.bak
	@echo "Next (owner only): git tag -s client-<slug>-v$(V) -m 'client-<slug> v$(V)' && git push origin main --tags && git push github main --tags"

deploy-staging: ## stub: refuses until deploy/deploy.sh is wired with a scoped token
	deploy/deploy.sh staging

deploy-prod: ## stub: refuses; prod needs a release tag signed by the owner
	deploy/deploy.sh prod
