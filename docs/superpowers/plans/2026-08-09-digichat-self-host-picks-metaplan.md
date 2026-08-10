# digichat Self-Host Picks — Meta-Plan

> **For agentic workers:** This is an **orchestration** plan. Implement each pick via its own plan file using superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Do **not** ship runtime code from this document alone.
>
> **Status:** Final review complete 2026-08-10 — ready to execute by stages below.
> **Fit synthesis:** [`docs/architecture/digichat-self-host-picks-fit.md`](../../architecture/digichat-self-host-picks-fit.md)

**Goal:** Land the three digichat self-host follow-ups (runtime CSP, Profile A GHCR pull, client docs onboard) as separate PRs in dependency order so a client can pull a stock digichat + stack, embed it under any parent, and ground answers on that client's docs.

**Architecture:** Pick 1 and Pick 2 Profile A glue are orthogonal and may proceed in parallel after Pick 2’s GHCR publish gate. Pick 3 is an offline `scripts/docs_onboard/` ops workflow (not a digicorpus peer module); its E2E chat smoke needs Pick 2’s digivault volume/URL. Shared contracts (env vars, image tags, `DIGIVAULT_ROOT` volume) stay fixed in the fit doc.

**Tech Stack:** digichat Next.js (CSP proxy), GHCR + Compose Profile A, digivault / digisearch / digifetch via `scripts/docs_onboard/`.

## Global Constraints

- Digi product/module names are always lowercase in prose (`digichat`, `digigraph`, `digikey`, `digivault`, `digisearch`, `digifetch`, `digithings`) — never DigiChat / DigiCorpus.
- **No digicorpus package.** Pick 3 = `scripts/docs_onboard/` + `docs/projects/<client>/` manifests.
- One implementation PR per pick (plus an optional docs-only PR that only lands plans). Do not combine Pick 1 + Pick 2 code in one PR.
- Never `frame-ancestors *`. Never bake `DIGICHAT_EMBED_TENANTS` as a Docker build-arg.
- Stack publish must **not** absorb digichat; digichat keeps `publish-digichat-image.yml`.
- Production pins: `DIGI_IMAGE_TAG=sha-<12>` (stack), `DIGICHAT_VERSION` / `DIGICHAT_IMAGE_TAG=vX.Y.Z` (digichat) — never `:latest` for client installs.
- Every shipping PR links a GitHub Issue (`task/<N>-slug` or `Fixes #<N>`). Docs-only `docs/*` branches are linkage-bypassed.
- Before editing a component: read `{component}/AGENTS.md` + `ARCHITECTURE.md`.

---

## Plan Index

| Pick | Plan | Branch (plan) | Implementation branch pattern | Primary deliverable |
|---|---|---|---|---|
| **1** | [`2026-08-09-digichat-runtime-frame-ancestors.md`](./2026-08-09-digichat-runtime-frame-ancestors.md) | `docs/plan-runtime-frame-ancestors` | `task/<N>-digichat-runtime-csp` (or `feat/…` + `Fixes #N`) | Stock digichat GHCR: runtime `DIGICHAT_EMBED_HOSTS` / tenant host keys → `/embed` CSP |
| **2** | [`2026-08-09-digichat-stack-ghcr.md`](./2026-08-09-digichat-stack-ghcr.md) | `docs/plan-stack-ghcr` | Ops: promote `#2023` → `main` + publish; code: `task/<N>-profile-a-ghcr` | Profile A pulls digikey / digigraph / digivault; INSTALL honesty |
| **3** | [`2026-08-09-digichat-corpus-ingest.md`](./2026-08-09-digichat-corpus-ingest.md) | `docs/plan-corpus-ingest` | `task/<N>-docs-onboard` (+ digivault local-search issue if split) | `scripts/docs_onboard/` + digivault local search when `DIGIVAULT_ROOT` set |

Parent sketch gaps: [`digichat-self-hosted-release.md`](../../architecture/digichat-self-hosted-release.md) §5.

---

## 1. Final review verdicts

### Pick 1 — Runtime CSP `frame-ancestors` → **Ready** (minor wording tweak)

- Approach is correct: bake fail-closed `frame-ancestors 'none'` in `next.config.ts`; `src/proxy.ts` overwrites CSP at request time; never emit `*`.
- Security rules are test-locked (reject `*`, production no localhost, precedence hosts → tenants → first-party).
- Scope stays digichat-only; does not touch stack GHCR or ingest.
- Docs path (INSTALL + profile env examples + sketch §5) is explicit and acknowledges rebuild-first language must die after ship.
- **Tweak before/during implement:** Fit wording still says “Pick 3 (corpus ingest)” in Global Constraints / Fit § — align to `scripts/docs_onboard` (no digicorpus). No blocking design change.

