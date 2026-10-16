"""EngineProvenance on BacktestResult (DIG-3391, contract DIG-945).

The DIG-945 contract: every published models.BacktestResult carries the build
that produced it (resolved nautilus_trader version + pin + root lock + balance
arithmetic + verified flag), populated once in run_backtest from the live
process; an unresolvable engine is fail-closed; one builder owns rendering.

The pin is never retyped here: every test reads it off
digiquant/pyproject.toml, the same file the implementation reads.
"""

from __future__ import annotations

import dataclasses
import hashlib
import tomllib
from importlib import metadata as _stdlib_metadata
from pathlib import Path

import pytest
from digiquant.models import (
    BacktestResult,
    apply_engine_provenance,
    build_engine_provenance,
    engine_provenance_note,
    read_nautilus_pin,
    read_root_lock_digest,
    resolved_nautilus_version,
)

from digiquant import models as models_mod

pytestmark = pytest.mark.unit


def _manifest_dir() -> Path:
    """digiquant package root, derived from the module under test."""
    root = Path(models_mod.__file__).resolve().parents[2]
    assert (root / "pyproject.toml").is_file(), f"no pyproject at {root}"
    return root


def _manifest_pin_text() -> str:
    """The nautilus_trader entry, parsed independently off the manifest."""
    with open(_manifest_dir() / "pyproject.toml", "rb") as handle:
        manifest = tomllib.load(handle)
    entries = manifest["project"]["optional-dependencies"]["nautilus"]
    hits = [str(e).strip() for e in entries if str(e).strip().startswith("nautilus_trader")]
    assert len(hits) == 1, f"expected one nautilus_trader entry, got {hits}"
    return hits[0]


def _pin_version(pin: str) -> str:
    assert "==" in pin, f"pin is not an exact specifier: {pin!r}"
    return pin.split("==", 1)[1].strip()


def _ok_result(**overrides) -> BacktestResult:
    base = {
        "run_id": "r1",
        "strategy_name": "s",
        "symbols": ["AAPL"],
        "start_time": "2024-01-01T00:00:00Z",
        "end_time": "2024-12-31T00:00:00Z",
        "status": "ok",
    }
    base.update(overrides)
    return BacktestResult(**base)


def _patch_resolved(monkeypatch, version: str | None):
    """Drive resolved_nautilus_version without touching the real install."""
    if version is None:

        def _missing(_name: str) -> str:
            raise _stdlib_metadata.PackageNotFoundError

        monkeypatch.setattr(models_mod._metadata, "version", _missing)
    else:
        monkeypatch.setattr(models_mod._metadata, "version", lambda _name: version)


def test_pin_is_read_off_the_manifest_not_retyped():
    pin = read_nautilus_pin()
    assert pin == _manifest_pin_text()
    assert pin != "unknown" and pin.startswith("nautilus_trader==")


def test_lock_digest_matches_the_root_lockfile_bytes():
    lock = _manifest_dir().parent / "uv.lock"
    assert lock.is_file(), "repo-root uv.lock missing: digest would be unreadable"
    expected = hashlib.sha256(lock.read_bytes()).hexdigest()[:12]
    assert read_root_lock_digest() == ("uv.lock", expected)
    assert len(expected) == 12 and all(c in "0123456789abcdef" for c in expected)


def test_resolved_version_matches_live_metadata_or_is_absent():
    try:
        live = _stdlib_metadata.version("nautilus-trader")
    except _stdlib_metadata.PackageNotFoundError:
        live = None
    assert resolved_nautilus_version() == live


def test_matching_engine_is_green_and_names_pin_and_lock(monkeypatch):
    pin = _manifest_pin_text()
    _patch_resolved(monkeypatch, _pin_version(pin))
    prov = build_engine_provenance(returns_series_verified=True)
    assert prov.engine == "nautilus_trader"
    assert prov.resolved_version == _pin_version(pin)
    assert prov.pin == pin
    assert prov.arithmetic == "balance_path"
    assert prov.returns_series_verified is True
    note = engine_provenance_note(prov)
    assert prov.resolved_version in note and pin in note
    assert "not citable" not in note and "!=" not in note


