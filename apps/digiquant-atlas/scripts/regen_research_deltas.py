#!/usr/bin/env python3
"""
regen_research_deltas.py

Regenerates all research segment delta documents (Apr 6-14, 2026) as proper full
evolved documents. Each delta is the COMPLETE research document for that day, derived
from the Apr 5 baseline by applying day-specific changes cumulatively.

Architecture:
  - Baseline (Sunday): Full document, all sections from scratch
  - Delta (weekday):   Full document, derived from previous day by updating only what changed
  - Diff view in library: compares current vs previous day to show evolution

This script upserts all 200 research segment × delta day documents to Supabase,
overwriting any existing brief summaries or empty payloads.

Usage:
  export $(cat config/supabase.env | xargs)
  python3 scripts/regen_research_deltas.py
  python3 scripts/regen_research_deltas.py --dry-run
  python3 scripts/regen_research_deltas.py --segment macro
  python3 scripts/regen_research_deltas.py --date 2026-04-08
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / "config" / "supabase.env")
    load_dotenv()
except ImportError:
    pass

try:
    from supabase import create_client
    _HAS_SB = True
except ImportError:
    _HAS_SB = False


# ---------------------------------------------------------------------------
# Price anchors from Supabase price_history (actual close prices)
# ---------------------------------------------------------------------------
PRICES = {
    "2026-04-06": {
        "SPY": 658.93, "QQQ": 588.50, "IWM": 252.36,
        "GLD": 427.65, "IAU": 87.61, "BIL": 91.44, "SHY": 82.28, "TLT": 86.65,
        "XLK": 136.78, "XLV": 146.28, "XLE": 59.68, "XLF": 49.88,
        "XLP": 82.66, "XLY": 109.04,
        # Derived narrative prices (simulated world)
        "WTI": 111.0, "GOLD_OZ": 4430, "DXY": 99.4, "BTC": 84000, "ETH": 1555,
        "TNX": 4.28,   # 10Y yield %
    },
    "2026-04-07": {
        "SPY": 659.22, "QQQ": 588.59, "IWM": 252.91,
        "GLD": 431.81, "IAU": 88.46, "BIL": 91.45, "SHY": 82.34, "TLT": 86.64,
        "XLK": 137.43, "XLV": 146.57, "XLE": 60.16, "XLF": 49.88,
        "XLP": 81.26, "XLY": 107.77,
        "WTI": 113.0, "GOLD_OZ": 4475, "DXY": 99.1, "BTC": 82200, "ETH": 1520,
        "TNX": 4.30,
    },
    "2026-04-08": {
        "SPY": 676.01, "QQQ": 606.09, "IWM": 260.47,
        "GLD": 434.53, "IAU": 89.04, "BIL": 91.45, "SHY": 82.42, "TLT": 86.92,
        "XLK": 141.69, "XLV": 149.67, "XLE": 58.05, "XLF": 51.20,
        "XLP": 82.78, "XLY": 110.82,
        "WTI": 103.0, "GOLD_OZ": 4510, "DXY": 98.5, "BTC": 87500, "ETH": 1625,
        "TNX": 4.33,
    },
    "2026-04-09": {
        "SPY": 679.91, "QQQ": 610.19, "IWM": 261.96,
        "GLD": 437.91, "IAU": 89.72, "BIL": 91.46, "SHY": 82.44, "TLT": 86.70,
        "XLK": 142.07, "XLV": 149.33, "XLE": 57.33, "XLF": 51.33,
        "XLP": 83.45, "XLY": 112.74,
        "WTI": 99.5, "GOLD_OZ": 4550, "DXY": 98.0, "BTC": 89200, "ETH": 1660,
        "TNX": 4.36,
    },
    "2026-04-10": {
        "SPY": 679.46, "QQQ": 611.07, "IWM": 261.30,
        "GLD": 437.13, "IAU": 89.56, "BIL": 91.49, "SHY": 82.41, "TLT": 86.49,
        "XLK": 142.62, "XLV": 147.31, "XLE": 56.94, "XLF": 50.77,
        "XLP": 82.37, "XLY": 112.89,
        "WTI": 98.0, "GOLD_OZ": 4540, "DXY": 98.2, "BTC": 88400, "ETH": 1645,
        "TNX": 4.35,
    },
    "2026-04-11": {
        "SPY": 679.46, "QQQ": 611.07, "IWM": 261.30,  # carry forward Fri close
        "GLD": 437.13, "IAU": 89.56, "BIL": 91.49, "SHY": 82.41, "TLT": 86.49,
        "XLK": 142.62, "XLV": 147.31, "XLE": 56.94, "XLF": 50.77,
        "XLP": 82.37, "XLY": 112.89,
        "WTI": 97.5, "GOLD_OZ": 4540, "DXY": 98.3, "BTC": 87800, "ETH": 1640,
        "TNX": 4.34,
    },
    "2026-04-13": {
        "SPY": 686.10, "QQQ": 617.39, "IWM": 265.07,
        "GLD": 435.36, "IAU": 89.21, "BIL": 91.49, "SHY": 82.47, "TLT": 86.75,
        "XLK": 145.61, "XLV": 147.97, "XLE": 57.11, "XLF": 51.66,
        "XLP": 81.55, "XLY": 113.92,
        "WTI": 97.0, "GOLD_OZ": 4525, "DXY": 98.5, "BTC": 91000, "ETH": 1710,
        "TNX": 4.31,
    },
    "2026-04-14": {
        "SPY": 694.46, "QQQ": 628.60, "IWM": 268.72,
        "GLD": 445.09, "IAU": 91.18, "BIL": 91.50, "SHY": 82.53, "TLT": 87.21,
        "XLK": 147.94, "XLV": 148.83, "XLE": 55.95, "XLF": 51.78,
        "XLP": 81.47, "XLY": 116.44,
        "WTI": 94.5, "GOLD_OZ": 4625, "DXY": 98.0, "BTC": 93000, "ETH": 1745,
        "TNX": 4.27,
    },
}

DELTA_DATES = [
    "2026-04-06", "2026-04-07", "2026-04-08", "2026-04-09",
    "2026-04-10", "2026-04-11", "2026-04-13", "2026-04-14",
]

# Narrative headlines and key events per day (for context)
DAY_CONTEXT = {
    "2026-04-06": {
        "day": "Monday", "delta_n": 1,
        "headline": "DXY Breaks 100 — Dollar Weakness Milestone; Iran Ceasefire Proposal Received",
        "key_events": [
            "DXY broke below 100.0 for first time since 2021 — structural dollar weakness signal",
            "Iran side sent 45-day ceasefire proposal to US via back-channel (Qatar mediator)",
            "Trump issued April 7 ultimatum: open Hormuz or face strikes on power infrastructure",
            "Fed confirmed at 3.50-3.75% (corrected from stale baseline data; March 18 FOMC decision)",
            "Markets flat as investors await Tuesday's ultimatum deadline",
        ],
        "spy_chg_pct": 0.04,
        "risk_regime": "Binary Risk (Pivoting)",
        "geopolitical": "Iran ceasefire proposal in hand — binary outcome by tomorrow",
    },
    "2026-04-07": {
        "day": "Tuesday", "delta_n": 2,
        "headline": "Trump Ultimatum Deadline Day — Iran Rejects Terms; Tensions Re-escalate",
        "key_events": [
            "Iran formally rejected Trump's April 7 ultimatum — Hormuz stays restricted",
            "US announced additional naval assets deployed to Gulf region",
            "Markets essentially flat — uncertainty creates two-way risk",
            "Gold rose +1.0% on renewed safe-haven demand (war premium bid)",
            "Oil rebounded from Monday dip back to $113 on conflict risk resumption",
        ],
        "spy_chg_pct": 0.04,
        "risk_regime": "Risk-Off (Geopolitical Tension)",
        "geopolitical": "Iran rejected ultimatum; US military posture escalated",
    },
    "2026-04-08": {
        "day": "Wednesday", "delta_n": 3,
        "headline": "CEASEFIRE SIGNED — Markets Rally 2.5%; Oil War Premium Partly Unwound",
        "key_events": [
            "US and Iran signed 45-day ceasefire — Hormuz Protocol extended, shipping resumes",
            "SPY surged +2.5% (6,594→6,760) on geopolitical de-escalation",
            "WTI crude fell -8.8% ($113→$103) as war premium unwound",
            "Energy sector (XLE) dropped -3.5% — oil price reduction = earnings headwind",
            "Technology (XLK +3.1%), Financials (XLF +2.6%) led the rally",
            "Gold HELD and rose slightly — tariff inflation concerns persist despite ceasefire",
        ],
        "spy_chg_pct": 2.54,
        "risk_regime": "Risk-On (Ceasefire Rally)",
        "geopolitical": "Ceasefire signed; war premium partially unwound; tariff inflation persists",
    },
    "2026-04-09": {
        "day": "Thursday", "delta_n": 4,
        "headline": "90-Day Tariff Pause Announced — Ceasefire Holds; Markets Add +0.6%",
        "key_events": [
            "Trump announced 90-day pause on reciprocal tariffs for most trading partners",
            "EXCEPTION: China tariffs remain and rise to 145% (escalation vs. all others de-escalated)",
            "SPY +0.6% ($676→$680) as markets absorbed dual tailwinds",
            "WTI crude fell further to $99.5 — ceasefire + demand concerns",
            "Gold continued rising (+$40) despite risk-on — tariff inflation hedge bid",
            "10Y yield rose to 4.36% — tariff pause = less need for emergency Fed cuts",
        ],
        "spy_chg_pct": 0.58,
        "risk_regime": "Cautious Recovery (Dual Tailwinds)",
        "geopolitical": "90-day tariff pause (ex-China); ceasefire day 2 holding",
    },
    "2026-04-10": {
        "day": "Friday", "delta_n": 5,
        "headline": "Post-Event Consolidation — Markets Hold Gains; Risk-On Confirmed",
        "key_events": [
            "SPY flat (-0.07%) after two days of strong gains — healthy consolidation",
            "Gold digested previous day's run, slight dip (-$10)",
            "Energy continued lower on demand revision — WTI $98, XLE -0.7%",
            "Healthcare (XLV) lagged as defensive rotation unwound",
            "Weekly: SPY +3.1%, QQQ +3.8%, IWM +3.6% — broad risk-on week confirmed",
            "10Y yield slightly lower (4.35%) — real rates still elevated",
        ],
        "spy_chg_pct": -0.07,
        "risk_regime": "Risk-On (Consolidation)",
        "geopolitical": "Ceasefire day 3 holding; tariff pause digested",
    },
    "2026-04-11": {
        "day": "Saturday", "delta_n": 6,
        "headline": "Weekend Review — Geopolitical Reset Complete; Tariff Regime Digested",
        "key_events": [
            "No market trading — review day for weekly developments",
            "Ceasefire day 4 holding — Hormuz shipping lanes fully reopened",
            "Oil tanker traffic normalizing; analysts revising WTI to $92-100 range target",
            "China tariff escalation (145%) expected to weigh on global trade in Q2 2026",
            "Q1 2026 earnings season opens Monday — JPMorgan, Goldman Sachs report",
            "Fed silence period ahead of May FOMC — no scheduled speeches",
        ],
        "spy_chg_pct": 0.0,
        "risk_regime": "Risk-On (Weekend Review)",
        "geopolitical": "Ceasefire holding; tariff pause framework intact; China excluded",
    },
    "2026-04-13": {
        "day": "Monday", "delta_n": 7,
        "headline": "Q1 Earnings Beat — JPMorgan, Goldman Sachs Outperform; SPY +1.0%",
        "key_events": [
            "JPMorgan Q1 2026: EPS $4.98 vs $4.60 est (BEAT +8.3%); revenue $44.3B vs $43.2B est",
            "Goldman Sachs Q1 2026: EPS $14.12 vs $12.85 est (BEAT +9.9%); trading revenue strong",
            "SPY +1.0% ($679→$686); XLF (financials) led at +0.6% on earnings confirmation",
            "Gold dipped slightly (-$15) — risk-on rotation from safe havens",
            "WTI stabilized at $97 — oil market finding equilibrium post-ceasefire",
            "10Y yield fell to 4.31% — strong earnings = no recession = disinflation narrative",
        ],
        "spy_chg_pct": 0.97,
        "risk_regime": "Risk-On (Earnings Season Opened Positively)",
        "geopolitical": "Ceasefire day 6 — Hormuz stable; tariff pause holding",
    },
    "2026-04-14": {
        "day": "Tuesday", "delta_n": 8,
        "headline": "Bank of America, Morgan Stanley Beat — Gold Surges 2.2%; SPY +1.2%",
        "key_events": [
            "Bank of America Q1 2026: EPS $0.90 vs $0.83 est (BEAT +8.4%); consumer banking resilient",
            "Morgan Stanley Q1 2026: EPS $2.60 vs $2.35 est (BEAT +10.6%); wealth mgmt strong",
            "SPY +1.2% ($686→$694); XLK +1.6% as tech rotated back in",
            "GOLD SURGED +2.2% (IAU $89.21→$91.18) — inflation hedge demand re-emerged",
            "Tariff inflation thesis re-affirmed: China 145% tariffs = imported cost pressures persist",
            "Energy continued lower (XLE -2.0%, WTI $94.5) — post-war-premium overshoot",
            "10Y yield dipped to 4.27% as gold bid confirmed flight-to-safety alongside risk-on paradox",
        ],
        "spy_chg_pct": 1.22,
        "risk_regime": "Risk-On with Inflation Vigilance",
        "geopolitical": "Ceasefire day 7 — stable; gold/tariff inflation the new dominant narrative",
    },
}

# ---------------------------------------------------------------------------
# Document generators — one per research segment
# ---------------------------------------------------------------------------

def gen_macro(date: str, p: dict, ctx: dict) -> str:
    d = ctx["delta_n"]
    headline = ctx["headline"]
    risk = ctx["risk_regime"]
    is_weekend = (date == "2026-04-11")

    if date == "2026-04-06":
        policy_state = "Easing (Confirmed)"
        policy_note = "Fed confirmed at 3.50-3.75% (March 18 FOMC); 2 consecutive holds at this level. ~35% cut probability for May."
        risk_appetite = "Pivoting — Binary Event Resolved Tomorrow"
        overall = "GEOPOLITICAL SHOCK (Softening) → INFLATIONARY SQUEEZE"
        geo_status = "Iran ceasefire proposal received (45-day). Trump ultimatum issued — answer due April 7."
    elif date == "2026-04-07":
        policy_state = "Easing (Hold)"
        policy_note = "Fed at 3.50-3.75%. No new data. May cut probability ~30% (declining as uncertainty rises)."
        risk_appetite = "Risk-Off (Geopolitical Re-escalation)"
        overall = "GEOPOLITICAL TENSION RESURGENT"
        geo_status = "Iran rejected Trump ultimatum. US additional naval assets deployed to Gulf. Standoff continues."
    elif date == "2026-04-08":
        policy_state = "Easing (Watch Inflation)"
        policy_note = "Fed at 3.50-3.75%. Ceasefire rally reduces recession risk; tariff inflation keeps cuts uncertain."
        risk_appetite = "Risk-On (Ceasefire Relief Rally)"
        overall = "TRANSITION: GEOPOLITICAL SHOCK → POST-CRISIS INFLATIONARY"
        geo_status = "45-day ceasefire SIGNED. Hormuz Protocol extended. Shipping lanes reopened. War premium unwinding."
    elif date == "2026-04-09":
        policy_state = "Easing (Hold — Dual Uncertainties)"
        policy_note = "Fed at 3.50-3.75%. Tariff pause reduces need for emergency cuts. May FOMC hold likely."
        risk_appetite = "Cautious Recovery (Dual Tailwinds)"
        overall = "POST-CRISIS RECOVERY — TARIFF INFLATION STRUCTURAL"
        geo_status = "Ceasefire holds day 2. Trump 90-day tariff pause (ex-China). China at 145% = persistent inflation."
    elif date == "2026-04-10":
        policy_state = "Easing (Hold)"
        policy_note = "Fed at 3.50-3.75%. Post-event consolidation; no new policy signals."
        risk_appetite = "Risk-On (Healthy Consolidation)"
        overall = "POST-CRISIS RECOVERY — INFLATIONARY REGIME CONFIRMED"
        geo_status = "Ceasefire day 3 — stable. Tariff pause holding. China 145% tariffs unchanged."
    elif date == "2026-04-11":
        policy_state = "Easing (Hold)"
        policy_note = "Fed silence period ahead of May FOMC. Rate at 3.50-3.75%."
        risk_appetite = "Risk-On (Stable Weekend)"
        overall = "POST-CRISIS RECOVERY — TARIFF INFLATION STRUCTURAL"
        geo_status = "Ceasefire day 4 holding. Hormuz tanker traffic normalizing. Oil $97."
    elif date == "2026-04-13":
        policy_state = "Easing (Hold)"
        policy_note = "Fed at 3.50-3.75%. Strong earnings reduce recession/emergency-cut pressure."
        risk_appetite = "Risk-On (Earnings Confirmation)"
        overall = "RECOVERY — EARNINGS UPSIDE + TARIFF INFLATION WATCHLIST"
        geo_status = "Ceasefire day 6 stable. Q1 earnings season: JPM, GS beat. Financials confirmed."
    else:  # Apr 14
        policy_state = "Easing (Hold — Inflation Vigilance)"
        policy_note = "Fed at 3.50-3.75%. Gold surge re-ignites inflation vigilance. May FOMC: hold with hawkish tilt."
        risk_appetite = "Risk-On with Inflation Vigilance"
        overall = "RECOVERY + GOLD BREAKOUT — TARIFF INFLATION REPRICING"
        geo_status = "Ceasefire day 7 stable. Gold +2.2% surge signals tariff inflation repricing underway."

    wti = p["WTI"]
    gold = p["GOLD_OZ"]
    spy = p["SPY"]
    spy_idx = spy * 10
    tny = p["TNX"]
    dxy = p["DXY"]

    prev_spy = {
        "2026-04-06": 658.5, "2026-04-07": 658.9, "2026-04-08": 659.2,
        "2026-04-09": 676.0, "2026-04-10": 679.9, "2026-04-11": 679.5,
        "2026-04-13": 679.5, "2026-04-14": 686.1,
    }.get(date, spy)

    spy_chg = ctx["spy_chg_pct"]

    events_md = "\n".join(f"- {e}" for e in ctx["key_events"])
    risk_watch_items = _macro_risk_watch(date)

    return f"""# Macro Analysis — {date}

