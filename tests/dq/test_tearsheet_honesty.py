"""Honesty threading through tearsheet surfaces (#4828).

Each surface that renders win-rate must carry N + Wilson 95% CI (never a
bare %), with LOW SAMPLE / REFUSED banners at the warn@30 / refuse@10
floors. African grey rule: every assertion names N.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from digiquant.charts.trades import _build_win_rate_donut, count_winning_trades
from digiquant.models import BacktestResult
from digiquant.stats.honesty import DISCLAIMER, HonestRateBlock
from digiquant.tearsheet_page import _build_page
from digiquant.tearsheet_stats import (
    _build_categorized_stats,
    _build_full_stats_table,
    _build_risk_metrics_table,
    resolve_win_rate,
)

from digiquant import tearsheet as tearsheet_mod

pytestmark = pytest.mark.unit


def _result(num_trades: int) -> BacktestResult:
    return BacktestResult(
        run_id="r1",
        strategy_name="ema_cross",
        symbols=["BTC-USD"],
        start_time="2020-01-01",
        end_time="2021-01-01",
        num_trades=num_trades,
    )


def _honest_result(k: int, n: int, num_trades: int, **block_kw) -> BacktestResult:
    """A result whose honest block (k, n) deliberately differs from the fills."""
    return BacktestResult(
        run_id="r1",
        strategy_name="ema_cross",
        symbols=["BTC-USD"],
        start_time="2020-01-01",
        end_time="2021-01-01",
        num_trades=num_trades,
        honest_rate=HonestRateBlock(k=k, n=n, **block_kw),
    )


def test_categorized_stats_win_rate_carries_n_and_ci() -> None:
    """Win Rate 0.6 with n=50 renders honest string, not a bare %."""
    html = _build_categorized_stats(None, None, {"Win Rate": 0.6}, _result(50))
    assert "n=50" in html  # n=50
    assert "CI" in html  # n=50
    assert "60.0%" in html  # k=30, n=50
    assert "60.00%" not in html  # n=50: old bare-% shape is gone


def test_categorized_stats_low_sample_banner() -> None:
    """Win Rate 0.6 with n=20 renders LOW SAMPLE alongside the interval."""
    html = _build_categorized_stats(None, None, {"Win Rate": 0.6}, _result(20))
    assert "LOW SAMPLE" in html  # n=20
    assert "n=20" in html  # n=20


def test_categorized_stats_refused_below_floor() -> None:
    """Win Rate 0.6 with n=5 renders REFUSED, not a percentage."""
    html = _build_categorized_stats(None, None, {"Win Rate": 0.6}, _result(5))
    assert "REFUSED" in html  # n=5


def test_categorized_stats_missing_win_rate_is_dash() -> None:
    """No Win Rate stat with n=50 stays an em-dash, not a fabricated CI."""
    html = _build_categorized_stats(None, None, {}, _result(50))
    assert "—" in html  # n=50


def test_risk_metrics_win_rate_carries_n_and_ci() -> None:
    """Risk table Win Rate 0.6 with n=50 renders honest string."""
    html = _build_risk_metrics_table(None, {"Win Rate": 0.6}, _result(50))
    assert "n=50" in html  # n=50
    assert "CI" in html  # n=50


def test_full_stats_win_rate_carries_n_and_ci() -> None:
    """Full-stats dump Win Rate 0.6 with n=50 renders honest string."""
    html = _build_full_stats_table(None, None, {"Win Rate": 0.6}, _result(50))
    assert "n=50" in html  # n=50
    assert "CI" in html  # n=50


def _page(win_rate: float | None, num_trades: int, result=None, **kw) -> str:
    blanks = {
        "strategy_display": "EMA Cross",
        "symbols_str": "BTC-USD",
        "params_str": "period=20",
        "profit_factor": 1.2,
        "sortino": 0.5,
        "calmar": 0.5,
        "price_gen": "",
        "price_tab": "",
        "equity_gen": "",
        "equity_tab": "",
        "dd_gen": "",
        "dd_tab": "",
        "monthly_gen": "",
        "dist_gen": "",
        "dist_tab": "",
        "rolling_gen": "",
        "rolling_tab": "",
        "yearly_gen": "",
        "rolling_equity_html": "",
        "realized_pnl_html": "",
        "trade_pnl_dist_html": "",
        "trade_pnl_dist_trades_html": "",
        "rolling_dd_html": "",
        "monthly_yearly_html": "",
        "per_trade_pnl_html": "",
        "win_rate_donut_html": "",
        "rolling_calmar_html": "",
        "cum_trade_pnl_html": "",
        "underwater_html": "",
    }
    blanks.update(kw)
    return _build_page(result or _result(num_trades), win_rate=win_rate, **blanks)


def test_kpi_strip_win_rate_carries_n_and_ci() -> None:
    """KPI WIN RATE 0.6 with n=50 carries N + CI, not a bare %."""
    html = _page(0.6, 50)
    assert "WIN RATE" in html  # n=50
    assert "n=50" in html  # n=50
    assert "CI" in html  # n=50
    assert "60.0% (30/50" in html  # k=30, n=50


def test_kpi_win_rate_threshold_uses_ci_lower_bound() -> None:
    """Point estimate 0.6 (> 0.5) with n=12 has CI lo ~0.32 → negative."""
    html = _page(0.6, 12)
    assert 'WIN RATE</span><span class="kpi-value negative">' in html  # n=12


def test_kpi_win_rate_confident_above_half_is_positive() -> None:
    """Win rate 0.9 with n=1000 has CI lo > 0.5 → positive."""
    html = _page(0.9, 1000)
    assert 'WIN RATE</span><span class="kpi-value positive">' in html  # n=1000


def test_kpi_win_rate_refused_below_floor() -> None:
    """Win rate 0.6 with n=5 renders REFUSED on the KPI strip."""
    html = _page(0.6, 5)
    assert "REFUSED" in html  # n=5


def test_rendered_page_ships_disclaimer_verbatim() -> None:
    """Fixed disclaimer string is present on the rendered page (n=50)."""
    html = _page(0.6, 50)
    assert DISCLAIMER in html  # n=50


def test_donut_uses_caller_wins_not_round() -> None:
    """win_rate=0.5, n=10, num_wins=7 → slices [7, 3], not round(0.5*10)."""
    fig = _build_win_rate_donut(0.5, 10, num_wins=7)
    assert fig is not None  # n=10
    assert list(fig.data[0].values) == [7, 3]  # k=7, n=10
    ann = fig.layout.annotations[0].text
    assert "n=10" in ann  # n=10
    assert "CI" in ann  # n=10


def test_donut_center_shows_honest_rate() -> None:
    """Donut for k=30, n=50 centers the point estimate with N + CI."""
    fig = _build_win_rate_donut(0.6, 50, num_wins=30)
    assert fig is not None  # n=50
    ann = fig.layout.annotations[0].text
    assert "60.0%" in ann  # k=30, n=50
    assert "n=50" in ann  # n=50


def test_donut_refused_below_floor() -> None:
    """Donut for n=5 shows REFUSED in the center, not a win-rate %."""
    fig = _build_win_rate_donut(0.6, 5, num_wins=3)
    assert fig is not None  # n=5
    ann = fig.layout.annotations[0].text
    assert "REFUSED" in ann  # n=5


def test_donut_without_wins_renders_unknown_center() -> None:
    """No caller count → unknown center (rate + n), never a pseudo k/n."""
    fig = _build_win_rate_donut(0.6, 50)
    assert fig is not None  # n=50
    assert list(fig.data[0].values) == [30, 20]  # n=50: slices stay rate-derived
    ann = fig.layout.annotations[0].text
    assert "n=50" in ann  # n=50
    assert "uncounted" in ann  # n=50
    assert "30/50" not in ann  # n=50: no reconstructed count as observed
    assert "95%" not in ann  # n=50: no interval off a reconstructed k


def test_donut_without_wins_clamps_percent_scale() -> None:
    """Percent-scale 60.0 without a count normalizes like the KPI path."""
    fig = _build_win_rate_donut(60.0, 50)
    assert fig is not None  # n=50
    assert list(fig.data[0].values) == [30, 20]  # k=30 slice, n=50
    assert "6000.0%" not in fig.layout.annotations[0].text  # n=50


def test_donut_without_wins_still_refuses_tiny_n() -> None:
    """No caller count with n=5 keeps the REFUSED guard (guard is about n)."""
    fig = _build_win_rate_donut(0.6, 5)
    assert fig is not None  # n=5
    assert "REFUSED" in fig.layout.annotations[0].text  # n=5


def test_count_winning_trades_from_series() -> None:
    """3 positives in a 10-trade series → 7 wins is wrong, 3 is right."""
    import polars as pl

    series = pl.Series("value", [10.0, -5.0, 3.0, -1.0, 7.0])
    assert count_winning_trades(series) == 3  # n=5
    assert count_winning_trades(None) is None


def test_count_winning_trades_never_touches_pandas_bridge() -> None:
    """A series exposing .to_pandas (raises without pyarrow) still counts."""

    class _NoPyarrow(list):
        def to_pandas(self):  # pragma: no cover - must never be called
            raise ModuleNotFoundError("No module named 'pyarrow'")

    series = _NoPyarrow([1.0, -2.0, 3.0, float("nan")])
    assert count_winning_trades(series) == 2  # n=3 (NaN dropped)


def _generator_module():
    import sys
    from pathlib import Path

    scripts = Path(__file__).resolve().parents[2] / "digiquant" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import generate_tearsheets

    return generate_tearsheets


def test_generate_log_win_rate_carries_n_and_ci() -> None:
    """Log helper for 55% over n=20 carries N + CI + LOW SAMPLE."""
    gt = _generator_module()
    s = gt._honest_win_rate_log(55.0, 20)
    assert "n=20" in s  # n=20
    assert "CI" in s  # n=20
    assert "LOW SAMPLE" in s  # n=20


def test_generate_log_win_rate_none_is_na() -> None:
    """Log helper with no win rate (n=0, DCA) stays n/a."""
    gt = _generator_module()
    assert gt._honest_win_rate_log(None, 0) == "n/a"  # n=0


def test_generate_log_win_rate_refused_below_floor() -> None:
    """Log helper for 60% over n=5 renders REFUSED."""
    gt = _generator_module()
    s = gt._honest_win_rate_log(60.0, 5)
    assert "REFUSED" in s  # n=5


# --- L7: surfaces read k/n off the honest block, never off the fill count ---


def test_categorized_stats_n_comes_from_the_block() -> None:
    """Block (30, 50) over 900 fills renders the block's n, not 900."""
    html = _build_categorized_stats(None, None, {"Win Rate": 0.6}, _honest_result(30, 50, 900))
    assert "60.0% (30/50" in html  # n=50
    assert "n=900" not in html  # n=50: the fill count is not a denominator


