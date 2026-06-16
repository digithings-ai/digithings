"""Tests for Fed rate-probability parsers (Pillar / #778).

Fixtures mirror the REAL Kalshi (KXFED) + Polymarket (gamma) JSON shapes captured live, so the
pure ``*_to_rows`` parsers are validated against production field names without any network.
"""

from __future__ import annotations

from datetime import date

import pytest

from digiquant.data.prices.fed_probabilities import (
    fed_distribution_from_ladder,
    kalshi_markets_to_rows,
    polymarket_events_to_rows,
)

pytestmark = pytest.mark.unit

AS_OF = date(2026, 6, 16)


def _kalshi_markets() -> list[dict]:
    # Real KXFED shape: "upper bound > strike" threshold contracts, prices as 0-1 strings.
    base = {
        "status": "active",
        "close_time": "2027-04-28T17:55:00Z",
        "strike_type": "greater",
        "event_ticker": "KXFED-27APR",
    }
    return [
        {
            **base,
            "ticker": "KXFED-27APR-T4.25",
            "floor_strike": 4.25,
            "yes_bid_dollars": "0.1100",
            "yes_ask_dollars": "0.2900",
            "last_price_dollars": "0.2900",
        },
        {
            **base,
            "ticker": "KXFED-27APR-T4.00",
            "floor_strike": 4.0,
            "yes_bid_dollars": "0.2700",
            "yes_ask_dollars": "0.5300",
            "last_price_dollars": "0.2600",
        },
        # Bad rows that must be skipped (no strike / no close_time / no prices).
        {
            **base,
            "ticker": "X",
            "floor_strike": None,
            "yes_bid_dollars": "0.5",
            "yes_ask_dollars": "0.5",
        },
        {"ticker": "Y", "floor_strike": 3.5, "strike_type": "greater"},  # no close_time, no price
    ]


class TestKalshi:
    def test_parses_survival_ladder(self) -> None:
        rows = kalshi_markets_to_rows(_kalshi_markets(), as_of=AS_OF)
        assert len(rows) == 2  # the two well-formed strikes; bad rows dropped
        by_id = {r["series_id"]: r for r in rows}
        top = by_id["FEDPROB/2027-04-28/upper_gt_4.25"]
        assert top["source"] == "kalshi"
        assert top["value"] == pytest.approx(0.20)  # mid(0.11, 0.29)
        assert top["obs_date"] == "2026-06-16"
        assert top["unit"] == "probability"
        assert top["meta"]["strike"] == 4.25
        assert by_id["FEDPROB/2027-04-28/upper_gt_4"]["value"] == pytest.approx(
            0.40
        )  # mid(0.27,0.53)

    def test_falls_back_to_last_price_when_no_bid_ask(self) -> None:
        rows = kalshi_markets_to_rows(
            [
                {
                    "floor_strike": 3.5,
                    "close_time": "2026-06-17T18:00:00Z",
                    "last_price_dollars": "0.7",
                }
            ],
            as_of=AS_OF,
        )
        assert rows[0]["value"] == pytest.approx(0.7)

    def test_out_of_range_price_dropped(self) -> None:
        rows = kalshi_markets_to_rows(
            [
                {
                    "floor_strike": 3.5,
                    "close_time": "2026-06-17T18:00:00Z",
                    "last_price_dollars": "1.4",
                }
            ],
            as_of=AS_OF,
        )
        assert rows == []  # a price > 1 is not a valid probability


def _polymarket_events() -> list[dict]:
    # Real gamma shape: outcomes / outcomePrices are JSON-ENCODED STRINGS.
    return [
        {
            "id": "51456",
            "slug": "how-many-fed-rate-cuts-in-2026",
            "endDate": "2026-12-31T00:00:00Z",
            "markets": [
                {
                    "question": "Will no Fed rate cuts happen in 2026?",
                    "slug": "will-no-fed-rate-cuts-happen-in-2026",
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": '["0.6915", "0.3085"]',
                    "lastTradePrice": 0.691,
                    "closed": False,
                    "groupItemThreshold": "0",
                },
                {  # closed → skipped
                    "question": "old",
                    "slug": "old",
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": '["1", "0"]',
                    "closed": True,
                },
            ],
        }
    ]


