"""H9 ``commit_run`` coherence + idempotency tests (#932, #1046)."""

from __future__ import annotations

from datetime import date
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
