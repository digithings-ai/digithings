# Hermes — architecture

> Analysis, debate, portfolio management, and reflection. Consumes Atlas research;
> produces analyst payloads, a rebalance decision, reflection records, and (via
> `portfolio_materialize`) booked `positions` / `theses` rows.
>
> Boundary: [ADR-0015](../../../../../docs/adr/0015-atlas-vs-hermes.md). Parent overview:
> [`digiquant/ARCHITECTURE.md`](../../../../../ARCHITECTURE.md) § Atlas + Hermes.

---

## End-to-end flow (chain)

Production cron invokes `python -m digiquant.olympus.hermes.chain`:

```
preflight (Atlas) → phases 1–6 research → phase7_synthesis (digest)
    → Hermes graph (7C → 7CD → 7D → 9)
    → phase7e risk-sizing → publish_phase → portfolio_materialize
```

`chain.run_atlas_then_hermes` runs Atlas with `publish=None`, then Hermes, then
terminal phases. Monthly runs stop after Atlas `phase_monthly` (no Hermes).

---

## Intended vs live analyst entry

### Intended (thesis-first)

1. **Translate** Atlas research (`phase7_digest` + segment bodies) into market-facing
   **theses** (`market-thesis-exploration` schema).
2. **Map** investment vehicles/tickers to each thesis (`thesis-vehicle-map`).
3. **Screen** the universe; analysts fan out over **thesis-attributed tickers**
   (plus held names for mandate review) — not an arbitrary watchlist slice.

Planned phases: h1 thesis review → h2 exploration → h3 vehicle map → h4 opportunity
screen → h5 asset analyst. Spec:
[`HERMES_SUBGRAPH.md`](HERMES_SUBGRAPH.md) §1. Wave 2 skills were never wired to the
live graph.

### Live today

| Step | Module | Behavior |
|------|--------|----------|
| Watchlist source | `chain.cli_main` | When `--watchlist` is empty: `load_prior_book` → `holdings_from_prior_book` + `select_focus_tickers` (`candidates.py`) |
| Focus selection | `candidates.select_focus_tickers` | Holdings first (from materialized `positions`, not stale `portfolio.json`), then top-N watchlist names by legible technical score |
| Analyst fan-out | `graph.build_hermes_phases` → `phase7c_analyst` | 4-axis specialists per ticker in the focus list; join → `phase7c_analysts` |
| Debate / PM | `phase7cd_debate`, `phase7d_pm` | Unchanged contract |
| Thesis table | `portfolio_materialize._upsert_theses` | **Post-PM**: one `theses` row per **held** ticker (`thesis_id = ticker.lower()`), not from h2/h3 |

**Gap:** `thesis_tracker` in the digest is always empty (Atlas research-only).
Hermes does not yet run thesis translation before analysts; `AnalystPayload.thesis`
is aggregated axis rationale, not a link to a `theses.thesis_id`.

---

## Boundary diagram

```mermaid
flowchart TB
  subgraph Atlas["Atlas (research)"]
    seg["Phases 1–5 segments"]
    bias["Phase 6 bias row"]
    dig["Phase 7 digest<br/>no positioning fields"]
    seg --> bias --> dig
  end

  subgraph HermesLive["Hermes (live)"]
    focus["Focus list<br/>holdings + tech scores"]
    c["7C analysts"]
    cd["7CD debate"]
    d["7D PM + risk debate"]
    e["7E risk sizing"]
    m["materialize → positions, theses"]
    focus --> c --> cd --> d --> e --> m
  end

  subgraph HermesPlanned["Hermes (planned h1–h4)"]
    h2["h2 market theses"]
    h3["h3 vehicle map"]
    h4["h4 opportunity screen"]
    h2 --> h3 --> h4
  end

  dig --> focus
  dig -.-> h2
  h4 -.->|"thesis-attributed tickers"| c
```

---

## Phase reference (live graph)

| Phase | File | Output state keys |
|-------|------|-------------------|
| 7C-i | `phases/phase7c_analyst.py` | `phase7c_specialists[ticker][axis]` |
| 7C-ii | same (join) | `phase7c_analysts[ticker]` |
| 7CD | `phases/phase7cd_debate.py` | `phase7cd_debates[ticker]` |
| 7D | `phases/phase7d_pm.py` | `phase7d_risk_debate`, `phase7d_rebalance` |
| 9 | `phases/phase9_evolution.py` | `phase9_evolution`, `decision_log` rows |
| 7E | `phases/phase7e_risk_sizing.py` | overwrites `phase7d_rebalance` weights |
| 9D | `portfolio_materialize.py` | Supabase `positions`, `theses`, `thesis_vehicles` |

---

## Related docs

- [`README.md`](README.md) — layout, CLI, tests
- [`AGENTS.md`](AGENTS.md) — agent operator guide
- [`HERMES_SUBGRAPH.md`](HERMES_SUBGRAPH.md) — Wave 2 planned topology (historical)
- Atlas Phase 7 boundary: [`atlas/docs/agentic/ARCHITECTURE.md`](../../atlas/docs/agentic/ARCHITECTURE.md) § Phase 7
