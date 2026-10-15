"""Medium-term BTC cycle pivots (DIG-1667) — ported from `claude/sdca-develop-sync`.

Pins a 15%-threshold zigzag on daily BTC closes, 2018-01-01 onward, for a
medium-term Stage A pass. Independent of the long-term `btc_v1` layer; the
two layers may overlap where a turn matters at both scales.
"""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.strategies.sdca.cycle_windows import CycleKind, SdcaCycleWindows

pytestmark = pytest.mark.unit


def test_medium_term_pivots_strictly_alternate_kind() -> None:
    windows = SdcaCycleWindows.btc_medium_term_v1().windows
    assert len(windows) > 50
    for prev, cur in zip(windows, windows[1:]):
        assert prev.kind != cur.kind, f"same-kind neighbours: {prev.name}, {cur.name}"


def test_medium_term_windows_are_ordered_and_named_once() -> None:
    windows = SdcaCycleWindows.btc_medium_term_v1().windows
    names = [w.name for w in windows]
    assert len(set(names)) == len(names)
    for w in windows:
        assert w.start <= w.end, w.name


def test_medium_term_first_window_clamped_to_floor() -> None:
    first = SdcaCycleWindows.btc_medium_term_v1().windows[0]
    assert first.start == date(2018, 1, 1)
    assert first.kind == CycleKind.PEAK


def test_medium_term_last_pin_is_right_censored_peak() -> None:
    last = SdcaCycleWindows.btc_medium_term_v1().windows[-1]
    assert last.name == "2026_08_27_peak"
    assert last.kind == CycleKind.PEAK


def test_medium_term_layer_is_independent_of_btc_v1() -> None:
    medium_names = {w.name for w in SdcaCycleWindows.btc_medium_term_v1().windows}
    long_names = {w.name for w in SdcaCycleWindows.btc_v1().windows}
    assert medium_names.isdisjoint(long_names)
    assert SdcaCycleWindows.btc_v1().windows[0].name == "2017_peak"
