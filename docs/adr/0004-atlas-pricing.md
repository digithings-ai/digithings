# ADR 0004: Atlas Pricing — Seat Tier + Metered Unit Cost

**Status:** accepted
**Date:** 2026-04-19

**Rationale for accepting:** All open questions in this ADR are deferred to post-GA validation rather than blocking — none require resolution before Phase 4/5 work (epics #10–13) can start. The two-axis pricing structure (seat + metered units), entitlement flow via DigiKey JWTs, and Stripe as billing provider are stable engineering decisions that downstream work can build against. Dollar figures and free-tier limits are explicitly illustrative and will be tuned once real usage data exists. Accepting unblocks billing integration, entitlement middleware, and Atlas UI copy.

## Context

Atlas is the commercial surface on top of DigiQuant (epic #12, tracked by issue #13 and related tasks). DigiQuant itself is open-core: the engine, strategy registry, and backtest harness live in this repository under a permissive license. Atlas layers research workflows, persisted outputs, hosted compute, and a polished UI on top — and is the planned revenue driver for the financial-AI vertical (see [`docs/VISION.md`](../VISION.md) → "Atlas tiering").

`docs/VISION.md` already commits to a **hybrid pricing model**: free batch tier + paid seats + metered API. Issue #28 asks for the *actual structure* — names, dimensions, illustrative numbers — so downstream work (billing integration, entitlement middleware, UI copy, sales collateral) can begin. Without a decided shape, epic #12 cannot execute.

Two things need to be fixed before execution:

1. **The dimensions of pricing** — what customers pay *for*. This is an engineering decision because it drives the data model (entitlements, meters, audit records) and must be stable even if dollar figures change.
2. **Illustrative starting numbers** — a concrete point of reference so billing plumbing, free-tier guardrails, and pricing-page copy can be built end-to-end. Actual numbers require market validation from first paying customers (see "Open questions").

## Decision

Atlas pricing has **two dimensions** combined in every paid plan:

1. **Seat** — a per-user monthly subscription. Grants access to the Atlas UI, persisted research, strategy slots, and an included allowance of metered units.
2. **Metered units** — measured consumption billed above the included allowance. Two meters for launch:
   - **Backtests run** (discrete unit — one backtest over one strategy over one date range).
   - **Optimize-hours** (continuous unit — compute time spent in parameter sweeps / walk-forward optimization, billed per minute, displayed as hours).

Every Atlas plan is `(seat_price) + (included_allowance) + (overage_rate_per_meter)`. Enterprise plans negotiate the allowance and overage rate; self-serve plans take published values.

### Launch tiers (illustrative — numbers require market validation)

| Tier | Seat / month | Included backtests | Included optimize-hours | Strategy slots | Backtest overage | Optimize overage |
|---|---|---|---|---|---|---|
| **Free** | $0 | 20 / month | 0 | 2 | — (hard cap) | — (hard cap) |
| **Atlas Pro** | $99 | 500 / month | 10 | 25 | $0.20 / backtest | $6 / hour |
| **Atlas Team** | $299 | 2,000 / month | 50 | 100 | $0.15 / backtest | $5 / hour |
| **Enterprise** | contact | negotiated | negotiated | unlimited | negotiated | negotiated |

The free tier is a hard cap (no overage billing — requests fail closed once the allowance is exhausted) so anonymous and trial users cannot generate surprise cost. Paid tiers meter overage and bill monthly in arrears.

Annual prepay discount: 2 months free (≈16.7%) on seat subscription. Metered overage is not discounted; it tracks unit cost.

These numbers are **explicitly a starting point**. They are sized off rough cost-per-run estimates at the target LiteLLM mode (`medium`) plus NautilusTrader backtest compute, with a margin placeholder. First-paying-customer feedback and a proper unit-economics pass (issue #28 "Inputs needed") will revise them before GA.

### Billing provider

Stripe. Self-serve checkout, Stripe-metered billing for overage, Stripe Customer Portal for plan changes. Invoices for Enterprise. No in-house billing code for non-negotiable reasons (PCI, chargebacks, tax — out of scope for a platform team).

### Entitlement flow

1. A buyer completes Stripe checkout; webhook lands on a new `atlas-billing` service.
2. `atlas-billing` writes the tenant's plan + allowances to the DigiKey tenant record and mints / updates a **scoped API key** (DigiKey already supports scoped keys — [see `digikey/`](../../digikey/)) with the plan's entitlement claims (`atlas.tier`, `atlas.backtests_included`, `atlas.optimize_hours_included`).
3. Atlas (and any DigiQuant endpoint that charges a meter) reads the entitlement claim from the presented JWT, checks live usage against the meter, and either serves, 402s (overage disabled), or records an overage event.
4. Overage events are written through `digibase.audit.redact_mapping` as immutable JSONL (see [`digibase/` audit pattern](../../digibase/)) *and* reported to Stripe as metered usage. The JSONL trail is the source of truth for disputes; Stripe is the source of truth for invoicing.

## Consequences

**Positive**
- Heavy-compute users pay proportionally; light users are not overcharged. Matches the cost structure of the underlying compute (backtests and optimize sweeps are the dominant cost drivers).
- Predictable *floor* (seat) plus scalable *ceiling* (metered). Customers can budget the floor and monitor the ceiling.
- Entitlement claims live in DigiKey JWTs — no new auth surface. Scoped-key mechanism already exists and is tested.
- Audit trail for metered units is free: `digibase.audit` already enforces the redact-then-append pattern.
- Stripe handles tax, dunning, PCI, and refunds. Zero in-house billing liability.

**Negative / tradeoffs**
- Two meters (backtests, optimize-hours) is more complex to communicate than a single unit. Pricing-page copy must make the distinction obvious.
- Metered billing means customers can be surprised by a bill. Mitigation: in-product usage dashboard, email alert at 80% / 100% of included allowance, optional hard-cap setting that converts overage-eligible tiers into free-tier behavior past the allowance.
- Entitlement enforcement must happen at *every* chargeable endpoint. A missing check is a revenue leak. Mitigation: entitlement middleware is a single library consumed by DigiQuant / Atlas handlers; CI requires every chargeable endpoint to declare its meter.
- Stripe webhook reliability is now on the critical path for entitlement updates. Mitigation: idempotent webhook handler + nightly reconciliation job against Stripe's API.

## Alternatives considered

1. **Flat subscription only (no metering).** Rejected. A single backtest-heavy customer can consume 10x the median customer's compute at the same price; light users effectively subsidize them and the unit economics invert past a small customer count.
2. **Pure metered (no seats).** Rejected. Unpredictable monthly bills make procurement impossible for quant-fund buyers (who need pre-approved budgets) and spook individual traders (who dislike "the meter is running" anxiety). Also removes the recurring-revenue floor needed for forecasting.
3. **Freemium only, no paid tier.** Rejected. No revenue path; contradicts `docs/VISION.md`'s commercial strategy for the financial-AI vertical.
4. **Token-based metering (per-LLM-token).** Considered. Rejected for launch because backtests and optimize-hours are more legible units for a quant buyer (they map to work, not to a model-internal detail) and because LLM token cost is a subset of — not a proxy for — total compute cost. Revisit if LLM cost dominates the unit economics.
5. **Per-domain-day metering** (Atlas research over N instrument-domains per day). Considered; noted in the VISION doc. Rejected for launch as too Atlas-specific — "backtest" and "optimize-hour" generalize across DigiQuant use beyond Atlas research runs. A research-specific meter can be added later without changing the structure.

## Open questions

- **Actual dollar figures.** The table above is illustrative. A unit-economics pass using real cost-per-run data from a working Atlas research subgraph (blocked on #10) is required before GA pricing. First-paying-customer feedback will set the anchor.
- **Free-tier limits.** 20 backtests / 2 strategy slots is a guess. Too generous and conversion suffers; too stingy and the free tier fails as a funnel. Instrument the free tier early and tune.
- **Enterprise tier definition.** What crosses the "contact us" threshold? Candidate triggers: SSO required, custom data connectors, on-prem deployment, > N seats, > Y metered units / month. Decide once two or three inbound enterprise conversations land.
- **Education / non-profit pricing.** Not addressed here. Likely a discount on Atlas Pro; revisit after launch.
- **Refund / grace policy for overage disputes.** Needs a written policy before self-serve metered billing goes live.

## Links

- Related: [ADR-0002 — Domain Unification](0002-domain-unification.md) (Atlas surface mounts at `digiquant.io/atlas`)
- Related: [`docs/VISION.md`](../VISION.md) → "Atlas tiering"
- Related: DigiKey scoped keys — [`digikey/`](../../digikey/)
- Related: Audit pattern — [`digibase/`](../../digibase/)
- Issue: #28 (this ADR), epic #12, dependency #10
