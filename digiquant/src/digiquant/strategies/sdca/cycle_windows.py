"""Documented per-asset cycle extrema for Stage A weight search.

Pin dates live here — the optimizer must not invent ad-hoc peak/trough lists.
Each asset has its own pin set (BTC v1, ETH research v1, …). Windows are
±45 calendar days around well-known cycle pins. A later high does not
automatically expand a set; edit the named factory if the pin should move.
"""

from __future__ import annotations

from datetime import date, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

_HALF_WINDOW = timedelta(days=45)
_MEDIUM_TERM_FLOOR = date(2018, 1, 1)


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


def _window(
    name: str, kind: CycleKind, pin: date, half_window: timedelta = _HALF_WINDOW
) -> CycleWindow:
    return CycleWindow(name=name, kind=kind, start=pin - half_window, end=pin + half_window)


def _medium_window(name: str, kind: CycleKind, pin: date, half_window_days: int) -> CycleWindow:
    """Like ``_window``, but clamps ``start`` to ``_MEDIUM_TERM_FLOOR``.

    Needed only for the first pivot in ``_MEDIUM_TERM_PIVOTS``: its
    half-window is sized from its right-hand neighbor (there's no
    left-hand one within the 2018+ series), which can push ``start``
    before the series' own 2018-01-01 floor.
    """
    half = timedelta(days=half_window_days)
    return CycleWindow(
        name=name, kind=kind, start=max(pin - half, _MEDIUM_TERM_FLOOR), end=pin + half
    )


