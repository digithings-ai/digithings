# Watchlist & Tracked Assets — ETF Rotation Universe

> Full ETF universe Claude monitors and may recommend for positioning.
> Current positions and weights are tracked in config/portfolio.json.
> Last updated: 2026-04-05

---

## 🇺🇸 US Equities — By Market Cap

| ETF | Description | Category |
|-----|-------------|----------|
| SPY | SPDR S&P 500 ETF | equity_us_large |
| QQQ | Invesco Nasdaq-100 ETF | equity_us_large |
| DIA | SPDR Dow Jones Industrial Average ETF | equity_us_large |
| IWB | iShares Russell 1000 (Broad Large Cap) | equity_us_large |
| VTI | Vanguard Total Stock Market ETF | equity_us_large |
| MDY | SPDR S&P 400 Mid Cap ETF | equity_us_mid |
| IJH | iShares Core S&P Mid-Cap ETF | equity_us_mid |
| IWM | iShares Russell 2000 Small Cap ETF | equity_us_small |
| IJR | iShares Core S&P Small-Cap ETF | equity_us_small |

---

## 🏭 US Equities — By Sector (SPDR Select)

| ETF | Sector | Category |
|-----|--------|----------|
| XLK | Technology | equity_sector |
| XLF | Financials | equity_sector |
| XLE | Energy | equity_sector |
| XLV | Health Care | equity_sector |
| XLI | Industrials | equity_sector |
| XLRE | Real Estate | equity_sector |
| XLU | Utilities | equity_sector |
| XLY | Consumer Discretionary | equity_sector |
| XLP | Consumer Staples | equity_sector |
| XLB | Materials | equity_sector |
| XLC | Communication Services | equity_sector |

---

## 🌐 International — Developed Markets

| ETF | Description | Category |
|-----|-------------|----------|
| EFA | iShares MSCI EAFE (Europe, Australasia, Far East) | equity_intl_developed |
| VEA | Vanguard Developed Markets ex-US | equity_intl_developed |
| VGK | Vanguard FTSE Europe ETF | equity_intl_developed |
| EWJ | iShares MSCI Japan ETF | equity_intl_developed |
| EWG | iShares MSCI Germany ETF | equity_intl_developed |
| EWU | iShares MSCI United Kingdom ETF | equity_intl_developed |
| EWA | iShares MSCI Australia ETF | equity_intl_developed |

---

## 🌏 Emerging Markets

| ETF | Description | Category |
|-----|-------------|----------|
| EEM | iShares MSCI Emerging Markets ETF | equity_em |
| VWO | Vanguard Emerging Markets Stock Index | equity_em |
| FXI | iShares China Large-Cap ETF | equity_em |
| ASHR | Xtrackers Harvest CSI 300 China A-Shares | equity_em |
| EWZ | iShares MSCI Brazil ETF | equity_em |
| EWT | iShares MSCI Taiwan ETF | equity_em |
| EWY | iShares MSCI South Korea ETF | equity_em |
| INDA | iShares MSCI India ETF | equity_em |

---

## 🪙 Crypto

### Index (native yfinance tickers — full price history)

| Ticker | Description | Category |
|--------|-------------|----------|
| BTC-USD | Bitcoin | crypto |
| ETH-USD | Ethereum | crypto |
| SOL-USD | Solana | crypto |
| XRP-USD | XRP (Ripple) | crypto |
| BNB-USD | BNB (Binance Coin) | crypto |

### ETFs (equity-like tickers)

| Ticker | Description | Category |
|--------|-------------|----------|
| BITO | ProShares Bitcoin Strategy ETF (BTC futures) | crypto |
| TRX-USD | TRON | crypto |
| DOGE-USD | Dogecoin | crypto |
| ADA-USD | Cardano | crypto |
| AVAX-USD | Avalanche | crypto |
| LINK-USD | Chainlink | crypto |
| DOT-USD | Polkadot | crypto |
| BCH-USD | Bitcoin Cash | crypto |
| LTC-USD | Litecoin | crypto |
| NEAR-USD | NEAR Protocol | crypto |
| ATOM-USD | Cosmos | crypto |
| XMR-USD | Monero | crypto |
| SUI20947-USD | Sui (yfinance ID: SUI20947-USD) | crypto |

