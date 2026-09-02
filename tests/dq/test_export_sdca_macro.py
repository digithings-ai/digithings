"""Unit tests for SDCA macro CSV staging (#3453)."""

from __future__ import annotations

import importlib.util
from io import BytesIO
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "digiquant" / "scripts" / "export_sdca_macro.py"
_spec = importlib.util.spec_from_file_location("export_sdca_macro", _SCRIPT)
assert _spec is not None and _spec.loader is not None
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

pytestmark = pytest.mark.unit


def test_write_observation_csv_round_trips_fred_shape(tmp_path: Path) -> None:
    dest = tmp_path / "M2SL.csv"
    mod.write_observation_csv([("2020-02-01", 15410.0), ("2020-01-01", 15400.1)], dest)
    text = dest.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "observation_date,M2SL"
    assert "2020-01-01,15400.1" in text
    from digiquant.strategies.sdca.indicator_catalog import load_date_value_frame

    dates, values = load_date_value_frame(dest)
    by_date = dict(zip([d.isoformat() for d in dates.to_list()], values.to_list(), strict=True))
    assert by_date["2020-01-01"] == pytest.approx(15400.1)
    assert by_date["2020-02-01"] == pytest.approx(15410.0)


def test_write_observation_csv_rejects_empty(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty"):
        mod.write_observation_csv([], tmp_path / "M2SL.csv")


def test_rows_from_fredgraph_parses_observation_date() -> None:
    csv = b"observation_date,DTWEXBGS\n2024-01-02,120.5\n2024-01-03,.\n2024-01-04,121.0\n"

    class _Resp(BytesIO):
        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def opener(_url: str) -> _Resp:
        return _Resp(csv)

    rows = mod.rows_from_fredgraph("DTWEXBGS", opener=opener)
    assert rows == [("2024-01-02", 120.5), ("2024-01-04", 121.0)]


def test_series_files_match_load_sdca_extra_sources() -> None:
    assert mod.SERIES_FILES == {"M2SL": "M2SL.csv", "DTWEXBGS": "DTWEXBGS.csv"}


def test_export_series_falls_through_when_fred_api_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    monkeypatch.setattr(mod, "rows_from_supabase", lambda _sid: [])

    def _boom(_sid: str, _key: str) -> list[tuple[str, float]]:
        raise RuntimeError("fred 500")

    monkeypatch.setattr(mod, "rows_from_fred_api", _boom)
    monkeypatch.setattr(mod, "rows_from_fredgraph", lambda _sid: [("2024-01-02", 1.0)])
    dest, source, n = mod.export_series("M2SL", tmp_path)
    assert source == "fredgraph"
    assert n == 1
    assert dest.is_file()


def test_btc_sdca_is_not_a_slapper_calibration_target() -> None:
    """Nightly verify must not require strategy_calibrations for btc_sdca (#3456)."""
    import json

    from digiquant.strategies.calibrations_loader import entry_is_slapper

    settings_path = (
        Path(__file__).resolve().parents[2]
        / "digiquant"
        / "src"
        / "digiquant"
        / "strategies"
        / "settings.json"
    )
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    entry = settings["strategies"]["btc_sdca"]
    assert not entry_is_slapper(entry, settings)
