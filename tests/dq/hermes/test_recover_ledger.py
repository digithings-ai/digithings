"""Recover H9 ledger commit from an already-booked positions row (#3330)."""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState
from digiquant.olympus.hermes.writers.commit_io import weights_fingerprint
from digiquant.olympus.hermes.writers.ledger_io import APPROVED_TARGETS, COMMITS, _policy_version_id
from digiquant.olympus.hermes.writers.recover_ledger import (
    _prior_current_weights,
    _recovery_state,
    recover_ledger_from_book,
)
from digiquant.olympus.tenancy import house_workspace_id

from tests.fixtures.fake_supabase import FakeSupabaseClient

pytestmark = pytest.mark.unit

RUN_DATE = date(2026, 8, 31)
PRIOR_DATE = date(2026, 8, 28)
HOUSE = str(house_workspace_id())
TICKERS = ("EWZ", "FXI", "GLD", "VGK", "XLF", "XLV")


def _pos(day: date, ticker: str, weight: float) -> dict:
    return {
        "date": day.isoformat(),
        "ticker": ticker,
        "weight_pct": weight,
        "workspace_id": HOUSE,
    }


def _price_rows(*, moved: bool = False) -> list[dict]:
    rows = [{"date": "2026-08-27", "ticker": t, "close": 50.0} for t in TICKERS]
    later = 55.0 if moved else 50.0
    rows.extend({"date": "2026-08-28", "ticker": t, "close": later} for t in TICKERS)
    return rows


def _seed_booked_day(client: FakeSupabaseClient, *, moved_prices: bool = False) -> None:
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
    client.canned_reads["price_history"] = _price_rows(moved=moved_prices)
    client.canned_reads["decision_log"] = [{"run_date": RUN_DATE.isoformat(), "ticker": "VGK"}]
    client.canned_reads[COMMITS] = []
    client.canned_reads[APPROVED_TARGETS] = []
    client.canned_reads["documents"] = []


def _mirror_writes(client: FakeSupabaseClient) -> None:
    """Fake reads come from canned_reads; production PostgREST reads inserted rows."""
    for table, rows in client.store.items():
        client.canned_reads[table] = list(client.canned_reads.get(table, [])) + list(rows)


HEAD_COMMIT_ID = "11111111-2222-3333-4444-555555555555"
BOOK_WEIGHTS = {
    "EWZ": 5.0771,
    "FXI": 5.0,
    "GLD": 9.4215,
    "VGK": 25.0,
    "XLF": 20.0,
    "XLV": 14.8384,
}
BOOK_CASH = 20.663


def _seed_head_commit(client: FakeSupabaseClient) -> None:
    client.canned_reads[COMMITS] = [
        {
            "id": HEAD_COMMIT_ID,
            "run_date": RUN_DATE.isoformat(),
            "workspace_id": HOUSE,
            "supersedes_id": None,
        }
    ]