def test_risk_metrics_n_comes_from_the_block() -> None:
    """Risk table uses the block's n when the honest block is present."""
    html = _build_risk_metrics_table(None, {"Win Rate": 0.6}, _honest_result(30, 50, 900))
    assert "60.0% (30/50" in html  # n=50
    assert "n=900" not in html  # n=50


def test_full_stats_n_comes_from_the_block() -> None:
    """Full-stats dump uses the block's n when the honest block is present."""
    html = _build_full_stats_table(None, None, {"Win Rate": 0.6}, _honest_result(30, 50, 900))
    assert "60.0% (30/50" in html  # n=50
    assert "n=900" not in html  # n=50


def test_kpi_n_comes_from_the_block() -> None:
    """KPI WIN RATE reads n off the block; the fills get their own card."""
    html = _page(0.6, 900, result=_honest_result(30, 50, 900))
    assert "60.0% (30/50" in html  # n=50
    assert "n=900" not in html  # n=50
    assert "TOTAL FILLS" in html  # n=50: fills still shown, under their own name
    # The colour band is driven by wilson(k, n) on the same n. On the block's
    # n=50 the lower bound is 0.46, which sits between the two thresholds and
    # so carries no class; on the 900-fill denominator it would be 0.02 and
    # paint the card negative. Pin the whole cell so the band travels with n.
    assert '<span class="kpi-value ">60.0% (30/50' in html  # n=50


