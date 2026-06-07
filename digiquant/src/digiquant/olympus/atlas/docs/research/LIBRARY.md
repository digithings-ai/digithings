# Research Library — digiquant-atlas

> Curated summaries of peer-reviewed academic research on portfolio management, factor investing,
> tactical asset allocation, and risk management. This file is the primary reference for the
> Asset Analyst (`skills/asset-analyst/SKILL.md`) and Portfolio Manager (`skills/portfolio-manager/SKILL.md`).
> **Load this file at the start of any portfolio analysis session.**
>
> For detailed per-paper notes, fetch from Supabase: `python3 scripts/fetch_research_library.py --type paper`

---

## Agent Loading Instructions

### Asset Analyst (`skills/asset-analyst/SKILL.md`)
Treat this library as **Input #5** in every analyst session:
1. Load `docs/research/LIBRARY.md` after loading the session segment files and before forming bull/bear arguments
2. Ground each bull and bear argument in at least one paper from this library (cite author + section)
3. Use the **Quick Reference tables** (Section 7) for per-asset decision rules grounded in research
4. For momentum assessment: cite Sections 1–2 (Faber SMA filter, Antonacci dual momentum, TSMOM)
5. For macro regime framing: cite Section 5.4 (Ilmanen 4-quadrant model)
6. For behavioral guardrails: cite Section 6 (Kahneman, Shefrin) to justify anti-anchoring discipline

### Portfolio Manager (`skills/portfolio-manager/SKILL.md`)
Treat this library as **Pre-Flight Input #5**:
1. Load `docs/research/LIBRARY.md` before Phase B (clean-slate construction)
2. Apply the **Black-Litterman conviction-weight mapping** (Section 4.2, Table) for position sizing
3. Run the **Ilmanen 4-quadrant regime check** (Section 5.4, Regime Table) before building the clean-slate portfolio
4. Use the **Kelly criterion** (Section 4.3) as a ceiling check: no position should exceed the conservative Kelly fraction given estimated Sharpe
5. Use the **drawdown budget** principle (Section 5 risk table) to ensure combined energy risk contribution doesn't exceed thesis support

### Orchestrator (`skills/orchestrator/SKILL.md`)
- LIBRARY.md is pre-loaded in Phase 6B (context load) — no additional action needed
- The research library informs regime classification and position sizing across all Phase 7 outputs

---

## How to Use This Library

- **Asset analysts**: Before forming a bull/bear view, check relevant papers under the asset's
  category (e.g., gold → Section 5 "Macro Regime & Safe Havens"; bonds → Section 4 and 5).
- **Portfolio manager**: Before constructing the clean-slate portfolio (Phase B), load Sections
  1, 3, and 4 to ground sizing and diversification decisions. For rebalance discipline, see
  Section 6.
- **Whenever momentum or trend is assessed**: cite the specific lookback period supported by
  Section 2 (12-month time-series momentum, skip last month for cross-sectional).

---

## Section 1 — Tactical Asset Allocation

### 1.1 Faber (2007, rev. 2013) — "A Quantitative Approach to Tactical Asset Allocation"
**Citation**: Mebane T. Faber. *The Journal of Wealth Management*, 2007. SSRN:962461.

**Summary**: Tests a simple 10-month simple moving average (SMA) rule across five asset classes
(US equities, foreign equities, US bonds, REITs, commodities). When an asset's price is above
its 10-month SMA, hold it; when below, move to cash (T-bills). Applied monthly. Over a backtested
period (1900–2012), the TAA rule cut the maximum drawdown from ~50% to under 15% while
preserving nearly all of the long-run return. The TAA portfolio improved the Sharpe ratio from
~0.34 (buy-and-hold) to ~0.77.

**Key Findings**:
- The 10-month SMA is a 200-day moving average equivalent — a widely-watched technical level
- Rule is trend-following in nature: it exits after a downturn has already begun (accepts some whipsaw)
- The improvement in risk-adjusted returns comes primarily from large drawdown reduction, not return enhancement
- Works across all five asset classes tested; robustness holds for 3–12 month lookbacks
- Even a simple equal-weight portfolio with this overlay outperforms most hedge fund indices on a risk-adjusted basis

**System Implications**:
- **IAU/DBO/XLE**: Apply 10-month SMA filter as the first screen. If price < 10M SMA → reduce to 0–5%; do not hold full weight in a confirmed downtrend
- **BIL/SHY allocation**: The "cash" alternative when trend signals are negative. High BIL/SHY allocation (40–47%) in the current portfolio is consistent with Faber: bearish trend signals across several sectors
- **Monthly review discipline**: Faber's rule is applied monthly; avoid intraday or weekly overreaction
- **Drawdown ceiling**: The objective is protecting against the catastrophic −40% to −50% drawdowns that destroy compounding. Research shows the cost is modest (slightly lower bull-market participation)

