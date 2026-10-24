"""Regression tests for the `digiquant prices fetch-macro` source selection.

No FRED key is normal: the fred source seals from Gloomberb (#4794), and a
set key does not dual-write the panel.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner
from digiquant.cli.prices import fetch_macro_cmd

pytestmark = pytest.mark.unit

# ─── fetch-macro sources ──────────────────────────────────────────────────


def test_fetch_macro_reads_gloomberb_without_api_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """#4794: no FRED key is normal — the fred source seals from Gloomberb.

    Yahoo still runs. No skip echo, no stale warning.
    """
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.delenv("DIGIQUANT_MARKET_DATA_BACKEND", raising=False)
    manifest = tmp_path / "macro_series.yaml"
    manifest.write_text("fred:\n  series:\n    - id: DGS10\n")
    row = {
        "source": "fred",
        "series_id": "DGS10",
        "obs_date": "2026-01-05",
        "value": 4.2,
    }
    with (
        patch(
            "digiquant.data.prices.gloomberb_macro.fetch_gloomberb",
            return_value=[row],
        ) as gloomb,
        patch(
            "digiquant.data.prices.macro_ingest.fetch_fx_yahoo",
            return_value=[
                {
                    "source": "yahoo",
                    "series_id": "FX/EUR",
                    "obs_date": "2026-01-05",
                    "value": 1.1,
                }
            ],
        ) as yahoo,
    ):
        result = CliRunner().invoke(
            fetch_macro_cmd,
            ["--manifest", str(manifest), "--sources", "fred,yahoo"],
        )
    assert result.exit_code == 0, result.output
    assert "FRED_API_KEY unset" not in result.output
    assert "#4794" not in result.output
    assert gloomb.called
    assert yahoo.called
    assert '"FX/EUR": 1' in result.output
    assert '"DGS10": 1' in result.output


def test_fetch_macro_fred_only_exits_zero_without_api_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A fred-only kick with no key fetches the Gloomberb panel."""
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.delenv("DIGIQUANT_MARKET_DATA_BACKEND", raising=False)
    manifest = tmp_path / "macro_series.yaml"
    manifest.write_text("fred:\n  series:\n    - id: DGS10\n")
    row = {
        "source": "fred",
        "series_id": "DGS10",
        "obs_date": "2026-01-05",
        "value": 4.2,
    }
    with patch(
        "digiquant.data.prices.gloomberb_macro.fetch_gloomberb",
        return_value=[row],
    ):
        result = CliRunner().invoke(
            fetch_macro_cmd,
            ["--manifest", str(manifest), "--sources", "fred"],
        )
    assert result.exit_code == 0, result.output
    assert "fred ingest skipped" not in result.output
    assert '"DGS10": 1' in result.output


def test_fetch_macro_ignores_a_set_fred_api_key(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """A set key does not dual-write: the panel stays Gloomberb-only."""
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    monkeypatch.delenv("DIGIQUANT_MARKET_DATA_BACKEND", raising=False)
    manifest = tmp_path / "macro_series.yaml"
    manifest.write_text("fred:\n  series:\n    - id: DGS10\n")
    row = {
        "source": "fred",
        "series_id": "DGS10",
        "obs_date": "2026-01-05",
        "value": 4.2,
    }
    with patch(
        "digiquant.data.prices.gloomberb_macro.fetch_gloomberb",
        return_value=[row],
    ) as gloomb:
        result = CliRunner().invoke(
            fetch_macro_cmd,
            ["--manifest", str(manifest), "--sources", "fred"],
        )
    assert result.exit_code == 0, result.output
    assert "FRED_API_KEY unset" not in result.output
    gloomb.assert_called_once()
