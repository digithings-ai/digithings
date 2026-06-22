"""Phase 7E — deterministic risk-sizing enforcement (#726, Pillar 2).

The node replaces the PM's eyeballed candidate book with sized, capped, reduce-only
weights and rebuilds the advisory action list, reading per-ticker vol from
``price_technicals`` (look-ahead-guarded) and sector buckets from ``sector_map``. It is
fail-soft (errors keep the PM book) and a no-op when the PM never ran.
"""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState, PhaseHermesState
from digiquant.olympus.hermes.models.pm_direction import PMDirectionMemo, TickerDirection
from digiquant.olympus.hermes.phases import phase7e_risk_sizing
from digiquant.olympus.hermes.phases.phase7e_risk_sizing import (
    RiskSizingDeps,
    build_risk_sizing_node,
)

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

RUN_DATE = date(2026, 6, 12)
# Caps relaxed so a *specific* constraint can be isolated per test (the default caps bind
# at 30% position / 40% sector / 12% vol — exercised by the default-caps tests below).
_RELAXED = {
    "max_single_etf_pct": 100,
    "max_sector_pct": 100,
    "target_portfolio_vol": 1.0e6,
    "weight_increment_pct": 0,
}


def _state(
    recommended: list[dict],
    analysts: dict | None = None,
    debates: dict | None = None,
    actions: list[dict] | None = None,
    preferences: dict | None = None,
    *,
    use_memo: bool = True,
) -> AtlasResearchState:
    state = AtlasResearchState(
        run_type="delta",
        run_date=RUN_DATE,
        baseline_date=date(2026, 6, 9),
        config=AtlasConfigBundle(preferences=preferences or {}),
    )
    analysts_dict = analysts or {}
    debates_dict = debates or {}
    if use_memo:
        long_tickers = [str(row["ticker"]) for row in recommended if row.get("ticker")]
        memo = PMDirectionMemo(
            date=RUN_DATE,
            roster=[
                TickerDirection(ticker=ticker, direction="long", conviction_rank=idx + 1)
                for idx, ticker in enumerate(long_tickers)
            ],
            memo="PM notes.",
        )
        state.phase_hermes = PhaseHermesState(
            pm_direction_memo=memo,
            asset_analysts=analysts_dict,
            deliberation_summaries=debates_dict,
        )
    else:
        state.phase7d_rebalance = {
            "recommended_portfolio": recommended,
            "actions": actions or [],
            "notes": "PM notes.",
        }
        state.phase_hermes = PhaseHermesState(
            asset_analysts=analysts_dict,
            deliberation_summaries=debates_dict,
        )
    return state


def _tech_rows(vols: dict[str, float], on: str = "2026-06-12") -> list[dict]:
    return [{"ticker": t, "date": on, "hist_vol_21": v, "atr_pct": None} for t, v in vols.items()]


def _run(state: AtlasResearchState, client: FakeSupabaseClient | None = None) -> dict | None:
    client = client or FakeSupabaseClient()
    out = build_risk_sizing_node(RiskSizingDeps(client=client))(state)
    phase_hermes = out.get("phase_hermes")
    if phase_hermes is not None:
        return phase_hermes.sized_book
    return out.get("phase7d_rebalance")


def _weights(rebal: dict) -> dict[str, float]:
    return {r["ticker"]: r["target_pct"] for r in rebal["recommended_portfolio"]}


# --------------------------------------------------------------------------- no-op / cash


def test_no_op_when_pm_never_ran() -> None:
    state = _state([])
    state.phase_hermes = PhaseHermesState()
    assert build_risk_sizing_node(RiskSizingDeps(client=FakeSupabaseClient()))(state) == {}


def test_empty_book_stays_empty_cash() -> None:
    rebal = _run(_state([]))
    assert rebal is not None
    assert rebal["recommended_portfolio"] == []


# --------------------------------------------------------------------------- core enforcement


