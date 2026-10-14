# Repo split: phased migration plan

Companion to [review.md](review.md) (verdict: MODIFY). Target topology is the proposal's
8 repos unchanged; this plan changes how we get there. Decisions referenced as `D-*` are in
[decisions.md](decisions.md); the ones marked **gate** must be answered before that phase starts.

Naming used below:
- **mono** = today's `digithings-ai/digithings`, renamed `digithings-ai/digithings-mono` in Phase 0.
- **R0** = the new public `digithings-ai/digithings`, created in Phase 3.
- R1 `digiquant-strategies`, R2 `digiquant-stack`, R3 `digiquant-web`, R4 `digithings-web`,
  R5 `digithings-stack`, R6 `digichat-tenants`, R7 `twelve-x` (exists).

```
P0 Contain ─► P1 Decouple (in mono) ─► P2 Release plumbing ─► P3 Cut R0 (public)
                                                                 │
             ┌───────────────────────────────────────────────────┘
             ▼
P4 Extract private repos: R6 → R1 → R2 → R5 → R3 → R4 → R7 ─► P5 Archive mono ─► P6 Docs & tooling sweep
```

Each phase ends with an exit check. No phase deploys anything that is not already deployed, except
the per-repo cut-over deploys in P4, which are gated by Chris's approval of the `release/*` PR.

---

## P0 — Contain (day 0–1)

Goal: end public exposure of client and strategy files now, without breaking any running workflow.

Gate: **D-G1** (GitHub Team) and **D-G2** (rename + private flip).

1. Upgrade org `digithings-ai` to GitHub Team (1 member → 1 seat). Chris only: billing.
2. Inventory before the flip (read-only):
   - `gh api repos/digithings-ai/digithings/environments`, `.../rulesets`, `.../actions/secrets`, `.../actions/variables` → saved to the issue.
   - Cloudflare: list Workers, Pages projects, custom domains, routes, KV namespaces, R2 buckets, and which repo/workflow deploys each (reconciles review G1, incl. `corpus-index`).
   - `gitleaks detect --log-opts="--all"` on a mirror clone → list of secrets ever committed (rotate any hits in P1).
   - Fetch each existing fork; `git log --all -- <private paths>` on each → record what it holds (result on the issue only).
3. Rename `digithings` → `digithings-mono` (GitHub keeps a redirect until a repo takes the old name).
4. Make `digithings-mono` private. Consequences to handle the same hour:
   - `production` environment loses *required reviewers* (not on Team for private). Interim gate: set the environment's deployment-branch policy to `main` only and keep `deploy-digiquant-runner` / `deploy-digithings-cron` on `workflow_dispatch` only (remove their `push` triggers in a PR first, step 0 of P0).
   - Re-check `module-branch-protection` ruleset and `develop`/`main` protection still apply (they do on Team).
   - Cloudflare Pages Git integration keeps working if the Cloudflare app has org-wide access (it is installed on the org).
   - Actions minutes now billed beyond Team's included minutes (review G6). Mitigation: path filters on the heaviest workflows, or a self-hosted runner on a dedicated machine (D-G4).
5. Update every remote: `~/Code/digithings*` worktrees, Paperclip project repositories, merge queue config, run-watch, worktree sweep, agent seat instructions that name the repo.

Exit check: anonymous `curl -s -o /dev/null -w '%{http_code}' https://github.com/digithings-ai/digithings-mono` → 404;
one merge-queue merge into `develop` succeeds; one CI run green; deploy workflows show `workflow_dispatch` only.

Rollback: flip visibility back to public (the rename can stay). Nothing is lost.

---

## P1 — Decouple inside mono (≈1–2 weeks, the bulk of the work)

All of the proposal's §1 refactors, as normal PRs into `develop`, **no moves yet**. Ordered so
each PR is independently shippable. Lane in brackets (operating rules).

