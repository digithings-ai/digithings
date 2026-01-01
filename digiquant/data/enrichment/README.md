# Gold enrichment snapshots (#4804)

Research staging for gloomberb enrichment snapshots. This directory is
**gitignored staging** (like `digiquant/.scratch/`): snapshot JSON files are
never committed. This README is the only committed file here — it documents
the layout so a fresh checkout (or the first live pull) reproduces it.

## Layout

Per tool, under `snapshots/<tool>/`:

```text
digiquant/data/enrichment/
  README.md                        # this file (committed)
  snapshots/                       # gitignored — local only
    <tool>/
      <YYYY-MM-DD>__<params12>.json  # one dated page per param set
      latest.json                    # pointer copy of the newest page
      <YYYY-MM-DD>__<params12>.metrics.json  # sidecar (options-skew only)
```

- `<params12>` is the first 12 hex chars of the SHA-256 of the canonical
  (sorted-keys) dispatcher params — one page per distinct param set per day.
- `latest.json` is refreshed on every write; pruning never deletes it.
- The `.metrics.json` sidecar exists only for `digifetch_options_chain`
  (per-expiry put/call OI + volume ratios); every other pull is snapshot-only.

## Provenance header

Every page wraps one dispatcher JSON payload with this header
(`src/digiquant/data/enrichment/snapshots.py::write_snapshot`):

| field | value |
|---|---|
| `snapshot_version` | `1` |
| `tool` | dispatcher name, e.g. `digifetch_news` |
| `params` | exact dispatcher args sealed |
| `fetched_at` | UTC `YYYY-MM-DDTHH:MM:SSZ` (also sources the `<YYYY-MM-DD>` stem) |
| `source` | `"gloomberb"` |
| `delay_notice` | `"Data delayed up to 15 minutes"` |
| `attribution` | `"Sourced from Gloomberb"` |
| `payload` | raw dispatcher `content` JSON string |

## Enrichment-only rule

Snapshots are enrichment-only by construction: free-tier data is delayed up
to 15 minutes, rate-limited, and history-capped — **never a pipeline input**.
Pipeline inputs stay on the R2/Supabase path. Nothing here is a source of
record; these pages are labeling context for later analysis.

## Pull inventory

All pulls go through the in-process digifetch dispatcher
(`data/gloomberb/agent_tools.py::build_digifetch_tool_dispatcher`) and are
implemented in `digiquant/scripts/pull_gold_enrichment.py`:

| subcommand | tool | params |
|---|---|---|
| `options-skew [--expiration EPOCH]` | `digifetch_options_chain` | `{"symbol": "GLD"}` (+ optional `expiration`). Per-expiry put/call OI + volume ratios from OI/volume/strike/side/expiration only — the free tier returns no greeks (IV rides along raw inside the snapshot). |
| `13f-gld` | `digifetch_13f_funds` | `{"what": "tickers", "tickers": ["GLD"]}`. The funds `holders` branch is never called (upstream 400s on every period format probed). |
| `econ-calendar` | `digifetch_econ_calendar` | `{}` (parameterless upstream; fixed ~105-row window). |
| `gold-news [--limit N]` | `digifetch_news` | `{"feed": "ticker", "ticker": "GLD", "limit": 50}` (limit bound 1–100). |
| `probe-lbma` | `digifetch_econ_series` | `{"series_id": <candidate>, "limit": 5, "sort_order": "desc"}` per candidate. **Hit-only**: a series with non-empty `observations` is snapshotted; misses record `None` and write nothing. |

## Cadence

`digiquant/scripts/refresh_gold_enrichment.py` is the idempotent refresh:
options-skew + econ-calendar + gold-news run **every run** (fast-moving);
13f-gld + probe-lbma run only with `--include-slow` (slow-moving). Each tool
dir is pruned to `--keep` dated pages afterwards (default 30; `latest.json`
is never pruned). One pull failing prints a warning and continues — exit 1
only if **all** pulls fail.

The weekly workflow `.github/workflows/enrich-gold-refresh.yml`
(`enrich-gold-refresh`, Mondays 09:00 UTC + `workflow_dispatch`) always runs
with `--include-slow`. No secrets (anonymous tools only), no Supabase/R2
writes. First live run is a post-merge operator action via
`workflow_dispatch`.

## Manual runs

```bash
PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/pull_gold_enrichment.py options-skew
PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/refresh_gold_enrichment.py --include-slow --keep 60
```

(`pull_gold_enrichment.py` subcommands: `options-skew`, `13f-gld`,
`econ-calendar`, `gold-news`, `probe-lbma`. `refresh_gold_enrichment.py`
without flags runs the three fast pulls only.)

## Consumers

**Nobody consumes snapshots yet.** They are labeling context for Plan 4
analysis (snapshot consumers + labeling analysis). Do not invent consumers —
no pipeline, strategy, or dashboard reads this directory.

## LBMA probe verdict

From the Task 3 report (`task-3-report.md`):

> "LBMA candidate ids (`GOLDPMGBD228NLBM`/`GOLDAMGBD228NLBM`) are brief-given
> FRED-style ids, unverified against the live Gloomberb econ catalog — the
> probe exists precisely to answer that. If both miss live, that is signal
> for Plan 4, not a test edit."

Offline, the hit/miss logic is verified with canned dispatchers (a hit seals
exactly one page under `digifetch_econ_series/`; a miss snapshots nothing and
records `None`). Against the real catalog the question is still open — no
live pull has run in this plan, and the first live probe is the post-merge
operator run above. A hit stays enrichment-only here; promoting an LBMA
series to the native manifest is a Plan-4 candidate, not this plan.
