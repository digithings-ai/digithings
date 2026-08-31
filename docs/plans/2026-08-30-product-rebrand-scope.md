# Product rebrand scope — drop Olympus / Atlas / Hermes / Kairos

> **Date:** 2026-08-30
> **Status:** Accepted — product name is **digiquant** (ADR-0026). On-site CTA is **`open dashboard`** (mark + `dashboard` in compact nav) — the site wordmark is already digiquant. Wave 1 copy and wave 3 identifiers ship on this branch. Folder / npm / CI workflow rename needs a `feat/` or `task/<N>-slug` branch.
> **Does not:** rewrite packages, `/olympus/` URLs, tables, workflows, or live-trading paths in wave 1
> **Human gate:** yes — kairos **package** rename later touches execution; path/OAuth move is wave 2

Two decisions, in order:

1. **Pick the product name** that replaces olympus (the dashboard / commercial surface).
2. **Strip subsystem brands** — atlas, hermes, kairos stop being product names. They become ordinary job labels (research, portfolio, execution).

Do not start a repo-wide identifier rewrite until (1) is locked. The blast radius below is large enough that the wrong name costs a second migration.

---

## 1. What exists today

Four Greek names currently do four different jobs:

| Name | Job today | User-visible? |
|------|-----------|----------------|
| **olympus** | Product brand for the operator dashboard (`frontend/olympus`, `digiquant.io/olympus/`) and the Python umbrella (`digiquant.olympus`) | Yes — nav CTA, page title, OAuth app, Access path |
| **atlas** | Research sub-graph (`digiquant.olympus.atlas`, A0–A4) | Yes on the landing pipeline scene; **no** in dashboard nav |
| **hermes** | Portfolio / deliberation sub-graph (`digiquant.olympus.hermes`, H1–H9) | Yes on landing; **no** in dashboard nav |
| **kairos** | Execution router + broker mirror (`digiquant.olympus.kairos`) | Yes on landing (“in development”); live-trading adjacent |

The dashboard **already** uses functional nav: Brief, Portfolio, Pipeline, FX Hub (`frontend/olympus/lib/nav.ts`). Atlas / Hermes / Kairos are marketing and code names, not chrome labels. Stripping subsystem brands from the UI is mostly a landing-page + copy job.

The mark itself (nested arcs + a small circle, used as favicon and as `OlympusMark` / `AtlasMark`) is what prompted the “letter A → alphabox / autobox / ai box” instinct:

```
frontend/olympus/public/icons/olympus-app-dark.svg
frontend/digiquant-web/components/landing/OlympusMark.tsx
```

Existing marketing already uses the *box* metaphor. From `frontend/digiweb/design/COPY_GUIDE.md`:

> digiquant: “A quant hedge fund. *In a box you own.*”
> Primary CTA on digiquant.io: `open olympus`

So “box” is already the product sentence. The open question is whether the dashboard needs a **second brand** besides digiquant, and if so which A-name.

**Out of scope for this rebrand:** twelve-x / FX Hub (already a functional nav label). NautilusTrader, LangGraph, LiteLLM stay as vendor names.

---

## 2. Measured blast radius

Counts are unique files matching each token (excluding `node_modules`, `.git`, `.venv`, lockfiles). Overlap is expected — one file can hit several names.

| Token | Files | Filename matches |
|-------|------:|-----------------:|
| olympus / Olympus / OLYMPUS | 783 / 324 / 132 | 98 |
| atlas / Atlas / ATLAS | 538 / 449 / 79 | 37 |
| hermes / Hermes / HERMES | 321 / 269 / 39 | 11 |
| kairos / Kairos / KAIROS | 71 / 88 / 16 | 9 |

Treat “rename everything” as **thousands of edits across two branch hops**, not a weekend grep. The useful split is **what users see** vs **what the runtime is called**.

### 2.1 User-facing (must change if the product name changes)

