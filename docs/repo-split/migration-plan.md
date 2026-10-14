# Repo split: phased migration plan

Companion to [review.md](review.md) (verdict: MODIFY). Target topology is the proposal's
8 repos unchanged; this plan changes how we get there. Decisions referenced as `D-*` are in
[decisions.md](decisions.md).

**Revised 2026-10-14 after Chris's gate answers:** org stays on GitHub **Free** (D-G1 = no); mono
stays **public until cutover** (D-G2 = no); R0 is a **fresh repo** (D-12′); R0 releases by **tags**
(D-R3); private repos use **self-hosted runners** (D-G4). Open follow-ups: D-G5 (deploy runner host)
and D-G6 (signed-tag deploy gate).

Naming used below:
- **mono** = today's `digithings-ai/digithings`. It stays public and keeps its name until the
  cutover in P3, where it is renamed `digithings-ai/digithings-mono` and made private.
- **R0** = the new public repo. Staged privately as `digithings-ai/digithings-next`; renamed to
  `digithings-ai/digithings` and made public at cutover.
- R1 `digiquant-strategies`, R2 `digiquant-stack`, R3 `digiquant-web`, R4 `digithings-web`,
  R5 `digithings-stack`, R6 `digichat-tenants`, R7 `twelve-x` (exists).

```
P0 Prepare ─► P1 Decouple (in mono) ─► P2 Release plumbing + deploy gate ─► P3 Cutover (R0 public, mono private)
                                                                               │
             ┌─────────────────────────────────────────────────────────────────┘
             ▼
P4 Extract private repos: R6 → R1 → R2 → R5 → R3 → R4 → R7 ─► P5 Archive mono ─► P6 Docs & tooling sweep
```

Each phase ends with an exit check. No phase deploys anything that is not already deployed, except
the per-repo cut-over deploys in P4, which run only from a release tag signed by Chris (D-G6).

## Constraints from GitHub Free

| Repo state | Branch protection / rulesets | Environments + required reviewers | Runner |
|---|---|---|---|
| Public (mono until P3, R0 after) | yes | yes | GitHub-hosted only (free minutes). **Never** a self-hosted runner: fork PRs could run code on it. |
| Private (R1–R7, mono after P3) | **no** | **no** (no environment secrets either) | Self-hosted (D-G4); 2,000 hosted min/month as overflow. |

Consequences:
- The human release gate for private repos cannot live on GitHub. It moves to the **deploy runner**:
  deploy jobs run `runs-on: [self-hosted, deploy]`, the deploy credentials exist only on that runner,
  and a job-started hook refuses any job that is not on a release tag signed by Chris (P2 step 6).
- On private repos `develop`/`main` cannot be protected. Mitigations: merge-queue-only merges by
  convention, CODEOWNERS (advisory), a nightly audit job that flags any direct push to `main`/`develop`.
  Rulesets are kept as code (`scripts/split/rulesets/`) so a later GitHub Team upgrade is one `apply`.
- Runners are registered **per repository** on private repos only. The org Default runner group keeps
  "Allow public repositories" off (runner groups with repo lists need Team).

---

## P0 — Prepare (day 0–2)

Goal: know everything that deploys from mono, and get the runner host and signing key ready.
Mono stays public (D-G2); its `production` environment and required reviewers keep working.

1. Inventory (read-only):
   - `gh api repos/digithings-ai/digithings/environments`, `.../rulesets`, `.../actions/secrets`, `.../actions/variables` → saved to the issue (names only, never values).
   - Cloudflare: list Workers, Pages projects, custom domains, routes, KV namespaces, R2 buckets, and which repo/workflow deploys each (reconciles review G1, incl. `corpus-index`).
   - `gitleaks detect --log-opts="--all"` on a mirror clone → list of secrets ever committed (rotate any hits in P1).
   - Fetch each existing fork; `git log --all -- <private paths>` on each → record what it holds (result on the issue only).
2. Remove `push` triggers from `deploy-digiquant-runner` / `deploy-digithings-cron` (dispatch only), in a PR into `develop`.
3. Runner host (D-G5): Chris provisions the deploy host. DevOps installs the runner software but does **not** register it yet (registration happens per private repo in P2/P4).
4. Signing key (D-G6): Chris creates an `ed25519-sk` SSH signing key on a FIDO2 key. Only the **public** key goes into `allowed_signers` (committed in each private repo and installed on the runner host).

