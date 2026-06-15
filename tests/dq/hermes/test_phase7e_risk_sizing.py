"""Phase 7E — deterministic risk-sizing enforcement (#726, Pillar 2).

The node replaces the PM's eyeballed candidate book with sized, capped, reduce-only
weights and rebuilds the advisory action list, reading per-ticker vol from
``price_technicals`` (look-ahead-guarded) and sector buckets from ``sector_map``. It is
fail-soft (errors keep the PM book) and a no-op when the PM never ran.
"""

from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState
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
) -> AtlasResearchState:
    state = AtlasResearchState(
        run_type="delta",
        run_date=RUN_DATE,
        baseline_date=date(2026, 6, 9),
        config=AtlasConfigBundle(preferences=preferences or {}),
    )
    state.phase7d_rebalance = {
        "recommended_portfolio": recommended,
        "actions": actions or [],
        "notes": "PM notes.",
    }
    state.phase7c_analysts = analysts or {}
    state.phase7cd_debates = debates or {}
    return state


def _tech_rows(vols: dict[str, float], on: str = "2026-06-12") -> list[dict]:
    return [{"ticker": t, "date": on, "hist_vol_21": v, "atr_pct": None} for t, v in vols.items()]


def _run(state: AtlasResearchState, client: FakeSupabaseClient | None = None) -> dict | None:
    client = client or FakeSupabaseClient()
    out = build_risk_sizing_node(RiskSizingDeps(client=client))(state)
    return out.get("phase7d_rebalance")


def _weights(rebal: dict) -> dict[str, float]:
    return {r["ticker"]: r["target_pct"] for r in rebal["recommended_portfolio"]}


# --------------------------------------------------------------------------- no-op / cash


def test_no_op_when_pm_never_ran() -> None:
    state = _state([])
    state.phase7d_rebalance = None
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
    assert w == {"SPY": pytest.approx(30.0), "TLT": pytest.approx(30.0)}


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


def test_effective_conviction_applies_debate_delta() -> None:
    # Equal analyst conviction (3); a +2 debate delta lifts A to 5 → A outweighs B ~5:3.
    rebal = _run(
        _state(
            [{"ticker": "AAA", "target_pct": 50}, {"ticker": "BBB", "target_pct": 50}],
            analysts={
                "AAA": {"conviction_score": 3, "stance": "buy"},
                "BBB": {"conviction_score": 3, "stance": "buy"},
            },
            debates={"AAA": {"conviction_delta": 2}, "BBB": {"conviction_delta": 0}},
            preferences=_RELAXED,
        ),
        FakeSupabaseClient(canned_reads={"price_technicals": _tech_rows({"AAA": 20, "BBB": 20})}),
    )
    w = _weights(rebal)
    assert w["AAA"] > w["BBB"]
    assert w["AAA"] / w["BBB"] == pytest.approx(5.0 / 3.0, rel=0.05)


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
    assert "Risk-sizing (Phase 7E)" in rebal["notes"]
    assert rebal["notes"].startswith("PM notes.")  # PM's note preserved


# --------------------------------------------------------------------------- fail-soft


def test_sizing_error_keeps_pm_book(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(**_kwargs):
        raise RuntimeError("sizer exploded")

    monkeypatch.setattr(phase7e_risk_sizing, "size_portfolio", _boom)
    state = _state(
        [{"ticker": "SPY", "target_pct": 50}],
        analysts={"SPY": {"conviction_score": 5, "stance": "buy"}},
    )
    # No update returned → the chain keeps state.phase7d_rebalance (the PM's book) intact.
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
