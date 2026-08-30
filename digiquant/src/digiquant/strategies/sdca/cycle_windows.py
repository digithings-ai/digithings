"""Documented BTC cycle extrema for Stage A weight search.

Pin dates live here — the optimizer must not invent ad-hoc peak/trough lists.
Windows are ±45 calendar days around well-known cycle pins (2017/2021/2025
highs, 2018/2022 lows). A later 2025 high does not automatically expand this
set; edit this model if the pin should move.
"""

from __future__ import annotations

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


class SdcaCycleWindows(BaseModel):
    """Named cycle windows. ``btc_v1()`` is the checked-in BTC pin set."""

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
        2025-01-20 high (Jan 2025 ATH region). ±45 days each.
        """
        return cls(
            windows=(
                _window("2017_peak", CycleKind.PEAK, date(2017, 12, 17)),
                _window("2018_trough", CycleKind.TROUGH, date(2018, 12, 15)),
                _window("2021_peak", CycleKind.PEAK, date(2021, 11, 10)),
                _window("2022_trough", CycleKind.TROUGH, date(2022, 11, 21)),
                _window("2025_peak", CycleKind.PEAK, date(2025, 1, 20)),
            )
        )


__all__ = ["CycleKind", "CycleWindow", "SdcaCycleWindows"]
