---
name: market-international
description: Deep-dive analysis of international and emerging markets. Covers Developed Markets (EFA, EWJ, EWG, EWU), Emerging Markets (EEM, MCHI, EWZ, EWT, EMB), and regional breakdowns across Asia, Europe, MENA, and LATAM. Signals include PBOC/China Politburo actions, DXY effect on EM, and regional geopolitical risk. Run as part of the Asset Class Deep Dives phase.
---

# International & Emerging Markets Skill

## Inputs
- `config/watchlist.md` (international ETFs: EEM, MCHI, EWJ, EWG, EFA, EWZ, EWT, EMB)
- `config/preferences.md`
- Macro regime output (regime context for risk appetite)
- Forex output (DXY and EM FX context)

---

## Data Layer

For structured country-level macro data use `mcp_world-bank_get_indicator_for_country` with:
- `NY.GDP.MKTP.KD.ZG` — GDP growth rate (annual %)
- `FP.CPI.TOTL.ZG` — CPI inflation (annual %)
- `GC.DOD.TOTL.GD.ZS` — central government debt as % of GDP
- `NE.TRD.GNFS.ZS` — trade (% of GDP)
- `BN.CAB.XOKA.GD.ZS` — current account balance (% of GDP)

Useful country codes: `CN` (China), `JP` (Japan), `DE` (Germany), `GB` (UK), `BR` (Brazil), `IN` (India), `KR` (South Korea), `MX` (Mexico), `TR` (Turkey).

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any regional news article, central bank statement, PBOC/BOJ/ECB policy page, or geopolitical report URL. Not for API endpoints, `.json`, or `.md` files.

---

## Research Steps

### 1. Developed Markets Overview
Search for current performance across DM:

**Europe:**
- **EFA** (iShares MSCI EAFE): broad DM ex-US, price, % change
- **EWG** (Germany — DAX proxy): largest Eurozone economy, industrial/export heavy
- **EWU** (UK — FTSE proxy): UK macro context; GBP exchange rate sensitivity
- **DAX / FTSE 100 / CAC 40**: overnight performance
- ECB recent meeting and rate path: are European rates diverging from Fed?
- Any European political risk: elections, coalition instability, EU budget
- Germany: manufacturing recession — PMI, industrial output

**Japan:**
- **EWJ** (Japan — Nikkei proxy): price and % change
- Nikkei 225 performance and context
- **BOJ policy**: any adjustment to yield curve control or rate stance? Most critical variable for EWJ
- USD/JPY level: strong yen hurts exporters (Toyota, Sony), weak yen boosts them
- Japanese corporate governance reforms: are earnings improving?
- Any Suga/Kishida/PM economic policy signals?

### 2. Emerging Markets Overview
**Broad EM:**
- **EEM** (iShares MSCI EM ETF): price, % change vs SPY
- EM vs DM relative performance: risk-on = EM outperforms; risk-off = DM/USD outperforms
- DXY correlation: strong dollar = EM currency headwind + capital outflows

**China (Critical Focus):**
- **MCHI** (iShares MSCI China): price and % change
- **FXI** (large-cap China): directional read
- PBOC: any policy rate cut, reserve requirement reduction, or window guidance?
- China Politburo / State Council: any economic stimulus announcement or Five-Year Plan directive?
- China PMI: NBS official and Caixin private sector readings
- Chinese real estate: Evergrande/Country Garden resolution status; housing starts
- Trade: any trade war escalation or de-escalation with US?
- Consumer confidence and retail sales data if recently published
- Strategic minerals / rare earths: export controls or geopolitical signals

**India:**
- **INDA** (iShares MSCI India): performance and trend
- RBI policy: interest rate direction
- Modi government fiscal policy: PLI scheme sectors, infrastructure buildout
- India as China alternative manufacturing hub (semiconductors, electronics)

