# digiquant consumer pricing (Stripe + UI)

> **Status:** proposed 2026-09-01. Owner pick before creating Stripe products.
> Amends D1 display names and the paid ladder. Does **not** yet change
> `workspaces.plan_tier` (`free | baseline | custom | enterprise`) — that is a
> follow-up entitlement hop after the names lock.
>
> Product surface is **digiquant**. Stripe product names must match the Billing
> tab and locked-state copy. Internal house-run jargon (**baseline** = the house
> book, not a SKU) stays in code and research docs.

## Why not the old SKU names

| Avoid as a Stripe product | Why |
|---------------------------|-----|
| **Baseline** | Already means the house book / house pipeline (delta-vs-baseline dates, `profile_key=house`). A $5 SKU named Baseline will collide with “full house glass-box” in agent and UI copy. |
| **Basic / Beginner** | Sounds like a cut of a real product. Condescending on a PM desk. |
| **Pro** | Generic; [Koyfin retired Pro](https://www.koyfin.com/help/pro-discontinuation/) and renamed the research path Premium. We would outgrow it the same way. |
| **Custom** | Sounds like a quote / professional-services SKU, not a self-serve plan. Keep “custom overlay” as the *capability*, not the product name. |
| **Observer** | Free teaser. Not a paid product. |
| **olympus** | Retired in product UI. |

## Ladder (recommended)

Four rungs: one free teaser, three paid. Each paid rung buys a **deeper cut of the same house**, then the right to run your own.

| Stripe + UI name | Internal id (next hop) | Monthly | Annual (2 months free) | What you get |
|------------------|------------------------|---------|------------------------|--------------|
| **Observer** | `free` | $0 | — | Teaser: digest *conclusions* + portfolio *names*. No weights, no pipeline, no brokers. Not a Stripe product. |
| **Brief** | `brief` | **$9** | $90 | Full daily **digest** + **house portfolio** (weights / NAV). Summary outputs only. No pipeline canvas, no brokers, no overlay. |
| **Desk** | `desk` | **$29** | $290 | Everything in Brief, plus the **full house pipeline** (research, deliberation, glass-box). **Paper broker connect.** |
| **Studio** | `studio` | **$99** | $990 | Everything in Desk, plus **your overlay pipeline**, private book, BYOK. |
| **Enterprise** | `enterprise` | invoice | — | Seats / SLA. Not self-serve. |

Observer stays free so Brief is not selling the same teaser twice.

### Owner’s $5 / $20 / $100

The *shape* is right (letter → glass-box → own pipeline). List prices above nudge each rung:

- **$9 not $5.** $5 is the [Substack median](https://nicheindex.co/what-to-charge-substack) for a newsletter, not a portfolio product. Stripe’s $0.30 flat fee is ~6% of a $5 charge; blended card+Billing rate on $5 is near 9% ([budgetforge ticket table](https://www.budgetforge.dev/tools/blended-stripe-rate-by-average-ticket-2026)). $9 still feels impulse-cheap and nets more.
- **$29 not $20.** Desk *is* the product (daily PM glass-box). Comps for “see the work / connect a book”: [Koyfin Plus $39/mo annual](https://www.koyfin.com/pricing-llm-info/), [Unusual Whales from $50/mo](https://unusualwhales.com/lp/unusual-whales-pricing), [Composer Trading Pass $40/mo](https://www.anygen.io/showcase/composer-trade-review/index.html), [QuantConnect Researcher $84/mo](https://www.quantconnect.com/pricing/?billing=mo). $20 underprices the IP and puts broker-support cost on a coffee-money SKU.
- **$99 not $100.** Same rung as [Koyfin Premium $79–$110/mo](https://www.koyfin.com/pricing-llm-info/). $99 is the classic self-serve top; $129 if overlay compute ever surprises us.

If you want rounder test-mode numbers, use **$9 / $29 / $99** anyway — changing a Stripe *price* later is easy; changing a *product name* after Checkout exists is messy.

## Name set (locked proposal)

**Brief / Desk / Studio.**

- **Brief** = the letter (digest) plus the book snapshot. Matches “summary outputs.”
- **Desk** = sit at the house desk: pipeline, deliberation, paper brokers. Login copy already says “desk.”
- **Studio** = run your own process on top of the house.

Runner-up if Brief feels too editorial: **Digest / Glassbox / Overlay**. Do not mix the two sets.

## Stripe catalog (type this)

Test mode. Recurring USD. Product name = UI name.

1. **Brief** — “Daily house digest and house portfolio.” Recurring $9 / month. Optional annual $90. Metadata `plan_tier=brief`.
2. **Desk** — “Full house pipeline, research, and paper broker connect.” Recurring $29 / month. Optional annual $290. Metadata `plan_tier=desk`.
3. **Studio** — “Your overlay pipeline, private book, and BYOK.” Recurring $99 / month. Optional annual $990. Metadata `plan_tier=studio`.

Paste the `price_…` ids into `.local/secrets/digithings-stripe.env` as:

```
STRIPE_PRICE_BRIEF_MONTHLY=price_…
STRIPE_PRICE_DESK_MONTHLY=price_…
STRIPE_PRICE_STUDIO_MONTHLY=price_…
# optional annuals
STRIPE_PRICE_BRIEF_ANNUAL=price_…
STRIPE_PRICE_DESK_ANNUAL=price_…
STRIPE_PRICE_STUDIO_ANNUAL=price_…
```

Today’s Edge Functions still read `STRIPE_PRICE_BASELINE_*` / `STRIPE_PRICE_CUSTOM_*` and map to `plan_tier=baseline|custom`. **Do not** name the Stripe products Baseline or Custom. After this doc is accepted, a follow-up hop adds `brief`, remaps Desk←today’s baseline surfaces + paper brokers, Studio←today’s custom, and switches the env names.

## What this changes vs D1 / SETTINGS-IA

| Capability | Today (D1) | This ladder |
|------------|------------|-------------|
| Digest conclusions + names | Observer | Observer |
| Full digest + house weights / NAV | Baseline | **Brief** |
| House pipeline / glass-box | Baseline | **Desk** |
| Paper broker connect | Custom only | **Desk** |
| Overlay / private book / BYOK | Custom | **Studio** |

Paper broker on Desk is the one entitlement move. Live trading stays human-gated and off this ladder.

## Comps (2026)

| Product | Paid rungs (monthly) | Notes |
|---------|----------------------|-------|
| [Koyfin](https://www.koyfin.com/pricing-llm-info/) | Plus $39, Premium $79, Advisor $209+ (annual list) | Research terminal. Plus ≈ “use our data”; Premium ≈ “build your own.” |
| [Seeking Alpha](https://traderhq.com/seeking-alpha-premium-vs-seeking-alpha-pro/) | Premium ~$25 ($299/yr), Pro $200 ($2,400/yr) | Newsletter + ratings vs institutional extras. |
| [Unusual Whales](https://unusualwhales.com/lp/unusual-whales-pricing) | from $50; Pro $75; Max $120 | Flow data, not a PM glass-box. |
| [Composer](https://www.anygen.io/showcase/composer-trade-review/index.html) | Trading Pass $40 ($32 annual) | Automate *your* strategy. |
| [QuantConnect](https://www.quantconnect.com/pricing/?billing=mo) | Researcher $84 | Compute + live nodes. |
| [Substack paid](https://nicheindex.co/what-to-charge-substack) | median $5 | Letter only. Brief is a letter *plus a book*. |

ADR-0004’s Atlas Pro $99 / Team $299 is the **metered API** seat table, not this consumer ladder.

## Follow-up (not this doc)

- Enum + RLS + `entitlements.ts` + settings Billing copy + checkout EF (three paid tiers).
- Do not `--apply` Stripe secrets until the owner confirms the file.
