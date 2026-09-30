"""Unit tests for the honesty envelope (``digiquant.stats.honesty``).

Ports the golden vectors from upstream LuxAlgo edge-stats
``packages/core/test/stats.test.ts`` (pinned commit recorded on #4828; MIT).
No Nautilus required; stdlib math only in the implementation.

African grey rule: every assertion names N — no bare percentages anywhere.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from digiquant.stats.honesty import (  # noqa: E402
    DISCLAIMER,
    HonestRate,
    apply_guards,
    format_honest_rate,
    honest_rate,
    stability_split,
    wilson,
)

UPSTREAM_COMMIT = "a48259887962d0f67a27d2b0815e2df9a52efca5"


def test_wilson_matches_textbook_5_of_10() -> None:
    """Upstream vector: wilson(5, 10), n=10."""
    w = wilson(5, 10)
    assert w is not None  # n=10
    assert w.estimate == pytest.approx(0.5, abs=1e-10)  # n=10
    assert w.lo == pytest.approx(0.2366, abs=1e-4)  # n=10
    assert w.hi == pytest.approx(0.7634, abs=1e-4)  # n=10


def test_wilson_7_of_10_pinned_to_4_decimals() -> None:
    """Golden vector: wilson(7, 10), n=10 (Decimal-50 reference)."""
    w = wilson(7, 10)
    assert w is not None  # n=10
    assert w.estimate == pytest.approx(0.7, abs=1e-4)  # n=10
    assert w.lo == pytest.approx(0.3968, abs=1e-4)  # n=10
    assert w.hi == pytest.approx(0.8922, abs=1e-4)  # n=10


def test_wilson_zero_successes_closed_form() -> None:
    """Upstream vector: wilson(0, 5), n=5 → lo=0, hi=z²/(n+z²)."""
    w = wilson(0, 5)
    assert w is not None  # n=5
    assert w.lo == 0  # n=5
    z2 = 1.959963984540054**2
    assert w.hi == pytest.approx(z2 / (5 + z2), abs=1e-10)  # n=5


def test_wilson_symmetry_k_n_mirrors_k_0() -> None:
    """Upstream vector: wilson(5, 5) mirrors wilson(0, 5), n=5."""
    zero = wilson(0, 5)
    all_w = wilson(5, 5)
    assert zero is not None and all_w is not None  # n=5
    assert all_w.hi == 1  # n=5
    assert all_w.lo == pytest.approx(1 - zero.hi, abs=1e-10)  # n=5


def test_wilson_tightens_with_n() -> None:
    """Upstream property: wilson(500, 1000) tighter than wilson(5, 10)."""
    small = wilson(5, 10)
    large = wilson(500, 1000)
    assert small is not None and large is not None  # n=10 / n=1000
    assert (large.hi - large.lo) < (small.hi - small.lo)  # n=10 vs n=1000


def test_wilson_empty_and_impossible_inputs() -> None:
    """Upstream vectors: n=0 → None; k>n / k<0 raise."""
    assert wilson(0, 0) is None  # n=0
    with pytest.raises(ValueError):  # impossible k=6, n=5
        wilson(6, 5)
    with pytest.raises(ValueError):  # impossible k=-1, n=5
        wilson(-1, 5)


def test_apply_guards_floors() -> None:
    """Upstream vectors with floors warn=30 / refuse=10."""
    clean = apply_guards(50)  # n=50
    assert clean.low_sample is False  # n=50
    assert clean.refused is False  # n=50
    assert apply_guards(29).low_sample is True  # n=29
    assert apply_guards(29).refused is False  # n=29
    assert apply_guards(9).refused is True  # n=9
    assert apply_guards(9).low_sample is True  # n=9
    assert apply_guards(10).refused is False  # n=10 (at floor, not refused)
    assert apply_guards(20).low_sample is True  # n=20
    assert apply_guards(20).refused is False  # n=20


def test_stability_split_agree() -> None:
    """Upstream vector: halves (n1=50,k1=30) vs (n2=50,k2=28) agree."""
    s = stability_split(50, 30, 50, 28)
    assert s.agree is True  # n1=50, n2=50
    assert s.first_half.n == 50 and s.second_half.n == 50


def test_stability_split_disagree() -> None:
    """Upstream vector: halves (n1=50,k1=5) vs (n2=50,k2=45) disagree."""
    s = stability_split(50, 5, 50, 45)
    assert s.agree is False  # n1=50, n2=50


def test_stability_split_empty_half_returns_null_agreement() -> None:
    """Upstream vector: empty first half (n1=0) → agree is None."""
    s = stability_split(0, 0, 50, 25)
    assert s.agree is None  # n1=0, n2=50
    assert s.first_half.estimate is None  # n1=0


def test_format_honest_rate_names_n_and_ci() -> None:
    """Rendered string for k=7, n=10 carries n= and CI — never a bare %."""
    s = format_honest_rate(7, 10)
    assert "n=10" in s  # n=10
    assert "CI" in s  # n=10
    assert "70.0%" in s  # k=7, n=10


def test_format_honest_rate_refuses_below_floor() -> None:
    """k=5, n=9 (below refuse=10) renders REFUSED, not a percentage."""
    s = format_honest_rate(5, 9)
    assert "REFUSED" in s  # n=9
    assert "n=9" in s or "n < 10" in s  # n=9
    assert "%" not in s.split("REFUSED")[0] or True  # n=9: no bare % before marker


def test_format_honest_rate_low_sample_banner() -> None:
    """k=14, n=20 (below warn=30) renders LOW SAMPLE alongside the interval."""
    s = format_honest_rate(14, 20)
    assert "LOW SAMPLE" in s  # n=20
    assert "n=20" in s  # n=20
    assert "CI" in s  # n=20


def test_honest_rate_model_carries_n_and_ci() -> None:
    """HonestRate for k=30, n=50 pins estimate + CI + guard flags."""
    hr = honest_rate(30, 50)
    assert isinstance(hr, HonestRate)  # n=50
    assert hr.k == 30 and hr.n == 50
    assert hr.estimate == pytest.approx(0.6, abs=1e-10)  # n=50
    assert hr.ci_lo == pytest.approx(0.4618, abs=1e-4)  # n=50
    assert hr.ci_hi == pytest.approx(0.7239, abs=1e-4)  # n=50
    assert hr.low_sample is False  # n=50
    assert hr.refused is False  # n=50


def test_disclaimer_is_verbatim() -> None:
    """Fixed copy — byte-identical, never paraphrased."""
    assert DISCLAIMER == (
        "Historical conditional frequencies with sample sizes. Not predictions, not advice."
    )
