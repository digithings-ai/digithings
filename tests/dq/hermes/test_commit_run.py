"""H9 ``commit_run`` coherence + idempotency tests (#932, #1046)."""

from __future__ import annotations

import pathlib
import re
from datetime import date, timedelta
from uuid import UUID

import pytest
from digiquant.olympus.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    ExcludedTicker,
    FocusRosterEntry,
    PhaseHermesState,
    PriorContext,
)
from digiquant.olympus.hermes.models.pm_direction import PMDirectionMemo, TickerDirection
from digiquant.olympus.hermes.phases.h9_commit_run import CommitRunDeps, build_commit_run_node
from digiquant.olympus.hermes.writers.commit_io import (
    _canonical_thesis_ids,
    load_commit_manifests,
    resolve_prior_commit,
)
from digiquant.olympus.hermes.writers.ledger_io import (
    _CLOSE_LOOKBACK_DAYS,
    _CLOSE_TICKER_BATCH,
    _frozen_symbols,
    _last_closes,
)
from digiquant.olympus.hermes.writers.ledger_io import (
    _heads as _ledger_heads,
)

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
    with_sized_book: bool = True,
    sized_book: dict | None = None,
    held: tuple[str, ...] = (),
    prior_book_held: tuple[str, ...] = (),
    excluded: tuple[str, ...] = (),
    excluded_reason: str = "held, no material change (below staleness threshold)",
    analysts: dict | None = None,
    pm_memo: PMDirectionMemo | None = None,
    preferences: dict | None = None,
    run_id: UUID = _SOURCE_RUN_ID,
) -> AtlasResearchState:
    # Prior-book holdings make a name "held" without putting it in the roster — the
    # real shape of a gated-out held position (held in the book, excluded from H5).
    # PriorContext is frozen, so it must be built at construction time.
    prior_context = (
        PriorContext(prior_book=[{"ticker": t, "weight_pct": 0.0} for t in prior_book_held])
        if prior_book_held
        else PriorContext()
    )
    state = AtlasResearchState(
        run_id=run_id,
        run_type="delta",
        run_date=RUN_DATE,
        baseline_date=date(2026, 6, 9),
        prior_context=prior_context,
        config=AtlasConfigBundle(preferences=preferences or {}),
    )
    roster = [FocusRosterEntry(ticker=t, roster_reason="held") for t in held]
    excluded_ledger = [ExcludedTicker(ticker=t, reason=excluded_reason) for t in excluded]
    hermes_fields: dict = dict(
        focus_roster=roster,
        focus_roster_excluded=excluded_ledger,
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
    if with_sized_book:
        hermes_fields["sized_book"] = sized_book if sized_book is not None else _sized_book()
    state.phase_hermes = PhaseHermesState(**hermes_fields)
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

    def test_decision_holding_days_do_not_shorten_position_risk_horizon(self, monkeypatch) -> None:
        monkeypatch.setenv("OLYMPUS_POSITION_RISK_FIELDS", "1")
        client = FakeSupabaseClient(
            canned_reads={
                "price_history": [{"date": "2026-06-12", "ticker": "SPY", "close": 600.0}],
                "price_technicals": [{"date": "2026-06-12", "ticker": "SPY", "atr_pct": 1.5}],
            }
        )

        _run(client, _state(preferences={"holding_days": 5}))

        spy = next(row for row in client.store["positions"] if row["ticker"] == "SPY")
        assert spy["horizon_days"] == 21

    def test_explicit_position_risk_horizon_is_persisted(self, monkeypatch) -> None:
        monkeypatch.setenv("OLYMPUS_POSITION_RISK_FIELDS", "1")
        client = FakeSupabaseClient()

        _run(client, _state(preferences={"holding_days": 5, "risk_horizon_days": 30}))

        spy = next(row for row in client.store["positions"] if row["ticker"] == "SPY")
        assert spy["horizon_days"] == 30

    def test_analyst_document_persists_full_thesis_and_risks(self) -> None:
        # Regression guard (#948): the analyst/{ticker} document must NOT truncate the
        # thesis and must carry a non-empty `risks` field. The prod 06-17..20 docs showed
        # theses clipped at ~1200 chars mid-word with no risks — that was the *deployed*
        # old model; the thesis-first AnalystPayload carries the full thesis + risks, and
        # this test pins that the persistence path never re-introduces a clip.
        from digiquant.olympus.hermes.writers.commit_io import publish_hermes_documents

        long_thesis = "SPY rides broad risk-on participation with constructive breadth. " * 40
        assert len(long_thesis) > 1200
        client = FakeSupabaseClient()
        state = _state(
            analysts={
                "SPY": {
                    "ticker": "SPY",
                    "stance": "buy",
                    "conviction_score": 4,
                    "thesis": long_thesis,
                    "risks": "A breadth divergence or a VIX spike above 25 invalidates the call.",
                    "sources": ["price_technicals:SPY:2026-06-12"],
                }
            },
        )
        publish_hermes_documents(client=client, state=state)

        analyst_doc = next(
            r for r in client.store["documents"] if r.get("document_key") == "analyst/SPY"
        )
        assert analyst_doc["payload"]["thesis"] == long_thesis  # full, not truncated
        assert len(analyst_doc["payload"]["thesis"]) > 1200  # the old hard clip is gone
        assert analyst_doc["payload"]["risks"].strip()  # risks persisted, non-empty


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

    def test_gated_out_held_position_in_excluded_ledger_is_allowed(self) -> None:
        """A held position deliberately gated out of H5 (Stage 1b staleness gate) is
        carried, not orphaned (#1030).

        AAPL is a prior-book holding (held) below the staleness threshold, so H4
        records it in ``focus_roster_excluded`` and dispatches no analyst. The
        position is still carried in the book (weight > 0) and is not flat — without
        the held-carry exemption, ``coherence_errors`` would fail-close with "lacks
        H5 analyst doc", the live regression that broke the quiet-day path.
        """
        client = FakeSupabaseClient()
        state = _state(
            sized_book={
                "recommended_portfolio": [
                    {"ticker": "SPY", "target_pct": 60.0},
                    {"ticker": "AAPL", "target_pct": 40.0},
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
            prior_book_held=("AAPL",),  # AAPL is genuinely held (prior book), not just excluded
            excluded=("AAPL",),  # gated out of H5 as a quiet held name — carried, not flat
            pm_memo=PMDirectionMemo(
                date=RUN_DATE,
                roster=[TickerDirection(ticker="SPY", direction="long", conviction_rank=1)],
            ),
        )
        out = _run(client, state)
        assert not out.get("errors"), out.get("errors")
        manifest = (out.get("phase_hermes") or PhaseHermesState()).commit_manifest or {}
        assert manifest.get("status") == "committed"

    def test_non_held_excluded_ticker_still_fails_closed(self) -> None:
        """The carry exemption is HELD-only (#1030 review).

        A non-held watchlist name in the excluded ledger (reason: below technical
        screen) that nonetheless lands in the book with a positive weight and no
        analyst doc must STILL fail closed — it was never owned, so it is not a
        carry. Guards against over-broadening the fail-closed exemption.
        """
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
            # QQQ is in the ledger but NOT held — a below-screen name, not a carry.
            excluded=("QQQ",),
            excluded_reason="not thesis-mapped and below technical screen",
            pm_memo=PMDirectionMemo(
                date=RUN_DATE,
                roster=[TickerDirection(ticker="SPY", direction="long", conviction_rank=1)],
            ),
        )
        result = _run(client, state)
        assert result.get("errors"), "non-held excluded ticker with weight must fail closed"
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

    def test_fresh_run_id_same_date_same_book_is_noop(self) -> None:
        """#1744: the retry shape the old run_id-keyed guard structurally could not see.

        ``AtlasResearchState.run_id`` defaults to ``uuid4()``, so CI's outer retry
        always presents a new id. Keyed on run_id the guard never fired and the
        second attempt re-booked the whole date; keyed on the date it is a no-op.
        """
        client = FakeSupabaseClient()
        node = build_commit_run_node(CommitRunDeps(client=client))
        node(_state())
        docs_after_first = len(client.store.get("documents", []))

        retry = node(_state(run_id=UUID("11111111-2222-3333-4444-555555555555")))
        manifest = (retry.get("phase_hermes") or PhaseHermesState()).commit_manifest or {}
        assert manifest.get("status") == "noop", (
            "a fresh run_id on the same date with the same book must not re-book"
        )
        assert len(client.store.get("documents", [])) == docs_after_first

    def test_same_date_conflicting_book_supersedes_instead_of_failing(self) -> None:
        """#1744: last-writer-wins, NOT a PhaseError.

        Replaces the former ``…_raises_phase_error`` expectation deliberately. Prod
        2026-06-24 carries three commit manifests with three *different*
        ``weights_fingerprint`` values, so a hard idempotency conflict on a
        run_date-keyed guard would fail the phase on a shape production already
        produces — and, with the uncommitted-book gate, report a degraded run for a
        book that did commit. Orphan pruning makes the re-commit converge on the
        last writer's book, so reconciling is both safe and the only honest verdict.
        """
        client = FakeSupabaseClient()
        node = build_commit_run_node(CommitRunDeps(client=client))
        first = node(_state(sized_book=_sized_book(100.0)))
        second = node(_state(sized_book=_sized_book(80.0)))

        assert not second.get("errors"), second.get("errors")
        first_manifest = (first.get("phase_hermes") or PhaseHermesState()).commit_manifest or {}
        second_manifest = (second.get("phase_hermes") or PhaseHermesState()).commit_manifest or {}
        assert second_manifest.get("status") == "committed"
        assert second_manifest.get("commit_seq") == first_manifest["commit_seq"] + 1
        assert second_manifest.get("supersedes") == [first_manifest["weights_fingerprint"]]

    def test_ambiguous_prior_manifests_recommit_rather_than_claim_noop(self) -> None:
        """Legacy manifests all read ``commit_seq`` 0, so "latest" is undecidable.

        ``documents`` has no timestamp column. On a date carrying several pre-#1744
        manifests (2026-06-24: three, fingerprints A/B/C) matching *any* of them by
        fingerprint could report "already booked" while the rows on disk belong to a
        different book, so the tie must resolve to a re-commit.
        """
        legacy = [
            {"schema_version": "1.0", "status": "committed", "weights_fingerprint": fp}
            for fp in ("fp-a", "fp-b", "fp-c")
        ]
        latest, next_seq = resolve_prior_commit(legacy)
        assert latest is None, "an undecidable tie must not be treated as the last writer"
        assert next_seq == 1

        single = [{"commit_seq": 4, "weights_fingerprint": "fp-d"}, *legacy]
        latest, next_seq = resolve_prior_commit(single)
        assert latest is not None and latest["weights_fingerprint"] == "fp-d"
        assert next_seq == 5

    def test_manifests_are_loaded_by_date_across_run_ids(self) -> None:
        """The PostgREST path filters ``document_key`` by prefix, not by run_id."""
        client = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    {
                        "date": RUN_DATE.isoformat(),
                        "document_key": "commit-run/some-other-uuid",
                        "payload": {"status": "committed", "weights_fingerprint": "fp-x"},
                    },
                    {
                        "date": RUN_DATE.isoformat(),
                        "document_key": "pm-rebalance",
                        "payload": {"not": "a manifest"},
                    },
                    {
                        "date": "2026-06-11",
                        "document_key": "commit-run/yesterday",
                        "payload": {"status": "committed", "weights_fingerprint": "fp-y"},
                    },
                ]
            }
        )
        found = load_commit_manifests(client=client, run_date=RUN_DATE)
        assert [m["weights_fingerprint"] for m in found] == ["fp-x"]

    def test_missing_sized_book_with_h7_memo_fails_closed(self) -> None:
        client = FakeSupabaseClient()
        state = _state(with_sized_book=False)
        node = build_commit_run_node(CommitRunDeps(client=client))
        result = node(state)
        assert result.get("errors")
        err = result["errors"][0]
        assert err.phase == "hermes_h9_commit_run"
        assert "sized_book" in err.message.lower()
        assert "positions" not in client.store