def test_donut_denominator_is_the_block_n() -> None:
    """Donut gets k and n from one source: the block, not the fill count."""
    counts = resolve_win_rate(_honest_result(30, 50, 900), 0.6, wins=count_winning_trades(None))
    assert (counts.k, counts.n, counts.counted) == (30, 50, True)  # n=50
    fig = _build_win_rate_donut(0.6, counts.n, num_wins=counts.k)
    assert fig is not None  # n=50
    assert list(fig.data[0].values) == [30, 20]  # n=50
    assert "n=50" in fig.layout.annotations[0].text  # n=50
    src = inspect.getsource(tearsheet_mod.create_tearsheet)
    assert "_build_win_rate_donut(win_rate, counts.n, num_wins=num_wins)" in src  # n=50


def test_donut_reconstruction_is_delegated_and_bounded() -> None:
    """No counted k -> None, so only the L6 donut may reconstruct; say so out loud.

    `_build_win_rate_donut` itself still does `round(wr * num_trades)` when
    handed `num_wins=None` (charts/trades.py, owned by L6/DIG-848). This leaf
    cannot remove it from an allowed file, so it pins the boundary instead:
    a block always counts, and a fallback is honest about not counting.
    """
    # With a block, the donut is handed a counted k — its reconstruction is dead.
    with_block = resolve_win_rate(_honest_result(30, 50, 900), 0.6, wins=None)
    assert with_block.counted is True  # n=50
    assert "wins uncounted" not in _donut_annotation(0.6, with_block.n, with_block.k)  # n=50
    # Without a block and without a counted series we decline to guess, and the
    # donut says so on its face rather than presenting a reconstruction as k.
    fallback = resolve_win_rate(_result(50), 0.6, wins=count_winning_trades(None))
    assert fallback.counted is False  # n=50
    assert fallback.n == 50  # n=50
    assert "wins uncounted" in _donut_annotation(0.6, fallback.n, None)  # n=50
    # `counted` is the only thing standing between a reconstruction and the
    # donut: flips True and the guess is presented as a counted k. Assert the
    # flag on the reconstruction itself, since the wiring above reads nothing else.
    assert fallback.k == round(0.6 * 50)  # n=50: it IS a rate x n guess...
    assert fallback.counted is False  # n=50: ...and it must never claim otherwise


