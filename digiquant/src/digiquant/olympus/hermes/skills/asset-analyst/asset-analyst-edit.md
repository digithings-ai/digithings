# Asset analyst — edit mode

Revise the prior ``analyst/{ticker}`` document via ``DocumentPatch`` ops. Do not
blind-rewrite — patch only stale sections (stance, cases, risks, targets) that
material signals changed.

Return ``DocumentPatch`` with ``target_document_key`` = ``analyst/{ticker}``.

Forecast lineage rules:
- Do **not** patch nested fields under ``/body/forecast/...``. To change economics,
  ``set`` the entire ``/body/forecast`` object with a complete ``ForecastTerms``
  replacement (or leave forecast untouched).
- Never patch ``/body/forecast_assessment`` — identity and provenance are
  system-owned and immutable.
