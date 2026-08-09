# digichat self-host picks — fit comparison

> Synthesis of the three follow-ups from [`digichat-self-hosted-release.md`](digichat-self-hosted-release.md) §5. Plans live under `docs/superpowers/plans/` (plan branches: `docs/plan-runtime-frame-ancestors`, `docs/plan-stack-ghcr`, `docs/plan-corpus-ingest`).

**Date:** 2026-08-09

---

## 1. One-sentence purpose

| Pick | Plan | Purpose |
|---|---|---|
| **1** | Runtime CSP (plan branch `docs/plan-runtime-frame-ancestors`) | Let operators allow any client embed parent on the **stock** digichat GHCR image via **runtime** env (`DIGICHAT_EMBED_HOSTS` / tenant host keys), without rebuilding for CSP. Gap: [`digichat-self-hosted-release.md`](digichat-self-hosted-release.md) §5. |
| **2** | Stack GHCR (plan branch `docs/plan-stack-ghcr`) | Finish Profile A so clients **pull** digikey / digigraph / digivault from GHCR (no monorepo `docker compose build`), including glue after [#2023](https://github.com/digithings-ai/digithings/pull/2023). Gap: [`digichat-self-hosted-release.md`](digichat-self-hosted-release.md) §5. |
| **3** | [`2026-08-09-digichat-corpus-ingest.md`](../superpowers/plans/2026-08-09-digichat-corpus-ingest.md) | Offline **ops** pipeline (`scripts/docs_onboard/`) — URL → docs-focused crawl → PDFs via digifetch/digisearch → **their** digivault and/or digisearch index so Profile A digichat → digigraph tools ground answers on that client's docs. Not a digicorpus peer module. |

Sketch gaps these close (from [`digichat-self-hosted-release.md`](digichat-self-hosted-release.md) §5 Still open): runtime CSP `frame-ancestors`; GHCR for digikey / digigraph / digivault; corpus / crawl / OCR / vault+search ingest.

---

## 2. Dependency / order recommendation

**Recommended:** Pick 2 (ops + Profile A pull) and Pick 1 (runtime CSP) in **parallel**; then Pick 3 MVP.

| Order | Why |
|---|---|
| **Pick 2 Task 1 first (or ASAP)** | Stack images are not pullable until `publish-service-images` runs on `main` (#2023 is on develop only). Without that, Profile A “pull not build” cannot smoke. |
| **Pick 1 anytime (parallel with Pick 2 Tasks 2–4)** | Touches only digichat Node CSP / publish-digichat; orthogonal to stack images. Unblocks “any parent embeds stock digichat” without waiting for digivault GHCR. |
| **Pick 2 Tasks 2–4 next** | Switch `compose.profile-a.yml` + INSTALL to GHCR pins; vendor config so clone-free Profile A is real. |
| **Pick 3 after digivault is reachable under Profile A** | Onboard scripts write `DIGIVAULT_ROOT` (and/or digisearch); end-to-end chat smoke needs Pick 2’s stack. digivault **local search** (Pick 3 Task 1) can start earlier against a local digivault, but client doc-chatbot acceptance assumes Profile A. Pick 1 CSP and Pick 2 GHCR stay orthogonal to the scrape scripts. |

```text
Pick 2 T1 (publish GHCR) ──┬── Pick 2 T2–4 (Profile A pull + config)
Pick 1 (runtime CSP)  ─────┘         │
                                     ▼
                              Pick 3 MVP (local search → scripts/docs_onboard → runbook)
```

Hard dependency: **Pick 3 E2E → Pick 2** (digivault up + stable URL/volume). Soft dependency: **Pick 3 demos → Pick 1** (parent site iframe). No hard edge between Pick 1 and Pick 2.

---

## 3. Shared contracts

Keep these stable across all three plans.

### Env vars

| Variable | Owner service | Role |
|---|---|---|
| `DIGICHAT_EMBED_HOSTS` | **digichat** only | Runtime parent hostnames (Pick 1). Non-secret. Never move onto digikey/digigraph. |
| `DIGICHAT_EMBED_TENANTS` | **digichat** only | Runtime tenant JSON (tokens). Never a Docker build-arg. Host keys feed CSP when hosts env unset (Pick 1). |
| `DIGICHAT_VERSION` / `DIGICHAT_IMAGE_TAG` | digichat release | Pin `ghcr.io/digithings-ai/digichat:v…` |
| `DIGI_IMAGE_TAG` | digikey / digigraph / digivault | Pin stack GHCR (`sha-<12>` preferred; not `:latest` in prod). **Separate** from digichat tags. |
| `DIGIVAULT_URL` | digigraph (default `http://digivault:8004`) | Runtime tool path for `digivault_hub` |
| `DIGIVAULT_ROOT` | digivault (+ `scripts/docs_onboard`) | Vault filesystem root / Compose volume target for onboard writes + local search |
| `AUTH_SECRET`, `DIGIKEY_BFF_TOKEN`, provider keys | Profile A `.env` | Unchanged by all three picks |

### Images

| Image | Publish | Notes |
|---|---|---|
| `ghcr.io/digithings-ai/digichat:vX.Y.Z` | `publish-digichat-image.yml` | Pick 1 changes CSP wiring only; stack publish must **not** absorb digichat. |
| `ghcr.io/digithings-ai/{digikey,digigraph,digivault}:…` | `publish-service-images.yml` | Pick 2. Also publishes other Python services; Profile A only needs these three. |
| LiteLLM | Public `docker.litellm.ai/berriai/litellm:main-stable` | digithings does **not** republish. |

### Volumes / compose overlays

| Artifact | Contract |
|---|---|
| Compose volume `digivault_data` → `/data/vault` | Stable across GHCR digivault upgrades; Pick 3 `write_vault_notes` writes here (or via `POST /v1/notes`), never into digichat. |
| `infra/digichat-release/compose.profile-a.yml` | Minimal Profile A client path (Pick 2 switches to `image:` + `DIGI_IMAGE_TAG`). |
| `infra/self-host/compose.ghcr.yml` + `make up-ghcr` | Full monorepo stack overlay — **not** the same as Profile A (extra services). |
| `infra/digichat-release/config/` (Pick 2 Task 4) | Vendored `litellm.yaml` so clients need release dir, not full monorepo `config/`. |
| `scripts/docs_onboard/` | Offline ops job **beside** the stack — shared multi-client scripts, not a Compose chat-tier service and not a digicorpus peer module. |

### digivault URL / root

- digigraph keeps `DIGIVAULT_URL=http://digivault:8004` on Profile A.
- Pick 3: when `DIGIVAULT_ROOT` is set, `digivault_search_notes` searches the local vault; otherwise Supabase FTS (digithings.ai reference). Same volume `scripts/docs_onboard` writes. Optional digisearch sink is separate (`DIGISEARCH_URL` / index name in the client manifest).

---

## 4. Conflicts / contradictions + resolve

| Topic | Severity | Resolution |
|---|---|---|
| **Semantic product conflicts** | None | Plans already declare non-overlap: CSP ≠ stack images ≠ ingest. |
| **INSTALL.md / `.env.profile-a.example` / sketch §5** | Merge risk | Pick 1 and Pick 2 both edit these. Merge order: land either first; when rebasing, keep Pick 2’s pull-not-build Profile A copy **and** Pick 1’s runtime CSP hosts comments. Do not reintroduce stack `--build` or CSP build-arg. |
| **INSTALL honesty on CSP** | Timing | Until Pick 1 ships, INSTALL may still document rebuild; Pick 2 must **not** invent a stack workaround for CSP. After Pick 1, strike rebuild-first. |
| **digivault search precedence** | Intentional change (Pick 3) | Local root when `DIGIVAULT_ROOT` set; Supabase when unset. Document in digivault ARCHITECTURE — does not break Pick 2 image pull. |
| **Stack publish reintroducing digichat CSP build-args** | Anti-pattern | Explicitly forbidden by Pick 1 Fit + Pick 2 constraints. |
| **Secrets in `DIGICHAT_EMBED_HOSTS`** | Anti-pattern | Hosts only; tenants JSON stays runtime-only (Pick 1 + Pick 3). |

---

## 5. Pick 2 / #2023 residual gaps (block Profile A clone-free)

[#2023](https://github.com/digithings-ai/digithings/pull/2023) is **partial** vs Pick 2 intent. Still blocking:

1. **Images not pullable** — `ghcr.io/digithings-ai/{digikey,digigraph,digivault}` packages 404 until workflow runs on `main` (merge was develop-only; `on.push.branches: [main]`).
2. **Profile A still `build:`** — `infra/digichat-release/compose.profile-a.yml` builds digikey / digigraph / digivault from monorepo context.
3. **INSTALL / release README honesty** — still say clone + `--build` for Python services.
4. **Two overlays, no client glue** — root `compose.ghcr.yml` ≠ digichat-release Profile A; no single recommended “Profile A = pull pins” command (`digichat-profile-a-up`).
5. **Config still monorepo-mounted** — even after images exist, LiteLLM/digigraph mount repo `config/` until Pick 2 Task 4 vendors `infra/digichat-release/config/`.

What #2023 **did** deliver (keep): publish workflow, root GHCR overlay + `make pull-ghcr` / `up-ghcr`, self-host template docs, OpenAPI contracts (orthogonal).

---

## 6. Suggested implementation sequence (checklist)

### Stage A — Unblock GHCR stack (Pick 2 ops)

- [ ] Promote #2023 commit to `main` (normal develop → main); run `Publish: service images` (`service=all`)
- [ ] Verify `docker pull` for digikey, digigraph, digivault; record production `DIGI_IMAGE_TAG=sha-…`

### Stage B — Stock digichat embeds any parent (Pick 1) — parallel with Stage C

- [ ] Harden host parsing + fail-closed builders (TDD)
- [ ] Bake `frame-ancestors 'none'` in `next.config`; `src/proxy.ts` overwrites runtime CSP on `/embed`
- [ ] Stop baking `DIGICHAT_EMBED_HOSTS` in Dockerfile / `publish-digichat-image.yml`
- [ ] Docs: INSTALL runtime CSP; profile env examples; mark sketch CSP gap addressed
- [ ] Acceptance: build without hosts → start with runtime hosts → single CSP, no `*`

### Stage C — Profile A pull path (Pick 2 glue) — parallel with Stage B

- [ ] `compose.profile-a.yml`: GHCR `image:` + `pull_policy` for digikey / digigraph / digivault; keep digichat `DIGICHAT_VERSION` pin; LiteLLM public
- [ ] `.env.profile-a.example` + `make digichat-profile-a-up` (no `--build`)
- [ ] INSTALL + release README + self-host template cross-link; mark sketch stack-GHCR gap
- [ ] Vendor `infra/digichat-release/config/litellm.yaml`; point compose volumes at `./config`
- [ ] RELEASE-SMOKE Profile A stack-pull checklist; health curls on :8005 / :8000 / :8004 / :3005

### Stage D — Client docs onboard MVP (Pick 3)

- [ ] digivault local filesystem search when `DIGIVAULT_ROOT` set (`digivault_search_notes`) — digivault task, not a scrape script
- [ ] `scripts/docs_onboard/` leaves + `run_onboard.py` parent (scrape → classify → fetch → vault and/or digisearch)
- [ ] Client manifests under `docs/projects/<client>/`; docs pages prioritized; `source_url` metadata
- [ ] `docs/ops/CLIENT_PIPELINES.md` + `docs/digichat/CLIENT-DOCS-ONBOARD.md` + INSTALL pointer; mark sketch corpus follow-up
- [ ] Profile A smoke: onboard into volume → search / digichat question hits ingested phrase

### Stage E — Later (out of MVP for this synthesis)

- [ ] Pick 3 later: richer crawl / images; Profile A Compose attach; digiquant as another pipeline entry (OCR stays digisearch)
- [ ] CI automation of RELEASE-SMOKE; Helm / ACA stubs (sketch still-open)

---

## See also

- Self-hosted release sketch (gaps): [`digichat-self-hosted-release.md`](digichat-self-hosted-release.md) §5
- Product end-state: [`digichat-modular-frontend.md`](digichat-modular-frontend.md) §5
- Pick 3 plan: [`../superpowers/plans/2026-08-09-digichat-corpus-ingest.md`](../superpowers/plans/2026-08-09-digichat-corpus-ingest.md)
- Client docs onboard runbook: [`../digichat/CLIENT-DOCS-ONBOARD.md`](../digichat/CLIENT-DOCS-ONBOARD.md)
- Ops pipelines index: [`../ops/CLIENT_PIPELINES.md`](../ops/CLIENT_PIPELINES.md)
- Client install: [`../digichat/INSTALL.md`](../digichat/INSTALL.md)

Pick 1 / Pick 2 implementation plans live on their plan branches
(`docs/plan-runtime-frame-ancestors`, `docs/plan-stack-ghcr`) until merged;
this synthesis keeps those picks orthogonal to Pick 3 docs onboard.
