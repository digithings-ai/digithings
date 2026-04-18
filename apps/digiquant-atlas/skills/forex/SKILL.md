---
name: market-forex
description: Run forex and currency analysis as part of the daily digest. Covers DXY, major pairs, EM currencies, carry trades, and FX as a risk sentiment signal. In the orchestrator, run as Phase 4C — output (DXY direction) feeds into international, commodities, and materials analysis.
---

# Forex Analysis Skill — v2

## Inputs
- `config/watchlist.md` (forex section)
- `config/preferences.md`
- Macro regime output
- Bonds output (rate differentials drive FX)

## Data Layer

> DB-first: read FX levels from Supabase (`daily_snapshots.market_data` / `documents.payload`).

For live rates, cross-currency calculations, and historical comparisons use the `mcp_frankfurter-f_*` tools:
- `mcp_frankfurter-f_get_latest_exchange_rates` — live rates for any base currency (e.g. base=USD for all pairs)
- `mcp_frankfurter-f_get_historical_exchange_rates` — rates over a date range for trend analysis
- `mcp_frankfurter-f_convert_currency_latest` — convert a specific amount between two currencies

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any central bank statement, geopolitical news article, or FX analysis page URL. Not for API endpoints, `.json`, or `.md` files.

---

## Research Steps

### 1. US Dollar (DXY)
- DXY level and 24h change
- Is the dollar strengthening or weakening?
- Key technical level: is it above or below 200-day MA? Near recent highs/lows?
- Dollar direction is the master variable for commodities, EM equities, and risk assets

### 2. Major Pairs
For each pair in watchlist:
- EUR/USD: price, direction, key ECB/Fed divergence driver
- USD/JPY: level, any BOJ intervention risk, carry implications
- GBP/USD: UK macro, any political or data driver
- USD/CAD: oil correlation, any CAD-specific catalyst
- AUD/USD: China proxy, commodity currency

### 3. Risk Sentiment from FX
- AUD/USD and NZD/USD rising = risk-on signal
- USD/JPY rising without yen intervention = carry risk-on
- Safe haven demand: JPY, CHF appreciating = risk-off
- EM currencies: strengthening = global risk appetite
- Summarize: what is FX collectively saying about risk sentiment?

### 4. Carry Trade Watch
- Is the yen carry trade under stress? (rapid USD/JPY moves can cause cross-asset liquidation)
- Any sudden JPY strengthening that could ripple into equities/crypto?

### 5. EM FX Stress Monitor
- **DXY and EM currencies**: strong DXY → EM capital outflows → EM currency weakness
- Key EM FX pairs: USD/BRL, USD/TRY, USD/ZAR, USD/MXN — any stress?
- EM FX Volatility Index (EMVX) if available
- Any country-specific EM currency crisis risk?
- USD/CNH (offshore yuan): PBOC fixing vs market rate — any significant divergence indicating stress?

### 6. Real Effective Exchange Rates (REER)
- USD REER: Is the dollar overvalued or undervalued on a trade-weighted, inflation-adjusted basis?
- Overvalued USD REER = headwind for US multinational earnings (currency effect on overseas revenues)
- EUR REER, JPY REER: any currency that is dramatically mis-valued creating regime risk?

### 7. Canadian Dollar (if relevant)
- USD/CAD level
- Oil correlation holding? (At $112 WTI, CAD should be strong)
- Any Bank of Canada signals or Canada-specific macro events?

## Output Format

```
### 💱 FOREX
**DXY**: [Level (±X%) | Trend: strengthening/weakening | Key level: ...]

**Key Pairs**:
- EUR/USD: X.XXXX (±X%) | [driver]
- USD/JPY: XXX.XX (±X%) | [driver / intervention risk?]
- GBP/USD: X.XXXX (±X%) | [driver]
- USD/CAD: X.XXXX (±X%) | [oil/BoC driver]

**EM FX Stress**: [Any EM currency crisis signal | USD/CNH fixing vs market]

**FX Risk Signal**: [Risk-on / Risk-off / Mixed — rationale]

**Carry Watch**: [Yen carry stable/stressed | implication for risk assets]

**USD REER**: [Over/undervalued — implication for US multinational earnings]

**Watch**: [Key FX event or level to monitor]
```

