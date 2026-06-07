# Hermes — agent operator guide

> Sibling of [`digiquant/src/digiquant/olympus/atlas/docs/AGENTS.md`](../../atlas/docs/AGENTS.md). Atlas owns
> research; Hermes owns analysis + portfolio management + reflection.
> Boundary contract: [ADR-0015](../../../../../../docs/adr/0015-atlas-vs-hermes.md).

## What Hermes does

Hermes consumes the daily Atlas digest (`DigestPayload`) and produces:

- **4-axis analyst payloads** per ticker (`phase7c_analyst`) — fundamental,
  technical, sentiment, news. Output: `phase7c_analysts[ticker]`.
- **Bull/Bear debate summaries** (`phase7cd_debate`) — N rounds, each with
  bull + bear contributions and a research-manager synthesis.
  Output: `phase7cd_debates[ticker]`.
- **Risk debate + PM allocation memo** (`phase7d_pm`) — risk-aggressive vs
  risk-conservative cases, then a portfolio-manager allocation memo.
  Output: `phase7d_risk_debate` + `phase7d_rebalance`.
- **Closed-loop reflection** (`phase9_evolution`) — alpha-vs-SPY scoring
  on prior decisions + lesson proposals for the next baseline.
  Output: `phase9_evolution`.

## Entry points

- **Production:** `python -m digiquant.olympus.hermes.chain --run-type baseline|delta`.
  Drives Atlas first (research), then Hermes (analysis), then a single
  terminal `publish_phase`. The cron workflows use this.
- **Standalone (research-skipping):** `python -m digiquant.olympus.hermes.graph
  --from-digest <state.json>` reads a serialised Atlas state and runs
  Hermes only.
- **Library:** `digiquant.olympus.hermes.chain.run_atlas_then_hermes(atlas_input,
  deps)` for in-process invocation.

## Skills

Each phase loads its prompt from `digiquant/src/digiquant/olympus/hermes/skills/<slug>/SKILL.md`
via `digiquant.olympus.hermes.skills.load_skill`. The Atlas loader cannot resolve
Hermes skills (and vice versa) — `SkillNotFoundError` if you try.

| Phase | Skills loaded |
|------|--------------|
| `phase7c_analyst` | `fundamental-analyst`, `technical-analyst`, `sentiment-analyst`, `news-analyst` |
| `phase7cd_debate` | `research-debate`, `research-manager` |
| `phase7d_pm`      | `risk-aggressive`, `risk-conservative` |
| `phase9_evolution`| `pipeline-evolution` |

The seven WAVE2 skills (`thesis`, `thesis-tracker`, `thesis-vehicle-map`,
`opportunity-screener`, `pm-allocation-memo`, `portfolio-manager`,
`deliberation`) live in `digiquant/src/digiquant/olympus/hermes/skills/` ahead of their first
runtime caller — see [`WAVE2_UNIT_SPECS.md`](WAVE2_UNIT_SPECS.md).

## Schemas

Hermes-side JSON-Schemas under `digiquant/src/digiquant/olympus/hermes/templates/schemas/`:
- analyst-side: `asset-recommendation`, `deep-dive`, `pipeline-review`
- debate / deliberation: `deliberation-{session-index,transcript}`
- PM: `pm-allocation-memo`, `rebalance-decision`, `thesis-vehicle-map`
- reflection: `evolution-{sources,quality-log,proposals}`,
  `market-thesis-exploration`
- delta diff: `document-delta`

Loaded via `digiquant.olympus.hermes.schemas.load_schema(name)`.

## Persistence

Hermes does not call Supabase directly. Phase outputs land in the shared
`HermesState`; the chain orchestrator's terminal `publish_phase` (provided
by `digiquant.olympus.atlas.phases.publish_phase`) flushes everything in one pass —
analyst payloads land in `documents` with `document_key='analyst/<TICKER>'`,
PM rebalance lands in `documents`, the digest goes to `daily_snapshots`.

`phase9_evolution` writes `decision_log` rows when `Phase9Deps` is wired
(production cron only — no-op on dry-run / fixture tests).

## Testing

```bash
pytest tests/dq/hermes/ -m unit -v        # all Hermes phase tests + chain integration
pytest tests/dq/atlas/ -m unit -v         # Atlas-side
pytest tests/dq/ -m unit -v               # both + the rest of digiquant
```

The Hermes test tree is gated by `tests/dq/hermes/conftest.py` — skipped
when `digigraph.graph.pipeline_builder` isn't importable (the standard
`digiquant tests` CI job installs only `digiquant[dev]`; the full set runs
in `atlas-graph-ci.yml`).

## Useful files

- [`HERMES_SUBGRAPH.md`](HERMES_SUBGRAPH.md) — architectural spec.
- [`WAVE2_UNIT_SPECS.md`](WAVE2_UNIT_SPECS.md) — Wave 2 expansion units.
- [Atlas operator guide](../../atlas/docs/AGENTS.md) — research-side counterpart.
- [Atlas runbook](../../atlas/docs/RUNBOOK.md) — operator playbook (covers both
  engines today; may split when Hermes operations diverge).
