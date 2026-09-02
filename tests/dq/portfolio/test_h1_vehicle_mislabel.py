"""H1 must not mint vehicle-shaped theses into the market register.

House rows on 2026-08-31 / 2026-09-01 used thesis_id ``veicle-{EWG,GLD,XLB}``
(missing the 'h' in vehicle), ``thesis_kind`` null, and price-technicals notes.
``persist_thesis_review`` upserted whatever the LLM emitted, so those ghosts
landed in the dashboard thesis list as market views 26–28.
"""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.portfolio.models.thesis import ThesisReviewOutput, ThesisStatusUpdate
from digiquant.portfolio.writers.thesis_io import (
    persist_thesis_review,
    vehicle_shaped_ticker,
)

from tests.dq.research.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

_RUN = date(2026, 9, 1)


def _review(*ids: str) -> ThesisReviewOutput:
    return ThesisReviewOutput(
        reviewed_theses=[
            ThesisStatusUpdate(
                thesis_id=thesis_id,
                prior_status="ACTIVE",
                new_status="ACTIVE",
                evidence=[f"price_technicals:{thesis_id.split('-')[-1].upper()} ADX 26.9"],
            )
            for thesis_id in ids
        ]
    )


def test_vehicle_shaped_ticker_matches_vehicle_and_veicle() -> None:
    assert vehicle_shaped_ticker("vehicle-ewg") == "ewg"
    assert vehicle_shaped_ticker("veicle-GLD") == "gld"
    assert vehicle_shaped_ticker("VEHICLE-XLB") == "xlb"
    assert vehicle_shaped_ticker("gold-silver-structural-rally") is None
    assert vehicle_shaped_ticker("ewg") is None


def test_persist_thesis_review_does_not_mint_veicle_typo_ids() -> None:
    client = FakeSupabaseClient()
    count = persist_thesis_review(
        client,  # type: ignore[arg-type]
        run_date=_RUN,
        review=_review("veicle-ewg", "veicle-gld", "veicle-xlb"),
        active_theses=[
            {
                "thesis_id": "gold-silver-structural-rally",
                "name": "Gold rally",
                "status": "ACTIVE",
                "thesis_kind": "market",
            }
        ],
    )

    assert count == 0
    assert client.store.get("theses", []) == []


def test_persist_thesis_review_does_not_carry_existing_veicle_ghosts() -> None:
    client = FakeSupabaseClient()
    count = persist_thesis_review(
        client,  # type: ignore[arg-type]
        run_date=_RUN,
        review=_review("veicle-ewg"),
        active_theses=[
            {
                "thesis_id": "veicle-ewg",
                "name": "veicle-ewg",
                "status": "CHALLENGED",
                "thesis_kind": None,
            },
            {
                "thesis_id": "vehicle-ewg",
                "name": "EWG vehicle thesis",
                "status": "ACTIVE",
                "thesis_kind": "vehicle",
                "vehicle": "EWG",
            },
        ],
    )

    written_ids = [row["thesis_id"] for row in client.store.get("theses", [])]
    assert "veicle-ewg" not in written_ids
    assert count == 0


def test_persist_thesis_review_skips_canonical_vehicle_ids() -> None:
    client = FakeSupabaseClient()
    count = persist_thesis_review(
        client,  # type: ignore[arg-type]
        run_date=_RUN,
        review=_review("vehicle-gld"),
        active_theses=[
            {
                "thesis_id": "vehicle-gld",
                "name": "GLD vehicle thesis",
                "status": "ACTIVE",
                "thesis_kind": "vehicle",
                "vehicle": "GLD",
            }
        ],
    )

    assert count == 0
    assert client.store.get("theses", []) == []


def test_persist_thesis_review_still_writes_known_market_theses() -> None:
    client = FakeSupabaseClient()
    count = persist_thesis_review(
        client,  # type: ignore[arg-type]
        run_date=_RUN,
        review=ThesisReviewOutput(
            reviewed_theses=[
                ThesisStatusUpdate(
                    thesis_id="gold-silver-structural-rally",
                    prior_status="ACTIVE",
                    new_status="CHALLENGED",
                    evidence=["DXY reclaimed 121"],
                )
            ]
        ),
        active_theses=[
            {
                "thesis_id": "gold-silver-structural-rally",
                "name": "Gold rally",
                "status": "ACTIVE",
                "thesis_kind": "market",
            }
        ],
    )

    assert count == 1
    row = client.store["theses"][0]
    assert row["thesis_id"] == "gold-silver-structural-rally"
    assert row["status"] == "CHALLENGED"
    assert row["thesis_kind"] == "market"


def test_persist_thesis_review_does_not_mint_unknown_market_ids() -> None:
    client = FakeSupabaseClient()
    count = persist_thesis_review(
        client,  # type: ignore[arg-type]
        run_date=_RUN,
        review=_review("invented-ticker-view"),
        active_theses=[
            {
                "thesis_id": "gold-silver-structural-rally",
                "name": "Gold rally",
                "status": "ACTIVE",
                "thesis_kind": "market",
            }
        ],
    )

    assert count == 0
    assert client.store.get("theses", []) == []
