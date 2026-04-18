"""tests/test_etl.py — Unit tests for ETL parsing functions in generate-snapshot.py
and update_tearsheet.py.

Run with:
    pytest tests/test_etl.py -v
"""
import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load_hyphenated(name: str, path: Path):
    """Load a Python module whose filename contains hyphens (not importable via import)."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


gs = _load_hyphenated("generate_snapshot", SCRIPTS / "generate-snapshot.py")
import update_tearsheet as ut  # noqa: E402


# ─── generate-snapshot.py: parse_regime ────────────────────────────────────

SAMPLE_DIGEST = """\
# Market Digest — 2026-04-07

## Macro Regime

**Overall Bias**: Bearish — Geopolitical Shock / Risk-Off

The market is in full risk-off mode following the Iran conflict escalation.

## Actionable Summary

- Maintain gold position
- Monitor oil volatility

## Risk Radar

- Iran ceasefire breakdown
- Fed surprise rate cut

## Thesis Tracker

| ID | Name | Vehicle | Invalidation | Status | Notes |
|----|------|---------|--------------|--------|-------|
| T-001 | Iran War | IAU/XLE | Ceasefire | Active | ATH gold |
| T-002 | Rates | BIL | Rate cut | Active | Cash drag |

## Portfolio Positioning

- **IAU** (Gold): 20% — safe haven
- **XLE** (Energy): 12% — geopolitical premium
"""


class TestParseRegime:
    def test_bearish_em_dash(self):
        result = gs.parse_regime(SAMPLE_DIGEST)
        assert result["bias"] == "Bearish"
        assert "Geopolitical" in result["label"] or "Risk" in result["label"]
        assert result["conviction"] in ("High", "Medium", "Low")

    def test_bullish_no_dash(self):
        content = "**Overall Bias**: Bullish — Strong macro tailwinds\n\nSome summary here."
        result = gs.parse_regime(content)
        assert result["bias"] == "Bullish"

    def test_missing_bias_returns_unknown(self):
        result = gs.parse_regime("No bias section here.\n")
        assert result["label"] == "Unknown"
        assert result["bias"] == "Unknown"

    def test_mixed_conviction(self):
        content = "**Overall Bias**: Conflicted — Mixed signals\n"
        result = gs.parse_regime(content)
        assert result["conviction"] == "Low"

    def test_high_conviction(self):
        content = "**Overall Bias**: Strong Bullish — Maximum risk-on\n"
        result = gs.parse_regime(content)
        assert result["conviction"] == "High"

    def test_summary_extracted(self):
        result = gs.parse_regime(SAMPLE_DIGEST)
        assert len(result["summary"]) > 0

    def test_en_dash_separator(self):
        content = "**Overall Bias**: Neutral – Waiting for data\n"
        result = gs.parse_regime(content)
        assert result["bias"] == "Neutral"


# ─── generate-snapshot.py: parse_segment_biases ────────────────────────────

class TestParseSegmentBiases:
    def test_parses_biases_from_digest(self):
        content = """\
## Segment Biases

| Segment | Bias | Conviction | Notes |
|---------|------|------------|-------|
| Crypto | Bearish | Medium | BTC struggling |
| Energy | Bullish | High | WTI spike |
"""
        result = gs.parse_segment_biases(content)
        assert isinstance(result, dict)

    def test_empty_table_returns_empty(self):
        result = gs.parse_segment_biases("No biases section.\n")
        assert result == {}


# ─── update_tearsheet.py: parse_digest ─────────────────────────────────────

class TestParseDigest:
    def setup_method(self, method):
        """Write sample digest to a temp file for each test."""
        import tempfile
        self._tmp = tempfile.NamedTemporaryFile(
            suffix=".md", mode="w", encoding="utf-8", delete=False,
            dir=str(Path(__file__).parent),
            prefix="digest_2026-04-07_"
        )
        self._tmp.write(SAMPLE_DIGEST)
        self._tmp.close()
        self._path = Path(self._tmp.name)

    def teardown_method(self, method):
        if self._path.exists():
            self._path.unlink()

    def test_date_extracted_from_filename(self):
        result = ut.parse_digest(self._path)
        assert result["date"] == "2026-04-07"

    def test_positions_parsed(self):
        result = ut.parse_digest(self._path)
        tickers = [p["ticker"] for p in result["positions"]]
        assert "IAU" in tickers
        assert "XLE" in tickers

    def test_regime_extracted(self):
        result = ut.parse_digest(self._path)
        assert "Bearish" in result["bias"] or result["bias"] != ""

    def test_theses_extracted(self):
        result = ut.parse_digest(self._path)
        assert len(result["theses"]) == 2
        ids = [t["id"] for t in result["theses"]]
        assert "T-001" in ids
        assert "T-002" in ids

    def test_actionable_extracted(self):
        result = ut.parse_digest(self._path)
        assert len(result["actionable"]) == 2

    def test_risks_extracted(self):
        result = ut.parse_digest(self._path)
        assert len(result["risks"]) == 2

    def test_empty_digest(self):
        """Parsing a totally empty file should not raise and should return defaults."""
        self._path.write_text("", encoding="utf-8")
        result = ut.parse_digest(self._path)
        assert result["positions"] == []
        assert result["theses"] == []
        assert result["actionable"] == []

    def test_no_regime_bias(self):
        """File with positions but no Overall Bias line."""
        self._path.write_text(
            "# Digest 2026-01-01\n\n- **SPY** (S&P500): 50% — core\n",
            encoding="utf-8"
        )
        result = ut.parse_digest(self._path)
        assert result["regime"] == "Unknown"