| # | Change | Unblocks | Lane |
|---|---|---|---|
| 1.1 | Path manifest script `scripts/split/manifest.py`: maps every tracked path to exactly one of R0–R7/delete; CI fails on unassigned paths. Pinned-SHA output stored as an artifact. | all | S |
| 1.2 | `digiquant.plugin` surface + entry-point discovery (`digiquant.strategies`, `digiquant.mcp_tools`, `digiquant.cli`); private strategies, SDCA MCP, optimiser, SDCA charts and CLI subcommands register through it; dummy-plugin conformance test. | R1 | M |
| 1.3 | `DIGIQUANT_CONFIG_DIR` + neutral example configs; production config only read via the env var. | R2 | S |
| 1.4 | Unfold `dashboard-api` into its own Worker again; route `/dashboard-api/*` by zone route (D-Q2′); extract `@digiquant/contract` (types + pure functions shared by desk and API). | R2, R3 | M |
| 1.5 | Supabase layering (D-Q6′): split migrations into `engine/` (tables the open pipeline reads/writes) and `prod/` (house-only); CI applies both in order on a scratch DB. | R0/R2 | M |
| 1.6 | npm packages: tsup builds, `exports` maps, `private: false`, `license: MIT`; PixelWordmark → `@digithings/ui`; `@digithings/catalog` (byok-providers + openapi); apps import only via package exports (lint rule bans `../../packages/*/src`). | R3, R4 | M |
| 1.7 | Tenant data out of code: `TENANT_CONFIG` KV read path with `digithings`-only fallback; seeds fetched from R2 at container boot; suggestion pools/looks from KV; production model list from KV/env. Prove on staging tenant first. | R5, R6 | M |
| 1.8 | Dockerfiles consume packages/images, not sibling paths (runner, stack, digichat). | R2, R5 | M |
| 1.9 | Deploy workflows for every Worker (stack, digichat, langfuse, cron, runner, dashboard-api, corpus-index, digidata-api) — tag/dispatch-triggered, `environment: production`, clean checkout. Retire manual `wrangler deploy`; `occ_invite_key_rollout.sh` split into "write secret/KV" (R6) and "deploy" (R5). | R5, R6 | M |
| 1.10 | Rotate any secret found by P0 gitleaks; move deploy tokens to per-target scoped Cloudflare tokens. | all | S |
| 1.11 | Guard workflow `moved-paths-guard`: fails a PR touching a path whose manifest destination is already extracted (populated in P4). | P4 | S |

Exit check: manifest has zero unassigned paths; no import crosses a repo boundary
(`scripts/split/check_boundaries.py`: Python imports, TS relative imports, Dockerfile COPY, workflow `paths`);
every deployed Worker has exactly one deploy workflow; `develop` → `main` promotion approved by Chris (D-14).

Rollback: each PR reverts on its own.

---

## P2 — Release plumbing (≈2–3 days, overlaps the end of P1)

1. **Python:** release-please manifest config, one component per module; publish to PyPI with
   trusted publishing (configured against the *future* R0 repo name and workflow — PyPI pending
   publishers allow this before the repo exists). A pending publisher does **not** reserve a name, so
   check all 12 names are free now (`digiquant` returned 404 on 2026-10-14) and publish the first
   versions as soon as R0 exists (D-P1).
2. **npm:** confirm Chris controls the `digithings` npm org (the org exists; ownership UNSURE) (D-P2). Publish `@digithings/*` from R0 only, after P3.
3. **Private Python (R1):** no GitHub Packages for Python (review F2). Use a git tag pin:
   `digiquant-strategies @ git+https://github.com/digithings-ai/digiquant-strategies@v0.1.0` locked by SHA in `uv.lock`;
   R2's Docker build reads it with a GitHub App installation token passed as a BuildKit secret (D-Q7).
4. **Private npm (`@digiquant/contract`):** GitHub Packages npm from R2; R3's Actions reads it with `GITHUB_TOKEN` after granting R3 access on the package.
5. **GitHub App `digithings-release-bot`:** creates tags, opens bump PRs, dispatches cron workflows. Installed per repo.
6. **Rulesets (template applied to every repo by script):**
   - `develop`: PR required, required checks, DCO, no force-push.
   - `main` (R0) / `release/*` (R2–R6): PR required, **CODEOWNERS = Chris**, require code-owner review, no bypass except Chris.
   - Tags `*-v*` / `v*`: creation restricted to the release bot.
   - `production` environment: deployment branches = `release/*` + release tags only.

