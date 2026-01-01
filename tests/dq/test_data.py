"""Unit tests for digiquant data layer (Polars)."""

from __future__ import annotations

from pathlib import Path

import pytest
from digiquant.data.loader import list_symbols_from_dir

from digiquant.data import (
    OHLCV_COLUMNS,
    generate_synthetic_ohlcv,
    load_ohlcv_csv,
)


@pytest.mark.unit
class TestGenerateSyntheticOhlcv:
    """generate_synthetic_ohlcv returns Polars DataFrame with OHLCV + symbol."""

    def test_returns_dataframe_with_expected_columns(self) -> None:
        df = generate_synthetic_ohlcv(
            symbols=["AAPL", "MSFT"], start_date="2024-01-01", end_date="2024-01-10"
        )
        assert df.shape[0] > 0
        for col in OHLCV_COLUMNS:
            assert col in df.columns

    def test_one_row_per_symbol_per_day(self) -> None:
        df = generate_synthetic_ohlcv(symbols=["X"], start_date="2024-01-01", end_date="2024-01-05")
        assert df.shape[0] == 5
        assert df["symbol"].unique().to_list() == ["X"]

    def test_deterministic_with_seed(self) -> None:
        a = generate_synthetic_ohlcv(
            symbols=["A"], start_date="2024-01-01", end_date="2024-01-03", seed=1
        )
        b = generate_synthetic_ohlcv(
            symbols=["A"], start_date="2024-01-01", end_date="2024-01-03", seed=1
        )
        assert a["close"].to_list() == b["close"].to_list()


@pytest.mark.unit
class TestLoadOhlcvCsv:
    """load_ohlcv_csv reads CSV with Polars."""

    def test_loads_valid_csv(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DIGIQUANT_DATA_ROOT", str(tmp_path))
        path = tmp_path / "AAPL.csv"
        path.write_text(
            "timestamp,open,high,low,close,volume\n"
            "2024-01-01,100,101,99,100.5,1000\n"
            "2024-01-02,100.5,102,100,101,1100\n"
        )
        df = load_ohlcv_csv(path)
        assert len(df) == 2
        required = {"open", "high", "low", "close", "volume"}
        assert required.issubset(set(df.columns)), (
            f"Missing columns: {required - set(df.columns)}"
        )
        assert "close" in df.columns
        assert df["close"][0] == 100.5
        assert df["symbol"].unique().to_list() == ["AAPL"]

    def test_raises_on_missing_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DIGIQUANT_DATA_ROOT", str(tmp_path))
        with pytest.raises(FileNotFoundError):
            load_ohlcv_csv(tmp_path / "nonexistent.csv")

    def test_rejects_path_outside_data_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # REM-055: load_ohlcv_csv refuses anything outside DIGIQUANT_DATA_ROOT.
        monkeypatch.setenv("DIGIQUANT_DATA_ROOT", str(tmp_path / "data"))
        with pytest.raises(ValueError, match="DIGIQUANT_DATA_ROOT"):
            load_ohlcv_csv(str(tmp_path / "escape.csv"))

    def test_raises_on_missing_required_columns(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DIGIQUANT_DATA_ROOT", str(tmp_path))
        path = tmp_path / "bad.csv"
        path.write_text("date,price\n2024-01-01,100\n")
        with pytest.raises(ValueError, match="missing columns"):
            load_ohlcv_csv(path)


@pytest.mark.unit
class TestListSymbolsFromDir:
    """list_symbols_from_dir lists symbols from CSV filenames."""

    def test_returns_symbols_from_csv_stems(self, tmp_path: Path) -> None:
        (tmp_path / "AAPL.csv").write_text("x")
        (tmp_path / "MSFT.csv").write_text("x")
        (tmp_path / "GOOGL_ohlcv.csv").write_text("x")
        syms = list_symbols_from_dir(tmp_path)
        assert set(syms) == {"AAPL", "MSFT", "GOOGL"}

    def test_returns_empty_for_nonexistent_dir(self) -> None:
        assert list_symbols_from_dir("/nonexistent/dir") == []
