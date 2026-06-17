"""Tests for the Hyperdash on-chain cohort-positioning provider (#801).

The fixture mirrors the REAL ``data.analytics.cohortSummary`` GraphQL shape (pnlCohorts with
top-level long/short + topMarkets), so the pure ``cohort_summary_to_positioning`` parser +
divergence calculator is validated against production field names with NO network. The scraper
itself is exercised with an injected fake session (still no network).
"""

from __future__ import annotations

from typing import Any  # noqa  # scored-lint: heterogeneous GraphQL fixture / JSON dicts

import polars as pl
import pytest

from digiquant.data.onchain.hyperdash import (
    CohortPositioning,
    HyperdashScraper,
    cohort_summary_to_positioning,
    get_onchain_cohort_positioning,
)

pytestmark = pytest.mark.unit


def _cohort_summary() -> dict[str, Any]:
    """Captured-shape cohortSummary: extremely-profitable net SHORT ETH while rekt piles LONG
    ETH (the live-validated divergence), and the mirror image on BTC. Mid cohorts carry no
    notional so the math is driven by the tails."""
    zero_mid = lambda cid: {  # noqa: E731 — terse fixture helper
        "id": cid,
        "longNotional": 0,
        "shortNotional": 0,
        "topMarkets": [],
    }
    return {
        "timestamp": "2026-06-17T00:00:00Z",
        "totalTraders": 12_345,
        "pnlCohorts": [
            {
                "id": "extremely_profitable",
                "label": "Extremely Profitable",
                "emoji": "👑",
                "range": "+$1M",
                "totalTraders": 100,
                "longNotional": 1_000_000,
                "shortNotional": 4_000_000,
                "topMarkets": [
                    {"ticker": "ETH", "longNotional": 100_000, "shortNotional": 900_000},
                    {"ticker": "BTC", "longNotional": 800_000, "shortNotional": 200_000},
                ],
            },
            zero_mid("very_profitable"),
            zero_mid("profitable"),
            zero_mid("unprofitable"),
            zero_mid("very_unprofitable"),
            {
                "id": "rekt",
                "label": "Rekt",
                "emoji": "💀",
                "range": "-$1M",
                "totalTraders": 200,
                "longNotional": 5_000_000,
                "shortNotional": 1_000_000,
                "topMarkets": [
                    {"ticker": "ETH", "longNotional": 900_000, "shortNotional": 100_000},
                    {"ticker": "BTC", "longNotional": 300_000, "shortNotional": 700_000},
                ],
            },
        ],
    }


class _FakeResp:
    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    def raise_for_status(self) -> None:  # noqa: D401
        return None

    def json(self) -> dict[str, Any]:
        return self._body


class _FakeSession:
    """Minimal requests-like session for the scraper (no network)."""

    def __init__(self, *, body: dict[str, Any] | None = None, exc: Exception | None = None) -> None:
        self._body = body
        self._exc = exc
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def post(self, url: str, **kwargs: Any) -> _FakeResp:
        self.calls.append((url, kwargs))
        if self._exc is not None:
            raise self._exc
        return _FakeResp(self._body or {})


def _eth(pos: CohortPositioning) -> dict[str, Any]:
    return pos.market_divergence.filter(pl.col("market") == "ETH").to_dicts()[0]