class TestOrphanPositionPruning:
    """#1744 — a same-date re-commit that drops a name must delete its row.

    ``positions`` is upserted on ``(date, ticker)`` with no delete, so before this
    fix a second commit for the same date that shrank the ticker set left the
    dropped row behind at its old weight: the raw book then exceeds 100% of NAV,
    ``refresh_performance_metrics`` sums the orphan into
    ``portfolio_metrics.invested_pct``, and ``build_events_from_positions_book``
    emits a phantom OPEN/TRIM/EXIT for a position no run intended to hold.

    The fake client reads from ``canned_reads`` and writes to ``store``, so a row
    that must be *seen and then deleted* is seeded into both.
    """

    @staticmethod
    def _client_with_same_date_rows(rows: list[dict]) -> FakeSupabaseClient:
        client = FakeSupabaseClient(canned_reads={"positions": list(rows)})
        client.store["positions"] = [dict(r) for r in rows]
        return client

    def test_dropped_ticker_is_deleted_not_left_as_orphan(self) -> None:
        # An earlier attempt on RUN_DATE booked XLF; this attempt's book is SPY only.
        client = self._client_with_same_date_rows(
            [{"date": RUN_DATE.isoformat(), "ticker": "XLF", "weight_pct": 5.0}]
        )
        out = _run(client, _state())

        assert not out.get("errors"), out.get("errors")
        tickers = {r["ticker"] for r in client.store["positions"]}
        assert tickers == {"SPY"}, f"orphan row survived the re-commit: {tickers}"
        manifest = (out.get("phase_hermes") or PhaseHermesState()).commit_manifest or {}
        assert manifest.get("pruned_tickers") == ["XLF"]

    def test_stale_cash_row_is_deleted_when_re_commit_is_fully_invested(self) -> None:
        # ``book_portfolio`` only appends CASH when cash_pct > 0.01, so a prior
        # partially-invested attempt's CASH row would otherwise survive a
        # fully-invested re-commit and contradict nav_history.cash_pct.
        client = self._client_with_same_date_rows(
            [{"date": RUN_DATE.isoformat(), "ticker": "CASH", "weight_pct": 20.0}]
        )
        _run(client, _state())  # default book: SPY 100% → cash_pct 0.0

        assert "CASH" not in {r["ticker"] for r in client.store["positions"]}
        nav_row = client.store["nav_history"][-1]
        assert nav_row["cash_pct"] == 0.0
        assert nav_row["invested_pct"] == 100.0

    def test_book_with_cash_keeps_its_own_cash_row(self) -> None:
        """The prune must never delete a CASH row the current book itself wrote."""
        client = self._client_with_same_date_rows([])
        _run(client, _state(sized_book=_sized_book(60.0)))
        rows = {r["ticker"]: r for r in client.store["positions"]}
        assert rows["CASH"]["weight_pct"] == 40.0
        assert rows["SPY"]["weight_pct"] == 60.0


class TestNavInterval:
    """#1745 — manifest NAV is compounded over the interval since the prior book date.

    ``nav_history`` is restated every evening by the metrics cron to "NAV as of this
    date's close", so ``_prior_nav`` already embeds the move up to the prior book
    date. The old ``query_price_deltas`` call applied the latest *one-day* delta on
    top of that, which double-counts on a dense series and loses the whole interval
    across a book gap.
    """

    @staticmethod
    def _client(*, book_date: str, closes: dict[str, float]) -> FakeSupabaseClient:
        return FakeSupabaseClient(
            canned_reads={
                "positions": [{"date": book_date, "ticker": "SPY", "weight_pct": 100.0}],
                "nav_history": [{"date": book_date, "nav": 100.0}],
                "price_history": [
                    {"date": d, "ticker": "SPY", "close": c} for d, c in sorted(closes.items())
                ],
            }
        )

    def test_dense_series_does_not_double_count_the_prior_day_return(self) -> None:
        """Prior book date == the last close before run_date → no further move.

        The production shape (2026-07-28): prior book 07-27, last close before the
        commit also 07-27. The old code applied the 07-24→07-27 return that
        ``nav_history`` had already absorbed into the 07-27 NAV, inflating the
        manifest by that return a second time.
        """
        client = self._client(
            book_date="2026-06-11",
            closes={"2026-06-10": 100.0, "2026-06-11": 110.0},
        )
        _run(client, _state())
        # 110/100 - 1 = +10% is already inside prior_nav; re-applying it would give 110.0.
        assert client.store["nav_history"][-1]["nav"] == pytest.approx(100.0, abs=1e-6)

    def test_book_gap_return_spans_the_whole_interval(self) -> None:
        """A 10-day book gap must record the interval return, not one day of it.

        Prod 2026-06-26 → 07-17 (18 skipped days) recorded +0.03% for a book whose
        actual weighted return over the interval was -0.37%.
        """
        client = self._client(
            book_date="2026-06-01",
            closes={"2026-06-01": 100.0, "2026-06-10": 89.0, "2026-06-11": 90.0},
        )
        _run(client, _state())
        # Interval 06-01 → 06-11 = -10%. The last one-day delta (89 → 90) is +1.12%.
        assert client.store["nav_history"][-1]["nav"] == pytest.approx(90.0, abs=1e-6)

    def test_ticker_with_no_close_at_the_interval_start_is_dropped(self) -> None:
        """Conservative-drop contract: a name we cannot price must not move the index."""
        client = self._client(
            book_date="2026-06-01",
            closes={"2026-06-11": 90.0},  # no close at or before the 06-01 anchor
        )
        _run(client, _state())
        assert client.store["nav_history"][-1]["nav"] == pytest.approx(100.0, abs=1e-6)

    def test_first_ever_run_seeds_the_index_at_100(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={"positions": [], "nav_history": [], "price_history": []}
        )
        _run(client, _state())
        assert client.store["nav_history"][-1]["nav"] == 100.0


class TestCanonicalThesisIds:
    """Verify thesis_id canonicalization in book_portfolio (#1046)."""

    _RUN_DATE = date(2026, 6, 12)

    def test_canonical_id_used_when_thesis_vehicle_row_exists(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "thesis_vehicles": [
                    {"date": self._RUN_DATE.isoformat(), "thesis_id": "MT1", "ticker": "SPY"},
                    {
                        "date": self._RUN_DATE.isoformat(),
                        "thesis_id": "vehicle-nvda",
                        "ticker": "NVDA",
                    },
                ]
            }
        )
        result = _canonical_thesis_ids(client, self._RUN_DATE, ["SPY", "NVDA", "TLT"])
        assert result["SPY"] == "MT1"
        assert result["NVDA"] == "vehicle-nvda"
        assert "TLT" not in result  # no thesis_vehicles row → falls back at call site

    def test_empty_tickers_returns_empty(self) -> None:
        client = FakeSupabaseClient()
        assert _canonical_thesis_ids(client, self._RUN_DATE, []) == {}

    def test_client_error_returns_empty_not_raises(self) -> None:
        class _BrokenClient:
            def table(self, _name: str) -> "_BrokenClient":
                return self

            def select(self, _cols: str) -> "_BrokenClient":
                return self

            def eq(self, *_args: object) -> "_BrokenClient":
                return self

            def in_(self, *_args: object) -> "_BrokenClient":
                return self

            def execute(self) -> None:
                raise RuntimeError("DB unavailable")

        result = _canonical_thesis_ids(_BrokenClient(), self._RUN_DATE, ["SPY"])  # type: ignore[arg-type]
        assert result == {}

    def test_book_portfolio_writes_canonical_thesis_id(self) -> None:
        """End-to-end: positions rows use canonical thesis_id, not bare ticker.lower()."""
        client = FakeSupabaseClient(
            canned_reads={
                "thesis_vehicles": [
                    {"date": RUN_DATE.isoformat(), "thesis_id": "MT1", "ticker": "SPY"},
                ],
                "nav_history": [],
                "price_history": [],
            }
        )
        state = _state()  # default: SPY 100%
        node = build_commit_run_node(CommitRunDeps(client=client))
        node(state)

        positions_written = client.store.get("positions", [])
        spy_row = next((r for r in positions_written if r.get("ticker") == "SPY"), None)
        assert spy_row is not None, "SPY position row not written"
        assert spy_row.get("thesis_id") == "MT1", (
            f"expected canonical thesis_id 'MT1', got {spy_row.get('thesis_id')!r}"
        )

    def test_book_portfolio_falls_back_to_vehicle_prefix_when_no_thesis_vehicle(self) -> None:
        """Tickers absent from thesis_vehicles get vehicle-{ticker.lower()} as thesis_id."""
        client = FakeSupabaseClient(
            canned_reads={
                "thesis_vehicles": [],  # no rows
                "nav_history": [],
                "price_history": [],
            }
        )
        state = _state()
        node = build_commit_run_node(CommitRunDeps(client=client))
        node(state)

        positions_written = client.store.get("positions", [])
        spy_row = next((r for r in positions_written if r.get("ticker") == "SPY"), None)
        assert spy_row is not None
        assert spy_row.get("thesis_id") == "vehicle-spy"