| Surface | Current | Notes |
|---------|---------|-------|
| Public URL | `https://digiquant.io/olympus/` | Next `basePath: '/olympus'`; static export to `dist/olympus/` |
| Page title / PWA name | `Olympus — digiquant` | `frontend/olympus/app/layout.tsx` |
| Landing CTA | `open olympus` / “Open Olympus” | SiteNav, hero, closing CTA, copy guide |
| Landing pipeline scene | Atlas → Hermes → Kairos | `PipelineScene.tsx` — the only place users still see subsystem brands as names |
| Auth | GitHub OAuth app `digiquant olympus`; callback `/olympus/auth/callback/` | Cloudflare Access still on `/olympus/*` until cutover |
| Broker OAuth | Alpaca redirect `/olympus/settings/brokers/callback/` | Must stay in lockstep with the public path |
| CSP / `_headers` | scoped to `/olympus*` | `frontend/olympus/lib/security-headers.mjs` |
| Vision / copy | `docs/vision/olympus.md`, COPY_GUIDE proper-noun list | Product names in prose are currently Olympus, Atlas, Hermes |

### 2.2 Runtime identifiers (change later, or never)

| Layer | Examples | Recommendation |
|-------|----------|----------------|
| Python package | `digiquant.olympus.{atlas,hermes,kairos}` (~342 files under `olympus/`) | Wave 4, after the public name is live. Kairos package rename is **human-gated** (execution). |
| CLI entry | `python -m digiquant.olympus.hermes.chain` | Cron + `pipeline-olympus.yml`. Alias the old module if renamed. |
| Env vars | ~40 `OLYMPUS_*` plus `NEXT_PUBLIC_OLYMPUS_*`, `OLYMPUS_KAIROS_ROUTING` | Keep names; add aliases only if a public contract requires it. |
| CSS | `.oly-*` (~20 classes), `.accent-atlas`, `.olympus-mark` | Keep `.oly-` as an internal prefix. Users never see it. |
| npm | workspace folder `frontend/olympus`, package name `olympus` | Wave 3 with the URL, not before. |
| CI | `test-olympus.yml`, `pipeline-olympus.yml`, `test-atlas-graph.yml`, `validate-olympus-pools.yml`, `pipeline-atlas-metrics.yml` | Rename when the folder/package moves. |
| Config | `config/olympus_models.yaml` | Internal; rename with the Python package. |
| Phase IDs | A0–A4, H1–H9 | **Keep.** These are graph coordinates, not brands. |
| ADRs / historical plans | ADR-0014, ADR-0015, ADR-0019, `docs/superpowers/plans/2026-06-24-olympus-*` | **Amend, do not rewrite.** Frozen history. |
| GitHub Projects / issues | hundreds of “Olympus/Atlas/Hermes/Kairos” titles | Leave. New work uses the new names. |

### 2.3 Database — do not rename tables for a brand change

Historical migrations are append-only. Tables already shipped:

- **`olympus_*`** — research state, accounting, evidence, attention, forecast, replay, profile_config, provider telemetry, …
- **`atlas_run_diagnostics`** (032, 041, 065)
- **`hermes_research_attention_plan`** (and related attention tables)
- Broker tables from kairos tenancy (`broker_orders`, `broker_executions`, …) — already functional names in 102

A brand change is not a schema change. Optional later: `CREATE VIEW` aliases. Never rewrite 001–107.

### 2.4 Branching

| Area | Component | Base branch |
|------|-----------|-------------|
| Dashboard, landing, copy, URL | `component:digiquant-web` / website / root docs | **one-hop → `develop`** |
| Python package, CLI, workflows, env | `component:digiquant` | **two-hop → `module/digiquant`** |
| digigraph model-routing mentions | `component:digigraph` | `module/digigraph` (audit; likely docs only) |

Frontend can ship the new name while the backend package is still `digiquant.olympus`. That is the intended sequence.

---

## 3. Target taxonomy (once a name is picked)

Replace four brands with **one product name + three job words**.

