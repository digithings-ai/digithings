"""Documented per-asset cycle extrema for Stage A weight search.

Pin dates live here — the optimizer must not invent ad-hoc peak/trough lists.
Each asset has its own pin set (BTC v1, ETH research v1, gold v1, …). Windows
are ±45 calendar days around well-known cycle pins. A later high does not
automatically expand a set; edit the named factory if the pin should move.

**A window is a scoring target, not an execution period.** The windows say when
a cycle turned so the Stage A search can ask "does this indicator read cheap
inside the buy windows and rich inside the sell windows?". They are not
periods to be traded, they imply no position sizing, and they carry no exposure
floor of any kind. (#4804, Plan 22 — the owner parked the earlier
"period as execution window" reading as a wrong turn.)

**A pin set is a chain of PAIRS, never a list of extremes.** Owner ruling 2: a
cycle runs buy, sell, buy, sell…, so two turns of the same kind in a row is
malformed — the set would define a buy with no sell and then another buy further
down. Every documented factory runs ``validate_paired_turns`` before it returns,
so a malformed set cannot ship. The model itself stays permissive because
``period_optimize`` legitimately builds one-sided window sets (a long-only buy
band); the invariant belongs to the *pin factories*, not to the container.

**Gold ships two sets, and they are comparable rather than competing.**
``gold_v1()`` is Set A, six close-based pins the owner approved by hand.
``gold_v2()`` is the same series' turns chosen by algorithm (20 of them). Every
Set A pin appears in ``gold_v2()`` with the same kind, so the two answer one
question at two granularities. Both derive from the ``close`` column of the
cached OHLCV — column index 1 is ``open``, and reading that instead once
produced a wrong-date incident.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

_HALF_WINDOW = timedelta(days=45)


class CycleKind(StrEnum):
    TROUGH = "trough"
    PEAK = "peak"


class CycleWindow(BaseModel):
    """Inclusive calendar window around one cycle extreme."""

    model_config = ConfigDict(frozen=True, strict=True)

    name: str = Field(min_length=1)
    kind: CycleKind
    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> CycleWindow:
        if self.end < self.start:
            raise ValueError(f"{self.name}: end {self.end} is before start {self.start}")
        return self

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end


def _window(name: str, kind: CycleKind, pin: date) -> CycleWindow:
    return CycleWindow(name=name, kind=kind, start=pin - _HALF_WINDOW, end=pin + _HALF_WINDOW)


def validate_paired_turns(windows: Sequence[CycleWindow]) -> None:
    """Owner ruling 2 as a callable guard: strictly alternating, never a lone turn.

    ``windows`` is read in **time order**, not declaration order, so a caller cannot
    pass a shuffled tuple and get a different verdict.

    What it refuses, and why each is malformed rather than merely unusual:

    - **A lone turn.** One window pairs with nothing: it defines neither a buy period
      nor a sell period, so it cannot be a scoring target for a buy/sell separation.
    - **Two turns of the same kind in a row.** Two peaks in a row is "a buy, no sell,
      and then another buy further down" — the exact shape the owner ruled out.

    What it deliberately does **not** refuse: **parity.** An odd number of turns is
    legal. Strict alternation still gives every peak an adjacent trough inside an
    odd-length set (this is why ``btc_v1()``'s five pins, peak…peak, are fine), and a
    balanced even-length set that ends on a trough is equally fine. ``gold_v1()``'s six
    pins are peak…trough and must not be rejected for being a closed pair.

    This lives here rather than as a ``SdcaCycleWindows`` validator because
    ``period_optimize.combine_periods`` builds one-sided window sets (long-only buy
    bands, and a peak/peak/trough/trough ordering) that this invariant would refuse —
    correctly, since those are not cycle pins.
    """
    ordered = sorted(windows, key=lambda window: (window.start, window.end))
    kinds = [window.kind for window in ordered]
    if len(kinds) == 1:
        raise ValueError(
            "a single window cannot pair: every peak needs an adjacent trough, so one turn "
            "defines neither a buy period nor a sell period and is malformed"
        )
    for earlier, later in zip(kinds, kinds[1:], strict=False):
        if earlier is later:
            raise ValueError(
                "window kinds must strictly alternate peak/trough, got "
                f"{earlier.value} twice in a row — a cycle set is a chain of pairs "
                "(buy, sell, buy, sell…), never two turns of the same kind"
            )


def _documented(*windows: CycleWindow) -> SdcaCycleWindows:
    """Build a named pin set, refusing a malformed one (owner ruling 2)."""
    validate_paired_turns(windows)
    return SdcaCycleWindows(windows=windows)


class SdcaCycleWindows(BaseModel):
    """Named cycle windows. ``btc_v1()`` / ``eth_research_v1()`` / ``gold_v1()`` /
    ``gold_v2()`` are pin sets."""

    model_config = ConfigDict(frozen=True, strict=True)

    windows: tuple[CycleWindow, ...]

    @model_validator(mode="after")
    def _non_empty(self) -> SdcaCycleWindows:
        if not self.windows:
            raise ValueError("at least one cycle window is required")
        return self

    def troughs(self) -> tuple[CycleWindow, ...]:
        return tuple(w for w in self.windows if w.kind == CycleKind.TROUGH)

    def peaks(self) -> tuple[CycleWindow, ...]:
        return tuple(w for w in self.windows if w.kind == CycleKind.PEAK)

    def kind_on(self, day: date) -> CycleKind | None:
        for window in self.windows:
            if window.contains(day):
                return window.kind
        return None

    @classmethod
    def btc_v1(cls) -> SdcaCycleWindows:
        """Documented BTC cycle pins used by Stage A.

        Pins: 2017-12-17 high, 2018-12-15 low, 2021-11-10 high, 2022-11-21 low,
        2025-01-20 high (Jan 2025 ATH region). ±45 days each. Five pins, so it is an
        odd-length set — legal, because strict alternation still pairs every peak
        inside it.
        """
        return _documented(
            _window("2017_peak", CycleKind.PEAK, date(2017, 12, 17)),
            _window("2018_trough", CycleKind.TROUGH, date(2018, 12, 15)),
            _window("2021_peak", CycleKind.PEAK, date(2021, 11, 10)),
            _window("2022_trough", CycleKind.TROUGH, date(2022, 11, 21)),
            _window("2025_peak", CycleKind.PEAK, date(2025, 1, 20)),
        )

    @classmethod
    def gold_v1(cls) -> SdcaCycleWindows:
        """**Set A** — the owner's approved gold cycle pins. Six of them, and only six.

        Each pin is a **close-based** turning point of ``GLD-USD`` (column ``close``;
        column index 1 is ``open``, a trap that already caused one wrong-date
        incident). Every date below is a bar whose close is the extreme of its own
        ±5-bar neighbourhood:

        ============  =======  ==========
        Pin           Kind     Close
        ============  =======  ==========
        2011-08-22    peak      $184.59
        2015-12-17    trough    $100.50
        2020-08-06    peak      $193.89
        2022-09-26    trough    $151.23
        2026-01-29    peak      $495.90
        2026-07-16    trough    $364.96
        ============  =======  ==========

        Strictly alternating peak/trough from a peak: a chain of three complete pairs,
        which is the owner's pairing invariant (owner ruling 2). Windows are **±45
        calendar days** around each pin.

        **What these windows are for.** They are a **scoring target for the Stage A
        indicator-weight search** — "is this indicator cheap inside the trough windows
        and rich inside the peak windows?" They are **not** execution periods, they are
        not periods to hold or trade, and they carry **no exposure floor**. Nothing about
        a ±45d band implies a position size or a required deployment.

        **Provenance.** Human-approved set A (owner, 2026-10-03) and independently
        corroborated by ``turn_detect.detect_turns``: at ``min_move_pct=15.0`` the
        detector reproduces **all six at 0-bar offsets with exact closes** — the same
        bars, to the cent. See ``gold_v2()`` for the detector's full 20-turn set, which
        contains these six.
        """
        return _documented(
            _window("2011_peak", CycleKind.PEAK, date(2011, 8, 22)),
            _window("2015_trough", CycleKind.TROUGH, date(2015, 12, 17)),
            _window("2020_peak", CycleKind.PEAK, date(2020, 8, 6)),
            _window("2022_trough", CycleKind.TROUGH, date(2022, 9, 26)),
            _window("2026_peak", CycleKind.PEAK, date(2026, 1, 29)),
            _window("2026_trough", CycleKind.TROUGH, date(2026, 7, 16)),
        )

    @classmethod
    def gold_v2(cls) -> SdcaCycleWindows:
        """The **algorithmic** gold pin set: 20 turns, chosen by rule rather than by hand.

        Same instrument, same price source, same ±45d windows and the same scoring-target
        meaning as ``gold_v1()`` (see that docstring: a scoring target for indicator
        weights, **not** execution periods, **no** exposure floor). The only difference is
        how the turning points were chosen — here, by an algorithm over the series, so the
        set can be re-derived instead of re-argued.

        **Why 20 pins.** The granularity was *selected*, not picked. ``turn_detect``
        sweeps ``min_move_pct`` (magnitude) against ``min_separation_days`` (time);
        ``sensitivity_consolidate.select_sensitivity_level`` then takes the qualifying
        calibration with the largest ``capture_depth`` — the summed ``|separation|`` of the
        indicators that clear the frozen 0.5 bar there, with direction fitted and
        stability-checked per indicator. On GLD closes that rule chose:

        =============  =========  ==============  =========  ========
        ``min_move_``  turns      window-day      capture   qualifies
        ``pct``                    share           depth
        =============  =========  ==============  =========  ========
        **15.0**      20 (10/10) 0.2234          **15.7457**  **yes**
        10.0          34 (17/17) 0.3554          10.6792     no — loses 4 indicators
        5.0           63 (32/31) 0.5990          7.1547      no — loses 5 indicators
        =============  =========  ==============  =========  ========

        15% is the **only** qualifying level, so the depth comparison never had to break
        a tie between two qualifiers. Headcount would also have said 15%, but under depth
        the answer no longer rests on ``walcl`` clearing the bar by 0.0042 z-units.

        **Provenance.** Detector config ``TurnDetectionConfig(min_move_pct=15.0,
        min_separation_days=45, confirmation_bars=5, window_half_width_days=45)`` over the
        ``close`` column of ``GLD-USD`` (5499 bars, 2004-11-18..2026-09-29). The pins are
        landed **literally** on purpose: importing ``turn_detect`` from this module would
        be circular (``turn_detect`` already imports ``CycleKind`` / ``CycleWindow`` from
        here), and recomputing at import time would make a documented pin set depend on
        the cache being present. Reproduce them with ``detect_turns`` on the same series
        and config; they are not free to drift, because the tests pin all twenty.

        **Names** are ``<year>_<kind>``; a second turn in the same year of the same kind
        takes an ordinal suffix so a name still identifies exactly one pin
        (``2013_trough`` vs ``2013_trough_2``). A name shared with ``gold_v1()`` means
        "the same turn in both sets" — Set A is a **subset** of this set, all six pins
        with the same kind.
        """
        return _documented(
            _window("2006_peak", CycleKind.PEAK, date(2006, 5, 12)),
            _window("2006_trough", CycleKind.TROUGH, date(2006, 10, 4)),
            _window("2008_peak", CycleKind.PEAK, date(2008, 3, 17)),
            _window("2008_trough", CycleKind.TROUGH, date(2008, 11, 12)),
            _window("2011_peak", CycleKind.PEAK, date(2011, 8, 22)),
            _window("2011_trough", CycleKind.TROUGH, date(2011, 12, 29)),
            _window("2012_peak", CycleKind.PEAK, date(2012, 10, 4)),
            _window("2013_trough", CycleKind.TROUGH, date(2013, 6, 27)),
            _window("2013_peak", CycleKind.PEAK, date(2013, 8, 27)),
            _window("2013_trough_2", CycleKind.TROUGH, date(2013, 12, 19)),
            _window("2014_peak", CycleKind.PEAK, date(2014, 3, 14)),
            _window("2015_trough", CycleKind.TROUGH, date(2015, 12, 17)),
            _window("2016_peak", CycleKind.PEAK, date(2016, 7, 8)),
            _window("2016_trough", CycleKind.TROUGH, date(2016, 12, 15)),
            _window("2020_peak", CycleKind.PEAK, date(2020, 8, 6)),
            _window("2021_trough", CycleKind.TROUGH, date(2021, 3, 8)),
            _window("2022_peak", CycleKind.PEAK, date(2022, 3, 8)),
            _window("2022_trough", CycleKind.TROUGH, date(2022, 9, 26)),
            _window("2026_peak", CycleKind.PEAK, date(2026, 1, 29)),
            _window("2026_trough", CycleKind.TROUGH, date(2026, 7, 16)),
        )

    @classmethod
    def eth_research_v1(cls) -> SdcaCycleWindows:
        """Research ETH cycle pins for Stage A. Not a published backtest.

        Pins: 2018-01-13 high, 2018-12-14 low, 2021-11-10 high, 2022-06-18 low
        (ETH's cycle bottom was June 2022, earlier than BTC's November 2022).
        ±45 days each. Revisit after a calibrated ETH backtest looks comfortable.
        """
        return _documented(
            _window("2018_peak", CycleKind.PEAK, date(2018, 1, 13)),
            _window("2018_trough", CycleKind.TROUGH, date(2018, 12, 14)),
            _window("2021_peak", CycleKind.PEAK, date(2021, 11, 10)),
            _window("2022_trough", CycleKind.TROUGH, date(2022, 6, 18)),
        )


__all__ = [
    "CycleKind",
    "CycleWindow",
    "SdcaCycleWindows",
    "validate_paired_turns",
]