class TestMemoUnaddressedHeldCarry:
    """#1649 — held names the H7 memo omits are carried, never dropped or blocked.

    Run 29936849103 (2026-07-22): the PM memo's roster omitted SEVEN held tickers
    (neither ``long`` nor ``flat``); H8 dropped them and H9 froze the commit with
    "held ticker X missing from book and not flat in H7". Memo coverage is LLM
    discipline — an owned position with no explicit instruction defaults to hold.
    """

    _SPY_ANALYST = {
        "ticker": "SPY",
        "stance": "buy",
        "conviction_score": 4,
        "thesis": "x",
        "risks": "",
        "sources": [],
    }

    def _memo_spy_long_only(self) -> PMDirectionMemo:
        return PMDirectionMemo(
            date=RUN_DATE,
            roster=[TickerDirection(ticker="SPY", direction="long", conviction_rank=1)],
        )

    def test_memo_omitted_held_name_in_book_commits(self) -> None:
        """Held + analyzed + memo-omitted (the DBO shape) commits once carried."""
        dbo_analyst = dict(self._SPY_ANALYST, ticker="DBO", thesis="oil carry")
        client = FakeSupabaseClient()
        state = _state(
            sized_book={
                "recommended_portfolio": [
                    {"ticker": "SPY", "target_pct": 60.0},
                    {"ticker": "DBO", "target_pct": 40.0},
                ],
                "actions": [],
                "notes": "",
            },
            analysts={"SPY": self._SPY_ANALYST, "DBO": dbo_analyst},
            prior_book_held=("DBO",),
            pm_memo=self._memo_spy_long_only(),
        )
        out = _run(client, state)
        assert not out.get("errors"), out.get("errors")
        manifest = (out.get("phase_hermes") or PhaseHermesState()).commit_manifest or {}
        assert manifest.get("status") == "committed"

    def test_memo_omitted_held_name_without_analyst_doc_still_commits(self) -> None:
        """Loop-2 exemption: a carried held name whose H5 failed today is not a stray."""
        client = FakeSupabaseClient()
        state = _state(
            sized_book={
                "recommended_portfolio": [
                    {"ticker": "SPY", "target_pct": 60.0},
                    {"ticker": "DBO", "target_pct": 40.0},
                ],
                "actions": [],
                "notes": "",
            },
            analysts={"SPY": self._SPY_ANALYST},
            prior_book_held=("DBO",),
            pm_memo=self._memo_spy_long_only(),
        )
        out = _run(client, state)
        assert not out.get("errors"), out.get("errors")
        manifest = (out.get("phase_hermes") or PhaseHermesState()).commit_manifest or {}
        assert manifest.get("status") == "committed"

    def test_memo_flat_held_name_is_addressed_not_carried(self) -> None:
        """An explicit ``flat`` is memo-addressed: exits are honored, never resurrected."""
        from digiquant.olympus.hermes.writers.commit_io import carried_held_tickers

        client = FakeSupabaseClient()
        state = _state(
            sized_book={
                "recommended_portfolio": [{"ticker": "SPY", "target_pct": 100.0}],
                "actions": [],
                "notes": "",
            },
            analysts={"SPY": self._SPY_ANALYST},
            prior_book_held=("TLT",),
            pm_memo=PMDirectionMemo(
                date=RUN_DATE,
                roster=[
                    TickerDirection(ticker="SPY", direction="long", conviction_rank=1),
                    TickerDirection(ticker="TLT", direction="flat", conviction_rank=2),
                ],
            ),
        )
        assert "TLT" not in carried_held_tickers(state)
        out = _run(client, state)
        assert not out.get("errors"), out.get("errors")
        manifest = (out.get("phase_hermes") or PhaseHermesState()).commit_manifest or {}
        assert manifest.get("status") == "committed"

    def test_carried_set_is_held_only_and_sizing_carries_drifted_weight(self) -> None:
        """The carry set never widens beyond held names; H8 injects the drifted weight."""
        from digiquant.olympus.hermes.phases.phase7e_risk_sizing import _held_carry_weights
        from digiquant.olympus.hermes.writers.commit_io import carried_held_tickers

        state = _state(
            with_sized_book=False,
            analysts={"SPY": self._SPY_ANALYST},
            prior_book_held=("DBO",),
            pm_memo=self._memo_spy_long_only(),
        )
        state.config.preferences["current_weights"] = {"DBO": 12.5, "SPY": 60.0}
        assert carried_held_tickers(state) == {"DBO"}, "non-held names must never be carried"
        assert _held_carry_weights(state) == {"DBO": 12.5}


# ─── Authoritative commit chain (#2418, migration 069) ──────────────────────

_COMMITS = "portfolio_ledger_commits"
_INTENTS = "portfolio_ledger_decision_intents"
_REQUESTED = "portfolio_ledger_requested_targets"
_ADJUSTMENTS = "portfolio_ledger_target_adjustments"
_APPROVED = "portfolio_ledger_approved_targets"
_ORDERS = "portfolio_ledger_order_intents"
_EXECUTIONS = "portfolio_ledger_paper_executions"

# Adjustments may be empty on a commit with no H8 deltas — keep them out of the
# "every table must have rows" loops; they are mirrored for supersession reads.
_LEDGER_TABLES = (_COMMITS, _INTENTS, _REQUESTED, _APPROVED, _ORDERS)


def _ledger_client(**closes: float) -> FakeSupabaseClient:
    """Fake client with a priceable close for each ticker the day before ``RUN_DATE``.

    H9 converts a weight delta to a share count at the last close strictly before
    ``run_date`` (the same window ``_interval_price_returns`` uses), so a ticker
    with no row here is deliberately unpriceable.
    """
    prior = "2026-06-11"
    return FakeSupabaseClient(
        canned_reads={
            "price_history": [
                {"date": prior, "ticker": ticker, "close": close}
                for ticker, close in closes.items()
            ]
        }
    )


def _mirror_ledger(client: FakeSupabaseClient) -> None:
    """Make the rows a prior run wrote readable by the next run in the same test.

    The fake reads from ``canned_reads`` and writes to ``store`` (see the ``delete``
    docstring on ``_FakeQuery``), so a two-attempt supersession test has to bridge
    them by hand.
    """
    for table in (*_LEDGER_TABLES, _ADJUSTMENTS, _EXECUTIONS):
        client.canned_reads[table] = [dict(r) for r in client.store.get(table, [])]


def _rows(client: FakeSupabaseClient, table: str) -> list[dict]:
    return list(client.store.get(table, []))


def _heads(rows: list[dict]) -> list[dict]:
    """Rows nobody supersedes — the *current* rows.

    ``supersedes_id IS NULL`` is the permanent chain **root**, not the head: the
    ledger is append-only, so attempt 1's row keeps its NULL forever.
    """
    superseded = {r.get("supersedes_id") for r in rows if r.get("supersedes_id")}
    return [r for r in rows if r["id"] not in superseded]


def _assert_linear_chain(rows: list[dict], label: str) -> None:
    """The DB invariants the fake cannot enforce, asserted directly.

    ``FakeSupabaseClient`` has no partial unique indexes, no foreign keys and no
    append-only trigger, so every supersession test would pass against it even with
    the root/head confusion above. Assert the *shape* instead: exactly one root, no
    two rows superseding the same row, and one linear root→head chain covering
    every row.
    """
    roots = [r for r in rows if not r.get("supersedes_id")]
    assert len(roots) == 1, f"{label}: expected exactly one root, got {len(roots)}"
    links = [r["supersedes_id"] for r in rows if r.get("supersedes_id")]
    assert len(links) == len(set(links)), f"{label}: two rows supersede the same row"
    seen, cursor = 1, roots[0]["id"]
    by_prior = {r["supersedes_id"]: r for r in rows if r.get("supersedes_id")}
    while cursor in by_prior:
        cursor = by_prior[cursor]["id"]
        seen += 1
    assert seen == len(rows), f"{label}: chain covers {seen} of {len(rows)} rows"


