<!-- title: [epic] SDCA v1 — ship btc_sdca as a live, published, optimized strategy on digiquant.io -->

Filed as [#3167](https://github.com/digithings-ai/digithings/issues/3167). Part of #1078. Sequencing
epic for the SDCA workstream: turn the engine we already built into a **published strategy on
digiquant.io alongside the Slappers**, calibrated on BTC, then generalize to other assets.

**Primary component:** digiquant (+ digiquant-web)
**Risk:** n/a (tracking epic)
**Type:** epic

## Where we actually are (2026-08-30)

#1080, #1081 and #1082 are all closed, and the engine is real — 22 unit tests, no placeholders. But
**nothing is published, nothing is fitted on real data, and no path exists from a `RiskModel` to a
running backtest.** The pieces are a kit, not a strategy.

| Piece | File | State |
|---|---|---|
| `RiskModel` protocol | `sdca/risk_model.py` | ✅ done |
| Valuation z-score | `sdca/valuation.py` | ✅ done |
| Composite risk (weighted vote → 0–100) | `sdca/composite_risk.py` | ✅ done |
| 21-node accum/dist curve | `sdca/curve.py` | ✅ done |
| Parity backtest harness | `sdca/backtest.py` | ✅ done (CI-only; never the published result) |
| Nautilus strategy wrapper | `sdca/nautilus_strategy.py` | ✅ done — but takes a `risk_path` parquet **nothing produces** |
| Curve presets | `sdca/presets.json` | ✅ 4 hand-authored personalities, **unoptimized** |
| BTC power-law provider | `sdca/btc_power_law.py` | ✅ code done; ❌ **coefficients are a synthetic placeholder** (`*.example.json`) |

### The seven gaps between here and "a live strategy on the site"

1. **No glue.** `BtcPowerLawRiskModel` is unreachable from `SdcaStrategy`. There is no function that
   goes rails → valuation-z → composite risk → the `date`/`risk` parquet the strategy loads. Flagged
   in the #3160 review and deliberately deferred. → **#3168**
2. **The curve is 21 free numbers.** Un-optimizable as-is, and the owner's actual requirement — *flat
   around fair value, progressively harder as valuation extends either way* — is a **shape**, not 21
   independent knobs. → **#3169**
3. **SDCA is not in the registry**, so `generate_tearsheets.py` (which builds every strategy via
   `get_strategy()`) cannot run it, and `settings.json` has no non-Slapper family. → **#3170**
4. **The tearsheet schema is trade-shaped.** `win_rate_pct`, `profit_factor`, `long`/`short`
   breakdowns are near-meaningless for a DCA book that mostly accumulates. The honest headline
   numbers for SDCA are **vs-lump-sum**, **vs-flat-DCA**, **average cost basis**, and **capital
   deployed**. → **#3171** (backend) / **#3172** (renderer)
5. **The BTC fit was never run on real data.** #1082 shipped validated against synthetic fixtures
   because the build sandbox had no network. Publishing rails fitted to fake data would be a false
   public claim. → **#3173**
6. **Nothing is optimized.** The presets are hand-authored personalities, explicitly "not tuned". No
   `strategy_specs.py` entry, so `digiquant_run_optimize` cannot touch SDCA. → **#3174**
7. **Only BTC is possible.** #1082's scope items 3 (generic per-asset valuation-z) and 4 (RS-driven
   risk) were never implemented — the issue closed on item 2 alone. → **#3175** (crypto) / **#3176**
   (equities, research-first)

## Target behaviour (owner's statement, 2026-08-30)

> Give it X amount of money. As valuations get lower the system buys progressively more; as they get
> higher it progressively sells a percentage of what it holds. Around the mean it does nothing.

Restated as an acceptance shape for the curve:

- a **dead zone** spanning fair value where the daily rate is exactly `0` — SDCA holds and does
  nothing;
- **progressive accumulation** below it: rate rises monotonically as risk → 0, spending from cash
  reserves;
- **progressive distribution** above it: rate falls monotonically as risk → 100, selling a
  *percentage of holdings* (never a fixed size, so it can never sell what it does not hold);
- the whole shape controlled by a handful of parameters an optimizer can search (#3169), not 21
  hand-set nodes.

Daily bars, one decision per day. Long-only is a config-level clamp, not a separate strategy.

## Sequencing

**Phase 1 — make it runnable end-to-end (no new maths).**
- [ ] #3168 — risk-index builder + MCP tool
- [ ] #3173 — real BTC fit, committed coefficients, rail validation *(needs network — cannot be done
      in a sandboxed session)*

**Phase 2 — make it publishable.**
- [ ] #3169 — parametric curve
- [ ] #3170 — registry + settings + tearsheet generation for `btc_sdca`
- [ ] #3171 — DCA-native metrics (schema 1.3)
- [ ] #3172 — digiquant.io renders the `dca` kind

**Phase 3 — make it good.**
- [ ] #3174 — walk-forward optimization of curve shape + indicator weights

**Phase 4 — make it general.**
- [ ] #3175 — generic per-asset valuation-z provider → `eth_sdca`, `sol_sdca`, `doge_sdca`
- [ ] #3176 — equity valuation research spike (PE, put/call, Buffett indicator) — spike before any
      implementation issue is filed

Phase 3 is where the strategy earns its place in the library; Phases 1–2 are what make Phase 3
measurable at all. **Do not publish a tearsheet before #3173 lands** — rails fitted to synthetic data
would put a fabricated backtest on a public site.

## Definition of done for v1

- [ ] `btc_sdca` appears in the digiquant.io strategy library with a full tearsheet, refreshed by the
      nightly pipeline like the Slappers.
- [ ] Its rails come from a real BTC fit over real cached history, with the fit window and coefficient
      provenance stated in the tearsheet notes.
- [ ] Its curve is the output of a walk-forward optimization with a stated objective and an
      out-of-sample segment, not a hand-authored preset.
- [ ] The published metrics are DCA-native: vs-lump-sum, vs-flat-DCA, cost basis, capital deployed —
      no win-rate theatre.
- [ ] The same code path runs `eth_sdca` and `sol_sdca` with only a different `RiskModel` + settings
      entry.

## Non-goals for v1

- Live trading. Any broker path stays behind the human gate (CLAUDE.md).
- RS-driven risk (#1082 item 4) — belongs with the RS rotation layer, #1084.
- On-chain valuation indicators — already scoped as #1086.
- The PineScript port — #1083, after the Python shape is final.
- The master composition engine — #1078's later phase.

## Context / links

- Reference artifact (owner's): https://sdca-signals-automation-production.up.railway.app
- Publish path: `digiquant/scripts/generate_tearsheets.py --push-supabase` → Supabase
  `strategy_tearsheets.metrics` → `frontend/digiquant-web` reads it live, no redeploy (#1069).
- Engine docs: `digiquant/ARCHITECTURE.md` § "SDCA Engine (#1080, #1081)".
- Optimization engine epic: #1079.
