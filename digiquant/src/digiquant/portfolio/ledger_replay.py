"""Ledger-anchored book weights — the WRITE side of DIG-2816.

``positions.weight_pct`` is a drift-carrying ACTUAL written by several independent
writers. ``position_events`` is the rebalance LEDGER — the operator's intended
target weight per ticker. Chris's 2026-10-10 verdict on the house book: the
25 Sep rebalance targets (UUP 15 / DBO 10 / XLV 10) are the correct weights, so a
writer must not persist a book the ledger cannot explain.

This module is the Python mirror of the read-side replay
(``apps/dashboard-api/src/ledger-weights.ts``, DIG-2803 / PR #5391). Both sides
must agree on what the ledger says, so the semantics are deliberately identical:

  * FAIL CLOSED. A missing, unreadable, future-dated or unrecognised event never
    invents or zeroes a weight. The book value stands and the row is reported
    unreconciled. A ledger read that raised leaves ``covered`` false and records
    the error, so "we could not read the ledger" is never reported as
    "the ledger agrees".
  * NOTHING IS HIDDEN. Anchoring ``weight_pct`` to the ledger target does not
    discard the positions value: every reconciliation carries the pre-anchor
    weight and the drift in percentage points.

``HOLD`` is deliberately NOT a weight-setting event — a hold restates today's
mark, it is not a decision about size — so it is counted and skipped, exactly as
on the read side.

Usage in a writer (see ``writers/commit_io.py`` and
``scripts/research/sync_positions_from_rebalance.py``)::

    state = fetch_ledger_state(client, workspace_id, book_date)
    report = reconcile_book(rows, state, writer="commit_io", mode="anchor")
    logger.info(report.summary())

``update_tearsheet.py`` computes ``position_events`` from day-over-day book
digests, so it is UPSTREAM of the ledger and must never be gated on it.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date as _date
from typing import Any, Dict, List, Mapping, Optional, Sequence

__all__ = [
    "LEDGER_WEIGHT_EVENT_TYPES",
    "LedgerReconcileError",
    "LedgerTarget",
    "LedgerWeightState",
    "BookReconciliation",
    "event_type",
    "fetch_ledger_state",
    "is_calendar_date",
    "reconcile_book",
    "replay_ledger_weights",
    "round_pct",
]

#: ``position_events.event`` values the replay understands. Mirrors §6.8.
LEDGER_WEIGHT_EVENT_TYPES = ("OPEN", "ADD", "EXIT", "TRIM")

_CALENDAR_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: A writer is only "conflicting" when the book and the ledger disagree by more
#: than this. 0.0 means any difference counts, which is the house default: the
#: desk shows weights to one decimal, so anything smaller is invisible anyway.
DEFAULT_DRIFT_TOLERANCE_PP = 0.0


class LedgerReconcileError(RuntimeError):
    """A book was about to be persisted that ``position_events`` contradicts.

    Carries the full report so a caller can log the evidence instead of a bare
    message.
    """

    def __init__(self, message: str, report: "BookReconciliation") -> None:
        super().__init__(f"{message} | {report.summary()}")
        self.report = report


@dataclass(frozen=True)
class LedgerTarget:
    """The ledger's current intended weight for one ticker."""

    ticker: str
    weight_pct: float
    event_date: str
    event: str
    prev_weight_pct: Optional[float] = None


@dataclass
class LedgerWeightState:
    """Replay outcome.

    The counters exist so a silent no-op is never confused with "the ledger
    agrees": a reader that found nothing usable must be able to say so.
    """

    targets: Dict[str, LedgerTarget] = field(default_factory=dict)
    exited: set = field(default_factory=set)
    latest_event_date: Optional[str] = None
    applied: int = 0
    #: Events skipped: unparseable date, unknown event type, empty ticker.
    ignored: int = 0
    #: Usable events dated after the book being written (never applied).
    future: int = 0
    #: OPEN/ADD/TRIM events whose ``weight_pct`` was null, non-finite or negative.
    unusable_weight: int = 0
    #: Set when the ledger read itself failed. ``covered`` is then false and the
    #: reconciliation is explicitly NOT a pass.
    read_error: Optional[str] = None

    @property
    def covered(self) -> bool:
        return self.read_error is None and bool(self.targets)