---

### 1.2 Antonacci (2012, 2016) — "Dual Momentum Investing"
**Citation**: Gary Antonacci. SSRN:2042750. Also: *Dual Momentum Investing* (McGraw-Hill, 2014).

**Summary**: Combines two momentum types: **absolute momentum** (compare each asset to its own
cash return — exit when return is negative) and **relative momentum** (pick the highest-momentum
asset from a universe). Absolute momentum acts as a risk filter: it exits to bonds when the asset's
own trailing return turns negative, thus sidestepping large bear markets. Relative momentum selects
among the *surviving* assets. Dual momentum backtested over 40+ years achieves higher Sharpe
(~0.84) and much lower drawdown than either momentum type alone.

**Key Findings**:
- Absolute momentum is the key driver of drawdown reduction — it exits *before* recoveries rather than *after* peaks
- 12-month lookback is optimal for absolute momentum; same for relative
- Outperforms in crisis periods (2000–2002, 2008): absolute momentum exits equities before the worst declines
- Works for stocks, bonds, currencies, and commodities — documented across asset classes

**System Implications**:
- Use the absolute momentum filter on IAU, XLE, DBO: if 12-month return < T-bill return → shift weight to BIL/SHY
- The current high cash allocation in BIL/SHY is consistent with absolute momentum triggering a risk-off signal on multiple equity assets
- When choosing between two similar assets (e.g., BIL vs SHY), use relative momentum (trailing 3–6 month return) to favor the stronger one
- Dual momentum validates moving from equity risk to duration-free cash (BIL) in bear markets rather than bonds (which have their own bear market risk when rates rise)

---

## Section 2 — Momentum & Trend Following

### 2.1 Jegadeesh & Titman (1993) — "Returns to Buying Winners and Selling Losers"
**Citation**: Narasimhan Jegadeesh and Sheridan Titman. *Journal of Finance*, Vol. 48, No. 1, pp. 65–91.

**Summary**: The original momentum study. Over 1965–1989, portfolios formed by buying stocks with
the highest 3-to-12-month past returns and shorting stocks with the lowest past returns produce
abnormal returns of ~1% per month. The momentum effect persists for 3–12 months and then reverses
over 2–5 years. The 6-month/6-month version is the classic reference. Momentum is distinct from
and not explained by the Fama-French value/size factors.

**Key Findings**:
- 12-month lookback (skip last month) is the standard window for cross-sectional equity momentum
- Momentum premium is ~10–12% annualized on average before costs for a long/short strategy
- Momentum works both within and across industries
- The premium partially reverses over 3–5 years (mean-reversion), implying behavioral rather than purely rational underpinning

**System Implications**:
- For sector ETF rotation (e.g., XLE vs XLV vs XLK), 12-month relative performance is a valid selection signal
- Skip the most recent month when calculating lookback to avoid short-term reversal contamination
- Momentum crashes occur sharply during market reversals (March 2009 type). Be aware: a crowded momentum position can unwind violently when the macro trend reverses

---

### 2.2 Moskowitz, Ooi & Pedersen (2012) — "Time Series Momentum"
**Citation**: Tobias J. Moskowitz, Yao Hua Ooi, and Lasse H. Pedersen. *Journal of Financial Economics*, Vol. 104, pp. 228–250.

**Summary**: Documents "time series momentum" (TSMOM) — a security's own past returns predict
its future returns — across 58 futures and forwards including equity indices, currencies,
commodities, and sovereign bonds over 25 years. The 12-month excess return is a positive
predictor. Effect persists for ~1 year then partially reverses. Works for *every* asset
contract examined. TSMOM explains managed futures fund performance (CTA returns).

**Key Findings**:
- TSMOM is distinct from cross-sectional momentum: it only uses each asset's OWN return history
- Positive autocorrelation is the dominant mechanism: winning assets keep winning, losing assets keep losing — until they don't
- TSMOM profit is highest in crisis periods (hedges equities by going short when negative momentum appears)
- Looking at 12-month lagged returns is the optimal signal horizon; shorter lookbacks add noise

**System Implications**:
- For assessing IAU, XLE, DBO: is the 12-month return positive vs T-bills? If yes, maintain conviction; if no, reduce
- TSMOM provides theoretical grounding for the momentum-based position management already implicit in this system
- The 1-year-then-partial-reversal pattern implies this system should not extend individual position horizons beyond 12–18 months without fresh thesis validation
- In the current geopolitical shock regime (Iran War, WTI $112, Gold ATH): both IAU and XLE show positive TSMOM — validates current overweight

---