class TestDivergenceParser:
    def test_parses_real_shape_and_computes_divergence(self) -> None:
        pos = cohort_summary_to_positioning(_cohort_summary())
        assert pos.error is None
        assert pos.has_data
        assert pos.snapshot_ts == "2026-06-17T00:00:00Z"
        assert pos.total_traders == 12_345

        eth = _eth(pos)
        # smart 100k/900k → bias 0.1; crowd 900k/100k → bias 0.9; divergence -0.8 (distribution).
        assert eth["smart_bias"] == pytest.approx(0.1)
        assert eth["crowd_bias"] == pytest.approx(0.9)
        assert eth["divergence"] == pytest.approx(-0.8)

        by_market = {r["market"]: r for r in pos.market_divergence.to_dicts()}
        # BTC: smart 800k/200k → 0.8; crowd 300k/700k → 0.3; divergence +0.5 (smart-money confirm).
        assert by_market["BTC"]["divergence"] == pytest.approx(0.5)

    def test_overall_aggregate_bias(self) -> None:
        pos = cohort_summary_to_positioning(_cohort_summary())
        # smart agg 1M/4M → 0.2; crowd agg 5M/1M → 0.8333; overall divergence ≈ -0.6333.
        assert pos.overall["smart_net_bias"] == pytest.approx(0.2)
        assert pos.overall["crowd_net_bias"] == pytest.approx(5 / 6)
        assert pos.overall["overall_divergence"] == pytest.approx(0.2 - 5 / 6)

    def test_top_divergent_markets_sorted_by_magnitude(self) -> None:
        top = cohort_summary_to_positioning(_cohort_summary()).top_divergent_markets()
        assert [m["market"] for m in top] == ["ETH", "BTC"]  # |−0.8| > |+0.5|
        assert top[0]["divergence"] == pytest.approx(-0.8)

    def test_compact_summary_shape(self) -> None:
        compact = cohort_summary_to_positioning(_cohort_summary()).compact_summary()
        assert compact["source"] == "hyperdash"
        assert compact["total_traders"] == 12_345
        assert compact["overall_divergence"] == pytest.approx(0.2 - 5 / 6, abs=1e-4)
        assert compact["top_divergent_markets"][0]["market"] == "ETH"

    def test_to_rows_for_persistence(self) -> None:
        rows = cohort_summary_to_positioning(_cohort_summary()).to_rows("2026-06-17")
        by_market = {r["market"]: r for r in rows}
        assert set(by_market) == {"ETH", "BTC"}
        assert by_market["ETH"]["date"] == "2026-06-17"
        assert by_market["ETH"]["divergence"] == pytest.approx(-0.8)
        assert by_market["ETH"]["total_traders"] == 12_345
        assert by_market["ETH"]["snapshot_ts"] == "2026-06-17T00:00:00Z"

    def test_unknown_cohorts_ignored(self) -> None:
        summary = {
            "timestamp": "t",
            "totalTraders": 1,
            "pnlCohorts": [
                {"id": "mystery_cohort", "topMarkets": [{"ticker": "X", "longNotional": 9}]},
            ],
        }
        pos = cohort_summary_to_positioning(summary)
        assert not pos.has_data  # the only cohort was unclassifiable → no signal

    def test_empty_and_malformed_are_safe(self) -> None:
        assert cohort_summary_to_positioning({}).has_data is False
        assert cohort_summary_to_positioning({"pnlCohorts": "nope"}).error is None
        assert cohort_summary_to_positioning({"pnlCohorts": []}).has_data is False