def _donut_annotation(rate: float, n: int, wins: int | None) -> str:
    """The donut's centre label for a given (rate, n, num_wins) hand-off."""
    fig = _build_win_rate_donut(rate, n, num_wins=wins)
    assert fig is not None
    return str(fig.layout.annotations[0].text)


def test_only_the_legacy_fallback_reconstructs_rate_times_n() -> None:
    """`round(rate * n)` survives in the fallback only — AST, so docs don't count."""
    from digiquant import tearsheet_page as page_mod
    from digiquant import tearsheet_stats as stats_mod

    def rounds(module) -> list[tuple[str, str]]:
        """Every ``round(...)`` in a module, paired with the function holding it.

        Pairing with the *enclosing* function is what makes this falsifiable:
        the pre-fix module also unparsed to ``['round(wr * n)']`` because its
        lone round sat in ``_honest_win_rate_text``. Reverted, this reports
        ``_honest_win_rate_text`` and the assertion fires.
        """
        src = Path(inspect.getsourcefile(module)).read_text()
        tree = ast.parse(src)
        sites: list[tuple[str, str]] = []
        for outer in ast.walk(tree):
            if not isinstance(outer, ast.FunctionDef):
                continue
            for node in ast.walk(outer):
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "round":
                    sites.append((outer.name, ast.unparse(node)))
        return sites

    assert rounds(stats_mod) == [
        ("resolve_win_rate", "round(wr * n)")
    ]  # n=50: one, in the fallback
    assert rounds(page_mod) == []  # n=50
    assert rounds(tearsheet_mod) == []  # n=50