### Spot ETFs (US-listed, preferred for vol/correlation vs equities)

| Ticker | Description | Category |
|--------|-------------|----------|
| IBIT | iShares Bitcoin Trust (BlackRock) | crypto |
| FBTC | Fidelity Wise Origin Bitcoin Fund | crypto |
| ETHA | iShares Ethereum Trust (BlackRock) | crypto |
| FETH | Fidelity Ethereum Fund | crypto |
| GBTC | Grayscale Bitcoin Trust | crypto |

> **Note:** Use index tickers (BTC-USD etc.) for long-run analysis and altcoin coverage.
> Use ETF tickers (IBIT/FBTC/ETHA) when correlating against equities or computing ETF premium/discount.

---

## 🥇 Commodities

| ETF | Description | Category |
|-----|-------------|----------|
| GLD | SPDR Gold Shares | commodity_gold |
| IAU | iShares Gold Trust (lower cost) | commodity_gold |
| SLV | iShares Silver Trust | commodity_silver |
| DBO | Invesco DB Oil Fund (optimized roll) | commodity_oil |
| USO | United States Oil Fund (WTI) | commodity_oil |
| BNO | United States Brent Oil Fund | commodity_oil |
| PDBC | Invesco Optimum Yield Diversified Commodity | commodity_other |
| DJP | iPath Bloomberg Commodity Index Total Return | commodity_other |
| CPER | United States Copper Index Fund | commodity_other |

---

## 🏦 Fixed Income & Cash Equivalents

| ETF | Description | Category |
|-----|-------------|----------|
| BIL | SPDR 1-3 Month T-Bill ETF (cash proxy) | cash |
| SHV | iShares Short Treasury Bond ETF (cash proxy) | cash |
| SHY | iShares 1-3 Year Treasury Bond ETF | fixed_income |
| IEF | iShares 7-10 Year Treasury Bond ETF | fixed_income |
| TLT | iShares 20+ Year Treasury Bond ETF | fixed_income |
| AGG | iShares Core U.S. Aggregate Bond ETF | fixed_income |
| HYG | iShares iBoxx High Yield Corporate Bond | fixed_income |
| LQD | iShares iBoxx Investment Grade Corporate Bond | fixed_income |
| TIP | iShares TIPS Bond ETF (inflation-linked) | fixed_income |
| EMB | iShares JP Morgan USD EM Bond ETF | fixed_income |

---

## ⚖️ Ratio / Spread Trade Pairs

Relative value positions — express a view on one asset outperforming another.

| Long | Short | Thesis Angle |
|------|-------|--------------|
| GLD | SLV | Gold/silver ratio — gold outperforms in risk-off / uncertainty |
| DBO | GLD | Oil over gold — growth/inflation bet, commodity cycle rotation |
| IWM | SPY | Small cap vs. large cap — domestic growth / rate cut bet |
| EEM | SPY | Emerging markets vs. US — USD weakness / reflation trade |
| XLE | XLU | Energy vs. utilities — risk-on within defensives |
| QQQ | IWM | Growth/quality over small cap — flight to large cap tech |
| TLT | HYG | Long Treasury / short HY — flight to quality, risk-off spread |
| EFA | SPY | International developed vs. US — non-USD outperformance |
| IAU | TLT | Gold vs. bonds — real assets over nominal in inflationary regime |

---

## 📊 Macro Indicators to Monitor

| Indicator | Why It Matters |
|-----------|----------------|
| DXY | US Dollar Index — key driver of EM, gold, and commodity direction |
| UUP | USD bull ETF (tradeable DXY proxy) — confirm dollar trend in portfolio terms |
| VIX | Equity volatility — risk-on vs. risk-off regime signal |
| MOVE Index | Bond market volatility — rate uncertainty |
| US 2Y / 10Y / 30Y | Yield levels and curve shape |
| 2s10s spread | Yield curve — recession indicator |
| Gold/Silver ratio | Risk-off (high ratio = gold preferred) vs. risk-on (low = silver) |
| Oil/Gold ratio | Cyclical growth signal |
| HY credit spreads (OAS) | Risk appetite in credit markets |
| CPI / PCE | Inflation — drives rate expectations and real asset positioning |
| NFP / Unemployment | Labor market — Fed reaction function |
| Fed Funds Rate | Rate environment — impacts all asset class positioning |
