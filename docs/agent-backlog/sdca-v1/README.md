# SDCA v1 — issue pack (epic + 9 work packages)

Consolidated, self-contained executor briefings for the program tracked as
[epic #3167](https://github.com/digithings-ai/digithings/issues/3167) (part of the parent SDCA epic,
[#1078](https://github.com/digithings-ai/digithings/issues/1078)). All 10 issues below are **already
filed on GitHub** — this folder exists so a Cursor (or any other) agent session that only has repo
access, not GitHub issue access, can execute the whole program from committed files, and so the plan
survives independent of the issue tracker.

Each WP file is a **self-contained executor briefing**: a cost-effective model should be able to
implement it from the file alone, without re-deriving anything from the epic or from chat history.
The goal, scope, and acceptance criteria are what was actually filed (the "Context / links" and
"Documentation" sections match the GitHub issue verbatim); each file additionally prepends a **Read
first** and **Branch** block that the GitHub issue bodies don't carry.

## Where we actually are (2026-08-30)

[#1080](https://github.com/digithings-ai/digithings/issues/1080),
[#1081](https://github.com/digithings-ai/digithings/issues/1081) and
[#1082](https://github.com/digithings-ai/digithings/issues/1082) are closed — the SDCA engine is real,
22 unit tests, no placeholders. But **nothing is published, nothing is fitted on real data, and no path
exists from a `RiskModel` to a running backtest.** The pieces are a kit, not a strategy. Full detail:
[`EPIC.md`](EPIC.md).

## Filing status

All 10 issues are filed. No `gh issue create` step is needed — this pack is for **execution**, not
filing. If an issue ever needs to be re-filed (e.g. a fresh repo with no GitHub issue history), copy
the corresponding `.md` file's body verbatim as the issue body; each file's first line is an HTML
comment carrying the exact title to use.

## Labels / routing / model per WP

| WP | Issue | Title | Component label | Base branch | Risk | Model | Human gate |
|----|-------|-------|-----------------|-------------|------|-------|------------|
| — | [#3167](https://github.com/digithings-ai/digithings/issues/3167) | epic | `component:digiquant` | n/a | n/a | n/a | n/a |
| A1 | [#3168](https://github.com/digithings-ai/digithings/issues/3168) | Risk-index builder | `component:digiquant` | `module/digiquant` | low | sonnet | no |
| A2 | [#3169](https://github.com/digithings-ai/digithings/issues/3169) | Parametric curve | `component:digiquant` | `module/digiquant` | med | opus | no |
| A3 | [#3176](https://github.com/digithings-ai/digithings/issues/3176) | Equity valuation spike | `component:digiquant` | `module/digiquant` | low | opus | no (research only) |
| B1 | [#3170](https://github.com/digithings-ai/digithings/issues/3170) | Publish `btc_sdca` (registry/settings/tearsheet) | `component:digiquant` | `module/digiquant` | med | opus | no |
| B2 | [#3173](https://github.com/digithings-ai/digithings/issues/3173) | Real BTC fit (needs network) | `component:digiquant` | `module/digiquant` | med | sonnet | no — but gates all publishing |
| B3 | [#3175](https://github.com/digithings-ai/digithings/issues/3175) | Generic per-asset `RiskModel` | `component:digiquant` | `module/digiquant` | med | opus | no |
| C1 | [#3171](https://github.com/digithings-ai/digithings/issues/3171) | DCA-native tearsheet metrics (schema 1.3) | `component:digiquant` | `module/digiquant` | med | opus | no |
| D1 | [#3172](https://github.com/digithings-ai/digithings/issues/3172) | digiquant.io renders `dca` kind | `component:digiquant-web` | `develop` (one-hop, #1310) | low | sonnet | no |
| D2 | [#3174](https://github.com/digithings-ai/digithings/issues/3174) | Walk-forward optimization | `component:digiquant` | `module/digiquant` | med | opus | no |

`digiquant` WPs are two-hop: `make task ISSUE=N` off `module/digiquant` (verify it isn't stale behind
`origin/develop` first — `make task` now refuses a stale module base itself, see root `CLAUDE.md`).
`digiquant-web` (D1 / #3172) is one-hop straight to `develop` per #1310.

## Dependency graph and waves

```
Wave A (no deps — start all three immediately)
  A1 #3168 risk-index builder        A2 #3169 parametric curve        A3 #3176 equity spike (research)

Wave B (after A1 / #3168 merges)
  B1 #3170 publish btc_sdca   B2 #3173 real BTC fit (network)   B3 #3175 generic RiskModel

Wave C (after B1 / #3170 merges)
  C1 #3171 DCA-native metrics (schema 1.3)

Wave D (after C1; D2 also needs A2 + B2)
  D1 #3172 digiquant.io renders dca kind      D2 #3174 walk-forward optimization
```

- **A3 (#3176)** is a research spike with no code dependency on anything else in this pack; run it
  whenever, it only gates whether equity-SDCA implementation issues get filed later.
- **B2 (#3173) needs outbound network access** to fill the price cache and cannot be completed in a
  network-isolated sandbox — see its own file for the explicit warning. Run it on a runner that can
  reach Coinbase.
- **Nothing may push to Supabase or publish a tearsheet to digiquant.io until B2 (#3173) lands** — a
  tearsheet fitted on the placeholder synthetic coefficients would be a fabricated public number. This
  is called out again in B1/#3170's acceptance criteria.
- **D2 (#3174)** is the last WP to become ready: it needs A2 (#3169, the curve becomes optimizable),
  C1 (#3171, the objective it optimizes against), and B2 (#3173, real rails — optimizing against
  synthetic rails is optimizing against nothing).

## File-ownership discipline (prevents cross-agent merge conflicts)

Run one WP per agent session; don't hand an agent the whole pack. Each WP file's own "Files" /
"Scope" section is the file list — an agent must not touch files outside it except these shared
append points:

- `digiquant/ARCHITECTURE.md` § SDCA Engine — every WP adds its own module-table row / `##`/`###`
  subsection; never edit another WP's section.
- `digiquant/src/digiquant/mcp_server.py` — A1/#3168 adds `digiquant_build_sdca_risk_index`; B3/#3175
  extends its `risk_model` selector afterward. Sequential by the wave order above, not concurrent.
- `digiquant/src/digiquant/strategies/registry.py` and `.../settings.json` — B1/#3170 owns these for
  this pack; do not add entries from another WP.
- `digiquant/src/digiquant/strategy_specs.py` — D2/#3174 owns the `sdca` entry.

Rebase on the base branch immediately before opening each PR.

## Verification is the exit condition

Every WP file ends with exact acceptance criteria and the `pytest -m unit -k ...` selector to run.
`make score` must clear all four dimensions (Security ≥8, Quality ≥8, Optimization ≥7, Accuracy ≥9)
per root `CLAUDE.md`. Do not open a PR red. Per the org review policy
([docs/agents/CODE_REVIEW_POLICY.md](../../agents/CODE_REVIEW_POLICY.md)), each task PR gets its own
review at the task-PR stage (fresh-context `/review`, Cursor Bugbot, or another hatch in that policy)
— that's cheaper and more actionable than reviewing the eventual `module/digiquant` → `develop`
promotion, which is the wrong moment to catch a finding.

## Never touch

Live-trading paths (`digiquant/src/digiquant/brokers/live/` must not exist yet), digikey auth code,
`.github/workflows/` (unless a WP explicitly says so), another WP's files.

## Definition of done for v1 (program-level, from the epic)

- [ ] `btc_sdca` appears in the digiquant.io strategy library with a full tearsheet, refreshed by the
      nightly pipeline like the Slappers.
- [ ] Its rails come from a real BTC fit over real cached history (B2/#3173), with fit window and
      coefficient provenance stated in the tearsheet notes.
- [ ] Its curve is the output of a walk-forward optimization (D2/#3174) with a stated objective and an
      out-of-sample segment, not a hand-authored preset.
- [ ] The published metrics are DCA-native (C1/#3171): vs-lump-sum, vs-flat-DCA, cost basis, capital
      deployed — no win-rate theatre.
- [ ] The same code path runs `eth_sdca` and `sol_sdca` (B3/#3175) with only a different `RiskModel` +
      settings entry.

## Non-goals for v1

- Live trading. Any broker path stays behind the human gate (root `CLAUDE.md`).
- RS-driven risk (#1082 item 4) — belongs with the RS rotation layer, #1084.
- On-chain valuation indicators — already scoped as #1086.
- The PineScript port — #1083, after the Python shape is final.
- The master composition engine — #1078's later phase.

## Files in this pack

- [`EPIC.md`](EPIC.md) — the epic body (#3167), verbatim.
- [`3168.md`](3168.md) · [`3169.md`](3169.md) · [`3170.md`](3170.md) · [`3171.md`](3171.md) ·
  [`3172.md`](3172.md) · [`3173.md`](3173.md) · [`3174.md`](3174.md) · [`3175.md`](3175.md) ·
  [`3176.md`](3176.md) — one file per WP, named by its GitHub issue number.
