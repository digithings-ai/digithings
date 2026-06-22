# Hermes — agent operator guide

> Sibling of [`digiquant/src/digiquant/olympus/atlas/docs/AGENTS.md`](../../atlas/docs/AGENTS.md).
> Atlas owns research (A0–A4); Hermes owns thesis-aware portfolio loop (H1–H9).
> Boundary: [ADR-0015](../../../../../../docs/adr/0015-atlas-vs-hermes.md) · Spec §9–§11:
> [`docs/superpowers/specs/2026-06-20-olympus-daily-thesis-design.md`](../../../../../../docs/superpowers/specs/2026-06-20-olympus-daily-thesis-design.md)

## What Hermes does

Hermes consumes the daily Atlas digest (`DigestPayload`) and runs **H1–H9**:

| Phase | Purpose | Key output |
|-------|---------|------------|
| H1–H2 | Market thesis review + exploration | `theses` rows, exploration docs |
| H3–H4 | Vehicle map + opportunity screener | `thesis_vehicles`, focus roster |
| H5 | Unified `AnalystPayload` per ticker | `phase_hermes.asset_analysts` |
| H6 | PM↔analyst deliberation (per ticker) | deliberation transcript + summary |
| H7 | PM direction memo | `PMDirectionMemo` — **no weights** |
| H8 | Deterministic risk sizing (7E) | `phase_hermes.sized_book` |
| H9 | Terminal `commit_run` | `positions`, nav, brief, `decision_log` |

## Entry points

- **Production:** `python -m digiquant.olympus.hermes.chain --cadence daily`
  (`--refresh-scope` for operator full refresh: `none|all|segments|hermes|digest|beliefs`).
  Deprecated shim: `--run-type baseline|delta` (warns; `monthly` rejected).
- **Standalone:** `python -m digiquant.olympus.hermes.graph --from-digest <state.json>`
- **Library:** `digiquant.olympus.hermes.chain.run_atlas_then_hermes(atlas_input, deps)`

## Extension checklist (§9–§11)

Before adding or changing a Hermes phase:

- [ ] Read spec §9–§11 and [`ARCHITECTURE.md`](ARCHITECTURE.md) H-path map
- [ ] Wire into `build_hermes_phases_thesis()` — **no parallel graph builders**
- [ ] At node entry: `resolve_edit_mode(...)`; load `*-full.md` or `*-edit.md` skill
- [ ] On `edit`: validate `DocumentPatch`, `merge_document_patch`, dual-publish delta + materialized row
- [ ] Wire `build_grounding` with correct phase blinding (§6.1 table)
- [ ] H7 phases: assert no weight fields (`test_pm_no_weights`)
- [ ] H8 remains deterministic — no LLM in sizing path
- [ ] Terminal booking only via H9 `commit_run` — do not reintroduce `portfolio_materialize` on daily path
- [ ] Add/update unit tests under `tests/dq/hermes/` or `tests/dq/olympus/`

## Skills

Each LLM phase loads from `digiquant/src/digiquant/olympus/hermes/skills/<slug>/`
via `digiquant.olympus.hermes.skills.load_skill`. Edit-mode skills use `*-edit.md`;
full rewrite uses `*-full.md`.

| Phase | Skills |
|-------|--------|
| H1 | `thesis` |
| H2 | `market-thesis-exploration` |
| H3 | `thesis-vehicle-map` |
| H4 | `opportunity-screener` (deterministic gate; skills for docs if needed) |
| H5 | `asset-analyst` |
| H6 | `deliberation` |
| H7 | `pm-direction` |

Cross-engine loads raise `SkillNotFoundError`.

## Schemas

Hermes JSON schemas under `digiquant/src/digiquant/olympus/hermes/templates/schemas/`:
`document-delta`, `AnalystPayload`, `PMDirectionMemo`, deliberation schemas,
`market-thesis-exploration`, `thesis-vehicle-map`, etc.
Loaded via `digiquant.olympus.hermes.schemas.load_schema(name)`.

## Persistence

- **H1–H7 artifacts:** `documents` + optional `document_deltas` via phase writers
- **H9 terminal:** `commit_run` upserts `positions`, `nav_history`, syncs `theses` /
  `thesis_vehicles`, publishes brief, appends `decision_log`
- **Atlas `publish_phase`:** research segments + digest only (chain terminal after Hermes)
- **Beliefs:** on-demand via `run_beliefs_distillation_if_triggered` — not a daily graph node

## Testing

```bash
pytest tests/dq/hermes/ -m unit -v
pytest tests/dq/olympus/ -m unit -v
pytest tests/dq/atlas/ -m unit -v
```

Hermes tests gate on `tests/dq/hermes/conftest.py` (full set in `atlas-graph-ci.yml`).

## Useful files

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — H1–H9 topology (canonical)
- [`HERMES_SUBGRAPH.md`](HERMES_SUBGRAPH.md) — historical Wave 2 spec
- [Atlas operator guide](../../atlas/docs/AGENTS.md)
- [Atlas runbook](../../atlas/docs/RUNBOOK.md)
