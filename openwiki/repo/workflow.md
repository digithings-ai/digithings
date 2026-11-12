---
type: repo-guide
title: Repo Workflow
description: Branching model, make targets, and review/merge policy pointers for this repository.
tags: [repo, branching, make, review-policy]
sources:
  - id: openwiki-source-4b2266e051b2270b6ec5aa4f
    resource: repo://BRANCHING.md
  - id: openwiki-source-a49bd70bd0f6d776441b838b
    resource: repo://docs/agents/CODE_REVIEW_POLICY.md
  - id: openwiki-source-012f2c78e3b1446dfc35803f
    resource: repo://Makefile
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-23T13:25:31.068Z
---

# Repo Workflow

This page is a pointer map, not a duplicate of the source docs. Normative
detail lives in `BRANCHING.md`, `AGENTS.md`, and
`docs/agents/CODE_REVIEW_POLICY.md`.

## Branching model

Two tiers: `main ← develop ← task/<N>-slug`. Task branches cut from
`develop` via `make task ISSUE=N`; `scripts/project_routing.json` routes
every component to `develop`. The `module/<component>` tier was retired
(#6751). `main` is what is deployed; `develop` is the default integration
branch. Name enforcement is client-side (`make hooks-install`); server-side,
`main` requires the review-coverage check.

## Make targets

Stack: `make up` / `down`, `pull-ghcr`, host-native `make stack-local` /
`stack-local-stop`, `make digichat-dev`, `make up-digichat-db`. Tests:
`make test-unit`, `make test-baseline`, `make test-e2e`. Workflow:
`make task ISSUE=N`, `make module-switch/-sync/-pr/-status`,
`make agents-init`, `make hooks-install`. Docs/data: `make doc-check`,
`make openapi-export` / `openapi-check`, digisearch seed/export targets.

## Review and merge policy

Default is in-session review on a fresh-context subagent (`/review <N>`)
with findings posted as `<!-- in-session-review -->` plus the
`reviewed:agent` label for the `main` coverage gate. Metered bots are
on-demand only (Bugbot `bugbot run` once per final diff; CodeRabbit
re-requests only for fixed majors). The merge queue merges a PR into
`develop` once required CI is green and the review gate is met. The
author does not merge. Human-gate exceptions still apply (`digikey/`
auth/crypto, live-trading paths, new external exposure, PRs into
`main`, release-please PRs).