def test_overwrites_pm_weights_with_position_capped_book() -> None:
    # PM eyeballed 50/50; the 30% default position cap rewrites it to 30/30 with the freed
    # 40% as cash (reduce-only). The PM's weights are discarded in favour of sizing.
    client = FakeSupabaseClient(
        canned_reads={"price_technicals": _tech_rows({"SPY": 15, "TLT": 15})}
    )
    rebal = _run(
        _state(
            [{"ticker": "SPY", "target_pct": 50}, {"ticker": "TLT", "target_pct": 50}],
            analysts={
                "SPY": {"conviction_score": 5, "stance": "buy"},
                "TLT": {"conviction_score": 5, "stance": "buy"},
            },
        ),
        client,
    )
    w = _weights(rebal)
    assert w["SPY"] == pytest.approx(30.0)
    assert w["TLT"] <= 30.0
    assert w["SPY"] >= w["TLT"]


def test_single_name_position_capped_to_thirty() -> None:
    client = FakeSupabaseClient(canned_reads={"price_technicals": _tech_rows({"SPY": 15})})
    rebal = _run(
        _state(
            [{"ticker": "SPY", "target_pct": 100}],
            analysts={"SPY": {"conviction_score": 5, "stance": "buy"}},
        ),
        client,
    )
    assert _weights(rebal) == {"SPY": pytest.approx(30.0)}


def test_drawdown_breaker_halves_gross() -> None:
    # nav_history shows a −25% drawdown (peak 100 → 75) → breaker scale 0.5. The single
    # name caps at 30%, then the breaker halves gross → 15% (the rest to cash).
    client = FakeSupabaseClient(
        canned_reads={
            "price_technicals": _tech_rows({"SPY": 15}),
            "nav_history": [
                {"date": "2026-06-01", "nav": 100.0},
                {"date": "2026-06-10", "nav": 75.0},
            ],
        }
    )
    rebal = _run(
        _state(
            [{"ticker": "SPY", "target_pct": 100}],
            analysts={"SPY": {"conviction_score": 5, "stance": "buy"}},
        ),
        client,
    )
    assert _weights(rebal) == {"SPY": pytest.approx(15.0)}
    assert "Drawdown breaker" in rebal["notes"]


def test_effective_conviction_applies_debate_delta() -> None:
    # Legacy 7D path: equal analyst conviction; debate delta lifts A over B.
    rebal = _run(
        _state(
            [{"ticker": "AAA", "target_pct": 50}, {"ticker": "BBB", "target_pct": 50}],
            analysts={
                "AAA": {"conviction_score": 3, "stance": "buy"},
                "BBB": {"conviction_score": 3, "stance": "buy"},
            },
            debates={"AAA": {"conviction_delta": 2}, "BBB": {"conviction_delta": 0}},
            preferences=_RELAXED,
            use_memo=False,
        ),
        FakeSupabaseClient(canned_reads={"price_technicals": _tech_rows({"AAA": 20, "BBB": 20})}),
    )
    w = _weights(rebal)
    assert w["AAA"] > w["BBB"]
    assert w["AAA"] / w["BBB"] == pytest.approx(5.0 / 3.0, rel=0.05)


def test_memo_conviction_rank_orders_weights() -> None:
    # H7 path: rank 1 (AAA) outweighs rank 2 (BBB) with equal analyst conviction.
    state = AtlasResearchState(
        run_type="delta",
        run_date=RUN_DATE,
        config=AtlasConfigBundle(preferences=_RELAXED),
    )
    state.phase_hermes = PhaseHermesState(
        pm_direction_memo=PMDirectionMemo(
            date=RUN_DATE,
            roster=[
                TickerDirection(ticker="AAA", direction="long", conviction_rank=1),
                TickerDirection(ticker="BBB", direction="long", conviction_rank=2),
            ],
            memo="PM notes.",
        ),
        asset_analysts={
            "AAA": {"conviction_score": 3, "stance": "buy"},
            "BBB": {"conviction_score": 3, "stance": "buy"},
        },
    )
    rebal = _run(
        state,
        FakeSupabaseClient(canned_reads={"price_technicals": _tech_rows({"AAA": 20, "BBB": 20})}),
    )
    w = _weights(rebal)
    assert w["AAA"] > w["BBB"]


