# Cloudflare v2 Phase 1 — Rename `frontend/` → `cloudflare/` (implementation spec)

- **Goal:** Rename the top-level directory `frontend/` to `cloudflare/` (it hosts Cloudflare Workers, Pages sites, Containers, cron — not just frontend code), updating every in-repo consumer so CI stays green on the rename commit itself.
- **Architecture:** Pure path rename. No behavior change, no dependency change, no wrangler binding/route/scaling change, no Pages project recreation. `git mv` preserves history; all references are rewritten `frontend/` → `cloudflare/` (word-boundary, see Task 3 caveats for `frontend_class_families.json` and prose matches like "research frontend regeneration").
- **Tech Stack:** git, GitHub Actions (dorny paths-filter via `scripts/ci_paths.yaml` + generated block in `ci.yml`), npm workspaces (root `package.json` + `package-lock.json`), Docker (root-context Dockerfiles), Next.js static export (`scripts/build-digithings.sh`, `scripts/build-digiquant.sh`), Cloudflare Workers/Pages/Containers (4 × `wrangler.toml`), Python guard scripts + pytest pin tests.
- **Spec:** self (this file). Spec only — no code changes were made while writing it. All line numbers below were read from the repo on 2026-09-10; re-verify with Task 1 commands before editing (line drift is expected).

## Global Constraints

- [ ] **Stay in-repo.** Work only inside `/Users/chrisstefan/Code/digithings`. Never touch sibling repos (`zeus`, `apollo`, etc.).
- [ ] **One commit for the whole rename** (`git mv` + all reference rewrites), so rollback is a single `git revert`. No stacking: nothing else lands on top until CI is green.
- [ ] **CI must be green on the rename commit before anything stacks on it.** That means the commit itself updates workflows, `ci_paths.yaml` + generated `ci.yml` block, build scripts, Dockerfiles, `package.json`/`package-lock.json`, `release-please-config.json`, guard scripts, pin tests, Makefile/compose, docs, and `ARCHITECTURE.md`.
- [ ] **Update docs + `ARCHITECTURE.md` refs in the same commit** (at minimum `ARCHITECTURE.md:548`, `AGENTS.md:71,132,387`, `docs/DEPLOYMENT.md`, `docs/LOCAL_STACK.md`, `ONBOARDING.md:215-217`, `BRANCHING.md:42`, `infra/*` READMEs, `docs/ops/*`, `frontend`-internal cross-refs). Bulk `sed` + `make doc-check` (Task 3.9).
- [ ] **Never touch `sleepAfter`/scaling.** `frontend/digithings-stack-cloudflare/src/index.ts` (`sleepAfter = "24h"`), `max_instances`, `instance_type`, `[triggers] crons`, routes, bindings, migrations are out of scope. The rename touches `wrangler.toml` *comments only* (image paths are relative `../../Dockerfile.*` and build context is repo root — unaffected).
- [ ] **Do not hand-edit `openwiki/`.** It is generated; let the scheduled `openwiki-update.yml` workflow regenerate after merge.
- [ ] **Cloudflare-dashboard changes are OWNER actions** (Task 5). The implementer lists them; only the owner clicks them.
- [ ] **Digi names stay lowercase** in any prose touched (`digithings`, `digichat`, …), per `AGENTS.md` naming rule.

---

## Task 0 — Pre-flight (branch + baseline)

- [ ] 0.1 Create the work branch from a current base (per `AGENTS.md` branching model; `frontend/`→`cloudflare/` is repo-level so it routes straight to `develop`):
  ```bash
  git fetch origin && git checkout -b chore/rename-frontend-to-cloudflare origin/develop && git status --short
  ```
- [ ] 0.2 Record the baseline: `git rev-parse --short HEAD` in the PR body, and confirm a clean tree (`git status --short` empty).
- [ ] 0.3 Confirm the full `frontend/` tree matches the inventory below (11 entries). If a 12th entry appeared since 2026-09-10, add it to Task 2 sequencing and to the Task 1 re-run:
  ```bash
  ls frontend/
  for d in frontend/*/; do echo "=== $d ==="; ls "$d"; done
  ```

### Verified `frontend/` tree (2026-09-10)

| # | Directory | Contents (top level) | Notes |
|---|-----------|----------------------|-------|
| 1 | `frontend/dashboard/` | app, components, lib, public, scripts, `package.json`, `next.config.mjs`, … | digiquant operator surface |
| 2 | `frontend/design/` | `assets/` (empty) | Keep dir (empty asset placeholder) — `git mv` it too so no stray `frontend/` remains |
| 3 | `frontend/digichat/` | Next.js BFF + `Dockerfile`, `drizzle/`, `scripts/trusted-proxy-server.mjs`, `ARCHITECTURE.md`, … | Has its own `Dockerfile` (internal `COPY` paths are relative — unaffected; only root-context Dockerfiles change) |
| 4 | `frontend/digichat-cloudflare/` | `src/`, `wrangler.toml`, `package.json`, `README.md` | Worker `digithings-digichat` |
| 5 | `frontend/digichat-ui/` | `src/`, `package.json`, `ARCHITECTURE.md` | Shared chat package |
| 6 | `frontend/digiquant-web/` | `app/`, `components/`, `public/`, `out/`, `package.json` | digiquant.io landing |
| 7 | `frontend/digithings-cron/` | `src/`, `wrangler.toml`, `package.json`, `README.md` | Worker `digithings-cron` |
| 8 | `frontend/digithings-stack-cloudflare/` | `container/`, `src/`, `wrangler.toml`, `package.json`, `README.md` | Worker `digithings-stack` |
| 9 | `frontend/digithings-web/` | `app/`, `components/`, `lib/`, `functions/`, `public/`, `out/`, `wrangler.toml` | digithings.ai Pages site |
| 10 | `frontend/digiweb/` | `brand/`, `design/`, `reference/`, `web/`, `scripts/`, `MANIFEST.json`, … | Design system + reference + `@digithings/web` |
| 11 | `frontend/web/` | `dist/` (build output: `components/`, `data/`, `ds-web.css`, `index.mjs`, `motion/`) | Build output — move with the tree, do not rebuild by hand |

---

