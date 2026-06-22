# Hermes — thesis-aware portfolio loop

Hermes consumes a research [`DigestPayload`](../../atlas/snapshot.py) from
[Atlas](../atlas/) and runs **H1–H9**: market thesis review → exploration → vehicle map →
opportunity screener → unified asset analyst → PM↔analyst deliberation → PM direction →
deterministic risk sizing → **`commit_run`** terminal booking.

See [ADR-0015](../../../../../docs/adr/0015-atlas-vs-hermes.md) and
[ADR-0020](../../../../../docs/adr/0020-olympus-mvp-daily-delta.md). Full topology:
[`ARCHITECTURE.md`](ARCHITECTURE.md).

## Phases (live graph — H1–H9)

| Step | Node | Purpose |
|------|------|---------|
| H1–H2 | thesis review + exploration | Market thesis lifecycle |
| H3–H4 | vehicle map + screener | Roster for analyst fan-out |
| H5 | `asset_analyst` (×N) | Unified `AnalystPayload` per ticker |
| H6 | `deliberation` (×N) | PM↔analyst cyclic sub-graph |
| H7 | `pm-direction` | `PMDirectionMemo` — direction + rank only |
| H8 | `risk-sizing` | Deterministic sizer (legacy 7E module) |
| H9 | `commit_run` | Terminal: positions, nav, brief, `decision_log` |

## Code layout

```
digiquant/src/digiquant/olympus/hermes/
├── graph.py                 ← build_hermes_phases_thesis / build_hermes_graph
├── chain.py                 ← run_atlas_then_hermes (cron entry)
├── phases/
│   ├── h1_thesis_review.py … h9_commit_run.py
│   └── phase7e_risk_sizing.py   ← H8
├── skills/                  ← thesis, asset-analyst, deliberation, pm-direction, …
└── docs/                    ← this directory
```

## CLI entry points

- `python -m digiquant.olympus.hermes.chain --cadence daily` — full Atlas A0–A4 → Hermes H1–H9. **Cron uses this** (`.github/workflows/pipeline-olympus.yml`).
- `--refresh-scope` — operator full refresh (`all`, `segments`, `hermes`, `digest`, `beliefs`)
- `python -m digiquant.olympus.hermes.graph --from-digest <path>` — Hermes only
- Deprecated: `--run-type baseline|delta` (warns); `monthly` rejected

## Documents

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — canonical H1–H9 map
- [`HERMES_SUBGRAPH.md`](HERMES_SUBGRAPH.md) — historical Wave 2 spec (topology now shipped)
- [`WAVE2_UNIT_SPECS.md`](WAVE2_UNIT_SPECS.md) — historical unit IDs
- [`AGENTS.md`](AGENTS.md) — extension checklist

## Tests

```
tests/dq/hermes/          ← H-path phase tests + chain integration
tests/dq/olympus/         ← edit-mode, commit_run, simulator gates
```