# Percentage-threshold zigzag on daily BTC-USD closes, 15% threshold,
# 2018-01-01 onward (matches the strategy's own tuning window). Each entry
# is (name, kind, pin, half_window_days) -- half_window_days is
# min(20, half the gap to the nearer neighbor pivot), floored at 2, since
# real medium-term swings can reverse within days (2021's parabolic run,
# the March 2024 top-to-crash) and a flat +/-20d window would make
# adjacent opposite-kind windows blanket each other there. See
# ``btc_medium_term_v1`` for the full derivation note.
_MEDIUM_TERM_PIVOTS: tuple[tuple[str, CycleKind, date, int], ...] = (
    ("2018_01_06_peak", CycleKind.PEAK, date(2018, 1, 6), 15),
    ("2018_02_05_trough", CycleKind.TROUGH, date(2018, 2, 5), 13),
    ("2018_03_04_peak", CycleKind.PEAK, date(2018, 3, 4), 13),
    ("2018_04_06_trough", CycleKind.TROUGH, date(2018, 4, 6), 14),
    ("2018_05_05_peak", CycleKind.PEAK, date(2018, 5, 5), 14),
    ("2018_06_28_trough", CycleKind.TROUGH, date(2018, 6, 28), 13),
    ("2018_07_24_peak", CycleKind.PEAK, date(2018, 7, 24), 8),
    ("2018_08_10_trough", CycleKind.TROUGH, date(2018, 8, 10), 8),
    ("2018_09_04_peak", CycleKind.PEAK, date(2018, 9, 4), 12),
    ("2018_12_15_trough", CycleKind.TROUGH, date(2018, 12, 15), 2),
    ("2018_12_20_peak", CycleKind.PEAK, date(2018, 12, 20), 2),
    ("2019_02_07_trough", CycleKind.TROUGH, date(2019, 2, 7), 20),
    ("2019_06_26_peak", CycleKind.PEAK, date(2019, 6, 26), 2),
    ("2019_07_01_trough", CycleKind.TROUGH, date(2019, 7, 1), 2),
    ("2019_07_09_peak", CycleKind.PEAK, date(2019, 7, 9), 3),
    ("2019_07_16_trough", CycleKind.TROUGH, date(2019, 7, 16), 3),
    ("2019_08_08_peak", CycleKind.PEAK, date(2019, 8, 8), 11),
    ("2019_10_24_trough", CycleKind.TROUGH, date(2019, 10, 24), 2),
    ("2019_10_27_peak", CycleKind.PEAK, date(2019, 10, 27), 2),
    ("2019_12_17_trough", CycleKind.TROUGH, date(2019, 12, 17), 20),
    ("2020_02_14_peak", CycleKind.PEAK, date(2020, 2, 14), 13),
    ("2020_03_12_trough", CycleKind.TROUGH, date(2020, 3, 12), 13),
    ("2020_08_17_peak", CycleKind.PEAK, date(2020, 8, 17), 11),
    ("2020_09_08_trough", CycleKind.TROUGH, date(2020, 9, 8), 11),
    ("2021_01_08_peak", CycleKind.PEAK, date(2021, 1, 8), 9),
    ("2021_01_27_trough", CycleKind.TROUGH, date(2021, 1, 27), 9),
    ("2021_02_21_peak", CycleKind.PEAK, date(2021, 2, 21), 3),
    ("2021_02_28_trough", CycleKind.TROUGH, date(2021, 2, 28), 3),
    ("2021_03_13_peak", CycleKind.PEAK, date(2021, 3, 13), 6),
    ("2021_03_25_trough", CycleKind.TROUGH, date(2021, 3, 25), 6),
    ("2021_04_13_peak", CycleKind.PEAK, date(2021, 4, 13), 6),
    ("2021_04_25_trough", CycleKind.TROUGH, date(2021, 4, 25), 6),
    ("2021_05_08_peak", CycleKind.PEAK, date(2021, 5, 8), 6),
    ("2021_06_08_trough", CycleKind.TROUGH, date(2021, 6, 8), 3),
    ("2021_06_14_peak", CycleKind.PEAK, date(2021, 6, 14), 3),
    ("2021_07_20_trough", CycleKind.TROUGH, date(2021, 7, 20), 18),
    ("2021_09_06_peak", CycleKind.PEAK, date(2021, 9, 6), 7),
    ("2021_09_21_trough", CycleKind.TROUGH, date(2021, 9, 21), 7),
    ("2021_11_08_peak", CycleKind.PEAK, date(2021, 11, 8), 20),
    ("2022_01_22_trough", CycleKind.TROUGH, date(2022, 1, 22), 12),
    ("2022_02_15_peak", CycleKind.PEAK, date(2022, 2, 15), 3),
    ("2022_02_21_trough", CycleKind.TROUGH, date(2022, 2, 21), 3),
    ("2022_03_29_peak", CycleKind.PEAK, date(2022, 3, 29), 18),
    ("2022_06_18_trough", CycleKind.TROUGH, date(2022, 6, 18), 20),
    ("2022_08_13_peak", CycleKind.PEAK, date(2022, 8, 13), 12),
    ("2022_09_06_trough", CycleKind.TROUGH, date(2022, 9, 6), 3),
    ("2022_09_12_peak", CycleKind.PEAK, date(2022, 9, 12), 3),
    ("2022_09_21_trough", CycleKind.TROUGH, date(2022, 9, 21), 4),
    ("2022_11_05_peak", CycleKind.PEAK, date(2022, 11, 5), 8),
    ("2022_11_21_trough", CycleKind.TROUGH, date(2022, 11, 21), 8),
    ("2023_02_20_peak", CycleKind.PEAK, date(2023, 2, 20), 9),
    ("2023_03_10_trough", CycleKind.TROUGH, date(2023, 3, 10), 9),
    ("2023_04_14_peak", CycleKind.PEAK, date(2023, 4, 14), 17),
    ("2023_06_14_trough", CycleKind.TROUGH, date(2023, 6, 14), 14),
    ("2023_07_13_peak", CycleKind.PEAK, date(2023, 7, 13), 14),
    ("2023_09_11_trough", CycleKind.TROUGH, date(2023, 9, 11), 20),
    ("2024_01_08_peak", CycleKind.PEAK, date(2024, 1, 8), 7),
    ("2024_01_22_trough", CycleKind.TROUGH, date(2024, 1, 22), 7),
    ("2024_03_13_peak", CycleKind.PEAK, date(2024, 3, 13), 3),
    ("2024_03_19_trough", CycleKind.TROUGH, date(2024, 3, 19), 3),
    ("2024_04_08_peak", CycleKind.PEAK, date(2024, 4, 8), 10),
    ("2024_05_01_trough", CycleKind.TROUGH, date(2024, 5, 1), 9),
    ("2024_05_20_peak", CycleKind.PEAK, date(2024, 5, 20), 9),
    ("2024_07_07_trough", CycleKind.TROUGH, date(2024, 7, 7), 10),
    ("2024_07_28_peak", CycleKind.PEAK, date(2024, 7, 28), 4),
    ("2024_08_05_trough", CycleKind.TROUGH, date(2024, 8, 5), 4),
    ("2024_08_25_peak", CycleKind.PEAK, date(2024, 8, 25), 6),
    ("2024_09_06_trough", CycleKind.TROUGH, date(2024, 9, 6), 6),
    ("2025_01_21_peak", CycleKind.PEAK, date(2025, 1, 21), 20),
    ("2025_04_08_trough", CycleKind.TROUGH, date(2025, 4, 8), 20),
    ("2025_10_06_peak", CycleKind.PEAK, date(2025, 10, 6), 20),
    ("2026_02_05_trough", CycleKind.TROUGH, date(2026, 2, 5), 20),
    ("2026_05_10_peak", CycleKind.PEAK, date(2026, 5, 10), 20),
    ("2026_06_30_trough", CycleKind.TROUGH, date(2026, 6, 30), 20),
    ("2026_08_27_peak", CycleKind.PEAK, date(2026, 8, 27), 20),
)