> Delta #{d} from baseline 2026-04-05 | {ctx['day']} | {headline}

---

## 📊 MACRO REGIME CLASSIFICATION

| Factor | State | Confidence | Key Driver |
|--------|-------|------------|------------|
| **Growth** | Slowing | High | ISM Manufacturing contracting; tariff headwinds compressing margins |
| **Inflation** | Hot | High | WTI ${wti:.0f}/bbl + China tariffs (145%) driving persistent cost-push |
| **Policy** | {policy_state} | High | {policy_note} |
| **Risk Appetite** | {risk_appetite} | Medium | {ctx['geopolitical']} |

**Overall Regime**: {overall}
- Primary driver: Iran War ceasefire trajectory + US tariff regime (China 145%)
- Gold at ${gold:,}/oz reflects dual bid: geopolitical hedge + tariff inflation hedge
- SPY ${spy:.2f} (S&P ~{spy_idx:,.0f}) — {'weekend close' if is_weekend else f'{spy_chg:+.1f}% today'}

---

## Key Macro Data Points

### Growth Indicators
| Indicator | Latest | Prior | Trend | Signal |
|-----------|--------|-------|-------|--------|
| S&P 500 | {spy_idx:,.0f} | {prev_spy * 10:,.0f} | {'↔ Flat' if abs(spy_chg) < 0.3 else ('↑ Rising' if spy_chg > 0 else '↓ Falling')} | {'No major change' if abs(spy_chg) < 0.3 else ('Risk-on momentum' if spy_chg > 0.5 else ('Relief rally' if spy_chg > 0 else 'Caution'))} |
| GDP (Q1 2026) | ~1.3% est. | ~1.5% | Slowing | Tariffs + oil shock weighing on Q1 final read |
| ISM Manufacturing | ~47.8 est. | 48.5 | Contracting | Two months below 50; tariff uncertainty stalling orders |
| ISM Services | ~51.4 est. | 52.1 | Slowing | Services holding but losing momentum |
| Consumer Confidence | ~91 est. | 95 | Declining | Pump prices + tariff pass-through hitting sentiment |
| Initial Jobless Claims | ~228K est. | 225K | Edging up | Labor market resilient but tariff layoffs emerging |
| Atlanta Fed GDPNow (Q1) | ~1.1% est. | 1.5% | Below trend | Pre-tariff-pause estimate; upward revision likely |

### Inflation Indicators
| Indicator | Latest | Prior | Trend | Signal |
|-----------|--------|-------|-------|--------|
| CPI (YoY) | ~4.1% est. | 3.8% | Rising | Oil + tariffs accelerating pass-through |
| Core CPI | ~3.4% est. | 3.2% | Sticky | Tariff pass-through appearing in core goods |
| PCE (Fed preferred) | ~3.7% est. | 3.5% | Rising | Well above Fed's 2% target |
| WTI Crude | ~${wti:.0f}/bbl | ${wti + 3:.0f} | {'Falling — war premium unwinding' if wti < 105 else 'Elevated — war premium intact'} | {'Ceasefire normalizing supply fears' if wti < 105 else 'Conflict risk bid maintained'} |
| 5Y5Y Breakeven | ~2.8% est. | 2.6% | Rising | Tariff inflation priced in medium-term |
| Gold | ~${gold:,}/oz | ${gold - 35:,} | Rising | Dual bid: geopolitical + tariff inflation hedge |

### Policy / Central Bank
| Factor | Status | Signal |
|--------|--------|--------|
| Fed Funds Rate | 3.50–3.75% | Easing cycle paused — inflation above target |
| Next FOMC | May 7, 2026 | Hold expected; tariff pass-through monitored |
| Rate cut probability (June) | ~25% | Receding — tariff + oil inflation delays easing |
| Fed Balance Sheet | QT slowing | Passive runoff only |
| ECB | Cautious easing | European growth concerns; tariff spillover |
| BOJ | Slowly normalizing | Yen stabilized; yield cap removed |
| DXY | {dxy:.1f} | {'Below 100 — structural weakness' if dxy < 100 else 'Near 100 — key level'} |
| 10Y Treasury | {tny:.2f}% | {'Falling — growth concerns' if tny < 4.30 else 'Rising — inflation/risk-on'} |

---

## Geopolitical Risk Assessment

### Iran Ceasefire — Status Update ({date})
- **Status**: {geo_status}
- **Hormuz Protocol**: {'Active — shipping lanes fully open' if date >= '2026-04-08' else ('Under negotiation — proposal in hand' if date == '2026-04-06' else 'Standoff — ultimatum rejected')}
- **Oil impact**: WTI ~${wti:.0f} ({'includes ~${max(0, wti-95):.0f}/bbl residual war premium' if wti > 100 else 'war premium largely unwound; approaching pre-conflict range'})
- **Ceasefire durability**: {'45-day window — US and Iran both have domestic political constraints; extension possible if Hormuz traffic remains normal' if date >= '2026-04-08' else 'Unresolved — 50/50 binary outcome'}

### US-China Tariff Escalation
- **Status**: China tariffs at **145%** — EXCLUDED from 90-day pause
- **Impact**: Structural inflation source; US-China trade flows severely disrupted
- **Watch**: China retaliation risk — Beijing has not announced symmetric measures yet
- **Supply chain**: US firms accelerating "China+1" diversification; Southeast Asia benefiting

### Scenario Analysis (Current)
| Scenario | Probability | Market Impact |
|----------|-------------|--------------|
| Ceasefire holds 45 days | 65% | WTI $90-100; equities stable; Fed holds |
| Ceasefire collapses within 2 weeks | 20% | WTI $115-125; equity -5-8%; VIX >30 |
| China retaliates on tariffs | 15% | Gold +5-10%; Tech/retail -8%; inflation +0.5% |

---

## Today's Key Developments
{events_md}

---

## Risk Watch — Next 24–72 Hours
{risk_watch_items}

---

## Portfolio Implications
- **Cash/Short Duration** (BIL/SHY): Appropriate given inflation above target; 3.50-3.75% Fed rate floor intact
- **Gold** (IAU): Dual-bid thesis intact — geopolitical + tariff inflation; bias remains OW
- **Equities** (SPY): Risk-on regime confirmed but selective — quality over beta; avoid China-exposed names
- **Energy** (XLE): Downgrade bias as oil war premium unwinds; structural demand still present but pricing revision ongoing
"""


def _macro_risk_watch(date: str) -> str:
    watches = {
        "2026-04-06": """- **CRITICAL**: Trump ultimatum response from Iran due April 7 — binary risk event
- **HIGH**: DXY break below 100 — watch for further dollar weakness; EUR/USD testing 1.105
- **MEDIUM**: Fed rate data correction absorbed — markets should not be surprised by 3.50-3.75% reality
- **MEDIUM**: ISM Services print Monday — confirms or denies growth slowdown narrative""",
        "2026-04-07": """- **CRITICAL**: Iran ultimatum rejected — watch for US military response announcement
- **HIGH**: Risk of Hormuz blockade attempt — oil could spike to $125-130 if escalation
- **HIGH**: Dollar attempting recovery from below-100 — DXY 99.0 key support
- **MEDIUM**: Equity market binary — any ceasefire signal = +3-5% relief; escalation = -5-8%""",
        "2026-04-08": """- **HIGH**: Ceasefire signed — watch for renegade factions attempting spoiler attacks
- **HIGH**: Energy sector adjustment — XLE repricing from $60→$56 as war premium exits; watch overshooting
- **MEDIUM**: Oil $103 — further downside to $95-100 if ceasefire holds; bottom may be $92-95 range
- **MEDIUM**: Gold holding despite risk-on = tariff inflation bid confirmed; watch for push above $4,600""",
        "2026-04-09": """- **HIGH**: China tariff 145% — watch Beijing retaliation; Chinese officials scheduled to speak
- **HIGH**: Gold rising alongside equities — unusual dual bid; means tariff inflation is primary driver, not fear
- **MEDIUM**: 10Y yield at 4.36% — rising on tariff pause (growth positive = less need for Fed emergency cuts)
- **MEDIUM**: Tariff pause expires in 90 days — June 8 is the next decision point""",
        "2026-04-10": """- **MEDIUM**: Post-event consolidation — any shock could re-test 6,700 SPY support
- **MEDIUM**: Energy overshooting to downside — XLE at $57; $55 is key technical support
- **MEDIUM**: China retaliation risk still unresolved — holiday weekend creates information gap
- **LOW**: Federal Reserve silence period — next communication after May 7 FOMC""",
        "2026-04-11": """- **MEDIUM**: Ceasefire durability — first weekend test; any Iranian military movement is a red flag
- **MEDIUM**: Monday earnings (JPM, GS) — if miss, financials sector could reverse 2.5% rally
- **MEDIUM**: China tariff: 145% applies to new orders; watch first month's trade data for impact
- **LOW**: Gold consolidating at $4,540 — any tariff escalation news could push to $4,700""",
        "2026-04-13": """- **HIGH**: Earnings season pace — BofA, Morgan Stanley Tuesday; any miss breaks current positive momentum
- **MEDIUM**: Gold slightly off highs ($4,525) — stable above $4,500 confirms inflation floor
- **MEDIUM**: Energy (XLE $57) — watch $55 support; WTI pricing in demand softening post-war-premium
- **LOW**: Ceasefire day 6 stable — no new developments needed; status quo bullish""",
        "2026-04-14": """- **HIGH**: Gold surge to $4,625 (+2.2%) — inflation re-pricing underway; watch for continuation above $4,700
- **HIGH**: Tariff inflation repricing in motion — TIPS spreads widening; real rates falling
- **MEDIUM**: Energy (XLE -2%, WTI $94.5) — approaching oversold territory; $92-93 technical support
- **MEDIUM**: SPY at $694 = S&P ~6,944 — approaching 7,000 psychological level; resistance test ahead
- **LOW**: China tariff response still pending; Beijing signals strategic patience (not immediate retaliation)""",
    }
    return watches.get(date, "- Monitor ceasefire durability and tariff regime evolution\n- Watch China retaliation risk\n- Gold/inflation thesis tracking")


def gen_bonds(date: str, p: dict, ctx: dict) -> str:
    d = ctx["delta_n"]
    tny = p["TNX"]
    bil = p["BIL"]
    shy = p["SHY"]
    tlt = p["TLT"]
    spy_chg = ctx["spy_chg_pct"]
    is_weekend = (date == "2026-04-11")

    # Yield curve narrative evolution
    curve_narratives = {
        "2026-04-06": ("Flattening (flight-to-quality bid)", "DXY below 100 creating dollar weakness = bonds bid; ceasefire proposal adds uncertainty", "Hold"),
        "2026-04-07": ("Flattening (tension bid)", "Iran ultimatum rejection = risk-off = Treasuries bid; oil re-escalation", "Hold"),
        "2026-04-08": ("Bear flattening (risk-on)", "Ceasefire = equities rally = Treasuries sold; short end anchored by Fed hold", "Reduce duration"),
        "2026-04-09": ("Bear steepening (tariff inflation)", "Tariff pause signals: less emergency Fed cuts needed; 10Y rising on growth optimism", "Reduce duration"),
        "2026-04-10": ("Stable steepener", "Consolidation; 2s10s spread widening slightly as risk-on continues", "Neutral"),
        "2026-04-11": ("Stable steepener", "Weekend; no new data; 10Y slightly off peak as equity risk-on holds", "Neutral"),
        "2026-04-13": ("Slight bull flattening (earnings positive)", "Earnings beats reduce recession risk; 10Y dipped slightly", "Neutral — watch earnings pace"),
        "2026-04-14": ("Bull flattening (gold surge = duration bid)", "Gold surge signals inflation concern + flight-to-safety; 10Y pulled down", "Favor short duration — gold vs bonds tension"),
    }
    curve_shape, curve_driver, duration_call = curve_narratives.get(date, ("Uncertain", "Monitor", "Neutral"))

    # HY spread narrative
    hy_spread = {"2026-04-06": 380, "2026-04-07": 395, "2026-04-08": 360, "2026-04-09": 345,
                 "2026-04-10": 342, "2026-04-11": 340, "2026-04-13": 335, "2026-04-14": 332}.get(date, 350)

    events_md = "\n".join(f"- {e}" for e in ctx["key_events"][:3])

    return f"""# Bonds & Rates — {date}

> Delta #{d} from baseline 2026-04-05 | {ctx['day']} | {ctx['headline']}

---

## 📊 BONDS REGIME ASSESSMENT

| Factor | State | Driver |
|--------|-------|--------|
| **Duration Bias** | {duration_call} | {curve_driver} |
| **Curve Shape** | {curve_shape} | 2s10s spread: ~{tny - 4.50 + 0.65:.2f}% (inverted/flat) |
| **Credit Stress** | Moderate | HY spreads: ~{hy_spread}bps vs investment grade |
| **Fed Posture** | Hold at 3.50-3.75% | May FOMC: hold expected; inflation above target |

**Bias**: SHORT DURATION preferred. BIL/SHY outperform in this regime.

---

## Key Rate Data

| Instrument | Level | Change | Signal |
|------------|-------|--------|--------|
| Fed Funds | 3.50-3.75% | Unchanged | Floor for short rates; BIL/SHY protected |
| 10Y Treasury | {tny:.2f}% | {'+' if date in ['2026-04-08','2026-04-09'] else '-' if date == '2026-04-14' else '~'}{abs(tny - 4.28):.2f}% vs baseline | {curve_driver[:60]} |
| 2Y Treasury | ~3.95% est. | Anchored by Fed | Short end tethered to Fed funds |
| 2s10s Spread | ~{(tny - 3.95):.2f}% | {'Steepening' if date >= '2026-04-08' else 'Flat'} | {'Ceasefire + tariff pause = growth optimism' if date >= '2026-04-08' else 'Uncertainty = flat curve'} |
| IG Credit Spread | ~115bps | Tightening | Risk-on environment supporting credit |
| HY Credit Spread | ~{hy_spread}bps | {'Tightening' if date >= '2026-04-08' else 'Widening'} | {'Risk appetite improving' if date >= '2026-04-08' else 'Risk-off widening'} |
| TIPS 10Y Real | ~{tny - 2.8:.2f}% | Rising | {'Inflation expectations rising with tariffs' if date >= '2026-04-09' else 'Geopolitical uncertainty suppressing real rates'} |

---

## Position Performance

| ETF | Close | Change | Thesis Status |
|-----|-------|--------|---------------|
| BIL (1-3M T-bills) | ${bil:.2f} | Flat | ✅ Income floor; 4.5%+ annualized; holds in any scenario |
| SHY (1-3Y T-notes) | ${shy:.2f} | +{(shy - 82.28) * 100 / 82.28:.1f}% since baseline | ✅ Duration tame; benefits from any flight-to-quality bid |
| TLT (20Y+) | ${tlt:.2f} | Volatile | ⚠️ Long duration = sensitivity to inflation/tariff narrative |
| LQD (IG Corp) | ~$108 est. | Stable | ✅ Credit spreads tightening; IG companies insulated |

---

## Fed Watch

- **Rate**: 3.50-3.75% confirmed (March 18, 2026 FOMC decision)
- **Next FOMC**: May 7, 2026 — pre-meeting silence period active
- **Market pricing**: ~25% probability of June cut; declining as tariff inflation materializes
- **Key data ahead**: April CPI (May 13) — critical for Fed path; tariff pass-through will show
- **Balance sheet**: Passive QT only; no active bond buying

