# Investment profiles + asset preferences + pipeline schedule

Schemas in `digiquant.profiles`:

- **`InvestmentProfile`** — slow-moving posture: risk tolerance, horizon, liquidity needs, base currency, tax jurisdiction, ESG stance, sector exclusions, experience level.
- **`AssetPreferences`** — faster-moving asset choices: named watchlists, custom universe, hard ticker exclusions, sector exclusions.
- **`PipelineSchedule`** — seven weekdays × `research` / `deliberation` / `execution` booleans for the one daily graph. Defaults enable all three stages every day.
- **`ExecutionPolicy`** — calendar/session mode, permitted venues, and closed-session behavior. Distinct from `digiquant.dashboard.replay.models.ExecutionPolicy` (replay fill assumptions). v1 locks `calendar_mode=venue_calendar` and `on_closed_session=defer`: a scheduled execution day never overrides a closed market.

`InvestmentProfile` / `AssetPreferences` are deliberately split: posture changes rarely (months/years), asset choices change frequently (days/weeks). `PipelineSchedule` / `ExecutionPolicy` are the workspace scheduling companion pair — schedule is user intent; execution policy encodes the non-bypassable calendar veto.

The schemas are intentionally coarse. Per-portfolio limits (CVaR, factor caps, position-size rules) live on a policy object, not here. Tax detail (state, ISA, RRSP, PEA, etc.) is deferred to a future `TaxProfile`.

## DB-backed ProfileConfig (Track B / #2609)

Runtime pins live in `digiquant.dashboard.profile_config.ProfileConfig` and the private
`olympus_profile_config` table (migration `075`). Preflight resolves an exact
`version_id` (or the house default). Nested optional fields include
`InvestmentProfile`, `AssetPreferences`, `PipelineSchedule`, and `ExecutionPolicy`
inside the append-only payload — they are not a second graph or a replacement for
the digithings house run. No new table is required for schedule/policy (#3611).

## Why versioned

Every model carries `schema_version: int = 1` independently. Storage layers (Supabase, research runner state) persist these long-term, so adding or reshaping fields without a version field would silently corrupt older rows. The version field gives migrations a hook: on read, dispatch on `schema_version` and upgrade in place. The models version independently — bumping `InvestmentProfile` to v2 does not require bumping `AssetPreferences` or `PipelineSchedule`.

## How to extend

1. **Additive, non-breaking** — new field with a sensible default. Keep `schema_version=1`. Existing fixtures still validate.
2. **Breaking** — field removed, retyped, or semantics changed. Bump `schema_version` (e.g. to `2`), keep the v1 model behind it, and add a migration in `digiquant.profiles` that upgrades v1 payloads to v2 on read. Update `examples` and the exported JSON schema (`schemas/investment_profile.v{N}.json`).

Field validators live alongside the models. Models use `extra="forbid"` to catch typos at load time and shared normalization helpers (insertion-order-preserving de-duplication; tickers upper-cased; sectors lower-cased; whitespace stripped; empties dropped).

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

### PipelineSchedule + ExecutionPolicy (#3611)
- Models: [`pipeline_schedule.py`](../../src/digiquant/profiles/pipeline_schedule.py), [`execution_policy.py`](../../src/digiquant/profiles/execution_policy.py)
- JSON schemas: [`schemas/pipeline_schedule.v1.json`](../schemas/pipeline_schedule.v1.json), [`schemas/execution_policy.v1.json`](../schemas/execution_policy.v1.json)
- Tests: [`tests/dq/profiles/test_pipeline_schedule.py`](../../../tests/dq/profiles/test_pipeline_schedule.py)
- Mirrored validators: Deno `digiquant/supabase/functions/_shared/profile-schemas.ts` and dashboard `frontend/dashboard/lib/settings/validate-profile.ts`
