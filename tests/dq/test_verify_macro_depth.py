"""Unit tests for the macro depth verifier (#4804)."""

from __future__ import annotations

import importlib.util
from datetime import date, timedelta
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "digiquant" / "scripts" / "verify_macro_depth.py"
_spec = importlib.util.spec_from_file_location("verify_macro_depth", _SCRIPT)
assert _spec is not None and _spec.loader is not None
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

pytestmark = pytest.mark.unit


def _write_series_csv(dest: Path, series: str, first: str, rows: int) -> None:
    start = date.fromisoformat(first)
    lines = [f"observation_date,{series}"]
    for i in range(rows):
        day = (start + timedelta(days=i)).isoformat()
        lines.append(f"{day},{100.0 + i * 0.01:.2f}")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _stage(tmp_path: Path, overrides: dict[str, tuple[str, int]] | None = None) -> None:
    overrides = overrides or {}
    for series, floor in mod.FLOORS.items():
        first, rows = overrides.get(series, (floor["first"], floor["rows"]))
        _write_series_csv(tmp_path / f"{series}.csv", series, first, rows)


def test_all_pass_staging_exits_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stage(tmp_path)
    monkeypatch.setattr(mod, "STAGING", tmp_path)
    assert mod.main() == 0


def test_truncated_baml_staging_exits_one_with_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stage(
        tmp_path,
        overrides={
            "BAMLH0A0HYM2": ("2023-09-30", 785),
            "BAMLC0A0CM": ("2023-09-30", 784),
        },
    )
    monkeypatch.setattr(mod, "STAGING", tmp_path)
    assert mod.main() == 1
    out = capsys.readouterr().out
    assert '"depth_ok": false' in out
    assert '"series": "BAMLH0A0HYM2"' in out
    assert '"series": "BAMLC0A0CM"' in out
    assert '"have_first": "2023-09-30"' in out
    # No healthy series is flagged: exactly the two BAML gaps.
    assert out.count('"have_first"') == 2