class TestDivergenceMonotonicity:
    @staticmethod
    def _eth_only(
        smart_long: float, smart_short: float, crowd_long: float, crowd_short: float
    ) -> dict:
        return {
            "timestamp": "t",
            "totalTraders": 1,
            "pnlCohorts": [
                {
                    "id": "extremely_profitable",
                    "longNotional": 0,
                    "shortNotional": 0,
                    "topMarkets": [
                        {"ticker": "ETH", "longNotional": smart_long, "shortNotional": smart_short}
                    ],
                },
                {
                    "id": "rekt",
                    "longNotional": 0,
                    "shortNotional": 0,
                    "topMarkets": [
                        {"ticker": "ETH", "longNotional": crowd_long, "shortNotional": crowd_short}
                    ],
                },
            ],
        }

    def test_bounds_and_zero(self) -> None:
        # Smart fully long, crowd fully short → +1 (max). Reversed → -1. Identical → 0.
        hi = _eth(cohort_summary_to_positioning(self._eth_only(100, 0, 0, 100)))["divergence"]
        lo = _eth(cohort_summary_to_positioning(self._eth_only(0, 100, 100, 0)))["divergence"]
        flat = _eth(cohort_summary_to_positioning(self._eth_only(50, 50, 50, 50)))["divergence"]
        assert hi == pytest.approx(1.0)
        assert lo == pytest.approx(-1.0)
        assert flat == pytest.approx(0.0)

    def test_strictly_increasing_in_smart_long(self) -> None:
        # Crowd fixed (fully short → crowd_bias 0). As smart leans more long, divergence rises.
        divs = [
            _eth(cohort_summary_to_positioning(self._eth_only(sl, 100 - sl, 0, 100)))["divergence"]
            for sl in (10, 50, 90)
        ]
        assert divs[0] < divs[1] < divs[2]

    def test_divergence_null_when_one_side_absent(self) -> None:
        # A market only the smart cohort touches → crowd_bias null → divergence null (no pair).
        pos = cohort_summary_to_positioning(self._eth_only(80, 20, 0, 0))
        eth = _eth(pos)
        assert eth["smart_bias"] == pytest.approx(0.8)
        assert eth["crowd_bias"] is None
        assert eth["divergence"] is None
        assert pos.has_data is False  # no complete (smart, crowd) pair


class TestHyperdashScraper:
    def test_fetch_parses_full_graphql_body(self) -> None:
        body = {"data": {"analytics": {"cohortSummary": _cohort_summary()}}}
        session = _FakeSession(body=body)
        pos = HyperdashScraper(session=session).fetch()
        assert pos.error is None and pos.has_data
        assert _eth(pos)["divergence"] == pytest.approx(-0.8)
        # The query went to the GraphQL endpoint with a polite UA.
        url, kwargs = session.calls[0]
        assert url.endswith("/graphql")
        assert "User-Agent" in kwargs["headers"]

    def test_fetch_fail_soft_on_network_error(self) -> None:
        session = _FakeSession(exc=ConnectionError("boom"))
        pos = HyperdashScraper(session=session).fetch()
        assert pos.error is not None
        assert pos.has_data is False
        assert pos.compact_summary()["overall_divergence"] is None

    def test_fetch_fail_soft_on_graphql_errors(self) -> None:
        session = _FakeSession(body={"errors": [{"message": "bad query"}], "data": None})
        pos = HyperdashScraper(session=session).fetch()
        assert pos.error == "graphql_errors"
        assert pos.has_data is False

    def test_get_onchain_uses_injected_provider(self) -> None:
        class _FakeProvider:
            def fetch(self) -> CohortPositioning:
                return cohort_summary_to_positioning(_cohort_summary())

        pos = get_onchain_cohort_positioning(provider=_FakeProvider())
        assert pos.has_data
        assert pos.total_traders == 12_345

    def test_default_path_disabled_makes_no_network_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Kill-switch off (the default) → no provider construction, no network: empty result.
        monkeypatch.delenv("ATLAS_ONCHAIN_POSITIONING", raising=False)

        def _boom(*_a: Any, **_k: Any) -> Any:
            raise AssertionError("must not construct a live scraper when the switch is off")

        monkeypatch.setattr("digiquant.data.onchain.hyperdash.HyperdashScraper", _boom)
        pos = get_onchain_cohort_positioning()
        assert pos.has_data is False and pos.error is None

    def test_default_path_enabled_runs_scraper(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Switch on → the default HyperdashScraper runs (here with an injected fake session).
        monkeypatch.setenv("ATLAS_ONCHAIN_POSITIONING", "1")
        body = {"data": {"analytics": {"cohortSummary": _cohort_summary()}}}
        monkeypatch.setattr(
            "digiquant.data.onchain.hyperdash.HyperdashScraper",
            lambda: HyperdashScraper(session=_FakeSession(body=body)),
        )
        pos = get_onchain_cohort_positioning()
        assert pos.has_data and pos.total_traders == 12_345
