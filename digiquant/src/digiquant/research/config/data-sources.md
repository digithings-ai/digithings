# Data Sources Directory

Reference list for all external data sources used in the daily digest pipeline. Organized by data type.

---

## X/Twitter — Monitored Accounts

### Macro & Fed Policy
| Handle | Focus |
|--------|-------|
| @federalreserve | Official Fed communications |
| @nytimes_econ | NYT economic reporting |
| @MikeZaccardi | Macro quant, Fed watch |
| @MacroAlf | Global macro research |
| @JeffSnider_AIP | Eurodollar/monetary system |
| @LynAldenContact | Macro + Bitcoin research |
| @RaoulGMI | Macro + liquidity cycles |
| @zerohedge | Market news aggregation |
| @EconomPic | Data visualization, macro |

### Equity & Sector
| Handle | Focus |
|--------|-------|
| @ResearchEdge | Sector rotation, hedgeye |
| @KeithMcCullough | Macro/sector tactical |
| @StockMKTNewz | Breaking equity news |
| @unusual_whales | Options flow, dark pool |
| @tradingeconomics | Economic data releases |

### Crypto & Digital Assets
| Handle | Focus |
|--------|-------|
| @WClementeIII | BTC on-chain analysis |
| @glassnode | On-chain data |
| @woonomic | BTC valuation models |
| @CryptoCapo_ | Technical analysis |
| @100trillionUSD | BTC stock-to-flow |
| @BitcoinArchive | BTC news aggregation |

### Hedge Fund / Institutional
| Handle | Focus |
|--------|-------|
| @BillAckman | Pershing Square — direct signal |
| @RayDalio | Bridgewater (commentary) |
| @CliffordAsness | AQR factor research |
| @druckenmiller | Duquesne (rare posts) |

### Energy & Commodities
| Handle | Focus |
|--------|-------|
| @OilPrice_com | Energy news |
| @EIAgov | EIA official data |
| @MorganCME | Commodity analysis |
| @KobeissiLetter | Markets + energy cross |

### Geopolitical
| Handle | Focus |
|--------|-------|
| @Geo_Intel | Geopolitical intelligence |
| @IranIntl_En | Iran-specific news (English) |
| @StrategyPage | Military strategy analysis |

---

## Market Data — Free/Freemium Sources

### Equities & Indices
| Source | URL | Data |
|--------|-----|------|
| Yahoo Finance | https://finance.yahoo.com | Quotes, news, fundamentals |
| Finviz | https://finviz.com | Screener, heatmaps, sector charts |
| Barchart | https://barchart.com | Options, futures, ETF flows |
| ETF.com | https://etf.com | ETF holdings, flows, comparison |

### Macro & Economic Data
| Source | URL | Data |
|--------|-----|------|
| FRED (Fed Reserve) | https://fred.stlouisfed.org | Economic time series |
| CME FedWatch | https://cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html | Fed rate probabilities |
| US Treasury | https://home.treasury.gov/resource-center/data-chart-center/interest-rates | Yield curve daily |
| BLS | https://bls.gov | CPI, PPI, jobs data |
| ISM | https://ismworld.org | PMI manufacturing + services |
| Atlanta Fed GDPNow | https://atlantafed.org/cqer/research/gdpnow | Real-time GDP estimate |

### Bonds & Credit
| Source | URL | Data |
|--------|-----|------|
| FRED | https://fred.stlouisfed.org | Yield curve, credit spreads |
| TRACE (FINRA) | https://finra.org/investors/learn-to-invest/types-investments/bonds/trace | Bond transaction data |
| ICE BofA | via FRED | IG/HY credit spread indices |

### Options & Derivatives
| Source | URL | Data |
|--------|-----|------|
| CBOE | https://cboe.com | VIX, SKEW, P/C ratios |
| Unusual Whales | https://unusualwhales.com | Options flow, dark pool |
| Market Chameleon | https://marketchameleon.com | IV, options analytics |
| SpotGamma | https://spotgamma.com | GEX (gamma exposure) |

### Commodities
| Source | URL | Data |
|--------|-----|------|
| EIA | https://eia.gov | Oil/gas inventory, production |
| CME Group | https://cmegroup.com | Futures quotes and data |
| Kitco | https://kitco.com | Gold and metals |
| LME | https://lme.com | Base metal inventory levels |

### Crypto
| Source | URL | Data |
|--------|-----|------|
| Glassnode | https://glassnode.com | On-chain BTC/ETH analytics |
| CryptoQuant | https://cryptoquant.com | Exchange flows, miner data |
| CoinGlass | https://coinglass.com | Funding rates, liquidations, open interest |
| Alternative.me | https://alternative.me/crypto/fear-and-greed-index | Crypto Fear & Greed Index |
| Farside | https://farside.co.uk/bitcoin-etf-flow-all-data-chart | BTC spot ETF daily flows |