def test_sector_cap_enforced_via_real_buckets() -> None:
    # Three Technology single-names (sector_map → sector-technology) → the 40% sector cap
    # trims the bucket from 100% to 40%, the rest to cash.
    techs = ["AAPL", "MSFT", "NVDA"]
    rebal = _run(
        _state(
            [{"ticker": t, "target_pct": 33} for t in techs],
            analysts={t: {"conviction_score": 4, "stance": "buy"} for t in techs},
            preferences={
                "max_single_etf_pct": 100,
                "target_portfolio_vol": 1.0e6,
                "weight_increment_pct": 0,
            },
        ),
        FakeSupabaseClient(canned_reads={"price_technicals": _tech_rows({t: 20 for t in techs})}),
    )
    w = _weights(rebal)
    assert sum(w.values()) == pytest.approx(40.0, abs=0.5)


# --------------------------------------------------------------------------- look-ahead guard


def test_look_ahead_guard_ignores_future_technicals() -> None:
    # A future-dated row (after run_date) with absurd vol would, if not guarded, blow up
    # vol-targeting and shrink the book to ~0. The .lte(run_date) guard excludes it, so the
    # 15%-vol row at run_date is used and the position caps at 30%.
    client = FakeSupabaseClient(
        canned_reads={
            "price_technicals": [
                {"ticker": "SPY", "date": "2026-06-12", "hist_vol_21": 15, "atr_pct": None},
                {"ticker": "SPY", "date": "2026-06-20", "hist_vol_21": 300, "atr_pct": None},
            ]
        }
    )
    rebal = _run(
        _state(
            [{"ticker": "SPY", "target_pct": 100}],
            analysts={"SPY": {"conviction_score": 5, "stance": "buy"}},
        ),
        client,
    )
    assert _weights(rebal) == {"SPY": pytest.approx(30.0)}


# --------------------------------------------------------------------------- actions / carried


def test_dropped_ticker_becomes_exit_action() -> None:
    # AAA below the conviction floor (1 < 2) is dropped from the book; its PM action row
    # flips to an explicit exit-to-cash, and it is absent from recommended_portfolio.
    rebal = _run(
        _state(
            [{"ticker": "AAA", "target_pct": 50}, {"ticker": "BBB", "target_pct": 50}],
            analysts={
                "AAA": {"conviction_score": 1, "stance": "buy"},
                "BBB": {"conviction_score": 5, "stance": "buy"},
            },
            actions=[
                {
                    "ticker": "AAA",
                    "action": "add",
                    "current_pct": 10,
                    "target_pct": 50,
                    "rationale": "PM liked AAA.",
                },
                {
                    "ticker": "BBB",
                    "action": "new",
                    "current_pct": 0,
                    "target_pct": 50,
                    "rationale": "PM liked BBB.",
                },
            ],
            use_memo=False,
        ),
        FakeSupabaseClient(canned_reads={"price_technicals": _tech_rows({"BBB": 15})}),
    )
    assert "AAA" not in _weights(rebal)
    aaa_action = next(a for a in rebal["actions"] if a["ticker"] == "AAA")
    assert aaa_action["action"] == "exit"
    assert aaa_action["target_pct"] == 0.0
    assert "removed by risk sizing" in aaa_action["rationale"]


