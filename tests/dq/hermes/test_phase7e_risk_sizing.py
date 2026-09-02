"""Phase 7E — deterministic risk-sizing enforcement (#726, Pillar 2).

The node replaces the PM's eyeballed candidate book with sized, capped, reduce-only
weights and rebuilds the advisory action list, reading per-ticker vol from
``price_technicals`` (look-ahead-guarded) and sector buckets from ``sector_map``. It is
fail-soft (errors keep the PM book) and a no-op when the PM never ran.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import polars as pl
import pytest
from digiquant.olympus.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    ExcludedTicker,
    PhaseHermesState,
    PriorContext,
)
from digiquant.olympus.hermes.models.pm_direction import PMDirectionMemo, TickerDirection
from digiquant.olympus.hermes.phases import phase7e_risk_sizing
from digiquant.olympus.hermes.phases.phase7e_risk_sizing import (
    RiskSizingDeps,
    build_risk_sizing_node,
)
from digiquant.olympus.hermes.sizing_events import (
    SizingAdjustment,
    SizingAdjustmentType,
    UnexplainedDeltaError,
    validate_sizing_lineage,
)
from digiquant.olympus.hermes.turnover import (
    apply_turnover_to_sized_book,
    clamp_no_trade_band,
    hold_drifted_book,
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


class TestUnchallengedCarryIsLowConfidence:
    """#1742 — a position whose H6 debate crashed may not be sized as a won argument.

    On 2026-07-31 the three highest-conviction new opens (VGK/FXI/IBIT, 30% of NAV) were
    all crash-carried: H6 published the analyst's own stance as a converged debate, and
    sizing had no way to know the PM challenge never ran.
    """

    _ANALYSTS = {
        "AAA": {"conviction_score": 3, "stance": "buy"},
        "BBB": {"conviction_score": 3, "stance": "buy"},
    }

    def _sized(
        self,
        debates: dict,
        preferences: dict | None = None,
        analysts: dict | None = None,
        **kwargs,
    ) -> dict:
        return _run(
            _state(
                [{"ticker": "AAA", "target_pct": 50}, {"ticker": "BBB", "target_pct": 50}],
                analysts=analysts or dict(self._ANALYSTS),
                debates=debates,
                preferences={**_RELAXED, **(preferences or {})},
                **kwargs,
            ),
            FakeSupabaseClient(
                canned_reads={"price_technicals": _tech_rows({"AAA": 20, "BBB": 20})}
            ),
        )

    def test_memo_path_caps_the_crash_carried_name_at_the_bar(self) -> None:
        # The memo branch is production (H7 writes a memo every run): rank 1 (AAA) would
        # outweigh rank 2 (BBB), but AAA's debate crashed, so it drops to the entry bar.
        rebal = self._sized({"AAA": {"carried": True, "carry_reason": "llm_failure"}})
        w = _weights(rebal)
        assert w["AAA"] == pytest.approx(w["BBB"])
        # Capped, never ejected — the name stays in the book and is named in the note.
        assert "AAA" in w
        assert "H6 deliberation failed" in rebal["notes"]
        # #2417 — the crash-carry haircut is reason-coded in the conviction domain, not
        # the weight-pct domain the book itself is asserted in above.
        conviction_events = [
            a for a in rebal["adjustments"] if a["adjustment_type"] == "conviction_floor"
        ]
        assert len(conviction_events) == 1
        event = conviction_events[0]
        assert event["ticker"] == "AAA"
        assert event["unit"] == "conviction"
        assert event["adjusted_pct"] == pytest.approx(2.0)  # default SizingCaps.min_conviction
        assert event["original_pct"] > event["adjusted_pct"]
        assert not any(a["ticker"] == "BBB" for a in conviction_events)

    def test_benign_fingerprint_skip_keeps_full_conviction(self) -> None:
        # The quiet-ticker carry (#925) is a real prior debate; it must not be haircut.
        rebal = self._sized({"AAA": {"carried": True, "carry_reason": "fingerprint_skip"}})
        w = _weights(rebal)
        assert w["AAA"] > w["BBB"]
        assert "H6 deliberation failed" not in rebal["notes"]
        # #2417 — a benign fingerprint-skip carry is a real debate, not an unchallenged
        # crash-carry, so it must never emit a conviction-floor event.
        assert not any(a["adjustment_type"] == "conviction_floor" for a in rebal["adjustments"])

    def test_legacy_path_caps_the_crash_carried_name_too(self) -> None:
        # No-memo branch, with the un-carried run as its own control: AAA's analyst
        # conviction of 5 outweighs BBB's 2 until AAA's debate crashes.
        analysts = {
            "AAA": {"conviction_score": 5, "stance": "buy"},
            "BBB": {"conviction_score": 2, "stance": "buy"},
        }
        control = self._sized({}, analysts=analysts, use_memo=False)
        crashed = self._sized(
            {"AAA": {"carried": True, "carry_reason": "llm_failure"}},
            analysts=analysts,
            use_memo=False,
        )
        assert _weights(control)["AAA"] > _weights(control)["BBB"]
        assert _weights(crashed)["AAA"] == pytest.approx(_weights(crashed)["BBB"])
        # #2417 — legacy (no-memo) path fires the same event; the un-carried control run
        # must not.
        assert not any(a["adjustment_type"] == "conviction_floor" for a in control["adjustments"])
        assert any(a["adjustment_type"] == "conviction_floor" for a in crashed["adjustments"])

    def test_cap_holds_when_the_bar_is_raised_above_the_default(self) -> None:
        # ``min_conviction`` above the memo floor of 2.0: capping AT the bar still clears
        # the sizer's ``>=`` selection, so the position survives at minimum size.
        rebal = self._sized(
            {"AAA": {"carried": True, "carry_reason": "llm_failure"}},
            preferences={"min_conviction": 3.0},
        )
        w = _weights(rebal)
        assert "AAA" in w
        assert w["AAA"] == pytest.approx(w["BBB"])
        # #2417 — a raised bar is reflected verbatim in the event's adjusted_pct.
        conviction_events = [
            a for a in rebal["adjustments"] if a["adjustment_type"] == "conviction_floor"
        ]
        assert len(conviction_events) == 1
        assert conviction_events[0]["adjusted_pct"] == pytest.approx(3.0)


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


def test_memo_path_publishes_h7_narrative_as_action_rationale() -> None:
    roster = [
        TickerDirection(
            ticker="AAA",
            direction="long",
            conviction_rank=1,
            narrative="Express persistent energy scarcity via upstream exposure.",
        ),
        TickerDirection(
            ticker="BBB",
            direction="long",
            conviction_rank=2,
            narrative="Hedge duration risk with short-duration credit.",
        ),
    ]
    rebal = _run(
        _memo_state(
            roster,
            analysts={
                "AAA": {"conviction_score": 5, "stance": "buy"},
                "BBB": {"conviction_score": 4, "stance": "buy"},
            },
        ),
        FakeSupabaseClient(canned_reads={"price_technicals": _tech_rows({"AAA": 20, "BBB": 20})}),
    )
    by_ticker = {row["ticker"]: row["rationale"] for row in rebal["actions"]}
    assert by_ticker["AAA"] == "Express persistent energy scarcity via upstream exposure."
    assert by_ticker["BBB"] == "Hedge duration risk with short-duration credit."


def _memo_state(
    roster: list[TickerDirection],
    *,
    analysts: dict[str, dict[str, object]] | None = None,
    preferences: dict | None = None,
) -> AtlasResearchState:
    state = AtlasResearchState(
        run_type="delta",
        run_date=RUN_DATE,
        config=AtlasConfigBundle(preferences=preferences or _RELAXED),
    )
    state.phase_hermes = PhaseHermesState(
        pm_direction_memo=PMDirectionMemo(date=RUN_DATE, roster=roster, memo="PM notes."),
        asset_analysts=analysts or {},
    )
    return state


def test_gapful_h7_ranks_match_dense_fallback() -> None:
    """Gapful ranks [2,7,11] must size like dense [1,2,3] (WP8.1)."""
    tickers = ["AAA", "BBB", "CCC"]
    vols = _tech_rows({t: 20 for t in tickers})
    dense_roster = [
        TickerDirection(ticker=t, direction="long", conviction_rank=idx + 1)
        for idx, t in enumerate(tickers)
    ]
    gapful_roster = [
        TickerDirection(ticker="AAA", direction="long", conviction_rank=2),
        TickerDirection(ticker="BBB", direction="long", conviction_rank=7),
        TickerDirection(ticker="CCC", direction="long", conviction_rank=11),
    ]
    dense = _weights(
        _run(_memo_state(dense_roster), FakeSupabaseClient(canned_reads={"price_technicals": vols}))
    )
    gapful = _weights(
        _run(
            _memo_state(gapful_roster), FakeSupabaseClient(canned_reads={"price_technicals": vols})
        )
    )
    assert set(dense) == set(gapful) == set(tickers)
    for ticker in tickers:
        assert dense[ticker] == pytest.approx(gapful[ticker])


def test_duplicate_h7_ranks_tie_by_symbol() -> None:
    """Duplicate ranks resolve deterministically by ticker symbol (WP8.1)."""
    roster = [
        TickerDirection(ticker="BBB", direction="long", conviction_rank=1),
        TickerDirection(ticker="AAA", direction="long", conviction_rank=1),
    ]
    vols = _tech_rows({"AAA": 20, "BBB": 20})
    w = _weights(
        _run(_memo_state(roster), FakeSupabaseClient(canned_reads={"price_technicals": vols}))
    )
    assert w["AAA"] > w["BBB"]


def test_h5_sell_cannot_drop_h7_long() -> None:
    """H5 sell/watch must not remove an H7-authorized long (WP8.1)."""
    roster = [TickerDirection(ticker="AAA", direction="long", conviction_rank=1)]
    analysts = {"AAA": {"conviction_score": 5, "stance": "sell"}}
    w = _weights(
        _run(
            _memo_state(roster, analysts=analysts),
            FakeSupabaseClient(canned_reads={"price_technicals": _tech_rows({"AAA": 15})}),
        )
    )
    assert "AAA" in w
    assert w["AAA"] > 0


def test_h7_flat_not_admitted_via_h5_buy() -> None:
    """H7 flat roster entry cannot enter sizing through H5 buy alone (WP8.1)."""
    roster = [
        TickerDirection(ticker="SPY", direction="long", conviction_rank=1),
        TickerDirection(ticker="DBO", direction="flat", conviction_rank=2),
    ]
    analysts = {
        "SPY": {"conviction_score": 5, "stance": "buy"},
        "DBO": {"conviction_score": 5, "stance": "buy"},
    }
    w = _weights(
        _run(
            _memo_state(roster, analysts=analysts),
            FakeSupabaseClient(
                canned_reads={"price_technicals": _tech_rows({"SPY": 15, "DBO": 15})}
            ),
        )
    )
    assert "SPY" in w
    assert "DBO" not in w


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
    # Legacy path: no rebalance update when sizing fails; WP6.3 may still attach audit snapshots.
    out = build_risk_sizing_node(RiskSizingDeps(client=FakeSupabaseClient()))(state)
    assert out.get("phase7d_rebalance") is None
    hermes = out.get("phase_hermes")
    if hermes is not None:
        assert hermes.sized_book is None
        assert hermes.risk_policy is not None
        assert hermes.covariance_snapshot is not None
    else:
        assert out == {}


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


@pytest.mark.unit
class TestHeldContinuityBackstop:
    """#1649 backstop — the FINAL sized book enforces held ⇒ positive weight or flat.

    The 2026-07-22 22:54 run reached H9 with NINE held names at weight<=0 despite the
    memo-unaddressed carry being live — the invariant must hold on the final dict
    regardless of which upstream crack fired.
    """

    def _held_state(self, *, flat: bool = False, with_weight: bool = True) -> AtlasResearchState:
        prior_book = [{"ticker": "DBO", "weight_pct": 7.5 if with_weight else None}]
        state = AtlasResearchState(
            run_type="delta",
            run_date=RUN_DATE,
            baseline_date=date(2026, 6, 9),
            config=AtlasConfigBundle(preferences={}),
            prior_context=PriorContext(prior_book=prior_book),
        )
        roster = [TickerDirection(ticker="SPY", direction="long", conviction_rank=1)]
        if flat:
            roster.append(TickerDirection(ticker="DBO", direction="flat", conviction_rank=2))
        else:
            # The exact 2026-07-22 shape: PM addressed the held name as long,
            # but sizing dropped it (weight absent from the final dict).
            roster.append(TickerDirection(ticker="DBO", direction="long", conviction_rank=2))
        state.phase_hermes = PhaseHermesState(
            pm_direction_memo=PMDirectionMemo(date=RUN_DATE, roster=roster)
        )
        return state

    def test_sized_out_held_name_is_readded_at_drifted_weight(self) -> None:
        state = self._held_state()
        events: list[SizingAdjustment] = []
        out = phase7e_risk_sizing._apply_held_continuity_backstop(
            {"SPY": 60.0}, state, events=events
        )
        assert out["DBO"] == 7.5, "held name dropped by sizing must be re-added"
        assert out["SPY"] == 60.0
        # #2417 — the re-add is a CONTINUITY_CARRY off an implicit (0) prior weight, never
        # conflated with a FLAT_EXIT (this ticker was never PM-flatted).
        assert len(events) == 1
        assert events[0].ticker == "DBO"
        assert events[0].adjustment_type == SizingAdjustmentType.CONTINUITY_CARRY
        assert events[0].original_pct == pytest.approx(0.0)
        assert events[0].adjusted_pct == pytest.approx(7.5)
        assert not any(e.adjustment_type == SizingAdjustmentType.FLAT_EXIT for e in events)

    def test_explicit_flat_is_never_resurrected(self) -> None:
        state = self._held_state(flat=True)
        events: list[SizingAdjustment] = []
        out = phase7e_risk_sizing._apply_held_continuity_backstop(
            {"SPY": 60.0}, state, events=events
        )
        assert "DBO" not in out, "an explicit flat is an exit — never re-added"
        # #2417 — H7-flat is FLAT_EXIT, structurally distinct from CONTINUITY_CARRY: a
        # ticker can never carry both event types out of this one call.
        assert len(events) == 1
        assert events[0].ticker == "DBO"
        assert events[0].adjustment_type == SizingAdjustmentType.FLAT_EXIT
        assert not any(e.adjustment_type == SizingAdjustmentType.CONTINUITY_CARRY for e in events)

    def test_unrecoverable_weight_stays_out_and_fails_closed_downstream(self) -> None:
        state = self._held_state(with_weight=False)
        events: list[SizingAdjustment] = []
        out = phase7e_risk_sizing._apply_held_continuity_backstop(
            {"SPY": 60.0}, state, events=events
        )
        assert "DBO" not in out, "no recoverable weight → leave out; H9 fails closed"
        # #2417 — no recoverable weight means no adjustment was actually made; nothing to
        # reason-code.
        assert events == []

    def test_non_held_names_untouched(self) -> None:
        state = self._held_state()
        events: list[SizingAdjustment] = []
        out = phase7e_risk_sizing._apply_held_continuity_backstop(
            {"SPY": 60.0, "QQQ": 0.0}, state, events=events
        )
        assert out["QQQ"] == 0.0, "backstop is held-only"
        # #2417 — QQQ is not a held ticker; the backstop never touches it or emits for it.
        assert not any(e.ticker == "QQQ" for e in events)


@pytest.mark.unit
class TestActionClassificationAndInvestedCap:
    """#1676 — held rebalances classify add/trim/hold (not 'new'); Σ invested ≤ 100%."""

    def test_memo_path_actions_classify_against_live_weights(self) -> None:
        # The H7 memo path passes original_actions=[] — previously EVERYTHING was "new".
        actions = phase7e_risk_sizing._rebuild_actions(
            [],
            pm_targets={"AAA": 1.0, "BBB": 1.0, "CCC": 1.0, "DDD": 1.0},
            sized={"AAA": 8.0, "BBB": 3.0, "CCC": 5.0, "DDD": 6.0},
            current_weights={"AAA": 5.0, "BBB": 5.0, "CCC": 5.0},
        )
        verbs = {row["ticker"]: row["action"] for row in actions}
        assert verbs == {"AAA": "add", "BBB": "trim", "CCC": "hold", "DDD": "new"}

    def test_post_cap_micro_delta_classifies_as_hold_and_carries_current_pct(self) -> None:
        """#3080 — immaterial post-control deltas publish as hold with live current_pct."""
        preferences = {"rebalance_threshold_pct": 3, "rebalance_rel_band_pct": 20}
        current = {"SPY": 20.0}
        sized = phase7e_risk_sizing._cap_total_invested({"SPY": 20.2, "QQQ": 80.0})
        sized = clamp_no_trade_band(sized, current_weights=current, preferences=preferences)
        actions = phase7e_risk_sizing._rebuild_actions(
            [],
            pm_targets={"SPY": 1.0},
            sized=sized,
            current_weights=current,
            preferences=preferences,
        )
        spy = next(a for a in actions if a["ticker"] == "SPY")
        assert spy["action"] == "hold"
        assert spy["current_pct"] == pytest.approx(20.0)
        assert spy["target_pct"] == pytest.approx(20.0)

    def test_memo_path_actions_carry_pm_selection_rationale(self) -> None:
        actions = phase7e_risk_sizing._rebuild_actions(
            [],
            pm_targets={"AAA": 1.0, "BBB": 1.0},
            sized={"AAA": 8.0, "BBB": 3.0},
            current_weights={"AAA": 5.0, "BBB": 5.0},
            selection_rationale_by_ticker={
                "AAA": "PM: energy scarcity thesis via upstream exposure.",
                "BBB": "PM: hedge duration risk with short-duration credit.",
            },
        )
        by_ticker = {row["ticker"]: row["rationale"] for row in actions}
        assert by_ticker["AAA"] == "PM: energy scarcity thesis via upstream exposure."
        assert by_ticker["BBB"] == "PM: hedge duration risk with short-duration credit."
        assert "deterministic risk sizing" not in by_ticker["AAA"]

    def test_memo_path_falls_back_to_sizing_note_without_selection_rationale(self) -> None:
        actions = phase7e_risk_sizing._rebuild_actions(
            [],
            pm_targets={"AAA": 1.0},
            sized={"AAA": 8.0},
            current_weights={"AAA": 5.0},
        )
        assert actions[0]["rationale"] == "Position weight set by deterministic risk sizing."

    def test_cap_scales_proportionally_over_100(self) -> None:
        events: list[SizingAdjustment] = []
        capped = phase7e_risk_sizing._cap_total_invested({"A": 60.0, "B": 50.0}, events=events)
        assert round(sum(capped.values()), 6) == 100.0
        assert round(capped["A"] / capped["B"], 6) == round(60.0 / 50.0, 6)
        # #2417 — every rescaled leg gets a FINAL_GROSS_SCALE event carrying the exact
        # pre/post values already asserted above.
        assert {e.ticker for e in events} == {"A", "B"}
        by_ticker = {e.ticker: e for e in events}
        assert by_ticker["A"].adjustment_type == SizingAdjustmentType.FINAL_GROSS_SCALE
        assert by_ticker["A"].original_pct == pytest.approx(60.0)
        assert by_ticker["A"].adjusted_pct == pytest.approx(capped["A"])
        assert by_ticker["B"].original_pct == pytest.approx(50.0)
        assert by_ticker["B"].adjusted_pct == pytest.approx(capped["B"])

    def test_cap_leaves_valid_books_untouched(self) -> None:
        book = {"A": 60.0, "B": 30.0}
        events: list[SizingAdjustment] = []
        assert phase7e_risk_sizing._cap_total_invested(dict(book), events=events) == book
        # #2417 — a book already at/under 100 is not rescaled, so no event fires.
        assert events == []

    def test_backstop_overshoot_is_capped(self) -> None:
        # The #1649 backstop legitimately re-adds drifted weight onto a full book;
        # the cap must bring the composition back to exactly 100.
        sized = {"A": 70.0, "B": 30.0}
        sized["DBO"] = 7.5  # backstop re-add
        events: list[SizingAdjustment] = []
        capped = phase7e_risk_sizing._cap_total_invested(sized, events=events)
        assert round(sum(capped.values()), 6) == 100.0
        assert capped["DBO"] > 0, "the rescued position survives the cap"
        # #2417 — DBO's rescale is reason-coded too, not just A/B's.
        assert any(
            e.ticker == "DBO" and e.adjustment_type == SizingAdjustmentType.FINAL_GROSS_SCALE
            for e in events
        )