class TestCommitChainLedger:
    """Task 2.3 — H9 appends the authoritative commit chain (#2418)."""

    def test_h9_appends_the_chain_for_every_final_ticker_and_cash(self) -> None:
        client = _ledger_client(SPY=100.0)
        out = _run(client, _state())
        assert not out.get("errors"), out.get("errors")

        symbols = {r["symbol"] for r in _rows(client, _APPROVED)}
        assert symbols == {"SPY", "CASH"}, "the cash residual must be queryable too"
        assert len(_rows(client, _COMMITS)) == 1
        assert {r["symbol"] for r in _rows(client, _INTENTS)} == {"SPY", "CASH"}
        assert {r["symbol"] for r in _rows(client, _REQUESTED)} == {"SPY", "CASH"}

        # CASH is a residual, never an order.
        assert [r["symbol"] for r in _rows(client, _ORDERS)] == ["SPY"]
        order = _rows(client, _ORDERS)[0]
        assert order["status"] == "pending"
        # nav 100 (seed), +100% of nav at a 100.0 close = 1 share.
        assert float(order["quantity"]) == pytest.approx(1.0)

        manifest = (out.get("phase_hermes") or PhaseHermesState()).commit_manifest or {}
        assert manifest["ledger_commit_id"] == _rows(client, _COMMITS)[0]["id"]

    def test_ledger_rows_are_inserted_never_upserted(self) -> None:
        # service_role holds SELECT + INSERT only on the 069 tables, and the
        # append-only trigger rejects UPDATE — an upsert would fail in production.
        client = _ledger_client(SPY=100.0)
        _run(client, _state())
        for table in _LEDGER_TABLES:
            rows = _rows(client, table)
            assert rows, f"{table} got no rows — the assertion below would be vacuous"
            for row in rows:
                assert "_on_conflict" not in row, f"{table} was written with upsert()"

    def test_h9_is_the_only_ledger_writer(self) -> None:
        import pathlib
        import subprocess

        root = pathlib.Path(__file__).resolve().parents[3]
        # ``append_commit_chain(`` — with the paren — matches the definition and every
        # call, but not a prose cross-reference in another module's docstring. Task 2.4's
        # ``execution_io`` legitimately names this function when explaining why its
        # supersession ids must be deterministic; that is documentation, not a second
        # commit authority, and a bare-name grep cannot tell the two apart.
        hits = subprocess.run(
            ["grep", "-rln", "append_commit_chain(", "--include=*.py", "digiquant/src"],
            cwd=root,
            capture_output=True,
            text=True,
        ).stdout.split()
        assert sorted(hits) == [
            "digiquant/src/digiquant/olympus/hermes/phases/h9_commit_run.py",
            "digiquant/src/digiquant/olympus/hermes/writers/ledger_io.py",
        ], f"a second commit authority appeared: {hits}"

    def test_identical_same_date_fingerprint_appends_nothing(self) -> None:
        client = _ledger_client(SPY=100.0)
        _run(client, _state())
        before = {t: len(_rows(client, t)) for t in _LEDGER_TABLES}
        assert before[_COMMITS] == 1, "attempt 1 wrote nothing — 0 == 0 proves no idempotency"
        _mirror_ledger(client)

        out = _run(client, _state(run_id=UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")))

        manifest = (out.get("phase_hermes") or PhaseHermesState()).commit_manifest or {}
        assert manifest.get("status") == "noop"
        assert {t: len(_rows(client, t)) for t in _LEDGER_TABLES} == before

    def test_changed_pre_fill_commit_supersedes_pending_orders(self) -> None:
        client = _ledger_client(SPY=100.0)
        _run(client, _state())
        _mirror_ledger(client)

        _run(
            client,
            _state(
                sized_book=_sized_book(spy_pct=50.0),
                run_id=UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff"),
            ),
        )

        commits = _rows(client, _COMMITS)
        assert len(commits) == 2
        _assert_linear_chain(commits, "commits")

        spy_targets = [r for r in _rows(client, _APPROVED) if r["symbol"] == "SPY"]
        _assert_linear_chain(spy_targets, "approved_targets/SPY")
        assert float(_heads(spy_targets)[0]["approved_weight"]) == pytest.approx(0.50)

        spy_orders = [r for r in _rows(client, _ORDERS) if r["symbol"] == "SPY"]
        assert len(spy_orders) == 2, "the changed commit must supersede the pending order"
        _assert_linear_chain(spy_orders, "order_intents/SPY")
        assert float(_heads(spy_orders)[0]["quantity"]) == pytest.approx(0.5)

    def test_existing_fill_freezes_the_symbol(self) -> None:
        client = _ledger_client(SPY=100.0)
        _run(client, _state())
        _mirror_ledger(client)

        # The executor records a fill by appending a terminal ``executed`` row that
        # supersedes the pending one — it cannot UPDATE the pending row in place.
        pending = _rows(client, _ORDERS)[0]
        filled_order_id = "11111111-2222-3333-4444-555555555555"
        client.canned_reads[_ORDERS] = [
            *client.canned_reads[_ORDERS],
            {
                **pending,
                "id": filled_order_id,
                "status": "executed",
                "supersedes_id": pending["id"],
            },
        ]
        client.canned_reads[_EXECUTIONS] = [
            {
                "id": "99999999-8888-7777-6666-555555555555",
                "order_intent_id": filled_order_id,
                "executed_date": "2026-06-15",
                "symbol": "SPY",
                "quantity": 1.0,
                "price": 100.0,
            }
        ]
        before = {t: len(_rows(client, t)) for t in _LEDGER_TABLES}

        out = _run(
            client,
            _state(
                sized_book=_sized_book(spy_pct=50.0),
                run_id=UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff"),
            ),
        )

        # The book still changed (CASH 0% -> 50%), so this is a real commit, not a noop.
        assert len(_rows(client, _COMMITS)) == before[_COMMITS] + 1

        # SPY is frozen: no *new* row in any table names it. Counting new rows per table
        # is what makes this falsifiable — slicing one table by another table's length
        # passes for the wrong reason.
        for table in (_INTENTS, _REQUESTED, _APPROVED, _ORDERS):
            fresh = [r for r in _rows(client, table)[before[table] :] if r["symbol"] == "SPY"]
            assert not fresh, f"{table}: a filled symbol was re-targeted — {fresh}"

        # 069's commits table has no ``frozen_symbols`` column (id, run_date,
        # policy_version_id, supersedes_id, effective_at, recorded_at) and
        # ``PortfolioCommit`` is extra="forbid" — so the skip is recorded where a reader
        # can see it, the manifest. Invariant 12: the gap must be visible, not silent.
        manifest = (out.get("phase_hermes") or PhaseHermesState()).commit_manifest or {}
        assert manifest["ledger_frozen_symbols"] == ["SPY"]

    def test_orphan_pruning_still_converges_with_the_ledger_on(self) -> None:
        client = _ledger_client(SPY=100.0)
        client.store["positions"] = [
            {"date": RUN_DATE.isoformat(), "ticker": "OLD", "weight_pct": 40.0}
        ]
        client.canned_reads["positions"] = [dict(r) for r in client.store["positions"]]

        _run(client, _state())

        tickers = {r["ticker"] for r in _rows(client, "positions")}
        assert "OLD" not in tickers, "legacy orphan pruning regressed"
        assert "SPY" in tickers

    def test_partial_ledger_failure_does_not_masquerade_as_committed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from digiquant.olympus.hermes.writers import ledger_io

        real_insert = ledger_io._insert

        def _fail_on_orders(*, client, table, rows):
            if table == _ORDERS:
                raise RuntimeError("ledger insert failed")
            return real_insert(client=client, table=table, rows=rows)

        monkeypatch.setattr(ledger_io, "_insert", _fail_on_orders)
        client = _ledger_client(SPY=100.0)

        with pytest.raises(RuntimeError, match="ledger insert failed"):
            _run(client, _state())

        # No manifest ⇒ the next attempt cannot short-circuit into "noop"; it
        # re-commits and supersedes instead of reporting a false success.
        assert not load_commit_manifests(client=client, run_date=RUN_DATE)
        assert _rows(client, _COMMITS), "the partial chain stays visible for triage"

    def test_kill_switch_keeps_legacy_projections_and_writes_no_ledger(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OLYMPUS_PORTFOLIO_LEDGER", "off")
        client = _ledger_client(SPY=100.0)

        out = _run(client, _state())

        assert not out.get("errors"), out.get("errors")
        assert all(not _rows(client, t) for t in _LEDGER_TABLES)
        assert not _rows(client, _ADJUSTMENTS)
        assert {r["ticker"] for r in _rows(client, "positions")} == {"SPY"}
        manifest = (out.get("phase_hermes") or PhaseHermesState()).commit_manifest or {}
        assert manifest.get("ledger_commit_id") is None


class TestTargetAdjustmentPersistence:
    """WP2 residual #2768 — durable requested→approved adjustment lineage."""

    def _book_with_cap(self) -> dict:
        return {
            "recommended_portfolio": [{"ticker": "SPY", "target_pct": 40.0}],
            "actions": [],
            "notes": "H8 sized with single-name cap",
            "requested_pct": {"SPY": 80.0},
            "adjustments": [
                {
                    "ticker": "SPY",
                    "adjustment_type": "single_name_cap",
                    "original_pct": 80.0,
                    "adjusted_pct": 40.0,
                    "unit": "pct",
                    "reason": "single-name cap 40%",
                }
            ],
        }

    def test_persists_target_adjustment_rows_keyed_to_requested_target(self) -> None:
        client = _ledger_client(SPY=100.0)
        _run(client, _state(sized_book=self._book_with_cap()))

        adjustments = _rows(client, _ADJUSTMENTS)
        assert len(adjustments) == 1
        row = adjustments[0]
        assert row["symbol"] == "SPY"
        assert row["adjustment_type"] == "single_name_cap"
        assert float(row["original_value"]) == pytest.approx(0.80)
        assert float(row["adjusted_value"]) == pytest.approx(0.40)
        assert row["reason"] == "single-name cap 40%"

        requested = {r["id"]: r for r in _rows(client, _REQUESTED)}
        assert row["requested_target_id"] in requested
        assert requested[row["requested_target_id"]]["symbol"] == "SPY"

    def test_requested_weight_reflects_pre_cap_intent(self) -> None:
        client = _ledger_client(SPY=100.0)
        _run(client, _state(sized_book=self._book_with_cap()))

        spy_requested = next(r for r in _rows(client, _REQUESTED) if r["symbol"] == "SPY")
        spy_approved = next(r for r in _rows(client, _APPROVED) if r["symbol"] == "SPY")
        assert float(spy_requested["requested_weight"]) == pytest.approx(0.80)
        assert float(spy_approved["approved_weight"]) == pytest.approx(0.40)
        assert spy_approved["requested_target_id"] == spy_requested["id"]

    def test_conviction_unit_adjustments_are_not_persisted_as_weight_rows(self) -> None:
        book = {
            "recommended_portfolio": [{"ticker": "SPY", "target_pct": 50.0}],
            "actions": [],
            "notes": "conviction floor only",
            "requested_pct": {"SPY": 50.0},
            "adjustments": [
                {
                    "ticker": "SPY",
                    "adjustment_type": "conviction_floor",
                    "original_pct": 0.9,
                    "adjusted_pct": 0.55,
                    "unit": "conviction",
                    "reason": "unchallenged conviction floor",
                }
            ],
        }
        client = _ledger_client(SPY=100.0)
        _run(client, _state(sized_book=book))
        assert not _rows(client, _ADJUSTMENTS)

    def test_no_unexplained_durable_delta_when_adjustments_cover_request(self) -> None:
        """Every material requested≠approved symbol must carry ≥1 adjustment row."""
        client = _ledger_client(SPY=100.0, AAPL=50.0)
        book = {
            "recommended_portfolio": [
                {"ticker": "SPY", "target_pct": 30.0},
                {"ticker": "AAPL", "target_pct": 20.0},
            ],
            "actions": [],
            "notes": "two capped names",
            "requested_pct": {"SPY": 60.0, "AAPL": 40.0},
            "adjustments": [
                {
                    "ticker": "SPY",
                    "adjustment_type": "single_name_cap",
                    "original_pct": 60.0,
                    "adjusted_pct": 30.0,
                    "unit": "pct",
                    "reason": "single-name cap",
                },
                {
                    "ticker": "AAPL",
                    "adjustment_type": "sector_cap",
                    "original_pct": 40.0,
                    "adjusted_pct": 20.0,
                    "unit": "pct",
                    "reason": "sector cap",
                },
            ],
        }
        _run(client, _state(sized_book=book, analysts=_multi_analysts("SPY", "AAPL")))

        by_symbol: dict[str, list[dict]] = {}
        for row in _rows(client, _ADJUSTMENTS):
            by_symbol.setdefault(row["symbol"], []).append(row)

        for req in _rows(client, _REQUESTED):
            if req["symbol"] == "CASH":
                continue
            approved = next(
                r for r in _rows(client, _APPROVED) if r["requested_target_id"] == req["id"]
            )
            req_w = float(req["requested_weight"])
            appr_w = float(approved["approved_weight"])
            if abs(req_w - appr_w) <= 1e-9:
                continue
            assert by_symbol.get(req["symbol"]), (
                f"{req['symbol']}: requested={req_w} approved={appr_w} with no "
                "TargetAdjustment row — durable delta unexplained"
            )


class TestLedgerIoMutationPins:
    """Close the surviving ``ledger_io`` mutations from the #2482 / #2487 review.

    Shape tests already cover chain linearity and insert-not-upsert. These pins lock
    *arithmetic and window semantics* that mutation testing showed were unguarded:
    look-ahead closes, prior-book share deltas, freeze-signal independence, fork
    refusal, and unpriced diagnostics.
    """

    def test_last_close_is_strictly_before_run_date_not_inclusive(self) -> None:
        """M16 — ``.lt(date)`` must not become ``.lte(date)`` (look-ahead)."""
        rows = [
            {"date": "2026-06-10", "ticker": "SPY", "close": 50.0},
            {"date": "2026-06-11", "ticker": "SPY", "close": 80.0},
            # Same calendar day as RUN_DATE — must never price the order.
            {"date": RUN_DATE.isoformat(), "ticker": "SPY", "close": 999.0},
        ]
        closes = _last_closes(
            client=FakeSupabaseClient(canned_reads={"price_history": rows}),
            tickers={"SPY"},
            run_date=RUN_DATE,
        )
        assert closes == {"SPY": 80.0}, (
            f"look-ahead close leaked into pricing: got {closes} "
            "(inclusive .lte would pick 999.0 on run_date)"
        )

    def test_last_close_picks_newest_in_lookback_not_oldest(self) -> None:
        """M15 — reduction must keep the latest close, not the first seen."""
        rows = [
            {"date": "2026-06-01", "ticker": "SPY", "close": 10.0},
            {"date": "2026-06-05", "ticker": "SPY", "close": 40.0},
            {"date": "2026-06-11", "ticker": "SPY", "close": 80.0},
        ]
        closes = _last_closes(
            client=FakeSupabaseClient(canned_reads={"price_history": rows}),
            tickers={"SPY"},
            run_date=RUN_DATE,
        )
        assert closes == {"SPY": 80.0}, f"oldest-or-mid close won: {closes}"

    def test_share_quantity_is_exact_delta_against_prior_book(self) -> None:
        """M1 / M23 / M24 / M26 — delta uses prior weight; nav and close must differ.

        prior SPY 40% → target 60% at nav=100, close=50 → |20%| * 100 / 50 = 0.4 shares.
        Ignoring prior (target-only) would emit 1.2; inverting nav/close would emit 10.
        """
        client = _ledger_client(SPY=50.0)
        out = _run(
            client,
            _state(
                sized_book=_sized_book(spy_pct=60.0),
                preferences={"current_weights": {"SPY": 40.0}},
            ),
        )
        assert not out.get("errors"), out.get("errors")
        orders = [r for r in _rows(client, _ORDERS) if r["symbol"] == "SPY"]
        assert len(orders) == 1, orders
        assert float(orders[0]["quantity"]) == pytest.approx(0.4)

    def test_prior_held_exit_emits_order_and_exit_decision(self) -> None:
        """M24 — prior-held symbols must stay in the row set so exits are explicit."""
        client = _ledger_client(SPY=50.0, MSFT=25.0)
        _run(
            client,
            _state(
                sized_book=_sized_book(spy_pct=60.0),
                analysts=_multi_analysts("SPY"),
                preferences={"current_weights": {"SPY": 40.0, "MSFT": 25.0}},
            ),
        )
        by_symbol = {r["symbol"]: r for r in _rows(client, _INTENTS)}
        assert by_symbol["MSFT"]["action"] == "exit"
        assert by_symbol["MSFT"]["reason"] == "thesis_invalidated"
        msft_orders = [r for r in _rows(client, _ORDERS) if r["symbol"] == "MSFT"]
        assert len(msft_orders) == 1
        # |0 - 25%| * nav 100 / close 25 = 1.0 share
        assert float(msft_orders[0]["quantity"]) == pytest.approx(1.0)

    def test_decision_mapping_is_not_collapsed_to_add(self) -> None:
        """M2 — trim / exit / cash no-op must not all become ADD/NEW_CONVICTION."""
        client = _ledger_client(SPY=50.0, AAPL=20.0, MSFT=25.0)
        _run(
            client,
            _state(
                sized_book=_multi_book(SPY=30.0, AAPL=20.0),
                analysts=_multi_analysts("SPY", "AAPL"),
                preferences={"current_weights": {"SPY": 50.0, "MSFT": 10.0}},
            ),
        )
        by_symbol = {r["symbol"]: (r["action"], r["reason"]) for r in _rows(client, _INTENTS)}
        assert by_symbol["SPY"] == ("trim", "conviction_reduced")
        assert by_symbol["AAPL"] == ("add", "new_conviction")
        assert by_symbol["MSFT"] == ("exit", "thesis_invalidated")
        assert by_symbol["CASH"] == ("no_op", "no_signal_change")

    def test_heads_are_found_by_exclusion_not_null_supersedes(self) -> None:
        """M5 — ``supersedes_id IS NULL`` is the permanent root, not the live head."""
        root = {"id": "root", "supersedes_id": None, "status": "pending"}
        tip = {"id": "tip", "supersedes_id": "root", "status": "pending"}
        assert _ledger_heads([root, tip]) == [tip]
        assert _ledger_heads([root]) == [root]

    def test_executed_order_head_alone_freezes_symbol(self) -> None:
        """M13 — freeze signal 1 (executed head) without a paper_executions row."""
        client = _ledger_client(SPY=100.0)
        _run(client, _state())
        _mirror_ledger(client)
        pending = _rows(client, _ORDERS)[0]
        filled_id = "11111111-2222-3333-4444-555555555555"
        client.canned_reads[_ORDERS] = [
            *client.canned_reads[_ORDERS],
            {**pending, "id": filled_id, "status": "executed", "supersedes_id": pending["id"]},
        ]
        client.canned_reads[_EXECUTIONS] = []
        frozen = _frozen_symbols(client=client, order_rows=list(client.canned_reads[_ORDERS]))
        assert frozen == {"SPY"}

    def test_paper_execution_alone_freezes_symbol(self) -> None:
        """M14 — freeze signal 2 (fill row) without flipping the order head to executed."""
        client = _ledger_client(SPY=100.0)
        _run(client, _state())
        _mirror_ledger(client)
        pending = _rows(client, _ORDERS)[0]
        client.canned_reads[_EXECUTIONS] = [
            {
                "id": "99999999-8888-7777-6666-555555555555",
                "order_intent_id": pending["id"],
                "executed_date": "2026-06-15",
                "symbol": "SPY",
                "quantity": 1.0,
                "price": 100.0,
            }
        ]
        frozen = _frozen_symbols(client=client, order_rows=list(client.canned_reads[_ORDERS]))
        assert frozen == {"SPY"}

    def test_unpriced_symbols_surface_on_the_manifest(self) -> None:
        """M28 — partial pricing must be visible, not silent."""
        client = _ledger_client(SPY=50.0)  # AAPL deliberately missing
        out = _run(
            client,
            _state(
                sized_book=_multi_book(SPY=40.0, AAPL=20.0),
                analysts=_multi_analysts("SPY", "AAPL"),
            ),
        )
        assert not out.get("errors"), out.get("errors")
        manifest = (out.get("phase_hermes") or PhaseHermesState()).commit_manifest or {}
        assert manifest.get("ledger_unpriced_symbols") == ["AAPL"]
        assert [r["symbol"] for r in _rows(client, _ORDERS)] == ["SPY"]
        assert {r["symbol"] for r in _rows(client, _APPROVED)} >= {"SPY", "AAPL", "CASH"}

    def test_multi_head_commit_fork_raises(self) -> None:
        """M29 — two live commit heads for one run_date must fail closed."""
        client = _ledger_client(SPY=50.0)
        client.canned_reads[_COMMITS] = [
            {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "run_date": RUN_DATE.isoformat(),
                "policy_version_id": "hermes-h8-sizing/x/deadbeef0001",
                "supersedes_id": None,
                "effective_at": "2026-06-12T00:00:00+00:00",
                "recorded_at": "2026-06-12T01:00:00+00:00",
            },
            {
                "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "run_date": RUN_DATE.isoformat(),
                "policy_version_id": "hermes-h8-sizing/x/deadbeef0002",
                "supersedes_id": None,
                "effective_at": "2026-06-12T00:00:00+00:00",
                "recorded_at": "2026-06-12T02:00:00+00:00",
            },
        ]
        with pytest.raises(RuntimeError, match="forked"):
            _run(client, _state(sized_book=_sized_book(spy_pct=60.0)))

    def test_effective_at_is_run_date_midnight_utc(self) -> None:
        """M7 — lineage effective time is the run date, not wall clock + drift."""
        client = _ledger_client(SPY=50.0)
        _run(client, _state(sized_book=_sized_book(spy_pct=60.0)))
        commit = _rows(client, _COMMITS)[0]
        assert commit["effective_at"].startswith("2026-06-12T00:00:00")


_MIGRATION_069 = (
    pathlib.Path(__file__).resolve().parents[3]
    / "digiquant"
    / "supabase"
    / "migrations"
    / "069_olympus_portfolio_ledger.sql"
)


def _migration_sql() -> str:
    raw = _MIGRATION_069.read_text(encoding="utf-8")
    return "\n".join(re.sub(r"--.*$", "", line) for line in raw.split("\n"))


def _table_body(sql: str, table: str) -> str:
    match = re.search(rf"CREATE TABLE IF NOT EXISTS public\.{table} \((.*?)\n\);", sql, re.S)
    assert match, f"table {table} not found in migration 069"
    return match.group(1)


def _allowed_values(sql: str, table: str, column: str) -> set[str]:
    """The closed vocabulary migration 069 actually permits for one column."""
    body = _table_body(sql, table)
    match = re.search(rf"{column} text NOT NULL CHECK \(\s*{column} IN \(([^)]*)\)", body, re.S)
    assert match, f"no closed CHECK found for {table}.{column}"
    values = set(re.findall(r"'([^']+)'", match.group(1)))
    assert values, f"parsed an empty vocabulary for {table}.{column}"
    return values


def _allowed_action_reason_pairs(sql: str) -> set[tuple[str, str]]:
    body = _table_body(sql, "portfolio_ledger_decision_intents")
    match = re.search(
        r"chk_portfolio_ledger_decision_intents_action_reason\s*CHECK \((.*)", body, re.S
    )
    assert match, "the action/reason pairing CHECK is gone"
    pairs: set[tuple[str, str]] = set()
    for action, single, group in re.findall(
        r"action = '(\w+)'\s+AND reason (?:= '(\w+)'|IN \(([^)]*)\))", match.group(1), re.S
    ):
        for reason in [single] if single else re.findall(r"'([^']+)'", group):
            pairs.add((action, reason))
    assert pairs, "parsed no action/reason pairs"
    return pairs


def _multi_book(**target_pcts: float) -> dict:
    return {
        "recommended_portfolio": [
            {"ticker": t, "target_pct": pct} for t, pct in target_pcts.items()
        ],
        "actions": [],
        "notes": "H8 sized book",
    }


def _multi_analysts(*tickers: str) -> dict:
    # coherence_errors fails closed on an open position with no H5 doc, so a
    # multi-ticker book needs one per name or H9 writes nothing at all.
    return {
        t: {
            "ticker": t,
            "stance": "buy",
            "conviction_score": 4,
            "thesis": "risk-on",
            "risks": "",
            "sources": [],
        }
        for t in tickers
    }


class TestLedgerRowsSatisfyMigration069:
    """Guard the seam between migration 069's CHECKs and the models that mirror them.

    The models in ``hermes.models.portfolio_ledger`` hand-mirror this DDL:
    ``Weight`` repeats ``BETWEEN 0 AND 1``, ``Symbol`` repeats ``length(symbol)
    BETWEEN 1 AND 20``, ``_ACTION_REASONS`` repeats the action/reason pairing CHECK.
    A mirror can drift **loose** — widen the Python side, or narrow the SQL side
    without it, and the model accepts a row Postgres answers with a 23514. Neither
    existing suite sees that: ``tests/dq/atlas/test_migration_069.py`` reads the DDL
    but no Python, and ``tests/dq/hermes/test_portfolio_ledger.py`` checks the models
    against their own literals. The failure would land in the nightly pipeline after
    promotion rather than on the PR, which is how this class of bug reached production
    three times already (#628, #1005, #1383).

    So parse the vocabularies out of migration 069 itself and assert the emitted rows
    satisfy them — parsed, not transcribed, so narrowing a CHECK fails these tests
    instead of silently outdating them. Confirmed by mutation: loosening ``Weight`` to
    ``le=100`` *and* dropping the writer's ``/100.0`` leaves 48 of the 50 tests in this
    file green; ``test_weight_columns_stay_inside_the_zero_to_one_domain`` is the direct
    catch, and ``test_changed_pre_fill_commit_supersedes_pending_orders`` fails with it. Mutating only the writer proves nothing — the models reject it first.

    ``test_emitted_columns_all_exist_in_the_migration`` covers the one thing no
    validator can: ``extra="forbid"`` guards what a caller passes *into* a model, not
    a model field with no column behind it, which is a PostgREST 400 rather than a
    CHECK violation.
    """

    def test_emitted_columns_all_exist_in_the_migration(self) -> None:
        # A key the table lacks is a PostgREST 400, not a CHECK violation.
        sql = _migration_sql()
        client = _ledger_client(SPY=100.0)
        _run(client, _state())
        for table in _LEDGER_TABLES:
            columns = set(
                re.findall(
                    r"^\s{4}([a-z_]+) (?:uuid|date|text|numeric|timestamptz)",
                    _table_body(sql, table),
                    re.M,
                )
            )
            assert columns, f"parsed no columns for {table}"
            rows = _rows(client, table)
            assert rows, f"{table} got no rows — the assertion below would be vacuous"
            for row in rows:
                unknown = set(row) - columns
                assert not unknown, f"{table} row carries column(s) the table lacks: {unknown}"

    def test_closed_vocabulary_columns_only_emit_permitted_values(self) -> None:
        sql = _migration_sql()
        client = _ledger_client(SPY=100.0, AAPL=50.0)
        _run(
            client,
            _state(
                sized_book=_multi_book(SPY=60.0, AAPL=30.0),
                analysts=_multi_analysts("SPY", "AAPL"),
            ),
        )
        for table, column in (
            (_INTENTS, "action"),
            (_INTENTS, "reason"),
            (_ORDERS, "status"),
        ):
            allowed = _allowed_values(sql, table, column)
            emitted = {r[column] for r in _rows(client, table)}
            assert emitted, f"no {table}.{column} values emitted — assertion would be vacuous"
            extra = emitted - allowed
            assert not extra, f"{table}.{column} emitted {extra}; DB allows {allowed}"

    def test_action_reason_pairs_are_permitted_by_the_pairing_check(self) -> None:
        # reason is legal and action is legal does not imply the PAIR is: the pairing
        # CHECK is a second axis, and an earlier read of this vocabulary was wrong.
        allowed = _allowed_action_reason_pairs(_migration_sql())
        client = _ledger_client(SPY=100.0, AAPL=50.0, MSFT=25.0)
        # exercise trim / add / exit / no_op together: SPY trimmed from 70, AAPL added
        # from nothing, MSFT held then dropped to zero, CASH the residual no_op.
        _run(
            client,
            _state(
                sized_book=_multi_book(SPY=40.0, AAPL=20.0),
                analysts=_multi_analysts("SPY", "AAPL"),
                preferences={"current_weights": {"SPY": 70.0, "MSFT": 10.0}},
            ),
        )
        emitted = {(r["action"], r["reason"]) for r in _rows(client, _INTENTS)}
        assert len(emitted) >= 2, f"only {emitted} — too uniform to prove the pairing holds"
        assert emitted <= allowed, f"illegal action/reason pair(s): {emitted - allowed}"

    def test_weight_columns_stay_inside_the_zero_to_one_domain(self) -> None:
        # H8's book is in percent; the DDL stores a [0, 1] fraction. A missed
        # conversion passes every fake-client test and 23514s on the first real run.
        client = _ledger_client(SPY=100.0, AAPL=50.0)
        _run(
            client,
            _state(
                sized_book=_multi_book(SPY=60.0, AAPL=30.0),
                analysts=_multi_analysts("SPY", "AAPL"),
            ),
        )
        for table, column in ((_REQUESTED, "requested_weight"), (_APPROVED, "approved_weight")):
            values = [r[column] for r in _rows(client, table) if r[column] is not None]
            assert values, f"no {table}.{column} values emitted"
            for value in values:
                number = float(value)
                assert number == number, f"{table}.{column} emitted NaN"
                infinite = number in (float("inf"), float("-inf"))
                assert not infinite, f"{table}.{column} emitted infinity"
                assert 0.0 <= number <= 1.0, f"{table}.{column}={number} violates BETWEEN 0 AND 1"

    def test_requested_targets_satisfy_the_exclusive_or_presence_check(self) -> None:
        client = _ledger_client(SPY=100.0)
        _run(client, _state())
        rows = _rows(client, _REQUESTED)
        assert rows, "no requested_targets emitted"
        for row in rows:
            has_weight = row["requested_weight"] is not None
            has_quantity = row["requested_quantity"] is not None
            assert has_weight != has_quantity, f"XOR presence CHECK violated by {row}"

    def test_order_rows_satisfy_the_quantity_and_rejection_checks(self) -> None:
        client = _ledger_client(SPY=100.0, AAPL=50.0)
        _run(
            client,
            _state(
                sized_book=_multi_book(SPY=60.0, AAPL=30.0),
                analysts=_multi_analysts("SPY", "AAPL"),
            ),
        )
        rows = _rows(client, _ORDERS)
        assert rows, "no order_intents emitted"
        for row in rows:
            quantity = float(row["quantity"])
            # ``_shares`` quantizes and drops non-positive quantities before insert, so
            # a zero row never reaches this loop — the > 0 assert guards NaN/leak paths
            # and documents the DDL CHECK rather than proving the drop branch.
            assert quantity > 0, f"quantity {quantity} violates the > 0 CHECK"
            assert quantity == quantity and quantity != float("inf"), "quantity is NaN/infinity"
            if row["status"] == "rejected":
                assert row["rejection_reason"] is not None, "rejected row needs a reason"
            else:
                assert row["rejection_reason"] is None, f"{row['status']} row carries a reason"

    def test_symbols_fit_the_length_check(self) -> None:
        # Guards the CASH sentinel too: a rename to something longer 23514s.
        client = _ledger_client(SPY=100.0)
        _run(client, _state())
        for table in (_INTENTS, _REQUESTED, _APPROVED, _ORDERS):
            symbols = {r["symbol"] for r in _rows(client, table)}
            assert symbols, f"no symbols emitted for {table}"
            for symbol in symbols:
                assert 1 <= len(symbol) <= 20, f"{table} symbol {symbol!r} breaks length CHECK"


class TestPriceReadRowCap:
    """Regression (CodeRabbit, PR #2482): the last-close read must not depend on an
    unbounded response.

    ``price_history`` holds one row per *calendar* day per ticker — migration 013
    forward-fills weekends and holidays from the prior close — so a
    ``_CLOSE_LOOKBACK_DAYS``-day lookback with ``.gte(floor)`` + ``.lt(run_date)``
    yields up to ``_CLOSE_LOOKBACK_DAYS`` rows per ticker (14 when lookback is 14),
    while Supabase truncates an unbounded PostgREST response at 1000 rows. A
    truncated ticker is indistinguishable from an unpriced one: it lands in
    ``unpriced_symbols`` and its committed target books no order intent at all.
    Silent, and it only appears once the universe grows.
    """

    CAP = 1000

    def _capped_client(self, tickers: list[str]) -> FakeSupabaseClient:
        """Canned history for ``tickers``, served through Supabase's row cap."""
        rows = [
            {
                "date": (RUN_DATE - timedelta(days=offset)).isoformat(),
                "ticker": ticker,
                "close": 100.0 + index,
            }
            for index, ticker in enumerate(tickers)
            for offset in range(1, _CLOSE_LOOKBACK_DAYS + 1)
        ]
        cap = self.CAP

        class _Capped(FakeSupabaseClient):
            def table(self, name: str):  # type: ignore[no-untyped-def]
                query = super().table(name)
                if name != "price_history":
                    return query
                inner = query.execute

                def _execute():  # type: ignore[no-untyped-def]
                    resp = inner()
                    resp.data = list(resp.data or [])[:cap]
                    return resp

                query.execute = _execute  # type: ignore[method-assign]
                return query

        return _Capped(canned_reads={"price_history": rows})

    def test_wide_universe_is_fully_priced_under_the_row_cap(self) -> None:
        # 80 tickers x 14 rows = 1120: a single unbatched request loses the tail.
        tickers = [f"TK{index:03d}" for index in range(80)]
        assert len(tickers) * _CLOSE_LOOKBACK_DAYS > self.CAP, "universe must exceed the cap"
        closes = _last_closes(
            client=self._capped_client(tickers), tickers=set(tickers), run_date=RUN_DATE
        )
        missing = sorted(set(tickers) - set(closes))
        assert not missing, (
            f"{len(missing)} ticker(s) lost to the row cap ({missing[:5]}...) — "
            "a truncated read is reported as unpriced and books no order intent"
        )

    def test_batch_is_derived_from_the_lookback(self) -> None:
        """Widening the window must not silently reintroduce truncation."""
        worst_case = _CLOSE_TICKER_BATCH * (_CLOSE_LOOKBACK_DAYS + 1)
        assert worst_case <= self.CAP, (
            f"a full batch can return {worst_case} rows, over the {self.CAP} cap"
        )


class TestForecastRegistryInH9:
    """WP4.6 (#2663): H9 persists forecast lineage after booking; failure cannot rebook."""

    def _assessment_payload(self) -> dict:
        from datetime import UTC, datetime
        from decimal import Decimal

        from digiquant.olympus.hermes.models.forecast import (
            ForecastAssessment,
            ForecastTerms,
            PriceAnchor,
            PriceAnchorStatus,
            RawUncertainty,
            forecast_assessment_id,
            forecast_terms_content_hash,
        )

        ts = datetime(2026, 6, 12, 15, 0, tzinfo=UTC)
        terms = ForecastTerms(
            horizon_sessions=21,
            half_life_sessions=10,
            bear_return=Decimal("-0.10"),
            base_return=Decimal("0.04"),
            bull_return=Decimal("0.15"),
            bear_probability=Decimal("0.25"),
            base_probability=Decimal("0.50"),
            bull_probability=Decimal("0.25"),
            thesis_valid_probability=Decimal("0.60"),
            raw_uncertainty=RawUncertainty.MEDIUM,
        )
        ch = forecast_terms_content_hash(terms)
        run = str(_SOURCE_RUN_ID)
        assessment = ForecastAssessment(
            forecast_id=forecast_assessment_id(ticker="SPY", source_run_id=run, content_hash=ch),
            ticker="SPY",
            terms=terms,
            source_run_id=run,
            provider_invocation_id="inv-h9",
            prompt_version="pv-1",
            artifact_version="av-1",
            price_anchor=PriceAnchor(
                status=PriceAnchorStatus.OBSERVED,
                price=Decimal("100"),
                observed_at=ts,
            ),
            effective_at=ts,
            known_at=ts,
            content_hash=ch,
        )
        return assessment.model_dump(mode="json")

    def test_books_once_and_persists_assessment(self) -> None:
        from tests.dq.atlas.test_forecast_registry import RegistryFake

        client = RegistryFake()
        state = _state(
            analysts={
                "SPY": {
                    "ticker": "SPY",
                    "stance": "buy",
                    "conviction_score": 4,
                    "thesis": "risk-on",
                    "risks": "",
                    "sources": [],
                    "forecast_assessment": self._assessment_payload(),
                }
            }
        )
        out = _run(client, state)
        manifest = out["phase_hermes"].commit_manifest
        assert manifest["status"] == "committed"
        assert manifest["forecast_registry_status"] == "ok"
        assert manifest["forecast_registry_assessments_written"] == 1
        assert len(client.store.get("olympus_forecast_assessments", [])) == 1
        assert len(client.store.get("positions", [])) >= 1

    def test_registry_failure_keeps_book_and_does_not_rebook(self, monkeypatch) -> None:
        from digiquant.olympus.hermes.phases import h9_commit_run as h9

        client = FakeSupabaseClient()
        state = _state(
            analysts={
                "SPY": {
                    "ticker": "SPY",
                    "stance": "buy",
                    "conviction_score": 4,
                    "thesis": "risk-on",
                    "risks": "",
                    "sources": [],
                    "forecast_assessment": self._assessment_payload(),
                }
            }
        )

        def boom(**_k):
            raise RuntimeError("registry down")

        monkeypatch.setattr(h9, "persist_forecast_lineage_from_state", boom)
        out = _run(client, state)
        manifest = out["phase_hermes"].commit_manifest
        assert manifest["status"] == "committed"
        assert manifest["forecast_registry_status"] == "degraded"
        positions_after = list(client.store.get("positions", []))
        assert positions_after, "book must remain after registry failure"

        # Re-run same book: noop path — must not create a second book.
        out2 = _run(client, state)
        assert out2["phase_hermes"].commit_manifest["status"] == "noop"
        assert len(client.store.get("positions", [])) == len(positions_after)


class TestRiskPolicyRegistryH9:
    def test_books_once_and_persists_h8_risk_snapshots(self) -> None:
        from datetime import UTC, datetime

        import polars as pl
        from digiquant.olympus.hermes.h8_risk_snapshots import resolve_h8_risk_artifacts

        from tests.dq.atlas.test_risk_policy_registry import RiskRegistryFake

        client = RiskRegistryFake()
        state = _state()
        bundle = resolve_h8_risk_artifacts(
            state=state,
            pm_tickers=["SPY"],
            corr=pl.DataFrame({"a": ["SPY"], "b": ["SPY"], "corr": [1.0]}),
        )
        state.phase_hermes = state.phase_hermes.model_copy(
            update={
                "risk_policy": bundle.policy.model_dump(mode="json"),
                "covariance_snapshot": bundle.covariance_snapshot.model_dump(mode="json"),
            }
        )
        state.knowledge_cutoff_at = datetime(2026, 6, 12, 21, 0, tzinfo=UTC)
        out = _run(client, state)
        manifest = out["phase_hermes"].commit_manifest
        assert manifest["status"] == "committed"
        assert manifest["schema_version"] == "1.6"
        assert manifest["risk_policy_registry_status"] == "ok"
        assert manifest["risk_policy_registry_run_refs_written"] == 1
        assert len(client.store.get("olympus_h8_risk_run_refs", [])) == 1

    def test_risk_registry_failure_keeps_book(self, monkeypatch) -> None:
        from digiquant.olympus.hermes.phases import h9_commit_run as h9

        client = FakeSupabaseClient()
        state = _state()

        def boom(**_k):
            raise RuntimeError("risk registry down")

        monkeypatch.setattr(h9, "persist_h8_risk_snapshots_from_state", boom)
        out = _run(client, state)
        manifest = out["phase_hermes"].commit_manifest
        assert manifest["status"] == "committed"
        assert manifest["risk_policy_registry_status"] == "degraded"
        assert client.store.get("positions", [])


class TestCostLiquidityRegistryH9Noop:
    """WP7 follow-up #2807 — fingerprint-noop must retry cost with prior ledger id."""

    def test_fingerprint_noop_retries_cost_with_prior_ledger_commit_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from digiquant.olympus.hermes.phases import h9_commit_run as h9
        from digiquant.olympus.hermes.writers.ledger_io import LedgerAppend

        client = _ledger_client(SPY=100.0)
        state = _state()
        captured: list[LedgerAppend | None] = []
        real = h9._persist_cost_liquidity_registry

        def wrap(*, client, state, ledger):  # type: ignore[no-untyped-def]
            captured.append(ledger)
            return real(client=client, state=state, ledger=ledger)

        monkeypatch.setattr(h9, "_persist_cost_liquidity_registry", wrap)
        out1 = _run(client, state)
        manifest1 = out1["phase_hermes"].commit_manifest
        assert manifest1["status"] == "committed"
        commit_id = manifest1.get("ledger_commit_id")
        assert commit_id, "first commit must mint ledger_commit_id for noop retry"
        assert captured and captured[0] is not None
        assert captured[0].commit_id == commit_id

        out2 = _run(client, state)
        manifest2 = out2["phase_hermes"].commit_manifest
        assert manifest2["status"] == "noop"
        assert len(captured) >= 2
        noop_ledger = captured[-1]
        assert noop_ledger is not None, "noop must not pass ledger=None when prior commit exists"
        assert noop_ledger.commit_id == commit_id
        assert manifest2.get("cost_liquidity_registry_reason") != "ledger_disabled"

    def test_noop_without_prior_ledger_commit_id_stays_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from digiquant.olympus.hermes.phases import h9_commit_run as h9
        from digiquant.olympus.hermes.writers.commit_io import (
            weights_fingerprint,
            weights_from_sized_book,
        )

        client = FakeSupabaseClient()
        state = _state()
        book = state.phase_hermes.sized_book
        assert book is not None
        weights = weights_from_sized_book(book)
        fp = weights_fingerprint(weights)
        monkeypatch.setattr(
            h9,
            "load_commit_manifests",
            lambda **_k: [
                {
                    "schema_version": "1.1",
                    "status": "committed",
                    "weights_fingerprint": fp,
                    "weights": {k: round(v, 4) for k, v in sorted(weights.items())},
                    "nav": 100.0,
                    "decision_log_rows": 0,
                    "commit_seq": 1,
                    # Pre-1.2 / ledger-off manifests have no ledger_commit_id.
                }
            ],
        )
        captured: list[object] = []

        def wrap(*, client, state, ledger):  # type: ignore[no-untyped-def]
            captured.append(ledger)
            return (
                {
                    "cost_liquidity_registry_status": "skipped",
                    "cost_liquidity_registry_reason": "ledger_disabled",
                    "cost_liquidity_registry_snapshots_written": 0,
                    "cost_liquidity_registry_estimates_written": 0,
                },
                {},
                {},
            )

        monkeypatch.setattr(h9, "_persist_cost_liquidity_registry", wrap)
        out = _run(client, state)
        assert out["phase_hermes"].commit_manifest["status"] == "noop"
        assert captured == [None]


class TestPreTradeRiskH9:
    """WP9.4 — H9 hash validation + append-only PreTradeRiskReport persistence (#2754)."""

    def _spy_report_payload(self, *, run_id: str = str(_SOURCE_RUN_ID)) -> dict:
        from digiquant.olympus.hermes.pretrade_risk import (
            PreTradeRiskBuildRequest,
            build_pretrade_risk_report,
        )

        report = build_pretrade_risk_report(
            PreTradeRiskBuildRequest(
                run_id=run_id,
                session_date=RUN_DATE,
                allocation_input_bundle_hash="a" * 64,
                risk_policy_hash="b" * 64,
                prior_risky_weights_pct={},
                prior_cash_weight_pct=100.0,
                final_risky_weights_pct={"SPY": 100.0},
                final_cash_weight_pct=0.0,
            )
        )
        return report.model_dump(mode="json")

    def _state_with_report(self, report: dict | None = None) -> AtlasResearchState:
        state = _state()
        payload = report if report is not None else self._spy_report_payload()
        book = dict(state.phase_hermes.sized_book or {})
        book["pre_trade_risk_report_hash"] = payload["report_content_hash"]
        book["allocation_input_bundle_hash"] = payload["allocation_input_bundle_hash"]
        state.phase_hermes = state.phase_hermes.model_copy(
            update={
                "sized_book": book,
                "pre_trade_risk_report": payload,
            }
        )
        return state

    def _merging_client(self) -> FakeSupabaseClient:
        from dataclasses import dataclass
        from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes

        from digiquant.olympus.atlas import pretrade_risk_registry as ptr

        from tests.dq.atlas.test_supabase_io import _FakeQuery, _FakeResponse

        @dataclass
        class _MergingQuery(_FakeQuery):
            def execute(self) -> _FakeResponse:
                if self._insert_rows is not None:
                    self.store.setdefault(self.table_name, []).extend(self._insert_rows)
                    return _FakeResponse(data=[dict(row) for row in self._insert_rows])
                if self._upsert_row is not None:
                    if self.table_name == ptr.REPORTS:
                        raise AssertionError("upsert is forbidden on pretrade risk reports")
                    rows = (
                        self._upsert_row
                        if isinstance(self._upsert_row, list)
                        else [self._upsert_row]
                    )
                    self.store.setdefault(self.table_name, []).extend(rows)
                    return _FakeResponse(data=[dict(row) for row in rows])
                if self._update_row is not None:
                    if self.table_name == ptr.REPORTS:
                        raise AssertionError("update is forbidden on pretrade risk reports")
                    updated: list[dict[str, Any]] = []
                    for row in self.store.get(self.table_name, []):
                        if self._matches(row):
                            row.update(self._update_row)
                            updated.append(row)
                    return _FakeResponse(data=updated)
                if self._delete:
                    if self.table_name == ptr.REPORTS:
                        raise AssertionError("delete is forbidden on pretrade risk reports")
                    rows = self.store.get(self.table_name, [])
                    removed = [r for r in rows if self._matches(r)]
                    self.store[self.table_name] = [r for r in rows if not self._matches(r)]
                    return _FakeResponse(data=removed)
                merged = list(self.canned) + list(self.store.get(self.table_name, []))
                rows = [r for r in merged if self._matches(r)]
                if self._limit is not None:
                    rows = rows[: self._limit]
                return _FakeResponse(data=rows)

        @dataclass
        class PretradeRiskFake(FakeSupabaseClient):
            def table(self, name: str) -> _MergingQuery:
                return _MergingQuery(
                    table_name=name,
                    store=self.store,
                    canned=list(self.canned_reads.get(name, [])),
                )

        return PretradeRiskFake()

    def test_enforce_missing_report_rejects_before_booking(self, monkeypatch) -> None:
        monkeypatch.setenv("OLYMPUS_PRETRADE_RISK_MODE", "enforce")
        client = FakeSupabaseClient()
        out = _run(client, _state())
        assert "errors" in out
        assert "missing_pre_trade_risk_report" in out["errors"][0].message
        assert not client.store.get("positions")

    def test_shadow_default_missing_report_commits_without_blocking(self, monkeypatch) -> None:
        """Default/shadow is fail-soft: missing report must not block the book (#2824)."""
        monkeypatch.delenv("OLYMPUS_PRETRADE_RISK_MODE", raising=False)
        client = FakeSupabaseClient()
        out = _run(client, _state())
        assert "errors" not in out
        manifest = out["phase_hermes"].commit_manifest
        assert manifest["status"] == "committed"
        assert manifest["pretrade_risk_registry_status"] == "shadow_invalid"
        assert manifest["pretrade_risk_registry_reason"] == "missing_pre_trade_risk_report"
        assert client.store.get("positions")

    def test_explicit_shadow_invalid_report_commits(self, monkeypatch) -> None:
        monkeypatch.setenv("OLYMPUS_PRETRADE_RISK_MODE", "shadow")
        client = FakeSupabaseClient()
        state = _state()
        state.phase_hermes = state.phase_hermes.model_copy(
            update={"pre_trade_risk_report": {"not": "a report"}}
        )
        out = _run(client, state)
        assert "errors" not in out
        manifest = out["phase_hermes"].commit_manifest
        assert manifest["status"] == "committed"
        assert manifest["pretrade_risk_registry_status"] == "shadow_invalid"
        assert "unknown_pre_trade_risk_report" in str(manifest["pretrade_risk_registry_reason"])
        assert client.store.get("positions")

    def test_enforce_unknown_report_rejects(self, monkeypatch) -> None:
        monkeypatch.setenv("OLYMPUS_PRETRADE_RISK_MODE", "enforce")
        client = FakeSupabaseClient()
        state = _state()
        state.phase_hermes = state.phase_hermes.model_copy(
            update={"pre_trade_risk_report": {"not": "a report"}}
        )
        out = _run(client, state)
        assert "errors" in out
        assert "unknown_pre_trade_risk_report" in out["errors"][0].message
        assert not client.store.get("positions")

    def test_enforce_book_fingerprint_mismatch_rejects(self, monkeypatch) -> None:
        monkeypatch.setenv("OLYMPUS_PRETRADE_RISK_MODE", "enforce")
        client = FakeSupabaseClient()
        report = self._spy_report_payload()
        # Attach a valid SPY report to a different book.
        state = _state(sized_book=_sized_book(spy_pct=50.0))
        book = dict(state.phase_hermes.sized_book or {})
        book["recommended_portfolio"] = [
            {"ticker": "SPY", "target_pct": 50.0},
            {"ticker": "TLT", "target_pct": 50.0},
        ]
        book["pre_trade_risk_report_hash"] = report["report_content_hash"]
        state.phase_hermes = state.phase_hermes.model_copy(
            update={
                "sized_book": book,
                "pre_trade_risk_report": report,
                "asset_analysts": {
                    "SPY": {
                        "ticker": "SPY",
                        "stance": "buy",
                        "conviction_score": 4,
                        "thesis": "risk-on",
                        "risks": "",
                        "sources": [],
                    },
                    "TLT": {
                        "ticker": "TLT",
                        "stance": "buy",
                        "conviction_score": 3,
                        "thesis": "hedge",
                        "risks": "",
                        "sources": [],
                    },
                },
            }
        )
        out = _run(client, state)
        assert "errors" in out
        assert "final_book_weights_fingerprint_mismatch" in out["errors"][0].message
        assert not client.store.get("positions")

    def test_enforce_persists_hash_bound_report(self, monkeypatch) -> None:
        monkeypatch.setenv("OLYMPUS_PRETRADE_RISK_MODE", "enforce")
        client = self._merging_client()
        state = self._state_with_report()
        out = _run(client, state)
        manifest = out["phase_hermes"].commit_manifest
        assert manifest["status"] == "committed"
        assert manifest["schema_version"] == "1.6"
        assert manifest["pretrade_risk_registry_status"] == "ok"
        assert manifest["pretrade_risk_registry_reports_written"] == 1
        assert manifest["pretrade_risk_report_hash"]
        assert manifest["pretrade_risk_report_id"]
        rows = client.store.get("olympus_pretrade_risk_reports", [])
        assert len(rows) == 1
        assert rows[0]["report_content_hash"] == manifest["pretrade_risk_report_hash"]
        assert rows[0]["report_id"] == manifest["pretrade_risk_report_id"]

    def test_identical_retry_skips_append(self, monkeypatch) -> None:
        monkeypatch.setenv("OLYMPUS_PRETRADE_RISK_MODE", "enforce")
        client = self._merging_client()
        state = self._state_with_report()
        _run(client, state)
        assert len(client.store.get("olympus_pretrade_risk_reports", [])) == 1
        out2 = _run(client, state)
        assert out2["phase_hermes"].commit_manifest["status"] == "noop"
        assert out2["phase_hermes"].commit_manifest["pretrade_risk_registry_reports_skipped"] == 1
        assert len(client.store.get("olympus_pretrade_risk_reports", [])) == 1

    def test_append_only_no_upsert_or_update(self, monkeypatch) -> None:
        monkeypatch.setenv("OLYMPUS_PRETRADE_RISK_MODE", "enforce")
        client = self._merging_client()
        state = self._state_with_report()
        _run(client, state)
        # Re-run must not mutate the stored body.
        first = dict(client.store["olympus_pretrade_risk_reports"][0])
        _run(client, state)
        second = client.store["olympus_pretrade_risk_reports"][0]
        assert second == first

    def test_h9_never_imports_or_calls_report_builder(self) -> None:
        import ast

        import digiquant.olympus.hermes.phases.h9_commit_run as h9
        import digiquant.olympus.hermes.writers.commit_io as commit_io

        for module in (h9, commit_io):
            src = pathlib.Path(module.__file__).read_text(encoding="utf-8")
            assert "build_pretrade_risk_report" not in src
            tree = ast.parse(src)
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        imported.add(alias.name)
            assert not any(
                name == "digiquant.olympus.hermes.pretrade_risk" or name.endswith(".pretrade_risk")
                for name in imported
            )