### 2.3 Hurst, Ooi & Pedersen (2017) — "A Century of Evidence on Trend-Following Investing"
**Citation**: Brian K. Hurst, Yao Hua Ooi, Lasse H. Pedersen. *Journal of Portfolio Management*, Fall 2017. AQR Working Paper.

**Summary**: Extends the time series momentum backtest to 1880 using historical UK/US equity,
bond, commodity, and currency data. The trend-following strategy (long assets with positive
trailing returns, short those with negative) is consistently profitable across all 110 years of
data through diverse macroeconomic regimes including WWI, WWII, the Great Depression, the 1970s
stagflation, and the 2008 GFC. The strategy performs especially well during equity bear markets.

**Key Findings**:
- Trend following passed through every identified macroeconomic regime with positive average returns
- Best performance in equity bear markets (1930s, 2000–2002, 2008) — acts as an equity crisis hedge
- The strategy underperforms in "whipsaw" environments: rapid regime changes with no sustained trend
- Post-2008 performance was muted due to increased asset correlations (central bank interventions compressing divergences)
- Still works: the data show the 2010s underperformance was a historically unusual but not unprecedented episode

**System Implications**:
- Trend following is a validated, century-long premium — not data-mined over a short backtest window
- The current system's reliance on trend signals (Faber TMMOM + Antonacci dual momentum) has a 140-year track record of generating positive returns
- Low-trend environments (post-QE, 2013–2021) are the risk regime where this system underperforms. Monitor for: persistent low VIX, Fed QE resumption, synchronized asset rallies
- The current geopolitical shock regime (WTI super-spike, Gold ATH) is a prime trend environment — trend signals should be trusted

---

### 2.4 Asness, Frazzini, Israel & Moskowitz (2014) — "Fact, Fiction and Momentum Investing"
**Citation**: Clifford S. Asness, Andrea Frazzini, Ronen Israel, Tobias J. Moskowitz. *Journal of Portfolio Management* (Fall 2014). AQR.

**Summary**: Systematically refutes 10 myths about momentum investing: (1) momentum is too small
to matter; (2) it only works on the short side; (3) it only works in small caps; (4) it doesn't
survive transaction costs; (5) it's "gone" since being published. Uses 212 years of US equity
data plus 40+ international markets. Momentum premium survives trading costs in live implementations,
is present in large-cap stocks, and works for long-only portfolios.

**Key Findings**:
- Momentum premium exists in 212 years of data (1801–2012) including multiple crashes and regime changes
- Works in 40+ countries and >12 asset classes beyond US equities
- Long-only momentum (buying winners, ignoring losers) still improves risk-adjusted returns even without shorting
- Transaction costs matter but do not eliminate the premium for monthly-rebalanced strategies
- Momentum's biggest weakness: sharp crashes during market recoveries after large drawdowns (e.g., March 2009)

**System Implications**:
- Long-only momentum (our system) is theoretically validated: we can rank sectors/ETFs by momentum without needing the short side
- Monthly rebalancing frequency is supportable from a transaction-cost perspective
- The "momentum crash" risk during sharp recoveries is the key tail risk: in a sudden risk-on reversal from geopolitical resolution, momentum strategies can suffer. Have a plan for fast de-risking of momentum positions on ceasefire/resolution news
- Asset-class momentum (rotating among ETFs rather than individual stocks) has even lower turnover and lower crash risk than single-stock momentum

---

### 2.5 Asness, Moskowitz & Pedersen (2013) — "Value and Momentum Everywhere"
**Citation**: Clifford S. Asness, Tobias J. Moskowitz, Lasse H. Pedersen. *Journal of Finance*, Vol. 68, No. 3.

**Summary**: Finds consistent value and momentum premia across 8 diverse markets and asset classes
(US equities, UK equities, Europe equities, Japan equities, bonds, currencies, equity index futures,
commodity futures). Value and momentum are negatively correlated with each other, meaning they
provide natural diversification when combined. A diversified portfolio of value+momentum strategies
across all asset classes achieves a Sharpe ratio not attainable from either alone.

**Key Findings**:
- Value and momentum work everywhere — not a U.S. equity data-mining artifact
- The negative correlation between value and momentum (r ≈ −0.5) implies combining them dramatically reduces volatility
- Common global risk factors (funding liquidity, sentiment) drive both premia
- Existing behavioral theories fail to explain the *cross-asset* correlation structure

**System Implications**:
- This system is primarily momentum-driven. Adding a value screen (e.g., is the sector cheap on forward P/E vs history?) would reduce momentum crash risk through natural hedging
- When momentum signal and valuation signal align (momentum positive AND sector is cheap): highest-conviction long
- When momentum and value conflict: reduce position size or hold at benchmark weight
- For IAU: gold is a store-of-value/inflation-hedge — not a traditional value asset — but its "value" can be assessed via real yield (negative real yields → gold is cheap)

---