# --------------------------------------------------------------------------- #2417 adjustment events


def test_held_carry_weights_direct_call_returns_drifted_weight_only() -> None:
    # Same memo-unaddressed fixture shape as TestHeldContinuityBackstop, exercised
    # directly against the earlier carry-injection function (#1030/#1555/#1649).
    # #2417 CodeRabbit review on #2434: this function no longer takes/emits events —
    # whether a carry actually lands (and so whether a CONTINUITY_CARRY event is
    # warranted) depends on the caller's own sized-dict check, exercised below in
    # ``TestCarryLoopEventEmission``.
    prior_book = [{"ticker": "DBO", "weight_pct": 7.5}]
    state = AtlasResearchState(
        run_type="delta",
        run_date=RUN_DATE,
        baseline_date=date(2026, 6, 9),
        config=AtlasConfigBundle(preferences={}),
        prior_context=PriorContext(prior_book=prior_book),
    )
    roster = [TickerDirection(ticker="SPY", direction="long", conviction_rank=1)]
    state.phase_hermes = PhaseHermesState(
        pm_direction_memo=PMDirectionMemo(date=RUN_DATE, roster=roster)
    )
    assert phase7e_risk_sizing._held_carry_weights(state) == {"DBO": 7.5}


@pytest.mark.unit
class TestCarryLoopEventEmission:
    """#2417 CodeRabbit review on #2434 (finding: phantom CONTINUITY_CARRY events).

    ``_build_sized_book``'s carry loop (around ``_held_carry_weights``) must emit a
    CONTINUITY_CARRY event only when the carry actually lands in ``sized`` — not
    when the ticker was already sized by the PM/sizer and the carry is a no-op. DBO
    is H4-gated (``focus_roster_excluded``) in both cases, so it is always in
    ``carried_held_tickers``; the two cases differ only in whether the H7 memo also
    addresses it as ``long`` (which feeds it into ``size_portfolio`` and pre-fills
    ``sized`` before the carry loop runs).
    """

    def _gated_state(self, *, memo_addressed: bool) -> AtlasResearchState:
        state = AtlasResearchState(
            run_type="delta",
            run_date=RUN_DATE,
            baseline_date=date(2026, 6, 9),
            config=AtlasConfigBundle(preferences=dict(_RELAXED)),
            prior_context=PriorContext(prior_book=[{"ticker": "DBO", "weight_pct": 7.5}]),
        )
        roster = [TickerDirection(ticker="SPY", direction="long", conviction_rank=1)]
        if memo_addressed:
            roster.append(TickerDirection(ticker="DBO", direction="long", conviction_rank=2))
        state.phase_hermes = PhaseHermesState(
            pm_direction_memo=PMDirectionMemo(date=RUN_DATE, roster=roster),
            focus_roster_excluded=[ExcludedTicker(ticker="DBO", reason="stale")],
        )
        return state

    def test_memo_unaddressed_carry_lands_and_emits_event(self) -> None:
        # DBO is gated AND memo-unaddressed: absent from size_portfolio's input, so
        # the carry loop's setdefault-style check finds it not-yet-sized and both
        # applies the drifted weight and reason-codes it.
        rebal = _run(
            self._gated_state(memo_addressed=False),
            FakeSupabaseClient(canned_reads={"price_technicals": _tech_rows({"SPY": 15})}),
        )
        # SPY's memo-derived target plus DBO's 7.5% carry exceed 100%, so
        # _cap_total_invested legitimately scales both down together — assert the
        # carry landed (positive weight, reason-coded), not an exact pre-cap value.
        assert _weights(rebal)["DBO"] > 0
        carries = [a for a in rebal["adjustments"] if a["adjustment_type"] == "continuity_carry"]
        assert any(a["ticker"] == "DBO" for a in carries)

    def test_memo_addressed_and_already_sized_skips_duplicate_event(self) -> None:
        # DBO is gated but ALSO explicitly addressed "long" by the memo, so it flows
        # through size_portfolio and is already in ``sized`` before the carry loop
        # runs. Before this fix, the loop appended a CONTINUITY_CARRY event
        # unconditionally here even though ``setdefault`` was a no-op — a phantom
        # record describing a carry that never happened.
        rebal = _run(
            self._gated_state(memo_addressed=True),
            FakeSupabaseClient(
                canned_reads={"price_technicals": _tech_rows({"SPY": 15, "DBO": 15})}
            ),
        )
        assert "DBO" in _weights(rebal)
        carries = [a for a in rebal["adjustments"] if a["adjustment_type"] == "continuity_carry"]
        assert not any(a["ticker"] == "DBO" for a in carries)