| Today | User-facing after | Code (eventual) |
|-------|-------------------|-----------------|
| olympus | **\<product\>** (see §4) | `frontend/<product>/`, later `digiquant.<product>` |
| atlas | **research** | `…/research/` (today `atlas/`) |
| hermes | **portfolio** (or deliberation, if you want the PM loop distinguished from the book) | `…/portfolio/` (today `hermes/`) |
| kairos | **execution** | `…/execution/` (today `kairos/`) — human gate |

Landing pipeline copy becomes:

> research → portfolio → execution

not “Atlas · Hermes · Kairos”.

CTA library (COPY_GUIDE) becomes a literal destination:

- If the product is its own name: `open alphabox` (or whatever is picked)
- If the dashboard *is* digiquant: `open digiquant`

Prose rule stays: Digi module names lowercase. The new product name is lowercase in docs the same way (`alphabox`, never AlphaBox), except language-idiomatic identifiers (`AlphaBoxSession`).

---

## 4. Product name — evaluation

The dashboard lives at **digiquant.io**. It does not need a new apex domain. Domain checks below are about *uniqueness and collision*, not a requirement to buy a TLD.

### 4.1 The three names you named

| Candidate | Fit to the mark / copy | Collision | Verdict |
|-----------|------------------------|-----------|---------|
| **alphabox** | Strong. Letter-A mark + existing “in a box you own” line. “Alpha” is native finance vocabulary. | `alphabox.com/.ai/.io/.app/.co/.dev/.finance` all taken. Live **same-category** product: 熵简科技 AlphaBox (`alphabox.top`) — Chinese 投研 / investment-research assistant. Dead USPTO Class 9 “Alphabox” (Parvus, abandoned 2007). EU “alphabox” registered for furniture hardware (different class). | **Usable as an in-product name on digiquant.io**, not as a global web brand. Accept the 投研 name collision or pick something cleaner. |
| **autobox** | Weak-moderate. “Auto” reads automation, not the letter A. | **Hard no.** Autobox® is Automatic Forecasting Systems’ flagship time-series product (since 1988; Box–Jenkins lineage). Same industry: forecasting software. `autobox.com` is theirs. | **Reject.** |
| **ai box / aibox** | Weak. Generic, SEO-impossible, does not need the letter-A mark. | **Hard no.** aibox.ai is an existing company. Box, Inc. holds BOX / BOX AI and **won a TTAB opposition** against “AI BOX” (serial 98727887, opposition sustained). Prior C&D was public. | **Reject.** |

### 4.2 Two stronger options

**A. Collapse the dashboard into digiquant (recommended default)**

No second consumer brand. The mark becomes the digiquant mark. CTA: `open digiquant`. URL: keep `/olympus/` as a redirect onto `/app/` (or just `/`, if the landing and the app stay split).

Why this wins:

- You already own the domain and the module name.
- Subsystem stripping is the actual pain (“Olympus / Atlas / Hermes / Kairos” is four names for one product). Adding *alphabox* as a fifth name repeats the problem with better taste.
- digichat is the chat surface; digiquant is the quant surface. That pairing is already the public architecture.
- Zero trademark research, zero new OAuth-app identity beyond “digiquant”.

Cost: the letter-A mark is no longer “explained” by the name. That is fine — most product marks are not acrostics.

**B. alphabox as the operator-surface name (recommended if you want a distinct product)**

Keep **digiquant** as the engine / site / module. Call the logged-in dashboard **alphabox**.

```
digiquant     — engine, site, module
  alphabox    — operator dashboard (was olympus)
  research    — was atlas
  portfolio   — was hermes
  execution   — was kairos
```

This matches the letter-A mark and the “box you own” line. Live it at `digiquant.io/alphabox/` (308 from `/olympus/`). Do **not** depend on alphabox.com / .ai / .io.

Cost: another proper noun in COPY_GUIDE; same-category collision with 熵简 AlphaBox; “alpha” is crowded in fintech (Alphio, AlphaVector, …).

### 4.3 Runners-up (only if A and B both lose)