Exit check: a dry-run release of one module (TestPyPI) and one npm package (`--dry-run`) green from mono.

---

## P3 — Cut R0, the new public repo (1 day + 2 days watch)

Gate: **D-12′** (fresh public repo, not in-place scrub), **D-G3** (public allowlist), P1 exit check passed.

1. Fresh `git clone --mirror` of mono at the promoted `main` tag `split-base-1`.
2. `git filter-repo --paths-from-file r0.paths` (allowlist from the manifest) `--replace-text denylist.txt` `--replace-message denylist.txt`.
   The denylist (client names, tenant identifiers, prompt fragments) lives **outside** any repo (Chris's machine / private ops), never committed.
3. Verify offline before any push:
   - `gitleaks detect --log-opts="--all"` → zero findings.
   - Denylist grep over every blob: `git rev-list --all --objects | git cat-file --batch-check` → zero hits.
   - No path outside the allowlist in any commit: `git log --all --name-only --format= | sort -u | diff - r0.paths.expanded`.
   - Tree at HEAD equals mono's tree for allowlisted paths (`git diff --stat` across repos = 0).
   - Fresh-clone `docker compose up` self-host smoke + full R0 CI on a private staging copy (`digithings-r0-staging`, private).
4. Create public `digithings-ai/digithings`; push only `main`, `develop` and release tags (no feature branches).
   Apply rulesets; install DCO; add CODEOWNERS, LICENSE (MIT), TRADEMARKS, SECURITY.
5. Publish v0.x of PyPI modules and `@digithings/*` npm, and GHCR `digichat` / `digillm` images, from R0.
6. In mono: R0 paths are now frozen (`moved-paths-guard` lists them). Development on public code moves to R0 from this moment.
   Open mono PRs that touch only R0 paths are re-opened against R0 by their owners (list posted on the tracking issue).

Exit check: anonymous clone of R0 works; packages install from PyPI/npm in a clean container; denylist grep on the *pushed* repo = 0.

Rollback: delete the new public repo (nothing depends on it yet except the fresh packages; yank them).
Point of no return: the first `pip install`/`npm install` by an outsider — after that, treat what was pushed as published.

---

## P4 — Extract the private repos (one repo per step, ≈1–2 days each)

Common recipe for every target Rn:
1. `git clone --mirror` mono → `git filter-repo --paths-from-file rN.paths --path-rename …`.
2. `gitleaks` + boundary check on the new repo; push to new private repo; apply ruleset template; LICENSE (proprietary).
3. Switch imports to published R0 packages (pins), wire CI, GitHub App, environment + secrets (copied by Chris or DevOps via `gh secret set`; never pasted into issues).
4. **Cut-over deploy** from the new repo's `release/*` (PR approved by Chris) — one deploy per target, verified (below).
5. Add Rn's paths to mono's `moved-paths-guard`; delete them from mono in one PR.
6. Update Paperclip project binding, merge queue, run-watch, CODEOWNERS, seat instructions for Rn.

Validation and rollback per target:

| Step | Repo | Cut-over and validation | Rollback |
|---|---|---|---|
| 4.1 | R6 digichat-tenants | `kv-sync` writes `TENANT_CONFIG` + seeds to staging namespace, then prod; tenant chat answers from KV (answer-check workflow green for each tenant); stack fallback serves only `digithings`. | Re-run `kv-sync` from previous tag (KV values are versioned by tag). |
| 4.2 | R1 digiquant-strategies | Tag `v0.1.0`; `pip install` from git tag in a clean container; plugin discovered by R0 `digiquant` (entry points list); backtest suite green; conformance test green. | R2 keeps pinning mono-built runner image until 4.3. |
| 4.3 | R2 digiquant-stack | Runner image built from pins (R0 PyPI + R1 git tag) deployed; one full pipeline run produces its outputs (compare row counts / artifacts with the previous mono run); dashboard-api deployed as own Worker; desk reads through it; `supabase db push` dry-run shows no diff. | `wrangler rollback` to previous Worker version; previous runner image tag. |
| 4.4 | R5 digithings-stack | stack, digichat, langfuse, cron, corpus-index each deployed once from `release/stack`; health checks on all routes listed in the proposal; cron dispatches R2/R7 workflows with the App token; tenant chat smoke per tenant. | `wrangler rollback` per Worker; cron rollback restores old dispatch targets. |
| 4.5 | R3 digiquant-web | New Pages project `digiquant-io-r3` direct-uploaded from `release/web`; preview checked against R2; move custom domain `digiquant.io`. Old project's Git builds disabled (production branch set to an unused name). | Move domain back to old project (minutes). |
| 4.6 | R4 digithings-web | Same as R3 for `digithings.ai`; routes to R5 (`/api/*`, `/embed*`) checked. | Move domain back. |
| 4.7 | R7 twelve-x | twelve-x desk surface + `digidata-api` moved; desk gate/palette in R3 made pluggable first (D-X1). twelve-x client gates apply. | Revert PRs in R3/R7; previous digidata-api version. |

Why this order: R6 first removes the most sensitive data from the platform images; R1 before R2
because R2 pins it; R2 before R5 because R5's cron binds to R2's Workers by name; web last because
the domain swap is the cheapest rollback and depends on R2/R5 APIs being stable. This keeps the
proposal's order except R5 moves before R3 (R3's desk depends on the platform routes being final).