## Section 3 — Factor Investing

### 3.1 Fama & French (1993) — "Common Risk Factors in the Returns on Stocks and Bonds"
**Citation**: Eugene F. Fama and Kenneth R. French. *Journal of Financial Economics*, Vol. 33, pp. 3–56.

**Summary**: Establishes the three-factor model: market risk (Mkt-RF), size premium (SMB: small minus
big), and value premium (HML: high minus low B/M ratio). Together, these three factors explain most
of the cross-sectional variation in average stock returns. The size and value premiums represent
compensation for risk that CAPM misses.

**Key Findings**:
- Value stocks (high book-to-market) earn a persistent premium (~4-5% annualized) over growth stocks
- Small-cap stocks earn a persistent premium (~3% annualized) over large-cap stocks
- The model does NOT explain the momentum premium (Fama-French acknowledge this)
- Sector ETFs have varying exposures to HML: Energy/Financials are value-tilted; Technology/Healthcare are growth-tilted

**System Implications**:
- XLE (energy) and XLP (staples) have high value factor loadings — historically resilient during value cycles
- XLV and XLE as long-term holds have academic support: both sectors have historically traded at value premiums vs growth sectors
- The Fama-French framework implies that a concentrated position in high-HML sectors (XLE) should outperform over a full cycle, but may lag during growth-dominated bull markets

---

### 3.2 Carhart (1997) — "On Persistence in Mutual Fund Performance"
**Citation**: Mark M. Carhart. *Journal of Finance*, Vol. 52, No. 1, pp. 57–82.

**Summary**: Extended the Fama-French model by adding a 4th factor — momentum (WML: winners minus
losers, defined as 12-1 month return). The 4-factor model (Mkt, SMB, HML, WML) became the industry
standard for evaluating active manager performance. Most mutual fund persistence disappeared once
controlling for the momentum factor. This confirmed momentum as a distinct, systematic premium.

**Key Findings**:
- Momentum (WML) factor has historically earned ~4-8% annualized premium in equities
- After controlling for momentum, very few active managers generate significant alpha
- The 11-month lookback (12 months minus last month) is the canonical cross-sectional momentum definition
- WML is the most powerful predictor of next-month returns among the four factors

**System Implications**:
- ETF selection based on sector momentum is consistent with academic factor investing — not speculation
- When evaluating whether to hold or exit a sector ETF, check whether the sector has positive WML momentum vs its Fama-French peer group
- The 12-1 month momentum window: use the last 12 months of returns, excluding the most recent month, as the ranking signal

---

### 3.3 Harvey, Liu & Zhu (2016) — "…and the Cross-Section of Expected Returns"
**Citation**: Campbell R. Harvey, Yan Liu, Heqing Zhu. *Review of Financial Studies*, Vol. 29, No. 1, pp. 5–68.

**Summary**: Surveyed 316 published factors claiming to predict cross-sectional stock returns. With
proper multiple-testing correction (Bonferroni, FDR), most factors fail to meet adjusted significance
thresholds. The study raises the t-statistic hurdle for a credible factor from 2.0 to 3.0+. Argues
that many published factors are noise or data-mined artifacts.

**Key Findings**:
- Of 316 factors, only ~60–70 survive multiple-testing correction
- The "factor zoo" problem: too many factors discovered, most won't survive out-of-sample
- Momentum, value, carry, and low volatility are among the most robust surviving factors
- Single-country, short-sample, or highly parameterized models should be treated with deep skepticism

**System Implications**:
- Only rely on factors with >30 years of out-of-sample evidence and multi-country replication: momentum (✓), value (✓), carry (✓), trend-following (✓)
- Distrust any factor or signal discovered in the last 5 years with <10 years of evidence
- For sector ETF anomalies or calendar effects: treat with deep skepticism; do not trade them without fundamental backing
- This validates the system's preference for well-established macro + momentum signals over novel quantitative signals

---

## Section 4 — Portfolio Construction

### 4.1 Markowitz (1952) — "Portfolio Selection"
**Citation**: Harry Markowitz. *Journal of Finance*, Vol. 7, No. 1, pp. 77–91.

**Summary**: The founding paper of Modern Portfolio Theory (MPT). Demonstrates mathematically that
for a given level of expected return, there exists a minimum-variance portfolio, and that combining
assets with low correlations reduces portfolio variance ("free lunch of diversification"). Investors
should select portfolios on the efficient frontier — the set of portfolios maximizing return per
unit of risk.