---

## Today's Key Developments (Bonds Lens)
{events_md}

---

## Bond Market Risk Watch
- **Tariff inflation risk**: China 145% tariffs = 6-12 month CPI lag; TIPS spreads widening
- **Duration**: Avoid TLT/long bonds; BIL/SHY optimal for 3.5-3.75% floor
- **Credit**: IG credit supported by earnings beats; HY tightening but watch over-leverage
- **Global**: ECB cautiously easing; BOJ normalizing — dollar weakness could persist if divergence continues

---

## Portfolio Implications
- **BIL**: HOLD — 4.5%+ income with no duration risk; ideal in stagflation-adjacent regime
- **SHY**: HOLD — modest duration with Fed floor protection; outperforms if any growth scare
- **TLT/Long bonds**: UNDERWEIGHT — tariff inflation + potential Fed delay = headwind to duration
- **Sector allocation**: Bonds as ballast only; equities and gold carrying alpha signal
"""


def gen_commodities(date: str, p: dict, ctx: dict) -> str:
    d = ctx["delta_n"]
    wti = p["WTI"]
    gold = p["GOLD_OZ"]
    iau = p["IAU"]
    xle = p["XLE"]

    oil_narrative = {
        "2026-04-06": ("Bid on tension; ceasefire proposal uncertainty", "Watch Trump ultimatum outcome — binary for oil", "$108-116"),
        "2026-04-07": ("Re-bid on ultimatum rejection; war premium returns", "Ultimatum rejected = escalation risk repriced", "$110-118"),
        "2026-04-08": ("SHARP DROP on ceasefire signing", "War premium partly unwinding; WTI testing $100 support", "$95-110"),
        "2026-04-09": ("Continued decline; tariff pause = demand revision", "Tariff pause signals global trade recovering; oil demand upward revision", "$95-103"),
        "2026-04-10": ("Stabilizing; finding equilibrium", "Supply normalized; demand revision upward from tariff pause", "$94-100"),
        "2026-04-11": ("Weekend stability; tanker traffic normalizing", "Hormuz fully open; analysts revising WTI target down to $90-100", "$93-99"),
        "2026-04-13": ("Stabilized; demand vs. supply in balance", "Earnings beats confirm economy healthy; oil demand expectations stable", "$94-100"),
        "2026-04-14": ("Further decline; overshooting post-ceasefire", "Supply fears fully unwound; watch demand side (tariff trade volume reduction)", "$90-97"),
    }
    oil_driver, oil_watch, oil_range = oil_narrative.get(date, ("Stable", "Monitor", "$95-105"))

    gold_narrative = {
        "2026-04-06": ("Rising — uncertainty bid", "DXY below 100 + ceasefire uncertainty = gold bid", "Bullish"),
        "2026-04-07": ("Rising — war premium reinforced", "Iran ultimatum rejection = geopolitical fear = gold bid", "Bullish"),
        "2026-04-08": ("Held/Rising despite risk-on", "Unusual: ceasefire signed but gold RISING = tariff inflation bid dominant", "Bullish — structural"),
        "2026-04-09": ("Rising — tariff inflation bid", "Gold up despite equities up = dual bid confirmed (gold ≠ just fear hedge now)", "Bullish — structural"),
        "2026-04-10": ("Slight pullback — consolidation", "Healthy digestion after $150+ run; tariff thesis intact", "Neutral/Bullish"),
        "2026-04-11": ("Stable at elevated levels", "Ceasefire stable; tariff inflation thesis in background bid", "Neutral/Bullish"),
        "2026-04-13": ("Slight dip on risk-on", "Earnings beats pulling capital to equities; gold minor rotation out", "Neutral — temporary dip"),
        "2026-04-14": ("SURGED +2.2% — breakout", "Tariff inflation repricing = gold breakout signal; targeting $4,750+", "Strongly Bullish"),
    }
    gold_driver, gold_watch, gold_bias = gold_narrative.get(date, ("Stable", "Monitor", "Neutral"))

    prev_gold = {"2026-04-06": 4400, "2026-04-07": 4430, "2026-04-08": 4475, "2026-04-09": 4510,
                 "2026-04-10": 4550, "2026-04-11": 4540, "2026-04-13": 4540, "2026-04-14": 4525}.get(date, gold - 30)
    gold_chg = f"+${gold - prev_gold:,}" if gold > prev_gold else f"-${prev_gold - gold:,}"

    return f"""# Commodities — {date}

> Delta #{d} from baseline 2026-04-05 | {ctx['day']} | {ctx['headline']}

---

## 📊 COMMODITIES REGIME ASSESSMENT

| Commodity | Bias | Driver | 24H Signal |
|-----------|------|--------|------------|
| **Crude Oil (WTI)** | {'Bearish (normalizing)' if wti < 105 else 'Bullish (war premium)'} | {oil_driver} | {oil_watch} |
| **Gold** | {gold_bias} | {gold_driver} | {gold_watch} |
| **Copper** | Neutral | China tariff = demand uncertainty | Watch China PMI for directional signal |
| **Natural Gas** | Neutral/Bullish | LNG exports to Europe still elevated | No major move; monitor Europe demand |
| **Silver** | Following gold | Gold/Silver ratio ~82x | Silver underperforming gold = risk-off silver bid lagging |

---

## Crude Oil (WTI)

| Metric | Level | vs Prior | Signal |
|--------|-------|----------|--------|
| WTI Spot | ~${wti:.0f}/bbl | {'vs $113 yesterday' if date == '2026-04-08' else 'vs prior day'} | {oil_driver} |
| Brent | ~${wti + 4:.0f}/bbl | Brent premium ~$4 | Geopolitical premium intact in Brent |
| War premium estimate | ~${max(0, wti - 85):.0f}/bbl | {'Unwinding' if wti < 105 else 'Intact'} | Baseline $85-90 when Hormuz fully clear |
| Target range | {oil_range} | — | Based on ceasefire trajectory |
| XLE (proxy) | ${xle:.2f} | — | Energy equities pricing {'normalization' if xle < 58 else 'war premium'} |

**Key driver**: {oil_driver}
**Watch**: {oil_watch}

---

## Gold

| Metric | Level | vs Prior | Signal |
|--------|-------|----------|--------|
| Gold Spot | ~${gold:,}/oz | {gold_chg} today | {gold_driver} |
| IAU ETF | ${iau:.2f} | — | IAU tracking gold direction |
| Gold/USD correlation | Negative | DXY {p['DXY']:.1f} | Dollar weakness = gold tailwind |
| Real rate impact | {p['TNX']:.2f}% - 2.8% = {p['TNX'] - 2.8:.2f}% real | {'Falling real rates = gold tailwind' if p['TNX'] < 4.35 else 'Rising real rates = headwind but narrative overrides'} | Tariff thesis overriding rate headwind |
| All-time high | ~$5,265/oz | -{(5265 - gold) / 5265 * 100:.0f}% from ATH | Structural regime change below ATH |
| Technical level | ${gold:,} | {'Key breakout above $4,600 if sustained' if gold > 4580 else 'Consolidating below $4,600 resistance'} | {'BREAKOUT WATCH' if gold > 4580 else 'Consolidation phase'} |

**Thesis**: Gold benefits from BOTH geopolitical uncertainty AND tariff inflation — dual bid mechanism. This is NOT just a fear trade; it is an inflation hedge with geopolitical overlay.

---

## Other Commodities

### Copper
- LME Copper: ~$9,850/ton (est.) — pressured by China tariff uncertainty
- China accounts for ~55% of global copper demand; 145% tariffs = demand uncertainty
- Watch: Chinese stimulus response — PMI data next week

### Natural Gas (Henry Hub)
- ~$3.80/MMBtu — elevated vs. summer norms; European LNG export demand sustained
- No major catalyst today; energy transition demand provides floor

---

## Today's Key Events
{chr(10).join(f'- {e}' for e in ctx['key_events'][:3])}

---

## Commodities Risk Watch
- **Oil**: {'Ceasefire durability — any collapse = WTI back to $115+' if wti > 100 else 'Demand softening risk — China tariff = trade volume drop = oil demand lower'}
- **Gold**: {gold_watch}
- **Copper**: China retaliation on tariffs could suppress commodity demand broadly
- **DXY impact**: Dollar at {p['DXY']:.1f} — further weakness = commodity tailwind (priced in USD)

---

## Portfolio Implications
- **IAU (Gold)**: HOLD OW — dual-bid thesis (geopolitical + tariff inflation) intact. Target $4,700-4,800 with tariff inflation materializing.
- **Energy (XLE/DBO)**: {'REDUCE — war premium unwinding + oil falling; XLE technical support at $55' if xle < 58 else 'HOLD — war premium intact; $60 key support; monitor ceasefire status'}
- **Base metals**: UNDERWEIGHT — China tariff uncertainty = demand compression
"""


def gen_forex(date: str, p: dict, ctx: dict) -> str:
    d = ctx["delta_n"]
    dxy = p["DXY"]

    dxy_narrative = {
        "2026-04-06": ("Below 100 — DOLLAR WEAKNESS MILESTONE", "DXY broke below 100 for first time since 2021; EUR/USD testing 1.105; structural dollar weakness signal", "Bullish gold/commodities, bearish US multinationals"),
        "2026-04-07": ("Near 100 — testing recovery", "DXY attempting recovery to 99-100 on Iran re-escalation fear; flight-to-dollar sentiment competing with structural weakness", "Tactical dollar bid; structural weakness intact"),
        "2026-04-08": ("Weakening — ceasefire risk-on", "Ceasefire risk-on = capital flows to global equities = dollar selling; EUR/USD ~1.108", "Dollar weakness accelerating"),
        "2026-04-09": ("Weak — tariff pause dollar positive partially offset", "Tariff pause = trade partners benefit = USD selling; but 90-day pause uncertainty limits EUR/USD upside", "Dollar soft; range-bound"),
        "2026-04-10": ("Stabilizing", "Post-event consolidation; DXY 98-99 establishing new range", "Dollar stable at new lower range"),
        "2026-04-11": ("Stable weekend", "No trading; DXY establishing 98-99 as new neutral zone", "Dollar range bound"),
        "2026-04-13": ("Slight strengthening — earnings dollar bid", "US earnings beats = capital inflows = mild dollar demand; DXY 98.5", "Dollar mild recovery"),
        "2026-04-14": ("Stable — gold breakout signal", "DXY stable near 98 as gold surges; weaker dollar + gold breakout = tariff inflation signal confirmed", "Dollar structurally weak; gold preferred store of value"),
    }
    dxy_status, dxy_driver, dxy_implication = dxy_narrative.get(date, ("Neutral", "Monitor", "Neutral"))

    eurusd = round(1.0 / (dxy / 100.0 * 1.058), 3)  # rough estimate
    usdjpy = round(dxy * 1.47, 1)  # rough estimate

    return f"""# Forex — {date}

> Delta #{d} from baseline 2026-04-05 | {ctx['day']} | {ctx['headline']}

---

## 📊 FOREX REGIME ASSESSMENT

| Currency | Bias | Key Driver | Level |
|----------|------|------------|-------|
| **USD (DXY)** | {'Bearish' if dxy < 99 else 'Neutral'} | {dxy_status} | {dxy:.1f} |
| **EUR/USD** | Bullish (vs USD) | USD weakness + ECB easing less hawkish than feared | ~{eurusd:.3f} est. |
| **USD/JPY** | Yen strengthening | BOJ normalization + risk-off yen bid | ~{usdjpy:.0f} est. |
| **USD/CNH** | CNH pressured | China tariffs 145% = capital outflow risk | ~7.25 est. |
| **USD/CHF** | CHF bid | Safe haven; ceasefire uncertainty | ~0.90 est. |
| **AUD/USD** | Volatile | China tariff = AUD (commodity currency) under pressure | ~0.62 est. |

**Overall Bias**: USD STRUCTURALLY WEAK. Dollar below 100 is a regime signal, not a tactical move.

---

## DXY Analysis

| Metric | Level | Signal |
|--------|-------|--------|
| DXY | {dxy:.1f} | {dxy_status} |
| Key level | 100.0 | Psychological support; now acting as resistance |
| 52W range | 98-110 | Currently near lower end of range |
| Driver | {dxy_driver[:80]} | — |

**Implications**: {dxy_implication}

---

## Major Pairs

### EUR/USD
- Level: ~{eurusd:.3f} est.
- Bias: {'Bullish — USD weakness primary driver' if dxy < 99 else 'Cautious — awaiting resolution'}
- ECB: Cautiously easing (25bps since Dec 2025); European growth concerns limit EUR strength
- Key level: 1.10 — now support; 1.12 is next target if DXY continues lower

### USD/JPY
- Level: ~{usdjpy:.0f} est.
- Bias: {'Yen strengthening — BOJ normalization + yen carry unwind' if dxy < 99 else 'Stable — balanced BOJ vs safety'}
- BOJ removing yield cap; Japanese investors repatriating assets
- Watch: Any BOJ rate hike accelerates yen rally (USD/JPY could test 145)

### USD/CNH
- Level: ~7.25 est. (PBOC managing depreciation)
- Tariff impact: China 145% tariffs = capital outflow pressure on CNH
- PBOC setting daily fixing to prevent disorderly depreciation
- Watch: PBOC response to tariff pressure — stimulus or depreciation?

### EM Currencies
- EM FX broadly benefiting from 90-day tariff pause (ex-China)
- MXN, BRL, INR all firmer on tariff relief
- China-exposed EM (KRW, TWD) under more pressure from 145% China tariffs

---

## Carry Trade Dynamics
- **Unwinding**: USD as funding currency (borrow USD, buy higher-yield EM) under pressure
- **Driver**: Dollar weakness makes USD carry more expensive (higher cost to maintain position)
- **Impact**: Further USD selling = EM currency strength = commodities bid (USD denominated)

---

## Today's Key Developments (Forex Lens)
{chr(10).join(f'- {e}' for e in ctx['key_events'][:3])}

---

## Forex Risk Watch
- **DXY {dxy:.1f}**: {'Below 100 structural break — if holds, commodities broadly supported; watch for dollar snap-back' if dxy < 100 else 'Near 100 key level — defense of 100 = dollar stabilization; break lower = commodity surge'}
- **CNH**: PBOC management key — disorderly CNH depreciation would destabilize EM broadly
- **JPY**: USD/JPY {usdjpy:.0f} — BOJ normalization pace matters; faster = yen rally
- **Tariff FX impact**: 90-day pause benefits trade partners (MXN, EUR, KRW); China excluded; CNH most at risk

---

## Portfolio Implications
- **USD assets**: DXY weakness = headwind to USD-denominated asset performance in global terms
- **Gold**: DXY below 100 = gold structural tailwind; IAU OW confirmed
- **International equities** (EFA, EM ex-China): Tariff pause + dollar weakness = double positive for international
- **Commodity currencies**: AUD pressured by China exposure; BRL/MXN benefiting from tariff pause
"""


def gen_crypto(date: str, p: dict, ctx: dict) -> str:
    d = ctx["delta_n"]
    btc = p["BTC"]
    eth = p["ETH"]

    btc_narrative = {
        "2026-04-06": ("Neutral — ranging on uncertainty", "Markets flat pending Iran ultimatum outcome; crypto tracking equities risk sentiment", "Watch $82K support"),
        "2026-04-07": ("Risk-off — selling on Iran ultimatum rejection", "BTC correlation with risk-on equities; ultimatum rejection = sell", "Key support $80K"),
        "2026-04-08": ("Risk-on rally — ceasefire catalyst", "Ceasefire signed = broad risk-on = BTC +6.5%; crypto tracking equity rally", "Resistance $90K"),
        "2026-04-09": ("Risk-on continuation + tariff pause", "Tariff pause = additional risk catalyst; BTC consolidating gains above $88K", "Bull momentum intact"),
        "2026-04-10": ("Consolidating post-rally", "BTC slight pullback after two-day run; healthy retest of $87-89K range", "Support $85K"),
        "2026-04-11": ("Weekend consolidation", "Lower volume weekend; institutional investors holding positions; DeFi activity stable", "Support $85K"),
        "2026-04-13": ("Risk-on momentum — earnings catalyst", "Q1 earnings beats = broad risk appetite = BTC reaching toward $92K", "Resistance $95K"),
        "2026-04-14": ("Risk-on + gold breakout = crypto bid", "Gold and crypto both up = macro hedge + risk-on dual bid", "Targeting $95-100K"),
    }
    btc_driver, btc_desc, btc_watch = btc_narrative.get(date, ("Neutral", "Ranging", "Monitor"))

    prev_btc = {"2026-04-06": 84000, "2026-04-07": 84000, "2026-04-08": 82200,
                "2026-04-09": 87500, "2026-04-10": 89200, "2026-04-11": 88400,
                "2026-04-13": 87800, "2026-04-14": 91000}.get(date, btc - 1500)
    btc_chg = f"+${(btc - prev_btc):,.0f}" if btc > prev_btc else f"-${(prev_btc - btc):,.0f}"

    return f"""# Crypto & Digital Assets — {date}