## Task 1 — Exhaustive path-reference inventory (re-run, then diff against this baseline)

Re-run these exact commands on the work branch. Every hit must be dispositioned in Task 3 (load-bearing rewrite) or Task 3.9 (bulk docs/prose rewrite). Zero `frontend/` hits must remain afterwards except intentional historical prose (none planned — rewrite all).

- [ ] 1.1 Full-filename inventory (baseline 2026-09-10: **~345 path hits across ~280 files**; `openwiki/*` excluded — generated):
  ```bash
  rg -l "frontend/" --glob '!node_modules' --glob '!package-lock.json' --glob '!.git/' -g '!openwiki/*' . | sort
  rg -n "frontend/" --glob '!node_modules' --glob '!package-lock.json' --glob '!.git/' -g '!openwiki/*' . | wc -l
  ```
- [ ] 1.2 Load-bearing consumers (must all be rewritten — line numbers verified 2026-09-10):
  ```bash
  rg -n "frontend/" .github/workflows/deploy-digichat-cloudflare-container.yml .github/workflows/deploy-digithings-cron.yml .github/workflows/deploy-digithings-cloudflare.yml .github/workflows/deploy-digiquant-cloudflare.yml .github/workflows/smoke-site.yml .github/workflows/sync-cheaperinference-cf-secrets.yml
  rg -n "frontend" scripts/build-digithings.sh scripts/build-digiquant.sh
  rg -n "frontend" Dockerfile.digichat-cloudflare Dockerfile.digithings-stack-cloudflare
  rg -n "frontend" Makefile docker-compose.yml package.json release-please-config.json scripts/ci_paths.yaml
  ```
- [ ] 1.3 CI filter block + generator Drift check (enforced in CI by the ruff-and-scripts job):
  ```bash
  rg -n "frontend" .github/workflows/ci.yml scripts/check_frontend_canon.py scripts/generate_ci_path_filters.py
  sed -n '60,200p' scripts/ci_paths.yaml
  ```
- [ ] 1.4 Tests that pin `frontend/` paths (all must be updated — they assert exact strings):
  ```bash
  rg -n "frontend" tests/scripts/test_deploy_build_inputs.py tests/scripts/test_deploy_digichat_cloudflare_container.py tests/scripts/test_mcp_container.py tests/scripts/test_check_deploy_freshness.py tests/scripts/test_frontend_dashboard_workspace.py tests/scripts/test_build_digiquant_dashboard_path.py tests/contracts/test_cross_service_surface.py
  ```
- [ ] 1.5 Verified **no-change** files (do NOT touch; record in PR body as checked):
  ```bash
  rg -n "frontend" digiquant/Dockerfile.mcp .github/workflows/publish-service-images.yml; echo "exit=$? (1 = confirmed clean)"
  ```
  Baseline: both return nothing — `digiquant/Dockerfile.mcp` only `COPY`s `digibase/`, `digikey/`, `digiquant/`; `publish-service-images.yml` only builds `digikey/digigraph/digiquant/digisearch/digismith/digivault/digiclaw` images.
- [ ] 1.6 Docs/runbook/prose sweep (bulk rewrite in Task 3.9):
  ```bash
  rg -ln "frontend/" --glob '!node_modules' --glob '!package-lock.json' --glob '!.git/' -g '!openwiki/*' AGENTS.md ARCHITECTURE.md BRANCHING.md ONBOARDING.md docs/ infra/ scripts/ digigraph/ digiquant/ digivault/ tests/ | sort
  ```
- [ ] 1.7 `package-lock.json` workspace keys (baseline: 21 keys starting with `frontend/`):
  ```bash
  node -e "const l=require('./package-lock.json'); console.log(Object.keys(l.packages||{}).filter(k=>k.startsWith('frontend')).join('\n'))"
  ```
  Baseline keys: `frontend/dashboard`, `frontend/digichat`, `frontend/digichat-cloudflare`, `frontend/digichat-ui`, `frontend/digiquant-web`, `frontend/digithings-cron`, `frontend/digithings-stack-cloudflare`, `frontend/digithings-web`, `frontend/digiweb/design`, `frontend/digiweb/reference`, `frontend/digiweb/web` (+ nested `node_modules/*` entries).

---

## Task 2 — The move (`git mv` sequencing)

Do the move **first**, before any content edits, so `git status` shows pure renames and reviewers can verify nothing was lost.

- [ ] 2.1 Move the whole tree in one command (preserves history, handles the empty `frontend/design/assets/` and `frontend/web/dist/` build output identically):
  ```bash
  git mv frontend cloudflare && git status --short | head -n 30
  ```
- [ ] 2.2 Verify: `ls cloudflare/` shows the same 11 entries as the Task 0 table; `ls frontend/` fails; `git status --short | rg '^R'` lists the renames:
  ```bash
  ls cloudflare/ && ls frontend/; echo "---"; git status --short | rg -c '^R'
  find cloudflare -maxdepth 1 -mindepth 1 | sort
  ```
- [ ] 2.3 If `git mv frontend cloudflare` is refused (e.g. a `cloudflare/` path already exists), stop — do not merge trees by hand; report back instead (this is the one sequencing escape hatch; there is no other planned ordering because a single top-level `git mv` is atomic for history purposes).
- [ ] 2.4 Only after 2.2 passes, proceed to Task 3 content edits.

---

## Task 3 — Reference rewrites (file-by-file, exact old → new)

Global rule: replace the literal prefix `frontend/` with `cloudflare/` **only when it denotes the repo path**. Two deliberate exceptions (do not blindly `sed` these without reading):
- `scripts/check_frontend_canon.py` — the script *filename* and identifiers (`check_frontend_canon`, `CENSUS_APPS`, `frontend_class_families.json`) stay; only the path literals it scans/consumes change.
- Prose matches where "frontend" is a plain word (e.g. `ONBOARDING.md:217` "research frontend regeneration", `docs/adr/*` historical descriptions, audit docs under `docs/reviews/`) — rewrite the path portion only (`frontend/dashboard/...` → `cloudflare/dashboard/...`), leave the English word "frontend" alone.