| Name | Why it exists | Availability (Vercel check, 2026-08-30) |
|------|----------------|------------------------------------------|
| **abox** | Shortest A+box. Very generic. | `abox.finance` available (~$12/yr). `abox.ai` / `abox.io` taken. |
| **axiombox** | Still A + box; “axiom” = first principles, fits research. Less finance-cliché than alpha. | `axiombox.ai` available ($160 / 2 yr). `axiombox.com` taken. |
| **theabox** | Phrase-y. | `theabox.ai` available. |

Do not introduce a `digi*` name for this surface (`digibox` is the old Sky set-top brand in the UK).

---

## 5. Rollout waves (after the name is locked)

Ship **copy before paths, paths before packages, packages before tables**. Frontend (`develop`) can lead; digiquant (`module/digiquant`) follows.

| Wave | What | Risk | Gate |
|------|------|------|------|
| **0** | Lock the name. File the ADR. Open the issue pack. | — | Human |
| **1** | User-facing copy only: titles, CTAs, landing pipeline labels (research / portfolio / execution), vision docs, COPY_GUIDE. **URL stays `/olympus/`.** | Low | Copy review |
| **2** | Public path + redirects + OAuth + Access + Alpaca callback + CSP. `basePath` + `dist/<name>/`. | Med — every redirect and vendor console | Human (auth redirects) |
| **3** | `frontend/olympus` folder + npm workspace name. Keep `.oly-*` CSS. | Med | one-hop `develop` |
| **4** | Python package / CLI / CI workflow names. Compat import shims for one release. | High | two-hop `module/digiquant` |
| **5** | Env-var aliases only if a public contract needs them. Prefer keeping `OLYMPUS_*`. | Med | ops |
| **never** | Rewrite old SQL migrations, ADR bodies, issue titles, or `olympus_*` / `atlas_run_diagnostics` table names. | — | — |

Kairos → execution in **code** is a separate, human-gated task. Wave 1 may already say “execution” on the landing page without touching `digiquant.olympus.kairos`.

### Redirect sketch (wave 2)

```
/olympus          → 308 /<new>/     (or /app/)
/olympus/*        → 308 /<new>/*    (preserve suffix)
```

Keep the old path as a permanent alias until vendor consoles (GitHub OAuth, Supabase Auth, Alpaca, Cloudflare Access) have been switched. Do not drop `/olympus/auth/callback/` until those consoles list the new URL.

### Tests per wave

- Wave 1–3: `cd frontend/olympus && npm run test && npm run build`; landing copy grep; `make doc-check`
- Wave 4: `pytest -m unit tests/dq/olympus tests/dq/atlas tests/dq/hermes tests/dq/olympus/kairos`
- Do not run Nautilus-heavy `make test-unit` on Linux as the rename signal (SIGABRT #42)

---

## 6. What to file after the name is picked

This brief is not an ADR. Once the name is chosen:

1. **ADR** — “olympus / atlas / hermes / kairos retired; product name is \<X\>; subsystems are research / portfolio / execution.” Amends ADR-0014, ADR-0015, ADR-0019. Does not rewrite them.
2. **Issue pack** (agent-task), split by wave, labels:
   - Waves 1–3: `component:digiquant-web` + `component:website / root docs`, base `develop`
   - Wave 4: `component:digiquant`, base `module/digiquant`
   - Kairos code rename: `risk:high`, human gate (live-trading path)
3. Update `docs/vision/olympus.md` title in wave 1; keep the filename until wave 3.

Draft issue title for wave 1:

> `[agent] Retire olympus/atlas/hermes/kairos from user-facing copy — product is <name>`

---

## 7. Recommendation

**Locked 2026-08-30:**

1. **Subsystem brands: strip.** User-facing words are research, portfolio, execution. Keep A0–A4 / H1–H9 as internal phase IDs.
2. **Product name: digiquant.** No second consumer brand (alphabox / autobox / aibox rejected).
3. **Do not grep-rename the repo.** Copy first (wave 1), URL second (wave 2), packages last (wave 4). Leave SQL and historical ADR bodies alone.

See [ADR-0026](../adr/0026-retire-olympus-atlas-hermes-kairos.md).
