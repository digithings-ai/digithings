# Hermes — analysis, portfolio mgmt, risk, reflection

Hermes is the analysis half of the DigiQuant pipeline. It consumes a
research [`DigestPayload`](../../src/digiquant/olympus/atlas/snapshot.py) produced by
[Atlas](../atlas/) and produces analyst reports, an allocation memo, and a
reflection record.

See [ADR-0015](../../../docs/adr/0015-atlas-vs-hermes.md) for the
responsibility boundary.

## Phases

| Phase | Purpose | Skills |
|------|---------|--------|
| `phase7c_analyst` | 4-axis analyst specialisation per ticker (#430) | `fundamental-analyst`, `technical-analyst`, `sentiment-analyst`, `news-analyst` |
| `phase7cd_debate` | Bull/Bear adversarial debate per ticker (#429) | `research-debate`, `research-manager` |
| `phase7d_pm` | Risk-aggressive vs conservative debate + PM allocation (#431) | `risk-aggressive`, `risk-conservative`, `pm-allocation-memo` |
| `phase9_evolution` | Closed-loop reflection / alpha scoring (#432) | `pipeline-evolution` |

## Code layout

```
digiquant/
├── src/digiquant/olympus/hermes/
│   ├── __init__.py
│   ├── state.py                 ← HermesState (alias for AtlasResearchState today)
│   ├── graph.py                 ← build_hermes_graph(...)
│   ├── chain.py                 ← run_atlas_then_hermes(...)
│   └── phases/
│       ├── phase7c_analyst.py
│       ├── phase7cd_debate.py
│       ├── phase7d_pm.py
│       └── phase9_evolution.py
├── hermes/
│   ├── skills/                  ← analyst / debate / PM / risk / reflection prompts
│   └── templates/schemas/       ← analyst / deliberation / evolution JSON-Schemas
└── docs/hermes/                 ← this directory
```

## CLI entry points

- `python -m digiquant.olympus.atlas.graph --run-type baseline|delta|monthly` — research only.
- `python -m digiquant.olympus.hermes.graph --from-digest <path>` — Hermes only over a saved Atlas state JSON.
- `python -m digiquant.olympus.hermes.chain --run-type baseline|delta|monthly` — full Atlas → Hermes → publish chain. **This is what cron uses.**

## Documents

- [`HERMES_SUBGRAPH.md`](HERMES_SUBGRAPH.md) — full sub-graph spec (topology, persistence, schemas).
- [`WAVE2_UNIT_SPECS.md`](WAVE2_UNIT_SPECS.md) — implementation units for the Wave 2 expansion (h1 thesis review, h2 market-thesis exploration, h3 vehicle map, h4 opportunity screen, h5 asset analyst, h6 deliberation, h7 PM allocation memo).
- [`AGENTS.md`](AGENTS.md) — agent operator guide.

## Test layout

```
tests/dq/hermes/
├── conftest.py                     ← collection gate (digigraph importable)
├── test_phase7c_specialists.py
├── test_phase7cd_debate.py
├── test_phase7d_risk_debate.py
├── test_phase9_reflection.py
└── test_chain_atlas_then_hermes.py ← Atlas → Hermes integration
```
