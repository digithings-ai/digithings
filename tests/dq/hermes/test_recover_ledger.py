"""Recover H9 ledger commit from an already-booked positions row (#3330)."""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.olympus.hermes.writers.ledger_io import COMMITS
from digiquant.olympus.hermes.writers.recover_ledger import recover_ledger_from_book
from digiquant.olympus.tenancy import house_workspace_id

from tests.fixtures.fake_supabase import FakeSupabaseClient

pytestmark = pytest.mark.unit

RUN_DATE = date(2026, 8, 31)
PRIOR_DATE = date(2026, 8, 28)
HOUSE = str(house_workspace_id())


def _pos(day: date, ticker: str, weight: float) -> dict:
    return {
        "date": day.isoformat(),
        "ticker": ticker,
        "weight_pct": weight,
        "workspace_id": HOUSE,
    }


def _seed_booked_day(client: FakeSupabaseClient) -> None:
    """Monday book matching the 2026-08-31 house positions (already decided)."""
    client.canned_reads["positions"] = [
        _pos(PRIOR_DATE, "CASH", 25.2189),
        _pos(PRIOR_DATE, "EWZ", 5.1046),
        _pos(PRIOR_DATE, "FXI", 9.8561),
        _pos(PRIOR_DATE, "GLD", 10.0),
        _pos(PRIOR_DATE, "VGK", 20.0429),
        _pos(PRIOR_DATE, "XLF", 14.9609),
        _pos(PRIOR_DATE, "XLV", 14.8166),
        _pos(RUN_DATE, "CASH", 20.663),
        _pos(RUN_DATE, "EWZ", 5.0771),
        _pos(RUN_DATE, "FXI", 5.0),
        _pos(RUN_DATE, "GLD", 9.4215),
        _pos(RUN_DATE, "VGK", 25.0),
        _pos(RUN_DATE, "XLF", 20.0),
        _pos(RUN_DATE, "XLV", 14.8384),
    ]
    client.canned_reads["nav_history"] = [
        {
            "date": RUN_DATE.isoformat(),
            "nav": 99.956707,
            "cash_pct": 20.663,
            "workspace_id": HOUSE,
        }
    ]
    client.canned_reads["price_history"] = [
        {"date": "2026-08-28", "ticker": t, "close": 50.0}
        for t in ("EWZ", "FXI", "GLD", "VGK", "XLF", "XLV")
    ]
    client.canned_reads["decision_log"] = [{"run_date": RUN_DATE.isoformat(), "ticker": "VGK"}]
    client.canned_reads[COMMITS] = []
    client.canned_reads["documents"] = []


class TestRecoverLedgerFromBook:
    def test_dry_run_does_not_insert(self) -> None:
        client = FakeSupabaseClient()
        _seed_booked_day(client)
        result = recover_ledger_from_book(client=client, run_date=RUN_DATE, apply=False)
        assert result.status == "dry_run"
        assert result.weights["VGK"] == 25.0
        assert result.weights["FXI"] == 5.0
        assert result.cash_pct == 20.663
        assert result.nav == pytest.approx(99.956707)
        assert client.store.get(COMMITS, []) == []
        assert client.store.get("documents", []) == []
        assert client.store.get("positions", []) == []

    def test_apply_appends_commit_from_positions_not_a_new_pm_decision(self) -> None:
        client = FakeSupabaseClient()
        _seed_booked_day(client)
        result = recover_ledger_from_book(client=client, run_date=RUN_DATE, apply=True)
        assert result.status == "committed"
        assert result.commit_id
        commits = client.store.get(COMMITS, [])
        assert len(commits) == 1
        assert commits[0]["workspace_id"] == HOUSE
        assert commits[0]["run_date"] == RUN_DATE.isoformat()
        approved = {
            r["symbol"]: float(r["approved_weight"])
            for r in client.store.get("portfolio_ledger_approved_targets", [])
        }
        assert approved["VGK"] == pytest.approx(0.25)
        assert approved["FXI"] == pytest.approx(0.05)
        docs = client.store.get("documents", [])
        manifest = next(r for r in docs if str(r.get("document_key", "")).startswith("commit-run/"))
        payload = manifest["payload"]
        assert payload["status"] == "committed"
        assert payload["recovery"] == "append_from_existing_book"
        assert payload["weights"]["VGK"] == 25.0
        assert payload["ledger_commit_id"] == result.commit_id
        assert client.store.get("positions", []) == []

    def test_second_apply_is_noop_when_manifest_exists(self) -> None:
        client = FakeSupabaseClient()
        _seed_booked_day(client)
        first = recover_ledger_from_book(client=client, run_date=RUN_DATE, apply=True)
        second = recover_ledger_from_book(client=client, run_date=RUN_DATE, apply=True)
        assert first.status == "committed"
        assert second.status == "already_committed"
        assert second.commit_id == first.commit_id
        assert len(client.store.get(COMMITS, [])) == 1

    def test_no_book_when_positions_missing(self) -> None:
        client = FakeSupabaseClient()
        client.canned_reads["positions"] = []
        client.canned_reads["nav_history"] = []
        result = recover_ledger_from_book(client=client, run_date=RUN_DATE, apply=True)
        assert result.status == "no_book"
        assert client.store.get(COMMITS, []) == []
