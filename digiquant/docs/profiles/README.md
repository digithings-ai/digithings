# Investment profiles + asset preferences + pipeline profiles

Three related but **distinct** schemas live under `digiquant.profiles`:

- **`InvestmentProfile`** — slow-moving *user intake* posture: risk tolerance, horizon, liquidity needs, base currency, tax jurisdiction, ESG stance, sector exclusions, experience level. DigiChat / UI profiling (#296 family).
- **`AssetPreferences`** — faster-moving *user* asset choices: named watchlists, custom universe, hard ticker exclusions, sector exclusions.
- **`ProfileConfig` / `PipelineProfile`** — Olympus Track B (#2607) *run policy*: universe, risk prefs, research themes, planner budgets. DB-backed (`olympus_pipeline_profiles`). digithings **house** profile/run is always-on and immutable; overlays plug into the **same** Atlas→Hermes graph (no forks). **Do not conflate** with `InvestmentProfile`.

`InvestmentProfile` / `AssetPreferences` are deliberately split: posture changes rarely, asset choices change frequently. `PipelineProfile` is orthogonal — it pins pipeline config at preflight under `OLYMPUS_PIPELINE_PROFILE_MODE` (`off` | `shadow` | `active`, default **`off`**). Shadow/off never expand H4 roster/cap or rewrite H7/H8 authority.

## Why versioned

Every model carries `schema_version: int = 1` independently. Storage layers (Supabase, Atlas runner state) persist these long-term, so adding or reshaping fields without a version field would silently corrupt older rows. The version field gives migrations a hook: on read, dispatch on `schema_version` and upgrade in place. The models version independently — bumping `InvestmentProfile` to v2 does not require bumping `ProfileConfig`.

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

### PipelineProfile / ProfileConfig (#2607)
- Models: [`digiquant/src/digiquant/profiles/pipeline_profile.py`](../../src/digiquant/profiles/pipeline_profile.py)
- Loader / preflight pin: [`digiquant/src/digiquant/profiles/pipeline_loader.py`](../../src/digiquant/profiles/pipeline_loader.py)
- Migration: [`supabase/migrations/075_olympus_pipeline_profiles.sql`](../../supabase/migrations/075_olympus_pipeline_profiles.sql)
- Tests: [`tests/dq/profiles/test_pipeline_profile.py`](../../../tests/dq/profiles/test_pipeline_profile.py), [`tests/dq/profiles/test_pipeline_loader.py`](../../../tests/dq/profiles/test_pipeline_loader.py), [`tests/dq/atlas/test_migration_075.py`](../../../tests/dq/atlas/test_migration_075.py)
- Hard rules: house run id `digithings-house-run`; overlays cannot cancel/replace it; no graph forks; shared-corpus WP12 / planner WP13 are hooks only in this seam.