> Delta #{d} from baseline 2026-04-05 | {ctx['day']} | {ctx['headline']}

---

## 📊 CRYPTO REGIME ASSESSMENT

| Asset | Bias | Price | Driver |
|-------|------|-------|--------|
| **Bitcoin (BTC)** | {'Bullish' if btc > 86000 else 'Neutral/Cautious'} | ~${btc:,.0f} | {btc_driver} |
| **Ethereum (ETH)** | {'Bullish' if eth > 1600 else 'Neutral'} | ~${eth:,.0f} | Following BTC; DeFi activity stable |
| **Crypto Fear & Greed** | {'Greed' if btc > 88000 else 'Fear/Neutral'} | ~{'65/100 est.' if btc > 88000 else '45/100 est.'} | {'Risk-on sentiment; capital rotating into risk assets' if btc > 88000 else 'Uncertainty; institutional caution'} |
| **BTC Dominance** | ~58% | Rising | BTC leading altcoin cycle; ETH ratio lagging |
| **Crypto/Gold correlation** | {'Positive' if date >= '2026-04-08' else 'Negative'} | — | {'Both as macro hedges; correlation = inflation narrative' if date >= '2026-04-08' else 'Inverse: crypto risk-off while gold hedges'} |

**Overall Crypto Bias**: {'BULLISH — dual catalysts (geopolitical relief + risk-on) supporting crypto' if btc > 88000 else 'CAUTIOUS — macro uncertainty limits crypto upside; wait for resolution'}

---

## Bitcoin (BTC)

| Metric | Level | Change | Signal |
|--------|-------|--------|--------|
| BTC Price | ${btc:,.0f} | {btc_chg} today | {btc_driver} |
| 30-day Realized Vol | ~65% | Elevated | High vol regime; position sizing important |
| ETF Inflows (IBIT) | {'Inflows — risk-on' if btc > 87000 else 'Neutral/outflows'} | Daily est. | Bitcoin ETF flows tracking sentiment |
| Mining hash rate | ~750 EH/s est. | Stable | Network security intact; miner margins healthy at ~$84K+ |
| Key support | $82,000 | — | Bull/bear dividing line |
| Key resistance | $95,000 | — | Next breakout target |

**Description**: {btc_desc}
**Watch**: {btc_watch}

---

## Ethereum (ETH)

| Metric | Level | Signal |
|--------|-------|--------|
| ETH Price | ${eth:,.0f} | Following BTC; underperforming on relative basis |
| BTC/ETH ratio | {btc/eth:.1f}x | ETH underperforming vs BTC |
| ETH Staking yield | ~3.8% | Stable; institutional staking demand |
| L2 activity | High | Arbitrum, Base driving transaction volume |
| DeFi TVL | ~$110B est. | Stable; no major depegs or exploits |

---

## Macro Overlay

- **Tariff impact**: Crypto uncorrelated to tariffs directly; affected via risk-sentiment
- **Dollar weakness** (DXY {p['DXY']:.1f}): Dollar weak = commodity and alternative assets bid = crypto tailwind
- **Gold correlation**: {'Gold and BTC both rising = macro inflation hedge narrative strong' if date >= '2026-04-09' else 'Watch gold/BTC relationship — if diverging, risk appetite is the driver, not macro'}
- **Institutional flows**: Bitcoin ETF daily flows (IBIT) positive on risk-on days; monitoring

---

## Today's Key Developments (Crypto Lens)
{chr(10).join(f'- {e}' for e in ctx['key_events'][:3])}

---

## Crypto Risk Watch
- **{'BTC above $90K = bull case confirming; target $100K before next consolidation' if btc > 88000 else 'BTC needs to hold $82K; break lower = test $75K support zone'}**
- **Regulatory**: No new US crypto regulation this week; SEC ETF approval posture unchanged
- **DXY**: Dollar weakness at {p['DXY']:.1f} = crypto tailwind persists as long as DXY stays below 100
- **Correlation flip**: If gold surges and BTC stays flat, crypto is in risk-asset mode not inflation-hedge mode

---

## Portfolio Implications
- **BTC/Crypto**: Not in current portfolio but on watchlist; monitor for entry at $80K support
- **Gold vs Crypto**: IAU (gold) preferred at this stage — lower volatility inflation hedge with portfolio management mandate
- **IBIT/ETF flows**: Use as sentiment indicator for broader risk appetite
"""


def gen_international(date: str, p: dict, ctx: dict) -> str:
    d = ctx["delta_n"]
    efa_level = p.get("EFA", 75.0)  # fallback

    intl_narrative = {
        "2026-04-06": ("Cautiously positive — ceasefire proposal relief", "Asian markets mixed; European markets slightly positive on ceasefire proposal; DXY weakness helps EM"),
        "2026-04-07": ("Risk-off — ultimatum rejection pressure", "Asia down on Iran news; Europe cautious; EM selling on risk-off"),
        "2026-04-08": ("Strong rally — ceasefire global relief", "Global equity rally; Nikkei +2%, DAX +2.5%; EM ex-China leading; EFA +2%+ implied"),
        "2026-04-09": ("Bifurcated — tariff pause benefits non-China", "EFA (developed ex-US) rallied; EM ex-China benefiting from 90-day pause; China markets lagging 145% tariff"),
        "2026-04-10": ("Post-event stabilization", "International markets consolidating after 2-day rally; Nikkei, DAX holding gains"),
        "2026-04-11": ("Weekend review", "Asian markets closed; European markets closed; futures stable"),
        "2026-04-13": ("Positive — US earnings read-through", "US earnings beats lifting global sentiment; EFA +0.5%; DXY weakness = non-USD asset boost"),
        "2026-04-14": ("Positive — dollar weakness = international tailwind", "Weak dollar + earnings season = international developed markets outperforming; EFA +1%"),
    }
    intl_status, intl_driver = intl_narrative.get(date, ("Neutral", "Monitor"))

    china_note = {
        "2026-04-06": "Chinese markets: mixed — tariffs at 145% already priced; ceasefire not directly relevant",
        "2026-04-07": "Chinese markets: risk-off selling; 145% tariff = structural headwind",
        "2026-04-08": "China markets: outperformed on ceasefire news (risk-on) but tariff 145% limits upside",
        "2026-04-09": "China EXCLUDED from 90-day tariff pause — Shanghai Composite underperformed global rally; CNH pressured",
        "2026-04-10": "China: lagging international peers; PBOC managing CNH; stimulus speculation elevated",
        "2026-04-11": "China: underperforming the week; 145% tariff = structural drag; watch PBOC announcements",
        "2026-04-13": "China: mixed; PBOC injecting liquidity; market awaiting policy response to 145% tariffs",
        "2026-04-14": "China: still underperforming; CNH pressured; PBOC not yet signaling major stimulus",
    }

    return f"""# International & Emerging Markets — {date}

> Delta #{d} from baseline 2026-04-05 | {ctx['day']} | {ctx['headline']}

---

## 📊 INTERNATIONAL REGIME ASSESSMENT

| Region | Bias | Key Driver | Signal |
|--------|------|------------|--------|
| **Europe (DAX/FTSE)** | {'Bullish' if date >= '2026-04-08' else 'Cautious'} | {'Ceasefire + tariff pause benefits' if date >= '2026-04-08' else 'Awaiting Iran/tariff resolution'} | {intl_status} |
| **Japan (Nikkei)** | Bullish (selective) | BOJ normalization + DXY weak | Yen strengthening = headwind for exporters |
| **China (Shanghai/CSI)** | Bearish | 145% US tariffs — EXCLUDED from pause | Structural headwind; PBOC managing |
| **EFA (Dev ex-US)** | {'Bullish' if date >= '2026-04-08' else 'Neutral'} | Tariff pause + dollar weakness = double positive | {intl_driver[:60]} |
| **EM ex-China** | Bullish (conditional) | Tariff pause + DXY weak | MXN, INR, BRL outperforming |
| **EM China** | Bearish | 145% tariffs + CNH pressure | PBOC managing depreciation |

---

## Regional Summary

### Europe
- **Status**: {intl_status}
- **DAX**: {'Rallying on risk-on; German auto sector benefits from tariff pause' if date >= '2026-04-08' else 'Cautious; energy costs still elevated but ceasefire helps'}
- **ECB**: Cautiously easing; European growth ~1.2% est. for 2026 — tariff pause gives breathing room
- **EUR/USD**: ~{round(1.0/(p['DXY']/100.0 * 1.058), 3):.3f} — dollar weakness = EUR/USD appreciation = mild headwind to EU exporters

### Japan
- **Nikkei**: {'Up on risk-on; yen strengthening creates cross-current for exporters' if date >= '2026-04-08' else 'Cautious; BOJ normalization + geopolitical uncertainty'}
- **BOJ**: Continuing slow normalization; yield cap removed; yen carry unwind in progress
- **Key risk**: Faster-than-expected BOJ hikes could spike yen to 140/USD = Nikkei headwind

### China
- **Status**: {china_note.get(date, 'Structural headwind from 145% tariffs')}
- **PBOC response**: Managing CNH depreciation daily; liquidity injections but no major stimulus yet
- **Trade impact**: US-China container shipping bookings down significantly; supply chain restructuring
- **Watch**: Beijing stimulus announcement — any major package = 3-5% Shanghai rally signal

### Emerging Markets (ex-China)
- **India**: Benefiting from "China+1" manufacturing diversification; Sensex near highs
- **Mexico**: MXN strengthening; USMCA still intact; near-shoring trend accelerating
- **Brazil**: BRL up; commodity exports support; tariff pause helps EM credit spreads
- **Southeast Asia**: Vietnam, Thailand benefiting most from China+1 supply chain shifts

---

## Today's Key Developments (International Lens)
{chr(10).join(f'- {e}' for e in ctx['key_events'][:3])}

---

## International Risk Watch
- **China retaliation**: 145% tariffs without symmetric response is unusual; Beijing typically responds; watch for announcement
- **DXY {p['DXY']:.1f}**: Dollar below 100 = tailwind for non-USD assets; USD strength reversal would hurt EM
- **Japan yen**: USD/JPY ~{round(p['DXY'] * 1.47, 0):.0f} — if reaches 140, Nikkei exporters pressure
- **EFA vs SPY**: {'International outperforming on tariff pause + dollar weakness — watch for continued trend' if date >= '2026-04-08' else 'International underperforming; resolution of Iran/tariff needed'}

---

## Portfolio Implications
- **EFA**: {'ADD — tariff pause (90-day) + DXY below 100 = international developed markets double positive; allocation increase justified' if date >= '2026-04-09' else 'WATCH — await resolution before adding; binary risk unresolved'}
- **China exposure**: AVOID direct China ETFs (FXI, KWEB) — 145% tariffs = structural headwind
- **EM ex-China**: Selective; India (INDA) and Mexico (EWW) have specific tailwinds
- **Currency hedge**: Consider unhedged positions given DXY structural weakness
"""


def gen_us_equities(date: str, p: dict, ctx: dict) -> str:
    d = ctx["delta_n"]
    spy = p["SPY"]
    qqq = p["QQQ"]
    iwm = p["IWM"]
    xlk = p["XLK"]
    xlv = p["XLV"]
    xle = p["XLE"]
    xlf = p["XLF"]
    xlp = p["XLP"]
    xly = p["XLY"]
    spy_chg = ctx["spy_chg_pct"]
    is_weekend = (date == "2026-04-11")

    # Market character assessment
    market_char = {
        "2026-04-06": "Flat/Range — binary event pending (Iran ultimatum due Tuesday)",
        "2026-04-07": "Flat with downside bias — ultimatum rejected; risk-off undertone",
        "2026-04-08": "STRONG RALLY — ceasefire signed; risk-on across sectors; +2.5%",
        "2026-04-09": "Continued advance — tariff pause adds to ceasefire rally; +0.6%",
        "2026-04-10": "Consolidation — healthy digestion; flat after strong 3-day run",
        "2026-04-11": "Weekend — no trading; holding 3-day gains",
        "2026-04-13": "Earnings-led advance — JPM/GS beat; SPY +1.0%; financials led",
        "2026-04-14": "Broad advance — more earnings beats; SPY +1.2%; tech + financials led",
    }

    sector_scorecard = {
        "2026-04-06": [
            ("Technology", "XLK", f"${xlk:.2f}", "Neutral/OW", "Medium", "Flat on uncertainty; NVDA/MSFT watching macro"),
            ("Healthcare", "XLV", f"${xlv:.2f}", "OW", "High", "Defensive bid persists; MRK, UNH holding"),
            ("Energy", "XLE", f"${xle:.2f}", "Cautious OW", "Low", "War premium intact but ceasefire proposal = risk"),
            ("Financials", "XLF", f"${xlf:.2f}", "Neutral", "Medium", "Awaiting Q1 earnings (Apr 13+)"),
            ("Cons Staples", "XLP", f"${xlp:.2f}", "OW", "Medium", "Defensive; inflation pass-through holding"),
            ("Cons Disc", "XLY", f"${xly:.2f}", "Neutral", "Medium", "Consumer confidence declining; oil-cost drag"),
        ],
        "2026-04-08": [
            ("Technology", "XLK", f"${xlk:.2f}", "OW", "High", "Led rally +3.1%; AI capex thesis intact"),
            ("Healthcare", "XLV", f"${xlv:.2f}", "OW", "High", "+2.1%; defensives rallied with market"),
            ("Energy", "XLE", f"${xle:.2f}", "UW", "High", "LAGGED -3.5%; war premium unwinding = earnings headwind"),
            ("Financials", "XLF", f"${xlf:.2f}", "OW", "Medium", "+2.6%; earnings optimism (Apr 13+)"),
            ("Cons Staples", "XLP", f"${xlp:.2f}", "Neutral", "Medium", "+1.9%; less defensive demand as risk-on"),
            ("Cons Disc", "XLY", f"${xly:.2f}", "OW", "Medium", "+2.8%; relief on lower oil = consumer spending"),
        ],
        "2026-04-13": [
            ("Technology", "XLK", f"${xlk:.2f}", "OW", "High", "+2.5% from Apr 9; AI cycle intact"),
            ("Healthcare", "XLV", f"${xlv:.2f}", "Neutral", "Medium", "Slight lag on risk-on; defensive rotation out"),
            ("Energy", "XLE", f"${xle:.2f}", "UW", "High", "Continued decline; WTI $97 = earnings compression"),
            ("Financials", "XLF", f"${xlf:.2f}", "OW", "High", "JPM/GS BEAT; sector re-rating upward"),
            ("Cons Staples", "XLP", f"${xlp:.2f}", "Neutral", "Low", "Underperforming as risk-on dominates"),
            ("Cons Disc", "XLY", f"${xly:.2f}", "OW", "Medium", "Lower oil + improving consumer; +0.7% on earnings"),
        ],
        "2026-04-14": [
            ("Technology", "XLK", f"${xlk:.2f}", "OW", "High", "XLK +1.6%; Microsoft, NVDA leading tech cycle"),
            ("Healthcare", "XLV", f"${xlv:.2f}", "Neutral/OW", "Medium", "BofA results boosted financial sector read-through"),
            ("Energy", "XLE", f"${xle:.2f}", "UW", "High", "-2.0%; WTI $94.5 = post-war-premium overshoot risk"),
            ("Financials", "XLF", f"${xlf:.2f}", "OW", "High", "BofA +8% EPS beat; MS wealth management strong"),
            ("Cons Staples", "XLP", f"${xlp:.2f}", "Neutral", "Low", "Defensive demand low in risk-on regime"),
            ("Cons Disc", "XLY", f"${xly:.2f}", "OW", "High", "+2% on day; lower oil + earnings confidence"),
        ],
    }
    # Default scorecard for other dates
    default_scorecard = [
        ("Technology", "XLK", f"${xlk:.2f}", "OW", "Medium", "Watching macro resolution"),
        ("Healthcare", "XLV", f"${xlv:.2f}", "OW", "Medium", "Defensive bid in uncertain market"),
        ("Energy", "XLE", f"${xle:.2f}", "Cautious OW", "Medium", "War premium trajectory key"),
        ("Financials", "XLF", f"${xlf:.2f}", "Neutral", "Low", "Ahead of Q1 earnings season"),
        ("Cons Staples", "XLP", f"${xlp:.2f}", "OW", "Medium", "Inflation pass-through defensive"),
        ("Cons Disc", "XLY", f"${xly:.2f}", "Neutral", "Medium", "Consumer confidence watch"),
    ]
    scorecard = sector_scorecard.get(date, default_scorecard)

    breadth_note = {
        "2026-04-06": "Breadth: Narrow — only 55% of S&P500 names advancing; selectivity required",
        "2026-04-07": "Breadth: Narrow — risk-off pressure; only 48% advancing",
        "2026-04-08": "Breadth: BROAD — 82% of S&P500 advancing; genuine risk-on; leadership across sectors",
        "2026-04-09": "Breadth: Broad — 75% advancing; ceasefire + tariff pause holding",
        "2026-04-10": "Breadth: Moderate — 62% advancing; consolidation healthy",
        "2026-04-11": "Breadth: N/A — weekend",
        "2026-04-13": "Breadth: 70% advancing — earnings-led breadth; financials broad; some defensive lagging",
        "2026-04-14": "Breadth: 72% advancing — broad-based; tech + financials + discretionary leading",
    }.get(date, "Breadth: Moderate — mixed signals")

    scorecard_rows = "\n".join(
        f"| {sec} | {etf} | {price} | {bias} | {conf} | {driver} |"
        for sec, etf, price, bias, conf, driver in scorecard
    )

    return f"""# US Equities — {date}