def test_caller_counted_wins_beat_the_reconstruction() -> None:
    """A counted k is kept as counted; only an uncounted one is reconstructed."""
    counted = resolve_win_rate(_result(50), 0.6, wins=40)
    assert (counted.k, counted.n, counted.counted) == (
        40,
        50,
        True,
    )  # n=50: the 0.6 rate is ignored
    assert "80.0% (40/50" in counted.text  # n=50
    assert counted.refused is False  # n=50
    # An absent rate must not be back-filled from n: no wins, no rate, no guess.
    uncounted = resolve_win_rate(_result(50), None)
    assert (uncounted.k, uncounted.counted) == (0, False)  # n=50
    assert uncounted.text == "—"  # n=50
    # n below the refuse floor is a refusal, not a small percentage.
    assert resolve_win_rate(_result(5), 0.6).refused is True  # n=5


def test_trade_count_rows_are_labelled_as_fills() -> None:
    """The counts that read num_trades say they are fill counts."""
    stats_html = _build_categorized_stats(None, None, {"Total Trades": 900}, _result(900))
    assert "# Fills" in stats_html  # n=900
    assert "# Trades" not in stats_html  # n=900
    page_html = _page(0.6, 900)
    assert "TOTAL FILLS" in page_html  # n=900
    assert "TOTAL TRADES" not in page_html  # n=900


def test_blockless_result_still_renders_via_the_fallback() -> None:
    """A result with no honest block keeps rendering, off num_trades."""
    counts = resolve_win_rate(_result(50), 0.6)
    assert (counts.k, counts.n, counts.counted) == (30, 50, False)  # n=50
    assert "60.0% (30/50" in counts.text  # n=50
    assert "60.0% (30/50" in _page(0.6, 50)  # n=50


def test_refused_block_renders_no_rate() -> None:
    """A refused block refuses on every surface, whatever the rate says."""
    refused = _honest_result(3, 5, 900)
    assert refused.honest_rate is not None and refused.honest_rate.refused  # n=5
    for html in (
        _build_categorized_stats(None, None, {"Win Rate": 0.6}, refused),
        _build_risk_metrics_table(None, {"Win Rate": 0.6}, refused),
        _build_full_stats_table(None, None, {"Win Rate": 0.6}, refused),
        _page(0.6, 900, result=refused),
    ):
        assert "REFUSED" in html  # n=5
        assert "60.0%" not in html  # n=5: a refused block renders no rate


def test_refused_card_carries_no_colour_band() -> None:
    """REFUSED is a refusal — recolouring it would publish the rate it withheld."""
    html = _page(0.6, 900, result=_honest_result(3, 5, 900))
    assert "REFUSED" in html  # n=5
    assert 'WIN RATE</span><span class="kpi-value negative">' not in html  # n=5
    assert 'WIN RATE</span><span class="kpi-value ">' in html  # n=5: unbanded
    # The band still works wherever the sample earns one.
    confident = _page(0.9, 1000, result=_honest_result(900, 1000, 9999))
    assert 'WIN RATE</span><span class="kpi-value positive">' in confident  # n=1000


def test_disclaimer_renders_once_inside_the_frequency_block() -> None:
    """The block's own disclaimer appears once — not on the card, not on a PnL row."""
    sentinel = "Closed round trips only; not a fill win rate."
    html = _page(0.6, 900, result=_honest_result(30, 50, 900, disclaimer=sentinel))
    assert html.count(sentinel) == 1  # n=50
    assert f'<div class="disclaimer">{sentinel}</div>' in html  # n=50
    assert '<div class="kpi"><span class="kpi-label">WIN RATE</span>' in html  # n=50
