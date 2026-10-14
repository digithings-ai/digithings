# Repo split: phased migration plan

Companion to [review.md](review.md) (verdict: MODIFY). Target topology is the proposal's
8 repos unchanged; this plan changes how we get there. Decisions referenced as `D-*` are in
[decisions.md](decisions.md).

**Revised 2026-10-14 after Chris's gate answers:** org stays on GitHub **Free** (D-G1 = no); mono
stays **public until cutover** (D-G2 = no); R0 is a **fresh repo** (D-12′); R0 releases by **tags**
(D-R3); private repos use **self-hosted runners** (D-G4). Answered 2026-10-14 17:40 CEST:
deploys + CI run on Chris's Mac under his normal user with a Cloudflare Worker fallback
(D-G5); signed release tags are optional/recommended, not mandatory (D-G6).

**Revised again 2026-10-14 (Chris's direction):** R1–R7 move to **Cursor Origin**, not to GitHub.
See [Source control on Cursor Origin](#source-control-on-cursor-origin). D-O1 … D-O5 answered 2026-10-14.

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
the per-repo cut-over deploys in P4, which run only from a release tag cut by Chris (D-G6:
signing the tag is optional/recommended, not mandatory).

## Constraints from GitHub Free

| Repo state | Branch protection / rulesets | Environments + required reviewers | Runner |
|---|---|---|---|
| Public (mono until P3, R0 after) | yes | yes | GitHub-hosted only (free minutes). **Never** a self-hosted runner: fork PRs could run code on it. |
| Private (R1–R7, mono after P3) | **no** | **no** (no environment secrets either) | Self-hosted (D-G4); 2,000 hosted min/month as overflow. |

Consequences:
- The human release gate for private repos cannot live on GitHub. It moves to the **deploy
  agent on Chris's Mac** (D-G5): Buildkite `deploy` queue runs there under his normal user,
  deploy credentials exist only there (plus the Worker fallback), and the gate hook refuses
  any job that is not on a release tag cut by Chris — with an optional `git verify-tag`
  signature check (D-G6, only when the tag carries a signature).
- On private repos `develop`/`main` cannot be protected. Mitigations: merge-queue-only merges by
  convention, CODEOWNERS (advisory), a nightly audit job that flags any direct push to `main`/`develop`.
  Rulesets are kept as code (`scripts/split/rulesets/`) so a later GitHub Team upgrade is one `apply`.
- Runners are registered **per repository** on private repos only. The org Default runner group keeps
  "Allow public repositories" off (runner groups with repo lists need Team).

## Source control on Cursor Origin

**Revised 2026-10-14 (Chris's direction):** R1–R7 live on **Cursor Origin** as primary. The table
above still applies to GitHub-hosted repos (mono until P5, and R0, which stays GitHub-primary per D-O1). Origin capabilities
were checked against Cursor's docs, not assumed; see [review.md § Cursor Origin](review.md#cursor-origin-as-the-source-control-home-direction-of-2026-10-14).
Decisions D-O1 … D-O5 (answered) are in [decisions.md](decisions.md#cursor-origin-decisions-answered).

Placeholders: `<ns>` = Chris's personal Origin namespace (D-O2). Clone URL `https://origin.cursor.com/<ns>/<repo>.git`.

### 1. Repo creation (visibility, ownership, naming)

| Repo | Home | Visibility | How it is created |
|---|---|---|---|
| R0 `digithings` | **GitHub** `digithings-ai/digithings` primary + Origin inbound mirror `<ns>/digithings` (D-O1). | GitHub: public. Origin: private (only option). | Chris runs `origin repo create-mirrored` after P3. |
| R1–R6 | Origin `<ns>/<repo>` | private | Empty repo; filtered history pushed in P4 (`git push` of `main`, `develop`, release tags only). |
| R7 `twelve-x` | Origin `<ns>/twelve-x` | private | See §3. |
| mono after P3 | **Stays on GitHub** (private, then archived in P5). Not moved to Origin. | private | — |

- Names are **the same as on GitHub** and are permanent while Origin is in beta, so they are fixed in P0 and not changed later.
- Chris creates the namespace and the repos (the CLI and API need his login). Agents prepare the
  commands and ruleset files; they never run `origin auth login` and never use a Cursor API key.
- The existing Origin mirror of mono in Chris's personal namespace stays as it is until P5, then is deleted (it holds the full public history).

### 2. Public repo and GitHub (direction of truth, CI, external PRs)

**Decided (D-O1): GitHub primary for R0, Origin inbound mirror.** Truth: GitHub → Origin (Origin
syncs branches, tags, PRs). Agents may clone from Origin; a push to the Origin mirror is forwarded to
GitHub, so GitHub rulesets still apply. CI: GitHub Actions on hosted runners (free on public repos);
PyPI trusted publishing keeps working unchanged. External PRs: native on GitHub, nothing to pull back.
This keeps one source of truth with only documented features, and it differs from Chris's first
direction only for R0. The Origin-primary option with a push mirror built by us was not chosen.

### 3. twelve-x with full history

R7 already exists as a private GitHub repo, and P4.7 adds the twelve-x paths from mono.
1. `gitleaks detect --log-opts="--all"` on a mirror clone of the GitHub repo. Rotate any hit first.
2. **No findings:** Chris runs `origin repo create-mirrored` for it (full history, branches, tags,
   PRs), checks it, then **detaches** it (one-way; Origin becomes primary). Detach needs Chris's user
   credential and admin on the GitHub repo.
3. **Findings:** `git filter-repo --replace-text denylist.txt` on the mirror clone, verify offline
   (same checks as P3 step 3), push to an empty Origin repo. PR history is not carried; the PR list is
   exported to the tracking issue first.
4. The GitHub repo is made read-only (archived, private) for 90 days as a rollback source, then deleted (D-O5: no client contract applies).
5. P4.7: extract the twelve-x paths from mono with `git filter-repo --paths-from-file r7.paths`,
   then merge them into the Origin repo with `--allow-unrelated-histories`, in a PR. History of both sources is kept.

### 4. CI on Origin

- GitHub Actions does **not** run on Origin pushes. Private repos use **Buildkite** with Origin
  connected as the repository provider (D-O3). Buildkite posts check runs to Origin PRs, so
  `require_status_checks` rulesets can use them.
- Agents are **self-hosted** (D-G4 stands): queue `ci` on Chris's Mac, no credentials;
  queue `deploy` on the Mac `deploy` agent only (D-G5), with the Cloudflare Worker fallback.
- Checkout uses `origin repo clone-fast` in a Buildkite `checkout` hook; Buildkite mints the short-lived Origin token.
- Workflows in `.github/workflows/` of R1–R7 are rewritten as `.buildkite/pipeline.yml`. The P1.9
  deploy workflows are written as plain scripts (`scripts/deploy/<target>.sh`) so the same script runs
  from GitHub Actions (mono) and from Buildkite (R2–R7).
- Scheduled jobs that `digithings-cron` dispatches through the GitHub API move to the Buildkite
  builds API (token on Chris's Mac, scoped to the pipelines it triggers).
- Public CI (R0) stays on GitHub-hosted runners (D-O1).

### 5. Cloudflare deploys after the move

- **Do not install the Cloudflare app in Cursor** and do not connect any Worker or Pages project to an
  Origin repo through Workers Builds: that integration auto-deploys on every push.
- Deploys run only on the `deploy` queue (Chris's Mac, Worker fallback), from a release tag
  cut by Chris (D-G5; signing optional per D-G6), with `wrangler deploy` / Pages direct upload.
  The gate hook is the same script as before with a Buildkite adapter: it checks `BUILDKITE_REPO`
  against the allowlist, `BUILDKITE_TAG` matches `<component>-v*`, `BUILDKITE_COMMIT` equals the
  tag's commit, and — only when the tag carries a signature — `git verify-tag` passes against
  `allowed_signers`. The pipeline step that deploys is read from the tagged commit, not from a later upload.
- Origin `repository pushed` webhooks are **not** wired to any deploy.
- Existing Git-connected Pages projects (on mono) are handled as before (P4.5, P4.6, P5): new
  direct-upload projects, then the domain moves.

### 6. Paperclip agents and worktrees

- Agents run as Chris's macOS user. Git on this Mac already reaches Origin through Chris's
  credential helper. **Chris** does every login (`origin auth login` or `origin ssh-key add`);
  agents never log in and never handle a token.
- Identity (D-O4, answered): agents **keep using Chris's account** through his existing credential
  helper. There is no separate agent account, so Origin rulesets do not bind agents. D-G6 is
  optional, so the tag gate is procedural, not hard: agents must never cut release tags, and the
  audit log is the control. The hard control is Chris cutting the tag.
- Worktrees: no change in how they work (`git worktree add` from an Origin clone). Remote convention:
  `origin` = Origin, `github` = GitHub (R0 only). `dt-dev` bootstrap clones R1–R7 from Origin.
- Tooling that calls `gh` must be ported before the first private repo moves (P2): merge queue
  (`origin pr` / Origin API, `merge_when_ready`), run-watch (Buildkite API), worktree sweep, PR-ownership
  checks. Paperclip project ↔ repo bindings use the Origin URL. Whether Paperclip's repository
  binding accepts a non-GitHub remote is UNSURE; checked in P2 on a scratch repo.

### 7. Branch protection and per-package release branches

Rulesets live as code in `scripts/split/rulesets/origin/` and are applied by Chris with
`origin api` (agents may run `origin ruleset list|view` to audit). Per private repo:

| Ruleset kind | Refs | Rules | Bypass |
|---|---|---|---|
| `merge_branch` | `~DEFAULT_BRANCH`, `develop`, `release/**` | `pull_request` (1 approval; code owners on `main` and `release/**`; merge methods `merge`, `squash`), `require_status_checks` (Buildkite `ci`), `require_branch_up_to_date` | Chris only |
| `push_branch` | same | `deletion`, `non_fast_forward`, `block_direct_updates` | Chris only |
| `push_tag` | `*-v*` | `deletion`, `non_fast_forward`, `ref_name_pattern` `^[a-z0-9-]+-v[0-9]+\.[0-9]+\.[0-9]+$`, `block_direct_updates` (no one but the bypass actor can create a release tag) | Chris only |

- Per-package release branches `release/<component>` (R2–R6) are now protected for real.
- Not available on Origin today: dismiss stale reviews, last-push approval, required thread
  resolution, signed tags. The optional signed-tag step (D-G6) covers the last one only when used.
- Agents use Chris's account (D-O4), and Chris is the bypass actor, so these rulesets are
  **advisory** for agents: they document intent and stop accidents, nothing more. Seat instructions
  still forbid agents from pushing to `main`/`release/*` and from creating release tags.
- Rulesets are proven on a scratch repo in P2 before any real repo depends on them: Chris checks the
  applied config with `origin ruleset view`, and a direct push to `develop` without bypass is refused
  (tested by Chris with bypass switched off for the test, then switched back on).

---

## P0 — Prepare (day 0–2)

Goal: know everything that deploys from mono, and get the Mac runner and the optional signing key ready.
Mono stays public (D-G2); its `production` environment and required reviewers keep working.

1. Inventory (read-only):
   - `gh api repos/digithings-ai/digithings/environments`, `.../rulesets`, `.../actions/secrets`, `.../actions/variables` → saved to the issue (names only, never values).
   - Cloudflare: list Workers, Pages projects, custom domains, routes, KV namespaces, R2 buckets, and which repo/workflow deploys each (reconciles review G1, incl. `corpus-index`).
   - `gitleaks detect --log-opts="--all"` on a mirror clone → list of secrets ever committed (rotate any hits in P1).
   - Fetch each existing fork; `git log --all -- <private paths>` on each → record what it holds (result on the issue only).
2. Remove `push` triggers from `deploy-digiquant-runner` / `deploy-digithings-cron` (dispatch only), in a PR into `develop`.
3. Runner host (D-G5, answered): no separate host. Chris runs the Buildkite `ci` and `deploy`
   agents on his Mac under his normal user. DevOps installs the agent software but does **not**
   register the `deploy` queue yet (registration happens per private repo in P2/P4). The full
   local-runner design (isolation, cache, concurrency, keep-awake, Worker fallback) is DIG-3561's
   deliverable; this step tracks only install + registration readiness.
4. Signing key (D-G6, optional): only if Chris adopts it. Chris creates an `ed25519-sk` SSH signing
   key on a FIDO2 key. Only the **public** key goes into `allowed_signers` (committed in each private
   repo and installed on the Mac). Unsigned release tags still deploy; signed ones verify when present.
5. Origin (D-O1 … D-O5, answered): Chris confirms the namespace and the repo names (permanent during beta),
   and creates the Buildkite organization and connects Origin (D-O3). No agent account (D-O4). Agents do no logins. Nobody installs the Cloudflare app in Cursor.

Exit check: inventory posted; deploy workflows show `workflow_dispatch` only; Mac agent reachable
by Chris; if the signing key is adopted, `git tag -s` + `git verify-tag` round-trip works with the new key on a scratch repo.

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
| 1.9 | Deploy workflows for every Worker (stack, digichat, langfuse, cron, runner, dashboard-api, corpus-index, digidata-api) — tag/dispatch-triggered, clean checkout, written so the same file runs either on GitHub-hosted with `environment: production` (mono while public) or on the Mac `deploy` queue without an environment (private repos). Retire manual `wrangler deploy`; `occ_invite_key_rollout.sh` split into "write secret/KV" (R6) and "deploy" (R5). | R5, R6 | M |
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
6. **Deploy gate on the Mac agent (D-G5 + D-G6)** — replaces protected `release/*` + environment reviewers:
   - Deploy credentials (scoped Cloudflare tokens, Supabase access token) live only on Chris's
     Mac, in a root-owned file read by the agent service, plus the Worker fallback. Not in GitHub secrets.
   - Gate script `scripts/split/runner/deploy-gate.sh` (versioned in R5, installed on the Mac by Chris)
     exits non-zero unless:
     1. the repo is in the host's repo allowlist (private repos only);
     2. the ref is `refs/tags/<component>-v*` (push or dispatch on that tag);
     3. the tag's commit matches the built commit;
     4. the workflow file is read from the same tagged commit.
     Optional 5th check (D-G6, only when adopted and the tag carries a signature): `git verify-tag`
     passes against the host's `allowed_signers` (Chris's `ed25519-sk` key only).
   - Tags are cut only by Chris (on a `release/*` or `main` commit; signing optional/recommended).
     Agents may prepare the release PR and changelog, never the tag.
   - CI agents (no credentials) run queue `ci` on the same Mac; the `deploy` queue refuses every job
     that is not a release-tag deploy. Local-runner tuning (concurrency, cache, keep-awake) is DIG-3561's.
   - Prove the gate on R7 (already private) with a no-op deploy job: foreign repo → refused; non-tag
     ref → refused; Chris-cut tag → runs; and, if signing is adopted, unsigned/agent-signed tag → refused.
     Without signing, the control is procedural: only Chris cuts release tags (seat instructions forbid
     agents; audit log records every tag).
7. **Repository settings as code:** `scripts/split/rulesets/` holds the full ruleset template
   (`develop` PR + checks + DCO; `main`/`release/*` code-owner review; tag creation limits). Applied
   now to R0 (public). Kept unapplied for private repos until a Team upgrade.

8. **Origin plumbing (scratch repo `<ns>/split-gate-test`):** Buildkite pipeline with `ci` and
   `deploy` queues; the gate hook with the Buildkite adapter (§5 of the Origin section); the three
   rulesets of §7 applied and tested; merge queue and run-watch ported off `gh`; a Paperclip project
   bound to the Origin URL. R1's git pin becomes `git+https://origin.cursor.com/<ns>/digiquant-strategies.git@v0.1.0`;
   `@digiquant/contract` becomes a git dependency on an R2 tag (no GitHub Packages from Origin, D-Q7′);
   Docker builds read both with a short-lived Origin token passed as a BuildKit secret.

Exit check: a dry-run release of one module (TestPyPI) and one npm package (`--dry-run`) green from mono;
R7 gate test above passes; the same cases pass on the Origin scratch repo via
Buildkite. Note (D-O4 + D-G6 optional): with agents on Chris's account and signing optional,
neither the rulesets nor the tag gate is a hard control — the control is procedural (only Chris
cuts release tags).

---

## P3 — Cutover: R0 public, mono private (1 day + 2 days watch)

Gate: **D-12′** (fresh repo — answered), **D-G3** (public allowlist), **D-G5/D-G6** (answered; gate proven in P2), P1 exit check passed.
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
6. Mono deploys switch to the gate: merge the prepared PR that points mono's deploy jobs at the Mac `deploy` queue and drops `environment: production`.
7. Rename `digithings` → `digithings-mono`; make it **private**. Register the Mac agent on it (now allowed: private). Disable the gate allowlist entry for any public repo.
8. Rename `digithings-next` → `digithings`; make it **public**. Apply rulesets from P2 step 7; install DCO; add CODEOWNERS, LICENSE (MIT), TRADEMARKS, SECURITY; `production`-style environment `pypi` with Chris as required reviewer.
8b. Origin for R0 (D-O1): Chris runs `origin repo create-mirrored` for the public R0 (inbound mirror).
9. Publish v0.x of PyPI modules and `@digithings/*` npm, and GHCR `digichat` / `digillm` images, from R0.
10. In mono: R0 paths frozen (`moved-paths-guard` lists them). Development on public code moves to R0. Open mono PRs that touch only R0 paths are re-opened against R0 by their owners (list posted on the tracking issue).
11. Update every remote: `~/Code/digithings*` worktrees, Paperclip project repositories, merge queue config, run-watch, worktree sweep, seat instructions that name the repo.

Exit checks:
- anonymous `curl -s -o /dev/null -w '%{http_code}' https://github.com/digithings-ai/digithings-mono` → 404;
- anonymous clone of `digithings-ai/digithings` gives R0 history only (first commit is the export, not mono's);
- one Chris-cut deploy from mono via the Mac agent succeeds; a non-tag ref is refused (and, if signing is adopted, an unsigned tag is refused);
- packages install from PyPI/npm in a clean container; denylist grep on the *pushed* repo = 0.

Rollback before step 8: rename back and make mono public again (nothing lost).
After step 8: delete or re-private R0 and yank packages. Point of no return: the first
`pip install`/`npm install` by an outsider — after that, treat what was pushed as published.

---

## P4 — Extract the private repos (one repo per step, ≈1–2 days each)

Common recipe for every target Rn:
1. `git clone --mirror` mono → `git filter-repo --paths-from-file rN.paths --path-rename …`.
2. `gitleaks` + boundary check on the new repo; Chris creates `<ns>/Rn` on Origin (private); push `main`, `develop`, release tags; commit `allowed_signers`, CODEOWNERS, LICENSE (proprietary); Chris applies the Origin rulesets (§7).
3. Switch imports to published R0 packages (pins); add `.buildkite/pipeline.yml` (queue `ci`); install the Origin App (replaces the GitHub App for bump PRs); add Rn to the gate allowlist. Non-deploy CI values are Buildkite secrets set by Chris or DevOps (never pasted into issues). Deploy credentials stay on Chris's Mac (plus Worker fallback). (R7: see Origin §3 for the history move.)
4. **Cut-over deploy** from a Chris-cut release tag — one deploy per target, verified (below).
5. Add Rn's paths to mono's `moved-paths-guard`; delete them from mono in one PR.
6. Update Paperclip project binding, merge queue, run-watch, CODEOWNERS, seat instructions for Rn.

Validation and rollback per target:

| Step | Repo | Cut-over and validation | Rollback |
|---|---|---|---|
| 4.1 | R6 digichat-tenants | `kv-sync` writes `TENANT_CONFIG` + seeds to staging namespace, then prod; tenant chat answers from KV (answer-check workflow green for each tenant); stack fallback serves only `digithings`. | Re-run `kv-sync` from previous tag (KV values are versioned by tag). |
| 4.2 | R1 digiquant-strategies | Tag `v0.1.0`; `pip install` from git tag in a clean container; plugin discovered by R0 `digiquant` (entry points list); backtest suite green; conformance test green. | R2 keeps pinning mono-built runner image until 4.3. |
| 4.3 | R2 digiquant-stack | Runner image built from pins (R0 PyPI + R1 git tag) deployed; one full pipeline run produces its outputs (compare row counts / artifacts with the previous mono run); dashboard-api deployed as own Worker; desk reads through it; `supabase db push` dry-run shows no diff. | `wrangler rollback` to previous Worker version; previous runner image tag. |
| 4.4 | R5 digithings-stack | stack, digichat, langfuse, cron, corpus-index each deployed once from a Chris-cut `stack-v*` tag; health checks on all routes listed in the proposal; cron dispatches R2/R7 workflows with the App token; tenant chat smoke per tenant. | `wrangler rollback` per Worker; cron rollback restores old dispatch targets. |
| 4.5 | R3 digiquant-web | New Pages project `digiquant-io-r3` direct-uploaded by the Mac agent from a Chris-cut `web-v*` tag; preview checked against R2; move custom domain `digiquant.io`. Old project's Git builds disabled (production branch set to an unused name). | Move domain back to old project (minutes). |
| 4.6 | R4 digithings-web | Same as R3 for `digithings.ai`; routes to R5 (`/api/*`, `/embed*`) checked. | Move domain back. |
| 4.7 | R7 twelve-x | twelve-x desk surface + `digidata-api` moved; desk gate/palette in R3 made pluggable first (D-X1). No client-contract gate (D-O5). | Revert PRs in R3/R7; previous digidata-api version. |

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
4. Remove mono from the gate allowlist; unregister its Mac agent queues for mono (the Mac then runs only R1–R7 agents).
5. Archive `digithings-mono` on GitHub (already private since P3; read-only). Keep it: it is the full-history audit trail and the rollback source.
6. Chris deletes the old Origin mirror of mono in his personal namespace (it holds the full public history).

---

## P6 — Docs, tooling and seat sweep (runs alongside P3–P5)

| Where | What to update |
|---|---|
| R0 `README.md`, `CONTRIBUTING.md`, `docs/DEPLOYMENT.md`, `docs/BRANCH_PROTECTION.md`, `docs/MERGE_QUEUE.md`, `docs/LICENSING.md`, `docs/SELF_HOST.md`, `docs/LOCAL_STACK.md` | Remove production deploy content (moves to R5/R2 runbooks); release model (tags + release-please); new repo map (public-safe version). |
| R5 runbook | Deploy gate: Mac agent host, hook, `allowed_signers` rotation (if adopted), how Chris cuts a release tag (signing optional), how to add a repo to the allowlist. |
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
All gate decisions are answered (2026-10-14, including D-G5/D-G6), so the CTO can create the leaves.
D-O1 … D-O5 are answered. Note: with D-O4 + D-G6-optional, no private repo has a hard technical deploy
control — the control is procedural until Chris adopts signing.