Fast path for the mechanical bulk (run AFTER the hand-checked files in 3.1–3.8, then review the diff):
```bash
rg -l "frontend/" --glob '!node_modules' --glob '!.git/' --glob '!package-lock.json' -g '!openwiki/*' .github/ scripts/ tests/ Makefile docker-compose.yml Dockerfile.digichat-cloudflare Dockerfile.digithings-stack-cloudflare package.json release-please-config.json ARCHITECTURE.md AGENTS.md BRANCHING.md ONBOARDING.md docs/ infra/ digigraph/ digiquant/ digivault/ digisearch/ frontend/ 2>/dev/null | xargs sed -i 's|frontend/|cloudflare/|g'
```
Then hand-verify 3.1–3.8 diffs hunk by hunk (`git diff --stat`, `git diff <file>`). `package-lock.json` is NOT in the list — it is regenerated (3.4).

### 3.1 GitHub workflows

**`.github/workflows/deploy-digichat-cloudflare-container.yml`** — old → new:
- [ ] Line 3 comment: `(see frontend/digichat-cloudflare/README.md)` → `(see cloudflare/digichat-cloudflare/README.md)`
- [ ] Line 15 comment: `digichat's own version (frontend/digichat/package.json)` → `(cloudflare/digichat/package.json)`
- [ ] Line 18 comment: `(frontend/digichat-cloudflare/** or` → `(cloudflare/digichat-cloudflare/** or`
- [ ] Lines 37–38 path filter: `- "frontend/digichat/package.json"` → `- "cloudflare/digichat/package.json"`; `- "frontend/digichat-cloudflare/**"` → `- "cloudflare/digichat-cloudflare/**"`
- [ ] Line 74: `current_version=$(jq -r .version frontend/digichat/package.json)` → `... cloudflare/digichat/package.json`
- [ ] Line 76: `echo "frontend/digichat/package.json has no .version field` → `echo "cloudflare/digichat/package.json has no .version field`
- [ ] Line 114: `grep -E '^(frontend/digichat-cloudflare/|Dockerfile\.digichat-cloudflare$)'` → `grep -E '^(cloudflare/digichat-cloudflare/|Dockerfile\.digichat-cloudflare$)'`
- [ ] Lines 120–121: `"$BEFORE:frontend/digichat/package.json"` → `"$BEFORE:cloudflare/digichat/package.json"` (both occurrences)
- [ ] Lines 142, 145 comments: `frontend/digichat-cloudflare has no lockfile` → `cloudflare/digichat-cloudflare has no lockfile`; `frontend/digichat-cloudflare/src/index.ts's` → `cloudflare/digichat-cloudflare/src/index.ts's`
- [ ] Line 157: `jq -r .version frontend/digichat/package.json` → `jq -r .version cloudflare/digichat/package.json`
- [ ] Line 165: `workingDirectory: frontend/digichat-cloudflare` → `workingDirectory: cloudflare/digichat-cloudflare`

**`.github/workflows/deploy-digithings-cron.yml`** — old → new:
- [ ] Line 11 path filter: `- "frontend/digithings-cron/**"` → `- "cloudflare/digithings-cron/**"`
- [ ] Line 45: `workingDirectory: frontend/digithings-cron` → `workingDirectory: cloudflare/digithings-cron`

**`.github/workflows/deploy-digithings-cloudflare.yml`** — old → new:
- [ ] Line 10: `- "frontend/digithings-web/**"` → `- "cloudflare/digithings-web/**"`
- [ ] Lines 14, 33–41 comments + filters: `frontend/digichat-ui/**` → `cloudflare/digichat-ui/**`; `frontend/digiweb/web/**` → `cloudflare/digiweb/web/**`; `frontend/digiweb/design/**` → `cloudflare/digiweb/design/**`; line 14 `frontend/digichat-ui/src/DigiChatSession.tsx` → `cloudflare/digichat-ui/src/DigiChatSession.tsx`
- [ ] Lines 105, 116, 122, 133–134, 138, 145 comments: `frontend/digichat/package.json` → `cloudflare/digichat/package.json`; `frontend/digichat-ui/package.json` → `cloudflare/digichat-ui/package.json`; `frontend/digichat`, `frontend/digiquant-web`, `frontend/dashboard`, `frontend/digiweb/reference` → `cloudflare/...` respectively
- [ ] Lines 162–163: `- "frontend/digithings-stack-cloudflare/package.json"` → `- "cloudflare/digithings-stack-cloudflare/package.json"`; `- "frontend/digiweb/reference/package.json"` → `- "cloudflare/digiweb/reference/package.json"`

**`.github/workflows/deploy-digiquant-cloudflare.yml`** — old → new:
- [ ] Lines 9–12 filters: `frontend/digiquant-web/**`, `frontend/digiweb/web/**`, `frontend/dashboard/**`, `frontend/digiweb/design/**` → `cloudflare/...`
- [ ] Lines 79, 81, 91–93, 100, 106 comments: `frontend/digichat-ui/**`, `frontend/digichat`, `frontend/digithings-web`, `frontend/digiweb/reference` → `cloudflare/...`
- [ ] Lines 122–123: `- "frontend/digithings-stack-cloudflare/package.json"` → `- "cloudflare/digithings-stack-cloudflare/package.json"`; `- "frontend/digiweb/reference/package.json"` → `- "cloudflare/digiweb/reference/package.json"`

**`.github/workflows/smoke-site.yml`** — comment-only, old → new:
- [ ] Line 1: `# Production clock: Cloudflare Worker digithings-cron (frontend/digithings-cron)` → `(cloudflare/digithings-cron)`
- [ ] Line 64: `# digithings.ai — Next.js static export (frontend/digithings-web).` → `(cloudflare/digithings-web)`
- [ ] Line 81: `# digiquant.io — Next.js static export (frontend/digiquant-web) +` → `(cloudflare/digiquant-web) +`

**`.github/workflows/sync-cheaperinference-cf-secrets.yml`** — old → new:
- [ ] Line 59: `workingDirectory: frontend/digichat-cloudflare` → `workingDirectory: cloudflare/digichat-cloudflare` (the `digithings-stack` job uses the Secrets HTTP API — no path — unchanged)

