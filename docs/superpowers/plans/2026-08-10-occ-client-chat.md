# Online Compliance Center (OCC) client chat — implementation plan

> **For agentic workers:** Plan only — do **not** implement feature code from this document until the human approves the next slice. OCC is **client #1** after digithings dogfood (client #0) validates the shared pipeline.
>
> **Status:** Draft (2026-08-10) — awaiting dogfood prerequisite ([#2037](https://github.com/digithings-ai/digithings/pull/2037) / [#2036](https://github.com/digithings-ai/digithings/issues/2036)).
> **Parent program:** [`2026-08-10-digithings-dogfood-cutover.md`](./2026-08-10-digithings-dogfood-cutover.md)
> **Client scope:** [`docs/projects/online-compliance-center/SCOPE.md`](../../projects/online-compliance-center/SCOPE.md)

---

## Goal

Ship **OCC help-center chat** on **`https://digithings.ai/chat/occ`** — same digichat UX and operator stack as **`https://digithings.ai/chat`**, but grounded on the **OCC corpus** (help.online-compliance-center.com help center + PDFs) via **docs_onboard → digivault + digisearch**, not the digithings/digiquant documentation vault.

| URL | Corpus | Purpose |
|-----|--------|---------|
| `digithings.ai/chat` | digithings + digiquant docs (client #0) | Unchanged — dogfood / public digithings assistant |
| `digithings.ai/chat/occ` | OCC help center (`occ_help` index + OCC vault subdir) | First external client deploy on shared digithings.ai host |

**Locked by human:** OCC chat lives under **digithings.ai** (ADR-0018 path model). There is **no** separate OCC chat hostname and **no** digiquant-style second chat site.

---

## Non-goals

- A second digichat Node image, digichat fork, or OCC-specific chat backend.
- Crawling `demo.online-compliance-center.com` or `portal.online-compliance-center.com` in v1.
- YouTube e-learning ingest in v1 (~14 videos; out of scope per SCOPE).
- Live crawl tools inside digigraph (onboard stays offline ops).
- develop → main promotion or GHCR publish (human-owned; same as dogfood Stage A).
- Touching live-trading paths.
- Replacing digithings `/chat` corpus or merging OCC into the digithings manifest.

---

## Prerequisites (hard gate)

### 1. Dogfood lands first ([#2037](https://github.com/digithings-ai/digithings/pull/2037))

Assume merged on `develop` before OCC implementation starts:

| Capability | Why OCC needs it |
|------------|------------------|
| Auth Option A (`DIGICHAT_REQUIRE_ROOT_AUTH=0`, ungated `/embed`) | Same public chat pattern for `/chat/occ` |
| `scripts/docs_onboard/` extensions (static, OpenAPI, repo, dual-sink, digivault API) | OCC uses the same pipeline |
| `scripts/sync_onboard_vault.py` Supabase publish glue | Production vault FTS for OCC notes |
| Runtime `DIGICHAT_EMBED_HOSTS` / `DIGICHAT_EMBED_TENANTS` (#2031) | CSP without image rebuild |
| `docs/projects/digithings/` dogfood manifest + operator runbook | Pattern to copy for OCC |

**Gate rule:** Do not open OCC implementation PRs until #2037 is merged and dogfood dry-run is green on `develop`.

### 2. Pipeline dry-run OK (OCC manifest)

Per [`SCOPE.md`](../../projects/online-compliance-center/SCOPE.md) dry-run plan:

- [ ] `scrape_site` on `help.online-compliance-center.com` only (~10 HTML paths, ~24 PDFs).
- [ ] `classify_pages` + `fetch_docs` — accordion HTML and PDF text extraction reviewed.
- [ ] Optional temp `write_vault_notes` spot-check under `clients/online-compliance-center`.
- [ ] **Defer** production `write_search_index` + Supabase sync until sitaas crawl approval.

### 3. sitaas crawl approval (human)

Written approval to index `help.online-compliance-center.com` (SCOPE open question #1). Manifest carries an explicit ingest hold until this clears.

### 4. Operator secrets (same host as dogfood)

- Cloudflare Tunnel → digichat Node (`NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN`).
- `CORE_SUPABASE_*` for vault publish (shared notes table; OCC rows under `clients/online-compliance-center/` paths).
- digisearch reachable from digigraph (`DIGISEARCH_URL`).
- LLM keys, `DIGIKEY_BFF_TOKEN`, `AUTH_SECRET`.

---

## Routing discovery (affects design)

### Current `/chat` stack (unchanged for digithings)

```text
Browser digithings.ai/chat
  → frontend/digithings-web/app/chat/page.tsx (DtNav + iframe)
  → ${NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN}/embed?host=digithings.ai&layout=page
  → digichat POST /api/chat (X-Embed-Host: digithings.ai)
  → digigraph → digillm + digivault hub (+ digisearch when configured)
```

References: [`infra/digichat-digithings/README.md`](../../../infra/digichat-digithings/README.md), [`docs/adr/0018-digichat-path-routing.md`](../../adr/0018-digichat-path-routing.md), [`frontend/digithings-web/components/ChatEmbedShell.tsx`](../../../frontend/digithings-web/components/ChatEmbedShell.tsx).

| Layer | Mechanism | OCC implication |
|-------|-----------|-----------------|
| **Pages parent** | Static shell + iframe; CSP `frame-src` from `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN` at prebuild | `/chat/occ` is a **second Pages route** — same `frame-src`; no CSP change |
| **Embed tenant** | `DIGICHAT_EMBED_TENANTS` JSON keyed by **hostname** → `slug`, `backend`, UI flags | `/chat` and `/chat/occ` share parent origin `digithings.ai` but need **different tenant slugs** |
| **CSP frame-ancestors** | digichat `DIGICHAT_EMBED_HOSTS` (runtime) | Still `digithings.ai` only — OCC does not add a new parent domain |
| **Corpus selection** | digigraph loads **one** `digiproject.yaml` / `DIGISEARCH_INDEX` today; vault FTS is **not** index-scoped | **New slice required:** per-tenant corpus routing (see Architecture) |

### Smallest path to `/chat/occ` without forking digichat

**Recommendation: virtual first-party embed host + parameterized Pages shell.**

1. **Pages:** Add `frontend/digithings-web/app/chat/occ/page.tsx` reusing `ChatEmbedShell` with `embedHostKey="occ.digithings.ai"` (new prop) instead of hardcoded `digithings.ai`.
2. **digichat registry:** Add a second first-party tenant entry (no new DNS):

```bash
# DIGICHAT_EMBED_TENANTS excerpt (runtime env — not a build-arg)
{
  "digithings.ai": {
    "slug": "digithings",
    "aliases": ["www.digithings.ai"],
    "gateMode": "ungated",
    "layout": "page",
    "activityDetail": "full",
    "token": "<first-party>",
    "backend": { "type": "digigraph" }
  },
  "occ.digithings.ai": {
    "slug": "occ",
    "gateMode": "ungated",
    "layout": "page",
    "activityDetail": "full",
    "title": "OCC help assistant",
    "welcome": "Ask about Online Compliance Center policies, procedures, and help articles.",
    "token": "<first-party>",
    "backend": {
      "type": "digigraph",
      "digisearchIndex": "occ_help",
      "vaultPathPrefix": "clients/online-compliance-center"
    }
  }
}
```

3. **First-party allowlist:** Extend `FIRST_PARTY_EMBED_HOSTS` in `frontend/digichat/src/lib/embed-first-party.ts` with `occ.digithings.ai` so the iframe works without `?token=` (same pattern as #1866 for `digithings.ai`).
4. **Iframe URL:** `/embed?host=occ.digithings.ai&layout=page` — `X-Embed-Host` resolves to OCC tenant slug `occ`.

**Why not path-only (`?tenant=occ` on same host)?** Viable alternative (one registry entry, slug query param). Virtual host avoids new digichat resolution rules and matches the existing host-keyed registry. Pick one in Stage 3; virtual host is fewer moving parts.

**Why not a second digichat deploy?** Human locked single operator stack; embed multi-tenancy already exists for external clients.

---

## Architecture

### Single deploy, path-based entry, tenant-based corpus

```text
digithings.ai/chat          → embed host digithings.ai  → tenant slug digithings → corpus digithings_docs
digithings.ai/chat/occ      → embed host occ.digithings.ai → tenant slug occ       → corpus occ_help
         │                              │                           │
         └──────── same digichat Node ──┴── same digigraph stack ───┘
```

| Concern | Approach |
|---------|----------|
| **UI** | One digichat GHCR image; per-tenant theme/title/welcome via embed registry |
| **Auth** | Ungated `/embed` (Option A); digikey BFF session keyed by `tenantSlug` (`digithings` vs `occ`) |
| **digisearch** | Per-tenant `default_index_name` from embed backend config → `X-Digi-Tenant` + header or `DIGI_TENANT_CORPUS_MAP` in digigraph |
| **digivault** | Onboard writes `vault_subdir: clients/online-compliance-center`; digigraph passes `vaultPathPrefix` to digivault search (new optional filter) or tags notes `client:occ` until RPC supports prefix |
| **Supabase** | Same notes table; path prefix distinguishes corpora; publish via `sync_onboard_vault.py` after onboard |
| **Isolation acceptance** | OCC questions must not cite digithings `ARCHITECTURE.md`; digithings `/chat` must not cite OCC-only PDFs |

### Corpus routing slice (new — not in dogfood #2037)

Dogfood assumes **one** corpus per digigraph instance. OCC needs a small cross-cutting extension:

| Component | Change (smallest) |
|-----------|-------------------|
| `frontend/digichat` `EmbedBackendConfig` | Optional `digisearchIndex`, `vaultPathPrefix` on `digigraph` backend |
| `frontend/digichat` `/api/chat` | Forward `X-Digi-Corpus-Index` / `X-Digi-Vault-Prefix` when set on tenant backend |
| `digigraph` research + digisearch hub | Honor corpus headers or `DIGI_TENANT_CORPUS_MAP[tenant_slug]` for `default_index_name` |
| `digivault` `digivault_search_notes` | Optional `path_prefix` argument; filter Supabase/local hits |

Fallback until vault prefix lands: OCC tenant uses **digisearch-only** grounding (`occ_help`); digivault tool disabled or prefix-filtered in digigraph for `occ` slug.

---

## Project config — `docs/projects/online-compliance-center/`

Already on `develop` (draft):

| File | Role |
|------|------|
| [`SCOPE.md`](../../projects/online-compliance-center/SCOPE.md) | Go-with-gaps verdict, volume, gaps, open questions |
| [`onboard.yaml`](../../projects/online-compliance-center/onboard.yaml) | Crawl manifest — **ingest hold** until approvals |

Proposed additions during implementation:

```text
docs/projects/online-compliance-center/
  README.md              # operator notes: tenant slug, index name, embed host, refresh cadence
  onboard.yaml           # (exists) primary manifest
  indexes/
    occ_help.yaml          # digisearch index manifest (mirrors digithings indexes/docs.yaml)
  GAPLOG.md                # compare-and-gap after first deploy
```

### `indexes/occ_help.yaml` (shape)

```yaml
index_name: occ_help
backend: azure_search   # or local per operator
description: |
  Online Compliance Center public help center (Joomla HTML + PDFs).
  Grounding corpus for digithings.ai/chat/occ.
sources: []   # populated by onboard sink, not static globs
```

---

## Ordered stages (implementation)

Each stage = one PR (or ops step) with acceptance criteria. **Target branch: `develop` only.**

### Stage 0 — Gate verification (no code)

- [ ] #2037 merged; dogfood manifest dry-run passes on `develop`.
- [ ] OCC `SCOPE.md` + `onboard.yaml` present on `develop`.
- [ ] sitaas crawl approval recorded (issue comment or client email on file).
- [ ] OCC dry-run steps 1–3 from SCOPE completed; gap list in `GAPLOG.md`.

**Acceptance:** Human sign-off on dry-run output; ingest hold may be lifted.

---

### Stage 1 — Project config finalize (docs PR)

- [ ] Add `README.md`, `indexes/occ_help.yaml`, `GAPLOG.md` under `docs/projects/online-compliance-center/`.
- [ ] Cross-link from `docs/digichat/CLIENT-DOCS-ONBOARD.md` and `docs/ops/CLIENT_PIPELINES.md`.
- [ ] Confirm manifest: `digisearch_index: occ_help`, `vault_subdir: clients/online-compliance-center`, help host only.

**Acceptance:** `python scripts/docs_onboard/run_onboard.py --manifest docs/projects/online-compliance-center/onboard.yaml --dry-run` validates.

---

### Stage 2 — Onboard run → OCC vault + digisearch (ops)

- [ ] Run full onboard (after approval): crawl → classify → fetch → dual-sink.
- [ ] Vault API upsert + `sync_onboard_vault.py` → Supabase.
- [ ] digisearch index `occ_help` populated; query returns known FAQ/PDF snippet.
- [ ] Idempotent re-run documented.

**Acceptance:** `OnboardResult` exit 0; digisearch `POST /query` with `index_name=occ_help` hits onboarded doc; Supabase row exists under `clients/online-compliance-center/`.

**Gap check:** Accordion markdown quality; sitemap 500; rate limits during crawl.

---

### Stage 3 — Corpus routing + embed tenant (digichat + digigraph PR)

- [ ] Extend `EmbedBackendConfig` for digigraph corpus fields (see Architecture).
- [ ] Add `occ.digithings.ai` tenant to operator env docs; extend first-party allowlist.
- [ ] digigraph per-tenant index/prefix routing (header or env map).
- [ ] digivault optional `path_prefix` on search (or interim digisearch-only for `occ`).

**Acceptance:**

- `curl` embed chat with `X-Embed-Host: occ.digithings.ai` resolves `tenantSlug=occ`.
- digigraph tool calls use `index_name=occ_help` for OCC tenant.
- digithings tenant still uses `digithings_docs` / full vault.

---

### Stage 4 — digithings.ai route `/chat/occ` (digithings-web PR)

- [ ] Parameterize `ChatEmbedShell` (`embedHost` prop; default `digithings.ai` for backward compat).
- [ ] Add `app/chat/occ/page.tsx` with OCC metadata (title, description).
- [ ] Optional: `DtNav` link or footer discoverability (human UX approval).
- [ ] No CSP change — same `frame-src` origin.

**Acceptance:** `digithings.ai/chat/occ` iframe loads; no CSP console errors; `/chat` unchanged.

---

### Stage 5 — Smoke + compare-and-gap

| Check | Method |
|-------|--------|
| OCC grounding | 10 canonical OCC questions (FAQ topic, named PDF policy) — hit/miss |
| Isolation | digithings `/chat` does not cite OCC-only sources; OCC does not cite digigraph ARCHITECTURE |
| Citations | Activity panel shows help URL or PDF source |
| Embed UX | No login wall; terminal scrollback; tool calls visible |
| Dual-sink | Same doc in digisearch + vault (where applicable) |
| Ops | Re-onboard idempotent; operator README updated |

**Acceptance:** ≥8/10 OCC canonical questions grounded (target ≥9 after gap fixes); human sign-off.

---

### Stage 6 — Optional hardening (follow-up PRs)

From SCOPE gaps — not blocking first deploy:

- [ ] Polite crawl rate limits in `scrape_site` for production re-crawl.
- [ ] Accordion HTML → cleaner markdown post-processor.
- [ ] `DIGISEARCH_OCR_ENABLED` verification on scanned PDFs (if any lack text layers).
- [ ] Scheduled re-crawl (GitHub Action or operator cron).
- [ ] E-learning / YouTube policy (v2).
- [ ] Marketing site `online-compliance-center.com` phase-2 manifest.

---

## Open questions

| # | Topic | Default / recommendation |
|---|-------|--------------------------|
| 1 | **Tenant slug** | `occ` (embed registry) vs `online-compliance-center` (manifest client key) — use `occ` for digikey/digichat; manifest keeps `client: online-compliance-center` |
| 2 | **digisearch index name** | `occ_help` per draft manifest — confirm with sitaas |
| 3 | **Battlecards** | Exclude unless explicitly linked from help and approved (SCOPE #4) |
| 4 | **E-learning** | Defer v1; document exclusion in welcome text if users ask about videos |
| 5 | **Refresh cadence** | Start manual post-help-center updates; automate after first stable deploy |
| 6 | **Virtual host vs `?tenant=`** | Prefer `occ.digithings.ai` embed host key; revisit if registry clutter grows |
| 7 | **Vault prefix filter** | Required for strict isolation; digisearch-only acceptable for MVP smoke |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Dogfood not merged | Hard gate Stage 0; no OCC code until #2037 lands |
| Corpus bleed (digithings ↔ OCC) | Per-tenant index + vault prefix; isolation smoke in Stage 5 |
| Crawl without approval | Ingest hold in manifest + Stage 0 human gate |
| Joomla accordion noise | Dry-run review; classification tuning; optional post-process |
| Sitemap 500 | BFS from seed + PDF link extraction |
| Single digigraph config | Corpus routing slice in Stage 3 — explicit PR, not ad-hoc env hacks |
| Shared rate limits on embed | Separate `tenantSlug` buckets (`digithings` vs `occ`) already isolate BFF limits |

---

## Related artifacts

| Doc | Role |
|-----|------|
| [`docs/projects/online-compliance-center/SCOPE.md`](../../projects/online-compliance-center/SCOPE.md) | Client reconnaissance + gaps |
| [`docs/projects/online-compliance-center/onboard.yaml`](../../projects/online-compliance-center/onboard.yaml) | Crawl manifest |
| [`docs/superpowers/plans/2026-08-10-digithings-dogfood-cutover.md`](./2026-08-10-digithings-dogfood-cutover.md) | Prerequisite program |
| [`docs/digichat/CLIENT-DOCS-ONBOARD.md`](../../digichat/CLIENT-DOCS-ONBOARD.md) | Operator runbook |
| [`infra/digichat-digithings/README.md`](../../../infra/digichat-digithings/README.md) | Tunnel + embed env |
| [`frontend/digichat/ARCHITECTURE.md`](../../../frontend/digichat/ARCHITECTURE.md) | Embed tenant registry |
| [`docs/adr/0018-digichat-path-routing.md`](../../adr/0018-digichat-path-routing.md) | `/chat` path model |

---

## Appendix — draft GitHub issue (do not create until implementation starts)

```markdown
Title: [agent] OCC client chat on digithings.ai/chat/occ

Labels: agent-task, component:website, component:digichat, component:digigraph, risk:med

## Summary

Add Online Compliance Center as client #1: docs_onboard corpus from help.online-compliance-center.com into occ_help + OCC vault subdir; expose ungated chat at digithings.ai/chat/occ on the shared digichat/digigraph stack with per-tenant corpus isolation.

## Prerequisites

- #2037 merged (dogfood client #0)
- Plan: docs/superpowers/plans/2026-08-10-occ-client-chat.md
- sitaas crawl approval
- OCC onboard dry-run reviewed

## Acceptance criteria

- [ ] docs/projects/online-compliance-center/ finalized; onboard applied to vault + digisearch
- [ ] digithings.ai/chat/occ loads digichat embed (OCC tenant)
- [ ] OCC questions ground on help/PDF corpus only
- [ ] digithings.ai/chat unchanged (digithings corpus)
- [ ] Operator README + GAPLOG updated
- [ ] No develop→main promotion in this task

## Out of scope

- demo/portal hosts; YouTube e-learning v1; second digichat deploy; GHCR publish
```
