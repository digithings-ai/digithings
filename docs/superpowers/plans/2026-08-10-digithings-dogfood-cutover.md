# digithings dogfood cutover — implementation plan

> **For agentic workers:** Plan only — do **not** implement feature code from this document until the human approves the next slice. Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task. **All implementation work stays on `develop`** until the human owns Stage A (GHCR publish on `main`).
>
> **Status:** In progress on `develop` (tracking [#2036](https://github.com/digithings-ai/digithings/issues/2036)) — Stages 1–4 + 3b + develop-safe 5/6/7/8 scaffolding landed; Stage A / live Stage 5 GHCR + live Stage 7 apply remain human/ops.
> **Parent program:** [`2026-08-09-digichat-self-host-picks-metaplan.md`](./2026-08-09-digichat-self-host-picks-metaplan.md)
> **Fit contracts:** [`digichat-self-host-picks-fit.md`](../../architecture/digichat-self-host-picks-fit.md)

---

## Goal

Make **digithings.ai** client **#0** for the same self-hosted digichat + Profile A stack clients install, with corpus grounded via the **docs_onboard** ops pipeline (website crawl, **monorepo documentation**, and OpenAPI specs). Sales story: *our public chat is the product we ship*.

**digiquant.io** is in scope as a **corpus source** (marketing/docs pages crawled into the same vault and digisearch indexes) and as a future **embed parent** only if digithings chat is iframed there later. There is **no** digiquant-hosted `/chat` page — chat UI lives on **digithings.ai** only.

Deliver incrementally on **`develop`**: deploy a slice, compare to the current production chat, record gaps, iterate. **Stage A** (develop → main promotion + GHCR publish) is **human-owned and deferred** — it does not block merging this plan or early implementation on `develop`.

---

## Non-goals

- A second digichat app, digicorpus module, or digiquant-specific chat backend.
- A **digiquant.io `/chat`** embed shell or digiquant-hosted chat page (de-scoped; see Locked decisions).
- Live crawl tools inside digigraph (onboard stays offline ops beside the stack).
- Rebuilding the terminal chat UI or a large auth redesign.
- Client-default auth ON — dogfood and most installs stay **ungated** on `/embed`.
- Replacing Cloudflare Pages + Tunnel operator topology with a new hosting model.
- Merging Pick 1 / Pick 2 / Pick 3 implementation PRs into one dogfood PR.
- Touching live-trading paths.
- **develop → main promotion or GHCR publish** in this program (human owns Stage A separately).

---

## Prerequisites (hard gate — no implementation before these)

### 1. Wait-for-merge: PRs #2028–#2031 on `develop`

| PR | Title (short) | State on `develop` (2026-08-10) | Needed for dogfood |
|---|---|---|---|
| [#2028](https://github.com/digithings-ai/digithings/pull/2028) | Self-host picks meta-plan | **MERGED** (`a5c264f`) | Plans + sequencing |
| [#2029](https://github.com/digithings-ai/digithings/pull/2029) | Profile A GHCR pull | **MERGED** (`8211e7c`) | `compose.profile-a.yml` pull-not-build |
| [#2030](https://github.com/digithings-ai/digithings/pull/2030) | docs_onboard + digivault local search | **MERGED** (`e13eaf5`) | `scripts/docs_onboard/`, runbook |
| [#2031](https://github.com/digithings-ai/digithings/pull/2031) | Runtime CSP frame-ancestors | **MERGED** (`2c30ee4`) | `DIGICHAT_EMBED_HOSTS` without rebuild |

Squash SHAs on `develop`: #2028 `a5c264f31da0d971fbf9cf31937f0af886166828`, #2029 `8211e7c321b7ed496300b029225c18e2593cf0cd`, #2030 `e13eaf5036fc379ffeebe980092d24b48d46bc6e`, #2031 `2c30ee40c30fe95edb23f4d4985d7d19e8329d44`.

**Gate rule:** Pick PRs #2028–#2031 are **merged on `develop`**. Implementation may proceed on `develop` without waiting for Stage A; Profile A GHCR pulls require Stage A before operator migration off monorepo build.

### 2. Stage A — GHCR stack images pullable (Pick 2 ops) — **human-owned, deferred**

From fit doc §5 / metaplan Stage A. **Not a blocker for plan merge or early `develop` work.** The human will schedule develop → main promotion and GHCR publish separately.

- [ ] Normal **develop → main** promotion includes publish workflow commit (`#2023` lineage). *(human)*
- [ ] Run `Publish: service images` (`service=all`) on `main`. *(human)*
- [ ] Verify `docker pull ghcr.io/digithings-ai/{digikey,digigraph,digivault}:sha-…`. *(human)*
- [ ] Record `DIGI_IMAGE_TAG` pin for digithings operator env. *(human)*

Without Stage A, Profile A “pull not build” cannot smoke on the operator host (packages 404 today). **Stage 5** (operator stack parity) waits on Stage A; Stages 1–4 and 3b may proceed on `develop` with monorepo build.

### 3. Operator secrets (human-held)

- Cloudflare Tunnel hostname → digichat Node (`NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN`).
- `CORE_SUPABASE_URL` + `CORE_SUPABASE_SERVICE_KEY` (or ADR-0022 fallbacks) for vault **publish** to Supabase.
- LLM provider keys for LiteLLM profile in `infra/digichat-release/config/`.
- `DIGIKEY_BFF_TOKEN`, `AUTH_SECRET` (digichat DB / BFF — even when root auth is OFF).

---

## Locked decisions (human, 2026-08-10)

| # | Topic | Decision |
|---|---|---|
| 1 | **Supabase table** | Keep using the **existing Supabase notes table** (production vault today). Modify schema if the new architecture requires it; starting fresh is OK if required. **Retain existing reference documents** in Supabase during transition for comparison. |
| 2 | **Crawl scope** | Crawl **both** public websites: **digithings.ai** and **digiquant.io** (and `www` variants). Allowed hosts in `onboard.yaml` confirmed. |
| 3 | **Sinks** | **Dual-sink for dogfood:** both **digivault** (Supabase publish) **and** **digisearch** (`sinks: [vault, search]`). |
| 4 | **digiquant.io `/chat`** | **No.** Chat UI is reserved for **digithings.ai** only. digiquant docs are in-scope corpus for that single digithings chat (same vault/search), not a separate chat page on digiquant.io. **De-scope Stage 6** digiquant `/chat` embed shell. digiquant.io may later be an embed *parent* only if digithings chat is iframed there — out of scope unless human asks. |
| 5 | **Legacy pipelines** | Run **parallel only as needed** during transition (`sync_architecture_vault.py`, `reindex_digithings_guide.py`, etc.) for comparison; **eventually retire** in favor of a single `docs/projects/digithings/` onboard manifest. |
| 6 | **Stage A / publish** | All dogfood work stays on **`develop`**. Human owns develop → main and GHCR publish later. Do not execute promotion or publish in this program. |
| 7 | **Repo / codebase docs ingest** | **Required for dogfood.** Extend onboard (dedicated stage / explicit source type) so the pipeline can ingest **monorepo documentation** — `ARCHITECTURE.md`, `docs/**`, `AGENTS.md`, etc. — into vault + digisearch alongside website crawl and OpenAPI. For digithings: GitHub repo fetch or local path scan of this monorepo. Pattern should generalize to any client with a GitHub repo. |

**Still open (non-blocking):**

- **Operator host:** Same machine as today’s Compose, or new Profile A host? (Tunnel target only.)
- **Auth follow-up:** If Option B (digikey OIDC) is wanted for a specific client, which IdP and timeline? (Not blocking dogfood.)

---

## Current baseline (what we compare against)

| Layer | Today | Reference |
|---|---|---|
| **Pages shell** | `frontend/digithings-web/app/chat/page.tsx` → iframe `/embed?host=digithings.ai` | `infra/digichat-digithings/README.md` |
| **digichat Node** | Operator Docker Compose (`--profile digichat --profile digivault`), often **monorepo build** | Same README |
| **Backend** | digigraph → LiteLLM; `digivault_hub` → digivault :8004 | INSTALL Profile A |
| **Vault read path** | Production digivault search: **Supabase FTS** when `DIGIVAULT_ROOT` unset | `digivault/ARCHITECTURE.md` |
| **Vault write path (legacy)** | `scripts/sync_architecture_vault.py` — `docs/vision` vault → Supabase notes table | CI / operator |
| **Repo docs index (parallel)** | `docs/projects/digithings-guide/` + `scripts/reindex_digithings_guide.py` → **digisearch** | Retire after onboard dual-sink cutover |
| **OpenAPI** | `docs/openapi/*.json` (FastAPI export + authored `digichat.json`) | `docs/openapi/README.md` |
| **Embed CSP** | Runtime `DIGICHAT_EMBED_HOSTS` / tenants (after #2031) | `frontend/digichat/src/proxy.ts` |
| **Auth** | `/` → `auth()` → redirect `/login`; `/embed` uses tenant `gateMode: ungated` | `frontend/digichat/src/app/page.tsx` |
| **digiquant.io** | Marketing/docs site; **no `/chat` page** — corpus crawl target only | `frontend/digiquant-web/` |

Dogfood success = same user-visible chat quality (grounding, citations, terminal UX on embed) on **stock GHCR pins** (after Stage A) + **onboard-driven corpus** (web + repo docs + OpenAPI) into **both** digivault and digisearch, with a **single** chat entrypoint on **digithings.ai**.

---

## Auth gate — options and recommendation

**Problem:** Root `/` login is a legacy Auth.js placeholder (dev password / generic OIDC). It does not match the terminal embed design and does not work for the human’s workflow. It must not block dogfood or ship as dead UI.

| Option | Summary | Pros | Cons |
|---|---|---|---|
| **A — Embed-only operator path (recommended default)** | Dogfood uses **only** `/embed` (Pages iframe). Add explicit env `DIGICHAT_REQUIRE_ROOT_AUTH=0` (default **0**): `/` redirects to `/embed` or shows a one-line “use embed” stub; **no** `/login` in operator config. | Zero auth maintenance; matches marketing “no sign-up”; smallest diff. | Direct visits to digichat origin `/` are not a full app shell. |
| **B — Thin digikey OIDC when enabled** | `DIGICHAT_REQUIRE_ROOT_AUTH=1` enables OIDC via digikey-issued session + terminal-styled gate on `/` only; `/embed` still tenant-gated separately. | Matches “some clients want auth” without legacy dev password. | Needs digikey/OIDC wiring + design pass; human gate on auth. |
| **C — Strip legacy UI** | Remove `/login` surface; delete dev password provider from production builds; keep machine-key BFF auth only. | No dead UI. | Breaks dev convenience unless `DIGICHAT_DEV_AUTH` stays dev-only. |

**Recommendation:** **Option A** for dogfood and default client installs — auth **OFF**, embed **ungated** (`gateMode: ungated` in tenant JSON). Schedule **Option B** as a follow-up issue only if a client needs root auth; never enable dev password in production.

**Acceptance (auth slice):** Operator can open `https://digithings.ai/chat` and chat without hitting `/login`; no broken login form on the dogfood path.

---

## Project config — `docs/projects/digithings/`

Client #0 manifests live beside other clients under `docs/projects/<client>/` (public; no `projects/` gitignore).

Proposed tree:

```text
docs/projects/digithings/
  README.md                 # operator notes: client #0, embed hosts, sync cadence
  onboard.yaml              # primary manifest for run_onboard.py
  sources/
    repo-docs.yaml          # monorepo globs → static file ingest
    openapi.yaml            # explicit OpenAPI file list
  indexes/
    docs.yaml               # digisearch index manifest (dual-sink)
```

### `onboard.yaml` shape (extends example manifest)

```yaml
client: digithings
# Web crawl — both public marketing + docs sites
seed_url: https://digithings.ai/
allowed_hosts:
  - digithings.ai
  - www.digithings.ai
  - digiquant.io
  - www.digiquant.io
max_pages: 200
max_depth: 4
sinks: [vault, search]              # locked: dual-sink for dogfood
digisearch_index: digithings_docs
vault_subdir: clients/digithings
docs_path_prefixes: ["/docs", "/chat", "/modules", "/architecture"]
skip_path_prefixes: ["/blog", "/careers", "/legal"]

# --- extensions (implementation adds schema fields) ---
static_sources: docs/projects/digithings/sources/repo-docs.yaml
openapi_sources: docs/projects/digithings/sources/openapi.yaml
# repo_source: (Stage 3b) github repo or local monorepo path for codebase docs
```

### `sources/repo-docs.yaml` (static files — local globs)

Reuse and **superset** `docs/projects/digithings-guide/indexes/docs.yaml` globs:

- Root + component `ARCHITECTURE.md`, `AGENTS.md`, `README.md`, ADRs, `docs/VISION.md`, etc.
- **Include** `docs/digichat/INSTALL.md`, `docs/openapi/README.md`, release/smoke docs added by self-host program.

Stage 3b adds **repo fetch** (GitHub API or clone) for the same doc patterns when the operator host does not mount the monorepo — generalize for any client repo.

### `sources/openapi.yaml`

```yaml
files:
  - docs/openapi/digikey.json
  - docs/openapi/digigraph.json
  - docs/openapi/digivault.json
  - docs/openapi/digisearch.json
  - docs/openapi/digismith.json
  - docs/openapi/digiquant.json
  - docs/openapi/digichat.json
kinds: [openapi, swagger]       # classify_pages / ingest tags
vault_note_type: api_reference
```

**OpenAPI ingest behavior (MVP):** Each spec → one digivault note (or sectioned notes per `paths` if size bound exceeded) with `page_class: openapi`, `source_url` = repo-relative path, `content_type: application/openapi+json`. No separate Swagger UI hosting required for MVP.

### Embed tenant (operator env, not in onboard.yaml)

Align with `infra/digichat-digithings/README.md`. **digithings.ai only** for chat embed (digiquant.io is crawl-only unless human later requests iframe parent):

```bash
DIGICHAT_EMBED_HOSTS=digithings.ai,www.digithings.ai
DIGICHAT_EMBED_TENANTS='{"digithings.ai":{"slug":"digithings","aliases":["www.digithings.ai"],"gateMode":"ungated",...,"backend":{"type":"digigraph"}}}'
```

---

## Supabase vault sink (production)

**Locked decision:** Production dogfood uses the **existing Supabase notes table** — evolve schema if onboard/OpenAPI needs new columns or `note_type` values; a fresh table is acceptable if migration is cleaner. **Keep legacy rows** during transition for side-by-side comparison.

**Read path (unchanged):** digivault service with **no** `DIGIVAULT_ROOT` → `SupabaseStore.search()` / `search_architecture_notes` RPC (table name may change if schema evolves — update RPC accordingly).

**Write path (target — two-step, smallest safe):**

```text
scripts/docs_onboard/run_onboard.py
  → write notes via digivault HTTP API (POST /v1/notes) into operator filesystem vault
  → scripts/sync_* publishes to Supabase (service role, idempotent upsert)
```

| Step | Mechanism | Notes |
|---|---|---|
| 1. Upsert notes | **digivault API** `POST /v1/notes` (`digivault/src/digivault/server.py`) | Extend `write_vault_notes.py` with `--digivault-url` (or manifest `vault_url`) instead of requiring `--vault-root` for prod. |
| 2. Publish to Supabase | Extend `scripts/sync_architecture_vault.py` **or** new `scripts/sync_onboard_vault.py` | Same digibase connector pattern; target existing Supabase table; idempotent upsert. Legacy `sync_architecture_vault.py` runs in parallel until cutover, then **retire**. |
| 3. digisearch sink | Onboard `sinks: [vault, search]` | Same classified pages → `digithings_docs` index (replaces ad-hoc `reindex_digithings_guide.py` after cutover). |
| 4. Operator cadence | GitHub Action or manual after onboard | Re-run on doc changes + after web crawl + after repo doc ingest. |

**Explicit anti-pattern:** Pointing production digivault at `DIGIVAULT_ROOT=/data/vault` **only** for dogfood while public chat expects Supabase — creates a split brain unless every write syncs.

**MVP acceptance:** After onboard + sync, a vault-grounded question on `digithings.ai/chat` retrieves content from a **new** onboard note (e.g. a tagged OpenAPI path or monorepo `ARCHITECTURE.md`) with citation; digisearch returns the same doc for hybrid retrieval if enabled.

---

## Ordered stages (implementation)

Each stage = one PR (or ops-only step) with acceptance criteria. **Compare-and-gap** after every stage that touches user-visible behavior. **Target branch: `develop` only** until human completes Stage A.

### Stage 0 — Gate verification (no code)

- [x] `develop` contains #2028, #2029, #2030, #2031 (merged 2026-08-10).
- [ ] Stage A GHCR pulls verified; pins recorded. *(human-owned — deferred; does not block plan merge)*
- [x] Gap list doc started: `docs/projects/digithings/GAPLOG.md` (questions, missing citations, UX deltas).

**Acceptance:** Checklist signed in PR or issue comment; implementation on `develop` may start without Stage A for non-GHCR stages.

---

### Stage 1 — Auth slice (small digichat PR)

- [x] Implement **Option A** default: `DIGICHAT_REQUIRE_ROOT_AUTH=0` → `/` does not redirect to broken `/login` on operator config.
- [x] Document in `infra/digichat-digithings/README.md` + INSTALL pointer.
- [x] Operator `.env` for digithings: auth off, embed ungated.

**Acceptance:** Tunnel smoke `curl -I` on `/` and `/embed` — no `/login` redirect on dogfood config; `digithings.ai/chat` works unchanged. *(operator verify after deploy)*

**Gap check:** Any bookmarked `/login` URLs? Terminal styling on embed only — OK.

---

### Stage 2 — Client #0 project config (docs-only PR)

- [x] Add `docs/projects/digithings/` tree (README, `onboard.yaml`, `sources/*`, `indexes/docs.yaml`).
- [x] Manifest reflects locked decisions: dual-sink, both website hosts, no digiquant `/chat`.
- [x] Cross-link from `docs/digichat/CLIENT-DOCS-ONBOARD.md` and `infra/digichat-digithings/README.md`.
- [x] Deprecation note: `digithings-guide` + legacy sync scripts remain for parallel comparison until cutover; single manifest wins later.

**Acceptance:** `python scripts/docs_onboard/run_onboard.py --manifest docs/projects/digithings/onboard.yaml --dry-run` (or unit tests) validates manifest (onboard on `develop`).

---

### Stage 3 — Onboard extensions (scripts PR)

- [x] **Static file ingest:** manifest `static_sources` → classify as `docs` / `repo_doc`.
- [x] **OpenAPI ingest:** manifest `openapi_sources` → `PageClass.openapi` (new enum value) or tagged `docs` with `kind: openapi|swagger`.
- [x] **digivault API sink:** `--digivault-url` + auth if needed; idempotent upsert consistent with `Vault.write_note(overwrite=True)`.
- [x] **digisearch sink:** honor `sinks: [vault, search]`; write to `digisearch_index` from manifest.

**Acceptance:** Unit tests in `tests/scripts/docs_onboard/`; dry-run produces classified list including `docs/openapi/digigraph.json` and dual-sink routing.

---

### Stage 3b — Repo / codebase documentation ingest (scripts PR)

**New — required for dogfood.** Legacy pipeline indexed in-repo architecture docs; onboard must do the same.

- [x] Add manifest field `repo_source` (or equivalent): GitHub `{owner}/{repo}` + ref **or** local path (dogfood: this monorepo).
- [x] Fetch or scan repo for documentation patterns: `ARCHITECTURE.md`, `AGENTS.md`, `docs/**`, ADRs, component READMEs (reuse/superset `repo-docs.yaml` globs).
- [x] Classify as `repo_doc`; ingest into **both** vault and digisearch sinks.
- [x] Document generalization: any self-host client with a GitHub repo can enable the same source type.

**Acceptance:** Dry-run lists `digigraph/ARCHITECTURE.md` (or similar) from repo source; integration test ingests one file to vault + digisearch stubs.

**Gap check:** Private repo auth (PAT) for non-digithings clients — document in runbook; dogfood uses public monorepo or mounted path. (`GITHUB_TOKEN` for github kind.)

---

### Stage 4 — Supabase publish glue (scripts PR)

- [x] Publish step from onboard vault dir (or API-exported tree) → **existing Supabase notes table** using service role.
- [x] Schema evolution if needed (new columns / `note_type` for OpenAPI); migration keeps legacy rows for comparison. *(maps `page_class=openapi` → `note_type=api_reference`; no table migration required for MVP)*
- [x] Wire operator runbook: onboard → sync → smoke query.
- [x] Do **not** log secrets; dry-run mode without DB.
- [x] Document legacy parallel run: `sync_architecture_vault.py` optional during transition; retirement criteria in README.

**Acceptance:** Staging Supabase row appears for a test note; production FTS returns it after sync. *(operator apply with `CORE_SUPABASE_*` — dry-run covered in CI)*

**Gap check:** Table schema vs OpenAPI body size; wikilink / summary fields.

---

### Stage 5 — Operator stack parity (infra PR) — **blocked on Stage A (human)**

- [ ] Migrate `infra/digichat-digithings` operator host from monorepo `docker compose build` to **Profile A GHCR pulls** (`make digichat-profile-a-up` or documented equivalent) with vendored `infra/digichat-release/config/`. *(docs prepared; execution blocked on Stage A)*
- [x] Pin `DIGICHAT_VERSION` + `DIGI_IMAGE_TAG` in operator env doc. *(placeholders in `.env.profile-a.example` + digithings README; live pin after Stage A)*
- [x] Runtime embed hosts: **digithings.ai only** (per locked decision).
- [x] digisearch in operator stack if not already present for dual-sink smoke. *(documented as beside-Profile-A; not baked into stock Profile A compose)*

**Acceptance:** `docs/digichat/RELEASE-SMOKE.md` operator subset passes on GHCR pins; digigraph health + chat POST succeed; digisearch index query returns onboarded repo doc. *(blocked on Stage A images)*

**Gap check:** LiteLLM config diff vs old monorepo mounts; Redis URL footgun from README.

---

### Stage 6 — Embed CSP verification (digithings.ai only) — **de-scoped**

**Removed:** digiquant.io `/chat` Pages shell (locked: no digiquant-hosted chat).

- [x] Verify digithings-web `frame-src` / prebuild headers include digichat embed origin. *(existing `lib/security-headers.mjs` + contract tests; documented)*
- [x] Confirm CSP: parent Pages `frame-src` ↔ digichat `frame-ancestors` for **digithings.ai** (Pick 1). *(documented in infra README; live console verify on deploy)*
- [x] Document: digiquant.io remains crawl-only; future iframe parent is a separate human request.

**Acceptance:** `digithings.ai/chat` iframe loads; no CSP console errors. No `/chat` route added to digiquant-web.

---

### Stage 7 — First full onboard (ops, incremental)

- [x] Dry-run crawl against **digithings.ai + digiquant.io** allowlisted hosts (low `max_pages` first). *(scaffolding: `--dry-run --skip-crawl` + manifest hosts; live crawl needs network/operator)*
- [x] Run repo doc ingest (Stage 3b) for monorepo documentation. *(unit/dry-run covered)*
- [ ] Apply vault API writes + Supabase sync + digisearch index. *(needs operator secrets + running stack)*
- [ ] Re-run `make openapi-export` if specs drift; onboard picks up JSON files.

**Acceptance:** `OnboardResult` exit 0; sync exit 0; chat cites onboarded OpenAPI, repo `ARCHITECTURE.md`, or crawled digiquant doc. *(apply blocked on secrets)*

---

### Stage 8 — Compare-and-gap loop (repeat until ship)

Fixed questionnaire after each deploy:

| Check | Method |
|---|---|
| Grounding | 10 canonical questions (architecture, install, digiquant API, ADR, digiquant marketing copy) — record hit/miss |
| Citations | Source URL / path visible in activity panel |
| Latency | Subjective vs prior Tunnel stack |
| Embed UX | Terminal scrollback, tool calls, no login wall on **digithings.ai/chat** |
| Dual-sink | Same doc retrievable via vault FTS and digisearch (where applicable) |
| Ops | Re-run onboard idempotent; pins documented in `RELEASES.md` |
| Legacy retirement | Gap list tracks when to drop `sync_architecture_vault.py` and `reindex_digithings_guide.py` |

Update `docs/projects/digithings/GAPLOG.md`; each gap → issue or next stage.

**Scaffolding:** `GAPLOG.md` template + `scripts/dogfood_compare_harness.py --dry-run` shipped. Live ≥9/10 scoring awaits first apply + chat probes.

**Ship criterion:** ≥9/10 canonical questions grounded with correct citations; no auth regression; GHCR pins only (post Stage A); human sign-off on gap list; legacy scripts retired or explicitly scheduled.

---

## Legacy retirement path

| Legacy artifact | During transition | After cutover |
|---|---|---|
| `scripts/sync_architecture_vault.py` | Optional parallel publish from `docs/vision` for comparison | **Retire** when onboard + Supabase glue covers all vault notes |
| `docs/projects/digithings-guide/` + `reindex_digithings_guide.py` | Keep until digisearch dual-sink verified | **Retire**; `onboard.yaml` + `indexes/docs.yaml` are canonical |
| Existing Supabase rows | **Keep** for comparison | Merge or archive per human; new onboard rows are source of truth |

---

## Risks

| Risk | Mitigation |
|---|---|
| Pick PRs not on `develop` | Cleared 2026-08-10 (#2028–#2031); scripts live on `develop` |
| GHCR 404 on `main` | Stage A human-owned; Stage 5 blocked until pulls work; earlier stages use monorepo build on `develop` |
| Split brain vault (local root vs Supabase) | API write + sync publish; never prod search on unpublished local root |
| Dual corpus (legacy sync vs onboard) | Parallel only for comparison; locked decision to eventually single manifest |
| Supabase schema mismatch for OpenAPI / repo_doc bodies | Stage 4 spike; evolve table; keep legacy rows |
| Auth regression | Stage 1 first; embed-only default |
| digiquant scope creep | Crawl + corpus only; no `/chat` shell unless human reopens |
| Crawl noise (marketing pages) | `docs_path_prefixes`, classify skip, low initial `max_pages` |
| OpenAPI size limits | Split large specs per path prefix |
| Repo ingest auth (private client repos) | Document PAT in runbook; dogfood uses public repo or local mount |

---

## Related artifacts

| Doc | Role |
|---|---|
| [`docs/digichat/INSTALL.md`](../../digichat/INSTALL.md) | Client install unit |
| [`docs/digichat/CLIENT-DOCS-ONBOARD.md`](../../digichat/CLIENT-DOCS-ONBOARD.md) | Onboard runbook |
| [`docs/ops/CLIENT_PIPELINES.md`](../../ops/CLIENT_PIPELINES.md) | Pipeline index |
| [`infra/digichat-digithings/README.md`](../../../infra/digichat-digithings/README.md) | Operator Tunnel path |
| [`infra/digichat-release/`](../../../infra/digichat-release/) | Profile A compose + env |
| [`docs/openapi/README.md`](../../openapi/README.md) | OpenAPI snapshots |

---

## Appendix — draft GitHub issue (do not create until implementation starts)

```markdown
Title: [agent] dogfood digithings.ai on self-host digichat + docs_onboard (client #0)

Labels: agent-task, component:website, component:digichat, risk:med, exec:claude

## Summary

Cut over digithings.ai to the same Profile A self-host stack clients get, with corpus from `scripts/docs_onboard` (digithings.ai + digiquant.io crawl, monorepo docs, OpenAPI) into digivault + digisearch. digithings is client #0. Single chat on digithings.ai — no digiquant.io /chat page.

## Prerequisites

- #2028, #2029, #2030, #2031 merged to develop
- Plan: docs/superpowers/plans/2026-08-10-digithings-dogfood-cutover.md
- Stage A GHCR publish on main (human-owned; required before Stage 5 operator GHCR migration)

## Acceptance criteria

- [ ] Auth OFF on dogfood path; digithings.ai/chat works without /login
- [ ] Operator stack runs GHCR pins (Profile A) after Stage A, not monorepo build
- [ ] `docs/projects/digithings/onboard.yaml` drives onboard (web + repo docs + OpenAPI)
- [ ] Dual-sink: vault Supabase publish + digisearch index
- [ ] Onboard writes via digivault API; Supabase publish makes notes searchable in prod
- [ ] DIGICHAT_EMBED_HOSTS includes digithings.ai only (digiquant.io crawl-only)
- [ ] GAPLOG: ≥9/10 canonical questions grounded with citations
- [ ] Legacy sync scripts retired or scheduled; RELEASES.md / operator README updated

## Out of scope

- digiquant.io /chat embed shell; digicorpus module; live crawl in digigraph; mandatory client auth; live-trading; develop→main promotion (human)
```