Exit check: inventory posted; deploy workflows show `workflow_dispatch` only; runner host reachable
by Chris; `git tag -s` + `git verify-tag` round-trip works with the new key on a scratch repo.

Rollback: nothing irreversible in this phase.

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
| 1.9 | Deploy workflows for every Worker (stack, digichat, langfuse, cron, runner, dashboard-api, corpus-index, digidata-api) — tag/dispatch-triggered, clean checkout, written so the same file runs either on GitHub-hosted with `environment: production` (mono while public) or on `[self-hosted, deploy]` without an environment (private repos). Retire manual `wrangler deploy`; `occ_invite_key_rollout.sh` split into "write secret/KV" (R6) and "deploy" (R5). | R5, R6 | M |
| 1.10 | Rotate any secret found by P0 gitleaks; move deploy tokens to per-target scoped Cloudflare tokens. | all | S |
| 1.11 | Guard workflow `moved-paths-guard`: fails a PR touching a path whose manifest destination is already extracted (populated in P4). | P4 | S |

Exit check: manifest has zero unassigned paths; no import crosses a repo boundary
(`scripts/split/check_boundaries.py`: Python imports, TS relative imports, Dockerfile COPY, workflow `paths`);
every deployed Worker has exactly one deploy workflow; `develop` → `main` promotion approved by Chris (D-14).

Rollback: each PR reverts on its own.

---

## P2 — Release plumbing and the deploy gate (≈3–4 days, overlaps the end of P1)

1. **Python:** release-please manifest config, one component per module; publish to PyPI with
   trusted publishing (configured against owner `digithings-ai`, repo `digithings`, the release
   workflow file and environment `pypi`; the same entry keeps working when R0 takes the name in P3).
   A pending publisher does **not** reserve a name, so check all 12 names are free now (`digiquant`
   returned 404 on 2026-10-14) and publish the first versions as soon as R0 is public (D-P1).
2. **npm:** confirm Chris controls the `digithings` npm org (the org exists; ownership UNSURE) (D-P2). Publish `@digithings/*` from R0 only, after P3.
3. **Private Python (R1):** no GitHub Packages for Python (review F2). Use a git tag pin:
   `digiquant-strategies @ git+https://github.com/digithings-ai/digiquant-strategies@v0.1.0` locked by SHA in `uv.lock`;
   R2's Docker build reads it with a GitHub App installation token passed as a BuildKit secret (D-Q7).
4. **Private npm (`@digiquant/contract`):** GitHub Packages npm from R2; R3's Actions reads it with `GITHUB_TOKEN` after granting R3 access on the package.
5. **GitHub App `digithings-release-bot`:** opens bump PRs, dispatches cron workflows. Installed per repo. It does **not** create deploy tags (it cannot sign them).
6. **Deploy gate on the self-hosted runner (D-G6)** — replaces protected `release/*` + environment reviewers:
   - Deploy credentials (scoped Cloudflare tokens, Supabase access token) live only on the deploy host, in a root-owned file read by the runner service user. Not in GitHub secrets.
   - `ACTIONS_RUNNER_HOOK_JOB_STARTED` script `scripts/split/runner/deploy-gate.sh` (versioned in R5, installed on the host by Chris) exits non-zero unless:
     1. `GITHUB_REPOSITORY` is in the host's repo allowlist (private repos only);
     2. `GITHUB_REF` is `refs/tags/<component>-v*` and `GITHUB_EVENT_NAME` is `push` or `workflow_dispatch` on that tag;
     3. `git verify-tag` of that tag passes against the host's `allowed_signers` (Chris's `ed25519-sk` key only);
     4. `GITHUB_WORKFLOW_REF` points to a workflow file at the same tagged commit.
   - Tags are created only by Chris (`git tag -s <component>-vX.Y.Z` on a `release/*` or `main` commit). Agents may prepare the release PR and changelog, not the tag.
   - CI runners (no credentials) can be separate runners labelled `[self-hosted, ci]`, on the Mac or the deploy host; the hook on the deploy runner rejects every job not labelled for deploy.
   - Prove the gate on R7 (already private) with a no-op deploy job: unsigned tag → job refused; agent-signed tag → refused; Chris-signed tag → runs.