**`.github/workflows/ci.yml`** (generated block — see 3.3; hand-check after regenerating):
- [ ] Lines 75 (`frontend/digiquant-web/lib/live/**`), 94–97 (digichat lane), 102–104 (dashboard lane), 109–118 (web lane), 190 (`frontend/digithings-cron/**`), 194 (`frontend/digichat/package.json`), 218–227 (frontend-canon comments) — all `frontend/` → `cloudflare/` via the generator, not by hand.

**`.github/workflows/test-web.yml` / `test-digichat.yml` / `test-dashboard.yml`** — comment-only:
- [ ] `test-web.yml:29-31,59,81,86,106,119`, `test-digichat.yml:16,18`, `test-dashboard.yml:15,17`: `frontend/digiweb/MIGRATION.md`, `frontend/digichat`, `frontend/digiweb/reference/README.md` → `cloudflare/...` (the `run: python3 scripts/check_frontend_canon.py` invocations are unchanged — script filename stays).

**`.github/workflows/publish-service-images.yml`** — [ ] verified clean (Task 1.5); no change.

### 3.2 Build scripts

**`scripts/build-digithings.sh`** — old → new:
- [ ] Line 3 comment: `(frontend/digithings-web)` → `(cloudflare/digithings-web)`
- [ ] Line 47: `npm --workspace frontend/digithings-web run build` → `npm --workspace cloudflare/digithings-web run build`
- [ ] Line 53: `cp -r frontend/digithings-web/out/. dist/` → `cp -r cloudflare/digithings-web/out/. dist/`
- [ ] Line 59: `from "./frontend/digithings-web/lib/security-headers.mjs"` → `from "./cloudflare/digithings-web/lib/security-headers.mjs"`
- [ ] Lines 116, 120–121, 130: `frontend/digithings-web/functions` (4 occurrences incl. `ERROR: expected frontend/digithings-web/functions`) → `cloudflare/digithings-web/functions`

**`scripts/build-digiquant.sh`** — old → new:
- [ ] Lines 4, 6 comments: `frontend/digiquant-web/out/`, `frontend/dashboard/out/` → `cloudflare/...`
- [ ] Lines 39–40: `frontend/dashboard/public/dashboard-data.json` (test + ERROR message) → `cloudflare/dashboard/public/dashboard-data.json`
- [ ] Line 67: `npm --workspace frontend/digiquant-web run build` → `npm --workspace cloudflare/digiquant-web run build`
- [ ] Line 68: `cp -r frontend/digiquant-web/out/. dist/` → `cp -r cloudflare/digiquant-web/out/. dist/`
- [ ] Line 93: `npm --workspace frontend/dashboard run build` → `npm --workspace cloudflare/dashboard run build`
- [ ] Line 95: `cp -r frontend/dashboard/out/. dist/dashboard/` → `cp -r cloudflare/dashboard/out/. dist/dashboard/`

### 3.3 CI path filters (source + generated block)

- [ ] 3.3.1 `scripts/ci_paths.yaml` — rewrite every `frontend/` glob to `cloudflare/`: `digiquant` lane (`frontend/digiquant-web/lib/live/**`), `digichat` lane (`frontend/digichat/**`, `frontend/digichat-ui/**`, `frontend/digiweb/web/**`, `frontend/digiweb/design/**`), `dashboard` lane (`frontend/dashboard/**`, `frontend/digiweb/web/**`, `frontend/digiweb/design/**`), `web` lane (`frontend/digithings-web/**`, `frontend/digiquant-web/**`, `frontend/digithings-cron/**`, `frontend/digichat-ui/**`, `frontend/digiweb/web/**`, `frontend/digiweb/design/**`, `frontend/digiweb/brand/**`, `frontend/digiweb/reference/**`, `frontend/digichat-cloudflare/**`, `frontend/digithings-stack-cloudflare/**`), and the `score`-lane comment (`frontend/** intentionally excluded`, still excluded — only the prefix changes).
- [ ] 3.3.2 Regenerate the embedded block in `ci.yml` (never hand-edit the block):
  ```bash
  python3 scripts/generate_ci_path_filters.py && python3 scripts/generate_ci_path_filters.py --check && git diff --stat .github/workflows/ci.yml scripts/ci_paths.yaml
  ```
- [ ] 3.3.3 `scripts/check_frontend_canon.py` — script name unchanged; rewrite consumed paths: header docstring (`frontend/`), lines 42, 45–54, 57 (allowlist entries), 67–74 (exclusions), `CENSUS_APPS` line 144 (values only, name stays), lines 154, 157 (`f"frontend/{app}/"` → `f"cloudflare/{app}/"`), 179 (`git ls-files frontend` → `git ls-files cloudflare`), 190, 217, 225 (`frontend/digiweb/MIGRATION.md` → `cloudflare/digiweb/MIGRATION.md`). Verify with:
  ```bash
  python3 scripts/check_frontend_canon.py && rg -n "frontend/" scripts/check_frontend_canon.py; echo "exit=$? (1 = clean)"
  ```

### 3.4 npm workspaces + lockfile + release-please

- [ ] 3.4.1 Root `package.json` workspaces block — old → new:
  ```json
  "workspaces": ["frontend/*", "frontend/digiweb/*"]  →  "workspaces": ["cloudflare/*", "cloudflare/digiweb/*"]
  ```
- [ ] 3.4.2 Regenerate the lockfile (do NOT sed it):
  ```bash
  npm install --package-lock-only && node -e "const l=require('./package-lock.json'); const ks=Object.keys(l.packages||{}); console.log('leftover frontend keys:', ks.filter(k=>k.startsWith('frontend')).length, '| cloudflare keys:', ks.filter(k=>k.startsWith('cloudflare')).length)"
  ```
  Expected: leftover `0`, `cloudflare` keys `11` (+ nested `node_modules/*` entries).
- [ ] 3.4.3 `release-please-config.json` — old → new: `"frontend/digichat"` key → `"cloudflare/digichat"`; `"jsonpath": "$.packages['frontend/digichat'].version"` → `"$.packages['cloudflare/digichat'].version"`. Then:
  ```bash
  python3 -c "import json; c=json.load(open('release-please-config.json')); print(list(c['packages'].keys()))"
  ```