### Sentiment & Positioning
| Source | URL | Data |
|--------|-----|------|
| CFTC COT | https://cftc.gov/MarketReports/CommitmentsofTraders | Commitments of Traders (weekly) |
| Polymarket | https://polymarket.com | Prediction market probabilities |
| AAII Sentiment | https://aaii.com/sentimentsurvey | Retail investor sentiment |
| CNN Fear & Greed | https://edition.cnn.com/markets/fear-and-greed | Multi-factor fear/greed |

### Politician Tracking
| Source | URL | Data |
|--------|-----|------|
| Quiver Quant | https://quiverquant.com/congress-trading | STOCK Act filings aggregated |
| Capitol Trades | https://capitoltrades.com | Congress trades searchable |
| EDGAR EFTS | https://efts.sec.gov/LATEST/search-index | Direct SEC search |

### Hedge Fund Intelligence
| Source | URL | Data |
|--------|-----|------|
| EDGAR 13F | https://sec.gov/cgi-bin/browse-edgar?action=getcompany | Quarterly 13F filings |
| WhaleWisdom | https://whalewisdom.com | 13F aggregation |
| 13F.info | https://13f.info | 13F tracker |

---

## Key Economic Calendar

Monitor these scheduled releases:
- **Weekly**: EIA petroleum inventory (Wednesday 10:30 ET), CFTC COT (Friday after close)
- **Monthly**: CPI (mid-month), PPI (mid-month), PCE (end of month), ISM Manufacturing (1st business day), ISM Services (3rd business day), Non-Farm Payrolls (first Friday)
- **Quarterly**: GDP advance/preliminary/final estimates; FOMC meetings and minutes

Use https://tradingeconomics.com/calendar or https://forexfactory.com for the calendar view.

---

## Programmatic Data Sources (Auto-Fetched — No API Keys)

These sources are pulled automatically via `./scripts/fetch-market-data.sh` when you run a **local** fetch (optional). Scripts may write transient JSON + Markdown under `data/agent-cache/daily/YYYY-MM-DD/data/` (gitignored; see repo `data/README.md`). **DB-first runs** should use **Supabase** (`price_technicals`, etc.) and published documents first; on-disk fetch output is a fallback when present. Web browsing remains for narrative/qualitative context.

### Quotes & Technicals
| Source | Library | Data | Output |
|--------|---------|------|--------|
| Yahoo Finance | `yfinance` | OHLCV (3-month) for all ~60 watchlist tickers, ~15min delayed | `data/quotes.json` |
| pandas-ta | `pandas_ta` | RSI(14), MACD(12/26/9), SMA20/50/200, ATR(14), Bollinger Bands | computed from OHLCV |
| Yahoo Finance | `yfinance` | 52W high/low, volume ratio, SMA50/200 cross flags | `data/quotes-summary.md` |

Script: `scripts/fetch-quotes.py`

### Macro Series
| Source | Library | Data | Output |
|--------|---------|------|--------|
| US Treasury XML API | `requests` | Full yield curve 1M–30Y (no auth, prior business day) | `data/macro.json` |
| Yahoo Finance | `yfinance` | VIX (`^VIX`), SKEW (`^SKEW`) | `data/macro.json` |
| Yahoo Finance | `yfinance` | WTI (`CL=F`), Brent (`BZ=F`), Gold (`GC=F`), Silver (`SI=F`), NatGas (`NG=F`), Copper (`HG=F`) | `data/macro.json` |
| Yahoo Finance | `yfinance` | BTC-USD, ETH-USD | `data/macro.json` |
| Yahoo Finance | `yfinance` | USD/CAD, EUR/USD, USD/JPY, GBP/USD, DXY (`DX-Y.NYB`) | `data/macro.json` |
| Yahoo Finance | `yfinance` | HYG, LQD, JNK, TLT, BIL (credit/rate proxies) | `data/macro.json` |
| Computed locally | Python | 2s10s, 3m10y, 5s30s, 2s30s spreads + inversion flags | `data/macro.json` |

Script: `scripts/fetch-macro.py`

### Treasury Yield Curve URL
```
https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value=YYYYMM
```
No API key. Returns XML with daily yield curve for the requested month. Script tries current month, falls back to prior month if no data yet published.

