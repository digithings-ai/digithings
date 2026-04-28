---
name: profile-setup
description: >
  Interactive investment profile setup wizard. Triggers on "set up profile", "configure profile",
  "investment profile setup", "profile wizard", "customize my preferences", "onboarding".
  Walks the user through 8 sections of multiple-choice questions to populate
  config/investment-profile.md with their personal investment preferences.
---

# Investment Profile Setup Wizard

This skill runs an interactive interview (5-10 minutes) to configure `config/investment-profile.md`.
Present questions in batches of 3-5 using the ask-questions tool. Each question should offer
concrete options the user can select from, plus freeform input where appropriate.

---

## Pre-Flight

1. Read `config/investment-profile.md` to see current defaults
2. Inform the user: *"I'll walk you through 8 sections to build your investment profile. Each section has 2-5 questions with options to pick from. Takes about 5-10 minutes. Your answers will be saved to config/investment-profile.md and used by all agents going forward."*

---

## Interview Flow

Run each batch sequentially. After each batch, write the answers into `config/investment-profile.md`
before proceeding to the next batch. This ensures partial progress is saved.

### Batch 1: Investor Identity (§1)

Ask these questions with selectable options:

| # | Question | Options |
|---|----------|---------|
| 1 | Account type? | Taxable brokerage, TFSA, RRSP, Margin, Corporate, Multiple (specify) |
| 2 | Home currency? | CAD, USD, EUR, GBP, Other (specify) |
| 3 | Brokerage? | Interactive Brokers, Questrade, Wealthsimple, TD Direct, Schwab, Other (specify) |
| 4 | Tax jurisdiction? | Canada, USA, UK, EU, Other (specify) |

**After answers**: Update §1 table in `config/investment-profile.md`.

### Batch 2: Investment Horizon (§2)

| # | Question | Options |
|---|----------|---------|
| 5 | How long do you typically hold positions? | Days (day trader), 1-4 weeks (swing), 1-6 months (position), 6-12 months (intermediate), 1+ years (long-term) |
| 6 | Shortest acceptable hold? | 1 day, 1 week, 2 weeks, 1 month |
| 7 | Longest before forced reassessment? | 1 month, 3 months, 6 months, 1 year, No limit |
| 8 | Upcoming liquidity needs? | None, Within 6 months, Within 1 year, Ongoing withdrawals |

**After answers**: Update §2 table. Set minimum/maximum hold and liquidity fields.

### Batch 3: Trade Frequency (§3)

| # | Question | Options |
|---|----------|---------|
| 9 | How often should the system suggest rebalancing? | Weekly, Bi-weekly, Monthly, Only on regime changes |
| 10 | Max trades per rebalance cycle? | 1-2 (minimal), 3-4 (moderate), 5-6 (active), Unlimited |
| 11 | Smallest position change worth making? | 3% of portfolio, 5% of portfolio, 10% of portfolio |

**After answers**: Update §3 table.

### Batch 4: Risk Tolerance (§4)

| # | Question | Options |
|---|----------|---------|
| 12 | Overall risk tolerance? | Conservative (capital preservation first), Moderate (balanced growth/protection), Moderate-aggressive (growth-tilted, can handle volatility), Aggressive (max growth, comfortable with big swings) |
| 13 | Max portfolio drawdown you can stomach? | -5%, -10%, -15%, -20%, -25%, -30%+ |
| 14 | Max loss on a single position before exit? | -5%, -10%, -15%, -20%, No hard stop |
| 15 | Use VIX-based defensive rules? | Yes — VIX>30 reduce equity / VIX>40 max defensive, Yes — but custom thresholds (specify), No — I'll decide manually |
| 16 | Leverage or margin? | None, Light margin (<1.5x), Full margin, Options allowed |
| 17 | Open to ratio/spread trades (long/short ETF pairs)? | Yes, No |

**After answers**: Update §4A, §4B, §4C tables. Derive position sizing limits from risk tolerance:
- Conservative → max 15% single ETF, max 30% theme, min 20% cash
- Moderate → max 20% single ETF, max 35% theme, min 15% cash
- Moderate-aggressive → max 20% single ETF, max 40% theme, min 10% cash
- Aggressive → max 25% single ETF, max 50% theme, min 5% cash

### Batch 5: Asset Preferences (§5)

| # | Question | Options |
|---|----------|---------|
| 18 | What instruments do you trade? | ETFs only, ETFs + individual stocks, ETFs + crypto (direct), ETFs + futures, Everything |
| 19 | Crypto exposure method? | Spot ETFs only (IBIT/FBTC/ETHA), Direct custody + ETFs, No crypto, Other (specify) |

Then for each asset class, ask a preference rating (pick one).

**After answers**: Update §5A, §5B tables.

### Batch 6: Sector Preferences (§5C)

For each GICS sector, ask preference:

| Sector | Options |
|--------|---------|
| Technology, Health Care, Energy, Financials, Consumer Staples, Industrials, Utilities, Real Estate, Materials, Consumer Discretionary, Communication Services | Overweight, Neutral, Underweight, Avoid |

**After answers**: Update §5C table.

### Batch 7: Macro & Thematic (§6)

| # | Question | Options |
|---|----------|---------|
| 21 | Default stance when regime is unclear? | Heavy cash (80%+), Balanced defensive, Stay invested but hedge, Keep current positions |
| 22 | Structural themes to always consider? (multi-select) | Gold as permanent hedge, Energy as secular play, Cash is a position, Quality over beta, Crypto as asymmetric bet, Emerging market growth, Rate cycle plays, None specific |
| 23 | Hard avoids? (multi-select) | Leveraged/inverse ETFs, Meme stocks, Individual stock picking, Options/derivatives, Frontier/micro markets, High yield credit, None |

**After answers**: Update §6 tables.

### Batch 8: Analysis & Benchmarks (§7-8)

| # | Question | Options |
|---|----------|---------|
| 24 | Analysis delivery style? | Blunt and direct, Detailed and thorough, Bullet-point heavy, Conversational |
| 25 | Require confidence labels on recommendations? | Yes (high/medium/low on every call), Only on major calls, No |
| 26 | Primary benchmark? | S&P 500 (SPY), 60/40 (SPY/AGG), All-weather, Custom (specify) |
| 27 | How often should performance be reviewed? | Every digest, Weekly, Monthly, Quarterly |

**After answers**: Update §7 and §8 tables.

---

## Post-Interview

1. Write all answers to `config/investment-profile.md`
2. Show a summary: "Here's your profile — review and tell me if anything needs changing"
3. Display the completed profile in a compact format
4. Remind the user: "You can re-run this anytime by saying 'set up profile' or edit config/investment-profile.md directly"

---

## Output

No output file — this skill modifies `config/investment-profile.md` in place.

