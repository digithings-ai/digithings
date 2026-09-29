"""Token-derived cost estimate (#4596) — the fallback when the provider reports no cost.

``run_diagnostics.est_cost_usd`` was always ``0.0`` because the house upstream reports no
per-call cost and the aggregation collapses "unknown" to zero. The column is *named*
``est_cost_usd``, so an estimate was always the intended semantic. This module pins the
estimator's two load-bearing properties: it sums the committed per-model prices over the
tokens actually recorded, and it never fabricates a number for a model it cannot price.

The provenance test is the important one: the committed table is not trusted on its own
word, it is checked against the repo's own ``docs/providers/snapshots/*.yaml``. Editing a
price to a value no snapshot corroborates makes that test fail.
"""

from __future__ import annotations

import glob
from pathlib import Path

import pytest
import yaml
from digiquant.research.pricing import (
    _UNPRICED_SLUGS,
    MODEL_PRICES_USD_PER_1M,
    estimate_cost_usd,
    price_for,
)

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SNAPSHOTS_GLOB = str(_REPO_ROOT / "docs" / "providers" / "snapshots" / "*.yaml")
_MODELS_CONFIG = _REPO_ROOT / "config" / "digiquant_models.yaml"


def _snapshot_prices_by_bare_name() -> dict[str, set[tuple[float, float]]]:
    """Bare model name -> the set of (input, output) prices the snapshots corroborate.

    A set rather than a single pair because the same bare name can appear in several
    provider snapshots (a hosted open-weight model is resold at different rates). The house
    rows must match *one* of them, and a wrong edit matches none.
    """
    prices: dict[str, set[tuple[float, float]]] = {}
    for path in sorted(glob.glob(_SNAPSHOTS_GLOB)):
        snapshot = yaml.safe_load(Path(path).read_text())
        if not isinstance(snapshot, dict):
            continue
        paid = snapshot.get("paid_tier") or {}
        for model in paid.get("models") or []:
            if not isinstance(model, dict) or not model.get("name"):
                continue
            cost_in = model.get("cost_per_1m_input")
            cost_out = model.get("cost_per_1m_output")
            if cost_in is None or cost_out is None:
                continue
            prices.setdefault(model["name"], set()).add((float(cost_in), float(cost_out)))
    return prices


def _house_slugs_from_policy() -> set[str]:
    """Every slug the model policy can actually route to, read from the committed config."""
    policy = yaml.safe_load(_MODELS_CONFIG.read_text())
    slugs: set[str] = set()
    for tier in (policy.get("tiers") or {}).values():
        for pool in (tier.get("allowed_models") or {}).values():
            slugs.update(pool)
    return slugs


class TestThePriceTable:
    def test_every_committed_price_is_corroborated_by_a_committed_snapshot(self) -> None:
        """The table's own provenance claim, enforced: each row must match the value in
        ``docs/providers/snapshots/<provider>.yaml`` for its bare model name.

        This is what makes an arbitrary edit fail — change ``gpt-5.6-luna`` to ``0.20`` and
        no snapshot corroborates ``(0.2, ...)``, so this goes red instead of silently
        shipping a fabricated number.
        """
        snapshots = _snapshot_prices_by_bare_name()
        for slug, price in MODEL_PRICES_USD_PER_1M.items():
            bare = slug.split("/", 1)[1]
            assert bare in snapshots, f"{slug}: no snapshot prices {bare!r}"
            assert (
                price.prompt_usd_per_1m,
                price.completion_usd_per_1m,
            ) in snapshots[bare], f"{slug}: {price} is not corroborated by any snapshot"

    def test_every_house_slug_is_priced_or_documented_as_unpriced(self) -> None:
        """Policy coverage: a slug the config can route to must be either in the table or in
        the explicit unpriced set — never silently missing from both."""
        house_slugs = _house_slugs_from_policy()
        assert house_slugs, "model policy parsed to nothing — check the config shape"
        for slug in house_slugs:
            assert slug in MODEL_PRICES_USD_PER_1M or slug in _UNPRICED_SLUGS, slug

    def test_the_unpriced_set_only_holds_house_slugs(self) -> None:
        """Keep the unpriced set honest: it is for slugs the policy routes to but the repo
        cannot price, not a dumping ground for retired names."""
        assert _UNPRICED_SLUGS <= _house_slugs_from_policy()

    def test_an_unknown_model_has_no_price(self) -> None:
        assert price_for("made-up/model") is None

    def test_every_committed_price_is_a_positive_pair(self) -> None:
        for slug, price in MODEL_PRICES_USD_PER_1M.items():
            assert price.prompt_usd_per_1m > 0, slug
            assert price.completion_usd_per_1m > 0, slug


class TestEstimateCostUsd:
    def test_sums_prompt_and_completion_tokens_at_the_committed_prices(self) -> None:
        # deepseek-v4-flash: 1M prompt * $0.07 + 1M completion * $0.28 = $0.35
        # gpt-5.6-luna:      2M prompt * $1.00                       = $2.00
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
        assert estimate == pytest.approx(2.35)

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
        assert estimate == pytest.approx(5.00)

    def test_a_priced_model_with_zero_tokens_is_none_not_zero(self) -> None:
        """The result keys on tokens, not on model-name recognition. A priced entry that
        priced no tokens is an absence, not a $0.00 estimate."""
        assert (
            estimate_cost_usd({"openai/gpt-5.6-luna": {"prompt_tokens": 0, "completion_tokens": 0}})
            is None
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
        junk. A telemetry estimate must never raise into the run's exit path — and junk that
        coerces to zero tokens is no estimate at all."""
        assert estimate_cost_usd({"openai/gpt-5.6-luna": usage}) is None

    def test_a_non_mapping_usage_entry_is_skipped(self) -> None:
        assert estimate_cost_usd({"openai/gpt-5.6-luna": "nope"}) is None  # type: ignore[dict-item]

    def test_a_non_mapping_input_is_none(self) -> None:
        assert estimate_cost_usd("nope") is None  # type: ignore[arg-type]
        assert estimate_cost_usd(None) is None  # type: ignore[arg-type]