def _seed_approved(client: FakeSupabaseClient, weights: dict[str, float]) -> None:
    client.canned_reads[APPROVED_TARGETS] = [
        {
            "run_date": RUN_DATE.isoformat(),
            "symbol": ticker,
            "approved_weight": pct / 100.0,
            "workspace_id": HOUSE,
        }
        for ticker, pct in weights.items()
    ]


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
        default_policy = _policy_version_id(
            AtlasResearchState(
                run_id=uuid4(),
                run_type="delta",
                run_date=RUN_DATE,
                config=AtlasConfigBundle(preferences={"current_weights": {}}),
            )
        )
        assert commits[0]["policy_version_id"] != default_policy
        approved = {
            r["symbol"]: float(r["approved_weight"]) for r in client.store.get(APPROVED_TARGETS, [])
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
        assert payload["commit_seq"] == 1
        assert payload["supersedes"] == []
        assert client.store.get("positions", []) == []

    def test_second_apply_is_noop_when_manifest_exists(self) -> None:
        client = FakeSupabaseClient()
        _seed_booked_day(client)
        first = recover_ledger_from_book(client=client, run_date=RUN_DATE, apply=True)
        _mirror_writes(client)
        second = recover_ledger_from_book(client=client, run_date=RUN_DATE, apply=True)
        assert first.status == "committed"
        assert second.status == "already_committed"
        assert second.commit_id == first.commit_id
        assert len(client.store.get(COMMITS, [])) == 1

    def test_ledger_without_manifest_matching_approved_publishes_manifest_only(self) -> None:
        """Positions + head commit + matching approved, no commit-run document (#3426)."""
        client = FakeSupabaseClient()
        _seed_booked_day(client)
        _seed_head_commit(client)
        _seed_approved(client, {**BOOK_WEIGHTS, "CASH": BOOK_CASH})
        result = recover_ledger_from_book(client=client, run_date=RUN_DATE, apply=True)
        assert result.status == "already_committed"
        assert result.commit_id == HEAD_COMMIT_ID
        assert client.store.get(COMMITS, []) == []
        assert client.store.get(APPROVED_TARGETS, []) == []
        docs = client.store.get("documents", [])
        manifest = next(r for r in docs if str(r.get("document_key", "")).startswith("commit-run/"))
        payload = manifest["payload"]
        assert payload["status"] == "committed"
        assert payload["recovery"] == "append_from_existing_book"
        assert payload["ledger_commit_id"] == HEAD_COMMIT_ID
        assert payload["weights"]["VGK"] == 25.0
        assert payload["supersedes"] == []

    def test_ledger_without_manifest_mismatch_is_conflict_without_force(self) -> None:
        client = FakeSupabaseClient()
        _seed_booked_day(client)
        _seed_head_commit(client)
        _seed_approved(client, {"VGK": 99.0, "CASH": 1.0})
        result = recover_ledger_from_book(client=client, run_date=RUN_DATE, apply=True)
        assert result.status == "conflict"
        assert result.commit_id == HEAD_COMMIT_ID
        assert client.store.get(COMMITS, []) == []
        assert client.store.get(APPROVED_TARGETS, []) == []
        assert client.store.get("documents", []) == []

    def test_force_recommit_appends_when_approved_mismatch(self) -> None:
        client = FakeSupabaseClient()
        _seed_booked_day(client)
        _seed_head_commit(client)
        _seed_approved(client, {"VGK": 99.0, "CASH": 1.0})
        result = recover_ledger_from_book(
            client=client, run_date=RUN_DATE, apply=True, force_recommit=True
        )
        assert result.status == "committed"
        assert result.commit_id != HEAD_COMMIT_ID
        assert len(client.store.get(COMMITS, [])) == 1
        payload = next(
            r["payload"]
            for r in client.store.get("documents", [])
            if str(r.get("document_key", "")).startswith("commit-run/")
        )
        assert payload["ledger_commit_id"] == result.commit_id
        assert payload["supersedes"] == []

    def test_force_recommit_supersedes_prior_manifest_fingerprints(self) -> None:
        client = FakeSupabaseClient()
        _seed_booked_day(client)
        _seed_head_commit(client)
        prior_fp = "prior-manifest-fingerprint-not-the-book"
        client.store["documents"] = [
            {
                "date": RUN_DATE.isoformat(),
                "document_key": "commit-run/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "workspace_id": HOUSE,
                "payload": {
                    "status": "committed",
                    "commit_seq": 1,
                    "weights_fingerprint": prior_fp,
                    "ledger_commit_id": HEAD_COMMIT_ID,
                    "source_run_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                },
            }
        ]
        result = recover_ledger_from_book(
            client=client, run_date=RUN_DATE, apply=True, force_recommit=True
        )
        assert result.status == "committed"
        written = next(
            r["payload"]
            for r in client.store.get("documents", [])
            if r["payload"].get("ledger_commit_id") == result.commit_id
        )
        assert written["supersedes"] == [prior_fp]
        assert written["supersedes"] != [weights_fingerprint(BOOK_WEIGHTS)]

    def test_cli_lives_under_scripts_not_installable_src(self) -> None:
        src = Path("digiquant/src/digiquant/olympus/hermes/writers/recover_ledger.py").read_text()
        assert "argparse" not in src
        assert Path("digiquant/scripts/recover_ledger.py").is_file()

    def test_cli_apply_stale_date_requires_yes(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "recover_ledger_cli", Path("digiquant/scripts/recover_ledger.py")
        )
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        rc = mod.main(["--date", "2020-01-01", "--apply"])
        assert rc != 0

    def test_partial_commit_without_approved_still_appends(self) -> None:
        client = FakeSupabaseClient()
        _seed_booked_day(client)
        client.canned_reads[COMMITS] = [
            {
                "id": "11111111-2222-3333-4444-555555555555",
                "run_date": RUN_DATE.isoformat(),
                "workspace_id": HOUSE,
                "supersedes_id": None,
            }
        ]
        result = recover_ledger_from_book(client=client, run_date=RUN_DATE, apply=True)
        assert result.status == "conflict"
        assert result.commit_id == "11111111-2222-3333-4444-555555555555"
        assert client.store.get(COMMITS, []) == []
        assert client.store.get(APPROVED_TARGETS, []) == []
        assert client.store.get("documents", []) == []

    def test_fingerprint_mismatch_is_conflict(self) -> None:
        client = FakeSupabaseClient()
        _seed_booked_day(client)
        book_fp = weights_fingerprint(
            {"EWZ": 5.0771, "FXI": 5.0, "GLD": 9.4215, "VGK": 25.0, "XLF": 20.0, "XLV": 14.8384}
        )
        client.store["documents"] = [
            {
                "date": RUN_DATE.isoformat(),
                "document_key": "commit-run/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "workspace_id": HOUSE,
                "payload": {
                    "status": "committed",
                    "weights_fingerprint": "definitely-not-the-book-on-disk",
                    "ledger_commit_id": "11111111-2222-3333-4444-555555555555",
                    "source_run_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                },
            }
        ]
        result = recover_ledger_from_book(client=client, run_date=RUN_DATE, apply=True)
        assert result.status == "conflict"
        assert result.commit_id == "11111111-2222-3333-4444-555555555555"
        assert book_fp != "definitely-not-the-book-on-disk"
        assert client.store.get(COMMITS, []) == []
        assert client.store.get(APPROVED_TARGETS, []) == []

    def test_prior_weights_are_mark_to_market(self) -> None:
        client = FakeSupabaseClient()
        _seed_booked_day(client, moved_prices=True)
        mtm = _prior_current_weights(client=client, run_date=RUN_DATE, workspace_id=None)
        assert mtm["FXI"] != pytest.approx(9.8561)
        assert mtm["FXI"] > 9.8561

    def test_recovery_policy_is_not_default_caps(self) -> None:
        hydrated = _recovery_state(
            run_date=RUN_DATE,
            source_run_id=uuid4(),
            current_weights={"FXI": 9.8561},
            workspace_id=None,
        )
        default = AtlasResearchState(
            run_id=uuid4(),
            run_type="delta",
            run_date=RUN_DATE,
            config=AtlasConfigBundle(preferences={"current_weights": {"FXI": 9.8561}}),
        )
        assert _policy_version_id(hydrated) != _policy_version_id(default)

    def test_no_book_when_positions_missing(self) -> None:
        client = FakeSupabaseClient()
        client.canned_reads["positions"] = []
        client.canned_reads["nav_history"] = []
        result = recover_ledger_from_book(client=client, run_date=RUN_DATE, apply=True)
        assert result.status == "no_book"
        assert client.store.get(COMMITS, []) == []

    def test_newer_incomplete_head_is_not_already_committed(self) -> None:
        client = FakeSupabaseClient()
        _seed_booked_day(client)
        book = {
            "EWZ": 5.0771,
            "FXI": 5.0,
            "GLD": 9.4215,
            "VGK": 25.0,
            "XLF": 20.0,
            "XLV": 14.8384,
        }
        book_fp = weights_fingerprint(book)
        client.canned_reads[COMMITS] = [
            {
                "id": "11111111-2222-3333-4444-555555555555",
                "run_date": RUN_DATE.isoformat(),
                "workspace_id": HOUSE,
                "supersedes_id": None,
            },
            {
                "id": "22222222-3333-4444-5555-666666666666",
                "run_date": RUN_DATE.isoformat(),
                "workspace_id": HOUSE,
                "supersedes_id": "11111111-2222-3333-4444-555555555555",
            },
        ]
        client.canned_reads[APPROVED_TARGETS] = [
            {
                "run_date": RUN_DATE.isoformat(),
                "symbol": ticker,
                "approved_weight": pct / 100.0,
                "workspace_id": HOUSE,
            }
            for ticker, pct in {**book, "CASH": 20.663}.items()
        ]
        client.store["documents"] = [
            {
                "date": RUN_DATE.isoformat(),
                "document_key": "commit-run/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "workspace_id": HOUSE,
                "payload": {
                    "status": "committed",
                    "commit_seq": 1,
                    "weights_fingerprint": book_fp,
                    "ledger_commit_id": "11111111-2222-3333-4444-555555555555",
                    "source_run_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                },
            }
        ]
        result = recover_ledger_from_book(client=client, run_date=RUN_DATE, apply=True)
        assert result.status == "already_committed"
        assert result.commit_id == "22222222-3333-4444-5555-666666666666"
        assert client.store.get(COMMITS, []) == []
        payload = next(
            r["payload"]
            for r in client.store.get("documents", [])
            if str(r.get("document_key", "")).startswith("commit-run/")
            and r["payload"].get("ledger_commit_id") == result.commit_id
        )
        assert payload["commit_seq"] == 2
        assert payload["supersedes"] == [book_fp]

    def test_ambiguous_commit_seq_is_conflict(self) -> None:
        client = FakeSupabaseClient()
        _seed_booked_day(client)
        payload = {
            "status": "committed",
            "commit_seq": 1,
            "weights_fingerprint": "aaaaaaaa",
            "ledger_commit_id": "11111111-2222-3333-4444-555555555555",
        }
        client.store["documents"] = [
            {
                "date": RUN_DATE.isoformat(),
                "document_key": f"commit-run/{suffix}",
                "workspace_id": HOUSE,
                "payload": dict(payload),
            }
            for suffix in (
                "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "bbbbbbbb-cccc-dddd-eeee-ffffffffffff",
            )
        ]
        result = recover_ledger_from_book(client=client, run_date=RUN_DATE, apply=True)
        assert result.status == "conflict"
        assert client.store.get(COMMITS, []) == []

    def test_recovery_manifest_increments_commit_seq(self) -> None:
        client = FakeSupabaseClient()
        _seed_booked_day(client)
        book_fp = weights_fingerprint(
            {"EWZ": 5.0771, "FXI": 5.0, "GLD": 9.4215, "VGK": 25.0, "XLF": 20.0, "XLV": 14.8384}
        )
        client.canned_reads[COMMITS] = [
            {
                "id": "11111111-2222-3333-4444-555555555555",
                "run_date": RUN_DATE.isoformat(),
                "workspace_id": HOUSE,
                "supersedes_id": None,
            }
        ]
        client.store["documents"] = [
            {
                "date": RUN_DATE.isoformat(),
                "document_key": "commit-run/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "workspace_id": HOUSE,
                "payload": {
                    "status": "committed",
                    "commit_seq": 4,
                    "weights_fingerprint": book_fp,
                    "ledger_commit_id": "11111111-2222-3333-4444-555555555555",
                    "source_run_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                },
            }
        ]
        result = recover_ledger_from_book(
            client=client, run_date=RUN_DATE, apply=True, force_recommit=True
        )
        assert result.status == "committed"
        written = next(
            r["payload"]
            for r in client.store.get("documents", [])
            if r["payload"].get("ledger_commit_id") == result.commit_id
        )
        assert written["commit_seq"] == 5
        assert written["supersedes"] == [book_fp]

    def test_recovery_module_does_not_call_book_portfolio(self) -> None:
        source = Path(
            "digiquant/src/digiquant/olympus/hermes/writers/recover_ledger.py"
        ).read_text()
        assert "book_portfolio(" not in source