### Pick 2 — Stack GHCR / Profile A pull → **Ready** (ops gate first)

- Correctly marks [#2023](https://github.com/digithings-ai/digithings/pull/2023) as **partial**: workflow + root `compose.ghcr.yml` landed on **develop**; packages remain 404 until publish runs on **main**.
- Remaining glue is clear: Profile A `image:` + `DIGI_IMAGE_TAG`, `make digichat-profile-a-up`, INSTALL honesty, vendored `infra/digichat-release/config/`.
- digichat publish stays separate; LiteLLM stays public upstream — good invariants.
- Smoke (Task 5) correctly gated on Task 1 images existing.
- **Tweak:** Related line still reads “PR under review” — treat as **merged to develop, not on main**. Prefer promoting `#2023` commit `3345a577` via normal develop→main, then `workflow_dispatch` `Publish: service images` (`service=all`), before Profile A glue PR merges (glue may land earlier but cannot smoke until images exist).

### Pick 3 — Client docs onboard (`scripts/docs_onboard`) → **Ready** (after rewrite)

- Rewrite is correct: **offline ops scripts**, not a Digi peer module; no `digicorpus/` package or `component:digicorpus`.
- Module roles are sharp: digifetch = transport; digisearch = parse/OCR/index; digivault = notes + local search; scripts = orchestration + classification.
- Task 1 (digivault local filesystem search when `DIGIVAULT_ROOT` set) can start before Profile A GHCR; E2E digichat smoke waits on Pick 2.
- Dual sink (vault and/or digisearch) + client manifests under `docs/projects/<client>/` match the fit contracts.
- **Tweak:** Keep MVP strict — defer richer crawl/Compose attach/digiquant entry (Task 10) until after first Profile A onboard smoke. Filename `…corpus-ingest…` is historical; prose must say docs onboard / `scripts/docs_onboard`.

---

## 2. Dependency graph and stages

Aligns with [`digichat-self-host-picks-fit.md`](../../architecture/digichat-self-host-picks-fit.md) §2 / §6.

```text
Stage A ── Pick 2 Task 1: promote #2023 → main + first GHCR publish
                │
                ├──────────────────────────────────────┐
                ▼                                      ▼
Stage B ── Pick 1 (runtime CSP)          Stage C ── Pick 2 Tasks 2–5
           (∥ Stage C)                                (Profile A pull + config + smoke)
                │                                      │
                └──────────────────┬───────────────────┘
                                   ▼
Stage D ── Pick 3 MVP
           digivault local search → scripts/docs_onboard leaves → runbook
           (E2E chat smoke needs Stage C digivault)
                                   │
                                   ▼
Stage E ── Later (out of program MVP)
           richer crawl; Compose attach; digiquant pipeline entry; CI RELEASE-SMOKE automation
```

| Stage | What | Parallelism | Hard deps |
|---|---|---|---|
| **A** | Pick 2 T1 — images pullable | Start **ASAP**; blocks smoke only | develop→main includes `3345a577` |
| **B** | Pick 1 full plan | ∥ Stage C | None vs Pick 2 |
| **C** | Pick 2 T2–5 Profile A glue | ∥ Stage B; smoke after A | Stage A for pull smoke |
| **D** | Pick 3 MVP | After C for E2E; T1 local search may start mid-C | Stage C for Profile A chat smoke |
| **E** | Non-MVP follow-ups | After D | — |

**Edges**

- Hard: Pick 3 E2E → Pick 2 (digivault up + stable volume/`DIGIVAULT_URL`).
- Soft: Pick 3 demos → Pick 1 (parent iframe).
- None: Pick 1 ↔ Pick 2 (except shared INSTALL.md merge discipline).

---

## 3. Branch / PR strategy

### Docs landing (this PR)

- Branch: `docs/plan-self-host-picks-metaplan` → **develop**.
- Contents: this meta-plan + the three pick plans + fit doc (none were on develop at review time).
- Does **not** authorize runtime changes; linkage bypass via `docs/*` head.

### One implementation PR per pick

| PR | Base | Head | Touches (avoid overlap) |
|---|---|---|---|
| Pick 1 | Prefer `module/digichat` if active; else `develop` (frontend one-hop) | `task/<N>-digichat-runtime-csp` | `frontend/digichat/**`, `publish-digichat-image.yml`, digichat INSTALL CSP section, profile env **CSP comments only** |
| Pick 2 glue | `develop` (root / digichat-release infra) | `task/<N>-profile-a-ghcr` | `infra/digichat-release/**`, Makefile Profile A targets, INSTALL Profile A **pull** copy, sketch §5 stack gap |
| Pick 3 | Split OK: digivault PR into `module/digivault` or develop-routed digivault; scripts PR into `develop` | `task/<N>-digivault-local-search`, `task/<N>-docs-onboard` | `digivault/**` local search; `scripts/docs_onboard/**`; `docs/ops/`, `docs/digichat/CLIENT-DOCS-ONBOARD.md`; INSTALL **pointer only** |

### Relationship to #2023

- [#2023](https://github.com/digithings-ai/digithings/pull/2023) is **MERGED** into **develop** (`3345a577`). State at review: **not** on `main`; GHCR packages for digikey / digigraph / digivault still missing.
- Do **not** reopen #2023 for Profile A glue. New Pick 2 PR completes Tasks 2–5; Task 1 is an **ops** action (promote + `gh workflow run "Publish: service images"`).
- Keep #2023 deliverables: `publish-service-images.yml`, `infra/self-host/compose.ghcr.yml`, `make pull-ghcr` / `up-ghcr`, OpenAPI contracts.

### Avoid INSTALL.md conflicts

Pick 1 and Pick 2 both edit `docs/digichat/INSTALL.md` and profile env examples.

1. Land either Stage B or Stage C first; the second **rebases** and merges both intents:
   - Keep Pick 2’s **pull-not-build** Profile A steps.
   - Keep Pick 1’s **runtime CSP** hosts comments (strike rebuild-first CSP).
2. Until Pick 1 merges, INSTALL may still document CSP rebuild — Pick 2 must **not** invent a stack workaround for CSP.
3. Pick 3 only adds a short pointer to `CLIENT-DOCS-ONBOARD.md` — do not rewrite Profile A install flow in the Pick 3 PR.
4. Prefer sequential merges of Pick 1 and Pick 2 on the same day rather than a mega-PR.

---

## 4. Execution checklist (agent tasks)

Owners are **agent sessions** following each pick plan. Checkboxes are program-level; pick plans own bite-sized steps.

### Stage A — Unblock GHCR stack (Pick 2 Task 1) — owner: ops / release agent

- [ ] Confirm packages missing: `gh api orgs/digithings-ai/packages/container/{digikey,digigraph,digivault}` → 404
- [ ] `git merge-base --is-ancestor 3345a577 origin/main` — if not, open/merge normal **develop → main** promotion (no force-push)
- [ ] `gh workflow run "Publish: service images" --ref main -f service=all` and wait for green
- [ ] `docker pull ghcr.io/digithings-ai/{digikey,digigraph,digivault}:…` — record production `DIGI_IMAGE_TAG=sha-<12>`
- [ ] Note pin in RELEASES / operator channel (optional one-line docs)

**Exit:** three stack images pullable; pin recorded.

### Stage B — Pick 1 implement → PR → review → merge — owner: digichat agent

- [ ] Read `frontend/digichat/AGENTS.md` + `ARCHITECTURE.md` + Next 16 `proxy.md`
- [ ] Open/link GitHub Issue; branch `task/<N>-digichat-runtime-csp`
- [ ] Execute pick plan Tasks 1–6 (TDD host parsing → fail-closed bake → `proxy.ts` → stop baking hosts → docs → acceptance curl)
- [ ] Open PR → CI green (`digichat` Vitest + docs) → `/review` or Bugbot when final → merge
- [ ] Mark sketch CSP gap addressed

**Exit:** stock image + runtime hosts → single `/embed` CSP with client origin; no `*`.

### Stage C — Pick 2 glue implement → PR → review → merge — owner: infra/docs agent (∥ Stage B)

- [ ] Open/link GitHub Issue; branch `task/<N>-profile-a-ghcr` from develop
- [ ] Execute pick plan Tasks 2–4 (compose `image:` + env + Makefile; INSTALL/README/sketch; vendor `config/litellm.yaml`)
- [ ] Open PR → CI green → review → merge (**rebase** if Pick 1 already touched INSTALL)
- [ ] Task 5 smoke after Stage A: Profile A up without `--build`; health on :8005 / :8000 / :8004 / :3005
- [ ] Mark sketch stack-GHCR gap addressed

**Exit:** clone-free Profile A pull path documented and smoked with pinned tags.

### Stage D — Pick 3 MVP implement → PR(s) → review → merge — owner: digivault + scripts agents

- [ ] Issue(s): digivault local search; docs_onboard pipeline (may be one or two PRs)
- [ ] Task 1: `digivault_search_notes` local root when `DIGIVAULT_ROOT` set — tests first; update digivault `ARCHITECTURE.md`
- [ ] Tasks 2–8: `scripts/docs_onboard/` models → scrape → classify → fetch → vault/search sinks → `run_onboard.py`
- [ ] Task 9: `docs/ops/CLIENT_PIPELINES.md` + `docs/digichat/CLIENT-DOCS-ONBOARD.md` + INSTALL pointer; mark sketch corpus follow-up
- [ ] Open PR(s) → CI green → review → merge
- [ ] Profile A smoke: onboard into `digivault_data` volume → digichat question hits ingested phrase

**Exit:** operator can run `python scripts/docs_onboard/run_onboard.py --manifest …` into Profile A vault/search and chat retrieves it.

### Stage E — Later (explicitly out of this program MVP)

- [ ] Pick 3 Task 10+ (richer crawl, Compose attach, digiquant entry)
- [ ] CI automation of RELEASE-SMOKE; Helm / ACA stubs per sketch still-open

---

## 5. Definition of done (whole program)

The program is **done** when all of the following are true:

1. **Publish:** `ghcr.io/digithings-ai/{digikey,digigraph,digivault}` exist on GHCR with a recorded `sha-<12>` pin; workflow proven on `main`.
2. **Profile A pull:** `infra/digichat-release/compose.profile-a.yml` uses GHCR `image:` (no monorepo `build:` for those three); `make digichat-profile-a-up` (or documented equivalent) starts without `--build`; LiteLLM remains public upstream.
3. **Runtime embed:** Stock digichat image admits a new parent via runtime `DIGICHAT_EMBED_HOSTS` and/or `DIGICHAT_EMBED_TENANTS` host keys; fail-closed; never `frame-ancestors *`; INSTALL no longer leads with rebuild-for-CSP.
4. **Docs onboard:** `scripts/docs_onboard/` exists (no digicorpus module); digivault local search works with `DIGIVAULT_ROOT`; runbook + example manifest published; Profile A smoke shows digichat → digigraph → vault/search grounding on an onboarded phrase.
5. **Docs honesty:** [`digichat-self-hosted-release.md`](../../architecture/digichat-self-hosted-release.md) §5 marks the three follow-ups addressed (or points to residual Stage E only); fit doc contracts unchanged (env/image/volume).
6. **Hygiene:** Three (or four, if digivault split) merged implementation PRs, each issue-linked; INSTALL contains both pull-not-build **and** runtime CSP without contradictory rebuild language.

---

## 6. Shared contracts (do not drift)

Copy of fit §3 — implementers must not invent parallel names:

| Contract | Rule |
|---|---|
| `DIGICHAT_EMBED_HOSTS` / `DIGICHAT_EMBED_TENANTS` | digichat only; hosts non-secret; tenants runtime-only |
| `DIGI_IMAGE_TAG` vs `DIGICHAT_VERSION` | separate pins |
| `DIGIVAULT_URL` / `DIGIVAULT_ROOT` | digigraph tools + onboard writes; same volume |
| `scripts/docs_onboard/` | beside the stack; not a Compose chat-tier service |
| digichat GHCR vs stack GHCR | separate workflows |

---

## 7. Self-review (meta)

| Spec / fit requirement | Covered by |
|---|---|
| Runtime CSP any parent on stock image | Stage B / Pick 1 |
| GHCR digikey/digigraph/digivault + Profile A pull | Stages A+C / Pick 2 |
| Client docs → vault/search without digicorpus | Stage D / Pick 3 |
| Parallel Pick 1 ∥ Pick 2 glue; Pick 3 after digivault | §2 stages |
| #2023 partial; publish on main ASAP | §3 + Stage A |
| INSTALL conflict discipline | §3 |
| Digi lowercase; Pick 3 = docs_onboard | Global Constraints |

**Placeholder scan:** none intentional — Stage E is explicitly deferred scope, not TBD implementation.

---

## Execution handoff

Meta-plan saved to `docs/superpowers/plans/2026-08-09-digichat-self-host-picks-metaplan.md`.

**Recommended start:** Stage A (promote + publish) immediately, then dispatch **two** implementation agents in parallel for Stages B and C, then Stage D.

**Per-pick execution:** subagent-driven-development against the pick plan file, not this meta-plan’s checkboxes alone.
