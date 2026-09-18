"""Trading-session forecast outcome resolver (#2676 / WP5.2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes

import pytest
from digiquant.portfolio.models.forecast import (
    ForecastAssessment,
    ForecastTerms,
    PriceAnchor,
    PriceAnchorStatus,
    RawUncertainty,
    forecast_terms_content_hash,
    materialize_forecast_amendment,
)
from digiquant.portfolio.models.forecast_calibration import OutcomeStatus
from digiquant.research import forecast_outcomes as fo
from digiquant.research import forecast_registry as fr
from digiquant.research.data.queries import UnknownTickerError
from digiquant.research.phases.preflight import (
    PreflightReflectDeps,
    build_preflight_reflect_node,
)
from digiquant.research.state import ResearchState

from tests.dq.research.test_supabase_io import FakeSupabaseClient, _FakeQuery, _FakeResponse

pytestmark = pytest.mark.unit

TS = datetime(2026, 7, 15, 20, 0, tzinfo=UTC)
CUTOFF = datetime(2026, 8, 25, 21, 0, tzinfo=UTC)
RUN_DATE = date(2026, 8, 25)
PRIOR_RUN = "run-prior-wp52"
CURRENT_RUN = "run-current-wp52"

# Mon–Fri Jul 15 → Aug 13 includes weekends; horizon=21 trading sessions → Aug 13.
SESSIONS = tuple(
    d
    for d in (date(2026, 7, 15) + timedelta(days=i) for i in range(45))
    if d.weekday() < 5  # skip Sat/Sun; no holiday in this window
)


@dataclass
class _MergingQuery(_FakeQuery):
    """Reads from store ∪ canned so inserts are visible to later selects."""

    def execute(self) -> _FakeResponse:
        if self._insert_rows is not None:
            if self.table_name == "decision_log":
                raise AssertionError("forecast outcomes must not write decision_log")
            self.store.setdefault(self.table_name, []).extend(self._insert_rows)
            return _FakeResponse(data=[dict(row) for row in self._insert_rows])
        if self._upsert_row is not None:
            if self.table_name == fo.OUTCOMES:
                raise AssertionError("upsert is forbidden on olympus_forecast_outcomes")
            rows = self._upsert_row if isinstance(self._upsert_row, list) else [self._upsert_row]
            self.store.setdefault(self.table_name, []).extend(rows)
            return _FakeResponse(data=[dict(row) for row in rows])
        if self._update_row is not None:
            if self.table_name == fo.OUTCOMES:
                raise AssertionError("update is forbidden on olympus_forecast_outcomes")
            updated: list[dict[str, Any]] = []
            for row in self.store.get(self.table_name, []):
                if self._matches(row):
                    row.update(self._update_row)
                    updated.append(row)
            return _FakeResponse(data=updated)
        merged = list(self.canned) + list(self.store.get(self.table_name, []))
        rows = [r for r in merged if self._matches(r)]
        if self._order is not None:
            col, desc = self._order
            rows.sort(key=lambda r: r.get(col, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        return _FakeResponse(data=rows)


@dataclass
class OutcomesFake(FakeSupabaseClient):
    def table(self, name: str) -> _MergingQuery:
        return _MergingQuery(
            table_name=name,
            store=self.store,
            canned=list(self.canned_reads.get(name, [])),
        )


def _terms(*, horizon: int = 21, **over: Any) -> ForecastTerms:
    base = dict(
        horizon_sessions=horizon,
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
    base.update(over)
    return ForecastTerms(**base)


def _assessment(
    *,
    ticker: str = "AAPL",
    source_run_id: str = PRIOR_RUN,
    observed_anchor: bool = True,
    ref_price: str = "100",
    known_at: datetime = TS,
    horizon: int = 21,
) -> ForecastAssessment:
    terms = _terms(horizon=horizon)
    ch = forecast_terms_content_hash(terms)
    from digiquant.portfolio.models.forecast import forecast_assessment_id

    if observed_anchor:
        anchor = PriceAnchor(
            status=PriceAnchorStatus.OBSERVED,
            price=Decimal(ref_price),
            observed_at=TS,
        )
    else:
        anchor = PriceAnchor(
            status=PriceAnchorStatus.UNAVAILABLE,
            unavailable_reason="mark_price_not_available_in_h5_state",
        )
    return ForecastAssessment(
        forecast_id=forecast_assessment_id(
            ticker=ticker, source_run_id=source_run_id, content_hash=ch
        ),
        ticker=ticker,
        terms=terms,
        source_run_id=source_run_id,
        provider_invocation_id="prov-1",
        prompt_version="asset-analyst-full@test",
        artifact_version="h5-full@1",
        price_anchor=anchor,
        effective_at=TS,
        known_at=known_at,
        content_hash=ch,
    )


def _seed_assessment(client: OutcomesFake, assessment: ForecastAssessment) -> None:
    fr.persist_forecast_lineage(client=client, assessments=[assessment])


class TestNthTradingSession:
    def test_skips_weekends_and_resolves_on_nth_session(self) -> None:
        assert date(2026, 7, 18) not in SESSIONS  # Saturday
        assert date(2026, 7, 19) not in SESSIONS  # Sunday
        ref = date(2026, 7, 15)
        maturity = fo._nth_session_after(ref, horizon_sessions=21, sessions=SESSIONS)
        assert maturity == date(2026, 8, 13)
        # Calendar-day +21 would land on Aug 5 — must not use that.
        assert maturity != date(2026, 8, 5)

    def test_holiday_gap_shifts_maturity(self) -> None:
        # Remove a mid-window weekday to simulate a holiday.
        holiday = date(2026, 7, 20)  # Monday
        sessions = tuple(d for d in SESSIONS if d != holiday)
        maturity = fo._nth_session_after(date(2026, 7, 15), horizon_sessions=21, sessions=sessions)
        assert maturity == date(2026, 8, 14)  # one session later than no-holiday


class TestResolveMaturedOutcomes:
    def test_resolves_due_forecast_with_exact_observed_anchor(self) -> None:
        assessment = _assessment(ref_price="100")
        ref = date(2026, 7, 15)
        mat = date(2026, 8, 13)
        client = OutcomesFake(
            canned_reads={
                "price_history": [
                    {"ticker": "AAPL", "date": ref.isoformat(), "close": "999"},  # ignored
                    {"ticker": "AAPL", "date": mat.isoformat(), "close": "106"},
                ],
            }
        )
        _seed_assessment(client, assessment)

        result = fo.resolve_matured_forecast_outcomes(
            client=client,
            run_date=RUN_DATE,
            knowledge_cutoff_at=CUTOFF,
            current_run_id=CURRENT_RUN,
            trading_sessions=SESSIONS,
        )
        assert result.resolved == 1
        assert result.pending == 0
        row = client.store[fo.OUTCOMES][0]
        assert row["status"] == OutcomeStatus.RESOLVED.value
        assert row["reference_session"] == ref.isoformat()
        assert row["maturity_session"] == mat.isoformat()
        # Exact anchor — not the price_history close at reference.
        assert Decimal(row["reference_snapshot"]["price"]) == Decimal("100")
        assert Decimal(row["maturity_snapshot"]["price"]) == Decimal("106")
        assert Decimal(row["realized_return"]) == Decimal("0.06")
        assert row["positive_label"] is True
        assert row["known_at"] == CUTOFF.isoformat()

    def test_missing_calendar_stays_pending(self) -> None:
        assessment = _assessment()
        client = OutcomesFake()
        _seed_assessment(client, assessment)
        result = fo.resolve_matured_forecast_outcomes(
            client=client,
            run_date=RUN_DATE,
            knowledge_cutoff_at=CUTOFF,
            trading_sessions=(),
        )
        assert result.resolved == 0
        assert fo.OUTCOMES not in client.store or not client.store[fo.OUTCOMES]

    def test_missing_maturity_close_stays_pending(self) -> None:
        assessment = _assessment()
        client = OutcomesFake(canned_reads={"price_history": []})
        _seed_assessment(client, assessment)
        result = fo.resolve_matured_forecast_outcomes(
            client=client,
            run_date=RUN_DATE,
            knowledge_cutoff_at=CUTOFF,
            trading_sessions=SESSIONS,
        )
        assert result.resolved == 0
        assert result.pending == 1
        assert fo.OUTCOMES not in client.store or not client.store[fo.OUTCOMES]

    def test_cutoff_hides_future_known_forecast(self) -> None:
        assessment = _assessment(known_at=CUTOFF + timedelta(hours=1))
        client = OutcomesFake(
            canned_reads={
                "price_history": [
                    {"ticker": "AAPL", "date": "2026-08-13", "close": "106"},
                ],
            }
        )
        _seed_assessment(client, assessment)
        result = fo.resolve_matured_forecast_outcomes(
            client=client,
            run_date=RUN_DATE,
            knowledge_cutoff_at=CUTOFF,
            trading_sessions=SESSIONS,
        )
        assert result.resolved == 0
        assert fo.OUTCOMES not in client.store or not client.store[fo.OUTCOMES]

    def test_same_run_exclusion(self) -> None:
        assessment = _assessment(source_run_id=CURRENT_RUN)
        client = OutcomesFake(
            canned_reads={
                "price_history": [
                    {"ticker": "AAPL", "date": "2026-08-13", "close": "106"},
                ],
            }
        )
        _seed_assessment(client, assessment)
        result = fo.resolve_matured_forecast_outcomes(
            client=client,
            run_date=RUN_DATE,
            knowledge_cutoff_at=CUTOFF,
            current_run_id=CURRENT_RUN,
            trading_sessions=SESSIONS,
        )
        assert result.resolved == 0
        assert result.skipped == 1

    def test_idempotent_second_pass(self) -> None:
        assessment = _assessment()
        client = OutcomesFake(
            canned_reads={
                "price_history": [
                    {"ticker": "AAPL", "date": "2026-08-13", "close": "106"},
                ],
            }
        )
        _seed_assessment(client, assessment)
        first = fo.resolve_matured_forecast_outcomes(
            client=client,
            run_date=RUN_DATE,
            knowledge_cutoff_at=CUTOFF,
            trading_sessions=SESSIONS,
        )
        second = fo.resolve_matured_forecast_outcomes(
            client=client,
            run_date=RUN_DATE,
            knowledge_cutoff_at=CUTOFF,
            trading_sessions=SESSIONS,
        )
        assert first.resolved == 1
        assert second.resolved == 0
        assert second.skipped == 1
        assert len(client.store[fo.OUTCOMES]) == 1

    def test_not_due_before_maturity_stays_pending(self) -> None:
        assessment = _assessment()
        client = OutcomesFake(
            canned_reads={
                "price_history": [
                    {"ticker": "AAPL", "date": "2026-08-13", "close": "106"},
                ],
            }
        )
        _seed_assessment(client, assessment)
        result = fo.resolve_matured_forecast_outcomes(
            client=client,
            run_date=date(2026, 8, 12),  # day before maturity session
            knowledge_cutoff_at=CUTOFF,
            trading_sessions=SESSIONS,
        )
        assert result.resolved == 0
        assert result.pending == 1

    def test_unavailable_anchor_uses_price_history_reference(self) -> None:
        assessment = _assessment(observed_anchor=False)
        ref = date(2026, 7, 15)
        mat = date(2026, 8, 13)
        client = OutcomesFake(
            canned_reads={
                "price_history": [
                    {"ticker": "AAPL", "date": ref.isoformat(), "close": "100"},
                    {"ticker": "AAPL", "date": mat.isoformat(), "close": "110"},
                ],
            }
        )
        _seed_assessment(client, assessment)
        result = fo.resolve_matured_forecast_outcomes(
            client=client,
            run_date=RUN_DATE,
            knowledge_cutoff_at=CUTOFF,
            trading_sessions=SESSIONS,
        )
        assert result.resolved == 1
        row = client.store[fo.OUTCOMES][0]
        assert Decimal(row["reference_snapshot"]["price"]) == Decimal("100")
        assert Decimal(row["realized_return"]) == Decimal("0.1")

    def test_does_not_read_decision_log_or_conviction(self) -> None:
        assessment = _assessment()
        client = OutcomesFake(
            canned_reads={
                "price_history": [
                    {"ticker": "AAPL", "date": "2026-08-13", "close": "106"},
                ],
                "decision_log": [
                    {
                        "ticker": "AAPL",
                        "conviction": 5,
                        "status": "pending",
                        "run_date": "2026-07-15",
                        "holding_days": 21,
                    }
                ],
            }
        )
        _seed_assessment(client, assessment)
        fo.resolve_matured_forecast_outcomes(
            client=client,
            run_date=RUN_DATE,
            knowledge_cutoff_at=CUTOFF,
            trading_sessions=SESSIONS,
        )
        assert "decision_log" not in client.store
        assert len(client.store[fo.OUTCOMES]) == 1

    def test_amendment_effective_id(self) -> None:
        assessment = _assessment()
        terms = _terms(horizon=21, base_return=Decimal("0.05"))
        amendment = materialize_forecast_amendment(
            base=assessment,
            terms=terms,
            source_run_id=PRIOR_RUN,
            provider_invocation_id="prov-am",
            reason="new_evidence",
            new_evidence_ids=("ev-1",),
            contradiction_ids=(),
            effective_at=TS + timedelta(days=1),
            known_at=TS + timedelta(days=1),
        )
        client = OutcomesFake(
            canned_reads={
                "price_history": [
                    {"ticker": "AAPL", "date": "2026-08-13", "close": "106"},
                ],
            }
        )
        fr.persist_forecast_lineage(client=client, assessments=[assessment], amendments=[amendment])
        result = fo.resolve_matured_forecast_outcomes(
            client=client,
            run_date=RUN_DATE,
            knowledge_cutoff_at=CUTOFF,
            trading_sessions=SESSIONS,
        )
        assert result.resolved == 1
        row = client.store[fo.OUTCOMES][0]
        assert row["effective_forecast_id"] == str(amendment.amendment_id)
        assert row["base_forecast_id"] == str(assessment.forecast_id)


class TestPreflightReflectWiring:
    def test_reflect_invokes_outcome_resolver_beside_decision_log(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []

        def fake_resolve_pending(**_kwargs: Any) -> int:
            calls.append("decision_log")
            return 0

        def fake_resolve_outcomes(**_kwargs: Any) -> fo.OutcomeResolveResult:
            calls.append("forecast_outcomes")
            return fo.OutcomeResolveResult(resolved=0)

        monkeypatch.setattr(
            "digiquant.research.phases.preflight.resolve_pending",
            fake_resolve_pending,
        )
        monkeypatch.setattr(
            "digiquant.research.phases.preflight.resolve_matured_forecast_outcomes",
            fake_resolve_outcomes,
        )
        node = build_preflight_reflect_node(PreflightReflectDeps(client=OutcomesFake()))
        state = ResearchState(
            run_type="delta",
            run_date=RUN_DATE,
            knowledge_cutoff_at=CUTOFF,
        )
        assert node(state) == {}
        assert calls == ["decision_log", "forecast_outcomes"]


class TestReturnFractionQuantize:
    def test_quantize_return_fraction_fits_forecast_outcome_bounds(self) -> None:
        """Long Decimal division must not trip ForecastOutcome decimal_max_digits."""
        from uuid import uuid4

        from digiquant.portfolio.models.forecast_calibration import (
            ForecastOutcome,
            SessionPriceSnapshot,
            forecast_outcome_content_hash,
            forecast_outcome_id,
        )

        long = Decimal("123.4567890123456789012345") / Decimal("987.6543210987654321")
        q = fo._quantize_return_fraction(long)
        assert q.as_tuple().exponent >= -8
        # Digit count within ReturnFraction max_digits=16 (sign ignored).
        digits = "".join(str(d) for d in q.as_tuple().digits)
        assert len(digits) <= 16

        # Smoke: constructing ForecastOutcome with quantized fields does not raise.
        ref = SessionPriceSnapshot(
            session_date=date(2026, 7, 15),
            price=Decimal("100.00000000"),
            observed_at=TS,
            known_at=TS,
        )
        mat = SessionPriceSnapshot(
            session_date=date(2026, 8, 13),
            price=Decimal("103.33333333"),
            observed_at=CUTOFF,
            known_at=CUTOFF,
        )
        forecast_mean = fo._quantize_return_fraction(Decimal("0.02"))
        realized = fo._quantize_return_fraction((mat.price - ref.price) / ref.price)
        residual = fo._quantize_return_fraction(realized - forecast_mean)
        base_id = uuid4()
        eff_id = uuid4()
        draft = {
            "base_forecast_id": base_id,
            "effective_forecast_id": eff_id,
            "ticker": "TEST",
            "horizon_sessions": 21,
            "reference_session": ref.session_date,
            "maturity_session": mat.session_date,
            "reference_snapshot": ref,
            "maturity_snapshot": mat,
            "forecast_mean_return": forecast_mean,
            "realized_return": realized,
            "signed_residual": residual,
            "positive_label": realized > 0,
            "status": OutcomeStatus.RESOLVED,
            "unavailable_reason": None,
            "event_time": mat.observed_at,
            "known_at": mat.known_at,
        }
        payload = {
            "base_forecast_id": str(base_id),
            "effective_forecast_id": str(eff_id),
            "ticker": "TEST",
            "horizon_sessions": 21,
            "reference_session": ref.session_date.isoformat(),
            "maturity_session": mat.session_date.isoformat(),
            "reference_snapshot": ref.model_dump(mode="json"),
            "maturity_snapshot": mat.model_dump(mode="json"),
            "forecast_mean_return": str(forecast_mean),
            "realized_return": str(realized),
            "signed_residual": str(residual),
            "positive_label": realized > 0,
            "status": OutcomeStatus.RESOLVED.value,
            "unavailable_reason": None,
            "event_time": mat.observed_at.isoformat(),
            "known_at": mat.known_at.isoformat(),
        }
        content_hash = forecast_outcome_content_hash(payload=payload)
        outcome_id = forecast_outcome_id(
            effective_forecast_id=eff_id,
            maturity_session=mat.session_date,
            content_hash=content_hash,
        )
        outcome = ForecastOutcome(outcome_id=outcome_id, content_hash=content_hash, **draft)
        assert outcome.realized_return == realized


class TestR2UnknownTickerIsAbsentClose:
    """A ticker outside the sealed R2 universe is an absent close, not a crash (#4119).

    ``r2_close_rows`` fails loud with ``LookupError`` for an unknown ticker, which is
    right for its own callers. The forecast outcome resolver's contract is different:
    no generation simply means "no reference close", which it already treats as
    pending. So the tolerance belongs at this call site, not in ``queries.py``.
    """

    @staticmethod
    def _unknown_ticker(monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_r2_close_rows(**_kwargs: Any) -> list[dict[str, Any]]:
            raise UnknownTickerError("unknown ticker 'MSFT'")

        monkeypatch.setattr(
            "digiquant.research.data.queries.r2_close_rows",
            fake_r2_close_rows,
        )
        monkeypatch.setattr(fo, "r2_backend_enabled", lambda: True)

    def test_fetch_session_close_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._unknown_ticker(monkeypatch)
        assert (
            fo._fetch_session_close(client=OutcomesFake(), ticker="MSFT", session=date(2026, 8, 13))
            is None
        )

    def test_outcome_stays_pending_instead_of_crashing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._unknown_ticker(monkeypatch)
        client = OutcomesFake()
        _seed_assessment(client, _assessment(ticker="MSFT", observed_anchor=False))

        result = fo.resolve_matured_forecast_outcomes(
            client=client,
            run_date=RUN_DATE,
            knowledge_cutoff_at=CUTOFF,
            trading_sessions=SESSIONS,
        )
        assert result.resolved == 0
        assert result.pending == 1
        assert fo.OUTCOMES not in client.store

    def test_known_ticker_still_resolves_via_r2(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Control: the catch must not swallow a real close."""
        maturity = date(2026, 8, 13)

        def fake_r2_close_rows(**_kwargs: Any) -> list[dict[str, Any]]:
            return [{"ticker": "AAPL", "date": maturity.isoformat(), "close": "106"}]

        monkeypatch.setattr(
            "digiquant.research.data.queries.r2_close_rows",
            fake_r2_close_rows,
        )
        monkeypatch.setattr(fo, "r2_backend_enabled", lambda: True)
        client = OutcomesFake()
        _seed_assessment(client, _assessment(ticker="AAPL"))

        result = fo.resolve_matured_forecast_outcomes(
            client=client,
            run_date=RUN_DATE,
            knowledge_cutoff_at=CUTOFF,
            trading_sessions=SESSIONS,
        )
        assert result.resolved == 1
        row = client.store[fo.OUTCOMES][0]
        assert Decimal(row["maturity_snapshot"]["price"]) == Decimal("106")

    def test_malformed_manifest_entry_still_fails_loud(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Control: ``KeyError`` is a ``LookupError``, so catch the signal, not the base.

        A v1 manifest entry missing ``object``/``sha256`` is a broken manifest, and
        used to crash the graph. It must keep crashing rather than become a forecast
        that stays pending forever (#4120 review).
        """

        def fake_r2_close_rows(**_kwargs: Any) -> list[dict[str, Any]]:
            raise KeyError("sha256")

        monkeypatch.setattr(
            "digiquant.research.data.queries.r2_close_rows",
            fake_r2_close_rows,
        )
        monkeypatch.setattr(fo, "r2_backend_enabled", lambda: True)
        with pytest.raises(KeyError, match="sha256"):
            fo._fetch_session_close(client=OutcomesFake(), ticker="AAPL", session=date(2026, 8, 13))

    def test_corrupt_manifest_still_fails_loud(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Control: only an absent ticker means absent; a bad manifest is a real fault."""

        def fake_r2_close_rows(**_kwargs: Any) -> list[dict[str, Any]]:
            raise ValueError("unsupported manifest version 2")

        monkeypatch.setattr(
            "digiquant.research.data.queries.r2_close_rows",
            fake_r2_close_rows,
        )
        monkeypatch.setattr(fo, "r2_backend_enabled", lambda: True)
        with pytest.raises(ValueError, match="unsupported manifest version 2"):
            fo._fetch_session_close(client=OutcomesFake(), ticker="AAPL", session=date(2026, 8, 13))


# The exact float64 close from run 35214931391, which aborted preflight.reflect
# with ``decimal_max_places`` on ``SessionPriceSnapshot.price`` (#4296).
FLOAT_NOISE_CLOSE = 10.380000114440918


class TestR2FloatCloseIngressQuantized:
    """R2 parquet stores OHLCV as float64 by design; the closure's Decimal ingress
    must quantize to the price model's money precision (#4296).

    ``Decimal(str(10.380000114440918))`` is a 15-place Decimal, which Pydantic
    rejects for ``PositivePrice`` (``decimal_places=8``). Rounding it here is a
    genuine ingress normalization — not a caught ``ValidationError`` and not a
    skipped matured outcome.
    """

    @staticmethod
    def _float_close(monkeypatch: pytest.MonkeyPatch, close: float) -> None:
        def fake_r2_close_rows(**_kwargs: Any) -> list[dict[str, Any]]:
            return [{"ticker": "AAPL", "date": "2026-08-13", "close": close}]

        monkeypatch.setattr(
            "digiquant.research.data.queries.r2_close_rows",
            fake_r2_close_rows,
        )
        monkeypatch.setattr(fo, "r2_backend_enabled", lambda: True)

    def test_raw_float64_would_fail_the_model(self) -> None:
        """Guard: the unfixed conversion still fails, so the test cannot pass by accident."""
        from digiquant.portfolio.models.forecast_calibration import SessionPriceSnapshot

        raw = Decimal(str(FLOAT_NOISE_CLOSE))
        assert raw.as_tuple().exponent < -8
        with pytest.raises(Exception, match="decimal_max_places"):
            SessionPriceSnapshot(
                session_date=date(2026, 8, 13),
                price=raw,
                observed_at=TS,
                known_at=TS,
            )

    def test_float64_close_validates_session_price_snapshot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from digiquant.portfolio.models.forecast_calibration import SessionPriceSnapshot

        self._float_close(monkeypatch, FLOAT_NOISE_CLOSE)
        price = fo._fetch_session_close(
            client=OutcomesFake(), ticker="AAPL", session=date(2026, 8, 13)
        )
        assert price is not None
        assert price.as_tuple().exponent >= -8
        digits = "".join(str(d) for d in price.as_tuple().digits)
        assert len(digits) <= 20  # PositivePrice max_digits=20
        snap = SessionPriceSnapshot(
            session_date=date(2026, 8, 13),
            price=price,
            observed_at=TS,
            known_at=TS,
        )
        assert snap.price == Decimal("10.38000011")

    def test_outcome_resolves_instead_of_aborting_reflect(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End-to-end: a float-noise close resolves, it does not crash preflight."""
        self._float_close(monkeypatch, FLOAT_NOISE_CLOSE)
        client = OutcomesFake()
        _seed_assessment(client, _assessment(ticker="AAPL", observed_anchor=False))

        result = fo.resolve_matured_forecast_outcomes(
            client=client,
            run_date=RUN_DATE,
            knowledge_cutoff_at=CUTOFF,
            trading_sessions=SESSIONS,
        )
        assert result.resolved == 1
        row = client.store[fo.OUTCOMES][0]
        assert Decimal(str(row["maturity_snapshot"]["price"])) == Decimal("10.38000011")
        assert row["status"] == OutcomeStatus.RESOLVED.value