def test_retained_position_verb_recomputed_to_trim() -> None:
    # PM held SPY at 50% and proposed holding 50%; the 30% position cap trims the sized
    # target to 30 < 50, so the published action must flip "hold" → "trim" (not stay
    # "hold" with a 30% target, which would misdescribe the enforced book).
    client = FakeSupabaseClient(canned_reads={"price_technicals": _tech_rows({"SPY": 15})})
    rebal = _run(
        _state(
            [{"ticker": "SPY", "target_pct": 50}],
            analysts={"SPY": {"conviction_score": 5, "stance": "buy"}},
            actions=[
                {
                    "ticker": "SPY",
                    "action": "hold",
                    "current_pct": 50,
                    "target_pct": 50,
                    "rationale": "PM holds SPY.",
                },
            ],
            use_memo=False,
        ),
        client,
    )
    spy_action = next(a for a in rebal["actions"] if a["ticker"] == "SPY")
    assert spy_action["action"] == "trim"
    assert spy_action["target_pct"] == pytest.approx(30.0)


def test_carried_holding_without_analyst_is_retained() -> None:
    # The PM recommends a name with no fresh analyst payload (a carried holding); it
    # defaults to the conviction floor + hold and survives at minimal tilt, not dropped.
    rebal = _run(
        _state(
            [{"ticker": "GLD", "target_pct": 40}, {"ticker": "SPY", "target_pct": 60}],
            analysts={"SPY": {"conviction_score": 5, "stance": "buy"}},  # GLD: none
            preferences=_RELAXED,
        ),
        FakeSupabaseClient(canned_reads={"price_technicals": _tech_rows({"SPY": 15, "GLD": 18})}),
    )
    assert "GLD" in _weights(rebal)


def test_notes_carry_sizing_explanation() -> None:
    rebal = _run(
        _state(
            [{"ticker": "SPY", "target_pct": 100}],
            analysts={"SPY": {"conviction_score": 5, "stance": "buy"}},
        ),
        FakeSupabaseClient(canned_reads={"price_technicals": _tech_rows({"SPY": 15})}),
    )
    assert "Risk-sizing (H8)" in rebal["notes"]
    assert rebal["notes"].startswith("PM notes.")  # PM's note preserved


# --------------------------------------------------------------------------- fail-soft


