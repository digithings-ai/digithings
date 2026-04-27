# Investment profiles

`digiquant.profiles.InvestmentProfile` is the canonical user-facing description of an investor's posture: risk tolerance, horizon, liquidity needs, base currency, coarse tax jurisdiction, ESG stance, excluded sectors, and self-reported experience. Atlas, Hermes, and Kairos consult it to filter idea generation, constrain deliberation, and shape portfolio construction.

The schema is intentionally coarse. Per-portfolio limits (CVaR, factor caps, position-size rules) live on a policy object, not here. Tax detail (state, ISA, RRSP, PEA, etc.) is deferred to a future `TaxProfile`.

## Why versioned

Every profile carries `schema_version: int = 1`. Storage layers (Supabase, Atlas runner state) persist profiles long-term, so adding or reshaping fields without a version field would silently corrupt older rows. The version field gives migrations a hook: on read, dispatch on `schema_version` and upgrade in place.

## How to extend

1. **Additive, non-breaking** — new field with a sensible default. Keep `schema_version=1`. Existing fixtures still validate.
2. **Breaking** — field removed, retyped, or semantics changed. Bump `schema_version` (e.g. to `2`), keep the v1 model behind it, and add a migration in `digiquant.profiles` that upgrades v1 payloads to v2 on read. Update `examples` and the exported JSON schema (`schemas/investment_profile.v{N}.json`).

Field validators live alongside the model in `digiquant/src/digiquant/profiles/investment_profile.py`. `excluded_sectors` is lower-cased, de-duplicated (insertion-order preserving), and stripped of empties. `base_currency` is upper-cased before pattern validation. `extra="forbid"` catches typos at load time rather than silently dropping them.

## Pointers

- Model: [`digiquant/src/digiquant/profiles/investment_profile.py`](../../src/digiquant/profiles/investment_profile.py)
- JSON schema: [`schemas/investment_profile.v1.json`](../schemas/investment_profile.v1.json) — regenerate via `python3 scripts/export_profile_schema.py`
- Example fixture: [`tests/dq/profiles/fixtures/example_profile.json`](../../../tests/dq/profiles/fixtures/example_profile.json)
- Tests: [`tests/dq/profiles/test_investment_profile.py`](../../../tests/dq/profiles/test_investment_profile.py)
