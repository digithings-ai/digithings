"""Token-derived USD estimates for the house model slugs (#4596).

The house upstream reports no per-call cost, so ``digigraph.usage`` collapses "unknown" to
``0.0`` and ``run_diagnostics.est_cost_usd`` read ``$0`` on every run — the spend alert in
:mod:`digiquant.research.telemetry` could never fire. This module supplies the fallback: a
small, committed per-model price table and :func:`estimate_cost_usd`, which sums the tokens
actually recorded per model at those prices.

**Honesty rules.** The table is deliberately tiny and hand-maintained — it is not a live
feed. It prices only the house slugs listed in ``config/digiquant_models.yaml`` and only
those whose price could be verified; :func:`estimate_cost_usd` returns ``None`` when *no*
model in the input has a known price rather than fabricating ``$0.00``, so "unpriced" and
"genuinely free" stay distinguishable. Unknown models are ignored, not guessed.

**Source of the committed numbers.** ``https://models.dev/catalog.json``, fetched
2026-09-23, first-party vendor entries (``deepseek``, ``google``, ``openai``). One
deliberate exception: models.dev's first-party ``deepseek`` entry still carries the retired
flat rate ($0.435/$0.87) for ``deepseek-v4-pro``, while the repo's own
``docs/providers/snapshots/deepseek.yaml`` (``last_checked: 2026-08-30``) records the
current effective price (peak $1.32/$3.96, off-peak $0.66/$1.98, effective 2026-08-16).
The **peak** rate is committed here: an estimate that systematically understates the one
model whose price tripled would defeat the alert it exists to make fire.

**Scope.** Prompt + completion tokens only. Cached prompt tokens are billed at the full
prompt rate — cache-hit discounts are provider- and model-specific and not always reported,
so this is a deliberate upper bound rather than a fabricated discount. Prices are USD per
1,000,000 tokens; :func:`estimate_cost_usd` rounds to 6 dp, matching ``cost_usd``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    """USD per 1,000,000 prompt / completion tokens for one model slug."""

    prompt_usd_per_1m: float
    completion_usd_per_1m: float


# House slugs from ``config/digiquant_models.yaml``. See the module docstring for the source
# and date of each number; do not add a slug without a verifiable price.
MODEL_PRICES_USD_PER_1M: dict[str, ModelPrice] = {
    "deepseek/deepseek-v4-flash": ModelPrice(0.15, 0.60),
    "deepseek/deepseek-v4-pro": ModelPrice(1.32, 3.96),
    "google/gemini-3.7-flash": ModelPrice(0.75, 3.75),
    "openai/gpt-5.6-luna": ModelPrice(0.20, 1.20),
    "openai/gpt-5.6-sol": ModelPrice(4.00, 20.00),
}


def price_for(model: str) -> ModelPrice | None:
    """The committed price for *model*, or ``None`` when it is not in the table."""
    return MODEL_PRICES_USD_PER_1M.get(model)


def _nonnegative_int(value: object) -> int:
    """Coerce a snapshot token count to a non-negative int; junk and bools become 0."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float) and math.isfinite(value):
        return max(int(value), 0)
    return 0


def estimate_cost_usd(by_model: Mapping[str, Mapping[str, object]]) -> float | None:
    """Estimate the USD cost of *by_model*, or ``None`` when nothing is priced.

    *by_model* is the per-model split from ``digigraph.usage`` — each value carries
    ``prompt_tokens`` / ``completion_tokens``. Only models with a committed price contribute;
    an unpriced-only input returns ``None`` (never fabricate). A priced model with zero tokens
    contributes ``0.0``, which is a real estimate, not an absence.
    """
    total = 0.0
    priced = False
    for model, usage in by_model.items():
        if not isinstance(usage, Mapping):
            continue
        price = MODEL_PRICES_USD_PER_1M.get(model)
        if price is None:
            continue
        prompt = _nonnegative_int(usage.get("prompt_tokens"))
        completion = _nonnegative_int(usage.get("completion_tokens"))
        total += prompt / 1_000_000 * price.prompt_usd_per_1m
        total += completion / 1_000_000 * price.completion_usd_per_1m
        priced = True
    if not priced:
        return None
    return round(total, 6)


__all__ = [
    "MODEL_PRICES_USD_PER_1M",
    "ModelPrice",
    "estimate_cost_usd",
    "price_for",
]
