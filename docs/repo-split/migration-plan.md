# Repo split: phased migration plan

Companion to [review.md](review.md) (verdict: MODIFY). Target topology is the proposal's
8 repos unchanged; this plan changes how we get there. Decisions referenced as `D-*` are in
[decisions.md](decisions.md).

**Revised 2026-10-14 after Chris's gate answers:** org stays on GitHub **Free** (D-G1 = no); mono
stays **public until cutover** (D-G2 = no); R0 is a **fresh repo** (D-12′); R0 releases by **tags**
(D-R3); private repos use **self-hosted runners** (D-G4). Answered 2026-10-14 17:40 CEST:
deploys + CI run on Chris's Mac under his normal user with a Cloudflare Worker fallback
(D-G5); signed release tags are MANDATORY (D-G6).

**Revised again 2026-10-14 (Chris's direction):** R1–R7 move to **Cursor Origin**, not to GitHub.
See [Source control on Cursor Origin](#source-control-on-cursor-origin). D-O1 … D-O5 answered 2026-10-14.

**Revised again 2026-10-14 22:09 (Chris, TOP PRIORITY, released):** GitHub Actions minutes are
exhausted, so **migration off GitHub comes first**: local Mac CI + Cloudflare Worker fallback +
Cursor Origin readiness move ahead of extraction. Missing GitHub Actions checks are **not**
failures; every PR records its local test pass in the PR body instead. Docs/code PRs into
`develop` via feature branch stay fine. Hard limits stand: no Origin/GitHub repo creation, no
history push, no Cloudflare config changes, no `main` merges, no production deploys — anything
needing those goes to Chris as a decision. Slices A–N, P are folded in
[Consolidated corrections](#consolidated-corrections-from-slices-an-p-dig-3573-2026-10-14);
open inputs (no draft yet: A, K, L, M, N) are listed there, not invented.

**Revised again 2026-10-14 23:18 (Chris, send-back, released):** R0 stays on GitHub, inbound
Origin mirror only. **Detach is forbidden for R0**, and **no twelve-x detach is scheduled
(P4.7 struck)**. Only the R0 public repo stays on GitHub; moving CI and crons off GitHub stays
top priority (local-ci, Cloudflare crons) — the suggestion to keep GitHub primary until 1 Nov
was NOT taken.

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
signing the tag is MANDATORY (D-G6).

## Constraints from GitHub Free

| Repo state | Branch protection / rulesets | Environments + required reviewers | Runner |
|---|---|---|---|
| Public (mono until P3, R0 after) | yes | yes | GitHub-hosted only (free minutes). **Never** a self-hosted runner: fork PRs could run code on it. |
| Private (R1–R7, mono after P3) | **no** | **no** (no environment secrets either) | Self-hosted (D-G4); 2,000 hosted min/month as overflow. |

Consequences:
- The human release gate for private repos cannot live on GitHub. It moves to the **deploy
  agent on Chris's Mac** (D-G5): local-ci `deploy` job runs there under his normal user,
  deploy credentials exist only there (plus the Worker fallback), and the gate hook refuses
  any job that is not on a release tag cut by Chris — with a mandatory `git verify-tag` (D-G6)
  signature check (D-G6: verify-tag always runs; unsigned tags are refused).
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
| R7 `twelve-x` | stays as-is (call (c)) | private | **ON HOLD 01:26** — no move until Chris rules whether the twelve-x desk moves. PR #5722 on hold. See §3. |
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

### 3. twelve-x — STRUCK 2026-10-14 23:18 (Chris)

No twelve-x detach is scheduled and P4.7 is struck: `chrizefan/twelve-x` is already a private
inbound mirror (Matrix finding 9, live since the 2026-08-18 initial sync), and Chris forbids any
detach. twelve-x stays as-is (GitHub private + existing inbound mirror). **Call (c) 01:26: R7 / PR #5722 ON HOLD until Chris rules whether the twelve-x desk moves.** The R7 twelve-x-path move
(desk surface + `digidata-api`) is undecided — it needs a new ruling, not this section. A later
"move" would be a detach or a gated outbound transition, never a first create.

### 4. CI on Origin (local-ci)

- GitHub Actions does **not** run on Origin pushes. The runner is **local-ci on Chris's Mac** (DIG-3561 dispatcher design + N §5: one launchd job, 2 concurrent / 1 heavy, ephemeral job dirs; plain `git clone` with a short-lived token for checkout).
- Rulesets that must hold are **`active`, never `evaluate`.

*Historical note (01:26): Buildkite was the D-O3 answer (Origin provider, self-hosted agents, `clone-fast` checkout, `.buildkite/` pipelines, `BUILDKITE_*` gate vars and token). Struck 23:18/23:36 — the runner is local-ci throughout, and no Buildkite org, pipeline, token, or adapter remains in any live step.*
  The agent identity is **not** a bypass actor: no agent seat holds bypass, so an `active` ruleset
  binds agents too. **Signed tags are mandatory before any private-repo deploy** (D-G6 now
  mandatory): the local-ci gate runs `git verify-tag` against `allowed_signers` on every release
  tag, and an unsigned tag is refused. (Origin has no signed-tag rule type — Matrix; the check
  lives in local-ci, which is also why it cannot be skipped.)
- Workflows in `.github/workflows/` of R1–R7 are rewritten as local-ci jobs (local-ci job matrix). The P1.9 deploy workflows are plain scripts (`scripts/deploy/<target>.sh`) so the same
  script runs from GitHub Actions (mono, interim) and from local-ci (R1–R7).
- Scheduled jobs that `digithings-cron` dispatches through the GitHub API move to the local-ci
  trigger API (D-R5-6; token on Chris's Mac, scoped to the pipelines it triggers).
- Anything that must run while the Mac is off goes to a Cloudflare cron/Workflow; Mac-only
  triggers fail visibly.
- Public CI (R0) stays on GitHub-hosted runners while minutes last (D-O1); a missing Actions check
  is not a failure — the local test pass in the PR body is the record.

### 5. Cloudflare deploys after the move

- **Do not install the Cloudflare app in Cursor** and do not connect any Worker or Pages project to an
  Origin repo through Workers Builds: that integration auto-deploys on every push.
- Deploys run only on the `deploy` queue (Chris's Mac, Worker fallback), from a release tag
  cut by Chris (D-G5; signing MANDATORY per D-G6), with `wrangler deploy` / Pages direct upload.
  The gate hook is the same script as before with a local-ci adapter: it checks the repo
  against the allowlist, the tag matches `<component>-v*`, the tag's commit equals the
  built commit, and `git verify-tag` passes against `allowed_signers` on every release tag
  (D-G6 mandatory — an unsigned tag is refused). The pipeline step that deploys is read from the tagged commit, not from a later upload.
- Origin `repository pushed` webhooks are **not** wired to any deploy.
- Existing Git-connected Pages projects (on mono) are handled as before (P4.5, P4.6, P5): new
  direct-upload projects, then the domain moves.

### 6. Paperclip agents and worktrees

- Agents run as Chris's macOS user. Git on this Mac already reaches Origin through Chris's
  credential helper. **Chris** does every login (`origin auth login` or `origin ssh-key add`);
  agents never log in and never handle a token.
- Identity (D-O4, answered): agents **keep using Chris's account** through his existing credential
  helper. There is no separate agent account. Binding `active` rulesets carry no agent bypass,
  and D-G6 is MANDATORY: local-ci `verify-tag` refuses unsigned tags. Agents must never cut release
  tags. The hard controls are `active` rulesets plus mandatory tag verification.
- Worktrees: no change in how they work (`git worktree add` from an Origin clone). Remote convention:
  `origin` = Origin, `github` = GitHub (R0 only). `dt-dev` bootstrap clones R1–R7 from Origin.
- Tooling that calls `gh` must be ported before the first private repo moves (P2): merge queue
  (`origin pr` / Origin API, `merge_when_ready`), run-watch (local-ci trigger API), worktree sweep, PR-ownership
  checks. Paperclip project ↔ repo bindings use the Origin URL. Whether Paperclip's repository
  binding accepts a non-GitHub remote is UNSURE; checked in P2 on a scratch repo.

### 7. Branch protection and per-package release branches

Rulesets live as code in `scripts/split/rulesets/origin/` and are applied by Chris with
`origin api` (agents may run `origin ruleset list|view` to audit). Per private repo:

| Ruleset kind | Refs | Rules | Bypass |
|---|---|---|---|
| `merge_branch` | `~DEFAULT_BRANCH`, `develop`, `release/**` | `pull_request` (1 approval; code owners on `main` and `release/**`; merge methods `merge`, `squash`), `require_status_checks` (local-ci), `require_branch_up_to_date` | Chris only |
| `push_branch` | same | `deletion`, `non_fast_forward`, `block_direct_updates` | Chris only |
| `push_tag` | `*-v*` | `deletion`, `non_fast_forward`, `ref_name_pattern` `^[a-z0-9-]+-v[0-9]+\.[0-9]+\.[0-9]+$`, `block_direct_updates` (no one but the bypass actor can create a release tag) | Chris only |

- Per-package release branches `release/<component>` (R2–R6) are now protected for real.
- Not available on Origin today: dismiss stale reviews, last-push approval, required thread
  resolution, signed tags. The mandatory signed-tag gate (D-G6) is enforced in local-ci `verify-tag`, since Origin has no signed-tag rule type.
- 23:18: the "advisory" reading is struck. Rulesets that must hold are **`active`**; the agent
  identity is **not** a bypass actor (no agent seat holds bypass). Seat instructions still forbid
  agents from pushing to `main`/`release/*` and from creating release tags — and now an `active`
  ruleset enforces it too. Chris alone holds bypass.
- Rulesets are proven on a scratch repo in P2 before any real repo depends on them: Chris checks the
  applied config with `origin ruleset view`, and a direct push to `develop` without bypass is refused
  (tested by Chris with bypass switched off for the test, then switched back on).

---

## P0 — Prepare (day 0–2)

Goal: know everything that deploys from mono, and get the Mac runner and the mandatory signing key ready.
Mono stays public (D-G2); its `production` environment and required reviewers keep working.

1. Inventory (read-only):
   - `gh api repos/digithings-ai/digithings/environments`, `.../rulesets`, `.../actions/secrets`, `.../actions/variables` → saved to the issue (names only, never values).
   - Cloudflare: list Workers, Pages projects, custom domains, routes, KV namespaces, R2 buckets, and which repo/workflow deploys each (reconciles review G1, incl. `corpus-index`).
   - `gitleaks detect --log-opts="--all"` on a mirror clone → list of secrets ever committed (rotate any hits in P1).
   - Fetch each existing fork; `git log --all -- <private paths>` on each → record what it holds (result on the issue only).
2. Remove `push` triggers from `deploy-digiquant-runner` / `deploy-digithings-cron` (dispatch only), in a PR into `develop`.
3. Runner host (D-G5, answered): no separate host. Chris runs the local-ci dispatcher
   (`com.digithings.ci-dispatch`, `ci` + `deploy` jobs) on his Mac under his normal user.
   The `deploy` job stays disarmed until P2/P4 arm it per private repo. The full
   local-runner design (isolation, cache, concurrency, keep-awake, Worker fallback) is DIG-3561's
   deliverable; this step tracks only install + readiness.
4. Signing key (D-G6, MANDATORY since 23:18): Chris creates an `ed25519-sk` SSH signing
   key on a FIDO2 key. Only the **public** key goes into `allowed_signers` (committed in each private
   repo and installed on the Mac). Unsigned release tags are refused by the local-ci gate.
5. Origin (D-O1, D-O2, D-O4, D-O5 answered; D-O3 STRUCK 23:36): Chris confirms the namespace and the repo names (permanent during beta).
Local-ci needs no Origin connect and no Buildkite org exists. No agent account (D-O4). Agents do no logins. Nobody installs the Cloudflare app in Cursor.

Exit check: inventory posted; deploy workflows show `workflow_dispatch` only; Mac agent reachable
by Chris; once the signing key is in place, `git tag -s` + `git verify-tag` round-trip works with the new key on a scratch repo.

2026-10-14 22:09 ordering note: the Mac CI dispatcher design (DIG-3561), the Origin checks-API
verification (DIG-3558, slice A) and the R0 mirror-lag watch (DIG-3560, slice C) are P0 work and
land before any extraction. Under the no-GitHub-services direction, R2/R5 deploy workflows become
local-ci/cron jobs at extraction (slices D/I notes); P0 step 2 (dispatch-only) is the interim only.

Rollback: nothing irreversible in this phase.

---

## P1 — Decouple inside mono (≈1–2 weeks, the bulk of the work)

All of the proposal's §1 refactors, as normal PRs into `develop`, **no moves yet**. Ordered so
each PR is independently shippable. Lane in brackets (operating rules).

| # | Change | Unblocks | Lane |
|---|---|---|---|
| 1.1 (DIG-3690) | Path manifest script `scripts/split/manifest.py`: maps every tracked path to exactly one of R0–R7/delete; CI fails on unassigned paths. Pinned-SHA output stored as an artifact. | all | S |
| 1.2 (DIG-3691) | `digiquant.plugin` surface + entry-point discovery (`digiquant.strategies`, `digiquant.mcp_tools`, `digiquant.cli`); private strategies, SDCA MCP, optimiser, SDCA charts and CLI subcommands register through it; dummy-plugin conformance test. | R1 | M |
| 1.3 (DIG-3692) | `DIGIQUANT_CONFIG_DIR` + neutral example configs; production config only read via the env var. | R2 | S |
| 1.4 (DIG-3693) | Unfold `dashboard-api` into its own Worker again; route `/dashboard-api/*` by zone route (D-Q2′); extract `@digiquant/contract` (types + pure functions shared by desk and API). | R2, R3 | M |
| 1.5 (DIG-3694) | Supabase layering (D-Q6′): split migrations into `engine/` (tables the open pipeline reads/writes) and `prod/` (house-only); CI applies both in order on a scratch DB. | R0/R2 | M |
| 1.6 (DIG-3695) | npm packages: tsup builds, `exports` maps, `private: false`, `license: MIT`; PixelWordmark → `@digithings-ai/ui`; `@digithings-ai/catalog` (byok-providers + openapi); apps import only via package exports (lint rule bans `../../packages/*/src`). | R3, R4 | M |
| 1.7 (DIG-3699) | Tenant data out of code: `TENANT_CONFIG` KV read path with `digithings`-only fallback; seeds fetched from R2 at container boot; suggestion pools/looks from KV; production model list from KV/env. **Call (b) 01:26: tenant configs live in KV ONLY — no repo files synced to KV (no `kv-sync` from repo files).** Prove on staging tenant first. | R5, R6 | M |
| 1.8 (DIG-3696) | Dockerfiles consume packages/images, not sibling paths (runner, stack, digichat). | R2, R5 | M |
| 1.9 (DIG-3697) | Deploy workflows for every Worker (stack, digichat, langfuse, cron, runner, dashboard-api, corpus-index, digidata-api) — tag/dispatch-triggered, clean checkout, **local-ci only (call 01:26: no "same file runs on GitHub-hosted" — deploy jobs run on the Mac `deploy` job without an environment).** Retire manual `wrangler deploy`; `occ_invite_key_rollout.sh` split into "write secret/KV" (R6) and "deploy" (R5). | R5, R6 | M |
| 1.10 (DIG-3698) | Rotate any secret found by P0 gitleaks; move deploy tokens to per-target scoped Cloudflare tokens. | all | S |
| 1.11 (DIG-3700) | Guard workflow `moved-paths-guard`: fails a PR touching a path whose manifest destination is already extracted (populated in P4). | P4 | S |
| 1.12 (DIG-3689) | R0 client-name scrub before D-12′: remove client-identifying names/paths from the R0 allowlist so the fresh public repo never carries them. | R0 | S |

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
2. **npm:** D-P2 SATISFIED 02:18 — Chris owns the `digithings-ai` npm org. Publish `@digithings-ai/*` from R0 only, after P3; nothing is published until he provides a token.
3. **Private Python (R1):** no GitHub Packages for Python (review F2). Use a git tag pin:
   `digiquant-strategies` from an Origin tag (`git+https://origin.cursor.com/<ns>/digiquant-strategies.git@v0.1.0`) locked by SHA in `uv.lock`;
   R2's Docker build reads it with a GitHub App installation token passed as a BuildKit secret (D-Q7).
   2026-10-14 22:09: **no GitHub Packages at all** (slices E/P notes) — R2 consumes R1 from a
   non-GitHub registry (private PyPI index on Chris's Mac, Origin artifacts, or vendored path pin;
   decision outstanding, owned by R2/epic owner), read with a short-lived Origin token as a BuildKit secret.
4. **Private npm (`@digiquant/contract`):** GitHub Packages npm from R2; R3's Actions reads it with `GITHUB_TOKEN` after granting R3 access on the package.
   the contract reaches R3 from a non-GitHub registry (decision c7256004 Option A);
   no `.github/workflows` additions in R3 (local-ci instead).
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
     5th check (D-G6 MANDATORY): `git verify-tag` passes against the host's `allowed_signers` (Chris's `ed25519-sk` key only); unsigned tags refused.
   - Tags are cut only by Chris (on a `release/*` or `main` commit; signing MANDATORY).
     Agents may prepare the release PR and changelog, never the tag.
   - CI agents (no credentials) run queue `ci` on the same Mac; the `deploy` queue refuses every job
     that is not a release-tag deploy. Local-runner tuning (concurrency, cache, keep-awake) is DIG-3561's.
   - Prove the gate on R7 (already private) with a no-op deploy job: foreign repo → refused; non-tag
     ref → refused; Chris-cut tag → runs; unsigned/agent-signed tag → refused by the gate.
     Only Chris cuts release tags (seat instructions forbid
     agents; audit log records every tag) — defence in depth behind the gate.
7. **Repository settings as code:** `scripts/split/rulesets/` holds the full ruleset template
   (`develop` PR + checks + DCO; `main`/`release/*` code-owner review; tag creation limits). Applied
   now to R0 (public). Kept unapplied for private repos until a Team upgrade.

8. **Origin plumbing (scratch repo `<ns>/split-gate-test`):** local-ci `ci` + `deploy` jobs;
   the gate hook with the local-ci adapter (§5 of the Origin section); the three
   rulesets of §7 applied as `active` and tested; merge queue and run-watch ported off `gh`; a Paperclip project
   bound to the Origin URL. R1's git pin becomes `git+https://origin.cursor.com/<ns>/digiquant-strategies.git@v0.1.0`;
   `@digiquant/contract` becomes a git dependency on an R2 tag (no GitHub Packages from Origin, D-Q7′);
   Docker builds read both with a short-lived Origin token passed as a BuildKit secret.

Exit check: a dry-run release of one module (TestPyPI) and one npm package (`--dry-run`) green from mono;
R7 gate test above passes; the same cases pass on the Origin scratch repo via
local-ci. Note (23:36): binding rulesets are `active` with no agent bypass, and the tag gate is
mandatory — both are hard controls; only-Chris-cuts-tags remains as defence in depth.

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
9. Publish v0.x of PyPI modules and `@digithings-ai/*` npm, and `digichat` / `digillm` images, from R0.
   Images are NOT covered by c7256004 — the image registry is OPEN in R5 (recommendation: Cloudflare registry, not DataTap ACR); `@digithings-ai/*` per decision c7256004 Option A.
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
3. Switch imports to published R0 packages (pins); add the repo to the local-ci job matrix (local-ci job matrix); install the Origin App (replaces the GitHub App for bump PRs); add Rn to the gate allowlist. Non-deploy CI values are local-ci secrets set by Chris or DevOps (never pasted into issues). Deploy credentials stay on Chris's Mac (plus Worker fallback). (R7: see Origin §3 for the history move.)
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
| 4.7 | R7 twelve-x — STRUCK 23:18 | No detach scheduled; twelve-x stays as-is. The desk-surface move is undecided (needs a new ruling). | n/a (struck). |

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
| R5 runbook | Deploy gate: Mac local-ci host, hook, `allowed_signers` rotation, how Chris cuts a release tag (signing MANDATORY, D-G6), how to add a repo to the allowlist. |
| openwiki | Per-module pages: install from PyPI/npm instead of monorepo paths; `openwiki/dashboard` → R3; `INSTRUCTIONS.md` repo map. |
| digibook (R4 `content/book`) | System-architecture chapter: repo map and release flow; "how the book is built" (now R4 + R0 docs pulled at build). |
| docs site (digithings.ai docs, openapi catalog) | Source openapi + byok catalog from `@digithings-ai/catalog`; links to R0 instead of mono paths. |
| `docs/repo-split/` (this folder) | Mark phases done; final repo map. |
| Paperclip | Projects ↔ repos, `dt-create-issue --project` mapping, merge queue repo list, worktree sweep, run-watch job → repo map, decisions/standing.md entry for the split. |
| Seat instructions and skills | Replace monorepo paths and the single-repo assumption; per-repo branch rules; agents never create release tags. |
| `~/Code` layout | `dt-dev` bootstrap: clones R0–R7 side by side, `uv`/npm overlays for local cross-repo work. |

---

## Consolidated corrections from slices A–N, P (DIG-3573, 2026-10-14)

**23:18 correction (Chris): no CI fallback exists today.** A dark Mac blocks merges — there is no
second runner to take over. The Cloudflare Worker fallback is a **design only** (DIG-3561 §8,
partial checks, never a full pass), and **Workers Builds auto-deploy on push is not allowed**
(never connect it to an Origin repo). Any plan text suggesting otherwise is superseded by this
paragraph.

Slice sources: B (DIG-3559), C (DIG-3560), D (DIG-3561), E (DIG-3562), F (DIG-3563),
G (DIG-3564), H (DIG-3565), I (DIG-3566), J (DIG-3567), P (DIG-3572) — each stored as the
`plan` document on its issue. No draft yet (open inputs, §8): A (DIG-3558), K (DIG-3568),
L (DIG-3569), M (DIG-3570), N (DIG-3571). Nothing below invents their content.

### 1. Order: migration off GitHub first (Chris 22:09, released)

P0 now leads with three items before any extraction: (a) Mac CI dispatcher design (slice D:
one `com.digithings.ci-dispatch` launchd job, 2 concurrent / 1 heavy cap, ephemeral
`~/Code/ci-runs/<repo>/<run-id>/` job dirs, per-repo minimal job lists, Worker fallback
partial-only) — proposal, needs Chris D-CI2 (caps + disk home); (b) Origin checks/status-API
verification (slice A, open); (c) R0 mirror-lag watch (slice C proposal: hourly HEAD+tag SHA
compare, one `[run-watch] r0-mirror-lag` ticket on persistent mismatch). Missing GitHub Actions
checks are not failures; each PR carries its local test pass in its body.

### 2. Source control + mirror (slices B, C — confirm the plan)

Slice B fixes exact names: Origin namespace = Chris's existing personal namespace (measured
`origin` remote, not assumed); remotes `origin` = Origin, `github` = GitHub (R0 only); every repo
`main` + `develop`; R0/R1 no release branches (tags only), R2/R5 `release/stack`, R3/R4
`release/web`, R6 none, R7 as today; tag shape `^[a-z0-9-]+-v[0-9]+\.[0-9]+\.[0-9]+$`;
rulesets as code in `scripts/split/rulesets/origin/` (Chris applies; agents audit only);
token names only (P §7: `CURSOR_AUTH_TOKEN`, Origin App token, short-lived Origin token,
`GITHUB_TOKEN`, `GH_DISPATCH_TOKEN`, `CLOUDFLARE_API_TOKEN`,
`CLOUDFLARE_ACCOUNT_ID`, Supabase access token, Pages direct-upload token). Slice C confirms
§2 above (GitHub-primary R0, inbound mirror, no custom code) and adds: divergence policy
(GitHub wins; never force-push the mirror; never detach R0), R0 Actions = publish + CI only,
never the self-hosted runner on R0, never the Cloudflare Cursor app.

### 3. Inventory corrections (slices E–J)

- R1 (E): 58 strategy sources + SDCA-coupled modules + 44+ tests; entry points
  `digiquant.strategies` / `digiquant.mcp_tools` / `digiquant.cli`; `generate_tearsheets.py`
  may split R1/R2 if a production job.
- R2 (F): `apps/dashboard-api/` is **127 files, not 117**; `research/config/` is **18, not 19**;
  workflow is `sync-digiquant-runner-mail-secret**s**.yml` (plural); runner needs
  `byok-providers.json` + `model-policy.json`, **not** `digiquant_models.yaml` (CI-side input);
  `validate-providers.py:239` is a docstring, not a runtime load; two extra dashboard couplings
  (`brief/load.test.ts`, `lib/api-client.test.ts`); `RESEARCH_POLICY_PATH` already exists
  (new `DIGIQUANT_CONFIG_DIR` only for the other two paths); mount-test pins at
  `dashboard-api-mount.test.js:209-210`. Open: `byok-providers.json` owner (R2+R5 consumers),
  `config/contract/` + `compose-contract.env` + parity-baseline ownership,
  `deploy-digiquant-cloudflare.yml` home, 68 untriaged `research/` files.
- R3 (G): PixelWordmark + deploy-models copy + entrypoint imports rewired pre-extraction;
  **call (a) 01:26: R3 absorbs `apps/dashboard` (minus the R7 twelve-x paths); R2 absorbs the digiquant core pipeline (house pipeline, `execution/staging_secrets.py`, `vendor_secret_*`, gloomberb/luxalgo clients, `research/docs/RUNBOOK.md`, `config/contract/secrets.yaml`). Both are PRIVATE — the R0 definition excludes them.**
  `apps/digiquant-web/` moves to R3 root.
- R4 (H): 246 + brand 22 files; **PixelWordmark moves to shared UI/brand BEFORE extraction**
  (R3 imports it).
- R5 (I, rev 2, answers by Chris 2026-10-14T20:14:46Z): blocking Dockerfile findings F1–F4 as
  above; F5 answered **D-R5-1: R5 keeps producing, builds locally on the Mac, pushes to a
  non-client registry** (R5 send-back rule 02:06 — the client ACR is not the target; registry per
  decision c7256004 Option A); **D-R5-2: self-host-parity homes in R5, contract published
  from R0** (parity scripts are R5's; R0 inputs become a published artifact; publish precedes the
  gate); **D-R5-3: zammad_mcp private** (closes D-T2; credential at runtime only);
  **D-R5-4: delete both dead `pj()` rows** (`jobs.ts` L336/L376 — follow-up H1, not performed in
  the inventory ticket); **D-R5-5: one shared local-ci pipeline with a repo argument**
  (no per-repo copy; R2 globs become a second argument value); **new D-R5-6 (R5 send-back rule 02:06): anything that must run while the Mac is off goes to a
  Cloudflare cron/Workflow — Mac-only triggers fail visibly instead of silently; 12 twelve-x rows unverified).**
  Sequencing: steps 1–2 (local CI + registry; shared-closure artifacts) parallel, everything below
  step 3 waits on both; **step 9 (dispatch re-point) is what keeps the estate running — R5 can cut
  over before it, but the clocks stop when GHA retires without a Mac-off path — that path is a
  Cloudflare cron/Workflow per the send-back rule, never a Mac-only trigger.** Follow-ups H1–H6 routed
  (dead-row deletion; shared pipeline; registry move; dispatch re-point; parity publish; **F15:
  R0's digillm image lane + `docker-compose.yml` still name `ghcr.io` — must not be missed**).
  F6/F7/F8/F10/F11/F12 and the `docs/ops/` triage stand as inventoried.
- R6 (J): corpora + seeds + KV-seed config + rollout/answer-check tooling + new `kv-sync`; R0
  residue grep list before the R0 cleanup PR; D-12 scrub **after** KV write proven.
- No-GitHub-services (E/G/H/P notes, Chris 22:09): no GitHub Packages / GHCR / Actions
  dependence anywhere; registries per decision c7256004 Option A; workflows become local-ci/cron jobs.

### 4. Secrets (slice P — names only, no values)

On GitHub Free private repos have no secret storage, so every R1–R7 runtime secret lives on
the Mac `deploy` agent (root-owned file) and is pushed to Cloudflare as Worker secrets or
KV/R2 by tenant sync; repos hold names + wiring only. Per-repo name lists are slice P's
document; Keychain `digithings-local/*` entries never enter any repo.

### 5. Rollback (per phase, unchanged + two additions)

P0–P2: nothing irreversible. P3: before step 8 rename-back; after step 8 delete/re-privatise
R0 and yank packages. P4 per-target table above stands, plus: R0 mirror divergence → stop
writing via Origin, finish on GitHub, re-run `create-mirrored` (Chris); Pages domain moves
revert by moving the domain back (minutes); KV rollback re-runs `kv-sync` from the previous tag.

### 6. Chris-approval gates (each: doer + verify)

1. Namespace + eight repo names (permanent in beta) — Chris confirms; verify `origin repo list`.
2. Local-ci readiness — dispatcher installed, `ci` + disarmed `deploy` jobs present. — Chris; verify on the Mac.
3. Mac dispatcher caps + `~/Code/ci-runs/` home (D-CI2) — Chris; verify agent reachable + week-one re-measure.
4. Non-GitHub registries (PyPI/npm/images) — Chris; verify first publishes resolve off-GitHub.
5. D-R5-1 image direction; `byok-providers.json` owner; `config/contract` home — Chris; verify plan edit.
6. Every P4 cut-over deploy from a Chris-cut release tag; verify per-target validation receipt.
7. P3 cutover renames + visibility + `create-mirrored` — Chris; verify SHA-equality table.

### 7. Order gates (23:18, binding)

1. **DIG-3605 (crons and jobs off GHA) completes before DIG-3608** (disable-GHA-workflows).
   The 30-row dispatch re-point (D-R5-6) is what keeps the estate running once GHA retires.
2. **Section-1 refactors land on `develop` before any extraction or filter-repo push.**
   Extraction PR #5726 (slice L, open) is dry-run only until the boundary checks are green on
   `develop`.
3. **The fresh public repo (D-12′) waits until a KV read of tenant config is proven**
   (R6 `kv-sync` to staging, tenant chat answering from KV). No public history is cut before that.

### 8. Docs + openwiki updates (this slice)

This PR updates `docs/repo-split/` only. P6 table additions from the slices: R0 README/CONTRIBUTING
(state the non-GitHub registries + local-ci reporting once chosen); R5/R2 runbooks (Mac gate hook,
`allowed_signers` rotation, tag-cut procedure); openwiki per-module pages (install from registries,
`openwiki/dashboard` → R3); digibook architecture chapter (repo map + release flow); Paperclip
bindings + seat instructions (Origin URLs, `origin`/`github` remotes, agents never cut release tags).
`repo-split.md`/`CONTRIBUTING`/openwiki/digibook pages land per repo at extraction; the public-safe
repo map lands in R0 at P3.

### 9. Local-ci merge rule (23:18)

A swap or disk-guard skip in local-ci posts a **failure status, not nothing** — a skipped gate is
a red gate, so a dark-Mac-adjacent skip can never read as green. **Fork PR path:** fork heads are
not mirrored to Origin (Matrix finding 7) — external review and CI for fork PRs stay on GitHub;
local-ci never executes fork code. Local-ci gates, per repo job list: **pytest, actionlint,
compose-validate and the audits are gated**; anything not gated is listed explicitly as not gated
in the job matrix — a lane that reports "all local checks passed" without them is misreporting.

### 10. Slices A, L, N — drafts folded (correction: drafts exist)

- **A (DIG-3558, in_review): capability matrix** (`plan` doc, 13,522 chars). Folded findings:
  `internal` needs no Teams plan (live `chrizefan/digithings` is `internal`); live inbound mirror
  already carries `evaluate` rulesets (`active` untested); "advisory" fails as a product claim
  (enforcement can be `active`); outbound mirroring gated-off, do not plan a push mirror — detach
  is the documented path (but forbidden for R0, struck for twelve-x); GHA minutes exhausted
  (matrix finding 5, = 22:09); **CloneKit fails on Ultra** (plain clone + short-lived token);
  fork heads never mirror; local check posts need an app token and **403 on mirrors** (local PR-body
  record is the working path); no signed-tag rule type (local `verify-tag` only); no native runner;
  no package registry (git tag pins stand); **`chrizefan/twelve-x` already a private inbound
  mirror** (finding 9 — the fact behind striking P4.7).
- **L (DIG-3569, in_review): extraction scripts, PR #5726 open** into `develop`
  (branch `DIG-3569-repo-split-extraction-scripts` @ `7f18d256f`, +507/-0, signed). Dry run at
  `d227b6ed5`: R1 488/114, R2 1441/489, R3 333/231, R4 446/273, R5 842/185, R6 290/50, R7 90/122
  (commits/files); gates green (dry-run 7/7, overlaps 0 unlisted, bash -n, 7/7 extractions).
  R6/R7 regenerated from delivered inventories. R5/R6 double-claim on 10 files recorded, ruling
  owed. Dry-run only until order gate F4-2 clears.
- **N (DIG-3571, in_review): deploy map + local-ci wrangler design + auto-deploy-off-main
  proposal** (`plan` doc, 17,497 chars). Folded: 6 live Workers mapped to R2/R5 (+1 sourceless
  `corpus-index` worker — open D-1: recommendation R5); 2 Pages projects (names unverified — open
  D-2); dead lane `deploy-digiquant-runner.yml` (delete); no workflow deploys Pages; 2 Workers
  already Mac-deployed; local-ci `wrangler deploy` rule (build on Mac, dry-run gate first,
  `--var` not `--define`, Docker needed even for dry-run on container Workers); crons stay in
  Cloudflare (never edit `[triggers]`); auto-deploy-off-main steps (Pages production branch =
  dashboard session D-3; `release/web` must exist first). Open D-1…D-5 (owner, Pages names,
  dashboard actor, Mac always-on, repo names).

Still open inputs (no draft): K (DIG-3568), M (DIG-3570). Each lands as its issue's `plan`
document; this section absorbs them without reordering the phases.

### 11. Overlap resolution + global rule (01:26, binding)

Each file has exactly one owner. No `overlaps-known.txt` whitelist exists or is needed in this tree.

- **R1:** `digiquant/scripts/export_sdca_macro.py`, `digiquant/scripts/plot_sdca_tearsheet.py`, SDCA parts of `optimize.py` (`_run_sdca_optimize`, SDCA imports).
- **R2:** `digiquant/scripts/generate_tearsheets.py` (production job) after its SDCA imports (:66, :161-162) go through the plugin hook (refactor 1.2); generic `optimize.py` shell (private with the digiquant core, per call (a)).
- **R6:** `scripts/verify_occ_invite_key.sh`, `occ_invite_key_fixture_server.mjs`, `occ_invite_key_rollout.sh` (write-secret/KV half, per refactor 1.9 split), `check_occ_rollout_auth_guard.py`, `index_occ_tickets.py`, `test_occ_rollout_scope_guard.sh`, `docs/ops/OCC_INVITE_KEY.md`.
- **R5:** `apps/digithings-stack-cloudflare/container/seed_chroma.sh` (generic container infra; tenant seeds come from R2/KV at boot).

**Global rule (all repo-split leaves):** no `.github/workflows` file moves into any private repo. Each workflow maps to a Cloudflare cron, a local-ci job on Chris's Mac, or deletion — recorded in DIG-3605 (crons/jobs off GitHub). Move lists drop every `.github/*` path. No Buildkite, no GitHub Packages/GHCR; signed release tags mandatory for private-repo deploys; no merges to main, no deploys, no repo creation.

---

### 12. Order gate: develop→main promotion + repo cleanup before extraction (02:24)

The `develop`→`main` promotion and repo cleanup (PR pile closed or retargeted, stale branches and worktrees pruned) happen before any extraction. No filter-repo push runs while the PR pile is open.

---

## Tracking

One epic under G07 with one leaf per row of P1, one per P4 step, plus P0, P2, P3, P5, P6.
All gate decisions are answered (2026-10-14, including D-G5/D-G6), so the CTO can create the leaves.
D-O1 … D-O5 are answered. Note: with `active` rulesets (no agent bypass) + mandatory D-G6, every private repo will have hard technical deploy controls, once the P2 gate is proven.