> Delta #{d} from baseline 2026-04-05 | {ctx['day']} | {ctx['headline']}

---

## 📊 US EQUITY REGIME ASSESSMENT

| Index | Level | Day Change | Signal |
|-------|-------|-----------|--------|
| **S&P 500 (SPY)** | ${spy:.2f} | {spy_chg:+.1f}% | {'No trading' if is_weekend else market_char.get(date, 'Mixed')} |
| **NASDAQ 100 (QQQ)** | ${qqq:.2f} | {'N/A' if is_weekend else f'{(qqq/588.5 - 1)*100:+.1f}% since Apr 6'} | Tech-heavy; AI capex intact |
| **Russell 2000 (IWM)** | ${iwm:.2f} | {'N/A' if is_weekend else f'{(iwm/252.36 - 1)*100:+.1f}% since Apr 6'} | Small cap lagging large cap; tariff exposure higher |
| **VIX** | {'N/A' if is_weekend else ('~18 est.' if date >= '2026-04-08' else '~24 est.')} | — | {'Elevated fear' if date <= '2026-04-07' else 'Normalizing'} |

**Market Character**: {market_char.get(date, 'Mixed — monitoring')}
{breadth_note}

---

## Sector Scorecard — {date}

| Sector | ETF | Price | Bias | Confidence | Key Driver |
|--------|-----|-------|------|------------|------------|
{scorecard_rows}

---

## Factor Performance

| Factor | ETF | Bias | Rationale |
|--------|-----|------|-----------|
| Quality | QUAL | OW | {'Earnings beats = quality factor confirmed' if date >= '2026-04-13' else 'Defensive; outperforming in uncertain macro'} |
| Low Vol | USMV | Neutral | {'Risk-on reduces defensive bid' if date >= '2026-04-08' else 'Bid in risk-off environment'} |
| Momentum | MTUM | {'OW' if date >= '2026-04-08' else 'Neutral'} | {'Post-ceasefire momentum building' if date >= '2026-04-08' else 'Uncertainty stalling momentum factor'} |
| Value | VTV | Neutral | Financials value; energy value challenged by oil decline |
| Growth | VUG | {'OW' if date >= '2026-04-08' else 'Neutral'} | {'Risk-on = growth factor outperforming' if date >= '2026-04-08' else 'Cautious; high valuations in uncertain regime'} |
| Small Cap | IWM | UW | Tariff exposure higher; dollar weakness helps partially |

---

## Market Structure

- **SPY level**: ${spy:.2f} — S&P ~{spy * 10:,.0f}
- **Post-baseline performance**: {(spy - 658.93) / 658.93 * 100:+.1f}% from Apr 5 baseline
- **Key support**: $670 (SPY) — previous resistance, now support post-ceasefire
- **Key resistance**: $700 (SPY) — psychological and technical round number
- **Technicals**: {'Above 20-day SMA; MACD positive; RSI ~62 — healthy range' if spy > 670 else 'Testing 20-day SMA; MACD cautious; RSI ~50 — uncertainty'}

---

## Today's Key Developments (Equities Lens)
{chr(10).join(f'- {e}' for e in ctx['key_events'][:4])}

---

## Equities Risk Watch
- **{'Ceasefire durability: Any reversal = SPY -5-8%; VIX back to 25+' if date <= '2026-04-10' else 'Earnings pace: Any major miss from mega-cap would break current momentum'}**
- **China tariffs (145%)**: Tech (AAPL, semiconductor supply chain) + retail (importers) at risk of cost guidance revision
- **Energy sector**: XLE at ${xle:.2f} — watch $55 technical support; below = momentum selling
- **SPY $700**: Round-number resistance approaching; profit-taking risk near 7,000 S&P

---

## Portfolio Implications
- **SPY holding (15% allocation)**: Thesis intact — risk-on regime confirmed; earnings season supporting
- **Sector tilts**: OVERWEIGHT quality/tech; UNDERWEIGHT energy/small cap; NEUTRAL financials
- **Add on dips**: Any pullback to SPY $670-675 = add opportunity
- **Exit watch**: SPY below $650 = re-evaluate thesis; $640 = stop-loss level
"""


# ---------------------------------------------------------------------------
# Sector generators (concise but complete — 11 sectors)
# ---------------------------------------------------------------------------

SECTOR_CONFIG = {
    "technology": {
        "etf": "XLK", "key": "XLK", "name": "Technology",
        "holdings": ["AAPL", "MSFT", "NVDA", "META", "GOOGL"],
        "baseline_bias": "OW", "baseline_driver": "AI capex cycle; cloud spending",
    },
    "healthcare": {
        "etf": "XLV", "key": "XLV", "name": "Healthcare",
        "holdings": ["UNH", "LLY", "MRK", "ABBV", "JNJ"],
        "baseline_bias": "OW", "baseline_driver": "Defensive; GLP-1 drug cycle",
    },
    "energy": {
        "etf": "XLE", "key": "XLE", "name": "Energy",
        "holdings": ["XOM", "CVX", "SLB", "COP"],
        "baseline_bias": "OW (war premium)", "baseline_driver": "Iran War oil premium",
    },
    "financials": {
        "etf": "XLF", "key": "XLF", "name": "Financials",
        "holdings": ["JPM", "BAC", "WFC", "GS", "MS"],
        "baseline_bias": "Neutral", "baseline_driver": "Rate sensitivity; Q1 earnings",
    },
    "consumer-staples": {
        "etf": "XLP", "key": "XLP", "name": "Consumer Staples",
        "holdings": ["PG", "KO", "PEP", "WMT", "COST"],
        "baseline_bias": "OW", "baseline_driver": "Defensive; inflation pass-through",
    },
    "consumer-disc": {
        "etf": "XLY", "key": "XLY", "name": "Consumer Discretionary",
        "holdings": ["AMZN", "TSLA", "HD", "NKE", "MCD"],
        "baseline_bias": "Neutral", "baseline_driver": "Consumer confidence declining",
    },
    "industrials": {
        "etf": "XLI", "key": "XLI", "name": "Industrials",
        "holdings": ["GE", "CAT", "HON", "UPS", "LMT"],
        "baseline_bias": "Neutral", "baseline_driver": "Tariff uncertainty on supply chains",
    },
    "utilities": {
        "etf": "XLU", "key": "XLU", "name": "Utilities",
        "holdings": ["NEE", "DUK", "SO", "AEP"],
        "baseline_bias": "Neutral", "baseline_driver": "Rate-sensitive; AI power demand",
    },
    "materials": {
        "etf": "XLB", "key": "XLB", "name": "Materials",
        "holdings": ["LIN", "APD", "SHW", "FCX", "NEM"],
        "baseline_bias": "Neutral", "baseline_driver": "China tariff = copper/metals demand uncertainty",
    },
    "real-estate": {
        "etf": "XLRE", "key": "XLRE", "name": "Real Estate",
        "holdings": ["AMT", "PLD", "EQIX", "O"],
        "baseline_bias": "UW", "baseline_driver": "Rate-sensitive; 10Y yield elevated",
    },
    "comms": {
        "etf": "XLC", "key": "XLC", "name": "Communications",
        "holdings": ["GOOGL", "META", "NFLX", "DIS", "VZ"],
        "baseline_bias": "OW", "baseline_driver": "AI-adjacent; digital advertising resilient",
    },
}


def gen_sector(seg: str, date: str, p: dict, ctx: dict) -> str:
    d = ctx["delta_n"]
    cfg = SECTOR_CONFIG.get(seg, {})
    etf_ticker = cfg.get("key", "XLK")
    etf_price = p.get(etf_ticker, 50.0)
    sec_name = cfg.get("name", seg.title())
    sec_etf = cfg.get("etf", "XLK")
    holdings_str = ", ".join(cfg.get("holdings", []))

    # Derive bias based on date and sector
    biases = _sector_day_bias(seg, date, p, ctx)

    events_short = ctx["key_events"][:2]

    return f"""# {sec_name} Sector — {date}

> Delta #{d} from baseline 2026-04-05 | {ctx['day']} | {ctx['headline']}

---

## 📊 SECTOR ASSESSMENT

| Metric | Value | Signal |
|--------|-------|--------|
| **ETF** | {sec_etf} @ ${etf_price:.2f} | {biases['direction']} |
| **Bias** | {biases['bias']} | {biases['conf']} confidence |
| **vs S&P today** | {biases['rel_perf']} | {biases['char']} |
| **Key driver** | {biases['driver']} | — |
| **Macro regime alignment** | {biases['macro_align']} | — |

---

## Sector Performance & Developments

### What Changed Since Baseline
{biases['what_changed']}

### Key Holdings Status
- **Tracked names**: {holdings_str}
- **Overall**: {biases['holdings_note']}

### Macro Cross-Reference
- **Growth regime** (Slowing): {biases['growth_note']}
- **Inflation regime** (Hot/Rising): {biases['inflation_note']}
- **Policy regime** (Easing): {biases['policy_note']}
- **Geopolitical** (Ceasefire trajectory): {biases['geo_note']}

---

## Today's Catalysts
{chr(10).join(f'- {e}' for e in events_short)}
- **Sector-specific**: {biases['sector_catalyst']}

---

## Sub-Sector Reads

| Sub-Sector | Bias | Key Driver |
|------------|------|------------|
{biases['subsectors']}

---

## Risk Watch
- **Upside**: {biases['upside_risk']}
- **Downside**: {biases['downside_risk']}
- **Key level**: {sec_etf} ${etf_price:.2f} — {'technical support' if etf_price > 55 else 'watch $55 floor'}

---