def test_sizing_error_keeps_pm_book(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(**_kwargs):
        raise RuntimeError("sizer exploded")

    monkeypatch.setattr(phase7e_risk_sizing, "size_portfolio", _boom)
    state = _state(
        [{"ticker": "SPY", "target_pct": 50}],
        analysts={"SPY": {"conviction_score": 5, "stance": "buy"}},
        use_memo=False,
    )
    # Legacy path: no update returned → phase7d_rebalance stays intact.
    assert build_risk_sizing_node(RiskSizingDeps(client=FakeSupabaseClient()))(state) == {}


def test_missing_technicals_uses_default_vol() -> None:
    # No price_technicals rows at all → the sizer falls back to its default vol; the book
    # still materializes (position cap binds), never crashes.
    rebal = _run(
        _state(
            [{"ticker": "SPY", "target_pct": 100}],
            analysts={"SPY": {"conviction_score": 5, "stance": "buy"}},
        ),
        FakeSupabaseClient(canned_reads={"price_technicals": []}),
    )
    assert _weights(rebal) == {"SPY": pytest.approx(30.0)}


# --------------------------------------------------------------------------- correlation pass-through


def _price_history_rows(tickers: list[str], n: int = 40) -> list[dict]:
    """Generate n price_history rows per ticker anchored just before RUN_DATE.

    Rows end at RUN_DATE so they fall inside the default 63-day lookback window
    used by ``get_return_correlations``. All tickers move together → ρ ≈ 1.0.
    """
    rows = []
    for i in range(n):
        d = (RUN_DATE - timedelta(days=n - 1 - i)).isoformat()
        for j, t in enumerate(tickers):
            rows.append({"date": d, "ticker": t, "close": 100.0 + i + j * 10})
    return rows


def test_corr_frame_passed_to_sizer_triggers_dedup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real corr frame wired from price_history through phase7e into size_portfolio.

    Two tickers with a >0.8 correlation and different convictions: the lower-conviction
    leg must be dropped by ``_corr_dedup`` (the ρ≈1.0 pair exceeds the default 0.80
    threshold). This verifies end-to-end that the corr frame is actually passed — if
    ``corr=None`` were still hardcoded, the identical-vol pair would NOT be de-duped.
    """
    # AAA conviction 5, BBB conviction 3 → BBB should be dropped (lower conviction).
    # Both are the same sector (UNKNOWN by default) so sector cap doesn't interfere.
    # All caps relaxed except the dedup threshold (default 0.80).
    tickers = ["AAA", "BBB"]
    # price_history: 40 rows each, perfectly correlated → ρ=1.0 > 0.80 threshold.
    ph_rows = _price_history_rows(tickers, n=40)
    tech_rows = [
        {"ticker": "AAA", "date": "2026-06-12", "hist_vol_21": 20, "atr_pct": None},
        {"ticker": "BBB", "date": "2026-06-12", "hist_vol_21": 20, "atr_pct": None},
    ]
    client = FakeSupabaseClient(
        canned_reads={"price_technicals": tech_rows, "price_history": ph_rows}
    )

    captured: dict = {}
    original_size = phase7e_risk_sizing.size_portfolio

    def _spy_size_portfolio(**kwargs):
        captured["corr"] = kwargs.get("corr")
        return original_size(**kwargs)

    monkeypatch.setattr(phase7e_risk_sizing, "size_portfolio", _spy_size_portfolio)

    rebal = _run(
        _state(
            [{"ticker": "AAA", "target_pct": 50}, {"ticker": "BBB", "target_pct": 50}],
            analysts={
                "AAA": {"conviction_score": 5, "stance": "buy"},
                "BBB": {"conviction_score": 3, "stance": "buy"},
            },
            preferences={
                "max_single_etf_pct": 100,
                "max_sector_pct": 100,
                "target_portfolio_vol": 1.0e6,
                "weight_increment_pct": 0,
                "corr_dedup_threshold": 0.80,
                "min_conviction": 2.0,
            },
        ),
        client,
    )
    # The corr frame was passed (not None) — confirms the plumbing is wired.
    assert captured.get("corr") is not None, "corr=None was passed; reader was not wired"
    assert isinstance(captured["corr"], pl.DataFrame)

    # BBB (conviction 3) must be dropped in favour of AAA (conviction 5).
    w = _weights(rebal)
    assert "AAA" in w, "AAA (higher conviction) should be retained"
    assert "BBB" not in w, "BBB (lower conviction, |corr|>0.80 with AAA) should be de-duped"


def test_correlation_reader_error_falls_back_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Correlation read failure must not crash phase7e; corr=None is the safe fallback."""
    from digiquant.olympus.atlas.data import queries as _queries_mod

    def _boom(**_kwargs):
        raise RuntimeError("price_history table gone")

    monkeypatch.setattr(_queries_mod, "get_return_correlations", _boom)

    captured: dict = {}
    original_size = phase7e_risk_sizing.size_portfolio

    def _spy(**kwargs):
        captured["corr"] = kwargs.get("corr")
        return original_size(**kwargs)

    monkeypatch.setattr(phase7e_risk_sizing, "size_portfolio", _spy)

    rebal = _run(
        _state(
            [{"ticker": "SPY", "target_pct": 100}],
            analysts={"SPY": {"conviction_score": 5, "stance": "buy"}},
        ),
        FakeSupabaseClient(canned_reads={"price_technicals": _tech_rows({"SPY": 15})}),
    )
    # The node must still produce a valid sized book.
    assert rebal is not None
    assert "SPY" in _weights(rebal)
    # And corr=None must have been passed (conservative fallback).
    assert captured.get("corr") is None, "expected corr=None fallback on reader error"
