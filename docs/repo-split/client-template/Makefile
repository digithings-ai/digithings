# <client-slug> targets (Forgejo repo digithings-ai/<client-slug>). Every target is safe to run
# locally; deploy targets refuse in the template (see deploy/README.md). deploy-* and release
# first check that the Forgejo repo is private (scripts/check_forgejo_private.sh, fails closed).
SHELL := /bin/bash
DIGITHINGS_DIR ?= ../digithings
REPO ?= $(notdir $(CURDIR))
# What `make bump` runs after re-pinning; CI tests override it with an offline check.
BUMP_TEST ?= $(MAKE) test
COMPOSE := docker compose -f compose/docker-compose.yml

.PHONY: help up dev down link unlink bump test qa check-private release deploy-staging deploy-prod

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

bump: ## pin digithings.lock to SHA=<40-char sha on R0 develop>, then run make test
	@[[ "$(SHA)" =~ ^[0-9a-f]{40}$$ ]] || { echo "usage: make bump SHA=<40-char sha on R0 develop>"; exit 1; }
	@if git -C "$(DIGITHINGS_DIR)" rev-parse --git-dir >/dev/null 2>&1; then \
	  git -C "$(DIGITHINGS_DIR)" merge-base --is-ancestor "$(SHA)" origin/develop \
	    || { echo "bump: $(SHA) is not on origin/develop in $(DIGITHINGS_DIR) (git fetch first?)"; exit 1; }; \
	fi
	@sed -i.bak -e 's/^kind=.*/kind=git-sha/' -e 's/^ref=.*/ref=develop/' -e 's/^sha=.*/sha=$(SHA)/' digithings.lock && rm -f digithings.lock.bak
	@echo "digithings.lock -> $(SHA)"
	$(BUMP_TEST)

test: ## offline checks: lock, tenant schema, corpus, tools (no model calls)
	scripts/check_lock.sh
	source scripts/env.sh && cd "$$DIGITHINGS_DIR" && uv run pytest -q "$$CLIENT_DIR/tests" -p no:cacheprovider

qa: ## golden questions on FREE models only; QID=Q1 for one; stops on the first 429 round
	tests/run_qa.sh $(or $(QID),all)

check-private: ## refuse unless the Forgejo origin repo reads as private (API + keychain token; fails closed)
	scripts/check_forgejo_private.sh

release: check-private ## bump VERSION + CHANGELOG and print the tag-and-push command (owner runs it; agents never push the github backup)
	@test -n "$(V)" || { echo "usage: make release V=X.Y.Z"; exit 1; }
	@echo "$(V)" > VERSION
	@sed -i.bak "s/^## Unreleased/## Unreleased\n\n## $(V) - $$(date +%F)/" CHANGELOG.md && rm -f CHANGELOG.md.bak
	@echo "VERSION and CHANGELOG.md bumped to $(V). Commit and merge to main, then the OWNER runs:"
	@echo "  git tag -s $(REPO)-v$(V) -m '$(REPO) v$(V)' && git push origin $(REPO)-v$(V) && git push github main $(REPO)-v$(V)"

deploy-staging: check-private ## stub: refuses until deploy/deploy.sh is wired with a scoped token
	deploy/deploy.sh staging

deploy-prod: check-private ## stub: refuses; prod needs a release tag signed by the owner
	deploy/deploy.sh prod
