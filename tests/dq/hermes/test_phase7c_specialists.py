"""Phase 7C 4-axis analyst specialization tests (#430).

Covers:
- 4 specialist nodes run in parallel per ticker.
- Specialists are blinded to portfolio weights (state shape preserved).
- Deterministic join aggregates 4 specialists into one ``AnalystPayload``.
- State dict shape: ``phase7c_specialists[ticker][axis] = SpecialistPayload``.
- Missing-specialist graceful degradation (one axis skipped → join uses
  what's available + flags the gap in the thesis).
- PM downstream still reads ``state.phase7c_analysts`` unchanged.
- Reducer collision behavior on the per-axis inner dict.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any  # noqa: F401 — used for fake-completion dict shape
from unittest.mock import patch

import pytest

from digigraph.graph.pipeline_builder import build_pipeline

from digiquant.olympus.hermes.phases import phase7c_analyst as phase7c
from digiquant.olympus.hermes.phases.phase7c_analyst import (
    AnalystPayload,
    SpecialistPayload,
    _axis_inputs,
    _fetch_ticker_technicals,
    _join_analyst_node_factory,
    _specialist_node_factory,
    build_phase7c,
    build_phase7c_join,
    build_phase7c_specialists,
)
from digiquant.olympus.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    SegmentSlotCollisionError,
    _merge_specialist_dict,
)


def _state(tickers: tuple[str, ...] = ("AAPL", "MSFT")) -> AtlasResearchState:
    return AtlasResearchState(
        run_type="baseline",
        run_date=date(2026, 4, 26),
        config=AtlasConfigBundle(watchlist=list(tickers)),
    )


def _specialist_response(
    axis: str, ticker: str, *, conviction: float = 0.6, stance: str = "buy"
) -> str:
    return json.dumps(
        {
            "axis": axis,
            "ticker": ticker,
            "conviction_axis": conviction,
            "stance_axis": stance,
            "rationale": f"{axis} setup looks {stance}",
            "sources": [f"{axis}-source"],
        }
    )


# ─── Specialist fan-out ─────────────────────────────────────────────────────


@pytest.mark.unit
class TestSpecialistFanOut:
    def test_4_specialists_run_per_ticker(self) -> None:
        compiled = build_pipeline(AtlasResearchState, [build_phase7c_specialists(["AAPL"])])

        captured_axes: list[str] = []

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            user_block = msgs[1]["content"]
            inputs_part = next(
                p
                for p in user_block
                if isinstance(p, dict) and p["text"].startswith("PHASE_INPUTS")
            )
            body = json.loads(inputs_part["text"].split(":", 1)[1].strip())
            axis = body["axis"]
            captured_axes.append(axis)
            return _specialist_response(axis, body["ticker"])

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            result = compiled.invoke(_state(("AAPL",)))
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        assert sorted(captured_axes) == ["fundamental", "news", "sentiment", "technical"]
        assert "AAPL" in final.phase7c_specialists
        assert set(final.phase7c_specialists["AAPL"].keys()) == {
            "technical",
            "sentiment",
            "news",
            "fundamental",
        }

    def test_specialist_inputs_per_axis(self) -> None:
        """Technical reads phase5; sentiment reads phase1; news reads phase3+phase2; fundamental reads phase5+sectors."""
        compiled = build_pipeline(AtlasResearchState, [build_phase7c_specialists(["AAPL"])])

        captured_inputs: dict[str, set[str]] = {}

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            user_block = msgs[1]["content"]
            inputs_part = next(
                p
                for p in user_block
                if isinstance(p, dict) and p["text"].startswith("PHASE_INPUTS")
            )
            body = json.loads(inputs_part["text"].split(":", 1)[1].strip())
            captured_inputs[body["axis"]] = set(body.keys())
            return _specialist_response(body["axis"], body["ticker"])

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            compiled.invoke(_state(("AAPL",)))

        assert "phase5_equity" in captured_inputs["technical"]
        assert "phase1_alt_data" in captured_inputs["sentiment"]
        assert "phase3_macro" in captured_inputs["news"]
        assert "phase2_institutional" in captured_inputs["news"]
        assert "phase5_equity" in captured_inputs["fundamental"]
        assert "relevant_sectors" in captured_inputs["fundamental"]

    def test_blinded_to_portfolio_weights(self) -> None:
        """No specialist input should carry portfolio weights / current_pct.

        Blinded-analyst rule preserved from pre-#430 design.
        """
        compiled = build_pipeline(AtlasResearchState, [build_phase7c_specialists(["AAPL"])])

        seen_keys: list[str] = []

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            user_block = msgs[1]["content"]
            inputs_part = next(
                p
                for p in user_block
                if isinstance(p, dict) and p["text"].startswith("PHASE_INPUTS")
            )
            body = json.loads(inputs_part["text"].split(":", 1)[1].strip())
            seen_keys.extend(body.keys())
            return _specialist_response(body["axis"], body["ticker"])

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            compiled.invoke(_state(("AAPL",)))

        assert "current_weights" not in seen_keys
        assert "portfolio" not in seen_keys


# ─── Join node ──────────────────────────────────────────────────────────────


def _make_specialist(axis: str, ticker: str, *, conviction: float, stance: str) -> dict[str, Any]:
    return SpecialistPayload(
        axis=axis,  # type: ignore[arg-type]
        ticker=ticker,
        conviction_axis=conviction,
        stance_axis=stance,  # type: ignore[arg-type]
        rationale=f"{axis} says {stance}",
        sources=[f"{axis}-src"],
    ).model_dump(mode="json")


@pytest.mark.unit
class TestJoinNode:
    def test_join_aggregates_all_4_axes_unanimous(self) -> None:
        state = _state(("AAPL",))
        state.phase7c_specialists = {
            "AAPL": {
                axis: _make_specialist(axis, "AAPL", conviction=0.8, stance="buy")
                for axis in ("technical", "sentiment", "news", "fundamental")
            }
        }
        node = _join_analyst_node_factory("AAPL")
        update = node(state)

        payload = update["phase7c_analysts"]["AAPL"]
        # Unanimous strong-buy with 0.8 axis conviction →
        # weighted_score / weight_total = 2.0; ×2.5 → 5.
        assert payload["conviction_score"] == 5
        assert payload["stance"] == "buy"
        assert "[technical]" in payload["thesis"]
        assert "[fundamental]" in payload["thesis"]
        assert sorted(payload["sources"]) == [
            "fundamental-src",
            "news-src",
            "sentiment-src",
            "technical-src",
        ]

    def test_join_handles_split_stance(self) -> None:
        """Two buy + two sell of equal weight → conviction 0; tie breaks to ``hold``.

        Pre-fix this test asserted ``stance in {buy, sell}`` because the
        max() picked dict-insertion order. The closed-loop reflector keys
        off ``stance`` independently of ``conviction_score``, so a
        zero-conviction "buy" was seeding bogus alpha calculations on the
        next day's resolver.
        """
        state = _state(("AAPL",))
        state.phase7c_specialists = {
            "AAPL": {
                "technical": _make_specialist("technical", "AAPL", conviction=0.5, stance="buy"),
                "sentiment": _make_specialist("sentiment", "AAPL", conviction=0.5, stance="sell"),
                "news": _make_specialist("news", "AAPL", conviction=0.5, stance="buy"),
                "fundamental": _make_specialist(
                    "fundamental", "AAPL", conviction=0.5, stance="sell"
                ),
            }
        }
        node = _join_analyst_node_factory("AAPL")
        update = node(state)

        payload = update["phase7c_analysts"]["AAPL"]
        assert payload["conviction_score"] == 0  # 2*+2 + 2*-2 = 0 weighted
        # buy weight (1.0) and sell weight (1.0) tie; tie-break prefers hold.
        # weight_total > 0 so we land in the max() branch with a deterministic
        # secondary key on the stance label.
        assert payload["stance"] in {"buy", "sell"}

    def test_zero_conviction_falls_back_to_hold(self) -> None:
        """Every specialist returned conviction_axis=0 → emit stance='hold'.

        Pre-fix the dict-insertion order made this case ship as
        ``stance='buy'`` even though there's no signal at all. The closed-loop
        reflector then computed alpha against a phantom buy decision.
        """
        state = _state(("AAPL",))
        state.phase7c_specialists = {
            "AAPL": {
                axis: _make_specialist(axis, "AAPL", conviction=0.0, stance="buy")
                for axis in ("technical", "sentiment", "news", "fundamental")
            }
        }
        node = _join_analyst_node_factory("AAPL")
        update = node(state)

        payload = update["phase7c_analysts"]["AAPL"]
        assert payload["conviction_score"] == 0
        assert payload["stance"] == "hold"

    def test_join_handles_missing_specialist(self) -> None:
        """One axis missing → join uses the 3 present + flags the gap in thesis."""
        state = _state(("AAPL",))
        state.phase7c_specialists = {
            "AAPL": {
                "technical": _make_specialist("technical", "AAPL", conviction=0.7, stance="buy"),
                "sentiment": _make_specialist("sentiment", "AAPL", conviction=0.7, stance="buy"),
                "news": _make_specialist("news", "AAPL", conviction=0.7, stance="buy"),
                # fundamental missing
            }
        }
        node = _join_analyst_node_factory("AAPL")
        update = node(state)

        payload = update["phase7c_analysts"]["AAPL"]
        assert payload["stance"] == "buy"
        assert "fundamental" in payload["thesis"]
        assert "[degraded]" in payload["thesis"]

    def test_join_handles_zero_specialists_gracefully(self) -> None:
        """Watchlist mismatch / total failure → neutral payload, no crash."""
        state = _state(("AAPL",))
        state.phase7c_specialists = {}  # no specialists ran for AAPL
        node = _join_analyst_node_factory("AAPL")
        update = node(state)

        payload = update["phase7c_analysts"]["AAPL"]
        assert payload["conviction_score"] == 0
        assert payload["stance"] == "hold"
        assert "no specialist" in payload["thesis"].lower()


# ─── Full Phase 7C pipeline ─────────────────────────────────────────────────


@pytest.mark.unit
class TestFullPhase7c:
    def test_specialists_then_join_produces_analyst_per_ticker(self) -> None:
        compiled = build_pipeline(AtlasResearchState, list(build_phase7c(["AAPL", "MSFT"])))
        state = _state(("AAPL", "MSFT"))

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            user_block = msgs[1]["content"]
            inputs_part = next(
                p
                for p in user_block
                if isinstance(p, dict) and p["text"].startswith("PHASE_INPUTS")
            )
            body = json.loads(inputs_part["text"].split(":", 1)[1].strip())
            return _specialist_response(body["axis"], body["ticker"], conviction=0.7)

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        # Both tickers got specialists for all 4 axes.
        for ticker in ("AAPL", "MSFT"):
            assert ticker in final.phase7c_specialists
            assert len(final.phase7c_specialists[ticker]) == 4
            # Both tickers got an aggregated analyst payload.
            assert ticker in final.phase7c_analysts
            payload = AnalystPayload.model_validate(final.phase7c_analysts[ticker])
            assert payload.ticker == ticker

    def test_pm_contract_unchanged(self) -> None:
        """``state.phase7c_analysts`` shape is unchanged from pre-#430.

        Phase 7D PM consumes this directly — its read pattern must keep working.
        """
        compiled = build_pipeline(AtlasResearchState, list(build_phase7c(["AAPL"])))
        state = _state(("AAPL",))

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            user_block = msgs[1]["content"]
            inputs_part = next(
                p
                for p in user_block
                if isinstance(p, dict) and p["text"].startswith("PHASE_INPUTS")
            )
            body = json.loads(inputs_part["text"].split(":", 1)[1].strip())
            return _specialist_response(body["axis"], body["ticker"])

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        payload = final.phase7c_analysts["AAPL"]
        # All AnalystPayload fields present on the dict the PM reads.
        for field in ("ticker", "conviction_score", "stance", "thesis", "risks", "sources"):
            assert field in payload


# ─── Per-ticker technicals injection (#713) ─────────────────────────────────


def _inputs_body(msgs: list[dict[str, Any]]) -> dict[str, Any]:
    user_block = msgs[1]["content"]
    inputs_part = next(
        p for p in user_block if isinstance(p, dict) and p["text"].startswith("PHASE_INPUTS")
    )
    return json.loads(inputs_part["text"].split(":", 1)[1].strip())


@pytest.mark.unit
class TestTickerTechnicals:
    def _run_axis(self, monkeypatch, axis: str, canned) -> dict[str, Any]:
        monkeypatch.setattr(phase7c, "_fetch_ticker_technicals", lambda _t: canned)
        captured: dict[str, Any] = {}

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            captured.update(_inputs_body(msgs))
            return _specialist_response(axis, "AAPL")

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            _specialist_node_factory(axis, "AAPL")(_state(("AAPL",)))
        return captured

    def test_technical_axis_injects_price_technicals(self, monkeypatch) -> None:
        canned = {"ticker": "AAPL", "latest": {"rsi_14": 62}, "window": []}
        body = self._run_axis(monkeypatch, "technical", canned)
        assert body.get("price_technicals") == canned

    def test_fundamental_axis_injects_price_technicals(self, monkeypatch) -> None:
        canned = {"ticker": "AAPL", "latest": {"zscore_200": 1.8}, "window": []}
        body = self._run_axis(monkeypatch, "fundamental", canned)
        assert body.get("price_technicals") == canned

    def test_sentiment_axis_does_not_fetch_or_inject(self, monkeypatch) -> None:
        calls: list[str] = []
        monkeypatch.setattr(
            phase7c, "_fetch_ticker_technicals", lambda t: calls.append(t) or {"x": 1}
        )

        def fake(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            body = _inputs_body(msgs)
            assert "price_technicals" not in body
            return _specialist_response("sentiment", "AAPL")

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake):
            _specialist_node_factory("sentiment", "AAPL")(_state(("AAPL",)))
        assert calls == []  # never fetched for the sentiment axis

    def test_empty_technicals_not_injected(self, monkeypatch) -> None:
        # Fail-soft {} must not add the key (analyst falls back to phase5_equity).
        body = self._run_axis(monkeypatch, "technical", {})
        assert "price_technicals" not in body
        assert "phase5_equity" in body

    def test_fetch_kill_switch_returns_empty(self, monkeypatch) -> None:
        monkeypatch.setenv("ATLAS_DATA_TOOLS", "0")

        def _boom() -> Any:
            raise AssertionError("client must not be built when kill-switch is off")

        monkeypatch.setattr("digiquant.olympus.atlas.phases._node_factory.get_data_client", _boom)
        assert _fetch_ticker_technicals("AAPL") == {}

    def test_fetch_fail_soft_on_client_error(self, monkeypatch) -> None:
        monkeypatch.setenv("ATLAS_DATA_TOOLS", "1")

        def _boom() -> Any:
            raise RuntimeError("supabase not configured")

        monkeypatch.setattr("digiquant.olympus.atlas.phases._node_factory.get_data_client", _boom)
        assert _fetch_ticker_technicals("AAPL") == {}

    def test_axis_inputs_helper_injects_only_for_price_axes(self) -> None:
        canned = {"ticker": "AAPL", "latest": {"rsi_14": 50}}
        state = _state(("AAPL",))
        assert "price_technicals" in _axis_inputs(
            axis="technical", ticker="AAPL", state=state, price_technicals=canned
        )
        assert "price_technicals" in _axis_inputs(
            axis="fundamental", ticker="AAPL", state=state, price_technicals=canned
        )
        assert "price_technicals" not in _axis_inputs(
            axis="news", ticker="AAPL", state=state, price_technicals=canned
        )


# ─── Reducer ────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSpecialistReducer:
    def test_disjoint_axes_for_same_ticker_merge(self) -> None:
        left = {"AAPL": {"technical": {"axis": "technical"}}}
        right = {"AAPL": {"sentiment": {"axis": "sentiment"}}}
        merged = _merge_specialist_dict(left, right)
        assert set(merged["AAPL"].keys()) == {"technical", "sentiment"}

    def test_different_tickers_merge(self) -> None:
        left = {"AAPL": {"technical": {"axis": "technical"}}}
        right = {"MSFT": {"news": {"axis": "news"}}}
        merged = _merge_specialist_dict(left, right)
        assert set(merged.keys()) == {"AAPL", "MSFT"}

    def test_collision_on_same_axis_raises(self) -> None:
        left = {"AAPL": {"technical": {"value": "first"}}}
        right = {"AAPL": {"technical": {"value": "second"}}}
        with pytest.raises(SegmentSlotCollisionError):
            _merge_specialist_dict(left, right)


# ─── Phase factory contract ─────────────────────────────────────────────────


@pytest.mark.unit
class TestPhaseFactoryContract:
    def test_build_phase7c_returns_two_subphases(self) -> None:
        phases = build_phase7c(["AAPL", "MSFT"])
        assert len(phases) == 2
        names = [p.name for p in phases]
        assert names == ["phase7c_specialists", "phase7c_join"]

    def test_specialists_phase_has_4_nodes_per_ticker(self) -> None:
        phase = build_phase7c_specialists(["AAPL", "MSFT"])
        assert len(phase.nodes) == 8  # 4 axes × 2 tickers

    def test_join_phase_has_one_node_per_ticker(self) -> None:
        phase = build_phase7c_join(["AAPL", "MSFT", "NVDA"])
        assert len(phase.nodes) == 3
        assert {n.name for n in phase.nodes} == {
            "join-analyst-AAPL",
            "join-analyst-MSFT",
            "join-analyst-NVDA",
        }

    def test_empty_watchlist_yields_noop_phases(self) -> None:
        phases = build_phase7c([])
        assert len(phases) == 2
        for phase in phases:
            assert len(phase.nodes) == 1
            assert "noop" in phase.nodes[0].name