def test_h7_flat_and_omitted_held_never_conflate_on_the_same_ticker() -> None:
    """#2417 — flat (FLAT_EXIT) and omitted/unaddressed (CONTINUITY_CARRY) are structurally
    exclusive: ``memo_addressed_tickers`` already includes flat-tagged tickers, so a held
    ticker can reach exactly one of the two backstop branches, never both.
    """
    harness = TestHeldContinuityBackstop()
    flat_events: list[SizingAdjustment] = []
    carry_events: list[SizingAdjustment] = []
    phase7e_risk_sizing._apply_held_continuity_backstop(
        {"SPY": 60.0}, harness._held_state(flat=True), events=flat_events
    )
    phase7e_risk_sizing._apply_held_continuity_backstop(
        {"SPY": 60.0}, harness._held_state(flat=False), events=carry_events
    )
    flat_types = {e.adjustment_type for e in flat_events if e.ticker == "DBO"}
    carry_types = {e.adjustment_type for e in carry_events if e.ticker == "DBO"}
    assert flat_types == {SizingAdjustmentType.FLAT_EXIT}
    assert carry_types == {SizingAdjustmentType.CONTINUITY_CARRY}
    assert flat_types.isdisjoint(carry_types)


def test_hold_drifted_book_direct_call_covers_all_three_branches() -> None:
    events: list[SizingAdjustment] = []
    out = hold_drifted_book(
        {"SPY": 25.0, "TLT": 0.0, "QQQ": 10.0},
        current_weights={"SPY": 20.0, "TLT": 15.0},
        events=events,
    )
    # continuing position (SPY): held at drifted current weight, not rebalanced to target
    assert out["SPY"] == 20.0
    # PM exit honored off-cadence (TLT): dropped to flat (residual becomes cash)
    assert "TLT" not in out
    # new entry (QQQ): booked at its sized target, no current weight to hold
    assert out["QQQ"] == 10.0

    by_ticker = {e.ticker: e for e in events}
    assert by_ticker["SPY"].adjustment_type == SizingAdjustmentType.CADENCE_HOLD
    assert by_ticker["SPY"].original_pct == pytest.approx(25.0)
    assert by_ticker["SPY"].adjusted_pct == pytest.approx(20.0)
    assert by_ticker["TLT"].adjustment_type == SizingAdjustmentType.FLAT_EXIT
    assert by_ticker["TLT"].original_pct == pytest.approx(15.0)
    assert by_ticker["TLT"].adjusted_pct == pytest.approx(0.0)
    # the new-entry branch is not an adjustment — no event for QQQ.
    assert "QQQ" not in by_ticker


