# Adaptive Two-Track Analyst Dispatch — Design Spec

**Date:** 2026-06-23
**Issue:** #1017 (umbrella)
**Status:** Design — pending review (brainstorm complete; not yet planned/implemented)

## Problem

The Olympus Hermes step that selects which vehicles get a costly per-asset LLM
"analyst" deep-dive (H4 → H5) is the system's attention-allocation controller —
it rations the scarcest, most expensive resource — yet it is exactly where
justification is absent today.

Current behaviour (verified):

- **H4** builds the analyst roster as a deterministic union of three buckets,
  capped at `ATLAS_MAX_ANALYSTS` (~25): `held` (prior book), `thesis_mapped`
  (from H3, carries `linked_market_thesis_id`), and `technical` (a pure
  `price_technicals` screen of the rest of the watchlist, **no thesis link**).
- The `technical` bucket is an **unjustified fan-out** (`roster_reason="technical"`,
  `linked_market_thesis_id=None`); in the no-DB-client path it degrades to
  watchlist order.
- **H5** runs the analyst, then for any non-`thesis_mapped` ticker calls
  `upsert_vehicle_thesis_from_analyst` — manufacturing a `vehicle-{ticker}` thesis
  **after** the fact from the analyst's own output. The thesis→dispatch arrow is
  **reversed**, and the audit trail is circular / non-falsifiable.
- The justification-capable model (`OpportunityScreenOutput` / `RosterPick{ticker,
  score, source_thesis_ids[], rationale}`, `models/thesis.py`) exists but is **dead
  code** — referenced only in specs, never instantiated.
- There is **no "excluded" ledger**: "why was this watchlist name NOT analyzed" is
  never recorded — the missing half of anti-waste.
- On thin-thesis days the funnel silently collapses to a pure technical scanner —
  exactly when conviction is lowest.

## Goals

1. **Every analyst dispatch carries an explicit, falsifiable reason** — a linked
   thesis, a discovery signal, or an honest exploration draw. No silent fan-out;
   no post-hoc thesis manufacture.
2. **No wasted analyst runs** — budget is bounded and allocated to where the
   expected information value is highest; the held book stops being re-analyzed
   unconditionally every day.
