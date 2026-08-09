# digithings dogfood cutover — implementation plan

> **For agentic workers:** Plan only — do **not** implement from this document until the wait-for-merge gate clears. After gate: use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task.
>
> **Status:** Draft 2026-08-10 — dogfood digithings.ai as self-host client #0.
> **Parent program:** [`2026-08-09-digichat-self-host-picks-metaplan.md`](./2026-08-09-digichat-self-host-picks-metaplan.md)
> **Fit contracts:** [`digichat-self-host-picks-fit.md`](../../architecture/digichat-self-host-picks-fit.md)

---

## Goal

Make **digithings.ai** client **#0** for the same self-hosted digichat + Profile A stack clients install, with corpus grounded via the **docs_onboard** ops pipeline (plus repo-local sources and OpenAPI specs). Sales story: *our public chat is the product we ship*.

**digiquant.io** is the same chat scope — a second embed parent / subdomain in the **same** digithings tenant, vault, and corpus — not a separate product or second onboard manifest.

Deliver incrementally: deploy a slice, compare to the current production chat, record gaps, iterate.

---

## Non-goals

- A second digichat app, digicorpus module, or digiquant-specific chat backend.
- Live crawl tools inside digigraph (onboard stays offline ops beside the stack).
- Rebuilding the terminal chat UI or a large auth redesign.
- Client-default auth ON — dogfood and most installs stay **ungated** on `/embed`.
- Replacing Cloudflare Pages + Tunnel operator topology with a new hosting model.
- Merging Pick 1 / Pick 2 / Pick 3 implementation PRs into one dogfood PR.
- Touching live-trading paths.

---

## Prerequisites (hard gate — no implementation before these)

### 1. Wait-for-merge: PRs #2028–#2031 on `develop`