- [ ] 3.4.4 `digiquant/scripts/research/check-types-sync.sh` — lines 7, 54: `TYPES_FILE="frontend/lib/database.types.ts"` → `"cloudflare/lib/database.types.ts"` and the echo line likewise. (Note: the path looks pre-existing-stale — no `frontend/lib/` exists in the tree; keep the rename one-to-one, do not fix the staleness here. Call it out in the PR body.)

### 3.5 Dockerfiles (build contexts are repo root — every `COPY` source path changes)

**`Dockerfile.digichat-cloudflare`** — old → new (all 14 path occurrences):
- [ ] Line 2 comment: `(same as frontend/digichat/Dockerfile)` → `(same as cloudflare/digichat/Dockerfile)`
- [ ] Lines 12–16: `COPY frontend/digichat/package.json frontend/digichat/` → `COPY cloudflare/digichat/package.json cloudflare/digichat/` (same pattern for `digichat-ui`, `digiweb/design`, `digiweb/web`, `dashboard` — both source AND dest change; dest must match because later `COPY --from=builder /app/frontend/...` paths and `npm --workspace` names change too)
- [ ] Line 17: `RUN npm ci --workspace frontend/digichat --include-workspace-root` → `--workspace cloudflare/digichat`
- [ ] Lines 26–27: `COPY frontend/digiweb/design ./frontend/digiweb/design` → `COPY cloudflare/digiweb/design ./cloudflare/digiweb/design` (same for `digiweb/web`)
- [ ] Line 29: `COPY ["frontend/digiweb/reference/app/(chatbot)/chatbot/chatbot.css", "frontend/digiweb/reference/app/(chatbot)/chatbot/chatbot.css"]` → both sides `cloudflare/...`
- [ ] Lines 30–31: `COPY frontend/digichat-ui ./frontend/digichat-ui` → `COPY cloudflare/digichat-ui ./cloudflare/digichat-ui` (same for `digichat`)
- [ ] Lines 42, 44: `require('./frontend/digichat/package.json')` → `require('./cloudflare/digichat/package.json')`; `npm run build --workspace frontend/digichat` → `--workspace cloudflare/digichat`
- [ ] Lines 52–56: `/app/frontend/digichat/.next/standalone`, `./frontend/digichat/.next/static`, `./frontend/digichat/public`, `./frontend/digichat/scripts/trusted-proxy-server.mjs`, `./frontend/digichat/drizzle` → `/app/cloudflare/...` / `./cloudflare/...`
- [ ] Line 65: `CMD ["node", "frontend/digichat/scripts/trusted-proxy-server.mjs"]` → `CMD ["node", "cloudflare/digichat/scripts/trusted-proxy-server.mjs"]`
- [ ] `digichat-cloudflare` trusted-proxy note: `frontend/digichat-cloudflare` has no `trusted-proxy-server.mjs` of its own — the file belongs to `frontend/digichat/scripts/`; no import update needed beyond the paths above. `frontend/digichat/src/lib/trusted-proxy-server.test.ts` imports `../../scripts/trusted-proxy-server.mjs` (relative — unaffected).

**`Dockerfile.digithings-stack-cloudflare`** — old → new:
- [ ] Lines 63, 65–69: `COPY frontend/digithings-stack-cloudflare/container/supervisor/supervisord.conf`, `container/entrypoint.sh`, `container/seed_chroma.sh`, `container/start_digikey.sh`, `container/start_digisearch.sh`, `container/seed` → `COPY cloudflare/digithings-stack-cloudflare/...` (dest filenames `/entrypoint.sh` etc. unchanged)

**`frontend/digichat/Dockerfile`** (moves to `cloudflare/digichat/Dockerfile`) — internal `COPY` paths are relative to its own dir (lines 47, 61 use `/app/frontend/digichat/...` as *container-side* absolute paths built from `WORKDIR /app` + repo-relative layout — re-read after the move; if the Dockerfile does `COPY . .` style relative copies, no change; only absolute `/app/frontend/...` references become `/app/cloudflare/...`). Verify with `rg -n "frontend" cloudflare/digichat/Dockerfile` post-move.

**`digiquant/Dockerfile.mcp`** — [ ] verified clean; no change.

### 3.6 `wrangler.toml` files (comments only — no binding/route/scaling edits)

- [ ] `cloudflare/digichat-cloudflare/wrangler.toml` line 36 comment: `# DIGICHAT_VERSION for GET /api/health is baked from frontend/digichat/package.json` → `... from cloudflare/digichat/package.json`. `image = "../../Dockerfile.digichat-cloudflare"` is relative (two levels up) — UNCHANGED. All `[[routes]]`, `[[containers]]`, `[[durable_objects.bindings]]`, `[[migrations]]`, `[vars]` — UNCHANGED.
- [ ] `cloudflare/digithings-stack-cloudflare/wrangler.toml` line 61 comment: `# Container — deploy frontend/digithings-stack-cloudflare and point secrets at:` → `# Container — deploy cloudflare/digithings-stack-cloudflare and point secrets at:`. `image = "../../digiquant/Dockerfile.mcp"` and `"../../Dockerfile.digithings-stack-cloudflare"` — relative, UNCHANGED. `sleepAfter`, `max_instances`, `instance_type`, routes, bindings, migrations — UNCHANGED (constraint).
- [ ] `cloudflare/digithings-web/wrangler.toml` lines 3, 13 comments: `(frontend/digithings-web)` → `(cloudflare/digithings-web)`; `transitive of the deleted frontend/digichat-cloudflare workspace` → `... of the deleted cloudflare/digichat-cloudflare workspace`. `pages_build_output_dir = "out"` — UNCHANGED.
- [ ] `cloudflare/digithings-cron/wrangler.toml` — no `frontend/` references inside (verified); no change. `[triggers] crons` — UNCHANGED.

### 3.7 Tests that pin paths (update exact asserted strings)