def test_apply_turnover_minimum_hold_override_emits_event_band_clamp_does_not() -> None:
    events: list[SizingAdjustment] = []
    out = apply_turnover_to_sized_book(
        {"SPY": 0.0, "TLT": 18.0},
        current_weights={"SPY": 20.0, "TLT": 20.0},
        prior_book=[
            {"ticker": "SPY", "weight_pct": 20, "entry_date": "2026-06-17"},  # inside hold
            {"ticker": "TLT", "weight_pct": 20, "entry_date": "2026-06-01"},  # outside hold
        ],
        preferences={"rebalance_threshold_pct": 3, "holding_days": 5},
        run_date=date(2026, 6, 19),
        events=events,
    )
    assert out["SPY"] == 20.0  # exit blocked by min-hold lockup
    assert out["TLT"] == 20.0  # 2pp delta < 3pp band → no-trade-band clamp holds it too

    # Only the min-hold override is a reason-coded adjustment; the no-trade-band clamp
    # is deliberately silent (#2417 §3 — the suppressed delta is immaterial by construction).
    assert len(events) == 1
    event = events[0]
    assert event.ticker == "SPY"
    assert event.adjustment_type == SizingAdjustmentType.MINIMUM_HOLD_OVERRIDE
    assert event.original_pct == pytest.approx(0.0)
    assert event.adjusted_pct == pytest.approx(20.0)