## Portfolio Implication
{biases['portfolio_note']}
"""


def _sector_day_bias(seg: str, date: str, p: dict, ctx: dict) -> dict:
    """Return sector-specific bias metrics for a given date."""
    spy_chg = ctx["spy_chg_pct"]
    etf_ticker = SECTOR_CONFIG.get(seg, {}).get("key", "XLK")
    etf_price = p.get(etf_ticker, 50.0)

    # Default structure
    b = {
        "bias": "Neutral", "conf": "Medium", "direction": "↔ Flat",
        "rel_perf": "In-line with market", "char": "Sector neutral",
        "driver": "Macro resolution in progress", "macro_align": "Partially aligned",
        "what_changed": "- No major sector-specific developments since baseline\n- Monitoring macro resolution",
        "holdings_note": "Holdings stable; no major moves",
        "growth_note": "Neutral impact on sector",
        "inflation_note": "Neutral impact on sector",
        "policy_note": "Neutral impact on sector",
        "geo_note": "Neutral impact on sector",
        "sector_catalyst": "No major sector-specific catalyst today",
        "subsectors": "| All sub-sectors | Neutral | Awaiting macro clarity |",
        "upside_risk": "Macro resolution + sector rotation",
        "downside_risk": "Continued macro uncertainty",
        "portfolio_note": "NEUTRAL — no action required; monitoring.",
    }

    if seg == "technology":
        if date <= "2026-04-07":
            b.update({"bias": "OW", "conf": "High", "direction": "↔ Flat in uncertainty",
                      "driver": "AI capex cycle intact; flat on macro uncertainty",
                      "what_changed": "- NVDA, MSFT flat — AI thesis intact but macro uncertainty stalling near-term momentum\n- Cloud spending unaffected by geopolitical events\n- DXY weakness = earnings translation benefit for US tech (international revenues)",
                      "sector_catalyst": "No sector catalyst; waiting for macro resolution",
                      "subsectors": "| Cloud/SaaS | OW | AI capex + consumption unchanged |\n| Semiconductors | OW/Wait | NVDA supply intact; China tariff watch for memory |\n| Hardware | Neutral | Supply chain tariff exposure (China) |",
                      "upside_risk": "AI spending acceleration from enterprise; NVDA earnings surprise",
                      "downside_risk": "China supply chain disruption from 145% tariffs; consumer electronics softness",
                      "portfolio_note": "OW on strength — AI cycle is multi-year; use any dip to SPY $670 as entry."})
        elif date == "2026-04-08":
            b.update({"bias": "OW", "conf": "High", "direction": "↑ Strong +3.1%",
                      "driver": "Led ceasefire rally; XLK +3.1% = sector outperformed",
                      "what_changed": "- XLK surged +3.1% on ceasefire rally — technology led the market\n- NVDA, MSFT, GOOGL all gained 3-4% on risk-on\n- AI infrastructure spending narrative unaffected by Iran/tariff\n- DXY weakness = positive for tech international revenues",
                      "sector_catalyst": "Ceasefire = risk-on = growth sectors led",
                      "subsectors": "| Cloud/SaaS | OW | Led rally; Microsoft Azure growth confirmed |\n| Semiconductors | OW | NVDA +3.5%; AI demand intact |\n| Hardware | Neutral/OW | Apple supply chain concerns remain but stock up 2.5% |",
                      "portfolio_note": "OVERWEIGHT — ceasefire removes near-term fear overhang; AI cycle accelerating."})
        elif date >= "2026-04-13":
            b.update({"bias": "OW", "conf": "High",
                      "direction": f"↑ +{(p.get('XLK', 145) - 136.78) / 136.78 * 100:.1f}% from baseline",
                      "driver": "Earnings season positive; tech read-through from financial results",
                      "what_changed": f"- XLK at ${p.get('XLK', 145):.2f} — +{(p.get('XLK', 145) - 136.78) / 136.78 * 100:.1f}% from Apr 5 baseline\n- Strong earnings season boosting ALL sectors including tech\n- AI capex theme confirmed in JPM/GS results (tech infrastructure spending)\n- Microsoft Azure Q1 guidance expected strong",
                      "sector_catalyst": "Earnings momentum; AI capex confirmation from enterprise spending data",
                      "portfolio_note": "OVERWEIGHT — maintaining; target XLK $155 over 3 months."})

    elif seg == "energy":
        if date <= "2026-04-07":
            b.update({"bias": "Cautious OW", "conf": "Low",
                      "driver": "War premium intact but binary — ceasefire = sharp sell-off",
                      "what_changed": "- XLE holding as war premium persists\n- Iran ceasefire proposal (Apr 6) vs rejection (Apr 7) creates binary\n- Oil market pricing uncertainty with wide bid-ask\n- Energy equity investors watching Iran situation closely",
                      "sector_catalyst": f"Iran news flow — {'ceasefire proposal created short-term uncertainty' if date == '2026-04-06' else 'ultimatum rejection briefly supported oil; now waiting for US response'}",
                      "subsectors": "| E&P (exploration) | OW | High oil price = strong cash flow |\n| Integrated (XOM/CVX) | OW | Earnings power high at $110+ |\n| OFS (services) | Neutral | Activity elevated but binary risk |",
                      "downside_risk": "Ceasefire signed = XLE -5-10% immediately; war premium exits",
                      "portfolio_note": "REDUCE to equal-weight — binary risk too high; war premium removal = significant sell."})
        elif date >= "2026-04-08":
            chg_from_base = (p.get("XLE", 57) - 59.68) / 59.68 * 100
            b.update({"bias": "UW", "conf": "High",
                      "direction": f"↓ {chg_from_base:.1f}% from Apr 5 baseline",
                      "driver": f"Ceasefire signed Apr 8 = war premium unwinding; WTI ${p['WTI']:.0f} from $112",
                      "what_changed": f"- XLE at ${p.get('XLE', 57):.2f} — DOWN as war premium exits (from $59.68 baseline)\n- WTI crude fell from $112 → ${p['WTI']:.0f} as Hormuz reopened and ceasefire held\n- XOM, CVX earnings guidance faces downward revision (lower oil = lower EPS)\n- Natural gas stable; LNG export demand holding\n- {'Continued decline; WTI approaching $95 support' if p['WTI'] < 99 else 'Finding support after sharp drop'}",
                      "sector_catalyst": f"Ongoing ceasefire = continued oil price normalization; WTI target $90-95 if holds",
                      "subsectors": f"| E&P | UW | Oil at ${p['WTI']:.0f} = cash flow compression vs $112 |\n| Integrated | UW | XOM/CVX guidance revision risk |\n| Renewables | Neutral | Unaffected by oil price move |",
                      "downside_risk": f"WTI falling to $90 = XLE at $54-55; E&P earnings compression",
                      "portfolio_note": f"UNDERWEIGHT — reduce energy exposure; war premium removing; XLE ${p.get('XLE', 57):.2f} heading toward $55 technical support."})

    elif seg == "financials":
        if date <= "2026-04-12":
            b.update({"bias": "Neutral", "conf": "Medium",
                      "driver": "Ahead of Q1 earnings (Apr 13+); rate environment supportive",
                      "what_changed": "- XLF stable ahead of earnings season\n- Fed at 3.50-3.75% = NIM (net interest margin) still positive for banks\n- Investment banking activity expected strong: IPO/M&A pipeline recovering\n- Consumer credit quality: monitoring charge-off rates",
                      "sector_catalyst": "Q1 earnings season starting April 13 (JPM, GS, BofA, MS)",
                      "subsectors": "| Large cap banks (JPM, BAC) | Neutral/OW | Earnings catalyst upcoming |\n| Investment banks (GS, MS) | OW | Trading revenues expected strong |\n| Insurance | Neutral | Geopolitical events creating claim risk |\n| FinTech | Neutral | Rate sensitivity |",
                      "portfolio_note": "WATCH — hold; Q1 earnings are the catalyst; any beat = add."})
        else:  # Apr 13+
            b.update({"bias": "OW", "conf": "High",
                      "direction": f"↑ +{(p.get('XLF', 51) - 49.88) / 49.88 * 100:.1f}% from baseline",
                      "driver": f"{'JPM EPS $4.98 BEAT (+8.3%); GS BEAT' if date == '2026-04-13' else 'BofA EPS $0.90 BEAT (+8.4%); MS EPS $2.60 BEAT (+10.6%)'}; earnings season confirmed positive",
                      "what_changed": f"- XLF at ${p.get('XLF', 51):.2f} — earnings driven re-rating\n- {'JPMorgan and Goldman beat by >8% — investment banking + trading strong' if date == '2026-04-13' else 'Bank of America consumer banking resilient; Morgan Stanley wealth management strong'}\n- Net interest margins holding at 3.50-3.75% Fed rate\n- Loan loss reserves: no deterioration — credit quality holding",
                      "sector_catalyst": f"{'JPM/GS Q1 earnings BEAT' if date == '2026-04-13' else 'BofA/MS Q1 earnings BEAT'} — sector re-rating to OW",
                      "portfolio_note": "ADD — Q1 earnings beats confirm sector thesis; XLF target $54 (3-month)."})

    elif seg == "consumer-staples":
        b.update({"bias": "OW" if date <= "2026-04-10" else "Neutral",
                  "conf": "Medium",
                  "driver": "Defensive with inflation pass-through; losing defensiveness as risk-on dominates",
                  "what_changed": f"- XLP at ${p.get('XLP', 82):.2f} — {'defensive bid intact' if date <= '2026-04-07' else ('less defensive demand as risk-on dominates' if date >= '2026-04-08' else 'stable')}\n- WMT, KO, PEP passing tariff costs through to consumers\n- Pricing power intact in low-elasticity categories",
                  "sector_catalyst": "Tariff pass-through pricing announcements from staples companies",
                  "subsectors": "| Food & Beverage | OW | Pricing power + recession hedge |\n| Household Products | Neutral | Raw material cost pressure from tariffs |\n| Discount Retail | OW | Consumers trading down on high prices |",
                  "portfolio_note": f"{'OW on defensives — uncertainty justifies premium' if date <= '2026-04-07' else 'REDUCE to NEUTRAL — risk-on reduces need for defensives; rotate to growth'}."})

    elif seg == "consumer-disc":
        b.update({"bias": "Neutral" if date <= "2026-04-07" else "OW",
                  "conf": "Medium",
                  "driver": f"{'Consumer confidence declining + oil cost drag limiting' if date <= '2026-04-07' else 'Oil falling post-ceasefire = discretionary spending relief; risk-on consumer'}",
                  "what_changed": (f"- XLY at ${p.get('XLY', 110):.2f}\n"
                                  + ("- Consumer confidence declining with oil prices elevated\n" if date <= "2026-04-07"
                                     else f"- Lower oil (~${p['WTI']:.0f}/bbl) = less consumer drag; risk-on = spending appetite\n")
                                  + "- AMZN, TSLA, HD key components"),
                  "sector_catalyst": f"{'Consumer confidence data' if date <= '2026-04-07' else 'Oil price decline = consumer spending recovery thesis'}",
                  "portfolio_note": f"{'NEUTRAL — consumer stress from oil prices limiting' if date <= '2026-04-07' else 'ADD — oil price decline + risk-on = consumer disc recovery trade'}."})

    elif seg == "industrials":
        b.update({"bias": "Neutral",
                  "driver": "Tariff uncertainty on supply chains; defense spending elevated",
                  "what_changed": f"- Industrials impacted by tariff uncertainty on input costs\n- Defense names (LMT, RTX) firm on Iran war spending\n- Infrastructure names flat\n- Tariff pause (90-day) gives manufacturing some relief",
                  "sector_catalyst": f"{'Tariff uncertainty stalling orders' if date <= '2026-04-07' else '90-day tariff pause = reshoring investment pause relief'}",
                  "portfolio_note": "NEUTRAL — mixed signals; defense OW, rest cautious; not in portfolio."})

    elif seg == "utilities":
        b.update({"bias": "Neutral" if date <= "2026-04-07" else "UW",
                  "driver": f"Rate-sensitive; 10Y at {p['TNX']:.2f}% = headwind; AI power demand = tailwind",
                  "what_changed": f"- XLU at ${p.get('XLU', 70):.2f}\n- {'Defensive bid in uncertainty' if date <= '2026-04-07' else 'Selling pressure as risk-on reduces defensives need'}\n- AI data center power demand structural positive\n- 10Y yield at {p['TNX']:.2f}% = discount rate headwind",
                  "sector_catalyst": "AI power demand (long-term positive) vs rising rates (near-term headwind)",
                  "portfolio_note": "NEUTRAL/UW — interest rate sensitivity makes this difficult; AI power is positive but rates limit upside."})

    elif seg == "materials":
        b.update({"bias": "Neutral",
                  "driver": "China tariff = copper/metals demand uncertainty; gold miners (NEM) positive on gold run",
                  "what_changed": f"- Materials: China tariff uncertainty suppressing metals demand\n- Copper ~$9,850/ton — China 55% of demand; tariffs creating uncertainty\n- Gold miners (NEM, GOLD) benefiting from gold at ${p['GOLD_OZ']:,}/oz\n- Lithium/EV materials: China supply chain concerns",
                  "sector_catalyst": f"Gold price at ${p['GOLD_OZ']:,} benefiting gold miners in XLB",
                  "portfolio_note": "NEUTRAL — gold mining names interesting but sector too China-dependent; watch NEM specifically."})

    elif seg == "real-estate":
        b.update({"bias": "UW",
                  "driver": f"10Y at {p['TNX']:.2f}% = elevated cap rates; REITs rate-sensitive",
                  "what_changed": f"- XLRE pressured by 10Y at {p['TNX']:.2f}%\n- Higher for longer rate environment = REIT discount rate headwind\n- Data center REITs (EQIX, AMT) partially insulated by AI demand\n- Office REITs: structural vacancy concerns",
                  "sector_catalyst": "Fed rate path — any cut probability rise = REIT relief rally",
                  "portfolio_note": "UNDERWEIGHT — until 10Y falls below 4.0%; data center REITs exception."})

    elif seg == "comms":
        b.update({"bias": "OW",
                  "driver": "AI-adjacent digital advertising; META, GOOGL strong; streaming growth",
                  "what_changed": f"- XLC at ${p.get('XLC', 100):.2f}\n- META, GOOGL benefiting from AI-powered ad targeting improving ROI\n- Digital advertising revenue resilient vs. linear TV\n- NFLX ad-supported tier growing\n- DIS streaming recovering",
                  "sector_catalyst": "Digital advertising resilience; AI targeting improvements",
                  "portfolio_note": "OW — AI-adjacent; digital ad cycle intact; META/GOOGL core holdings in index."})

    elif seg == "healthcare":
        b.update({"bias": "OW" if date <= "2026-04-10" else "Neutral",
                  "driver": "Defensive + GLP-1 drug (obesity/diabetes) secular growth cycle",
                  "what_changed": f"- XLV at ${p.get('XLV', 147):.2f}\n- {'Defensive bid in geopolitical uncertainty' if date <= '2026-04-07' else ('Part of broad ceasefire rally but less than cyclicals' if date == '2026-04-08' else 'Slight underperformance as risk-on rotates to cyclicals')}\n- LLY (GLP-1/Mounjaro demand) sustaining premium valuation\n- MRK, ABBV patent cliffs but biosimilar pressure manageable",
                  "sector_catalyst": "GLP-1 adoption curve; no major regulatory event this week",
                  "portfolio_note": f"{'OW — defensive + GLP-1 secular growth; risk-off insurance' if date <= '2026-04-07' else 'NEUTRAL — risk-on rotates away from defensives; GLP-1 still bullish but near-term momentum elsewhere'}."})

    return b


# ---------------------------------------------------------------------------
# Alt-data segment generators (7 segments)
# ---------------------------------------------------------------------------

def gen_sentiment_news(date: str, p: dict, ctx: dict) -> str:
    d = ctx["delta_n"]
    spy_chg = ctx["spy_chg_pct"]

    sentiment_state = {
        "2026-04-06": ("43 — Fear", "Elevated fear; binary event pending", "Bulls waiting for Tuesday outcome"),
        "2026-04-07": ("38 — Extreme Fear", "Ultimatum rejection = fear spike", "Options skew elevated; put demand"),
        "2026-04-08": ("62 — Greed", "Ceasefire = sentiment flip in single session", "VIX dropped 4 points on day"),
        "2026-04-09": ("68 — Greed", "Continued momentum; tariff pause added fuel", "Retail FOMO emerging"),
        "2026-04-10": ("65 — Greed", "Slight pullback in sentiment; consolidation healthy", "Conviction holding"),
        "2026-04-11": ("63 — Greed", "Weekend; futures stable; sentiment holding gains", "No panic selling"),
        "2026-04-13": ("70 — Greed", "Earnings beats = sentiment positive; approaching overbought watch", "Watch for exhaustion signals"),
        "2026-04-14": ("72 — Greed", "Strong sentiment; gold surge = inflation fear adding complexity", "Caution: divergence between risk-on AND gold"),
    }
    fng, fng_desc, fng_note = sentiment_state.get(date, ("50 — Neutral", "Neutral sentiment", "Monitor"))

    news_items = {
        "2026-04-06": ["Trump ultimatum dominates financial media — binary outcome framing", "DXY below 100 covered as 'dollar in freefall' narrative emerging", "Gold coverage positive: dual-bid thesis gaining mainstream recognition"],
        "2026-04-07": ["Iran ultimatum rejection — 'Brinkmanship continues' narrative", "Market flatness despite geopolitical noise: resilience or complacency?", "Bears citing overvaluation; bulls citing earnings season catalyst"],
        "2026-04-08": ["CEASEFIRE: Wall Street Journal, Bloomberg, CNBC lead with 'risk-on'", "Energy sector selloff covered as 'war premium exits'", "Gold holding despite ceasefire — analysts noting inflation bid"],
        "2026-04-09": ["Tariff pause: 'Trump blinks on tariffs for 90 days (except China)'", "Dual catalyst narrative: ceasefire + tariff pause = 'all-clear signal'", "China 145% tariffs — 'trade war with China continues despite broader pause'"],
        "2026-04-10": ["Post-event consolidation — market shrugging off small negatives", "Earnings preview: JPM, GS, BofA expectations elevated", "Gold/inflation narrative building: 'is the tariff pause inflationary?'"],
        "2026-04-11": ["Weekend review: 'Risk-on week confirmed; best week since January'", "Gold coverage: '$4,540/oz — structural support, not just fear bid'", "Q1 earnings preview: consensus estimates high; bar is high"],
        "2026-04-13": ["JPM, GS beat: 'Banks signal economy better than feared'", "'Earnings season starts well — bullish'", "Gold slight dip covered as 'healthy consolidation'"],
        "2026-04-14": ["BofA, MS beat: 'Broadening earnings season quality'", "GOLD SURGE: '$4,625 — inflation trade back on?'", "Paradox coverage: 'How can stocks AND gold both rally?'"],
    }

    news_md = "\n".join(f"- {n}" for n in news_items.get(date, ["Markets monitoring macro developments"]))

    return f"""# Sentiment & News Intelligence — {date}

> Delta #{d} from baseline 2026-04-05 | {ctx['day']} | {ctx['headline']}

---

## 📊 SENTIMENT DASHBOARD

| Indicator | Level | Signal | Interpretation |
|-----------|-------|--------|----------------|
| **Fear & Greed Index** | {fng} | {fng_desc} | {fng_note} |
| **VIX** | {'~24 (elevated)' if date <= '2026-04-07' else '~18 (normalizing)' if date <= '2026-04-10' else '~17 (low)'} | {'Risk-off' if date <= '2026-04-07' else 'Risk-on'} | Market complacency{'watch' if date >= '2026-04-09' else ' vs fear'} |
| **Put/Call Ratio** | {'~1.2 (elevated puts)' if date <= '2026-04-07' else '~0.85 (normal)' if date <= '2026-04-10' else '~0.80 (bullish)'} | {'Bearish positioning' if date <= '2026-04-07' else 'Neutral' if date <= '2026-04-10' else 'Slightly bullish'} | Options market positioning |
| **AAII Bull/Bear** | {'38%/42% (net bearish)' if date <= '2026-04-07' else '52%/30% (net bullish)'} | {'Contrarian bullish signal' if date <= '2026-04-07' else 'Elevated bullishness — watch'} | Retail sentiment survey |
| **Social media** | {'High fear/uncertainty' if date <= '2026-04-07' else 'Positive momentum/FOMO'} | {fng_desc} | Reddit/Twitter/X trending |

---

## News Headlines ({date})
{news_md}

---

## Narrative Analysis

### Dominant Narrative: {'"Binary risk — Iran ultimatum"' if date <= '2026-04-07' else '"Post-crisis recovery"' if date <= '2026-04-10' else '"Earnings season + inflation paradox"'}
{ctx['headline']}

### Contrarian Signals
- {'CONTRARIAN BULLISH: Extreme fear = retail selling into wholesale opportunity' if date <= '2026-04-07' else 'CAUTION: Greed reading at ' + fng.split()[0] + ' — sentiment stretched; not a sell signal but contrarian awareness needed'}
- {'Put/call elevated = hedging activity = smart money uncertainty vs retail fear' if date <= '2026-04-07' else 'Watch: AAII bulls at elevated levels = tactical pullback risk after 3+ day run'}

---

## Social Media / Alternative Sentiment
- **Reddit (r/wallstreetbets, r/investing)**: {'"Bracing for Iran response" threads dominating' if date <= '2026-04-07' else '"Apes together strong — risk-on" sentiment' if date <= '2026-04-10' else '"Earnings FOMO" posts increasing'}
- **Twitter/X Financial**: {'Macro/geopolitical debate — CNBC contributors split' if date <= '2026-04-07' else 'Bullish FOMO dominating timeline — watch for peak-sentiment signal'}
- **Polymarket**: {'Iran escalation probability: ~52%' if date <= '2026-04-07' else 'Ceasefire holding probability: ~78%'}

---

## Sentiment Risk Watch
- {'**EXTREME FEAR**: Use contrarian signal — extreme fear often precedes reversal; watch for binary resolution' if date <= '2026-04-07' else '**GREED WATCH**: F&G at ' + fng.split()[0] + ' — pullback probability increases above 70; not a sell but reduce new entries'}
- **News cycle**: {'Iran ultimatum resolution = major narrative shift; prepare for volatility' if date <= '2026-04-07' else 'Earnings pace and gold surge creating narrative conflict — monitor for resolution'}
- **Macro disconnect**: {'Options market not pricing ceasefire = asymmetric upside if ceasefire occurs' if date <= '2026-04-07' else 'Gold up AND equities up simultaneously = unusual; signals tariff inflation repricing underway'}
"""


def gen_cta_positioning(date: str, p: dict, ctx: dict) -> str:
    d = ctx["delta_n"]
    cta_state = {
        "2026-04-06": ("Short equities / Long vol", "CTAs short equities from Apr 4 sell signal; long volatility products", "Headwind to equity rally if CTAs flip"),
        "2026-04-07": ("Short equities / Long vol", "Maintaining short positions; ultimatum rejection confirms bears", "CTA short = additional selling pressure"),
        "2026-04-08": ("COVERING — forcing flip", "Ceasefire rally triggered CTA short-covering cascade; +2.5% move = forced buy", "CTA covering = mechanical buying adding to rally"),
        "2026-04-09": ("Long equities (flipped)", "CTAs flipped to long after covering; now tail-wind to equity momentum", "Mechanical buy = additional momentum fuel"),
        "2026-04-10": ("Long equities (building)", "CTAs adding to long positions on consolidation; trend signal confirmed", "Positive: CTAs supporting equity floor"),
        "2026-04-11": ("Long equities (stable)", "Weekend; CTA positions stable; monitoring futures", "CTA momentum long = Monday gap risk if any negative news"),
        "2026-04-13": ("Long equities (confirmed)", "Earnings beats = trend confirmation = CTAs adding to longs", "Mechanical + fundamental buyers both long"),
        "2026-04-14": ("Long equities / Long gold", "CTAs adding gold exposure on breakout signal above $4,600", "Dual CTA longs = equities + gold = inflationary regime signal"),
    }
    cta_pos, cta_desc, cta_signal = cta_state.get(date, ("Neutral", "Mixed signals", "Monitor"))

    return f"""# CTA & Systematic Positioning — {date}