- [ ] `tests/scripts/test_deploy_build_inputs.py` — docstring + assertions referencing `frontend/digithings-web`, `frontend/digichat-ui/src/DigiChatSession.tsx`, `frontend/digiweb/brand`, `frontend/digiweb/scripts`, `frontend/digiweb/reference/package.json`, `frontend/digiweb/reference/**`, `frontend/digichat` → `cloudflare/...` (bulk sed covers; re-run to confirm green).
- [ ] `tests/scripts/test_deploy_digichat_cloudflare_container.py` — lines 63–64, 92, 126, 136, 220–221, 226, 240, 253, 295: `frontend/digichat/...` and `frontend/digichat-cloudflare/...` (both real-path fixtures under a scratch repo AND asserted workflow strings) → `cloudflare/...`.
- [ ] `tests/scripts/test_mcp_container.py` — lines 7, 28–30: `frontend/digithings-stack-cloudflare/` (docstring + `REPO_ROOT / "frontend" / ...` ×3) → `cloudflare/...`.
- [ ] `tests/scripts/test_check_deploy_freshness.py` — lines 348, 356, 368, 373 comments: `frontend/digiweb/reference/...` → `cloudflare/...`.
- [ ] `tests/scripts/test_frontend_dashboard_workspace.py` — file NAME stays; lines 17–18, 25–27, 32–35, 40, 42, 56–57, 61, 68, 78–81, 86–87, 91, 95, 98, 101, 104 + docstring: `frontend/dashboard`, `frontend/olympus`, `frontend/digichat/Dockerfile`, `frontend/digichat-ui` → `cloudflare/...` (the `olympus` half is historical — keep the string, only the prefix changes).
- [ ] `tests/scripts/test_build_digiquant_dashboard_path.py` — lines 15–16, 22, 25, 68: `REPO_ROOT / "frontend" / ...` and asserted `cp -r frontend/dashboard/out/...` strings → `cloudflare/...`.
- [ ] `tests/contracts/test_cross_service_surface.py:33` comment: `Vitest under frontend/digichat/` → `under cloudflare/digichat/`.

### 3.8 Makefile / compose / hooks / misc scripts

- [ ] `Makefile` lines 32, 34–35, 139, 141, 143, 145, 152, 192: `cd frontend/digichat`, `cd frontend/dashboard`, `frontend/digichat/.env.local`, `frontend/digichat/OPERATIONS.md`, `frontend/digithings-web/lib/apiDocs.ts + sharedDocs.ts` → `cloudflare/...`.
- [ ] `docker-compose.yml:432`: `dockerfile: frontend/digichat/Dockerfile` → `dockerfile: cloudflare/digichat/Dockerfile`.
- [ ] `scripts/claude-hooks/auto-format.sh:22-24`: `"$PROJECT_ROOT/frontend/digichat/"*`, `"${file#"$PROJECT_ROOT/frontend/digichat/}"`, `cd "$PROJECT_ROOT/frontend/digichat"` → `cloudflare/digichat`.
- [ ] `scripts/claude-hooks/protected-path-bash-guard.sh:19`, `scripts/claude-hooks/protected-path-guard.sh:41`, `scripts/hooks/pre-push.sh:126` comments: `frontend/**/references/**/live/` → `cloudflare/**/references/**/live/`.
- [ ] `scripts/fetch_repo_activity.py:135`: `f"frontend/{mid}"` → `f"cloudflare/{mid}"`.
- [ ] `scripts/score.py:63,84`: `("frontend/digiweb/design/terminal/highlight-dom.js", ...)` and `"frontend/digiweb/design/"` → `cloudflare/...`.
- [ ] `scripts/validation/make_tearsheets.py:27-28` comments + `digiquant/scripts/generate_tearsheets.py:11,74,285` (`REPO_ROOT / "frontend" / "digiquant-web" / ...`): → `cloudflare/...`.
- [ ] `scripts/readiness.py:75`: `"digichat": ["frontend/digichat/src"]` → `["cloudflare/digichat/src"]`.
- [ ] `scripts/worktree_task.sh:173,181` comments: `frontend/` → `cloudflare/`; `component_path="frontend/digichat"` → `"cloudflare/digichat"`.
- [ ] `scripts/d1_sync.py:362`, `scripts/vectorize_sync.py:21,328`, `digivault/src/digivault/tenant_scope.py:28` comments: `frontend/digithings-stack-cloudflare/wrangler.toml` → `cloudflare/...`.
- [ ] `scripts/gen-api-vault.ts:16-18` imports: `../frontend/digiweb/web/src/data/modules`, `../frontend/digithings-web/lib/sharedDocs`, `../frontend/digithings-web/lib/docsSerializers` → `../cloudflare/...`.
- [ ] `digigraph/src/digigraph/languages.py:7`, `digigraph/src/digigraph/chat_prompt.py:86` comments: `frontend/digichat/src/lib/...` → `cloudflare/digichat/src/lib/...`.
- [ ] `infra/digichat-digithings/README.md` (lines 35, 38, 58, 67, 73, 83, 138, 225–226), `infra/digichat-release/README.md:109`, `infra/digichat-release/compose.profile-a-bundle.yml:18` → `cloudflare/...`.

### 3.9 Docs / runbooks / in-tree cross-refs (bulk + `doc-check`)

