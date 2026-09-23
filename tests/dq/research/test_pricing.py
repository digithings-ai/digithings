"""Token-derived cost estimate (#4596) — the fallback when the provider reports no cost.

``run_diagnostics.est_cost_usd`` was always ``0.0`` because the house upstream reports no
per-call cost and the aggregation collapses "unknown" to zero. The column is *named*
``est_cost_usd``, so an estimate was always the intended semantic. This module pins the
estimator's two load-bearing properties: it sums the committed per-model prices over the
tokens actually recorded, and it never fabricates a number for a model it cannot price.
"""

from __future__ import annotations

import pytest
from digiquant.research.pricing import (
    MODEL_PRICES_USD_PER_1M,
    estimate_cost_usd,
    price_for,
)

pytestmark = pytest.mark.unit

_HOUSE_SLUGS = (
    "deepseek/deepseek-v4-flash",
    "deepseek/deepseek-v4-pro",
    "google/gemini-3.7-flash",
    "openai/gpt-5.6-luna",
    "openai/gpt-5.6-sol",
)


class TestThePriceTable:
    def test_covers_every_house_slug_in_the_model_policy(self) -> None:
        for slug in _HOUSE_SLUGS:
            assert price_for(slug) is not None, slug
            assert slug in MODEL_PRICES_USD_PER_1M

    def test_an_unknown_model_has_no_price(self) -> None:
        assert price_for("made-up/model") is None

    def test_every_committed_price_is_a_positive_pair(self) -> None:
        for slug, price in MODEL_PRICES_USD_PER_1M.items():
            assert price.prompt_usd_per_1m > 0, slug
            assert price.completion_usd_per_1m > 0, slug


class TestEstimateCostUsd:
    def test_sums_prompt_and_completion_tokens_at_the_committed_prices(self) -> None:
        # deepseek-v4-flash: 1M prompt * $0.15 + 1M completion * $0.60 = $0.75
        # gpt-5.6-luna:      2M prompt * $0.20                       = $0.40
        estimate = estimate_cost_usd(
            {
                "deepseek/deepseek-v4-flash": {
                    "calls": 1,
                    "prompt_tokens": 1_000_000,
                    "completion_tokens": 1_000_000,
                },
                "openai/gpt-5.6-luna": {
                    "calls": 1,
                    "prompt_tokens": 2_000_000,
                    "completion_tokens": 0,
                },
            }
        )
        assert estimate == pytest.approx(1.15)

    def test_returns_none_when_no_model_has_a_known_price(self) -> None:
        """Never fabricate: an unpriced run estimates nothing rather than $0.00, so the caller
        can tell "unknown" apart from "genuinely free"."""
        assert (
            estimate_cost_usd(
                {"made-up/model": {"prompt_tokens": 10_000, "completion_tokens": 5_000}}
            )
            is None
        )
        assert estimate_cost_usd({}) is None

    def test_ignores_unknown_models_but_still_sums_the_known_ones(self) -> None:
        estimate = estimate_cost_usd(
            {
                "made-up/model": {"prompt_tokens": 9_999_999, "completion_tokens": 9_999_999},
                "openai/gpt-5.6-sol": {"prompt_tokens": 1_000_000, "completion_tokens": 0},
            }
        )
        assert estimate == pytest.approx(4.00)

    def test_a_known_model_with_zero_tokens_is_a_zero_estimate_not_none(self) -> None:
        assert (
            estimate_cost_usd({"openai/gpt-5.6-luna": {"prompt_tokens": 0, "completion_tokens": 0}})
            == 0.0
        )

    @pytest.mark.parametrize(
        "usage",
        [
            {"prompt_tokens": None, "completion_tokens": "x"},
            {"prompt_tokens": -5, "completion_tokens": -5},
            {"prompt_tokens": True, "completion_tokens": False},
            {"prompt_tokens": float("nan"), "completion_tokens": float("inf")},
        ],
    )
    def test_junk_token_values_are_treated_as_zero_not_raised(self, usage: dict) -> None:
        """``by_model`` comes from an untyped fail-soft snapshot, so its values can be absent or
        junk. A telemetry estimate must never raise into the run's exit path."""
        assert estimate_cost_usd({"openai/gpt-5.6-luna": usage}) == 0.0

    def test_a_non_mapping_usage_entry_is_skipped(self) -> None:
        assert estimate_cost_usd({"openai/gpt-5.6-luna": "nope"}) is None  # type: ignore[dict-item]
