# Asset analyst — full write

Produce a complete unified ``AnalystPayload`` for the ticker in ``phase_inputs``.

Required fields: conviction_score (−5..+5), stance, thesis, risks, fundamentals,
technicals, headwinds, tailwinds, bull_case, bear_case, price_targets (or null),
expectations, sources.

When ``roster_reason`` is not ``thesis_mapped``, author a vehicle-local investment
thesis in your output.
