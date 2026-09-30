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


def _patch_canned(monkeypatch: pytest.MonkeyPatch, seen: dict, payloads: dict) -> None:
    """Route each tool name to its canned payload; record every call."""

    def _fake_factory():
        def _dispatch(name: str, args: dict):
            seen.setdefault("calls", []).append({"name": name, "args": args})
            key = args.get("series_id", name) if isinstance(args, dict) else name
            return payloads[key]

        return _dispatch

    monkeypatch.setattr(
        "digiquant.data.gloomberb.agent_tools.build_digifetch_tool_dispatcher", _fake_factory
    )


def _canned_13f_json() -> str:
    return json.dumps(
        {
            "data": {
                "funds": [
                    {"name": "Bridgewater Associates", "cik": "0001350694", "tickers": ["GLD"]},
                    {"name": "Millennium Management", "cik": "0001273087", "tickers": ["GLD"]},
                ]
            }
        }
    )


def _canned_calendar_json() -> str:
    return json.dumps(
        {
            "data": {
                "events": [
                    {"id": "ev-1", "date": "2026-10-01", "country": "US", "event": "ISM PMI"},
                    {"id": "ev-2", "date": "2026-10-02", "country": "US", "event": "Payrolls"},
                ]
            }
        }
    )


def _canned_news_json() -> str:
    return json.dumps(
        {
            "data": {
                "items": [
                    {"id": "n-1", "headline": "Gold hits record on rate-cut bets"},
                    {"id": "n-2", "headline": "GLD inflows climb for third week"},
                ]
            }
        }
    )


def _canned_series_json() -> str:
    return json.dumps(
        {
            "data": {
                "observations": [
                    {"date": "2026-09-29", "value": 2650.5},
                    {"date": "2026-09-26", "value": 2648.0},
                ],
                "info": {"id": "GOLDPMGBD228NLBM", "title": "LBMA Gold PM fix"},
            }
        }
    )


def _canned_error_json() -> str:
    return json.dumps(
        {
            "data": {
                "code": "not_found",
                "message": "Unknown series 'BOGUS-ID-XYZ'",
                "retryable": False,
            }
        }
    )


def test_snapshot_13f_gld(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_ENRICHMENT_DIR", str(tmp_path))
    seen: dict = {}
    _patch_canned(monkeypatch, seen, {"digifetch_13f_funds": _canned_13f_json()})
    mod = _load_pull_module()

    path = mod.snapshot_13f_gld(fetched_at=_FETCHED_AT)

    assert Path(path).parent.name == "digifetch_13f_funds"
    assert seen["calls"] == [
        {"name": "digifetch_13f_funds", "args": {"what": "tickers", "tickers": ["GLD"]}}
    ]
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    assert doc["tool"] == "digifetch_13f_funds"
    assert doc["params"] == {"what": "tickers", "tickers": ["GLD"]}
    assert doc["delay_notice"]


def test_snapshot_econ_calendar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_ENRICHMENT_DIR", str(tmp_path))
    seen: dict = {}
    _patch_canned(monkeypatch, seen, {"digifetch_econ_calendar": _canned_calendar_json()})
    mod = _load_pull_module()

    path = mod.snapshot_econ_calendar(fetched_at=_FETCHED_AT)

    assert Path(path).parent.name == "digifetch_econ_calendar"
    assert seen["calls"] == [{"name": "digifetch_econ_calendar", "args": {}}]
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    assert doc["tool"] == "digifetch_econ_calendar"
    assert doc["params"] == {}
    assert doc["delay_notice"]


def test_snapshot_gold_news(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_ENRICHMENT_DIR", str(tmp_path))
    seen: dict = {}
    _patch_canned(monkeypatch, seen, {"digifetch_news": _canned_news_json()})
    mod = _load_pull_module()

    path = mod.snapshot_gold_news(fetched_at=_FETCHED_AT)

    assert Path(path).parent.name == "digifetch_news"
    assert len(seen["calls"]) == 1
    assert seen["calls"][0]["name"] == "digifetch_news"
    assert seen["calls"][0]["args"]["ticker"] == "GLD"
    assert seen["calls"][0]["args"]["feed"] == "ticker"
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    assert doc["tool"] == "digifetch_news"
    assert doc["delay_notice"]


def test_probe_lbma_hit_and_miss(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_ENRICHMENT_DIR", str(tmp_path))
    seen: dict = {}
    _patch_canned(
        monkeypatch,
        seen,
        {
            "GOLDPMGBD228NLBM": _canned_series_json(),
            "BOGUS-ID-XYZ": _canned_error_json(),
        },
    )
    mod = _load_pull_module()
    monkeypatch.setattr(mod, "LBMA_CANDIDATES", ("GOLDPMGBD228NLBM", "BOGUS-ID-XYZ"))

    out = mod.probe_lbma_series(fetched_at=_FETCHED_AT)

    assert set(out) == {"GOLDPMGBD228NLBM", "BOGUS-ID-XYZ"}
    assert out["BOGUS-ID-XYZ"] is None
    assert out["GOLDPMGBD228NLBM"] is not None
    assert Path(out["GOLDPMGBD228NLBM"]).parent.name == "digifetch_econ_series"
    pages = list((tmp_path / "digifetch_econ_series").glob("[0-9]*__*.json"))
    assert len(pages) == 1
    assert Path(pages[0]).read_text(encoding="utf-8")