> Delta #{d} from baseline 2026-04-05 | {ctx['day']} | {ctx['headline']}

---

## 📊 CTA POSITIONING OVERVIEW

| Metric | Status | Signal |
|--------|--------|--------|
| **Equity trend signal** | {cta_pos} | {cta_desc} |
| **Fixed income** | {'Short duration' if date <= '2026-04-07' else 'Neutral duration' if date <= '2026-04-10' else 'Short duration'} | Bonds: rate uncertainty |
| **Commodities** | {'Long oil' if date <= '2026-04-07' else 'Reducing oil; adding gold' if date <= '2026-04-10' else 'Long gold'} | War premium exit = CTA oil reduction |
| **Vol positioning** | {'Long vol (VIX longs)' if date <= '2026-04-07' else 'Vol selling (VIX shorts)'} | {'Fear hedge' if date <= '2026-04-07' else 'Vol normalization = additional risk-on fuel'} |
| **DXY** | Short USD | Dollar structural weakness confirmed by trend models |

---

## CTA Signal Analysis

### Current Signal: {cta_pos}
{cta_desc}

**Portfolio impact**: {cta_signal}

### Trigger Events
{chr(10).join(f'- {e}' for e in ctx['key_events'][:3])}

---

## Systematic Strategy Summary

| Strategy Type | Positioning | Driver |
|--------------|-------------|--------|
| Trend Following (CTA) | {cta_pos} | Momentum signal from {'Apr 4 sell-off' if date <= '2026-04-07' else 'Apr 8 ceasefire reversal'} |
| Risk Parity | {'De-risked' if date <= '2026-04-07' else 'Re-risking'} | Volatility-weighted allocation adjusting |
| Volatility Selling | {'Paused/Reduced' if date <= '2026-04-07' else 'Resuming'} | VIX {'elevated — pause premium selling' if date <= '2026-04-07' else 'normalizing — vol selling profitable again'} |
| Statistical Arbitrage | Neutral | Factor-neutral; market neutral |

---

## CTA Risk Watch
- **{cta_signal}**
- {'Ceasefire could trigger mass CTA short-covering = amplified rally' if date <= '2026-04-07' else 'CTA long = if any reversal, CTAs become sellers = amplified downside'}
- **VIX watch**: {'VIX at 24 — CTAs buy VIX; any spike = more short-selling pressure' if date <= '2026-04-07' else 'VIX at 18 — CTAs selling vol; keep below 22 for trend to hold'}

---

## Portfolio Implication
{'CTAs short equities = additional selling pressure risk; maintain defensive positioning until CTA flip confirmed' if date <= '2026-04-07' else 'CTAs now long equities = mechanical buying floor; equity dips more likely to be bought'}
"""


def gen_options_derivatives(date: str, p: dict, ctx: dict) -> str:
    d = ctx["delta_n"]
    vix_level = 24 if date <= "2026-04-07" else 18 if date <= "2026-04-10" else 17
    pcr = 1.2 if date <= "2026-04-07" else 0.85

    return f"""# Options & Derivatives Intelligence — {date}

> Delta #{d} from baseline 2026-04-05 | {ctx['day']} | {ctx['headline']}

---

## 📊 OPTIONS MARKET OVERVIEW

| Metric | Level | Signal |
|--------|-------|--------|
| **VIX** | ~{vix_level} | {'Elevated — fear premium' if vix_level > 20 else 'Normalizing — risk-on confirmed'} |
| **Put/Call Ratio** | ~{pcr} | {'Elevated put demand — hedging' if pcr > 1.0 else 'Normal — balanced market'} |
| **Term Structure** | {'Inverted (front > back)' if vix_level > 20 else 'Normal contango'} | {'Fear front-loaded' if vix_level > 20 else 'Vol sellers returning'} |
| **Skew (25-delta)** | {'Steep — puts expensive' if vix_level > 20 else 'Normalizing'} | Downside protection premium |
| **GEX (Gamma Exp)** | {'Negative — dealers short gamma' if vix_level > 20 else 'Positive — dealers long gamma'} | {'Amplifies moves both ways' if vix_level > 20 else 'Dampens volatility — pin action'} |

---

## Key Options Observations ({date})

### SPY Options
- **IV rank**: {'High (75th percentile) — options expensive; sell premium' if vix_level > 20 else 'Normal (40th percentile) — options fairly priced'}
- **Key strikes**: {'$640 puts (protection); $680 calls (capped upside)' if vix_level > 20 else f'${p["SPY"]:.0f}±10 most active; ${(p["SPY"]//10+1)*10:.0f} call wall growing'}
- **0DTE activity**: High — retail activity in same-day options active
- **Options flow**: {'Net put buyers — institutions hedging; retail buying calls on dips' if vix_level > 20 else 'Net call buyers — momentum; retail following institutional'}

### Gold (GLD) Options
- **IAU/GLD IV**: {'Rising — geopolitical uncertainty bid' if date <= '2026-04-07' else 'Moderating after moves'}
- **Call skew**: {'Calls bid — upside positioning for geopolitical spike' if date <= '2026-04-07' else f'Calls bid at ${p["GOLD_OZ"] + 200:,}/oz — tariff inflation positioning'}

### VIX Options
- **VIX level**: {vix_level}
- **VIX calls (tail protection)**: {'Expensive — hedgers buying; VIX $30+ calls in demand' if vix_level > 20 else 'Cheaper — tail risk priced lower; potential to sell VIX calls as income'}
- **Expected move (1 week)**: {'±{:.1f}% based on VIX'.format(vix_level * 0.23) } implied

---

## Today's Key Developments (Options Lens)
{chr(10).join(f'- {e}' for e in ctx['key_events'][:3])}

---

## Options Risk Watch
- {'**BINARY EVENT**: Option market implying ±3-5% move on Iran news; consider strangle if binary risk hedging needed' if date <= '2026-04-07' else '**VOL COMPRESSION**: VIX falling = vol sellers winning; watch for VIX snap-back if any macro shock'}
- **Gamma risk**: {'Negative gamma = dealer hedging amplifies moves — be cautious on market-on-close' if vix_level > 20 else 'Positive gamma = dealers absorbing volatility — range-bound between strikes'}
- **Earnings**: {'Options pricing in ±4-6% moves for JPM, GS on April 13' if date <= '2026-04-12' else f'Post-earnings implied vol collapsing — sell premium post-print strategy'}

---

## Portfolio Implication
{'Consider hedging: SPY puts (April expiry) cost elevated but justified for binary Iran event; ratio: 5-10% of portfolio protection' if date <= '2026-04-07' else f'Vol selling opportunity: VIX at {vix_level} = options richly priced vs realized vol; covered calls on SPY positions add income'}
"""


def gen_politician_signals(date: str, p: dict, ctx: dict) -> str:
    d = ctx["delta_n"]
    events = {
        "2026-04-06": [
            "Trump: 'Iran has until Tuesday to open Hormuz or face consequences' — market binary defined",
            "Treasury Sec Bessent: 'Dollar weakness reflects global rebalancing, not US weakness' — attempted to calm DXY concerns",
            "SecState Rubio: 'Back-channel communications ongoing with Iran via Qatar mediator'",
            "Congress: Senate passed $45B emergency defense authorization 78-22 — bipartisan support",
        ],
        "2026-04-07": [
            "Trump: 'Iran chose wrong — they will face consequences' after ultimatum rejection",
            "SecDef: Additional carrier group deployed to Gulf — military posture escalated",
            "China: PBOC governor said 'China ready to use all policy tools' in response to tariffs",
            "Fed (Silence period begins): No officials speaking ahead of May 7 FOMC",
        ],
        "2026-04-08": [
            "Trump: 'Iran chose peace — the ceasefire is good for America and the world'",
            "White House: 'This is a 45-day pause; Iran must demonstrate good faith'",
            "SecState Rubio: 'The Hormuz Protocol remains in force; shipping monitored closely'",
            "China: Foreign Ministry: 'China notes the ceasefire; our tariff situation is separate'",
        ],
        "2026-04-09": [
            "Trump: 'We're giving our trading partners 90 days — they've been terrific except China'",
            "Trump on China: '145% tariffs stay; they haven't called, which is their loss'",
            "Bessent: 'The tariff pause creates negotiating leverage with good-faith partners'",
            "Xi Jinping: 'China will not be coerced; we have our own tools' — retaliation signal",
        ],
        "2026-04-10": [
            "Fed silence period: No speeches; May 7 FOMC approaching",
            "Trump: 'The markets love what we're doing; it's all coming together'",
            "Congressional Republicans: Support tariff pause as 'strategic patience'",
            "Democrats: 'Why is China exempted? Bipartisan concern on China tariff strategy'",
        ],
        "2026-04-11": [
            "Weekend: Trump golfing at Mar-a-Lago; minimal policy statements",
            "Bessent interview: 'The 90-day pause is not a capitulation — it's strategy'",
            "China Foreign Ministry: 'We are evaluating our response; no rush'",
            "Fed: Pre-FOMC silence period continues through May 7",
        ],
        "2026-04-13": [
            "Trump called JPMorgan CEO Dimon: 'Congratulations — great quarter proves America wins'",
            "White House: 'Q1 earnings season proving our economic policies working'",
            "China: No retaliation announcement — strategic patience continues",
            "Congressional hearing: Treasury Sec Bessent on tariff strategy; defended China exclusion",
        ],
        "2026-04-14": [
            "Trump: 'Gold at record — people are protecting their wealth with America's policies'",
            "Bessent: 'We're monitoring inflation; tariffs are strategic, not inflationary'",
            "Fed Vice Chair (pre-silence ended): 'We are watching tariff pass-through carefully'",
            "China: PBOC injected CNY 300B via MLF — stimulus signaling without announcement",
        ],
    }

    signals_md = "\n".join(f"- {s}" for s in events.get(date, ["No major signals today"]))

    return f"""# Politician & Official Signals — {date}

> Delta #{d} from baseline 2026-04-05 | {ctx['day']} | {ctx['headline']}

---

## 📊 OFFICIAL SIGNAL DASHBOARD

| Official | Signal | Market Impact |
|----------|--------|--------------|
| **Trump (POTUS)** | {'"Iran ceasefire achieved"' if date == '2026-04-08' else '"90-day tariff pause (ex-China)"' if date == '2026-04-09' else '"Iran ultimatum"' if date <= '2026-04-07' else '"Earnings signal economy strong"'} | {'Major market catalyst' if date in ['2026-04-08', '2026-04-09'] else 'Moderate'} |
| **Treasury (Bessent)** | {'Dollar weakness as rebalancing' if date == '2026-04-06' else 'Tariff pause = strategy' if date >= '2026-04-09' else 'Monitoring situation'} | {'Calming' if date <= '2026-04-07' else 'Confidence'} |
| **Fed (Powell)** | {'Silence period (pre-FOMC)' if date >= '2026-04-07' else 'Rate at 3.50-3.75% (confirmed)'} | No surprise; market priced |
| **China (Xi/PBOC)** | {'Retaliation signals' if date >= '2026-04-09' else 'Watching Iran situation'} | {'Uncertainty' if date >= '2026-04-09' else 'Low'} |
| **Congressional** | {'Bipartisan defense support' if date <= '2026-04-08' else 'Mixed on China tariff strategy'} | Low direct market impact |

---

## Key Official Statements ({date})
{signals_md}

---

## Fed Communication Tracker
- **Rate**: 3.50-3.75% (March 18, 2026 FOMC — confirmed)
- **Posture**: {'Pre-FOMC silence period — no communications' if date >= '2026-04-07' else 'Hold posture confirmed; data-dependent'}
- **Next FOMC**: May 7, 2026
- **Key watch**: April CPI (May 13) — tariff pass-through will determine June cut probability
- **Dissents at last meeting**: One dissent for further hold; consensus on pause

---

## Congressional/Legislative Tracker
- **Defense**: Senate approved $45B emergency authorization — bipartisan
- **Tariffs**: No congressional action; executive authority intact
- **China**: Growing bipartisan concern on China 145% tariff strategy vs. allies
- **Debt ceiling**: Not immediate issue; under monitoring

---

## Politician Trading (Insider-adjacent)
- **Energy stocks**: Watch if pro-ceasefire politicians reduce energy holdings
- **Defense stocks**: Watch defense committee members — LMT, RTX, GD
- **Monitor**: FORM 4 filings (executive transactions) at SEC EDGAR

---

## Signal Risk Watch
- **China retaliation**: Xi's 'own tools' language = tariff retaliation could come any day
- **Trump**: Binary communicator — any tweet/Truth Social post can move markets significantly
- **Fed silence**: No Fed speeches until after May 7 FOMC — market pricing in vacuum
- **Congressional China**: Bipartisan China tariff critique could create political pressure on 145% stance
"""


def gen_institutional_flows(date: str, p: dict, ctx: dict) -> str:
    d = ctx["delta_n"]

    flow_data = {
        "2026-04-06": ("$2.1B outflows from equity ETFs (SPY, QQQ)", "Institutional caution ahead of Tuesday binary event", "$800M into gold ETFs (GLD, IAU) — geopolitical hedge"),
        "2026-04-07": ("$3.4B outflows from equity ETFs", "Iran ultimatum rejection = institutional risk reduction", "$1.2B into bond ETFs (TLT, LQD) — flight to safety"),
        "2026-04-08": ("$5.8B INFLOWS to equity ETFs — largest single day", "Ceasefire = institutional forced repositioning", "$600M OUT of gold ETFs — risk-on rotation; gold held vs outflows = underlying strength"),
        "2026-04-09": ("$3.2B inflows to equity ETFs", "Tariff pause added additional inflow catalyst", "$400M into gold ETFs resuming — tariff inflation bid"),
        "2026-04-10": ("$1.1B moderate inflows", "Consolidation; institutional positioning stabilizing", "$200M into gold ETFs — steady bid"),
        "2026-04-11": ("Weekend — limited data", "Futures markets: institutional net long", "Gold futures: net long positioning increasing"),
        "2026-04-13": ("$2.8B inflows — earnings driven", "JPM, GS beats = institutional confidence", "$150M into financials ETFs (XLF) specifically"),
        "2026-04-14": ("$3.5B inflows — broad", "Multi-sector inflows; tech, financials, gold all receiving", "$900M into gold ETFs — largest since April 8 inflow day"),
    }
    equity_flow, equity_driver, gold_flow = flow_data.get(date, ("Mixed flows", "Uncertain", "Neutral"))

    return f"""# Institutional Intelligence — {date}

> Delta #{d} from baseline 2026-04-05 | {ctx['day']} | {ctx['headline']}

---

## 📊 INSTITUTIONAL FLOW SUMMARY

| Asset Class | Flow | Direction | Driver |
|-------------|------|-----------|--------|
| **US Equity ETFs** | {equity_flow} | {'↑ Inflow' if 'inflow' in equity_flow.lower() else '↓ Outflow'} | {equity_driver} |
| **Gold ETFs** | {gold_flow} | {'↑' if 'into' in gold_flow.lower() else '↓' if 'out of' in gold_flow.lower() else '→'} | Dual bid: geo + tariff inflation |
| **Bond ETFs** | {'↑ Inflow (TLT, LQD)' if date <= '2026-04-07' else '→ Neutral outflows' if date <= '2026-04-10' else '↑ Slight inflows'} | — | {'Flight to safety' if date <= '2026-04-07' else 'Risk-on reduces bond demand'} |
| **Energy ETFs** | {'↓ Outflows (XLE)' if date >= '2026-04-08' else '↑ Inflows (XLE) — war premium'} | — | Oil price trajectory |
| **International ETFs** | {'↑ Inflows (EFA)' if date >= '2026-04-09' else '→ Neutral'} | — | Tariff pause + dollar weakness |

---

## ETF Flow Detail

### Equity Flows
{equity_flow}
**Driver**: {equity_driver}

### Gold Flows
{gold_flow}
**Context**: Gold ETF flows unusual — {'institutional buying during risk-off (normal)' if date <= '2026-04-07' else 'institutional BUYING alongside equity inflows = tariff inflation thesis gaining traction (unusual and important signal)'}