class SdcaCycleWindows(BaseModel):
    """Named cycle windows. ``btc_v1()`` / ``eth_research_v1()`` are pin sets."""

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
        2025-10-06 high. ±45 days each.

        The 2025 pin was originally 2025-01-20 (that region's local high on
        the way up). Chris's 2026-09-04 chart review identified the actual
        cycle top as later and higher; 2025-10-06 ($124,720) is confirmed by
        a subsequent ~53% drawdown into the 2026-06-30 trough. 2025-01-20
        remains a real pin at medium-term scale -- see
        ``btc_medium_term_v1``'s ``2025_01_21_peak``.
        """
        return cls(
            windows=(
                _window("2017_peak", CycleKind.PEAK, date(2017, 12, 17)),
                _window("2018_trough", CycleKind.TROUGH, date(2018, 12, 15)),
                _window("2021_peak", CycleKind.PEAK, date(2021, 11, 10)),
                _window("2022_trough", CycleKind.TROUGH, date(2022, 11, 21)),
                _window("2025_peak", CycleKind.PEAK, date(2025, 10, 6)),
            )
        )

    @classmethod
    def btc_medium_term_v1(cls) -> SdcaCycleWindows:
        """Medium-term BTC pullback/rally pins for a medium-term Stage A pass.

        Derived from a percentage-threshold zigzag on daily closes (15%
        threshold, 2018-01-01 onward -- matches the strategy's own tuning
        window). A zigzag flips the tracked extreme on every threshold-sized
        reversal, which guarantees strict peak/trough alternation by
        construction. This replaces an earlier local-extrema-plus-prominence
        approach whose fallback logic could silently overwrite the
        previously-kept *opposite*-kind pin, producing runs of same-kind
        pins -- Chris's 2026-09-04 chart review caught this directly ("I
        find we have a lot more bottoms than tops"), plus a specific missing
        March 2022 top and missing bottoms/tops within the 2018 decline and
        the 2023-2024 uptrend. All of those are now individual pins below.

        Unlike the old set, this one does NOT exclude pivots that fall
        inside a ``btc_v1()`` long-term window. Excluding a single, unpaired
        pivot from a strictly-alternating series can break the alternation
        (verified against the 2021-11-08 peak, which sits inside the
        long-term 2021_peak window); the two layers are independent and
        allowed to overlap where a turn matters at both scales.

        Each pin's half-window is ``min(20, half the gap to the nearer
        neighbor pivot)``, floored at 2 days -- real medium-term swings can
        reverse within days (2021's parabolic run, the March 2024
        top-to-crash), and a flat +/-20d window would make adjacent
        opposite-kind windows blanket each other there.

        The final pin, 2026-08-27 peak, is right-censored: a real local
        high, not yet confirmed by a full 15% reversal (only a ~4% pullback
        as of 2026-09-02).
        """
        return cls(
            windows=tuple(
                _medium_window(name, kind, pin, half_window_days)
                for name, kind, pin, half_window_days in _MEDIUM_TERM_PIVOTS
            )
        )

    @classmethod
    def eth_research_v1(cls) -> SdcaCycleWindows:
        """Research ETH cycle pins for Stage A. Not a published backtest.

        Pins: 2018-01-13 high, 2018-12-14 low, 2021-11-10 high, 2022-06-18 low
        (ETH's cycle bottom was June 2022, earlier than BTC's November 2022).
        ±45 days each. Revisit after a calibrated ETH backtest looks comfortable.
        """
        return cls(
            windows=(
                _window("2018_peak", CycleKind.PEAK, date(2018, 1, 13)),
                _window("2018_trough", CycleKind.TROUGH, date(2018, 12, 14)),
                _window("2021_peak", CycleKind.PEAK, date(2021, 11, 10)),
                _window("2022_trough", CycleKind.TROUGH, date(2022, 6, 18)),
            )
        )


__all__ = ["CycleKind", "CycleWindow", "SdcaCycleWindows"]
