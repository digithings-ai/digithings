"""Unit tests for the GLD options-skew enrichment pull (#4804)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[3] / "digiquant" / "scripts" / "pull_gold_enrichment.py"

_EXP_1 = 1798761600
_EXP_2 = 1801363200
_FETCHED_AT = "2026-09-30T12:00:00Z"


def _load_pull_module():
    spec = importlib.util.spec_from_file_location("pull_gold_enrichment", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _leg(side: str, strike: float, expiration: int, oi: float, vol: float) -> dict:
    return {
        "contract_symbol": f"GLD260116{side[0].upper()}{strike:08.0f}",
        "side": side,
        "strike": strike,
        "expiration": float(expiration),
        "open_interest": oi,
        "volume": vol,
    }


def _canned_chain_json() -> str:
    calls = [
        _leg("call", 270.0, _EXP_1, 100.0, 10.0),
        _leg("call", 280.0, _EXP_1, 200.0, 30.0),
        _leg("call", 270.0, _EXP_2, 800.0, 80.0),
        _leg("call", 280.0, _EXP_2, 200.0, 20.0),
    ]
    puts = [
        _leg("put", 270.0, _EXP_1, 150.0, 20.0),
        _leg("put", 280.0, _EXP_1, 450.0, 60.0),
        _leg("put", 270.0, _EXP_2, 100.0, 50.0),
        _leg("put", 280.0, _EXP_2, 150.0, 50.0),
    ]
    return json.dumps(
        {"data": {"chain": {"underlying_symbol": "GLD", "calls": calls, "puts": puts}}}
    )


def _patch_dispatcher(monkeypatch: pytest.MonkeyPatch, seen: dict) -> None:
    canned = _canned_chain_json()

    def _fake_factory():
        def _dispatch(name: str, args: dict):
            seen["name"] = name
            seen["args"] = args
            return canned

        return _dispatch

    monkeypatch.setattr(
        "digiquant.data.gloomberb.agent_tools.build_digifetch_tool_dispatcher", _fake_factory
    )


def test_snapshot_options_skew_ratios_and_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DIGIQUANT_ENRICHMENT_DIR", str(tmp_path))
    seen: dict = {}
    _patch_dispatcher(monkeypatch, seen)
    mod = _load_pull_module()

    path, metrics = mod.snapshot_options_skew(fetched_at=_FETCHED_AT)

    assert seen["name"] == "digifetch_options_chain"
    assert Path(path).parent.name == "digifetch_options_chain"
    assert metrics == {
        str(float(_EXP_1)): {"put_call_oi": 2.0, "put_call_volume": 2.0},
        str(float(_EXP_2)): {"put_call_oi": 0.25, "put_call_volume": 1.0},
    }
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    assert doc["tool"] == "digifetch_options_chain"
    assert doc["delay_notice"]


def test_snapshot_options_skew_writes_metrics_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DIGIQUANT_ENRICHMENT_DIR", str(tmp_path))
    _patch_dispatcher(monkeypatch, {})
    mod = _load_pull_module()

    path, metrics = mod.snapshot_options_skew(fetched_at=_FETCHED_AT)

    sidecar = Path(path).parent / f"{Path(path).stem}.metrics.json"
    assert sidecar.is_file()
    assert json.loads(sidecar.read_text(encoding="utf-8")) == metrics


def test_snapshot_options_skew_unwraps_live_dispatcher_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Live dispatcher answers {"content", "ok"}; the pull must use content."""
    monkeypatch.setenv("DIGIQUANT_ENRICHMENT_DIR", str(tmp_path))
    canned = _canned_chain_json()

    def _fake_factory():
        def _dispatch(name: str, args: dict):
            assert name == "digifetch_options_chain"
            return {"content": canned, "ok": True}

        return _dispatch

    monkeypatch.setattr(
        "digiquant.data.gloomberb.agent_tools.build_digifetch_tool_dispatcher", _fake_factory
    )
    mod = _load_pull_module()

    path, metrics = mod.snapshot_options_skew(fetched_at=_FETCHED_AT)

    assert Path(path).parent.name == "digifetch_options_chain"
    assert metrics[str(float(_EXP_1))]["put_call_oi"] == 2.0
