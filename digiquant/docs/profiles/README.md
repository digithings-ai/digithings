# Investment profiles + asset preferences

Two companion schemas live in `digiquant.profiles`:

- **`InvestmentProfile`** — slow-moving posture: risk tolerance, horizon, liquidity needs, base currency, tax jurisdiction, ESG stance, sector exclusions, experience level.
- **`AssetPreferences`** — faster-moving asset choices: named watchlists, custom universe, hard ticker exclusions, sector exclusions.

They are deliberately split: posture changes rarely (months/years), asset choices change frequently (days/weeks). Splitting simplifies cache invalidation and audit trails. Atlas / Hermes / Kairos consult both to filter idea generation, constrain deliberation, and shape portfolio construction.

The schemas are intentionally coarse. Per-portfolio limits (CVaR, factor caps, position-size rules) live on a policy object, not here. Tax detail (state, ISA, RRSP, PEA, etc.) is deferred to a future `TaxProfile`.

## Why versioned

Every model carries `schema_version: int = 1` independently. Storage layers (Supabase, Atlas runner state) persist these long-term, so adding or reshaping fields without a version field would silently corrupt older rows. The version field gives migrations a hook: on read, dispatch on `schema_version` and upgrade in place. The two models version independently — bumping `InvestmentProfile` to v2 does not require bumping `AssetPreferences`.

## How to extend

1. **Additive, non-breaking** — new field with a sensible default. Keep `schema_version=1`. Existing fixtures still validate.
2. **Breaking** — field removed, retyped, or semantics changed. Bump `schema_version` (e.g. to `2`), keep the v1 model behind it, and add a migration in `digiquant.profiles` that upgrades v1 payloads to v2 on read. Update `examples` and the exported JSON schema (`schemas/investment_profile.v{N}.json`).

Field validators live alongside the models. Both use `extra="forbid"` to catch typos at load time and shared normalization helpers (insertion-order-preserving de-duplication; tickers upper-cased; sectors lower-cased; whitespace stripped; empties dropped).

`AssetPreferences` runs one extra rule after field validation: **exclusion wins over inclusion**. Tickers in `excluded_tickers` are silently dropped from every watchlist and from `custom_universe`, even if the user lists them in both places. The drop is silent rather than a hard error because users edit lists incrementally and intermittent overlaps are expected.

## Pointers

### InvestmentProfile
- Model: [`digiquant/src/digiquant/profiles/investment_profile.py`](../../src/digiquant/profiles/investment_profile.py)
- JSON schema: [`schemas/investment_profile.v1.json`](../schemas/investment_profile.v1.json) — regenerate via `python3 scripts/export_profile_schema.py`
- Example fixture: [`tests/dq/profiles/fixtures/example_profile.json`](../../../tests/dq/profiles/fixtures/example_profile.json)
- Tests: [`tests/dq/profiles/test_investment_profile.py`](../../../tests/dq/profiles/test_investment_profile.py)

### AssetPreferences
- Model: [`digiquant/src/digiquant/profiles/asset_preferences.py`](../../src/digiquant/profiles/asset_preferences.py)
- JSON schema: [`schemas/asset_preferences.v1.json`](../schemas/asset_preferences.v1.json) — same export script
- Example fixture: [`tests/dq/profiles/fixtures/example_asset_preferences.json`](../../../tests/dq/profiles/fixtures/example_asset_preferences.json)
- Tests: [`tests/dq/profiles/test_asset_preferences.py`](../../../tests/dq/profiles/test_asset_preferences.py)