class TestPolymarket:
    def test_parses_yes_probability_from_json_strings(self) -> None:
        rows = polymarket_events_to_rows(_polymarket_events(), as_of=AS_OF)
        assert len(rows) == 1  # the open market; closed one dropped
        row = rows[0]
        assert row["source"] == "polymarket"
        assert row["value"] == pytest.approx(0.6915)  # Yes price, JSON-decoded
        assert row["series_id"].startswith("FEDPROB/2026-12-31/pm/")
        assert row["obs_date"] == "2026-06-16"

    def test_empty_or_malformed_is_safe(self) -> None:
        assert polymarket_events_to_rows([], as_of=AS_OF) == []
        assert (
            polymarket_events_to_rows([{"markets": [{"outcomes": "not-json"}]}], as_of=AS_OF) == []
        )


class TestDistribution:
    def test_ladder_differences_into_normalized_pmf(self) -> None:
        ladder = {3.25: 0.97, 3.50: 0.80, 3.75: 0.60, 4.00: 0.40, 4.25: 0.20}
        out = fed_distribution_from_ladder(ladder)
        dist = out["distribution"]
        assert dist["<=3.25"] == pytest.approx(0.03)
        assert dist["3.5"] == pytest.approx(0.17)
        assert dist[">4.25"] == pytest.approx(0.20)
        assert sum(dist.values()) == pytest.approx(1.0, abs=1e-6)
        assert out["n_strikes"] == 5
        assert out["most_likely"] in dist  # a real bucket

    def test_negative_diffs_clamped_and_renormalized(self) -> None:
        # A non-monotone (noisy) ladder: surv should fall with strike, but here it rises — the
        # negative band masses clamp to 0 and the result still normalizes (no negative probs).
        out = fed_distribution_from_ladder({3.5: 0.4, 3.75: 0.6})
        assert all(v >= 0 for v in out["distribution"].values())
        assert sum(out["distribution"].values()) == pytest.approx(1.0, abs=1e-6)

    def test_too_few_strikes_returns_empty(self) -> None:
        assert fed_distribution_from_ladder({3.5: 0.5}) == {}


class TestReader:
    def test_get_fed_rate_probabilities_nearest_meeting(self) -> None:
        from digiquant.olympus.atlas.data.queries import get_fed_rate_probabilities
        from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

        client = FakeSupabaseClient(
            canned_reads={
                "macro_series_observations": [
                    {
                        "source": "kalshi",
                        "series_id": "FEDPROB/2026-06-17/upper_gt_3.75",
                        "obs_date": "2026-06-16",
                        "value": 0.6,
                        "meta": {},
                    },
                    {
                        "source": "kalshi",
                        "series_id": "FEDPROB/2026-06-17/upper_gt_4",
                        "obs_date": "2026-06-16",
                        "value": 0.4,
                        "meta": {},
                    },
                    {
                        "source": "polymarket",
                        "series_id": "FEDPROB/2026-06-17/pm/will-the-fed-hold",
                        "obs_date": "2026-06-16",
                        "value": 0.7,
                        "meta": {"question": "Will the Fed hold?"},
                    },
                ]
            }
        )
        out = get_fed_rate_probabilities(client=client, run_date=AS_OF)
        assert out["meeting_date"] == "2026-06-17"
        assert set(out["sources"]) == {"kalshi", "polymarket"}
        assert out["kalshi"]["distribution"]["4"] == pytest.approx(0.2)  # 0.6 - 0.4
        assert out["polymarket"][0]["prob"] == pytest.approx(0.7)

    def test_get_fed_rate_probabilities_empty_when_no_rows(self) -> None:
        from digiquant.olympus.atlas.data.queries import get_fed_rate_probabilities
        from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

        client = FakeSupabaseClient(canned_reads={"macro_series_observations": []})
        assert get_fed_rate_probabilities(client=client, run_date=AS_OF) == {}
