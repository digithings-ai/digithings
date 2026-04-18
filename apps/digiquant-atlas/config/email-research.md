# Email Research Setup Guide

This file documents how to set up a dedicated research email inbox for receiving newsletters, institutional research, and market intelligence that feeds the daily digest pipeline.

---

## Overview

The goal is a **single dedicated Gmail account** (`market-research@gmail.com` or similar) that receives only high-signal financial research. You read it once per day before running your digest. Claude can be provided with digested content via paste or attachment during the session.

---

## Step 1: Create the Dedicated Gmail Account

1. Go to https://accounts.google.com/signup
2. Create: `[firstname]market.research@gmail.com` or similar
3. Enable Gmail in all clients (iOS Mail, Apple Mail, etc.) via IMAP
4. Set up a forwarding rule: subscriptions you upgrade will all go here
5. **Never use this email for anything except research subscriptions**

---

## Step 2: Gmail Filters (Critical)

Create filters immediately to organize incoming mail:

### Priority Labels to Create:
- `RESEARCH/Macro` (yellow)
- `RESEARCH/Equity` (orange)
- `RESEARCH/Crypto` (blue)
- `RESEARCH/HedgeFund` (green)
- `RESEARCH/Options-AltData` (purple)
- `RESEARCH/Energy` (red)
- `RESEARCH/Geopolitical` (dark grey)

### Auto-Archive Non-Research Emails:
- Filter: `to:market.research@gmail.com -from:(*newsletter*|*substack*|*research*)` → Archive immediately

---

## Step 3: Subscription List

Subscribe to the following newsletters/alerts at your dedicated email:

### Free Tier (Subscribe Immediately)

| Source | URL | Label | Frequency |
|--------|-----|-------|-----------|
| Macro Alf Newsletter | https://totalreturn.substack.com | RESEARCH/Macro | Weekly |
| Doomberg | https://doomberg.substack.com | RESEARCH/Energy | 2x/week |
| The Kobeissi Letter | https://kobeissiletter.com | RESEARCH/Macro | Daily |
| Barchart Options Digest | https://barchart.com | RESEARCH/Options-AltData | Daily |
| EIA Weekly Petroleum | https://eia.gov/petroleum/supply/weekly/ sign up for email | RESEARCH/Energy | Wednesday |
| Farside BTC ETF Flows | https://farside.co.uk | RESEARCH/Crypto | Daily |
| CFTC COT via email alert | https://cftc.gov/MarketReports/CommitmentsofTraders | RESEARCH/Options-AltData | Friday |
| Capitol Trades Alerts | https://capitoltrades.com (set up alerts) | RESEARCH/HedgeFund | As filed |
| Quiver Quant Weekly | https://quiverquant.com | RESEARCH/HedgeFund | Weekly |
| FRED Email Alerts | https://fred.stlouisfed.org (set up series alerts for 10Y, 2Y, DXY) | RESEARCH/Macro | On release |
| WSJ Markets (free tier) | https://wsj.com | RESEARCH/Macro | Daily |

### Paid (If Budget Allows — Ranked by ROI)

| Source | URL/Cost | Label | Why Valuable |
|--------|----------|-------|--------------|
| SpotGamma HIRO | https://spotgamma.com (~$399/yr) | RESEARCH/Options-AltData | Dealer gamma exposure, real-time GEX |
| Glassnode Advanced | https://glassnode.com (~$799/yr) | RESEARCH/Crypto | Full on-chain analytics |
| Unusual Whales ($29/mo) | https://unusualwhales.com | RESEARCH/Options-AltData | Options flow, dark pool, congress trades |
| WhaleWisdom Pro | https://whalewisdom.com (~$40/mo) | RESEARCH/HedgeFund | 13F analytics, fund tracking |
| Bridgewater Daily Observations | Institutional only | RESEARCH/HedgeFund | Direct macro view (if accessible) |
| Energy Intel | https://energyintel.com | RESEARCH/Energy | Upstream oil market intelligence |

---

## Step 4: How to Use During Digest Sessions

### Option A: Manual Paste
1. Open research inbox before starting digest
2. Skim emails by label
3. Copy-paste key excerpts into Claude conversation at session start
4. Prompt: "Here are my research emails from the past 24h: [paste]. Integrate these into the relevant segments."

### Option B: Pre-Session Summary
1. Read all emails in 15-20 minutes
2. Verbally brief Claude at session start: "Key intel from email today: [your summary]"
3. This works well when most emails confirm what you already see in the data

### Option C: Attachment (PDF/Text)
1. Forward newsletters to yourself as text
2. Attach to Claude conversation
3. Claude reads and integrates automatically

### Best Practice:
- Use Option A during Phase 1 (Alternative Data) — paste relevant sections into `skills/alt-sentiment-news/SKILL.md` where that skill asks for email context
- Use Option B during Phase 2 (Institutional) — hedge fund letters, fund commentary
- Use Option C for long-form research (quarterly letters, deep dive reports)

---

## Step 5: Quarterly Hedge Fund Letter Calendar

| Fund | Letter Timing | What to Look For |
|------|--------------|-----------------|
| Berkshire Hathaway | Annual report (February) | Buffett's macro commentary, equity allocation |
| Pershing Square | Quarterly (45-60 days after Q end) | Ackman's macro views, activist targets |
| Third Point | Quarterly | Loeb's top holdings, themes |
| Greenlight Capital | Quarterly | Einhorn's shorts, value ideas |
| Bridgewater | Daily Observations (institutional) | Macro regime framing |
| AQR | Research papers + quarterly | Factor analysis, portfolio construction |

**Action**: When a quarterly letter is released, devote 10 minutes to extracting key positions and biases. Update `config/hedge-funds.md` with latest known positions.

---

## Step 6: Alerts to Set Up

### Price Alerts (via Barchart or Yahoo Finance)
- WTI Crude: Alert at $120 (escalation) and $80 (thesis invalidation)
- Gold: Alert at $5,000 (next psychological level) and $4,200 (support)
- BTC: Alert at $75,000 and $55,000
- VIX: Alert at 30 (high vol regime) and 16 (complacency)
- 10Y Yield: Alert at 5.00% (breakout) and 4.00% (easing signal)

### EDGAR Alerts
- Set up EDGAR email alerts for holdings >5% on key names: https://efts.sec.gov/LATEST/search-index
- Filter on 13D/13G filings for holdings in your watchlist

### Google Alerts
- Create Google Alerts for: "Iran Strait of Hormuz", "[your tracked hedge fund names]", "Federal Reserve pivot", "OPEC+ production"
- Deliver to research email, label `RESEARCH/Geopolitical`