- [ ] 3.9.1 `ARCHITECTURE.md:548` (`frontend/digichat/ARCHITECTURE.md` link), `:409` (`cd frontend/digichat && npm run dev`) → `cloudflare/...`.
- [ ] 3.9.2 `AGENTS.md:71` (dashboard path), `:132` (presentation-only + score-filter globs), `:387` (`frontend/digichat/.env.local`) → `cloudflare/...`.
- [ ] 3.9.3 `docs/DEPLOYMENT.md` lines 139, 152, 162, 164, 168, 245, 257, 267; `docs/LOCAL_STACK.md:46`; `docs/ops/digithings-cron.md:10`; `docs/ops/vectorize-cutover.md:7,27,50,198`; `docs/ops/HOUSE_BOOK_SCOPE.md:99`; `ONBOARDING.md:215-217,229`; `BRANCHING.md:42` → `cloudflare/...` (keep the English word "frontend" where it is prose, e.g. ONBOARDING "research frontend regeneration" stays, only the paths change; ONBOARDING:216 "Workspace installs must happen under `frontend/`" → "under `cloudflare/`").
- [ ] 3.9.4 `docs/adr/0009-frontend-umbrella.md` and other ADRs, `docs/agent-backlog/**`, `docs/superpowers/**`, `docs/reviews/**`, `docs/plans/**`, `docs/vision/**`, `docs/agents/**`, `docs/architecture/**`, `docs/digichat/**`, `docs/dashboard-audits/**`, `docs/projects/**` — bulk sed `frontend/` → `cloudflare/` (historical audit docs describe the tree at the time; prefix rewrite keeps links resolving — accepted).
- [ ] 3.9.5 In-tree cross-refs that moved with the tree: `frontend/digiweb/reference/lib/brandKit.ts:3-5`, `frontend/digiweb/web/src/index.ts:352`, `frontend/digichat-ui/ARCHITECTURE.md`, `frontend/digichat/{AGENTS,ARCHITECTURE,CONTROLS,OPERATIONS,README,next.config.ts}`, `frontend/dashboard/{README,docs,lib}`, `frontend/digiquant-web/{app,components,public}`, `frontend/digithings-web/{app,lib}`, `frontend/digiweb/{ARCHITECTURE,MANIFEST,MIGRATION,PRODUCT,README,scripts}`, `frontend/{digichat-cloudflare,digithings-cron,digithings-stack-cloudflare}/README.md` — bulk sed covers (verify with Task 1.1 re-run returning zero).
- [ ] 3.9.6 `make doc-check` must pass (validates internal markdown links post-rewrite):
  ```bash
  make doc-check
  ```
- [ ] 3.9.7 `openwiki/` — no hand edits; the scheduled `openwiki-update.yml` regenerates after merge (note in PR body).

---

## Task 4 — Verification (all on the rename commit, before merge)

- [ ] 4.1 Zero-leftover grep (excluding generated `openwiki/*`, which regenerates):
  ```bash
  rg -n "frontend/" --glob '!node_modules' --glob '!.git/' -g '!openwiki/*' -g '!docs/superpowers/plans/2026-09-10-cloudflare-v2-phase1-dir-rename.md' . ; echo "exit=$? (1 = clean)"
  node -e "const l=require('./package-lock.json'); console.log('leftover:', Object.keys(l.packages||{}).filter(k=>k.startsWith('frontend')).length)"
  ```
- [ ] 4.2 CI-path generator drift check + canon guard:
  ```bash
  python3 scripts/generate_ci_path_filters.py --check && python3 scripts/check_frontend_canon.py
  ```
- [ ] 4.3 Full CI on the PR (push and wait — required lanes: `ci.yml` filters incl. regenerated block, `deploy-digithings-cloudflare.yml` + `deploy-digiquant-cloudflare.yml` build checks, `deploy-digichat-cloudflare-container.yml`, `deploy-digithings-cron.yml`, `test-web.yml`, `test-digichat.yml`, `test-dashboard.yml`, `sync-architecture-vault` if triggered). Fix forward on the same branch; do not stack anything on top until green.
- [ ] 4.4 Local build-script dry runs (prove the rewritten paths resolve):
  ```bash
  bash -n scripts/build-digithings.sh && bash -n scripts/build-digiquant.sh
  npm --workspace cloudflare/digithings-web run build  # or the full ./scripts/build-digithings.sh if time allows
  npm --workspace cloudflare/digiquant-web run build
  npm --workspace cloudflare/dashboard run build
  ```