def is_calendar_date(value: Any) -> bool:
    """True only for a real ``YYYY-MM-DD`` calendar date.

    A shape check alone lets ``2026-02-31`` through, so the parsed date is
    round-tripped back to text and compared.
    """
    if not isinstance(value, str) or not _CALENDAR_DATE.match(value):
        return False
    try:
        parsed = _date.fromisoformat(value)
    except ValueError:
        return False
    return parsed.isoformat() == value


def round_pct(value: float) -> float:
    """Round to 6dp, half away from zero (the read side uses JS ``Math.round``)."""
    scaled = float(value) * 1e6
    if math.isnan(scaled) or math.isinf(scaled):  # NaN / inf
        return float(value)
    rounded = math.floor(scaled + 0.5) if scaled >= 0 else math.ceil(scaled - 0.5)
    return rounded / 1e6


def event_type(raw: Any) -> Optional[str]:
    """Normalise a raw ``position_events.event`` value, or ``None`` if unknown."""
    up = str(raw if raw is not None else "").strip().upper()
    return up if up in LEDGER_WEIGHT_EVENT_TYPES else None


def _coerce_weight(raw: Any) -> Optional[float]:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def _later(a: Optional[str], b: str) -> str:
    return b if a is None or b > a else a


def replay_ledger_weights(
    events: Sequence[Mapping[str, Any]],
    book_date: Optional[str],
) -> LedgerWeightState:
    """Replay ``position_events`` into per-ticker target weights as of ``book_date``.

    Events dated after ``book_date`` are counted and dropped: a committed book
    must never be reconciled against a decision taken after it. ``book_date``
    that is missing or not a calendar date yields an uncovered state, which the
    caller must treat as "no ledger" rather than "an empty ledger".
    """
    state = LedgerWeightState()
    if not book_date or not is_calendar_date(book_date):
        return state

    # Replay in date order so the reader's own SQL ordering cannot change the
    # outcome. Python's sort is stable, so a same-date pair resolves to the later
    # arrival and ``state.targets`` holds the last write.
    # The key must survive a non-Mapping row: a junk row is IGNORED below, not fatal,
    # so sorting it here with ``e.get`` would raise before the guard ever runs.
    ordered = sorted(
        events or [], key=lambda e: str(e.get("date") or "") if isinstance(e, Mapping) else ""
    )

    for raw in ordered:
        if not isinstance(raw, Mapping):
            state.ignored += 1
            continue
        etype = event_type(raw.get("event"))
        event_date = str(raw.get("date") or "")[:10]
        if etype is None or not is_calendar_date(event_date):
            state.ignored += 1
            continue
        if event_date > book_date:
            state.future += 1
            continue
        ticker = str(raw.get("ticker") or "").strip()
        if not ticker:
            state.ignored += 1
            continue
        if etype == "EXIT":
            state.targets.pop(ticker, None)
            state.exited.add(ticker)
            state.applied += 1
            state.latest_event_date = _later(state.latest_event_date, event_date)
            continue
        weight = _coerce_weight(raw.get("weight_pct"))
        if weight is None or weight < 0:
            # Fail closed: an event we cannot read leaves the prior target
            # standing rather than silently resetting the position to zero.
            state.unusable_weight += 1
            continue
        state.targets[ticker] = LedgerTarget(
            ticker=ticker,
            weight_pct=weight,
            event_date=event_date,
            event=etype,
            prev_weight_pct=_coerce_weight(raw.get("prev_weight_pct")),
        )
        state.exited.discard(ticker)
        state.applied += 1
        state.latest_event_date = _later(state.latest_event_date, event_date)

    return state