def test_drifted_engine_is_visible_not_fail_closed(monkeypatch):
    pin = _manifest_pin_text()
    _patch_resolved(monkeypatch, "0.0.0-test-drift")
    prov = build_engine_provenance(returns_series_verified=True)
    assert prov.resolved_version != _pin_version(pin)
    note = engine_provenance_note(prov)
    assert "0.0.0-test-drift" in note and pin in note and "!=" in note
    assert "not citable" not in note
    stamped = apply_engine_provenance(_ok_result(), prov)
    assert stamped.engine_provenance is not None
    assert stamped.status == "ok" and "engine_provenance" not in stamped.missing


def test_absent_engine_is_fail_closed(monkeypatch):
    _patch_resolved(monkeypatch, None)
    prov = build_engine_provenance(returns_series_verified=False)
    assert prov.resolved_version is None
    assert "engine unresolved — not citable" in engine_provenance_note(prov)
    stamped = apply_engine_provenance(_ok_result(), prov)
    assert stamped.status == "partial"
    assert "engine_provenance" in stamped.missing
    assert stamped.engine_provenance is not None


def test_fail_closed_never_downgrades_an_error(monkeypatch):
    _patch_resolved(monkeypatch, None)
    prov = build_engine_provenance(returns_series_verified=False)
    stamped = apply_engine_provenance(_ok_result(status="error"), prov)
    assert stamped.status == "error"
    assert "engine_provenance" in stamped.missing


def test_resolved_engine_leaves_status_and_missing_untouched(monkeypatch):
    pin = _manifest_pin_text()
    _patch_resolved(monkeypatch, _pin_version(pin))
    prov = build_engine_provenance(returns_series_verified=True)
    before = _ok_result(missing=["sharpe_ratio"])
    stamped = apply_engine_provenance(before, prov)
    assert (stamped.status, stamped.missing) == ("ok", ["sharpe_ratio"])
    assert before.engine_provenance is None, "apply must copy, not mutate"


def test_run_backtest_stamps_a_real_run():
    pytest.importorskip("nautilus_trader")
    import tempfile

    from digiquant.backtest import run_backtest
    from digiquant.data.loader import generate_synthetic_ohlcv

    df = generate_synthetic_ohlcv(["AAPL"], freq="1d")
    with tempfile.TemporaryDirectory() as tmp:
        df.write_csv(Path(tmp) / "AAPL.csv")
        result = run_backtest(strategy_name="ema_cross", symbols=["AAPL"], data_dir=tmp)
    prov = result.engine_provenance
    assert prov is not None, "run_backtest must populate the block"
    assert prov.resolved_version == resolved_nautilus_version()
    assert prov.pin == _manifest_pin_text()
    lock = _manifest_dir().parent / "uv.lock"
    assert prov.lock.file == "uv.lock"
    assert prov.lock.sha256_12 == hashlib.sha256(lock.read_bytes()).hexdigest()[:12]
    assert prov.arithmetic == "balance_path"
    assert prov.returns_series_verified == ("returns_series" not in result.missing)
    assert "engine_provenance" not in result.missing or result.status == "partial"


def test_research_dataclass_carries_no_engine_field():
    from digiquant.research import backtest as research_backtest

    names = [f.name for f in dataclasses.fields(research_backtest.BacktestResult)]
    assert not [n for n in names if n.startswith("engine")], names


def test_generate_tearsheets_renders_only_through_the_builder():
    src = (_manifest_dir() / "scripts" / "generate_tearsheets.py").read_text()
    assert "engine_provenance_note(" in src, "must append the builder output"
    assert "nautilus_trader==" not in src, "no retyped pin in the script"
    assert "importlib" not in src, "no own version logic in the script"
