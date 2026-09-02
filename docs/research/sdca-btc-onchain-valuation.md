# SDCA BTC on-chain valuation catalog

Research note (not production code). Date: 2026-08-30.

This note ranks the **canonical Bitcoin cycle-valuation indicators**
practitioners actually use for cheap/rich timing (not day-trade trivia),
maps the top cluster onto **one free catalog**, and recommends a small
non-collinear subset for [#1086](https://github.com/digithings-ai/digithings/issues/1086).
It does **not** implement ingest, scrape Look Into Bitcoin / CheckOnChain /
Woobull, edit `cursor/sdca-two-stage-fit-af6c` or composite-weights, or
touch live-trading.

Parallel work: `docs/research/sdca-indicator-pool.md` (branch
`cursor/sdca-indicator-pool-af6c`) already inventoried the *candidate* pool
and deferred on-chain. This note **extends** that source hunt with a
fuller Bitview / Bitcoin Research Kit (BRK) catalog probe. It does not
contradict the Coin Metrics community, BGeometrics, or NUPL identity
findings from that note.

Related issues: [#1086](https://github.com/digithings-ai/digithings/issues/1086)
(on-chain WP), [#3167](https://github.com/digithings-ai/digithings/issues/3167)
(SDCA epic).

---

## Normalized intent

### Goal

Name the valuation / cycle-timing cluster, pick a **single ingest source**
that can supply it without a paid Glassnode key, and freeze a 3–5 metric
v1 subset that is not three copies of realized cap.

### Requirements

1. Rank by how often the metric is treated as **cycle valuation / timing**,
   not “on-chain trivia” (HODL-wave colour bands, address cohorts, fee
   share, inscriptions).
2. For the top ~8–12: what it measures, typical cheap/rich read,
   collinearity, data needed (UTXO realized cap vs price-only).
3. Honest single-source hunt: prefer 1 self-hostable catalog; if that
   catalog has gaps, name the smallest extra (community API, not scrape).
4. Recommend the **one source to ingest first** for #1086.

### Out of scope

Production scraper, scheduled ingest, `RiskModel` code, live-trading,
`--push-supabase`, two-stage-fit / composite-weights branches.

### Ranking method (not a bibliometric)

Rank is a **practitioner consensus**, 2025–2026, from the public dashboards
and metric guides that cycle analysts actually keep open:

- Look Into Bitcoin’s featured on-chain list (Philip Swift) —
  [charts/on-chain-charts](https://www.lookintobitcoin.com/charts/on-chain-charts/)
- Glassnode metric guides + “On-chain Originals” toolkit —
  [metric-guides](https://docs.glassnode.com/further-information/metric-guides),
  [studio originals](https://studio.glassnode.com/charts/btc-onchain-originals?a=BTC)
- CheckOnChain dashboard families (Checkmate) —
  [charts.checkonchain.com](https://charts.checkonchain.com/)
- 2025–2026 commentary that the **amplitude** of these oscillators damped
  under ETF / treasury buyers even when the **clock** (days since
  halving) still marked the cycle
  ([HTX on the 2025 top](https://www.htx.com/news/the-bitcoin-4-year-cycle-has-never-disappeared-it-just-chang-J5c99l0v/);
  [Nonce Media on 2026 signal decay](https://www.noncemedia.com/bitcoin-exchange-reserves-historic-low-rally-signal-broken-2026/))

S2F, Rainbow, Mayer, daily RSI, Fear & Greed, exchange-reserve “supply
shock,” and Hyperdash perp positioning are **not** in this ranking:
wrong thesis, invalidated, price-duplicate of the SDCA power-law rails,
or the wrong horizon. In-repo Hyperdash remains an Atlas overlay
([`hyperdash.py`](../../digiquant/src/digiquant/data/onchain/hyperdash.py));
it is not an MVRV/SOPR history.

---

## Ranked cluster (valuation / cycle timing)

| Rank | Indicator | Why it is “canonical” | Typical cheap / rich read | Collinear with | Data needed |
|---|---|---|---|---|---|
| 1 | **MVRV** (market / realized cap) | Origin of on-chain valuation. Murad Mahmudov & David Puell, Oct 2018, on Nic Carter / Antoine Le Calvez realized cap ([Glassnode MVRV](https://docs.glassnode.com/further-information/metric-guides/mvrv/mvrv-ratio); [Ledger School lineage](https://situationroom.space/ledger-school/realized-price-mvrv)). LookIntoBitcoin, CheckOnChain, Glassnode, and every composite “barometer” lead with it. | **Cheap:** MVRV ≲ 1 (spot below aggregate cost basis). **Rich:** historically ~3.5–3.7 at cycle tops; later cycles print lower peaks — treat 3.7 as an artefact, not a trigger. | **NUPL** is a monotone transform (`NUPL = 1 − 1/MVRV`). Realized price is the denominator. Percent-supply-in-profit is the same UTXO P/L idea. | **UTXO realized cap** + spot. Not price-only. |
| 2 | **MVRV-Z** | The chart people actually screenshot. Awe & Wonder, Oct 2018: `(market − realized) / expanding σ(market)` ([Glassnode MVRV-Z](https://docs.glassnode.com/further-information/metric-guides/mvrv/mvrv-z-score.md); [LookIntoBitcoin](https://www.lookintobitcoin.com/charts/mvrv-zscore/)). | **Cheap:** z in the historical green band (prior bottoms). **Rich:** z in the red band (prior tops). Absolute z has **compressed** each cycle (see 2025–2026 note). | Same series as MVRV. **Do not** vote MVRV and MVRV-Z together. Compute our own causal z from MVRV. | Same as MVRV. No extra vendor “Z” product required. |
| 3 | **NUPL** | Glassnode / LookIntoBitcoin sentiment stages (Tuur Demeester, Tamás Blummer, Michiel Lescrauwaet 2019; RSK write-up). `(market − realized) / market` ([Glassnode NUPL](https://docs.glassnode.com/further-information/metric-guides/unrealized-profit-loss/nupl-net-unrealized-profit-loss.md)). | **Cheap:** NUPL < 0 (capitulation). **Rich:** historically > ~0.75 (euphoria). 2025 top reportedly never cleared 0.75 ([HTX](https://www.htx.com/news/the-bitcoin-4-year-cycle-has-never-disappeared-it-just-chang-J5c99l0v/)). | **Do not dual-count with MVRV.** Identity holds on Bitview live: `mvrv=1.481577` → `1−1/MVRV=0.32504` vs `nupl=0.325044` (2026-08-30). | Same UTXO realized cap as MVRV. |
| 4 | **Realized price** (realized cap / supply) | Coin Metrics, Dec 2018, first “cost basis” pricing model. Glassnode On-chain Originals lead with it. LookIntoBitcoin + CheckOnChain keep it as the fair-value line. | Spot **below** realized price = network at a loss (historically late-bear). Spot far above = rich. Use as a **level**, not a second oscillator. | Denominator of MVRV. Voting realized price *and* MVRV is one idea twice. | UTXO creation prices. |
| 5 | **SOPR / aSOPR** | Flow, not stock. Renato Shirakashi SOPR; Rafael Schultze-Kraft **aSOPR** drops UTXOs < 1 hour ([Glassnode aSOPR](https://docs.glassnode.com/further-information/metric-guides/sopr/asopr-adjusted-sopr.md)). LookIntoBitcoin added SOPR; CheckOnChain Profit/Loss family is built on it. | Oscillates around **1**. **Cheap / capitulation:** sustained < 1 (coins spent at a loss). **Reset:** aSOPR reclaiming 1 from below. **Rich:** elevated > 1 with LTH spending. Daily SOPR is noisier than aSOPR. | Related to MVRV **at extremes** (everyone is in profit so spent coins are too) but it is a **flow** of realized P/L, not a stock of unrealized P/L. Worth a second vote. | Spent-output creation vs spend value (UTXO). aSOPR needs the <1h filter. |
| 6 | **Puell Multiple** | David Puell, Mar 2019. The miner-income oscillator every dashboard still ships ([Glassnode Puell](https://docs.glassnode.com/further-information/metric-guides/coin-issuance/puell-multiple.md); CheckOnChain Mining). | **Cheap:** < 0.5 historically marked miner-stress bottoms. **Rich:** > 4 historically marked tops (early cycles 6–10). Halvings **step-change** the multiple down 50%. 2025–2026: spent a long time < 0.5 without a classic floor ([Nonce](https://www.noncemedia.com/bitcoin-exchange-reserves-historic-low-rally-signal-broken-2026/)). | **Between halvings**, subsidy is nearly constant, so subsidy-only Puell ≈ `price / 365d MA(price)` — cousin of Mayer / SMA distance, **not** of MVRV. True miner-revenue Puell adds **fees**. | Daily miner USD (issuance × spot; fees optional) + 365d MA. Not UTXO realized cap. |
| 7 | **RHODL ratio** | Philip Swift / LookIntoBitcoin: realized-cap of ~1-week coins / realized-cap of 1–2y coins, often × market age ([LookIntoBitcoin RHODL](https://www.lookintobitcoin.com/charts/rhodl-ratio/); CheckOnChain). Praised as a top-caller that skipped the false Apr-2013 MVRV spike. | **Cheap:** young realized-value subdued vs the 1–2y cohort (green band). **Rich:** speculative young value dominates (red band). Bands are chart-calibrated, not a single number. | Same **realized-cap idea** as MVRV, but an **age-structure ratio**, not a monotone of aggregate MVRV. Can disagree mid-cycle. Do not also vote LTH/STH MVRV as a third realized-cap split. | UTXO age bands × creation price. |
| 8 | **Reserve Risk** | Hans Hauge construction; LookIntoBitcoin + CheckOnChain + Glassnode CDD family. `spot / HODL Bank`, where HODL Bank accumulates the opportunity cost of not spending old coins ([LookIntoBitcoin Reserve Risk](https://www.lookintobitcoin.com/charts/reserve-risk/); [Glassnode](https://docs.glassnode.com/further-information/metric-guides/coin-days-destroyed/reserve-risk.md)). | **Cheap:** green band — high holder conviction vs low price (historically outsized forward returns). **Rich:** red band — price high vs conviction. 2025 bull reportedly never left accumulation colours ([HTX](https://www.htx.com/news/the-bitcoin-4-year-cycle-has-never-disappeared-it-just-chang-J5c99l0v/)). | Sibling of RHODL / liveliness / CDD (all “are old coins moving?”). Pick **one** of {RHODL, Reserve Risk} for v1. | Spot + cumulative CDD / HODL Bank (UTXO lifespan). |
| 9 | **Pi Cycle Top** | Philip Swift. `111d SMA / (2 × 350d SMA)`; cross at 1 historically marked blow-off tops. Famous, **price-only**. LookIntoBitcoin + CheckOnChain “Magic Lines.” | **Rich / top:** ratio → 1 (111d crosses 2×350d). Not a bottom indicator. **Failed to fire** at the 2025 top in several recaps ([HTX](https://www.htx.com/news/the-bitcoin-4-year-cycle-has-never-disappeared-it-just-chang-J5c99l0v/); [Spark comparison](https://www.spark.money/tools/bitcoin-market-cycle-indicator-comparison)). | **Collinear with SDCA power-law rails and Mayer / 200w.** Do not add as an on-chain vote. Compute from Coinbase close if ever wanted as a *technical* extra. | Price only. |
| 10 | **CVDD** | Willy Woo, Apr 2019. Cumulative value-days-destroyed scaled into a **price** that has hugged bear floors. Glassnode Originals + LookIntoBitcoin. | A **floor model**, not an oscillator. Spot tagging CVDD ≈ late-bear. Not a top signal (Top Cap / Delta Top are the complementary Woo ceilings). | Built from CDD × price; related to Transfer Price / Balanced Price (Puell). Distinct from MVRV stock. | Cumulative CDD × price + Woo’s calibration constant. |
| 11 | **Thermocap / thermocap multiple** | Woo / Originals: cumulative USD value of **issuance** (subsidy at each block’s spot), vs market cap. “Monetary premium over thermocap” on CheckOnChain. | Multiple **high** = market rich vs historical miner-issuance cost. Used more as a slow valuation multiple than a timing oscillator. | Related to Puell (both miner USD) but **cumulative stock** vs Puell’s 365d flow ratio. Related to Investor Cap (`realized − thermo`). | Cumulative subsidy USD (not UTXO realized cap). |
| 12 | **LTH / STH MVRV** (and VDD multiple) | Post-2021 “the MVRV that still moves.” LookIntoBitcoin and CheckOnChain now feature STH-MVRV / LTH-MVRV as cycle tools; VDD multiple (TXMC / LookIntoBitcoin) flags spending-velocity tops. | STH-MVRV **< 1** = short-term cohort underwater (local bottom heuristic). LTH-MVRV extremes = structural. VDD high = old coins spent into strength (top). | **Nested in aggregate MVRV / RHODL / SOPR.** Useful later as a *replacement* for vanilla MVRV, not an extra vote beside it. | Same UTXO set, 155d (Glassnode) / 150d (BRK) LTH cutoff. |

**Honourable mentions, not ranked as valuation:** NVT / NVTS (Woo; volume PE — ETF off-chain settlement has eaten the denominator), Hashribbons (miner capex, not valuation), Delta Price / Balanced Price / Top Cap (Originals *price models*, highly collinear with realized + CVDD), percent addresses in profit (MVRV cousin), AVIV / cointime (Checkmate’s newer fair-value — promising, not yet the consensus “famous” set).

### 2025–2026 read (do not ignore)

Spot ETFs and corporate treasuries moved a large share of *economic* volume
off the UTXO set. Several 2025–2026 recaps say MVRV, NUPL, Pi Cycle, and
Reserve Risk **did not print classic euphoria** at the Oct 2025 high, while
days-since-halving still matched prior tops. For SDCA that is an argument
to (1) **z-score on a long window** rather than freeze 2017 thresholds,
(2) keep on-chain as **one vote beside** the power-law rails, not a veto,
(3) never treat exchange-reserve drawdowns as “coins leaving the market”
without labelled ETF custody.

---

## Single-source hunt

Question: which **one catalog** can supply the valuation cluster
**without a paid Glassnode key?**

### Verdict

**Yes — Bitcoin Research Kit, hosted as [Bitview](https://bitview.space/api)
or self-hosted (MIT).** It is the only free, documented, no-key API that
returns MVRV, NUPL, SOPR/aSOPR, Puell, realized price, RHODL, Reserve Risk,
thermocap, and Pi Cycle as first-class series. It is **not** a complete
Glassnode clone (no CVDD, no named MVRV-Z, RHODL formula differs). That is
still enough for #1086 v1.

Smallest extra if a second feed is wanted: **Coin Metrics community** for
an independent `CapMVRVCur` + `IssTotUSD` cross-check (CC BY-NC — not for
commercial tearsheet republish without legal review). Not required to
*have* the cluster.

### Live probe (2026-08-30)

No production scraper. Read-only GETs against public docs/APIs.

#### Bitview / BRK (primary)

- Docs: [bitview.space/api](https://bitview.space/api),
  [llms.txt](https://bitview.space/llms.txt),
  source [github.com/bitcoinresearchkit/mono](https://github.com/bitcoinresearchkit/brk)
  (GitHub `full_name` `bitcoinresearchkit/mono`, **MIT**).
- Health `GET https://bitview.space/health`: `status=healthy`,
  `version=0.12.0`, `indexed_height=computed_height=tip_height=964790`,
  `blocks_behind=0`. Catalog advertises ~61k series, no auth, CORS open,
  MCP at `https://mcp.bitview.space/`.
- Search-then-GET (their documented workflow). **day1** latest, 2026-08-30:

| Series | Latest | day1 from | Notes |
|---|---|---|---|
| `mvrv` | **1.481577** | ~2011 (nulls in 2010 window) | Spot / realized price, all UTXOs. |
| `nupl` | **0.325044** | same | Docs state `1 − 1/MVRV`. Identity holds. |
| `realized_price` | **$53,028.66** | 2011 | USD cost basis. |
| `sopr_24h` | **1.0027** | 2010 (ones) | Trailing 24h SOPR; `sopr` itself is **height-only**. |
| `asopr_24h` | **1.0092** | 2010 | <1h filter. Prefer this over raw SOPR. |
| `puell_multiple` | **0.950** | 2011 | **Subsidy-only** (BRK description: block subsidy USD / 365d mean). Not fees. |
| `rhodl_ratio` | **0.167** | useful by 2013 | **1d–1w realized cap / 1–2y realized cap.** Docs do **not** mention LookIntoBitcoin’s “× market age” calibration — treat as a sibling, not a drop-in. |
| `reserve_risk` | **4.21e-6** | 2011 | `spot / HODL Bank`. Needs log or expanding-z; raw is tiny. |
| `thermo_cap_multiple` | **16.96** | 2011 | market / cumulative subsidy USD. |
| `pi_cycle` | **0.414** | SMA warmup | Price-only. Far from 1. |
| `lth_mvrv` / `sth_mvrv` | present | — | LTH = UTXOs ≥ **150d** (Glassnode commonly 155d). |
| `nvt`, `liveliness`, `vocdd` | present | — | `vocdd` is **height-indexed** supply-adjusted value of CDD — a **brick**, not Woo’s CVDD price. |
| `mvrv_z`, `cvdd` | **404** | — | Compute Z locally. No CVDD series. |

Also present and **not** in the v1 subset: `investor_cap`, `cointime_price`,
HODL-bank internals, LTH/STH SOPR.

Hosted Bitview is a **public research instance** (no SLA in the docs).
Production ingest should plan to **self-host BRK** against a bitcoind so
the feed is not a third-party single point of failure. License (MIT)
allows that. This note does not add that dependency.

#### Coin Metrics community (secondary, incomplete)

- Base: `https://community-api.coinmetrics.io/v4`, no key,
  [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)
  ([community package](https://docs.coinmetrics.io/packages/coin-metrics-community-data)).
- Catalog-v2 for `btc`: **31** metrics. Valuation-relevant that **200**:
  `CapMVRVCur` (history from **2010-07-18**), `CapMrktCurUSD`, `SplyCur`,
  `IssTotUSD` / `IssTotNtv`, `PriceUSD`, exchange flows.
- **403** without credentials (unchanged from the indicator-pool probe):
  `SOPR`, `NUPL`, `CapRealUSD`, `CapMVRVZ`, `RevUSD`.
- Latest overlap: `CapMVRVCur` **2026-08-29 = 1.475** vs Bitview
  `mvrv` **1.482** vs BGeometrics **1.486** — close enough that the
  *ratio* is the same object; do not mix vendors inside one z-window.

`IssTotUSD` is enough to **rebuild a subsidy-only Puell** locally, but
BRK already serves `puell_multiple`. Community data is the right
**cross-check**, the wrong **cluster source**, and the wrong license for
a commercial digiquant.io tearsheet without review.

#### BGeometrics (not the ingest)

- `GET https://bitcoin-data.com/v1/mvrv` **200**, 1461 points
  **2022-08-30 → 2026-08-29**, last `mvrv=1.4864`. Confirms the **4-year
  free window**.
- Free tier: **15 req/day**, ~8–10/hour
  ([services](https://charts.bgeometrics.com/services.html),
  [pricing](https://portal.bitcoin-data.com/pricing)).
- Commercial redistribution / publishing is **restricted**
  ([terms](https://bgeometrics.com/terms/),
  [commercial publishing add-on](https://bitcoin-data.com/bguser/commercial-publishing-features.html)).
- API *names* MVRV, NUPL, SOPR, Puell, Reserve Risk, etc. — coverage is
  not the blocker; **ToS + 4y + rate limit** are.

#### Paid / scrape-fragile (do not ingest)

| Source | Why it is famous | Why not #1086 v1 |
|---|---|---|
| Glassnode Studio / API | The industry metric-guide set | Paid. Atlas ops already list it as a research subscription, not an ingest. |
| CryptoQuant | Miner + exchange | Paid. |
| Look Into Bitcoin | The public *chart* canon (MVRV-Z, RHODL, Pi, CVDD, …) | Charts, not a documented bulk API. Scrape = ToS/human-gate. |
| CheckOnChain | Checkmate’s working set (Originals, SOPR, Puell, RHODL, AVIV) | Same: dashboard, not a free series API. |
| Woobull | Woo NVT / thermocap / Top Cap | Chart site; NVT even cites Coin Metrics **Pro** volume. |

### BRK vs Glassnode’s famous set

| Glassnode / LookIntoBitcoin “famous” | BRK series | Gap |
|---|---|---|
| MVRV | `mvrv` | — |
| MVRV-Z | *(none)* | Compute causal expanding z from `mvrv` |
| NUPL | `nupl` | Identity of MVRV; do not ingest as a second vote |
| Realized price | `realized_price` | — |
| SOPR / aSOPR | `sopr_24h`, `asopr_24h` | Use aSOPR |
| LTH/STH MVRV, SOPR, NUPL | `lth_*`, `sth_*` | 150d vs Glassnode 155d |
| Puell | `puell_multiple` | **Subsidy-only** vs some “miner revenue” builds |
| RHODL | `rhodl_ratio` | Missing LookIntoBitcoin age-of-market multiplier |
| Reserve Risk | `reserve_risk` | Present |
| Pi Cycle | `pi_cycle` | Price-only |
| Thermocap | `thermo_cap`, `thermo_cap_multiple` | Present |
| CVDD | **missing** (`vocdd` ≠ CVDD) | Only real hole in the *Originals* toolkit |
| Entity-adjusted NVT, labelled ETF custody | missing | Out of v1 |

**Honest line:** one self-host (BRK) supplies SOPR + MVRV + Puell + RHODL
together. Coin Metrics community does **not**. No need for a two-vendor
cluster unless we want a license-constrained MVRV audit tape.

---

## BTC SDCA on-chain v1 subset

Four votes, four families. Map each to `[-3, +3]` with **cheap = +**
(same convention as `power_law_zscore.py`). Do **not** also enable NUPL,
realized price, MVRV-Z-as-raw, LTH/STH MVRV, or Pi Cycle.

| # | Indicator | Bitview series | Family | z mapping (when #1086 is executed) |
|---|---|---|---|---|
| 1 | **MVRV-Z** | `mvrv` (`day1`) | Stock cost-basis | Causal expanding (or very long rolling) z of **−MVRV**. This is the Glassnode-style vote; not a second MVRV. |
| 2 | **aSOPR** | `asopr_24h` (`day1`) | Flow realized P/L | Causal z of **−(aSOPR − 1)** or a slow z of −aSOPR. The economically meaningful SOPR. |
| 3 | **Puell** | `puell_multiple` (`day1`) | Miner issuance | Causal z of **−Puell**. Document the subsidy-only definition. Do not invent a fee-inclusive series from BRK. |
| 4 | **RHODL** | `rhodl_ratio` (`day1`) | Age-wealth | Causal z of **−RHODL** (log first if needed). One holder-structure vote; **not** Reserve Risk as well. |

**One source to ingest first:** **Bitview `GET /api/series/{id}/day1`**
(or the same paths on a self-hosted BRK). Start with those four ids plus
`realized_price` as a **non-voting annotation** (cost-basis line for
tearsheets / Atlas). Skip `nupl`.

**Not v1 (collinear or wrong layer):**

- NUPL, raw MVRV alongside MVRV-Z, LTH/STH MVRV.
- Reserve Risk (same conviction family as RHODL; add only if RHODL is
  dropped).
- Pi Cycle, Mayer, 200w — price-only, overlap the power-law `power_law_z`
  (*r* ≈ 0.84 in the indicator-pool note).
- CVDD — not in BRK; floor model, not an oscillator.
- Thermocap multiple — slow cousin of Puell; keep off the v1 ballot.
- Hyperdash — positioning, not valuation.
- Coin Metrics `CapMVRVCur` **instead of** BRK MVRV — still valid as a
  *fallback if Bitview is down*, but it cannot carry SOPR/Puell/RHODL, and
  CC BY-NC blocks commercial republish. Prefer BRK MIT for the pipeline.

**Null rule reminder** (from the indicator-pool note, still true): today’s
composite **nulls the day** if any enabled extra is null. A Bitview
outage would halt SDCA if these are enabled. #1086 must either
fail-soft (skip-missing) or keep the on-chain vote **off** until the
series is dense. That is an implementer problem, not this note.

**License:** BRK MIT is the path that can eventually appear on
digiquant.io. Coin Metrics community and BGeometrics are research-only
until legal says otherwise. Do not scrape Look Into Bitcoin.

---

## What #1086 should do next (not this PR)

1. Read-only client for Bitview/BRK `day1` series (four ids above),
   Polars, Pydantic, persistent-failure tracker like other digiquant
   pipelines. Prefer self-host later; hosted is enough to **bootstrap
   history**.
2. Local MVRV-Z; do not buy Glassnode’s z.
3. Wire as extras into `compute_composite_risk` **after** a skip-missing
   or equivalent fail-soft exists.
4. Cross-check MVRV vs Coin Metrics `CapMVRVCur` in tests/research, not
   in the production blend.
5. Human gate before any live-trading path. None of this is live-trading.

---

## Sources (accessed 2026-08-30)

- Bitview API / llms.txt / health / series metadata and `day1` latest:
  [https://bitview.space/api](https://bitview.space/api),
  [https://bitview.space/llms.txt](https://bitview.space/llms.txt)
- BRK source + MIT: [https://github.com/bitcoinresearchkit/brk](https://github.com/bitcoinresearchkit/brk)
- Coin Metrics community catalog + timeseries: [https://community-api.coinmetrics.io/v4](https://community-api.coinmetrics.io/v4);
  license [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/);
  docs [community data](https://docs.coinmetrics.io/packages/coin-metrics-community-data)
- BGeometrics `GET /v1/mvrv`, [terms](https://bgeometrics.com/terms/),
  [pricing](https://portal.bitcoin-data.com/pricing)
- Look Into Bitcoin on-chain list / MVRV-Z / RHODL / Reserve Risk:
  [https://www.lookintobitcoin.com/charts/on-chain-charts/](https://www.lookintobitcoin.com/charts/on-chain-charts/)
- Glassnode metric guides (MVRV, MVRV-Z, NUPL, aSOPR, Puell, Reserve Risk)
  and [On-chain Originals](https://studio.glassnode.com/charts/btc-onchain-originals?a=BTC)
- CheckOnChain: [https://charts.checkonchain.com/](https://charts.checkonchain.com/)
- Woobull (NVT / valuations, no API): [http://charts.woobull.com/bitcoin-valuations/](http://charts.woobull.com/bitcoin-valuations/)
- 2025–2026 cycle commentary:
  [HTX](https://www.htx.com/news/the-bitcoin-4-year-cycle-has-never-disappeared-it-just-chang-J5c99l0v/),
  [Nonce Media](https://www.noncemedia.com/bitcoin-exchange-reserves-historic-low-rally-signal-broken-2026/)
- Indicator origin notes:
  [Ledger School — realized price & MVRV](https://situationroom.space/ledger-school/realized-price-mvrv),
  [Spark cycle-indicator comparison](https://www.spark.money/tools/bitcoin-market-cycle-indicator-comparison)