- [ ] 4.5 Docker build-context check (root context; prove the rewritten `COPY` sources exist):
  ```bash
  docker build --no-push -f Dockerfile.digichat-cloudflare --target builder . --dry-run 2>/dev/null || docker build -f Dockerfile.digichat-cloudflare --target builder . 
  docker build --no-push -f Dockerfile.digithings-stack-cloudflare . --dry-run 2>/dev/null || echo "no dry-run; run a real build in CI"
  ```
  (If the daemon is unavailable locally, CI's container-deploy lanes are the gate — say so in the PR body.)
- [ ] 4.6 Wrangler dry-run per Worker (from each package dir; `--dry-run` if the installed wrangler supports it, else `wrangler deploy --dry-run --outdir /tmp/wrangler-dry` — commands must NOT deploy):
  ```bash
  (cd cloudflare/digichat-cloudflare && npx wrangler deploy --dry-run)
  (cd cloudflare/digithings-stack-cloudflare && npx wrangler deploy --dry-run)
  (cd cloudflare/digithings-cron && npx wrangler deploy --dry-run)
  (cd cloudflare/digithings-web && npx wrangler pages dev --help >/dev/null && echo "pages dev available")
  ```
- [ ] 4.7 Pages preview builds: open the Cloudflare Pages preview deployments for `digithings.ai` and `digiquant.io` triggered by the PR branch (dashboard shows them once the owner confirms the root-directory setting still resolves — Task 5), or run the static exports locally (4.4) and confirm `dist/` contains the expected roots.
- [ ] 4.8 Pin-test subset (the tests edited in 3.7):
  ```bash
  python3 -m pytest tests/scripts/test_deploy_build_inputs.py tests/scripts/test_deploy_digichat_cloudflare_container.py tests/scripts/test_mcp_container.py tests/scripts/test_check_deploy_freshness.py tests/scripts/test_frontend_dashboard_workspace.py tests/scripts/test_build_digiquant_dashboard_path.py -q
  ```

---

## Task 5 — Cloudflare-dashboard OWNER checklist (owner clicks, implementer does not)

The rename changes the repo paths the Pages projects build from. The dashboard holds its own copy of Root directory / Build command / Output directory — nothing in git can change those. After the rename commit merges to the Pages production branch:

- [ ] **OWNER 5.1 — Pages project `digithings.ai`** → Dash → Workers & Pages → `digithings-web`/`digithings.ai` → Settings → Builds & deployments:
  - Root directory: `frontend/digithings-web` → `cloudflare/digithings-web` (exact field: **Root directory / Project path**)
  - Build command: if it references `scripts/build-digithings.sh` by repo-root relative path, unchanged; if it `cd frontend/digithings-web`, change to `cd cloudflare/digithings-web` (read the current value first — the repo-side script assembles repo-root `dist/`, see `scripts/build-digithings.sh` header + `cloudflare/digithings-web/wrangler.toml` production-root caveat)
  - Output directory: unchanged (`dist` / `out` as currently configured — confirm, do not alter)
  - Then: Retry deployment on the merged commit; confirm the production deployment goes green.
- [ ] **OWNER 5.2 — Pages project `digiquant.io`** → same Settings page:
  - Root directory: `frontend/digiquant-web` → `cloudflare/digiquant-web` (exact field: **Root directory / Project path**)
  - Build command / Output directory: read-then-confirm (repo-side `scripts/build-digiquant.sh` builds `dist/` + `dist/dashboard/`); change only a `frontend/`-prefixed `cd` if present.
  - Then: Retry deployment; confirm green.
- [ ] **OWNER 5.3 — Workers (`digithings-digichat`, `digithings-stack`, `digithings-cron`)**: no dashboard change (deploys run from the package dirs via wrangler; `workingDirectory` updates in Task 3.1 cover CI). Confirm the next scheduled `digithings-cron` tick and one manual `wrangler deploy` each still succeed post-merge.
- [ ] **OWNER 5.4 — Secrets**: no change (`sync-cheaperinference-cf-secrets.yml` secret names unchanged; only its `workingDirectory` moved). Do not rotate anything as part of this rename.
- [ ] **OWNER 5.5 — Custom domains / routes / bindings**: explicitly unchanged (Task 3.6 touched comments only). If the dashboard shows a diff prompt on any binding, stop and re-verify — nothing should differ.

---

## Acceptance criteria

- [ ] `ls frontend/` fails; `ls cloudflare/` shows all 11 members; `git log --follow -- cloudflare/digichat/package.json` (and spot-checks on 2–3 other moved files) shows pre-rename history (i.e. the move was `git mv`, not delete+add).
- [ ] Task 4.1 greps return zero `frontend/` hits outside `openwiki/` (generated) and this plan file itself (which records old→new strings by design), and zero `frontend*` keys in `package-lock.json`.
- [ ] `generate_ci_path_filters.py --check`, `check_frontend_canon.py`, and `make doc-check` all pass.
- [ ] Full CI green on the single rename commit (Task 4.3), including both Pages deploy build checks and the container/cron lanes.
- [ ] Wrangler dry-runs (4.6) succeed from all three Worker dirs; no `sleepAfter`/scaling/route/binding diff in any `wrangler.toml` (`git diff` on the three Worker `wrangler.toml`s shows comment lines only).
- [ ] Owner confirms 5.1–5.2 production Pages deployments green post-merge; 5.3 cron tick observed.
- [ ] PR body records: base SHA (Task 0.2), the Task 1.5 no-change verifications, the `check-types-sync.sh` pre-existing-staleness note (3.4.4), and whether Docker builds ran locally or in CI (4.5).

## Rollback

- [ ] **Primary: revert the single commit.** `git revert <rename-sha>` (or `gh pr revert` after merge) restores `frontend/` and every reference atomically. Then re-revert or fix-forward the two dashboard Root-directory fields (Task 5.1–5.2) back to `frontend/...` — the revert PR body must carry that owner reminder.
- [ ] **If Pages auto-deployed a broken build before the revert**: owner uses Dash → Workers & Pages → project → Deployments → Rollback to the last `frontend/`-era production deployment for each of the two sites, then fixes the Root directory field.
- [ ] **No data migration involved** — no D1/Vectorize/R2/KV state is touched by this rename, so no data rollback exists or is needed.

## Risks

| # | Risk | Likelihood / Impact | Mitigation in this spec |
|---|------|---------------------|-------------------------|
| 1 | Missed `frontend/` string outside the inventoried set (long tail: `docs/agent-backlog`, ADRs, vision docs) | Likely / Low (docs-only) but breaks the zero-grep acceptance | Task 1.1 full-tree re-run + 4.1 zero-grep gate; bulk sed covers all non-generated dirs |
| 2 | CI path-filter drift: `ci.yml` embedded block edited by hand instead of regenerated | Medium / High (wrong lanes fire or required lanes skip; drift check fails) | 3.3.2 mandates the generator + `--check`; 4.2 gates on it |
| 3 | `package-lock.json` hand-edited or stale (11 workspace keys + nested entries) | Medium / High (broken `npm ci` everywhere) | 3.4.2 regenerates via `npm install --package-lock-only`; 4.1 counts leftover keys |
| 4 | Dockerfile `COPY` dest/source mismatch (source renamed but dest left `frontend/`, or vice versa) breaking the standalone server layout + `trusted-proxy-server.mjs` CMD | Medium / High (container boot failure) | 3.5 rewrites both sides; 4.5 build check; container-deploy CI lane is the gate |
| 5 | Cloudflare Pages builds break because dashboard Root directory still points at `frontend/...` | Certain if owner step skipped / High (production sites stop deploying; last-good build keeps serving, per `smoke-site.yml` freshness notes) | Task 5 owner checklist with exact project + field; freshness jobs (`smoke-site.yml`) detect a stalled project post-merge |
| 6 | `release-please` loses the digichat package (key rename `frontend/digichat` → `cloudflare/digichat` mis-typed) | Low / Medium (missed releases, wrong tag paths) | 3.4.3 exact old→new + `python3 -c` key listing; verify the next release-please PR targets `cloudflare/digichat/CHANGELOG.md` |
| 7 | `check-types-sync.sh` staleness (`frontend/lib/database.types.ts` never existed at that path) becomes `cloudflare/lib/database.types.ts` — still nonexistent | Certain / Low (pre-existing, not caused here) | One-to-one rename only; PR-body note (3.4.4); separate follow-up issue, not this commit |
| 8 | Accidental `sleepAfter`/scaling/route edit while touching `wrangler.toml` comments | Low / High (container warm policy or public exposure changes) | Global constraint + 3.6 comment-only rule + acceptance criterion diffing Worker `wrangler.toml`s to comments-only |
| 9 | Sibling-repo edits (`zeus`/`apollo` share path assumptions) | Low / High (out-of-scope blast radius) | Global constraint: stay in-repo; Task 0.1 branches in `digithings` only |
| 10 | `openwiki/` hand-edited to chase the rename, conflicting with the generator | Low / Medium (merge churn with scheduled regen) | 3.9.7: never touch; workflow regenerates |
