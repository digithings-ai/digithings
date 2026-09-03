# SDCA research state

Canonical answer to "what's the current best validated candidate right now."
Every trial report compares against **this file's current entry**, not against
memory, prose from an earlier session, or `settings.json`. This file exists
because those three previously disagreed about which config was "the
baseline," which cost a `git log -p settings.json` dig to untangle.

Update this file only on an explicit accept from Chris. Update `settings.json`
separately (his call, possibly later — accepting a candidate here does not
by itself mean it ships).

## Current best validated candidate

- **Weights:** `power_law=1.0, m2=0.5, dxy=0.5` (all other indicators — `rs_eth`,
  `weekly_rsi`, `weekly_macd`, `sma_band` — at `0.0`)
- **Curve:** published `btc_optimized` shape (buy knee 24.1, sell knee 71.9)
- **Validated:** +84.90% OOS (`curve_simulator`), +84.78% OOS (`nautilus`,
  `evaluate_sdca_trial_nautilus`) — same 3-fold walk-forward split, both
  evaluators agree to within 0.1pp once both are run fresh under current code.
- **Date:** 2026-09-03

## Known discrepancy: this is NOT what's live in settings.json

`digiquant/src/digiquant/strategies/settings.json`'s `btc_sdca` block currently
has `weekly_rsi=0.25, weekly_macd=0.5` turned on in addition to the three
weights above (set by commit `82cd1ddcc`, an unrelated "Cursor Agent" commit
that itself documents `beats_flat_dca_oos: false`). That 5-weight live config
has been walk-forward-validated twice this session and loses both times:

- `btc_5member_curve_walkforward_provenance.json`: mean OOS vs-flat-DCA =
  **-16.21%** (curve re-fit to match the live 5-weight index, still loses OOS)
- Ad-hoc fresh 7-indicator Stage-A search scoring the exact live weight set:
  **-46.23% to -51.28%** OOS (varies with rolling-composite window; see
  git log on `composite_rolling_window` work, commit `b38c89440`)

No provenance file currently has `beats_flat_dca_oos: true`. The 3-weight
baseline above is the best validated result, not a strategy that reliably
beats flat DCA — "current best candidate" and "beats the public benchmark"
are different claims; don't conflate them in a trial report.

**Open question for Chris:** is the "Cursor Agent" process still actively
changing this composite? Reverting `settings.json` to the validated 3-weight
baseline is only safe to propose once that's confirmed — see immediate
backlog item 3 below.

## Standard trial protocol

Every iteration, in order:

1. State the hypothesis (what's changing and why) up front.
2. "Index then curve, repeat" (`digiquant/AGENTS.md` § index-then-curve) —
   re-run the Stage-A weight search if the index changed, then re-fit the
   curve against the new index. Never fit a curve against a stale index.
3. `curve_simulator` first for a fast go/no-go. Only promote to a full
   Nautilus walk-forward if the candidate clears `curve_simulator` — don't
   spend a Nautilus pass on a loser.
4. Emit a tearsheet via `scripts/emit_sdca_trial_tearsheet.py` — get the
   visual before any accept/reject discussion. See its `--help` / module
   docstring for the CLI and the preview flow
   (`frontend/digiquant-web/app/strategies/preview/page.tsx`).
5. Report a compact metrics table (IS/OOS vs-flat-DCA under both evaluators,
   max drawdown, capital_deployed_pct, buy/sell dwell time) alongside the
   preview link.
6. Only on Chris's explicit accept: update this file, and separately
   (his call) `settings.json`.

Never call a config "the baseline" without citing this file's current entry.
If a trial's own weight set is later validated and accepted, replace the
"Current best validated candidate" section above — don't leave two entries
that could both be read as "the baseline."

## Immediate backlog (proposed order)

1. Fresh Stage-A weight search on the dead-zone-fixed rolling composite
   (`composite_rolling_min_samples=20`, window ∈ [1095, 1825] days — OOS was
   flat across that range, see commit `b38c89440`), scored against the
   corrected true baseline above, not the live 5-weight config.
2. Joint period re-tuning of the five confluence indicators (RSI 8/7, MACD
   6/13 or 8/17, SMA-band 60/10, rs_eth 90/45, power_law-trend 120d) — each
   was smoke-tested individually; never applied jointly.
3. Ask Chris directly whether the "Cursor Agent" process is still active on
   this composite — determines whether reverting `settings.json` to the
   validated baseline is safe to propose.
4. Infra: fix `nautilus_evaluator.py`'s one-`BacktestEngine()`-per-process
   crash (currently forces a subprocess-per-fold workaround) — worth doing
   early since this loop leans on Nautilus validation every iteration.
5. Regenerate the stale `btc_optimized_provenance.json` (predates this
   session's confluence-indicator upgrades, so its cached numbers no longer
   describe the current code path).
