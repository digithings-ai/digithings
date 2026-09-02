# Pipeline screenshot matrix

Glass-box acceptance for #2645 / #1945: every Pipeline topology **stage** has
desktop + mobile fixtures, plus a representative **artifact family** set.

Product names stay lowercase in prose (`digithings`, `dashboard`, `digiquant`).

## Fixture layout

Committed under [`fixtures/screenshots/`](../fixtures/screenshots/):

| Path | Role |
|------|------|
| `manifest.json` | Canonical required path list (Vitest gate) |
| `stages/<stageId>-{desktop,mobile}.png` | One shot per topology stage × viewport |
| `artifacts/<family>-desktop.png` | Representative artifact / inspection surfaces |

## Stage × viewport matrix

Stages mirror `PIPELINE_TOPOLOGY` in `lib/pipeline-topology.ts`:

| Stage | Desktop | Mobile |
|-------|---------|--------|
| Inputs | `stages/inputs-desktop.png` | `stages/inputs-mobile.png` |
| Research | `stages/research-desktop.png` | `stages/research-mobile.png` |
| Synthesis | `stages/synthesis-desktop.png` | `stages/synthesis-mobile.png` |
| Selection | `stages/selection-desktop.png` | `stages/selection-mobile.png` |
| Decision | `stages/decision-desktop.png` | `stages/decision-mobile.png` |
| Learning | `stages/learning-desktop.png` | `stages/learning-mobile.png` |

Capture guidance:

- **Desktop:** walkthrough previous/next may open the selected step’s artifact.
- **Mobile:** previous/next only move/highlight; document open stays explicit tap.
- Prefer a representative run date with real persisted docs when available.

## Representative artifact families

| Family id | Example `document_key` / surface | Fixture |
|-----------|----------------------------------|---------|
| `attention-plan` | `attention-plan` | `artifacts/attention-plan-desktop.png` |
| `research-segment` | `macro` | `artifacts/research-segment-desktop.png` |
| `fanout-alt-data` | `alt-cta-positioning` | `artifacts/fanout-alt-data-desktop.png` |
| `fanout-analyst` | `analyst/QQQ` | `artifacts/fanout-analyst-desktop.png` |
| `digest` | `digest` | `artifacts/digest-desktop.png` |
| `deliberation` | `deliberation/QQQ` | `artifacts/deliberation-desktop.png` |
| `pm-direction` | `pm-direction-memo` | `artifacts/pm-direction-desktop.png` |
| `pm-rebalance` | `pm-rebalance` | `artifacts/pm-rebalance-desktop.png` |
| `commit` | `commit-run/…` | `artifacts/commit-desktop.png` |
| `beliefs` | `beliefs` | `artifacts/beliefs-desktop.png` |
| `call-trace` | Call trace panel (`olympus_run_event_trace`) | `artifacts/call-trace-desktop.png` |
| `artifact-ledger` | ledger-only e.g. `risk-debate` | `artifacts/artifact-ledger-desktop.png` |

Families align with `REPRESENTATIVE_RUN_DOCUMENT_KEYS` in
`lib/pipeline-document-discoverability.ts` plus the Call trace surface.

## Placeholders vs operator capture

CI only requires each manifest path to exist as a non-empty PNG (magic `\x89PNG`).
Initial commits may use 1×1 placeholders. Operators replace them with real
captures without changing the manifest path contract.

```bash
# From frontend/dashboard — fails if any required path is missing
npm run test -- lib/screenshot-manifest.test.ts
```

## Out of scope

- Full visual regression / pixel-diff suite
- Corpus \| Book \| Profile chrome (#2643)
- digiquant WP4 / live-trading paths