---

## Hedge Fund Intelligence

| Signal | Date | Detail |
|--------|------|--------|
| Citadel | Long equities | Ceasefire catalyst = risk-on positioning |
| Bridgewater | Gold + bonds | All-weather: inflation hedge positioning confirmed |
| Renaissance | Systematic | CTA signals now long equities after flip |
| Millennium | Sector rotations | Reducing energy; adding technology |
| Point72 | Earnings plays | Long financials ahead of JPM/GS earnings |

---

## 13D/13G Filing Watch (Week of Apr 6-14)
- No new major activist filings this week
- Watch: Any 5%+ threshold crossings in energy companies (M&A or activist post-ceasefire)
- Insider buying: Financial sector executives buying own stock ahead of earnings

---

## Today's Key Developments (Flows Lens)
{chr(10).join(f'- {e}' for e in ctx['key_events'][:3])}

---

## Institutional Flow Risk Watch
- **{'Outflows reversing = technical buy signal coming' if date <= '2026-04-07' else 'Inflow pace sustainability — if earnings disappoint, institutional quick to reverse'}**
- **Gold ETF dual bid**: Institutions buying gold alongside equities = STRUCTURAL, not just fear
- **Energy outflows**: Systematic re-allocation from energy to tech/financials in progress

---

## Portfolio Implication
{'Institutional de-risking = stay cautious; BIL/SHY appropriate; wait for institutional flip signal' if date <= '2026-04-07' else 'Institutional flows supporting both gold (IAU) and equities (SPY) — confirms dual holding thesis'}
"""


def gen_hedge_fund_intel(date: str, p: dict, ctx: dict) -> str:
    d = ctx["delta_n"]

    return f"""# Hedge Fund Intelligence — {date}

> Delta #{d} from baseline 2026-04-05 | {ctx['day']} | {ctx['headline']}

---

## 📊 HEDGE FUND POSITIONING OVERVIEW

| Strategy | Positioning | Change from Baseline | Driver |
|----------|-------------|---------------------|--------|
| **Macro Global** | Long gold, short energy | Reducing energy as war premium exits | Iran ceasefire trajectory |
| **Long/Short Equity** | {'Net short' if date <= '2026-04-07' else 'Net long (flipping)'} | {'Maintaining shorts' if date <= '2026-04-07' else 'Covering shorts, adding longs'} | {'Binary event caution' if date <= '2026-04-07' else 'Ceasefire + earnings catalyst'} |
| **Event Driven** | {'Long energy (war premium)' if date <= '2026-04-07' else 'Short energy, long financials'} | Sector rotation | {'War premium trade' if date <= '2026-04-07' else 'Earnings season + oil normalization'} |
| **Quant/CTA** | {'Short equities' if date <= '2026-04-07' else 'Long equities (mechanical flip)'} | Signal-driven | Trend model flipped {'on Apr 8 ceasefire surge' if date >= '2026-04-08' else 'not yet'} |
| **Multi-Strategy** | Neutral | Balanced book | Uncertainty = balanced risk |

---

## Notable Fund Positioning (Intelligence)

### Bridgewater Associates (Ray Dalio)
- Allocation: ~20% gold, 30% bonds, 50% equities (all-weather tilted for inflation)
- Q1 commentary: "Tariff inflation regime is our base case; gold is the clearest beneficiary"
- Action: Adding IAU/GLD; reducing long-duration bonds

### Citadel (Ken Griffin)
- Action: {'Cautious — binary risk management' if date <= '2026-04-07' else 'Adding equity risk post-ceasefire'}
- Focus: {'Volatility positioning — long VIX near-term' if date <= '2026-04-07' else 'Earnings plays in financials; long XLF ahead of JPM/GS'}

### Millennium Management
- Action: {'Sector-neutral' if date <= '2026-04-07' else 'Long tech (XLK), short energy (XLE)'}
- Rationale: AI capex + ceasefire = tech up; war premium exit = energy down

### Pershing Square (Bill Ackman)
- Recent: Long gold and anti-inflation assets
- Public statement: "Tariffs are inflationary; the 90-day pause doesn't change the thesis"

---

## Short Interest Watch (Top Shorted Names)
| Name | Short Interest | Change | Signal |
|------|---------------|--------|--------|
| XLE (Energy ETF) | {'Rising' if date >= '2026-04-08' else 'Elevated from baseline'} | {'Increasing short as war premium exits' if date >= '2026-04-08' else 'Shorts holding'} | Energy bears gaining conviction |
| Energy names (XOM, CVX) | {'Increasing' if date >= '2026-04-08' else 'Stable'} | — | War premium exit = earnings compression |
| China-exposed tech | Elevated | Increasing | 145% tariff = margin compression risk |

---

## Today's Key Developments (HF Intel Lens)
{chr(10).join(f'- {e}' for e in ctx['key_events'][:3])}

---

## HF Risk Watch
- **CTA flip**: {'CTAs still short equities; any forced covering = +3-5% additional move — watch for trigger' if date <= '2026-04-07' else 'CTAs now long; if any reversal trigger, mechanical selling would amplify downside'}
- **Energy short squeeze**: Elevated short interest in energy + any ceasefire collapse = massive squeeze risk
- **Gold**: Bridgewater-style macro funds adding gold = institutional validation of dual-bid thesis

---

## Portfolio Implication
{'Hedge fund positioning cautious = market has room to run if binary event resolves positively; contrarian opportunity' if date <= '2026-04-07' else 'Hedge fund positioning now aligned with our thesis (long equities + gold); risk = overcrowded trade if sentiment turns'}
"""


def gen_opportunity_screen(date: str, p: dict, ctx: dict) -> str:
    d = ctx["delta_n"]
    spy = p["SPY"]

    screen_results = {
        "2026-04-06": {
            "holdings": [("BIL", "+3", "Hold", "Income floor; short rate neutral in any outcome"), ("SHY", "+2", "Hold", "Duration safe; Fed floor"), ("IAU", "+3", "Hold", "Dual-bid intact"), ("XLE", "+1", "Watch", "Binary risk"), ("XLP", "+2", "Hold", "Defensive")],
            "opportunities": [("SHY", "+2", "Add on binary resolution"), ("IAU", "+3", "Add on any dip")],
        },
        "2026-04-08": {
            "holdings": [("BIL", "+3", "Hold", "Income floor stable"), ("SHY", "+2", "Hold", "Duration safe"), ("IAU", "+3", "Hold/Add", "Tariff inflation bid persists"), ("SPY", "+3", "Add", "Ceasefire confirmed risk-on")],
            "opportunities": [("SPY", "+3", "Add — ceasefire catalyst"), ("EFA", "+2", "Starter — tariff pause + dollar weakness"), ("XLK", "+2", "Tech led rally")],
        },
        "2026-04-09": {
            "holdings": [("BIL", "+3", "Hold", "Income stable"), ("SHY", "+2", "Hold", "Duration OK"), ("IAU", "+3", "Hold", "Gold rising even with risk-on"), ("SPY", "+3", "Hold", "Tariff pause + ceasefire")],
            "opportunities": [("EFA", "+3", "Add — tariff pause + DXY weak"), ("IAU", "+3", "Add — tariff inflation thesis confirmed")],
        },
        "2026-04-13": {
            "holdings": [("BIL", "+3", "Hold", "Income floor"), ("SHY", "+2", "Hold", "Safe duration"), ("IAU", "+3", "Hold", "Slight dip but thesis intact"), ("SPY", "+3", "Hold", "Earnings season positive"), ("EFA", "+2", "Hold", "International recovery")],
            "opportunities": [("XLF", "+3", "Add on earnings beats — JPM, GS confirmed"), ("SPY", "+3", "Hold current allocation")],
        },
        "2026-04-14": {
            "holdings": [("BIL", "+3", "Hold", "Income floor"), ("SHY", "+2", "Hold", "Safe"), ("IAU", "+4", "STRONG ADD", "Gold breakout +2.2%; tariff inflation repricing"), ("SPY", "+3", "Hold", "Earnings momentum"), ("EFA", "+2", "Hold", "Dollar weak = international tailwind")],
            "opportunities": [("IAU", "+4", "Add — gold breakout signal; targeting $4,750+"), ("SPY", "+3", "Hold")],
        },
    }

    screen = screen_results.get(date, screen_results["2026-04-06"])

    holdings_rows = "\n".join(
        f"| {t} | {score} | {action} | {rationale} |"
        for t, score, action, rationale in screen.get("holdings", [])
    )
    opps_rows = "\n".join(
        f"| {t} | {score} | {rationale} |"
        for t, score, rationale in screen.get("opportunities", [])
    )

    return f"""# Opportunity Screen — {date}

> Delta #{d} from baseline 2026-04-05 | {ctx['day']} | {ctx['headline']}

---

## 📊 SCREEN RESULTS OVERVIEW

| Market Context | Status | Signal |
|----------------|--------|--------|
| **Regime** | {ctx['risk_regime']} | Determines scoring weights |
| **SPY level** | ${spy:.2f} | Market anchor |
| **Bias** | {'Risk-off — score defensive higher' if date <= '2026-04-07' else 'Risk-on — score growth/momentum higher'} | Screen tuning |
| **Gold bid** | IAU ${p['IAU']:.2f} | Inflation thesis active |

---

## Current Holdings Analysis

| Ticker | Score | Action | Rationale |
|--------|-------|--------|-----------|
{holdings_rows}

---

## Opportunity Candidates

| Ticker | Score | Rationale |
|--------|-------|-----------|
{opps_rows}

---

## Screen Methodology (Delta Update)

**Regime weights applied** ({ctx['risk_regime']}):
- Regime alignment: 2 pts max (aligned with {'defensive' if date <= '2026-04-07' else 'risk-on'} regime = +2)
- Momentum signal: 1 pt max (CTA/institutional flow direction)
- Thesis status: 1 pt max (active thesis + thesis confirmed)
- Sector bias: 1 pt max (OW sector = +1)
- Total max score: +5

**Score → Action thresholds**:
- Score ≥ +3: HOLD or ADD
- Score = +2: HOLD, monitor
- Score = +1: WATCH, reduce on weakness
- Score ≤ 0: EXIT or AVOID

---

## Screen Changes vs Yesterday
- {'No major screen changes — awaiting binary event resolution' if date <= '2026-04-07' else 'SPY score UPGRADED to +3 on ceasefire confirmation' if date == '2026-04-08' else 'EFA added as opportunity candidate on tariff pause + DXY weakness' if date == '2026-04-09' else 'IAU score upgraded to +4 on gold breakout' if date == '2026-04-14' else 'Screen stable; holdings confirmed'}

---

## Key Tickers to Monitor
- **IAU**: Gold at ${p['GOLD_OZ']:,}/oz — {'inflation + geopolitical bid; CORE holding' if p['GOLD_OZ'] > 4500 else 'Holding; thesis intact'}
- **SPY**: ${spy:.2f} — {'Risk-on; earnings season supporting' if spy > 670 else 'Cautious; awaiting macro resolution'}
- **EFA**: {'OPPORTUNITY — tariff pause + dollar weakness = international tailwind' if date >= '2026-04-09' else 'Not yet; binary risk unresolved'}
- **XLE**: {'AVOID/REDUCE — oil war premium unwinding; XLE heading lower' if p.get('XLE', 58) < 58.5 else 'WATCH — binary; war premium exit would trigger reduction'}

---

## Positioning summary
{'DEFENSIVE — hold BIL/SHY/IAU; minimal equity exposure; await binary resolution' if date <= '2026-04-07' else 'RISK-ON — add SPY; hold IAU (dual-bid); add EFA (tariff pause); reduce energy (XLE)'}
"""


# ---------------------------------------------------------------------------
# Document key resolution
# ---------------------------------------------------------------------------

SEGMENT_DOC_KEYS = {
    "macro": "deltas/macro.delta.md",
    "bonds": "deltas/bonds.delta.md",
    "commodities": "deltas/commodities.delta.md",
    "forex": "deltas/forex.delta.md",
    "crypto": "deltas/crypto.delta.md",
    "international": "deltas/international.delta.md",
    "us-equities": "deltas/us-equities.delta.md",
    "technology": "deltas/sectors/technology.delta.md",
    "healthcare": "deltas/sectors/healthcare.delta.md",
    "energy": "deltas/sectors/energy.delta.md",
    "financials": "deltas/sectors/financials.delta.md",
    "consumer-staples": "deltas/sectors/consumer-staples.delta.md",
    "consumer-disc": "deltas/sectors/consumer-disc.delta.md",
    "industrials": "deltas/sectors/industrials.delta.md",
    "utilities": "deltas/sectors/utilities.delta.md",
    "materials": "deltas/sectors/materials.delta.md",
    "real-estate": "deltas/sectors/real-estate.delta.md",
    "comms": "deltas/sectors/comms.delta.md",
    "sentiment-news": "deltas/sentiment-news.delta.md",
    "cta-positioning": "deltas/cta-positioning.delta.md",
    "options-derivatives": "deltas/options-derivatives.delta.md",
    "politician-signals": "deltas/politician-signals.delta.md",
    "institutional-flows": "deltas/institutional-flows.delta.md",
    "hedge-fund-intel": "deltas/hedge-fund-intel.delta.md",
    "opportunity-screen": "deltas/opportunity-screen.delta.md",
}


def generate_document(seg: str, date: str) -> str | None:
    p = PRICES.get(date)
    ctx = DAY_CONTEXT.get(date)
    if not p or not ctx:
        return None

    generators = {
        "macro": gen_macro,
        "bonds": gen_bonds,
        "commodities": gen_commodities,
        "forex": gen_forex,
        "crypto": gen_crypto,
        "international": gen_international,
        "us-equities": gen_us_equities,
        "sentiment-news": gen_sentiment_news,
        "cta-positioning": gen_cta_positioning,
        "options-derivatives": gen_options_derivatives,
        "politician-signals": gen_politician_signals,
        "institutional-flows": gen_institutional_flows,
        "hedge-fund-intel": gen_hedge_fund_intel,
        "opportunity-screen": gen_opportunity_screen,
    }

    if seg in generators:
        return generators[seg](date, p, ctx)
    elif seg in SECTOR_CONFIG:
        return gen_sector(seg, date, p, ctx)
    return None


def upsert_document(sb, seg: str, date: str, content: str, dry_run: bool) -> bool:
    doc_key = SEGMENT_DOC_KEYS.get(seg)
    if not doc_key:
        print(f"  SKIP: no doc key for {seg}")
        return False

    baseline_date = "2026-04-05" if date <= "2026-04-11" else "2026-04-12"
    payload = {
        "content": content,
        "date": date,
        "segment": seg,
        "doc_type": "Research Delta",
        "baseline_date": baseline_date,
        "run_type": "delta",
        "schema_version": "1.0",
    }

    if dry_run:
        print(f"  DRY-RUN: would upsert {doc_key} @ {date} ({len(content)} chars)")
        return True

    try:
        # Update BOTH the top-level content column AND the payload.
        # The frontend reads doc.content (top-level column) first (queries.ts line ~939).
        result = sb.table("documents").update(
            {"payload": payload, "content": content}
        ).eq("document_key", doc_key).eq("date", date).execute()

        if result.data:
            print(f"  ✓ Updated {doc_key} @ {date} ({len(content)} chars)")
            return True
        else:
            # Row doesn't exist yet — insert it
            row = {
                "document_key": doc_key,
                "date": date,
                "segment": seg,
                "doc_type": "Research Delta",
                "run_type": "delta",
                "category": "output",
                "content": content,
                "payload": payload,
            }
            sb.table("documents").upsert(row, on_conflict="document_key,date").execute()
            print(f"  ✓ Upserted {doc_key} @ {date} ({len(content)} chars)")
            return True
    except Exception as e:
        print(f"  ✗ Error for {doc_key} @ {date}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Regenerate research delta documents")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--segment", help="Process only this segment")
    parser.add_argument("--date", help="Process only this date")
    args = parser.parse_args()

    if not args.dry_run:
        if not _HAS_SB:
            print("ERROR: supabase not installed. Run: pip install supabase")
            sys.exit(1)
        sb = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"],
        )
    else:
        sb = None

    all_segments = list(SEGMENT_DOC_KEYS.keys())
    dates = [args.date] if args.date else DELTA_DATES
    segments = [args.segment] if args.segment else all_segments

    total = 0
    ok = 0
    for date in dates:
        print(f"\n{'='*60}")
        print(f"DATE: {date} — {DAY_CONTEXT[date]['headline']}")
        print(f"{'='*60}")
        for seg in segments:
            content = generate_document(seg, date)
            if content is None:
                print(f"  SKIP {seg} — no generator")
                continue
            total += 1
            success = upsert_document(sb, seg, date, content, args.dry_run)
            if success:
                ok += 1

    print(f"\n{'='*60}")
    print(f"COMPLETE: {ok}/{total} documents {'(DRY RUN)' if args.dry_run else 'upserted'}")


if __name__ == "__main__":
    main()
