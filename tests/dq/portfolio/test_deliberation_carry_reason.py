"""``carry_reason`` provenance contract (#1742, #2930, #4592).

``DeliberationSummary.carried`` is set by several unrelated paths, so
``carry_reason`` is what tells them apart downstream (H7's debate summaries, the
published ``deliberation/{ticker}`` document, and the sizing cap). Each reason
constant must therefore be a member of the ``CarryReason`` Literal — a value the
model cannot represent is a value the constructing node raises on.

Regression: ``CARRY_ATTENTION`` ("attention_carry", the WP13.4 post-H5 re-route)
was defined and used by the H6 node but missing from the Literal, so every
attention-enforced carry raised ``ValidationError`` (#4592).
"""

from __future__ import annotations

import typing

import digiquant.portfolio.models.deliberation as deliberation
import pytest
from digiquant.portfolio.models.deliberation import (
    CARRY_ATTENTION,
    CARRY_FINGERPRINT_SKIP,
    CARRY_LLM_FAILURE,
    CARRY_LOW_VALUE,
    CarryReason,
    DeliberationSummary,
    is_unchallenged_carry,
)

pytestmark = pytest.mark.unit

_ALL_CARRY_REASONS = (
    CARRY_FINGERPRINT_SKIP,
    CARRY_LLM_FAILURE,
    CARRY_LOW_VALUE,
    CARRY_ATTENTION,
)


def _discovered_carry_reasons() -> set[str]:
    """Every module-level ``CARRY_*`` string constant, found without hardcoding."""
    return {
        value
        for name, value in vars(deliberation).items()
        if name.startswith("CARRY_") and isinstance(value, str)
    }


def test_discovered_carry_constants_match_the_named_set() -> None:
    """A new ``CARRY_*`` constant the tests do not name must fail here, not silently pass."""
    assert _discovered_carry_reasons() == set(_ALL_CARRY_REASONS)


def test_every_carry_reason_constant_is_in_the_literal() -> None:
    """A reason the node can set must be a value the model accepts."""
    allowed = set(typing.get_args(CarryReason))
    missing = _discovered_carry_reasons() - allowed
    assert not missing, sorted(missing)


@pytest.mark.parametrize("reason", _ALL_CARRY_REASONS)
def test_deliberation_summary_accepts_each_carry_reason(reason: str) -> None:
    summary = DeliberationSummary(ticker="XLE", carried=True, carry_reason=reason)
    assert summary.carry_reason == reason


def test_attention_carry_summary_constructs() -> None:
    """The exact shape the H6 node builds for ``deliberation_enforce == "carry"`` (#2930)."""
    carried = DeliberationSummary(
        ticker="XLE",
        converged=True,
        conclusion="attention carry: hold",
        net_stance="neutral",
        conviction_delta=0,
        transcript=[],
        carried=True,
        carry_reason=CARRY_ATTENTION,
    )
    assert carried.carried is True
    assert carried.carry_reason == CARRY_ATTENTION
    # attention_carry is a benign skip, not an unchallenged crash
    assert is_unchallenged_carry(carried.model_dump()) is False


def test_llm_failure_is_the_only_unchallenged_carry() -> None:
    for reason in _ALL_CARRY_REASONS:
        summary = DeliberationSummary(ticker="XLE", carried=True, carry_reason=reason)
        expected = reason == CARRY_LLM_FAILURE
        assert is_unchallenged_carry(summary.model_dump()) is expected, reason