7. **Repository settings as code:** `scripts/split/rulesets/` holds the full ruleset template
   (`develop` PR + checks + DCO; `main`/`release/*` code-owner review; tag creation limits). Applied
   now to R0 (public). Kept unapplied for private repos until a Team upgrade.

Exit check: a dry-run release of one module (TestPyPI) and one npm package (`--dry-run`) green from mono;
R7 gate test above passes all three cases.

---

## P3 — Cutover: R0 public, mono private (1 day + 2 days watch)

Gate: **D-12′** (fresh repo — answered), **D-G3** (public allowlist), **D-G6** (gate proven in P2), P1 exit check passed.
Mono is public until this day (D-G2), so P3 runs as soon as P1 and P2 are done; the private-repo
extraction (P4) comes after, not before, to keep the exposure window short.

Staging (days before cutover):
1. Fresh `git clone --mirror` of mono at the promoted `main` tag `split-base-1`.
2. `git filter-repo --paths-from-file r0.paths` (allowlist from the manifest) `--replace-text denylist.txt` `--replace-message denylist.txt`.
   The denylist (client names, tenant identifiers, prompt fragments) lives **outside** any repo (Chris's machine / private ops), never committed.
3. Verify offline before any push:
   - `gitleaks detect --log-opts="--all"` → zero findings.
   - Denylist grep over every blob: `git rev-list --all --objects | git cat-file --batch-check` → zero hits.
   - No path outside the allowlist in any commit: `git log --all --name-only --format= | sort -u | diff - r0.paths.expanded`.
   - Tree at HEAD equals mono's tree for allowlisted paths (`git diff --stat` across repos = 0).
4. Push to private `digithings-ai/digithings-next` (only `main`, `develop`, release tags). Run full R0 CI there (hosted minutes; no self-hosted runner) and the fresh-clone `docker compose up` self-host smoke.

Cutover day (Chris does the renames and visibility changes; agents prepare):
5. Freeze merges into mono. Re-run steps 1–3 from the final `main` SHA if it moved; force-push `digithings-next`.
6. Mono deploys switch to the gate: merge the prepared PR that sets mono's deploy jobs to `runs-on: [self-hosted, deploy]` and drops `environment: production`.
7. Rename `digithings` → `digithings-mono`; make it **private**. Register the deploy runner on it (now allowed: private). Disable the runner hook allowlist entry for any public repo.
8. Rename `digithings-next` → `digithings`; make it **public**. Apply rulesets from P2 step 7; install DCO; add CODEOWNERS, LICENSE (MIT), TRADEMARKS, SECURITY; `production`-style environment `pypi` with Chris as required reviewer.
9. Publish v0.x of PyPI modules and `@digithings/*` npm, and GHCR `digichat` / `digillm` images, from R0.
10. In mono: R0 paths frozen (`moved-paths-guard` lists them). Development on public code moves to R0. Open mono PRs that touch only R0 paths are re-opened against R0 by their owners (list posted on the tracking issue).
11. Update every remote: `~/Code/digithings*` worktrees, Paperclip project repositories, merge queue config, run-watch, worktree sweep, seat instructions that name the repo.

Exit checks:
- anonymous `curl -s -o /dev/null -w '%{http_code}' https://github.com/digithings-ai/digithings-mono` → 404;
- anonymous clone of `digithings-ai/digithings` gives R0 history only (first commit is the export, not mono's);
- one Chris-signed deploy from mono via the runner succeeds; an unsigned tag is refused;
- packages install from PyPI/npm in a clean container; denylist grep on the *pushed* repo = 0.

Rollback before step 8: rename back and make mono public again (nothing lost).
After step 8: delete or re-private R0 and yank packages. Point of no return: the first
`pip install`/`npm install` by an outsider — after that, treat what was pushed as published.

---

## P4 — Extract the private repos (one repo per step, ≈1–2 days each)

Common recipe for every target Rn:
1. `git clone --mirror` mono → `git filter-repo --paths-from-file rN.paths --path-rename …`.
2. `gitleaks` + boundary check on the new repo; push to new private repo; commit `allowed_signers`, CODEOWNERS, ruleset template (unapplied), LICENSE (proprietary).
3. Switch imports to published R0 packages (pins); wire CI on `[self-hosted, ci]`; install the GitHub App; register the deploy runner for Rn and add Rn to the hook allowlist. Repo-level Actions secrets only for non-deploy values (copied by Chris or DevOps via `gh secret set`; never pasted into issues). Deploy credentials stay on the runner host.
4. **Cut-over deploy** from a Chris-signed release tag — one deploy per target, verified (below).
5. Add Rn's paths to mono's `moved-paths-guard`; delete them from mono in one PR.
6. Update Paperclip project binding, merge queue, run-watch, CODEOWNERS, seat instructions for Rn.

Validation and rollback per target:

| Step | Repo | Cut-over and validation | Rollback |
|---|---|---|---|
| 4.1 | R6 digichat-tenants | `kv-sync` writes `TENANT_CONFIG` + seeds to staging namespace, then prod; tenant chat answers from KV (answer-check workflow green for each tenant); stack fallback serves only `digithings`. | Re-run `kv-sync` from previous tag (KV values are versioned by tag). |
| 4.2 | R1 digiquant-strategies | Tag `v0.1.0`; `pip install` from git tag in a clean container; plugin discovered by R0 `digiquant` (entry points list); backtest suite green; conformance test green. | R2 keeps pinning mono-built runner image until 4.3. |
| 4.3 | R2 digiquant-stack | Runner image built from pins (R0 PyPI + R1 git tag) deployed; one full pipeline run produces its outputs (compare row counts / artifacts with the previous mono run); dashboard-api deployed as own Worker; desk reads through it; `supabase db push` dry-run shows no diff. | `wrangler rollback` to previous Worker version; previous runner image tag. |
| 4.4 | R5 digithings-stack | stack, digichat, langfuse, cron, corpus-index each deployed once from a signed `stack-v*` tag; health checks on all routes listed in the proposal; cron dispatches R2/R7 workflows with the App token; tenant chat smoke per tenant. | `wrangler rollback` per Worker; cron rollback restores old dispatch targets. |
| 4.5 | R3 digiquant-web | New Pages project `digiquant-io-r3` direct-uploaded by the deploy runner from a signed `web-v*` tag; preview checked against R2; move custom domain `digiquant.io`. Old project's Git builds disabled (production branch set to an unused name). | Move domain back to old project (minutes). |
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
4. Remove mono from the runner hook allowlist; unregister its runners.
5. Archive `digithings-mono` (already private since P3; read-only). Keep it: it is the full-history audit trail and the rollback source.

---

## P6 — Docs, tooling and seat sweep (runs alongside P3–P5)

| Where | What to update |
|---|---|
| R0 `README.md`, `CONTRIBUTING.md`, `docs/DEPLOYMENT.md`, `docs/BRANCH_PROTECTION.md`, `docs/MERGE_QUEUE.md`, `docs/LICENSING.md`, `docs/SELF_HOST.md`, `docs/LOCAL_STACK.md` | Remove production deploy content (moves to R5/R2 runbooks); release model (tags + release-please); new repo map (public-safe version). |
| R5 runbook | Deploy runner: host, hook, `allowed_signers` rotation, how Chris cuts a signed release tag, how to add a repo to the allowlist. |
| openwiki | Per-module pages: install from PyPI/npm instead of monorepo paths; `openwiki/dashboard` → R3; `INSTRUCTIONS.md` repo map. |
| digibook (R4 `content/book`) | System-architecture chapter: repo map and release flow; "how the book is built" (now R4 + R0 docs pulled at build). |
| docs site (digithings.ai docs, openapi catalog) | Source openapi + byok catalog from `@digithings/catalog`; links to R0 instead of mono paths. |
| `docs/repo-split/` (this folder) | Mark phases done; final repo map. |
| Paperclip | Projects ↔ repos, `dt-create-issue --project` mapping, merge queue repo list, worktree sweep, run-watch job → repo map, decisions/standing.md entry for the split. |
| Seat instructions and skills | Replace monorepo paths and the single-repo assumption; per-repo branch rules; agents never create release tags. |
| `~/Code` layout | `dt-dev` bootstrap: clones R0–R7 side by side, `uv`/npm overlays for local cross-repo work. |

---

## Tracking

One epic under G07 with one leaf per row of P1, one per P4 step, plus P0, P2, P3, P5, P6.
The gate decisions are answered (2026-10-14), so the CTO can create the leaves. P0 steps 3–4 and
P2 step 6 wait for D-G5 / D-G6.