**Brazil & LATAM:**
- **EWZ** (iShares Brazil): price and % change
- Brazil: central bank (BCB) rate policy, BRL direction, political risk
- Any LATAM commodity-currency signal from oil/metals prices
- Mexico: near-shoring beneficiary, USMCA trade flows

**Taiwan:**
- **EWT** (iShares Taiwan): price and change
- TSMC context: semiconductor supply chain signal; geopolitical risk
- Cross-strait tension: any escalation signal? (Most critical Taiwan risk)

**South Korea:**
- **EWY** if on watchlist: Samsung, SK Hynix semiconductor exposure; BOK policy

### 3. EM Debt Signal
- **EMB** (iShares EM Dollar-Denominated Bonds): price and yield
- EM sovereign spreads: widening (stress) or tightening (relief)
- Key EM debt risks: any country approaching IMF program, sovereign default risk
- Impact of US dollar strength on EM debt serviceability

### 4. DXY Effect on International Markets
From forex output (or re-check):
- USD strengthening → headwind for EM equities and EM fixed income (capital flows out)
- USD weakening → tailwind for EM equities; boosts international equity returns in USD terms
- What is the current DXY trend doing to international ETF returns?
- Which regions have the most DXY sensitivity?

### 5. Geopolitical & Regional Risks
- **Middle East / Iran War**: impact on MENA region, energy-exporting EM, shipping routes
- **Taiwan Strait**: any developments affecting EWT, semiconductor supply chain
- **Russia/Ukraine**: ongoing conflict effect on European energy, Eastern European ETFs
- **China-Taiwan flashpoints**: frequency of PLA air incursions or naval exercises
- **LATAM political instability**: any election or policy change risk

### 6. China Deep Focus (given dominance in EM)
China constitutes ~25-30% of EEM — a dedicated China read:
- Latest economic data: GDP trajectory, official vs private PMI divergence
- Property market: are prices bottoming? New lending data?
- Stimulus pipeline: size and composition of any new package
- PBOC tools: rate cuts, RRR cuts, re-lending facilities
- Geopolitical: any Taiwan or South China Sea developments
- Trade war: US tariffs, EU tariffs, any retaliatory measures
- Tech crackdown: regulatory environment for Chinese tech

---

## Output Format

```
### 🌏 INTERNATIONAL & EMERGING MARKETS
**Bias**: [Bullish EM / Bearish EM / DM-preferred / Neutral] | Confidence: [High / Medium / Low]

**DM (Developed Markets):**
| ETF | Region | Price | 24h | Driver |
|-----|--------|-------|-----|--------|
| EFA | Broad DM ex-US | $X | ±X% | |
| EWJ | Japan | $X | ±X% | BOJ: [hawkish/dovish] |
| EWG | Germany | $X | ±X% | PMI/political |
| EWU | UK | $X | ±X% | BoE/GBP |

**Emerging Markets:**
| ETF | Region | Price | 24h | Driver |
|-----|--------|-------|-----|--------|
| EEM | Broad EM | $X | ±X% | |
| MCHI | China | $X | ±X% | PBOC / stimulus |
| EWZ | Brazil | $X | ±X% | commodity/BRL |
| EWT | Taiwan | $X | ±X% | TSMC / cross-strait |
| EMB | EM Debt | $X | ±X% | spread direction |

**China Signal (Top Priority):**
- PBOC action: [Any stimulus / rate cut / RRR change]
- Economy: [PMI, property, consumer — improving or worsening?]
- Geopolitical: [Any Taiwan or trade war development]

**DXY Effect**: [Current DXY direction + impact on EM and international ETF returns]

**EM Risk Appetite**: [Are capital flows moving toward or away from EM?]

**Geopolitical Regional Risks:**
- Iran War: [Middle East / shipping route effect]
- Taiwan: [Any cross-strait tension update]
- Europe: [NATO/Ukraine/ECB signal]

**EMB (EM Debt)**: $X — [Spread direction and key country risk]

**Implication for Portfolio**: [Do we need international ETF exposure? Are EEM/MCHI/EWJ attractive vs domestic?]
```

---