3. **Two tracks** — *exploit* (validate/size theses we hold) and *explore*
   (discover opportunities and feed tomorrow's theses), each with its own budget
   and reason type.
4. **Adaptive** — the budget size and the explore/exploit split follow the market
   regime (information value), not a static rule.

These were the user's explicit decisions in the brainstorm: **two-track** +
**adaptive (regime-driven) budget**.

## Grounding (why this shape)

A research sweep (peer-reviewed theory + how other multi-agent LLM finance
systems work + practitioner funnels) produced five candidate architectures
(A–E). This design is **E (Two-Speed Adaptive Hybrid)**, composed from A
(exploit), B (explore), and D (adaptive budget):

- **Exploration/exploitation & fixed-budget best-arm identification** — frames
  dispatch as allocating a bounded analyst budget between validating known theses
  and probing uncertain off-thesis names (MAB / best-arm ID; Thompson sampling).
- **Rational inattention (Sims 2003) & value-of-information (Howard EVPI/EVSI)** —
  attention flows to high uncertainty-reduction × payoff-relevance, not raw
  salience; an asset the thesis already pins down is wasted capacity.
- **Regime-conditioned attention (Kacperczyk–Van Nieuwerburgh–Veldkamp, Econometrica
  2016)** — research value is regime-state-dependent: fewer/shallower dives in
  high-correlation risk-off regimes, more in dispersion regimes.
- **Cost-aware cascades (RouteLLM ICLR 2025; cost-aware ranking)** — a cheap broad
  scan that escalates only threshold-crossers to a costly analyst is provably
  cost-optimal *given a real cost gap*.
- **Mixed top-down/bottom-up evidence (Brinson 1986 vs Ibbotson–Kaplan 2000)** —
  argues against committing to a single paradigm; instrument both and let measured
  hit-rate arbitrate.
- **Other AI finance systems** (TradingAgents, ai-hedge-fund, Expert Investment
  Teams) all skip selection entirely (human-supplied or full fixed universe,
  strictly one-pass) — confirming the selection problem is real and under-solved,
  and that we must not over-build a step whose value is unproven.

**Honest caveat (carried from the research):** every design can guarantee a reason
*string*; only upstream H2/H3 thesis quality makes it a real *reason*. And the
single highest-leverage waste fix may be the held-book staleness gate, independent
of the rest. The instrumentation (below) is therefore load-bearing, not optional.

## Architecture

A two-speed control loop wrapping the existing H1–H9 graph.

```
            ┌─────────────────────── SLOW layer (thesis scope) ──────────────────────┐
            │ H2/H3 thesis funnel: theses → scored candidate vehicles                  │
            │ runs on staleness / regime-flip, NOT unconditionally daily               │
            └───────────────────────────────┬─────────────────────────────────────────┘
                                             │ (theses, priors, in-scope sectors)
                 ┌───────────────────────────▼───────────────────────────┐
 regime ───────▶│  H4  Budget Controller + Roster Builder                  │
 classifier     │  • regime → budget B and explore/exploit split           │
 (VIX term-     │  • EXPLOIT lane: thesis_mapped candidates (RosterPick)    │
 structure,     │  • EXPLORE lane: T1 broad cheap scan → delta-gated picks  │
 dispersion,    │  • ε exploration slice: off-thesis uncertain names        │
 breadth)       │  • held book: staleness/delta gate (not unconditional)    │
                │  • emits OpportunityScreenOutput{roster[], excluded[]}     │
                └───────────────────────────┬───────────────────────────────┘
                                             │ roster: each entry has a DispatchReason
                 ┌───────────────────────────▼───────────────────────────┐
                 │  H5  Asset analysts (parallel fan-out)                  │
                 │  • analyst receives its DispatchReason + linked thesis  │
                 │  • may emit ≤K structured FOLLOW-UP requests            │
                 │    (sub-sector/vertical ETF) → feed NEXT cycle's T1     │
                 │  • NO post-hoc thesis except for exploration picks      │
                 │    that earn conviction (gated + aged-out)              │
                 └───────────────────────────┬───────────────────────────┘
                                             │ + dispatch-outcome record (feedback)
                 ┌───────────────────────────▼───────────────────────────┐
                 │  H6→H9 unchanged (deliberation, pm-direction, commit)   │
                 └─────────────────────────────────────────────────────────┘
                                             │
                       feedback table (realized hit-rate / decision-change
                       per reason-type) ─────► tunes next cycle's split
```

## Components

### 1. `DispatchReason` contract (the unifying data model)

Every roster entry carries exactly one typed reason. **Home model (decision):**
`RosterPick` (the dead `OpportunityScreenOutput.roster[]` member) becomes the
single source of truth — it already has `score`, `source_thesis_ids[]`, `rationale`
and `rank`. `FocusRosterEntry` (today's roster element) is either replaced by
`RosterPick` or reduced to a thin projection of it; the two models **merge** rather
than both carrying reason fields. The reason discriminator + payload:

- `thesis` → `{source_thesis_ids: list[str], rationale, kill_criterion}` (exploit)
- `discovery` → `{trigger_signal, score, kill_criterion}` (T1 delta crosser)
- `exploration` → `{posterior_uncertainty}` (the ε-slice draw)
- `held` → `{prior_position, staleness_trigger}` — a retained book name re-analyzed
  because its staleness/delta check fired; "we own it and X changed" is its reason.

Invariant: **no entry reaches H5 without a non-empty reason** — including the
retained `held` bucket. Enforced as a **soft gate**: if an entry somehow reaches
dispatch with an empty reason, log an error and apply an honest default; do **not**
raise (a hard validator would crash the whole daily run; the roster is constructed
in H4 and a thin slip must not take down production).

### 2. Slow thesis layer (exploit source)

H2/H3 stay as the thesis source but are **cadence-decoupled** from the daily
analyst run: re-run only on a staleness threshold or a regime flip; otherwise
reuse prior theses. H3 emits per-thesis (v1) rationale + `candidate_tickers`
(per-ticker rationale is a future enhancement — see Open Questions).

### 3. T1 broad scan (explore source)

A new near-zero-cost tier (no LLM) scoring the **whole** universe each cycle from
existing `price_technicals` / flow / breadth data. Threshold-crossers escalate;
the score + triggering signal become the `discovery` reason. The uncovered→covered
**transition** (delta) is the dispatch trigger, not a full-universe re-rank.

### 4. Budget controller (adaptive, regime-conditioned)

A regime classifier sets the budget. It builds on signals Olympus **already
computes** — VIX level/term-structure and market breadth — plus cross-asset
correlation/dispersion which is **to be built** (not currently computed; a small
new derived-metric step). Resolve the exact signal set during planning. Outputs:

- **B** — number of analyst dives this cycle (replaces the static cap).
- **explore/exploit split** — explore↑ when conviction is thin / markets quiet;
  exploit↑ when strong theses exist; depth/B shrink in high-correlation risk-off
  regimes (idiosyncratic dives have low marginal value when assets move together).

Held book: re-analyze a held name only when a staleness/delta check says its
decision could move — not unconditionally daily.

### 5. Analyst follow-up loop (explore depth)

H5 analysts may emit ≤K structured follow-up dispatch requests for adjacent
sub-sector/vertical ETFs. These feed the **next** cycle's T1 (bounded recursion,
depth-capped) — **not** same-cycle unbounded recursion. This is **net-new
construction**, not a reuse of existing machinery: there is no cross-ticker
deep-dive request mechanism today (H6 is a per-ticker debate loop and "deep-dive"
is only an artifact-label string). It requires (a) a new structured-output field
on the analyst result for follow-up requests, and (b) a next-cycle seed that feeds
those requests into T1. Budget Stage 4 accordingly.

### 6. Feedback / instrumentation

A `dispatch_outcomes` record per dispatch: reason-type, and realized signal —
did the dive change a PM inclusion/sizing decision? did the position get taken?
did the thesis validate? This is the reward signal the adaptive split consumes
and the evidence that tells us whether the explore lane earns its budget. Without
it, "adaptive" is blind and the redesign is unmeasurable.

### 7. Excluded ledger

Populate `OpportunityScreenOutput.excluded[]` — record why each non-dispatched
watchlist name was skipped. Cheap to add; the missing half of anti-waste; enables
the recall measurement (did we wrongly prune something that mattered?).

## Data flow

1. Regime classifier computes regime + sets `B` and split.
2. Slow layer supplies theses (fresh or reused) → exploit candidates with
   `source_thesis_ids` + rationale.
3. T1 scans the universe → discovery candidates with score + signal; ε-slice draws
   exploration candidates by posterior uncertainty.
4. H4 fills `B` from the lanes per the split, gates the held book on staleness,
   emits `OpportunityScreenOutput{roster[], excluded[]}` — every roster entry a
   `DispatchReason`.
5. H5 fans out analysts (each told *why* it was dispatched + the linked thesis);
   analysts may emit follow-up requests.
6. H6–H9 unchanged. Dispatch outcomes recorded.
7. Outcomes tune the next cycle's split; follow-up requests seed the next T1.

## Error handling / degradation

- **Thin-thesis day:** explore lane carries the cycle — never a silent collapse to
  a blind technical scan.
- **No regime signal:** fall back to a static split + log.
- **Empty reason at dispatch:** soft gate logs + honest default, never raises.
- **Follow-up runaway:** depth-cap + next-cycle-only + budget-gated.
- **Exploration duds:** expected by design; socialized as intentional, bounded by
  the ε-slice size, recorded in outcomes.
- **Orphan exploration theses:** only created post-analyst on earned conviction,
  with an age-out/INVALIDATE path so they don't pollute tomorrow's H1 review.

## Testing

- Unit: `DispatchReason` invariant (no empty reason survives the soft gate);
  regime→(B, split) mapping; T1 scoring determinism; held staleness gate;
  follow-up depth cap; excluded-ledger population.
- Regression: a held+thesis-mapped ticker keeps its thesis link (today's link-loss
  bug); thin-thesis day routes budget to explore, not a blind scan.
- Routing: every watchlist ticker that reaches H5 carries a non-empty, typed
  reason (the contract).
- Integration: a clean baseline run produces a roster whose every entry is
  justified and whose `excluded[]` accounts for the rest of the watchlist.

## Build sequence (staged; each stage shippable + testable)

1. **Contract + exploit wiring** — wire `OpportunityScreenOutput`, converge the
   roster element on `RosterPick` (merge/replace `FocusRosterEntry` per the home-
   model decision above) so every entry carries `score`/`source_thesis_ids`/
   `rationale`, carry H3 rationale + the full linked thesis into the H5 analyst
   prompt, remove the reversed arrow (keep post-hoc only for exploration), add the
   excluded ledger, add the held staleness/delta gate, fix the held+thesis-mapped
   link-loss. *(Fixes today's verified failures; no new LLM.)*
2. **Adaptive budget** — regime classifier → `B` + explore/exploit split, applied
   at the **real** production choke point: H4 `compute_focus_roster` →
   `roster_cap.capped_tickers` (`h4_opportunity_screener.py`), which feeds the
   runtime `build_h5_from_state` fan-out (`graph.py`). **Not** the `capped_tickers`
   call inside `build_h5_asset_analyst` — that path is test-only and not wired into
   the runtime graph, so editing it would be dead-code work.
3. **Explore lane** — T1 broad scan + discovery reason + ε exploration slice.
4. **Follow-up loop + feedback** — build the (net-new) analyst follow-up channel:
   a structured-output field for follow-up requests + a next-cycle seed into T1;
   add the `dispatch_outcomes` feedback table and wire it into the adaptive split.
   *(Net-new — no existing H6 machinery to reuse; budget accordingly.)*

Each stage is its own issue + TDD PR into `module/digiquant`. Measurement from the
clean baseline run (held-book cost share, technical-vs-thesis hit-rate, T1 cost
gap) informs whether stages 3–4 are justified before building them.

## Open questions (resolved defaults; override during planning)

- **Per-thesis vs per-ticker rationale:** v1 uses H3's per-thesis rationale; per-
  ticker "why THIS vehicle" is a larger H3 schema/prompt change — deferred.
- **Follow-up cadence:** next-cycle only (avoids same-cycle runaway).
- **Roster size:** variable-length, conviction-realized, capped by `B` (not a fixed
  top-K) — thin days produce a small/empty exploit set, explore fills.
- **Regime detector:** built from existing market-data signals; exact signal set to
  be confirmed against what Atlas already computes during planning.
- **Durable exploration theses:** created only post-analyst on earned conviction,
  with age-out — not pre-dispatch stubs.

## Non-goals

- Replacing the analyst, deliberation (H6), pm-direction (H7), or commit (H9)
  stages — they are unchanged.
- Expanding the universe enumeration manually — the T1 scan auto-includes any ETF
  in the watchlist; follow-ups pull adjacent vehicles on demand.
- A full value-of-information dollar model (Architecture C) — too hard to calibrate
  honestly today; the regime-conditioned budget is the tractable proxy.