class TestValidateSizingLineage:
    """#2417 §6/§7 — the standalone validator, exercised directly.

    The wired production call site (``_validate_h8_lineage``, invoked from
    ``risk_sizing()`` after ``_build_sized_book`` returns) has its own coverage
    below in ``TestValidateH8LineageCallSite`` — both the golden path (a real,
    materially-capped book that logs nothing) and the regression path (a
    monkeypatched silent mutation that the wired check must catch).
    """

    def test_unexplained_material_delta_raises(self) -> None:
        with pytest.raises(UnexplainedDeltaError, match="AAA"):
            validate_sizing_lineage(
                requested={"AAA": 10.0, "BBB": 5.0},
                approved={"AAA": 4.0, "BBB": 5.0},
                adjustments=[],
                materiality_pct=1.0,
            )

    def test_fully_explained_delta_does_not_raise(self) -> None:
        adjustment = SizingAdjustment(
            ticker="AAA",
            adjustment_type=SizingAdjustmentType.SINGLE_NAME_CAP,
            original_pct=10.0,
            adjusted_pct=4.0,
            reason="single-name cap",
        )
        validate_sizing_lineage(
            requested={"AAA": 10.0, "BBB": 5.0},
            approved={"AAA": 4.0, "BBB": 5.0},
            adjustments=[adjustment],
            materiality_pct=1.0,
        )  # must not raise

    def test_delta_inside_materiality_band_does_not_raise(self) -> None:
        # 0.5pp delta < the 1.0pp band — immaterial by the pipeline's own definition,
        # so no explaining event is required (mirrors the turnover no-trade-band clamp).
        validate_sizing_lineage(
            requested={"AAA": 10.0},
            approved={"AAA": 10.5},
            adjustments=[],
            materiality_pct=1.0,
        )  # must not raise