@dataclass
class BookReconciliation:
    """What the ledger said about one book a writer was about to persist."""

    writer: str
    mode: str
    state: Optional[LedgerWeightState]
    #: Tickers whose persisted weight now comes from the ledger.
    anchored: List[str] = field(default_factory=list)
    #: ticker -> pre-anchor weight minus the ledger target, in pp.
    drift_pp: Dict[str, float] = field(default_factory=dict)
    #: Non-CASH book tickers the ledger says nothing about.
    unreconciled: List[str] = field(default_factory=list)
    #: Tickers the ledger covers that have no book row at all.
    ledger_only: List[str] = field(default_factory=list)
    #: Book rows the ledger has EXITed and not re-opened — a real conflict.
    conflicts: List[str] = field(default_factory=list)
    tolerance_pp: float = DEFAULT_DRIFT_TOLERANCE_PP

    @property
    def covered(self) -> bool:
        return self.state is not None and self.state.covered

    @property
    def read_error(self) -> Optional[str]:
        return self.state.read_error if self.state is not None else None

    @property
    def clean(self) -> bool:
        """True only when the ledger AGREED with the book.

        An UNCOVERED state is never clean. With no ledger read there is nothing to
        agree with, and ``not conflicts and not unreconciled`` is trivially true for
        an empty ledger — so this would report a failed read as a passing gate,
        which is the exact silent-pass the whole guard exists to prevent. Callers
        that genuinely want "no disagreement found" should read ``covered`` first.
        """
        return (
            self.covered and not self.conflicts and not self.unreconciled and not self.ledger_only
        )

    def drifted(self) -> List[str]:
        return sorted(t for t, pp in self.drift_pp.items() if abs(pp) > self.tolerance_pp)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "writer": self.writer,
            "mode": self.mode,
            "covered": self.covered,
            "read_error": self.read_error,
            "anchored": sorted(self.anchored),
            "drifted": self.drifted(),
            "drift_pp": dict(sorted(self.drift_pp.items())),
            "unreconciled": sorted(self.unreconciled),
            "ledger_only": sorted(self.ledger_only),
            "conflicts": sorted(self.conflicts),
            "tolerance_pp": self.tolerance_pp,
            "ledger": None
            if self.state is None
            else {
                "latest_event_date": self.state.latest_event_date,
                "applied": self.state.applied,
                "ignored": self.state.ignored,
                "future": self.state.future,
                "unusable_weight": self.state.unusable_weight,
                "targets": len(self.state.targets),
                "exited": len(self.state.exited),
            },
        }

    def summary(self) -> str:
        """One grep-able line. Never prints a bare "ok"."""
        head = (
            f"ledger-reconcile[{self.writer}] mode={self.mode} covered={self.covered} "
            f"anchored={len(self.anchored)} drifted={len(self.drifted())} "
            f"unreconciled={len(self.unreconciled)} ledger_only={len(self.ledger_only)} "
            f"conflicts={len(self.conflicts)} tolerance_pp={self.tolerance_pp}"
        )
        state = self.state
        if state is not None:
            head += (
                f" ledger[latest={state.latest_event_date} applied={state.applied}"
                f" ignored={state.ignored} future={state.future}"
                f" unusable_weight={state.unusable_weight} targets={len(state.targets)}"
                f" exited={len(state.exited)}]"
            )
        if state is not None and state.read_error:
            head += f" READ_ERROR={state.read_error}"
        for ticker in self.conflicts:
            head += f" CONFLICT={ticker}"
        return head


