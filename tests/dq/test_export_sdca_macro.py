"""Unit tests for SDCA macro CSV staging (#3453, #4794 PR3).

The gloomberb panel does not serve DTWEXBGS, so the script no longer touches
the FRED observations API or fredgraph.csv: M2SL stages from the existing
Supabase rows or the sealed R2 ``fred__M2SL`` generation, and DTWEXBGS is
omitted with one warning so the dxy weight zeros loudly in the SDCA loader.
No network, no key.
"""

from __future__ import annotations

import importlib.util
import logging
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


def test_no_fred_fetch_paths_remain() -> None:
    assert not hasattr(mod, "rows_from_fred_api")
    assert not hasattr(mod, "rows_from_fredgraph")
    assert not hasattr(mod, "fetch_fred_series")


def test_series_files_match_load_sdca_extra_sources() -> None:
    assert mod.SERIES_FILES == {
        "M2SL": "M2SL.csv",
        "GVZCLS": "GVZCLS.csv",
        "WALCL": "WALCL.csv",
        "BAMLH0A0HYM2": "BAMLH0A0HYM2.csv",
        "BAMLC0A0CM": "BAMLC0A0CM.csv",
        "T5YIE": "T5YIE.csv",
        "NFCI": "NFCI.csv",
        "DFII10": "DFII10.csv",
    }


def test_export_series_writes_gvz_staging_csv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod, "rows_from_supabase", lambda _sid: [("2024-01-02", 18.5)])
    dest, source, n = mod.export_series("GVZCLS", tmp_path)
    assert source == "supabase"
    assert n == 1
    assert dest.name == "GVZCLS.csv"
    assert dest.read_text(encoding="utf-8").splitlines()[0] == "observation_date,GVZCLS"


def test_export_series_m2sl_from_r2_without_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.setattr(mod, "rows_from_supabase", lambda _sid: [])
    monkeypatch.setattr(
        mod, "rows_from_r2", lambda _sid: [("2024-01-01", 20800.5), ("2024-02-01", 20850.0)]
    )
    dest, source, n = mod.export_series("M2SL", tmp_path)
    assert source == "r2"
    assert n == 2
    assert dest is not None and dest.is_file()


def test_export_series_dtwexbgs_warns_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.setattr(
        mod, "rows_from_supabase", lambda _sid: (_ for _ in ()).throw(AssertionError("no read"))
    )
    with caplog.at_level(logging.WARNING, logger=mod.logger.name):
        dest, source, n = mod.export_series("DTWEXBGS", tmp_path)
    assert (dest, source, n) == (None, "skipped", 0)
    assert "DTWEXBGS is not on the gloomberb panel; dxy sibling CSV skipped" in caplog.text
    assert not (tmp_path / "DTWEXBGS.csv").exists()


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
