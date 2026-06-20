"""H9 ``commit_run`` coherence + idempotency tests (#932)."""

from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest

from digiquant.olympus.atlas.state import (
    AtlasResearchState,
    FocusRosterEntry,
    PhaseHermesState,
)
from digiquant.olympus.hermes.models.pm_direction import PMDirectionMemo, TickerDirection
from digiquant.olympus.hermes.phases.h9_commit_run import CommitRunDeps, build_commit_run_node

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

RUN_DATE = date(2026, 6, 12)
_SOURCE_RUN_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def _sized_book(spy_pct: float = 100.0) -> dict:
    return {
        "recommended_portfolio": [{"ticker": "SPY", "target_pct": spy_pct}],
        "actions": [],
        "notes": "H8 sized book",
    }


def _state(
    *,
    sized_book: dict | None = None,
    held: tuple[str, ...] = (),
    analysts: dict | None = None,
    pm_memo: PMDirectionMemo | None = None,
) -> AtlasResearchState:
    state = AtlasResearchState(
        run_id=_SOURCE_RUN_ID,
        run_type="delta",
        run_date=RUN_DATE,
        baseline_date=date(2026, 6, 9),
    )
    roster = [FocusRosterEntry(ticker=t, roster_reason="held") for t in held]
    state.phase_hermes = PhaseHermesState(
        focus_roster=roster,
        sized_book=sized_book if sized_book is not None else _sized_book(),
        asset_analysts=analysts
        or {
            "SPY": {
                "ticker": "SPY",
                "stance": "buy",
                "conviction_score": 4,
                "thesis": "risk-on",
                "risks": "",
                "sources": [],
            }
        },
        pm_direction_memo=pm_memo
        or PMDirectionMemo(
            date=RUN_DATE,
            roster=[TickerDirection(ticker="SPY", direction="long", conviction_rank=1)],
            memo="go long SPY",
        ),
    )
    return state


def _run(client: FakeSupabaseClient, state: AtlasResearchState) -> dict:
    node = build_commit_run_node(CommitRunDeps(client=client))
    return node(state)


class TestCommitRunBooking:
    def test_books_positions_nav_and_publishes_brief(self) -> None:
        client = FakeSupabaseClient()
        _run(client, _state())

        positions = {r["ticker"]: r for r in client.store.get("positions", [])}
        assert positions["SPY"]["weight_pct"] == 100.0
        assert len(client.store.get("nav_history", [])) == 1

        docs = client.store.get("documents", [])
        brief = next(r for r in docs if r.get("document_key") == "pm-rebalance")
        brief_weights = {
            row["ticker"]: row["target_pct"] for row in brief["payload"]["recommended_portfolio"]
        }
        assert brief_weights["SPY"] == positions["SPY"]["weight_pct"]

    def test_persists_decision_log_without_phase9(self) -> None:
        client = FakeSupabaseClient()
        _run(client, _state())
        rows = client.store.get("decision_log", [])
        assert len(rows) == 1
        assert rows[0]["ticker"] == "SPY"
        assert rows[0]["status"] == "pending"
        assert rows[0]["run_id"] == str(_SOURCE_RUN_ID)


class TestCommitRunCoherence:
    def test_held_ticker_flat_in_h7_is_allowed(self) -> None:
        client = FakeSupabaseClient()
        memo = PMDirectionMemo(
            date=RUN_DATE,
            roster=[
                TickerDirection(ticker="SPY", direction="long", conviction_rank=1),
                TickerDirection(ticker="IJR", direction="flat", conviction_rank=2),
            ],
            memo="exit small cap",
        )
        state = _state(
            sized_book={
                "recommended_portfolio": [{"ticker": "SPY", "target_pct": 100.0}],
                "actions": [],
                "notes": "",
            },
            held=("IJR", "SPY"),
            pm_memo=memo,
        )
        out = _run(client, state)
        manifest = (out.get("phase_hermes") or PhaseHermesState()).commit_manifest or {}
        assert manifest.get("status") == "committed"
        assert "IJR" not in {
            r["ticker"] for r in client.store.get("positions", []) if r["ticker"] != "CASH"
        }

    def test_held_ticker_missing_without_flat_fails_closed(self) -> None:
        client = FakeSupabaseClient()
        state = _state(
            sized_book={
                "recommended_portfolio": [{"ticker": "SPY", "target_pct": 100.0}],
                "actions": [],
                "notes": "",
            },
            held=("IJR", "SPY"),
        )
        node = build_commit_run_node(CommitRunDeps(client=client))
        result = node(state)
        assert result.get("errors"), "expected PhaseError for dropped held ticker"
        assert "positions" not in client.store

    def test_open_position_without_analyst_or_flat_fails_closed(self) -> None:
        client = FakeSupabaseClient()
        state = _state(
            sized_book={
                "recommended_portfolio": [
                    {"ticker": "SPY", "target_pct": 60.0},
                    {"ticker": "QQQ", "target_pct": 40.0},
                ],
                "actions": [],
                "notes": "",
            },
            analysts={
                "SPY": {
                    "ticker": "SPY",
                    "stance": "buy",
                    "conviction_score": 4,
                    "thesis": "x",
                    "risks": "",
                    "sources": [],
                }
            },
            pm_memo=PMDirectionMemo(
                date=RUN_DATE,
                roster=[
                    TickerDirection(ticker="SPY", direction="long", conviction_rank=1),
                    TickerDirection(ticker="QQQ", direction="long", conviction_rank=2),
                ],
            ),
        )
        node = build_commit_run_node(CommitRunDeps(client=client))
        result = node(state)
        assert result.get("errors")
        assert "positions" not in client.store


class TestCommitRunIdempotency:
    def test_rerun_same_source_run_id_is_noop(self) -> None:
        client = FakeSupabaseClient()
        state = _state()
        node = build_commit_run_node(CommitRunDeps(client=client))
        first = node(state)
        pos_count_1 = len(client.store.get("positions", []))
        second = node(state)
        pos_count_2 = len(client.store.get("positions", []))
        first_manifest = (first.get("phase_hermes") or PhaseHermesState()).commit_manifest or {}
        second_manifest = (second.get("phase_hermes") or PhaseHermesState()).commit_manifest or {}
        assert first_manifest.get("status") == "committed"
        assert second_manifest.get("status") == "noop"
        assert pos_count_2 == pos_count_1

    def test_same_source_run_id_conflicting_book_raises_phase_error(self) -> None:
        client = FakeSupabaseClient()
        node = build_commit_run_node(CommitRunDeps(client=client))
        node(_state(sized_book=_sized_book(100.0)))
        conflict = node(_state(sized_book=_sized_book(80.0)))
        assert conflict.get("errors")
        err = conflict["errors"][0]
        assert err.phase == "hermes_h9_commit_run"
        assert "conflict" in err.message.lower() or "mismatch" in err.message.lower()