def reconcile_book(
    rows: Sequence[Mapping[str, Any]],
    state: Optional[LedgerWeightState],
    *,
    writer: str,
    mode: str = "anchor",
    tolerance_pp: float = DEFAULT_DRIFT_TOLERANCE_PP,
    strict: bool = True,
) -> BookReconciliation:
    """Reconcile book rows a writer is about to persist against the ledger.

    ``mode``:

    * ``"anchor"`` — copy the rows and replace ``weight_pct`` with the ledger
      target wherever the ledger covers the ticker. The book's own weight is
      preserved in the report as drift, so the substitution stays measurable.
    * ``"strict"`` — do not touch the rows; report only. Used by the writer
      whose whole job is to persist a specific book
      (``sync_positions_from_rebalance.py``), where silently overwriting the
      book with the ledger would defeat its purpose.

    ``CASH`` is skipped: it is never a ledger target, it is the residual.

    Raises :class:`LedgerReconcileError` when ``strict`` and the ledger says the
    book holds a ticker it has EXITed. A phantom holding is never a legitimate
    state and never a rounding artefact, so it is refused in both modes.
    """
    if mode not in ("anchor", "strict"):
        raise ValueError(f"unknown reconcile mode {mode!r}")

    report = BookReconciliation(writer=writer, mode=mode, state=state, tolerance_pp=tolerance_pp)
    covered = report.covered
    ledger = state if (covered and state is not None) else None
    seen: set = set()
    out: List[Dict[str, Any]] = []

    for raw in rows or []:
        row = dict(raw) if isinstance(raw, Mapping) else {}
        ticker = str(row.get("ticker") or "").strip()
        if not ticker:
            out.append(row)
            continue
        if ticker.upper() == "CASH":
            out.append(row)
            continue
        seen.add(ticker)
        positions_weight = _coerce_weight(row.get("weight_pct")) or 0.0
        target = ledger.targets.get(ticker) if ledger is not None else None
        if target is None:
            if ledger is not None:
                if ticker in ledger.exited:
                    report.conflicts.append(ticker)
                else:
                    report.unreconciled.append(ticker)
            out.append(row)
            continue
        drift = round_pct(positions_weight - target.weight_pct)
        report.drift_pp[ticker] = drift
        if mode == "anchor":
            row["weight_pct"] = target.weight_pct
            report.anchored.append(ticker)
        out.append(row)

    if ledger is not None:
        report.ledger_only = sorted(t for t in ledger.targets if t not in seen)
    report.unreconciled.sort()
    report.conflicts.sort()

    if strict and report.conflicts:
        raise LedgerReconcileError(
            f"book holds {len(report.conflicts)} ticker(s) position_events has EXITed; "
            f"refusing to persist a book the ledger contradicts",
            report,
        )

    if mode == "anchor" and isinstance(rows, list):
        rows[:] = out  # in-place so callers keep their list object
    return report


def fetch_ledger_state(
    client: Any,
    workspace_id: Optional[str],
    book_date: Optional[str],
    *,
    table: str = "position_events",
) -> LedgerWeightState:
    """Read ``position_events`` up to and including ``book_date`` and replay it.

    The read is scoped by ``workspace_id`` and ordered by ``date`` ascending, so
    the caller gets exactly the window the ledger is authoritative over. No
    ``book_source`` filter is applied: the read side applies none either, and two
    sides of the same contract must not disagree about what the ledger contains.

    A failed read returns an UNCOVERED state carrying ``read_error`` — never a
    state that could be mistaken for an agreement.
    """
    state = LedgerWeightState()
    if not book_date or not is_calendar_date(book_date):
        state.read_error = None
        return state
    try:
        query = client.table(table).select("date,ticker,event,weight_pct,prev_weight_pct")
        if workspace_id:
            query = query.eq("workspace_id", str(workspace_id))
        res = query.lte("date", book_date).order("date").execute()
    except Exception as exc:  # fail closed: never guess, never report a failed read as agreement
        state.read_error = f"{type(exc).__name__}: {exc}"
        return state
    rows = getattr(res, "data", None)
    if rows is None:
        state.read_error = f"ledger read returned no data attribute ({type(res).__name__})"
        return state
    return replay_ledger_weights(rows, book_date)