| PR | Title (short) | State (2026-08-10) | Needed for dogfood |
|---|---|---|---|
| [#2028](https://github.com/digithings-ai/digithings/pull/2028) | Self-host picks meta-plan | **MERGED** | Plans + sequencing |
| [#2029](https://github.com/digithings-ai/digithings/pull/2029) | Profile A GHCR pull | **MERGED** | `compose.profile-a.yml` pull-not-build |
| [#2030](https://github.com/digithings-ai/digithings/pull/2030) | docs_onboard + digivault local search | **OPEN** | `scripts/docs_onboard/`, runbook |
| [#2031](https://github.com/digithings-ai/digithings/pull/2031) | Runtime CSP frame-ancestors | **MERGED** | `DIGICHAT_EMBED_HOSTS` without rebuild |

**Gate rule:** Do not start dogfood **implementation** until **#2030 is merged to `develop`** (and local `develop` is pulled). #2028 / #2029 / #2031 are already on `develop`.

### 2. Stage A — GHCR stack images pullable (Pick 2 ops)

From fit doc §5 / metaplan Stage A:

- [ ] Normal **develop → main** promotion includes publish workflow commit (`#2023` lineage).
- [ ] Run `Publish: service images` (`service=all`) on `main`.
- [ ] Verify `docker pull ghcr.io/digithings-ai/{digikey,digigraph,digivault}:sha-…`.
- [ ] Record `DIGI_IMAGE_TAG` pin for digithings operator env.

Without Stage A, Profile A “pull not build” cannot smoke on the operator host (packages 404 today).

### 3. Operator secrets (human-held)

- Cloudflare Tunnel hostname → digichat Node (`NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN`).
- `CORE_SUPABASE_URL` + `CORE_SUPABASE_SERVICE_KEY` (or ADR-0022 fallbacks) for vault **publish** to Supabase.
- LLM provider keys for LiteLLM profile in `infra/digichat-release/config/`.
- `DIGIKEY_BFF_TOKEN`, `AUTH_SECRET` (digichat DB / BFF — even when root auth is OFF).

---

## Current baseline (what we compare against)

| Layer | Today | Reference |
|---|---|---|
| **Pages shell** | `frontend/digithings-web/app/chat/page.tsx` → iframe `/embed?host=digithings.ai` | `infra/digichat-digithings/README.md` |
| **digichat Node** | Operator Docker Compose (`--profile digichat --profile digivault`), often **monorepo build** | Same README |
| **Backend** | digigraph → LiteLLM; `digivault_hub` → digivault :8004 | INSTALL Profile A |
| **Vault read path** | Production digivault search: **Supabase FTS** when `DIGIVAULT_ROOT` unset | `digivault/ARCHITECTURE.md` |
| **Vault write path (legacy)** | `scripts/sync_architecture_vault.py` — `docs/vision` vault → `architecture_notes` | CI / operator |
| **Repo docs index (parallel)** | `docs/projects/digithings-guide/` + `scripts/reindex_digithings_guide.py` → **digisearch** | Not the primary digivault chat path today |
| **OpenAPI** | `docs/openapi/*.json` (FastAPI export + authored `digichat.json`) | `docs/openapi/README.md` |
| **Embed CSP** | Runtime `DIGICHAT_EMBED_HOSTS` / tenants (after #2031) | `frontend/digichat/src/proxy.ts` |
| **Auth** | `/` → `auth()` → redirect `/login`; `/embed` uses tenant `gateMode: ungated` | `frontend/digichat/src/app/page.tsx` |
| **digiquant.io** | Marketing site; **no `/chat` embed shell yet** | `frontend/digiquant-web/` |

Dogfood success = same user-visible chat quality (grounding, citations, terminal UX on embed) on **stock GHCR pins** + **onboard-driven corpus**, with digiquant.io as an additional embed parent when we add the shell.

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
    repo-docs.yaml          # optional: globs → static file ingest (extends reindex list)
    openapi.yaml            # optional: explicit OpenAPI file list
  indexes/                  # optional later: digisearch index manifest if dual-sink
    docs.yaml
```

### `onboard.yaml` shape (extends example manifest)

```yaml
client: digithings
# Web crawl — public marketing + docs site (not the whole internet)
seed_url: https://digithings.ai/
allowed_hosts:
  - digithings.ai
  - www.digithings.ai
  - digiquant.io
  - www.digiquant.io
max_pages: 200
max_depth: 4
sinks: [vault]                    # dogfood primary: digivault → Supabase publish
digisearch_index: digithings_docs # only if dual-sink enabled later
vault_subdir: clients/digithings
docs_path_prefixes: ["/docs", "/chat", "/modules", "/architecture"]
skip_path_prefixes: ["/blog", "/careers", "/legal"]

# --- extensions (implementation adds schema fields) ---
static_sources: docs/projects/digithings/sources/repo-docs.yaml
openapi_sources: docs/projects/digithings/sources/openapi.yaml
```

### `sources/repo-docs.yaml` (static files)

Reuse and **superset** `docs/projects/digithings-guide/indexes/docs.yaml` globs:

- Root + component `ARCHITECTURE.md`, `AGENTS.md`, `README.md`, ADRs, `docs/VISION.md`, etc.
- **Include** `docs/digichat/INSTALL.md`, `docs/openapi/README.md`, release/smoke docs added by self-host program.

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

Align with `infra/digichat-digithings/README.md` but add digiquant hosts:

```bash
DIGICHAT_EMBED_HOSTS=digithings.ai,www.digithings.ai,digiquant.io,www.digiquant.io
DIGICHAT_EMBED_TENANTS='{"digithings.ai":{"slug":"digithings","aliases":["www.digithings.ai","digiquant.io","www.digiquant.io"],"gateMode":"ungated",...,"backend":{"type":"digigraph"}}}'
```

---

## Supabase vault sink (production)

**Locked decision:** Production dogfood must use the **same Supabase-backed vault** as today — not a standalone operator `DIGIVAULT_ROOT` that diverges from what `digivault_search_notes` reads when unset.

**Read path (unchanged):** digivault service with **no** `DIGIVAULT_ROOT` → `SupabaseStore.search()` / `search_architecture_notes` RPC.

**Write path (target — two-step, smallest safe):**

```text
scripts/docs_onboard/run_onboard.py
  → write notes via digivault HTTP API (POST /v1/notes) into operator filesystem vault
  → scripts/sync_* publishes to Supabase (service role, idempotent upsert)
```

| Step | Mechanism | Notes |
|---|---|---|
| 1. Upsert notes | **digivault API** `POST /v1/notes` (`digivault/src/digivault/server.py`) | Extend `write_vault_notes.py` with `--digivault-url` (or manifest `vault_url`) instead of requiring `--vault-root` for prod. |
| 2. Publish to Supabase | Extend `scripts/sync_architecture_vault.py` **or** new `scripts/sync_onboard_vault.py` | Same digibase connector pattern; target table/RPC must match production FTS (`architecture_notes` today — **confirm with human**). |
| 3. Operator cadence | GitHub Action or manual after onboard | Re-run on doc changes + after web crawl. |

**Explicit anti-pattern:** Pointing production digivault at `DIGIVAULT_ROOT=/data/vault` **only** for dogfood while public chat expects Supabase — creates a split brain unless every write syncs.

**MVP acceptance:** After onboard + sync, a vault-grounded question on `digithings.ai/chat` retrieves content from a **new** onboard note (e.g. a tagged OpenAPI path) with citation.

---

## Ordered stages (implementation)

Each stage = one PR (or ops-only step) with acceptance criteria. **Compare-and-gap** after every stage that touches user-visible behavior.

### Stage 0 — Gate verification (no code)

- [ ] `develop` contains #2028, #2029, #2030, #2031.
- [ ] Stage A GHCR pulls verified; pins recorded.
- [ ] Gap list doc started: `docs/projects/digithings/GAPLOG.md` (questions, missing citations, UX deltas).

**Acceptance:** Checklist signed in PR or issue comment; no dogfood code merged before this.

---

### Stage 1 — Auth slice (small digichat PR)

- [ ] Implement **Option A** default: `DIGICHAT_REQUIRE_ROOT_AUTH=0` → `/` does not redirect to broken `/login` on operator config.
- [ ] Document in `infra/digichat-digithings/README.md` + INSTALL pointer.
- [ ] Operator `.env` for digithings: auth off, embed ungated.

**Acceptance:** Tunnel smoke `curl -I` on `/` and `/embed` — no `/login` redirect on dogfood config; `digithings.ai/chat` works unchanged.

**Gap check:** Any bookmarked `/login` URLs? Terminal styling on embed only — OK.

---

### Stage 2 — Client #0 project config (docs-only PR)

- [ ] Add `docs/projects/digithings/` tree (README, `onboard.yaml`, `sources/*`).
- [ ] Cross-link from `docs/digichat/CLIENT-DOCS-ONBOARD.md` and `infra/digichat-digithings/README.md`.
- [ ] Deprecation note: `digithings-guide` remains until cutover completes; single manifest wins later.

**Acceptance:** `python scripts/docs_onboard/run_onboard.py --manifest docs/projects/digithings/onboard.yaml --dry-run` (or unit tests) validates manifest once #2030 lands.

---

### Stage 3 — Onboard extensions (scripts PR, after #2030)

- [ ] **Static file ingest:** manifest `static_sources` → classify as `docs` / `repo_doc`.
- [ ] **OpenAPI ingest:** manifest `openapi_sources` → `PageClass.openapi` (new enum value) or tagged `docs` with `kind: openapi|swagger`.
- [ ] **digivault API sink:** `--digivault-url` + auth if needed; idempotent upsert consistent with `Vault.write_note(overwrite=True)`.

**Acceptance:** Unit tests in `tests/scripts/docs_onboard/`; dry-run produces classified list including `docs/openapi/digigraph.json`.

---

### Stage 4 — Supabase publish glue (scripts PR)

- [ ] Publish step from onboard vault dir (or API-exported tree) → Supabase using service role.
- [ ] Wire operator runbook: onboard → sync → smoke query.
- [ ] Do **not** log secrets; dry-run mode without DB.

**Acceptance:** Staging Supabase row appears for a test note; production FTS returns it after sync.

**Gap check:** Table schema vs `architecture_notes` columns; wikilink / summary fields.

---

### Stage 5 — Operator stack parity (infra PR)

- [ ] Migrate `infra/digichat-digithings` operator host from monorepo `docker compose build` to **Profile A GHCR pulls** (`make digichat-profile-a-up` or documented equivalent) with vendored `infra/digichat-release/config/`.
- [ ] Pin `DIGICHAT_VERSION` + `DIGI_IMAGE_TAG` in operator env doc.
- [ ] Runtime embed hosts include digithings + digiquant (Stage 6 can add Pages shell).

**Acceptance:** `docs/digichat/RELEASE-SMOKE.md` operator subset passes on GHCR pins; digigraph health + chat POST succeed.

**Gap check:** LiteLLM config diff vs old monorepo mounts; Redis URL footgun from README.

---

### Stage 6 — Embed parents (website PR)

- [ ] **digiquant.io:** add `/chat` Pages shell mirroring digithings-web (`ChatEmbedShell`, `host=digiquant.io` or shared tenant).
- [ ] `digiquant-web` `frame-src` / prebuild headers include digichat embed origin.
- [ ] Confirm CSP: parent Pages `frame-src` ↔ digichat `frame-ancestors` (Pick 1).

**Acceptance:** iframe loads on both origins; no CSP console errors.

---

### Stage 7 — First full onboard (ops, incremental)

- [ ] Dry-run crawl against allowlisted hosts (low `max_pages` first).
- [ ] Apply vault API writes + Supabase sync.
- [ ] Re-run `make openapi-export` if specs drift; onboard picks up JSON files.

**Acceptance:** `OnboardResult` exit 0; sync exit 0; chat cites onboarded OpenAPI or repo doc.

---

### Stage 8 — Compare-and-gap loop (repeat until ship)

Fixed questionnaire after each deploy:

| Check | Method |
|---|---|
| Grounding | 10 canonical questions (architecture, install, digiquant API, ADR) — record hit/miss |
| Citations | Source URL / path visible in activity panel |
| Latency | Subjective vs prior Tunnel stack |
| Embed UX | Terminal scrollback, tool calls, no login wall |
| digiquant parity | Same answers on digiquant.io/chat iframe |
| Ops | Re-run onboard idempotent; pins documented in `RELEASES.md` |

Update `docs/projects/digithings/GAPLOG.md`; each gap → issue or next stage.

**Ship criterion:** ≥9/10 canonical questions grounded with correct citations; no auth regression; GHCR pins only; human sign-off on gap list.

---

## Risks

| Risk | Mitigation |
|---|---|
| #2030 delayed | Hard gate; dogfood scripts depend on `run_onboard.py` |
| GHCR 404 on `main` | Stage A before Profile A migration |
| Split brain vault (local root vs Supabase) | API write + sync publish; never prod search on unpublished local root |
| Dual corpus (`sync_architecture_vault` vs onboard) | Stage 2 documents merge path; eventually single `docs/projects/digithings` manifest |
| `architecture_notes` schema mismatch for OpenAPI bodies | Stage 4 spike; may need `note_type` / JSON body column |
| Auth regression | Stage 1 first; embed-only default |
| digiquant scope creep | Same tenant + manifest; only embed host differs |
| Crawl noise (marketing pages) | `docs_path_prefixes`, classify skip, low initial `max_pages` |
| OpenAPI size limits | Split large specs per path prefix |

---

## Open questions (human)

1. **Supabase table:** Keep all dogfood notes in `architecture_notes`, or a parallel table / `client` partition field? (Blocks Stage 4 schema.)
2. **digithings.ai crawl scope:** Crawl only `digithings.ai`, or also off-site docs (e.g. GitHub Pages docs subdomain)? Allowed hosts list in manifest needs confirmation.
3. **digisearch dual-sink:** Enable `sinks: [vault, search]` for dogfood now, or vault-only until digisearch is in operator stack?
4. **Operator host:** Same machine as today’s Compose, or new Profile A host? Affects Tunnel target only.
5. **digiquant.io `/chat`:** Ship in Stage 6, or defer until digithings.ai gap loop is green?
6. **Legacy `docs/vision` sync:** Retire `sync_architecture_vault.py` after cutover, or run both during transition?
7. **Auth follow-up:** If Option B (digikey OIDC) is wanted for a specific client, which IdP and timeline? (Not blocking dogfood.)
8. **Stage A timing:** Who promotes develop→main for first GHCR publish — coordinated with this program or separate ops?

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

Cut over digithings.ai (and digiquant.io embed parent) to the same Profile A self-host stack clients get, with corpus from `scripts/docs_onboard` and Supabase vault publish. digithings is client #0.

## Prerequisites

- #2028, #2029, #2030, #2031 merged to develop
- Stage A GHCR publish on main (pullable digikey/digigraph/digivault)
- Plan: docs/superpowers/plans/2026-08-10-digithings-dogfood-cutover.md

## Acceptance criteria

- [ ] Auth OFF on dogfood path; digithings.ai/chat and digiquant.io/chat (if shipped) work without /login
- [ ] Operator stack runs GHCR pins (Profile A), not monorepo build
- [ ] `docs/projects/digithings/onboard.yaml` drives onboard (web + repo files + OpenAPI)
- [ ] Onboard writes via digivault API; Supabase publish makes notes searchable in prod
- [ ] DIGICHAT_EMBED_HOSTS includes digithings.ai + digiquant.io
- [ ] GAPLOG: ≥9/10 canonical questions grounded with citations
- [ ] RELEASES.md / operator README updated with pins and run order

## Out of scope

- digicorpus module; live crawl in digigraph; mandatory client auth; live-trading
```
