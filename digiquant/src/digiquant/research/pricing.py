"""Token-derived USD estimates for the house model slugs (#4596).

The house upstream reports no per-call cost, so ``digigraph.usage`` collapses "unknown" to
``0.0`` and ``run_diagnostics.est_cost_usd`` read ``$0`` on every run — the spend alert in
:mod:`digiquant.research.telemetry` could never fire. This module supplies the fallback: a
small, committed per-model price table and :func:`estimate_cost_usd`, which sums the tokens
actually recorded per model at those prices.

**Honesty rules.** The table is deliberately tiny and hand-maintained — it is not a live
feed. It prices only the house slugs listed in ``config/digiquant_models.yaml`` and only
those whose price the repo's own committed snapshot corroborates; :func:`estimate_cost_usd`
returns ``None`` when no tokens were priced rather than fabricating ``$0.00``, so "unpriced"
and "genuinely free" stay distinguishable. Unknown models are ignored, not guessed.

**Source of the committed numbers.** Each row is taken verbatim from the corresponding
committed ``docs/providers/snapshots/<provider>.yaml``, field
``paid_tier.models[].cost_per_1m_input`` / ``cost_per_1m_output`` (USD per 1M tokens):

- ``deepseek/deepseek-v4-flash`` — ``deepseek.yaml`` (``last_checked: 2026-08-30``), 0.07 / 0.28
- ``deepseek/deepseek-v4-pro`` — ``deepseek.yaml``, **peak** rate 1.32 / 3.96. The snapshot
  repurposed its ``*_long`` fields for the off-peak figures (0.66 / 1.98) after the
  2026-08-16 peak/off-peak switch; the peak rate is committed here because an estimate that
  systematically understates the one model whose price tripled would defeat the alert it
  exists to make fire.
- ``openai/gpt-5.6-luna`` — ``openai.yaml`` (``last_checked: 2026-07-19``), 1.00 / 6.00
- ``openai/gpt-5.6-sol`` — ``openai.yaml``, 5.00 / 30.00

``google/gemini-3.7-flash`` is a house slug with **no price here**: it is absent from the
committed ``docs/providers/snapshots/gemini.yaml`` (the snapshot predates the model), so
there is no in-repo source to cite. It is recorded in :data:`_UNPRICED_SLUGS` and will be
priced when the snapshot is refreshed.

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
# and date of each number; do not add a slug without a snapshot-corroborated price.
MODEL_PRICES_USD_PER_1M: dict[str, ModelPrice] = {
    "deepseek/deepseek-v4-flash": ModelPrice(0.07, 0.28),
    "deepseek/deepseek-v4-pro": ModelPrice(1.32, 3.96),
    "openai/gpt-5.6-luna": ModelPrice(1.00, 6.00),
    "openai/gpt-5.6-sol": ModelPrice(5.00, 30.00),
}

# House slugs deliberately left unpriced: each is absent from the committed snapshot for its
# provider, so the repo has no source for a number. ``google/gemini-3.7-flash`` postdates the
# committed ``docs/providers/snapshots/gemini.yaml``; it moves into the table when that
# snapshot is refreshed. Do not invent a price to clear the policy-coverage test.
_UNPRICED_SLUGS: frozenset[str] = frozenset({"google/gemini-3.7-flash"})


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
    """Estimate the USD cost of *by_model*, or ``None`` when no tokens were priced.

    *by_model* is the per-model split from ``digigraph.usage`` — each value carries
    ``prompt_tokens`` / ``completion_tokens``. Only models with a committed price contribute;
    unknown models are ignored, never counted as ``0``. The result keys on **tokens**, not on
    model-name recognition: an input whose only priced entries carry zero (or junk) tokens
    returns ``None``, so a priced-but-empty entry cannot masquerade as a real ``$0.00``.
    """
    if not isinstance(by_model, Mapping):
        return None
    total = 0.0
    priced_tokens = 0
    for model, usage in by_model.items():
        if not isinstance(usage, Mapping):
            continue
        price = MODEL_PRICES_USD_PER_1M.get(model)
        if price is None:
            continue
        prompt = _nonnegative_int(usage.get("prompt_tokens"))
        completion = _nonnegative_int(usage.get("completion_tokens"))
        priced_tokens += prompt + completion
        total += prompt / 1_000_000 * price.prompt_usd_per_1m
        total += completion / 1_000_000 * price.completion_usd_per_1m
    if priced_tokens == 0:
        return None
    return round(total, 6)


__all__ = [
    "MODEL_PRICES_USD_PER_1M",
    "ModelPrice",
    "estimate_cost_usd",
    "price_for",
]