Freeze rule per step: from step 1 until step 5 of the recipe, PRs touching Rn's paths in mono are
held (guard in "warn" mode during extraction, "fail" mode after cut-over).

---

## P5 — Archive mono (after 4.7 + 14 days)

1. Confirm `moved-paths-guard` covers every path in mono; manifest shows nothing left.
2. Close or re-home every open PR and issue (owners per PR-ownership rule).
3. Disable Pages Git integration on the old projects, then delete them after 30 days.
4. Archive `digithings-mono` (read-only, private). Keep it: it is the full-history audit trail and the rollback source.

---

## P6 — Docs, tooling and seat sweep (runs alongside P3–P5)

| Where | What to update |
|---|---|
| R0 `README.md`, `CONTRIBUTING.md`, `docs/DEPLOYMENT.md`, `docs/BRANCH_PROTECTION.md`, `docs/MERGE_QUEUE.md`, `docs/LICENSING.md`, `docs/SELF_HOST.md`, `docs/LOCAL_STACK.md` | Remove production deploy content (moves to R5/R2 runbooks); release model (tags + release-please); new repo map (public-safe version). |
| openwiki | Per-module pages: install from PyPI/npm instead of monorepo paths; `openwiki/dashboard` → R3; `INSTRUCTIONS.md` repo map. |
| digibook (R4 `content/book`) | System-architecture chapter: repo map and release flow; "how the book is built" (now R4 + R0 docs pulled at build). |
| docs site (digithings.ai docs, openapi catalog) | Source openapi + byok catalog from `@digithings/catalog`; links to R0 instead of mono paths. |
| `docs/repo-split/` (this folder) | Mark phases done; final repo map. |
| Paperclip | Projects ↔ repos, `dt-create-issue --project` mapping, merge queue repo list, worktree sweep, run-watch job → repo map, decisions/standing.md entry for the split. |
| Seat instructions and skills | Replace monorepo paths and the single-repo assumption; per-repo branch rules (`develop` → `main`/`release/*`). |
| `~/Code` layout | `dt-dev` bootstrap: clones R0–R7 side by side, `uv`/npm overlays for local cross-repo work. |

---

## Tracking

One epic under G07 with one leaf per row of P1, one per P4 step, plus P0, P2, P3, P5, P6.
Leaves are created only after Chris answers the gate decisions (operating rules: no reflex tickets).