**Key Findings**:
- Diversification is mathematically provable: combining imperfectly correlated assets reduces portfolio variance below the weighted average of individual variances
- The efficient frontier is the set of Pareto-optimal portfolios: no higher return is achievable without more risk
- Mean-variance optimization requires estimates of means, variances, and correlations — all of which are highly uncertain
- Error maximization problem: small estimation errors in expected returns produce drastically different optimal portfolios (known as Markowitz's "error maximizer" critique)

**System Implications**:
- The system's diversification across gold (IAU), energy equity (XLE), oil (DBO), healthcare (XLV), staples (XLP), and cash (BIL/SHY) is Markowitz-consistent: these assets have historically low pairwise correlations
- Gold and energy equities have near-zero or negative correlation with bonds → current allocation provides genuine diversification
- Avoid using raw mean-variance optimization without constraints: the output is highly sensitive to return estimates. The current quantized-weight system (0-5-10-15-20%) implicitly guards against this
- The efficient frontier shifts with the macro regime: in risk-off regimes, the optimal portfolio moves to lower-volatility assets (cash, gold, short-duration bonds), which is what Faber TAA and dual momentum accomplish

---

### 4.2 Black & Litterman (1992) — "Global Portfolio Optimization"
**Citation**: Fischer Black and Robert Litterman. *Financial Analysts Journal*, Vol. 48, No. 5, pp. 28–43. Goldman Sachs, 1992.

**Summary**: Addresses the input sensitivity problem of Markowitz optimization by starting from
CAPM equilibrium expected returns (which imply the market-cap-weighted portfolio is optimal) and
combining with the investor's own "views" using Bayesian updating. The resulting portfolio blends
the market-cap equilibrium with investor conviction — the more confident the investor's view, the
more the portfolio deviates from equilibrium.

**Key Findings**:
- CAPM equilibrium returns serve as a "neutral prior" — what you would hold if you had no views
- Bayesian update: strong conviction → large deviation from equilibrium; weak conviction → stay near market weights
- Solves the "corner solution" problem of Markowitz (pure optimization produces all-or-nothing portfolios)
- Portfolio tilts should be proportional to conviction strength, not just expected return magnitude

**System Implications**:
- The quantized weight system (0-5-10-15-20%) implicitly implements a Black-Litterman-style conviction scale
- 0% weight = no view, exit; 5% = weak conviction; 10% = moderate; 15% = strong; 20% = maximum conviction
- When an analyst produces a "Hold" with neutral sentiment, the appropriate weight is near benchmark (market weight) — consistent with BL equilibrium
- High conviction (e.g., IAU during confirmed gold safe-haven regime) → 15-20%; Low conviction → do not exceed 5%

---

### 4.3 Thorp (2006) / Kelly (1956) — Kelly Criterion and Position Sizing
**Citation**: John L. Kelly Jr. *Bell System Technical Journal*, 1956. Edward O. Thorp popularized in *The Mathematics of Gambling* (1984) and hedge fund applications.

**Summary**: The Kelly Criterion determines the optimal bet size (as a fraction of capital) to
maximize the long-run growth rate of a portfolio. For a bet with probability p of winning and
odds b, the Kelly fraction is f* = (bp - q) / b, where q = 1 - p. Half-Kelly (f = 0.5 × f*)
is the practical recommendation for most investors because it halves the volatility of wealth
relative to full Kelly while sacrificing only ~13% of the growth rate.

**Key Findings**:
- Kelly maximizes the expected logarithm of wealth (log-optimal growth)
- Full Kelly is extremely volatile — large drawdowns are common even with a persistent edge
- Half-Kelly is the dominant practical recommendation: lower drawdown, still captures most of the growth advantage
- Kelly fraction falls to zero when edge (expected return) is zero or negative
- Kelly provides a hard ceiling on position size: exceeding it reduces long-run growth (overbetting)

**System Implications**:
- In the context of this ETF rotation system, Kelly translates to: a 20% maximum single position cap is consistent with a high-conviction (p~0.6–0.65) thesis
- When analyst conviction is 55% (slightly favorable), Kelly implies a much smaller position (5-10%)
- Never exceed 20% in a single ETF (consistent with the `max_single_etf_pct: 20` constraint in config/portfolio.json)
- The current high cash allocation (BIL+SHY = 47%) is rational under Kelly when few assets have a clear edge: cash (Kelly fraction for a ~0% edge bet is zero)

---

## Section 5 — Macro Regime & Safe Havens

### 5.1 Baur & Lucey (2010) — "Is Gold a Hedge or a Safe Haven?"
**Citation**: Dirk G. Baur and Brian M. Lucey. *Financial Review*, Vol. 45, No. 2, pp. 217–229.

**Summary**: Distinguishes between "hedge" (asset uncorrelated with stocks on average) and "safe haven"
(asset negatively correlated with stocks in the worst market conditions). Empirically, gold is both:
it is a hedge on average (low or zero correlation with equities) and a safe haven in extreme equity
market downturns (negative correlation during the worst 5% of equity days). Gold's safe-haven
property holds for the US, UK, and Germany but is temporary — it does not persist beyond 15 trading days.

**Key Findings**:
- Gold is a hedge: average correlation with US equities is ~0 to −0.05
- Gold is a safe haven: in extreme downturns (bottom 5% of equity returns), gold-equity correlation turns significantly negative
- The safe-haven property is time-limited: it typically lasts 10–15 trading days after a shock
- Gold does NOT provide sustained equity protection in prolonged bear markets — only in sudden crises
- Bonds (US Treasuries) are also a safe haven but primarily for medium-term rate-driven equity declines

**System Implications**:
- IAU position in the current regime (geopolitical shock, Iran War) is well-supported: gold's safe-haven property is most reliable during sudden crisis/shock events
- Monitor: if the crisis transitions from acute shock to prolonged recession, gold's safe-haven premium fades and a real-yield-based thesis becomes more important
- During a ceasefire or shock resolution, the safe-haven bid unwinds — IAU may decline 5-10% suddenly. Watch for position-sizing adjustment
- The current portfolio's ~20% IAU allocation is at the Kelly ceiling for a high-conviction safe-haven thesis

---

### 5.2 Gorton & Rouwenhorst (2006) — "Facts and Fantasies About Commodity Futures"
**Citation**: Gary B. Gorton and K. Geert Rouwenhorst. *Financial Analysts Journal*, Vol. 62, No. 2, pp. 47–68.

**Summary**: Conducted the first systematic analysis of commodity futures returns (1959–2004).
Five key findings: (1) commodities provide equity-like average returns; (2) commodity futures
are negatively correlated with equities and bonds over most horizons; (3) commodity futures provide
inflation protection (positive correlation with CPI); (4) commodities perform well late in the
business cycle; (5) commodity roll yield matters — backwardated markets outperform contangoed markets.

**Key Findings**:
- Average annualized commodity futures return: ~5% real, roughly equal to equity real returns
- Negative correlation with equities (r ≈ −0.15) and bonds (r ≈ −0.21): genuine diversification benefit
- Inflation protection: commodity futures correlate positively with unexpected inflation
- Business cycle timing: commodities tend to be early/mid-cycle laggards and late-cycle outperformers
- Backwardation vs contango: buying futures in backwardated markets earns a positive roll yield; contangoed markets destroy value over time

**System Implications**:
- DBO (DB Oil Optimum Yield fund) uses an optimized roll strategy to minimize contango drag — academically justified approach
- The late-cycle property of commodities supports current positioning: we are in a late-cycle/stagflation-adjacent regime (WTI $112, geopolitical disruption → supply shock)
- Negative stock-commodity correlation validates holding both XLE and BIL simultaneously
- Monitor roll yield: if WTI futures shift to steep contango (demand destruction), DBO's total return will lag spot oil price significantly

---

### 5.3 Erb & Harvey (2006) — "The Strategic and Tactical Value of Commodity Futures"
**Citation**: Claude B. Erb and Campbell R. Harvey. *Financial Analysts Journal*, Vol. 62, No. 2, pp. 69–97.

**Summary**: Companion paper to Gorton & Rouwenhorst. Focuses on the sources of expected commodity
return: spot return, roll yield (backwardation/contango), and collateral yield. Finds that the
expected return of a diversified commodity portfolio is close to cash unless the individual
commodity is in backwardation. Also examines inflation hedging: commodities are better hedges
against unexpected inflation than against expected inflation.

**Key Findings**:
- Spot commodity price appreciation alone (without roll): roughly 0% real over long horizons
- Roll yield is the primary driver of total return for commodity funds
- Diversified commodity baskets underperform individual commodity selection
- Commodities are a better hedge for unexpected inflation (supply shocks) than expected inflation
- High commodity prices at purchase imply lower future returns (mean-reversion in commodity prices over 3-5 years)

**System Implications**:
- A supply-shock driven commodity spike (like current WTI from Iran War) is precisely the unexpected-inflation scenario where DBO/XLE earnings protection is strongest
- High entry price for oil exposure (WTI $112) means the future return potential is lower — not a long-term structural hold at these levels
- Exit discipline: plan for when WTI returns to $80-90 (Erb & Harvey mean-reversion window ≈ 2-3 years post-spike)
- Current thesis invalidation triggers ($80 WTI) are consistent with the mean-reversion evidence

---

### 5.4 Ilmanen (2011) — "Expected Returns" (Macro Regime Framework)
**Citation**: Antti Ilmanen. *Expected Returns: An Investor's Guide to Harvesting Market Rewards*. John Wiley & Sons, 2011.

**Summary**: Comprehensive framework for expected returns across all asset classes. Organizes
return premia into four categories: (1) carry, (2) value, (3) momentum, (4) volatility selling.
Macro framework: assets can be classified as "good inflation hedges" (commodities, TIPS, gold)
vs "good deflation/growth hedges" (Treasuries, quality bonds). Growth vs inflation creates a 2×2
regime matrix with optimal assets in each quadrant.

**Four Macro Regimes (Ilmanen)**:

| Regime | Growth | Inflation | Outperforming Assets |
|--------|--------|-----------|----------------------|
| Goldilocks | Rising | Low | Equities, Credit, Real Estate |
| Stagflation | Falling | Rising | Commodities, Gold, TIPs, short T-bills |
| Deflation | Falling | Falling | Long Treasuries, quality bonds |
| Reflation | Rising | Rising | Equities, Commodities, EM |

**Current Regime Assessment**: Geopolitical shock → supply-driven inflation spike + slowing growth = **Stagflation** quadrant → validates IAU, XLE, DBO, XLV (defensive), BIL (short T-bills).

**System Implications**:
- The system's current positioning (IAU 20%, XLE 12%, DBO 5%, XLV 8%, XLP 8%, BIL/SHY 47%) maps directly to the Stagflation + Deflation-adjacent regime in Ilmanen's framework
- As the regime transitions, different assets outperform. Monitor the 4 quadrant signals weekly in the macro digest
- Regime transitions are the highest-conviction rebalance moments: moving from Stagflation to Deflation → exit commodities, add long bonds
- XLV (healthcare) and XLP (staples) are Stagflation-resilient sectors: sticky revenues, pricing power, low rate sensitivity

---

## Section 6 — Behavioral Finance & Investment Discipline

### 6.1 Tversky & Kahneman (1974) — "Judgment under Uncertainty: Heuristics and Biases"
**Citation**: Amos Tversky and Daniel Kahneman. *Science*, Vol. 185, No. 4157, pp. 1124–1131.

**Summary**: Identifies three major heuristics that lead to systematic cognitive biases in judgment:
(1) **Representativeness** — judging likelihood by resemblance rather than base rates; (2)
**Availability** — judging likelihood by ease of recall; (3) **Anchoring** — estimates are biased
toward an initial value. In investment contexts, anchoring to recent prices, past purchase prices,
or target prices creates systematic errors.

**Key Findings**:
- Anchoring is extremely robust: even irrelevant initial values bias subsequent estimates
- Adjustment from an anchor is typically insufficient — people do not move far enough from the starting point
- Representativeness causes investors to extrapolate recent trends as if they represent the underlying distribution
- Availability bias causes overweighting of dramatic, memorable events (crashes, spikes)

**System Implications**:
- The anti-anchoring architecture (Phase A/B blinded to existing weights) directly implements the fix for anchoring bias
- Never start a position review with the question "should I keep what I own?" — start with "what should I own?" (achieved by Phase A/B blindness protocol)
- Availability bias risk: the Iran War narrative feels vivid and recent → may cause overweighting of geopolitical-risk assets. Ask: what does the 12-month momentum model say independent of the news narrative?
- Representativeness: current WTI $112 may feel permanent because the trend is strong; recall Erb & Harvey mean-reversion evidence from Section 5.3

---

### 6.2 Kahneman & Tversky (1979) — "Prospect Theory: An Analysis of Decision Under Risk"
**Citation**: Daniel Kahneman and Amos Tversky. *Econometrica*, Vol. 47, No. 2, pp. 263–291.

**Summary**: Replaces expected utility theory with Prospect Theory. Key features: (1) gains and
losses are evaluated relative to a reference point (current portfolio value); (2) **loss aversion**:
losses are weighted ~2× more than equivalent gains; (3) **diminishing sensitivity**: marginal
impact of gains/losses decreases with magnitude; (4) **probability weighting**: people overweight
small probabilities and underweight large ones.

**Key Findings**:
- Loss aversion coefficient λ ≈ 2.25: a $1 loss feels as bad as a $2.25 gain feels good
- Reference-point anchoring: evaluating performance relative to purchase price (not opportunity cost) leads to suboptimal hold/sell decisions
- Prospect theory predicts the disposition effect (Section 6.3) and overtrading
- Loss aversion causes excessive risk aversion after losses — investors hold too much cash after drawdowns

**System Implications**:
- The 5% rebalance threshold (≥5% weight difference triggers action) is intended to overcome loss aversion — force periodic review that ignores emotional attachment to unrealized losses
- After a drawdown in any position, prospect theory predicts a tendency to hold (waiting to "get back to even"). The thesis-based exit criteria (WTI <$80 → exit DBO/XLE regardless of entry price) overcomes this
- High BIL/SHY allocation post-drawdown is a loss-aversion artifact as much as a rational signal. Use Faber TAA and momentum models to objectively re-evaluate entry rather than relying on gut
- When a position has large unrealized gains (IAU at ATH), prospect theory predicts premature exit. Use the systematic 10M SMA and thesis validity check instead of "locking in profits" instinct

---

### 6.3 Shefrin & Statman (1985) — "The Disposition to Sell Winners Too Early and Ride Losers Too Long"
**Citation**: Hersh Shefrin and Meir Statman. *Journal of Finance*, Vol. 40, No. 3, pp. 777–790.

**Summary**: Documents the "disposition effect": investors systematically realize gains too quickly
(sell winners) and hold losses too long (ride losers). Provides behavioral explanation based on
Prospect Theory + regret aversion + mental accounting. Tax-loss harvesting aside, the disposition
effect is irrational: it ignores expected future returns completely.

**Key Findings**:
- Disposition effect is robust across retail and institutional investors, multiple markets, and time periods
- The tendency to ride losers is the more costly error: losing positions have negative future momentum
- Winning stocks that are sold tend to continue outperforming; losing stocks held tend to continue underperforming
- Mental accounting (keeping each position in a separate mental "account") drives the behavior

**System Implications**:
- The thesis-based exit discipline (define exit criteria BEFORE entering a position) is the behavioral finance approved method for beating the disposition effect
- For each position in the portfolio, there should always be a written answer to: "what would make me sell this?" If the answer is not written, the disposition effect is in control
- Current long-term losers (e.g., any sector with sustained 12M negative momentum) should be exited according to the dual-momentum rule — do not hold "waiting for a bounce"
- Current long-term winners (IAU at ATH) should not be trimmed based on "it's had a great run" — hold until the 10M SMA signals or the thesis invalidates

---

## Quick Reference: Decision Rules by Asset Type

### Gold (IAU)
| Condition | Action | Paper Reference |
|-----------|--------|-----------------|
| Price > 10M SMA AND real yields negative | Hold/Add to 20% | Faber 1.1, Baur & Lucey 5.1 |
| Price < 10M SMA | Reduce to 5% or exit | Faber 1.1 |
| 12M return positive vs T-bills | Maintain conviction | Antonacci 1.2, TSMOM 2.2 |
| Ceasefire/shock resolution | Monitor safe-haven unwind — plan trim | Baur & Lucey 5.1 |

### Energy (XLE, DBO)
| Condition | Action | Paper Reference |
|-----------|--------|-----------------|
| WTI in backwardation AND >$90 | Hold DBO; oil premium valid | Gorton & Rouwenhorst 5.2 |
| WTI <$80 (invalidation) | Exit both XLE and DBO | Faber 1.1, system thesis |
| WTI futures in steep contango | Reduce DBO (roll drag) | Erb & Harvey 5.3 |
| 12M energy sector momentum positive | Hold/Add XLE | TSMOM 2.2, Carhart 3.2 |

### Cash (BIL, SHY)
| Condition | Action | Paper Reference |
|-----------|--------|-----------------|
| Multiple momentum signals negative | Maintain high cash | Antonacci dual momentum 1.2 |
| Clear bull-trend resumes (price > 10M SMA across sectors) | Redeploy cash to trending sectors | Faber 1.1 |
| BIL yield > SHY yield AND SHY momentum negative | Favor BIL | Relative momentum (1.2) |

### Healthcare/Staples (XLV, XLP)
| Condition | Action | Paper Reference |
|-----------|--------|-----------------|
| Stagflation regime confirmed | Hold/Add (defensive sector) | Ilmanen 5.4 |
| Goldilocks regime (low inflation, rising growth) | Reduce — cyclicals outperform | Ilmanen 5.4 |
| Sector 12M momentum positive | Hold regardless of regime | Carhart 3.2 |

---

## Further Reading

Full paper notes are in Supabase (`research/papers/*`). Fetch any paper during a session:

```bash
python3 scripts/fetch_research_library.py --type paper          # list all 7 papers
python3 scripts/fetch_research_library.py --key research/papers/macro-regime
python3 scripts/fetch_research_library.py --key research/papers/momentum-trend
python3 scripts/fetch_research_library.py --key research/papers/portfolio-construction
python3 scripts/fetch_research_library.py --key research/papers/risk-management
python3 scripts/fetch_research_library.py --key research/papers/factor-investing
python3 scripts/fetch_research_library.py --key research/papers/tactical-asset-allocation
python3 scripts/fetch_research_library.py --key research/papers/behavioral-finance
```

Papers available: `macro-regime` · `momentum-trend` · `portfolio-construction` · `risk-management` · `factor-investing` · `tactical-asset-allocation` · `behavioral-finance`

---

*Library version: 1.1 | Updated: 2026-04-14 | Full papers migrated to Supabase (`research/papers/*`)*
*Papers are cited by author/year. Verify against published versions for quantitative thresholds.*
