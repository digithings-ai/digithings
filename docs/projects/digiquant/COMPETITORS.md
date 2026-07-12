# DigiQuant — Competitive Notes

Tracks products that compete with DigiQuant's positioning, and patterns worth learning from. Update as new competitors surface or existing entries go stale. Each entry follows the template at the bottom.

## Landscape at a glance

| Product | Segment | Strategy authoring | Live execution | Pricing model |
|---|---|---|---|---|
| [Minara.ai](#minaraai) | Crypto/DeFi, retail | Pine Script-like ("Pine Runtime") | Autopilot, on-device approval gate | Usage credits (tiered cap) |
| [Horizon.Trade](#horizontrade) | ETF/factor-rotation, retail | Plain-English → AI-generated code | One-click broker connect + deploy | Waitlist / pre-launch, no pricing disclosed |
| [Composer (SoFi)](#composer-sofi) | US equities/ETFs, retail | Plain-English → visual no-code editor | Automated rebalancing via linked brokerage | Flat monthly subscription |
| [QuantConnect](#quantconnect) | Multi-asset, institutional + quant retail | Python (LEAN) + "Mia" AI assistant | Managed co-located live deployment, 20+ brokers | Cloud-resource-usage tiers |
| **DigiQuant** | Multi-asset, agentic orchestration | Python (NautilusTrader) + LangGraph sub-graphs | Human-approval-gated live path | N/A (open-core) |

## Patterns worth learning from

- **On-device/local/cloud model tiering for execution authority** (Minara/DMind): splitting a model family by where it runs, and pinning the final go/no-go decision to the lowest-trust-required tier, is a concrete alternative to a human-approval gate. DigiThings' current rule is human-in-the-loop for all live-trading paths (`CLAUDE.md`, enforced via digikey) — worth revisiting only if latency becomes a stated requirement, not by default.
- **Flat/credit-metered pricing per action** (Minara, Composer) is easier for retail users to reason about than raw token billing. Relevant if digillm-routed usage is ever exposed as a billed API.
- **Open engine + AI assistant layered on top** (QuantConnect's LEAN + Mia) is architecturally the closest analog to DigiQuant's NautilusTrader + LangGraph/Atlas/Hermes split — validates the "open backtest/execution core, agentic layer on top" shape as a proven pattern rather than a novel bet.
- **Strategy marketplace / social copy-trading** (Horizon, Minara) recurs across nearly every competitor as a growth/retention lever — none of DigiThings' current components do this; worth a note if DigiQuant ever targets retail distribution rather than staying institutional-only.
- **Plain-English-to-backtest as the default entry point**, with code/DSL as a secondary "advanced" surface, is now table stakes across this whole category (all four competitors below lead with it) — not a differentiator on its own, just a baseline expectation.

---

## Minara.ai

Identified: 2026-07-02 · Source: https://minara.ai (site + `/docs`)

**What it is:** "AI-native financial operating system" for crypto/DeFi trading. Natural-language chat research, "Strategy Studio" for generating quant strategies from plain-language descriptions, backtesting, and "Autopilot" for autonomous execution. Assets covered: crypto perps (Hyperliquid/Lighter), spot across 8 chains, US equities/commodities via Hyperliquid, prediction markets (Polymarket-style).

**Pricing:** Usage-based credits, not seats. Tiers Lite (1,400 credits/mo), Starter (4,000), Pro (20,000). Typical costs: ~20 credits/chat, ~40/Deep Research report, ~15/workflow "Minara node" (Monitor/Trade/Notify nodes are free). Dollar prices weren't extractable (rendered as images on the pricing page).

**Strategy authoring:** "Pine Runtime" — TradingView Pine Script-like DSL, retail-friendly — versus DigiQuant's NautilusTrader Python-native backtest/optimize/live pipeline.

**Model/safety architecture (the notable part):** Their model family "DMind" is tiered by deployment location:
- Nano (270M params, on-device) — transaction-time safety checks, no network round-trip
- Mini (4B, local) — strategy analysis over private holdings
- Oracle (21B, cloud, 256k context) — market research, cross-chain analysis, long-form reports

The final trade go/no-go decision always executes **on-device**, never in the cloud. DMind handles finance-native reasoning (on-chain parsing, DeFi protocol risk); general-purpose LLMs (they cite Claude) handle broader tasks.

**Comparison to DigiQuant:**
- Minara is crypto/DeFi-first and retail-oriented; DigiQuant is asset-class-agnostic and NautilusTrader-based, reading as more institutional.
- DigiThings' live-trading safety model is a **human-in-the-loop** approval gate (per `CLAUDE.md`: "Never touch live-trading paths without explicit human approval," enforced via digikey auth). Minara's on-device model tiering is a **device-in-the-loop** alternative — it trades auditability for lower latency. Worth referencing as a contrast point if DigiQuant's live-trading authorization design is revisited, not necessarily worth copying given DigiThings' compliance stance.
- Their flat-credit-per-action pricing is simpler than token-metered LLM billing and could be a reference model if DigiThings ever exposes usage-based API pricing for digillm-routed calls.

**Caveat:** Snapshot from 2026-07-02 — re-check `minara.ai/docs` before citing specifics externally; startup pricing/product details change fast.

## Horizon.Trade

Identified: 2026-07-02 · Source: https://horizon.trade (home + pricing page, fetched directly)

**What it is:** AI-powered algorithmic trading platform: describe a trading idea in plain English, AI converts it into structured, executable rules, backtests it against historical data across multiple timeframes, and offers one-click deployment to a connected broker for live automated execution. Provides risk analytics (Sharpe ratio, drawdown, win rate, profit factor) and lets users iterate/re-test parameters continuously. Featured example: an 11-ETF sector-momentum rotation strategy (top 3 by trailing momentum, monthly rebalance) backtested at +32.7% return / 1.71 Sharpe.

**Asset classes:** Site emphasizes ETFs (sector, country, factor, bond) as the primary showcase; broader coverage is implied via broker integrations but not confirmed. Note: an earlier search-summary pass on this doc said "stocks, crypto, forex" — that was not corroborated by the direct site fetch and should be treated as unverified until seen firsthand.

**Pricing:** No pricing disclosed. The site is currently a **waitlist/access-request** funnel ("Get Access" / "Join Waitlist"), not a live self-serve product — pre-launch or limited-access stage as of 2026-07-02. Contact is hello@horizon.trade for specifics.

**Comparison to DigiQuant:** Closest positioning match to DigiQuant's "describe intent, get a backtested and deployable strategy" pitch, but aimed at unassisted retail traders end-to-end (one-click broker connect + live deploy) with no visible approval gate, versus DigiQuant's orchestrated pipeline with an explicit human-approval requirement for live paths. Being pre-launch/waitlist-gated makes it a weaker near-term competitive threat than Minara or QuantConnect, but worth re-checking once it opens access broadly — the ETF-momentum framing suggests they may be targeting a narrower retail-factor-investing niche rather than general multi-asset quant.

**Caveat:** Snapshot from 2026-07-02, homepage + pricing page only (no `/docs`). Multiple similarly-named "Horizon" trading products exist (horizon-trade.com, horizontrading.ai, horizontrading.io) — this entry is specifically about `horizon.trade`; don't conflate with the others.

## Composer (SoFi)

Identified: 2026-07-02 · Source: https://www.composer.trade

**What it is:** No-code platform (now under SoFi) for building, backtesting, and auto-executing trading strategies. Users describe investment goals in natural language; AI generates a strategy, then a visual editor lets them adjust weightings, add conditional ("if this, then that") logic, apply filters, and backtest against benchmarks. Fully automated execution and rebalancing across linked accounts, including IRAs.

**Pricing:** Zero commissions/management fees; flat monthly subscription ("Composer Trading Pass") with a free trial; some additional fees may apply per fee schedule.

**Strategy authoring:** Visual/no-code editor (allocation weights + conditional blocks), not a scripting language — the most retail-simplified authoring model of the group.

**Supported assets:** US equities and ETFs only; retirement account support (Traditional/Roth IRA) is distinctive — none of the other competitors here mention tax-advantaged account integration.

**Comparison to DigiQuant:** Narrowest scope (US equities/ETFs, no crypto/derivatives) and most retail-simplified of the group — effectively "robo-advisor with a strategy builder" rather than a quant research platform. Low direct overlap with DigiQuant's institutional/multi-asset ambitions, but the IRA/tax-advantaged-account integration is a distribution angle worth noting if DigiThings ever considers a retail-facing product surface.

**Caveat:** Snapshot from 2026-07-02; SoFi ownership may mean pricing/features shift with SoFi's broader roadmap rather than an independent startup's.

## QuantConnect

Identified: 2026-07-02 · Source: https://www.quantconnect.com

**What it is:** Cloud-based algorithmic trading platform built on **LEAN**, an open-source engine (20k+ GitHub stars, 180+ contributors) that can run on-premises or in QuantConnect's cloud. Layers an agentic AI assistant, **Mia**, on top for natural-language strategy design, automated backtesting, code editing, and one-step deployment. Full workflow: Research (cloud notebooks + terabytes of financial/alt data + ML libraries) → Backtest (point-in-time, multi-asset, realistic fees/slippage/margin) → Optimize (parallelized parameter sweeps) → Live (managed co-located deployment, $45B+/month volume, 20+ broker integrations).

**Pricing:** Tiered by cloud resource usage; free tier includes research notebooks and backtesting, premium tiers add institutional-grade live infrastructure.

**Target users:** Broad — 514,000-person community spanning retail quants, data scientists, hedge funds, and academic institutions.

**Comparison to DigiQuant:** The closest structural analog in this list — an open-source, multi-asset backtest/live engine (LEAN, playing NautilusTrader's role) with an agentic AI layer bolted on top (Mia, playing digigraph/Atlas/Hermes's role). Validates that DigiQuant's "open execution core + agentic orchestration" architecture is a proven, scaled pattern (500k+ users, real live volume) rather than a novel bet. Main gaps vs. DigiQuant to watch: QuantConnect's AI layer (Mia) is a single assistant rather than a supervisor + specialized sub-graph architecture, and it doesn't appear to have DigiQuant's explicit human-approval gate for live-trading paths as a first-class compliance feature — an area where DigiQuant could differentiate for institutional/regulated buyers.

**Caveat:** Snapshot from 2026-07-02, single homepage fetch — pricing tier details and Mia's actual capabilities weren't independently verified against QuantConnect's docs.

---

## Entry template

Copy this when adding a new competitor:

```markdown
## <Name>

Identified: <date> · Source: <url(s) actually fetched, or "web search summary" if not>

**What it is:** <one paragraph — category, core product, target user>

**Pricing:** <model + tiers if known>

**Strategy authoring / tech:** <how strategies are built, key architecture>

**Comparison to DigiQuant:** <where it overlaps, where it doesn't, what's worth learning or contrasting>

**Caveat:** <freshness date, anything unverified or ambiguous (e.g. name collisions)>
```