class TestLineageMaterialityPct:
    """#2417 §6 — ``_lineage_materiality_pct`` mirrors the turnover no-trade-band formula."""

    def test_defaults_when_preferences_empty(self) -> None:
        assert phase7e_risk_sizing._lineage_materiality_pct({}) == pytest.approx(3.0)

    def test_relative_band_wins_when_wider_than_the_flat_threshold(self) -> None:
        # 20% of a 50%-weight current position = 10pp, wider than the 3pp flat floor.
        pct = phase7e_risk_sizing._lineage_materiality_pct(
            {
                "rebalance_threshold_pct": 3,
                "rebalance_rel_band_pct": 20,
                "current_weights": {"SPY": 50.0},
            }
        )
        assert pct == pytest.approx(10.0)

    def test_flat_threshold_wins_when_current_weights_are_small(self) -> None:
        # 20% of a 5%-weight position = 1pp, narrower than the 3pp flat floor.
        pct = phase7e_risk_sizing._lineage_materiality_pct(
            {
                "rebalance_threshold_pct": 3,
                "rebalance_rel_band_pct": 20,
                "current_weights": {"SPY": 5.0},
            }
        )
        assert pct == pytest.approx(3.0)


class TestValidateH8LineageCallSite:
    """#2417 §6/§7 — the production call site wired into ``risk_sizing()``, not just the
    standalone validator (closes the gap flagged in OLY-REV-009 finding #4).
    """

    def test_direct_call_is_silent_when_every_material_delta_has_an_event(self) -> None:
        adjustment = SizingAdjustment(
            ticker="SPY",
            adjustment_type=SizingAdjustmentType.SINGLE_NAME_CAP,
            original_pct=50.0,
            adjusted_pct=30.0,
            reason="single-name cap",
        )
        sized_book: dict = {
            "recommended_portfolio": [{"ticker": "SPY", "target_pct": 30.0}],
            "adjustments": [adjustment.model_dump()],
        }
        # must not raise and must not log — nothing here is a failure.
        phase7e_risk_sizing._validate_h8_lineage({"SPY": 50.0}, sized_book, {})

    def test_direct_call_logs_but_does_not_raise_on_unexplained_delta(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        sized_book: dict = {
            "recommended_portfolio": [{"ticker": "SPY", "target_pct": 10.0}],
            "adjustments": [],
        }
        with caplog.at_level(logging.ERROR, logger=phase7e_risk_sizing.__name__):
            phase7e_risk_sizing._validate_h8_lineage({"SPY": 50.0}, sized_book, {})
        assert "H8 lineage validation failed" in caplog.text

    def test_wired_end_to_end_golden_path_logs_nothing(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # A real position-capped book (50% requested -> 30% cap) through the actual
        # ``risk_sizing()`` node: the cap step emits a SINGLE_NAME_CAP event, so the
        # wired lineage check finds nothing unexplained and logs no error.
        client = FakeSupabaseClient(canned_reads={"price_technicals": _tech_rows({"SPY": 15})})
        state = _state(
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
        )
        with caplog.at_level(logging.ERROR, logger=phase7e_risk_sizing.__name__):
            out = build_risk_sizing_node(RiskSizingDeps(client=client))(state)
        rebal = out["phase7d_rebalance"]
        assert rebal["recommended_portfolio"][0]["target_pct"] == pytest.approx(30.0)
        assert "H8 lineage validation failed" not in caplog.text

    def test_wired_memo_path_logs_nothing_despite_no_matching_adjustment(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # #2417 CodeRabbit review on #2434 (Fix #4): the H7 memo path's "targets" are
        # conviction-weight placeholders (1.0 per long ticker), not pct-scale PM
        # requests — comparing them against the sizer's actual pct output as if they
        # were the same unit produced a spurious "unexplained delta" on every run,
        # even with zero real adjustments. Default (non-_RELAXED) preferences drive
        # SPY's vol-scaled weight far from the 1.0 placeholder on purpose, so this
        # would have false-positived before ``targets_are_weights`` gated it off for
        # the memo path.
        client = FakeSupabaseClient(canned_reads={"price_technicals": _tech_rows({"SPY": 15})})
        state = _state(
            [{"ticker": "SPY", "target_pct": 50}],
            analysts={"SPY": {"conviction_score": 5, "stance": "buy"}},
        )
        with caplog.at_level(logging.ERROR, logger=phase7e_risk_sizing.__name__):
            out = build_risk_sizing_node(RiskSizingDeps(client=client))(state)
        rebal = out["phase_hermes"].sized_book
        assert "SPY" in _weights(rebal)
        assert "H8 lineage validation failed" not in caplog.text

    def test_wired_end_to_end_catches_a_silent_regression_and_stays_fail_soft(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Simulates a future adjustment site silently mutating a weight without emitting
        a ``SizingAdjustment`` — exactly the regression class this lineage layer exists
        to catch — by monkeypatching ``_cap_total_invested`` (a real call site inside
        ``_build_sized_book``) with a variant that mutates but never appends to
        ``events``. Asserts the wired check (a) logs the failure and (b) stays
        fail-soft: ``risk_sizing()`` still returns the already-computed sized book
        unchanged, it never raises past this point.
        """

        def _silently_mutating_cap_total_invested(
            sized: dict[str, float], events: list | None = None
        ) -> dict[str, float]:
            mutated = dict(sized)
            if "SPY" in mutated:
                mutated["SPY"] = mutated["SPY"] * 0.5
            return mutated

        monkeypatch.setattr(
            phase7e_risk_sizing,
            "_cap_total_invested",
            _silently_mutating_cap_total_invested,
        )

        # PM's own target_pct (10) is deliberately far from the sizing pipeline's
        # natural full-conviction allocation (100% for a single long, uncapped under
        # _RELAXED) so the post-mutation value (50, see below) cannot coincidentally
        # land back on the PM's requested number and mask the injected regression.
        client = FakeSupabaseClient(canned_reads={"price_technicals": _tech_rows({"SPY": 15})})
        state = _state(
            [{"ticker": "SPY", "target_pct": 10}],
            analysts={"SPY": {"conviction_score": 5, "stance": "buy"}},
            preferences=_RELAXED,
            use_memo=False,
        )
        with caplog.at_level(logging.ERROR, logger=phase7e_risk_sizing.__name__):
            out = build_risk_sizing_node(RiskSizingDeps(client=client))(state)

        # fail-soft: the node still returns the sized book, unmutated by the lineage
        # check itself — the silent 100%→50% regression is the injected fault, not a
        # side effect of validation. (A single full-conviction ticker sizes to 100%
        # under _RELAXED caps before the monkeypatched halving runs.)
        rebal = out["phase7d_rebalance"]
        assert rebal["recommended_portfolio"][0]["target_pct"] == pytest.approx(50.0)
        assert "H8 lineage validation failed" in caplog.text


# --------------------------------------------------------------------------- WP6.1 incumbent golden paths (#2687)


def test_incumbent_memo_and_effective_inputs_match_golden_fixture() -> None:
    """Freeze ``_memo_effective_inputs`` and ``_effective_inputs`` before WP6.2.

    WP8.1: memo-path stances are always ``buy`` — H7 owns eligibility, not H5.
    """
    from datetime import date

    from digiquant.olympus.hermes.models.pm_direction import PMDirectionMemo, TickerDirection

    from tests.dq.hermes.incumbent_risk_fixtures import load_incumbent_risk_fixture

    golden = load_incumbent_risk_fixture()
    memo = PMDirectionMemo(
        date=date(2026, 6, 12),
        roster=[
            TickerDirection(ticker="AAA", direction="long", conviction_rank=1),
            TickerDirection(ticker="BBB", direction="long", conviction_rank=2),
            TickerDirection(ticker="CCC", direction="long", conviction_rank=3),
        ],
        memo="test",
    )
    memo_conv, memo_st = phase7e_risk_sizing._memo_effective_inputs(
        memo,
        {"AAA": {"stance": "buy"}, "BBB": {"stance": "hold"}, "CCC": {"stance": "sell"}},
        2.0,
    )
    expected_memo = golden["memo_effective_inputs"]["three_long_mixed_stances"]
    assert {k: round(v, 4) for k, v in memo_conv.items()} == expected_memo["convictions"]
    assert memo_st == expected_memo["stances"]

    leg_conv, leg_st = phase7e_risk_sizing._effective_inputs(
        ["AAA", "BBB", "CCC"],
        {
            "AAA": {"conviction_score": 5, "stance": "buy"},
            "BBB": {"conviction_score": 3, "stance": "hold"},
        },
        {"AAA": {"conviction_delta": 1.0}, "BBB": {"conviction_delta": -0.5}},
        2.0,
    )
    expected_leg = golden["effective_inputs"]["analyst_debate_blend"]
    assert {k: round(v, 4) for k, v in leg_conv.items()} == expected_leg["convictions"]
    assert leg_st == expected_leg["stances"]


def test_incumbent_default_caps_final_book_matches_golden_fixture() -> None:
    """Representative H8 end-state under default ``SizingCaps`` stays golden."""
    from digiquant.olympus.hermes.sizing import TickerRisk, size_portfolio

    from tests.dq.hermes.incumbent_risk_fixtures import (
        assert_book_matches_golden,
        load_incumbent_risk_fixture,
        sizing_result_snapshot,
    )

    golden = load_incumbent_risk_fixture()["representative_books"]["default_caps_equity_bond"]
    result = size_portfolio(
        convictions={"SPY": 4.0, "TLT": 4.0},
        stances={"SPY": "buy", "TLT": "buy"},
        risk={
            "SPY": TickerRisk("SPY", hist_vol_21=20.0, sector="broad", asset_class="EQUITY"),
            "TLT": TickerRisk("TLT", hist_vol_21=8.0, sector="bonds", asset_class="FIXED_INCOME"),
        },
    )
    assert_book_matches_golden(sizing_result_snapshot(result), golden)


def test_h8_attaches_risk_snapshots_without_changing_book() -> None:
    """WP6.3 (#2698): resolver runs before sizing; incumbent weights unchanged."""
    from digiquant.olympus.hermes.models.risk_policy import PolicyArtifactStatus

    client = FakeSupabaseClient(
        canned_reads={"price_technicals": _tech_rows({"SPY": 15, "TLT": 15})}
    )
    state = _state(
        [{"ticker": "SPY", "target_pct": 50}, {"ticker": "TLT", "target_pct": 50}],
        analysts={
            "SPY": {"conviction_score": 5, "stance": "buy"},
            "TLT": {"conviction_score": 5, "stance": "buy"},
        },
    )
    baseline = _weights(_run(state, client))
    out = build_risk_sizing_node(RiskSizingDeps(client=client))(state)
    hermes = out["phase_hermes"]
    assert hermes.risk_policy is not None
    assert hermes.covariance_snapshot is not None
    assert hermes.risk_policy["status"] in (
        PolicyArtifactStatus.AVAILABLE.value,
        PolicyArtifactStatus.DEGRADED.value,
        PolicyArtifactStatus.UNAVAILABLE.value,
    )
    assert _weights(hermes.sized_book) == baseline
