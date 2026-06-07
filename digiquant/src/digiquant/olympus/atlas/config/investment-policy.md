# Investment policy (constraints)

**Canonical profile:** [`config/investment-profile.md`](investment-profile.md) — horizon, risk, sizing, and preferences live there.

**Purpose of this file:** gives agents and scripts a single label for “policy constraints” without duplicating long-form content. When in doubt, **`investment-profile.md` wins**.

## Non-negotiables (summary)

- Respect **§4 Risk Tolerance & Constraints** in `investment-profile.md` (position limits, leverage, derivatives).
- Respect **§3 Trade Frequency & Rebalancing** (no churn; materiality triggers).
- Portfolio validation: `scripts/validate-portfolio.sh` uses `config/portfolio.json` + profile constraints.

Do not maintain parallel policy tables here—update `investment-profile.md` and keep portfolio JSON aligned.
