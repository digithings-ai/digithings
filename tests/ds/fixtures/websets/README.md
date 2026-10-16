# Websets fixtures

Vendored inputs for the Phase D websets suite (`tests/ds/test_websets_*.py`). Scratch
paths (`/tmp/exa-review/`) never appear in code, tests, or docstrings; these files are
the stable copies. Values are sanitized: no API keys, tokens, or bearer values are
stored here.

- `s5_category_company.json` — live EXA `/search` response (type=auto, category=company,
  numResults=3, query "agtech companies in the US that raised series A"), observed
  2026-09-14 during the earlier review against the operator's free-tier key
  (`requestId 97792aab5a5323b7e4c74a5381d9ce7e`, cost $0.007). Shapes and numbers are
  verbatim (NuCicer $16M total / Series A 2025-07-01 $11.5M; Pollen Systems $3.45M;
  Orchard $26.4M); the only scrub is the EXA `image` field, set to `null` because the
  LinkedIn media URLs it carried embed signed query tokens. Live re-validation was **not
  performed** by the Phase D Task 8 record (no live stack/EXA key in that env — see
  `digisearch/ARCHITECTURE.md` § Phase D live verification record); re-check the sample against
  a keyed `/search` call when the live record is re-run.
- `exa_401_pro_required.json` — frozen from the spec quote (`401: Upgrade to a Pro plan`)
  and the landed adapter/tests convention; the raw live body was observed but not
  persisted during the earlier probe, so this is a spec-frozen static fixture, not a
  captured payload. Live re-validation is tracked by the EXA live-pin follow-up (#4123).
- `fx_ecb_snapshot.json` — ECB euro foreign exchange reference rates fetched from the
  official daily feed on 2026-09-15 (`reference_date 2026-09-15`); rates are currency
  units per 1 EUR per the documented `convention` field. The offline default for Phase D
  funding normalization. Re-validated during the Task 8 live record (2026-09-15): the
  live feed still served `reference_date 2026-09-15` with all 29 rates identical, so the
  vendored payload is unchanged; re-fetch and bump both dates once a later reference
  date is published.
