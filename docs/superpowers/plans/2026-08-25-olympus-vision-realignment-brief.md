# Olympus Vision Realignment Brief

> **Date:** 2026-08-25  
> **Status:** Recommendation only — no implementation authorized by this document  
> **Scope:** Top-down refresh of product shape vs. the 2026-08-06 pipeline metaplan  
> **Does not:** rewrite the metaplan, start #2422, or change runtime code  
> **Facts:** WP1 done; WP2 coded but `--no-ledger` / empty `holding_lots`; WP3 unfiled; `module/digiquant` synced (#2587)  
> **Authority:** Locked product decisions below supersede earlier brief recommendations where they conflict. Metaplan delivery sequence / gates remain; this brief is the product-shape addendum.

---

## 1. Aligned vision

Olympus v1 is a **digithings-owned house ETF paper book** as the immutable baseline: the **house default run always runs**. No user profile can move, cancel, or replace it. Around that baseline sits a **shared research corpus** (deduped by asset/theme; never forked per user) that any profile may consume. User profiles are **DB-backed** investment overlays — additional research requests and/or different preferences (universe, risk, themes) — plugged into the **same Atlas→Hermes pipeline**; they request extra work into the shared corpus; they do not own or fork the house run. Editable Settings UI can wait, but plumbing must accept ProfileConfig from the database now and the UI must show **read-only house profile pins**.

**Privacy split:** research corpus, analysis, and thesis artifacts keyed by asset/theme are **shared / anonymizable**. The **portfolio phase** (positions, fills, orders, NAV, mandate→book outcomes for that profile) is **user-private**. Track A portfolio/ledger work is the privacy-boundary home for per-user books. **Later (not v1):** optional public portfolios others can subscribe to — design must not preclude it; do not build it now.

An LLM **planner decides cadence** before any research gate — long-horizon themes are not forced daily; refresh reasons are user-visible. Delivery is a **dual track, not either/or**: research glass-box + corpus + planner runs **in parallel** with accounting ledger/NAV — accounting does not excuse invisible research spend; planner/corpus does not excuse fake NAV. **Brief** is the daily read; **Pipeline** is the primary glass-box; **inspectable ledger/periods** are product, not operator garnish.

**Kairos / execution:** v1 defaults to **paper portfolios** and/or **manual** trade execution. Put **groundwork** for later connect-account routing via Interactive Brokers API and Alpaca Trading API / MCP (AI) surfaces; **live-trading cutover remains human-gated** per repo rules (see §4 execution note).

---

## 2. What's still right in the metaplan

- **One canonical Atlas → Hermes (H1–H9) graph** with clear phase ownership (H4 roster, H5 evidence/forecast, H6 challenge only, H7 mandate, H8 weights, H9 commit).
- **Evidence and contracts before optimizer promotion** — typed artifacts, version pins, degraded states, no fabricated zeroes.
- **Accounting-grade lineage** (action → fill → holding → period NAV/contribution) as a hard gate before learning claims and policy comparisons — **Phase 0 stays**.
- **Attention / research-state ideas** (pin, carry, shared evidence, pre-provider routing) — directionally correct; pull **forward**, not after WP8–10.
- **Safe parallelism and promotion discipline** (shadow → canary → cutover; WP1 telemetry independent of WP2).
- **No live-trading / digikey changes** without an explicit human gate.

---

## 3. What's misaligned

| Area | Metaplan / docs today | Aligned product |
|---|---|---|
| Product shape | Infra program for **one institutional book**; multi-tenant/profile thin or absent | Named **ETF house book** (digithings-owned, always-on) + thin **DB-backed ProfileConfig** seam |
| Research timing | WP12/WP13 late (after WP8–10 path); WP13 over-gated for shadow | Pull **corpus + ProfileConfig + planner shadow** forward **alongside** WP2/WP3 |
| Cost story | Optimize after foundations; attention after WP11/WP12 | Cost lives in **H5×N + H6×N** now — shape cuts beside WP1 |
| Frontend | Invariant 18 limits UI to reader cutovers; conflicts with glass-box (#1945) | **Brief** = daily read; **Pipeline** = primary glass-box (product); Portfolio exposes **Tearsheet \| Ledger \| Period**; add **Corpus \| Book \| Profile** (read-only first) + Planner strip; **FX Hub** orthogonal / labeled separately |
| Phase 0 framing | Strict WP1→WP2→WP3 before research/UI product | **Parallel tracks** A trust/money ∥ B research plumbing ∥ C glass-box — neither substitutes |
| Missing WPs | No PipelineProfile / ProfileConfig package; WP12 too late | Name a **ProfileConfig / PipelineProfile** work package early on Track B (DB-backed) |
| Silent spend | Many nodes without user-facing artifact | **Glass-box rule:** WP1-attributed attempt ⇒ named UI surface, else delete/merge |
| Corpus ownership | Implicit single-book research store | **digithings house run immutable** + profile request → publish-if-missing into shared corpus; keys tenant-agnostic (see §4) |
| Privacy | Not explicit | Shared research vs **private** portfolio books (Track A = privacy home) |
| Kairos | Out of program / chrome by default | **Groundwork** for IB + Alpaca connect; paper/manual default; live path human-gated |
| Learning | In-path / same-day feedback risk | **Track E** after Gate 1; off daily path but UI-visible when run |

---

## 4. Recommended v1 architecture principles

1. **Dual track** — research glass-box + corpus + planner **∥** accounting ledger/NAV. Neither substitutes for the other.
2. **One pipeline, many profiles** — profiles are investment config (universe, risk prefs, themes), not forked graphs. Profile applies only at **compile / mandate / book**; not on corpus keys.
3. **Shared research corpus** — dedupe by asset/theme/segment; one write wins; consumers read pins/versions, never re-ground the same question.
4. **Corpus keys are tenant-agnostic** — `theme:` / `asset:` / `segment:` only. Profile identity never appears in the key.
5. **House corpus / default run ownership** — digithings owns the house default run; it **always runs** and is **immutable** (no profile can move, cancel, or replace it). Profiles may request **additional** research and/or different preferences; overlays publish into the shared corpus **only if missing** (or stale per planner policy). Preferences and overlay requests are **stored in the database**, not config-files-only.
6. **Privacy / sharing boundary** — **Shared / anonymizable:** research corpus, analysis, thesis/research artifacts keyed by asset/theme. **User-private:** portfolio phase (positions, fills, orders, NAV, mandate→book for that profile). Track A portfolio/ledger work is the privacy-boundary home for per-user books. **Later (not v1 blocker):** optional public portfolios + subscribe; do not preclude; do not build now.
7. **Config seam now; Profile UI read-only first** — ProfileConfig in digiquant plumbing (DB); chrome shows house pins; editable Settings later.
8. **LLM planner before the research gate** — carry / refresh / deep / skip with **visible refresh reasons**; no hard stage count. **Planner cannot** expand H4 roster/cap or rewrite H7/H8 authority.
9. **Brief = daily read; Pipeline = primary glass-box** — Pipeline + inspectable ledger are **product**. Chrome states ETF house book. Missing today: corpus identity, planner reasons, read-only profile pins, ledger/period inspectability (not charts alone).
10. **Glass-box rule** — if WP1 would attribute a physical attempt to a node, that node needs a named UI surface (Attention plan, Corpus update, Analyst dossier, Challenge, Mandate, Book change, Learning batch, NAV period) — else delete/merge the call.
11. **Fewer powerful stages** — pin/carry → macro pack → thesis ledger → attention roster → **one** evidence+forecast grounding → optional challenge → H7/H8/H9.
12. **WP1 measures; Tracks B/C do not wait on WP8–10**; Track A (WP2→WP3) must still become truthful before NAV is sold as authoritative.
13. **Kairos / execution groundwork** — research + plumbing for Interactive Brokers API and Alpaca Trading API / MCP so users may later **connect** portfolios for automated routing; otherwise **paper** and/or **manual** execution. **Human gate still applies** for live-trading paths: groundwork OK; live cutover remains gated.

### Execution groundwork note (official docs skim, 2026-08-25)

- **IBKR Web API** (unified Client Portal / trading surface): HTTPS + OAuth 2.0; retail often via Client Portal Gateway; trading session required for orders; usable for account/portfolio read (`/portfolio/...`), order submit/modify/cancel (`/iserver/account/{id}/orders`), and paper/sim accounts when the linked live Pro account is funded. Third-party vendor automated trading needs compliance onboarding. Defer: full vendor onboarding, Account Management API for advisors, live cutover. Docs: [IBKR Web API trading](https://www.interactivebrokers.com/campus/ibkr-api-page/web-api-trading/), [IBKR API home](https://www.interactivebrokers.com/campus/ibkr-api-page/ibkr-api-home/).
- **Alpaca Trading API** + **alpaca-py** `TradingClient`: same API shape for paper vs live; paper via separate keys / `paper=True` / `https://paper-api.alpaca.markets`. Clear connect-account → submit/cancel orders → positions path for groundwork. **Alpaca MCP Server** (docs/marketing: AI-assisted trading over the Trading API; defaults to paper; live via env flag) is the current “AI SDK / Traders” surface — useful for agent-shaped tooling later, not a v1 product dependency. Defer: live keys, Broker API white-label, crypto/options depth beyond paper connect. Docs: [Trading API](https://docs.alpaca.markets/docs/trading-api), [Paper trading](https://docs.alpaca.markets/docs/paper-trading), [alpaca-py Trading](https://alpaca.markets/sdks/python/trading.html), [MCP Server](https://docs.alpaca.markets/docs/alpaca-mcp-server).
- **v1 default:** paper portfolios and/or manual execution. Live broker routing stays behind the repo human gate.

### Silent-call disposition

| Call class | Disposition |
|---|---|
| H6 generic re-search | **Dies** — H6 is challenge / missing-fact only |
| Tool-loop residuals | **Die or roll into parent artifact** — never a freestanding billable node |
| Learning / maturation | **Off the daily path** (Track E); when run, UI-visible as Learning batch |
| Beliefs / intermediate opinions | **Visible in Pipeline glass-box or die** until H7 consumes them into Mandate |

### Recommended IA (v1)

| Surface | Role |
|---|---|
| **Brief** | Daily read |
| **Pipeline** | Primary glass-box (Attention plan, Corpus update, dossier, Challenge, Mandate, Book change, …) |
| **Portfolio** | **Tearsheet \| Ledger \| Period** — ledger/period inspectability is product; **user-private** books |
| **Corpus \| Book \| Profile** | Shared corpus identity; house book; **read-only** house profile pins first |
| **Planner strip** | Cadence + refresh reasons (not H4/H7/H8 authority) |
| **FX Hub** | Orthogonal; labeled separately |

---

## 5. Recommended sequence (reordered vs strict Phase 0 → 1 → …)

Parallel tracks (do not serialize B/C behind WP8–10):

| Track | Focus | Near-term |
|---|---|---|
| **A** Trust / money | WP2 residual → WP3 | Seed `holding_lots`; finish WP2 reader contracts (#2422 when scheduled); **file WP3**; privacy-boundary home for per-user books |
| **B** Research plumbing | ProfileConfig (DB) → WP12 (corpus) → WP13 **shadow** | ProfileConfig/PipelineProfile WP; tenant-agnostic corpus; planner shadow (not over-gated); house run always-on |
| **C** Glass-box | #1945 | Pipeline as primary product surface; map WP1 attempts → named UI |
| **D** Signal | WP4+ | After Track A foundations allow honest outcomes; no H8 promotion early |
| **E** Learning | After Gate 1 | Off daily path; UI-visible batches when run |

### This week

- **Declare product chrome** — ETF house book; Brief = daily read; Pipeline = primary glass-box; Portfolio Tearsheet | Ledger | Period; Corpus | Book | Profile (read-only); Planner strip; FX Hub separate. Brief only — **no full metaplan rewrite**.
- **Track A:** close WP2 hollowness (`--no-ledger` / empty lots); seed authoritative `holding_lots`.
- **Track A:** schedule #2422 (legacy labeling) as WP2 residual — not a product redesign.
- **Keep WP1 hot** — measure H5/H6 duplication and tool-loop residuals against glass-box rule.
- **Refresh metaplan progress strip only** (WP1 done; WP2 hollow; WP3 unfiled; module synced #2587).

### This month (A ∥ B ∥ C)

- **A:** file and start **WP3** (reconciled periods + curated views) once lots make WP2 non-fiction.
- **B:** land **ProfileConfig (DB)** → shared corpus (WP12-class, pulled forward) → **AttentionPlan planner in shadow** (WP13-class shadow, not blocked on full canary gates).
- **C:** advance glass-box **#1945** — corpus identity, planner refresh reasons, read-only profile pins, ledger/period inspectability on Pipeline/Portfolio.
- **Research-shape cuts on B** (parallel): pin/carry, macro pack, thesis ledger, attention roster, **single grounding**, optional H6; kill silent calls per §4.
- **Do not** promote optimizer / calibration into H8 until Gate 1 (Track A) is honest.
- **Do not** wait for WP8–10 to start B or C.
- **Kairos:** start IB/Alpaca connect groundwork design only as needed; paper/manual remain default; no live cutover.

### Later

- Track **D** full Phase 1–2 contracts behind existing gates.
- Enforce AttentionPlan out of shadow only after WP1 reconciliation + shadow quality.
- Track **E** outcomes / lessons / replay / governance after Gate 1.
- Editable Profile Settings and multi-profile UX once ProfileConfig + corpus are boring.
- Optional **public portfolios + subscribe** (community-style) — design-compatible only until scheduled.
- Kairos live connect behind human gate after paper path is boring.

---

## 6. Open questions still worth asking

**Resolved (2026-08-25):**

1. **Corpus write ownership** — digithings owns the always-on house default run (immutable; no profile can move/cancel/replace it). Profiles may request additional research / different preferences (DB-backed); research publishes into the shared corpus if missing (or stale per planner). Overlays do not fork the house run.
2. **Kairos / execution in Olympus v1** — **groundwork in** for Interactive Brokers API + Alpaca Trading/MCP surfaces; **paper and/or manual** default; live-trading cutover remains human-gated. Not “out of chrome”; not a full Kairos product redesign now.
3. **Stale vs missing for shared corpus** — profile requests publish-if-missing; refresh of an existing pin follows planner policy (theme TTL / event shock / explicit human refresh) without forking keys or reopening double-research by default. Exact TTL/shock rules remain planner-policy detail, not ownership debate.

**Still open (≤2):**

1. **Who pays for profile-requested research?** — house budget vs profile/tenant budget when a profile forces refresh or requests themes outside the house run.
2. **IB vs Alpaca first for paper connect?** — which broker path to ground first for connect-account / paper order submit (Alpaca paper keys look simpler; IBKR covers broader brokerage but heavier session/gateway).

---

## 7. My recommendation

Run **Tracks A ∥ B ∥ C this month**: make WP2 real and file WP3 for honest money (**private** per-user books; Track A = privacy boundary), keep the **digithings-owned always-on house run** as the immutable baseline, pull **DB-backed ProfileConfig** + tenant-agnostic shared corpus + planner **shadow** forward (not after WP8–10), and ship Pipeline/#1945 glass-box as **product** beside Brief. Put **Kairos IB + Alpaca groundwork** on the roadmap behind paper/manual defaults and the live-trading human gate — do not build live cutover from this brief. Withdraw any “quarantine Pipeline” or “hold NAV until the story is clear” guidance — ledger/period inspectability and Pipeline are the sell; Brief is the daily read. Kill H6 generic re-search and silent tool-loops under the WP1→UI-surface rule. Planner proposes attention with visible reasons only — never H4 width or H7/H8 authority. That dual track keeps the metaplan’s authority spine while fixing the real cost bill and the invariant-18 vs #1945 conflict without a full metaplan rewrite.

---

## Lens sources (compressed)

| Lens | Verdict used here |
|---|---|
| Vision | digithings-owned always-on house ETF run + DB ProfileConfig + shared corpus / private books; fewer stages; accounting before optimizer yes, before product shape no |
| Frontend | **Withdraw** Pipeline quarantine / hold-NAV; Brief=daily read; Pipeline=primary glass-box; Corpus\|Book\|Profile; Tearsheet\|Ledger\|Period; FX separate |
| Pipeline | Dual track; glass-box rule; silent-call kills; planner ≤ attention; tenant-agnostic corpus keys; house run immutable |
| Freshness | Phase 0 stays; A∥B∥C∥D∥E; WP12 too late; WP13 over-gated for shadow; missing ProfileConfig WP; inv.18 vs #1945; WP1 done; WP2 hollow; WP3 unfiled; module synced #2587 |
| Execution | Kairos groundwork IB + Alpaca; paper/manual default; live human-gated |

---

*Next doc action: additive progress/product-intent strip on the 2026-08-06 metaplan — not a full rewrite. See metaplan § Progress / Product intent (2026-08-25).*