### Installation
```bash
pip install -r requirements.txt
# yfinance>=0.2.40, pandas>=2.0.0, numpy>=1.24.0, pandas-ta>=0.3.14b, requests>=2.28.0
```

---

## MCP Servers (Agent-Accessible via VS Code Copilot + Claude Desktop)

Configured in `.vscode/mcp.json` (VS Code Copilot) and `~/Library/Application Support/Claude/claude_desktop_config.json` (Claude Desktop / Cowork). MCP servers extend the AI agent's capabilities — they are called directly by the agent during pipeline execution as structured data tools. They complement (not replace) the existing `fetch-*.py` scripts.

**Phase→Tool mapping** — use these tools at the listed phase instead of web-browsing for the same data:

| Server ID | Tool Prefix | What It Provides | Use In Phase |
|-----------|------------|-----------------|-------------|
| `fred` | `mcp_fred_*` | 800K+ FRED series: GDP, CPI, UNRATE, PCE, DGS10, DFF, T10YIE, T10Y2Y, credit spreads | Phase 3 (Macro) + Phase 4A (Bonds) |
| `polymarket` | `mcp_polymarket_*` | Prediction market probabilities: rate cuts, elections, geopolitical events | Phase 1 (Alt Data) |
| `crypto-feargreed` | `mcp_crypto-feargr_*` | Crypto Fear & Greed Index — current value, N-day history, trend analysis | Phase 1 (Alt Data) + Phase 4D (Crypto) |
| `coingecko` | `mcp_coingecko_*` | 200+ chains, 8M+ tokens, DeFi TVL, exchange volumes — free public tier | Phase 4D (Crypto) |
| `frankfurter-fx` | `mcp_frankfurter-f_*` | Live + historical FX rates across 30+ currency pairs | Phase 4C (Forex) |
| `world-bank` | `mcp_world-bank_*` | GDP growth, inflation, debt-to-GDP, trade data by country | Phase 4E (International) |
| `sec-edgar` | `mcp_sec-edgar_*` | 10-K/10-Q/8-K filings, XBRL financials, Form 3/4/5 insider trades | Phase 2 (Institutional) |
| `alpha-vantage` | `mcp_alpha-vantage_*` | Fundamentals, earnings calendar, news sentiment — 25 req/day | Phase 5 (Equities) |

> **SEC EDGAR**: Requires Docker running. Image: `stefanoamorelli/sec-edgar-mcp:latest`. User-Agent string as the only credential.
> **CoinGecko**: Free public tier — leave API key blank.

### Key FRED Series by Phase

| Phase | FRED Series IDs | Description |
|-------|----------------|-------------|
| Macro (3) | `DFF`, `DGS2`, `DGS10`, `DGS30`, `T10Y2Y`, `T10Y3M` | Fed Funds, yields, 2s10s/3m10y spreads |
| Macro (3) | `CPIAUCSL`, `PCEPI`, `UNRATE`, `GDP`, `GDPC1` | CPI, PCE, unemployment, GDP |
| Bonds (4A) | `T10YIE`, `T5YIE`, `DFII10` | 10Y/5Y TIPS breakeven, 10Y real yield |
| Bonds (4A) | `BAMLH0A0HYM2`, `BAMLC0A0CM` | HY OAS, IG OAS credit spreads |
| Macro (3) | `VIXCLS`, `DTWEXBGS` | VIX close, broad USD trade-weighted index |

### Key CoinGecko Queries

Use `mcp_coingecko_execute` with the path and method:
- Coin prices: `GET /simple/price?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true`
- Market overview: `GET /coins/markets?vs_currency=usd&order=market_cap_desc&per_page=20`
- Trending: `GET /search/trending`

### Key Polymarket Queries

- `mcp_polymarket_trending_markets` — top active markets today
- `mcp_polymarket_search_markets` with query like "Fed rate cut", "Iran", "election"
- `mcp_polymarket_market_summary` — probability and volume for a specific market

### Key Frankfurter FX Queries

- `mcp_frankfurter-f_get_latest_exchange_rates` — live rates for any base currency
- `mcp_frankfurter-f_get_historical_exchange_rates` — trend over date range

### Key World Bank Queries

Use `mcp_world-bank_get_indicator_for_country` with:
- `NY.GDP.MKTP.KD.ZG` — GDP growth rate
- `FP.CPI.TOTL.ZG` — CPI inflation
- `GC.DOD.TOTL.GD.ZS` — government debt as % of GDP

### Prerequisites

```bash
# Docker (for sec-edgar)
docker pull stefanoamorelli/sec-edgar-mcp:latest

# uv (for uvx-based servers)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Node.js v18+ (for coingecko npx server)
node --version
```
