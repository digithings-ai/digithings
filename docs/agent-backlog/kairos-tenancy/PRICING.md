# digiquant consumer pricing (Stripe + UI)

> **Status:** implemented 2026-09-01. Live Stripe catalog is Brief / Desk /
> Studio at **$10 / $30 / $100** per month (annual = ten months — two months
> free). Observer stays free and is not a Stripe product. Enterprise is invoice.
>
> Product surface is **digiquant**. Stripe product names match the Billing tab
> and locked-state copy. Internal house-run jargon (**baseline** = the house
> book, not a SKU) stays in code and research docs.
>
> Annual is shown as a **percent off the monthly list**: equivalent `$/mo` with
> the monthly list struck through and `N% off`, plus `billed $N/yr`. Checkout
> defaults to annual; the toggle still offers monthly.

## Why not the old SKU names

| Avoid as a Stripe product | Why |
|---------------------------|-----|
| **Baseline** | Already means the house book / house pipeline (delta-vs-baseline dates, `profile_key=house`). A $5 SKU named Baseline will collide with “full house glass-box” in agent and UI copy. |
| **Basic / Beginner** | Sounds like a cut of a real product. Condescending on a PM desk. |
| **Pro** | Generic; [Koyfin retired Pro](https://www.koyfin.com/help/pro-discontinuation/) and renamed the research path Premium. We would outgrow it the same way. |
| **Custom** | Sounds like a quote / professional-services SKU, not a self-serve plan. Keep “custom overlay” as the *capability*, not the product name. |
| **Observer** | Free teaser. Not a paid product. |
| **olympus** | Retired in product UI. |

## Ladder (live)

Four rungs: one free teaser, three paid. Each paid rung buys a **deeper cut of the same house**, then the right to run your own.

| Stripe + UI name | Internal id | Monthly | Annual (2 months free) | What you get |
|------------------|-------------|---------|------------------------|--------------|
| **Observer** | `free` | $0 | — | Teaser: digest *conclusions* + portfolio *names*. No weights, no pipeline, no brokers. Not a Stripe product. |
| **Brief** | `brief` | **$10** | $100 ($8.33/mo) | Full daily **digest** + **house portfolio** (weights / NAV). Summary outputs only. No pipeline canvas, no brokers, no overlay. |
| **Desk** | `desk` | **$30** | $300 ($25/mo) | Everything in Brief, plus the **full house pipeline** (research, deliberation, glass-box). **Paper broker connect.** |
| **Studio** | `studio` | **$100** | $1000 ($83.33/mo) | Everything in Desk, plus **your overlay pipeline**, private book, BYOK. |
| **Enterprise** | `enterprise` | invoice | — | Seats / SLA. Not self-serve. |

Observer stays free so Brief is not selling the same teaser twice. Billing UI
shows annual as **17% off** the monthly list (equivalent `$ /mo` vs struck
`$ /mo`), billed yearly.

The earlier $9 / $29 / $99 recommendation was a list-price nudge. Live products shipped at round tens; changing a Stripe *price* later is easy; do not rename the products.

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

1. **Brief** — “Daily house digest and house portfolio.” Recurring $10 / month. Annual $100 (two months free). Metadata `plan_tier=brief`.
2. **Desk** — “Full house pipeline, research, and paper broker connect.” Recurring $30 / month. Annual $300. Metadata `plan_tier=desk`.
3. **Studio** — “Your overlay pipeline, private book, and BYOK.” Recurring $100 / month. Annual $1000. Metadata `plan_tier=studio`.

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

Today’s Edge Functions read `STRIPE_PRICE_BRIEF_*` / `STRIPE_PRICE_DESK_*` /
`STRIPE_PRICE_STUDIO_*` and map to `plan_tier=brief|desk|studio`. Do **not**
name Stripe products Baseline, Custom, or Observer. Apply **migration 115**
before the webhook writes the new ids (old CHECKs reject them).

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

## Follow-up (ops)

- Apply migration 115 on `core`; set EF secrets from `.local/secrets/digithings-stripe.env`; redeploy `stripe-webhook`, `create-checkout-session`, `customer-portal`.
- Do not `--apply` cutover 113/900 from this hop.
