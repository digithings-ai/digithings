"""Per-strategy subprocess isolation for the tearsheet generator (#1389).

NautilusTrader's Rust logging can only initialize once per process
(``log::set_boxed_logger``), so ``generate_tearsheets.py`` runs each strategy's
backtest in its own spawned process. These tests exercise the multi-strategy
loop wiring with the backtest mocked out (no Nautilus required): worker-result
interpretation (including a SIGABRT crash), a real spawn round-trip on the
no-data path, and ``main()``'s failure aggregation, exit code, and index merge.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "digiquant" / "scripts" / "generate_tearsheets.py"
_spec = importlib.util.spec_from_file_location("generate_tearsheets", _SCRIPT)
assert _spec is not None and _spec.loader is not None
gts = importlib.util.module_from_spec(_spec)
# Register before exec so spawned workers can resolve ``_strategy_worker`` by module name.
sys.modules["generate_tearsheets"] = gts
_spec.loader.exec_module(gts)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Worker-result interpretation (parent side of the pipe)
# ---------------------------------------------------------------------------


def test_interpret_worker_result_ok() -> None:
    entry = {"strategy": "btc_slapper"}
    got, err = gts._interpret_worker_result(("ok", entry), 0)
    assert got == entry
    assert err is None


def test_interpret_worker_result_error_message() -> None:
    got, err = gts._interpret_worker_result(("error", "KeyError: 'close'"), 1)
    assert got is None
    assert err is not None and "KeyError" in err


def test_interpret_worker_result_crash_maps_signal() -> None:
    # A Rust panic aborts the child (SIGABRT) before it can report anything:
    # the pipe yields nothing and the process exit code is -6.
    got, err = gts._interpret_worker_result(None, -6)
    assert got is None
    assert err is not None and "SIGABRT" in err


# ---------------------------------------------------------------------------
# Real spawn round-trip (backtest short-circuits before Nautilus: no data)
# ---------------------------------------------------------------------------


def test_spawned_worker_reports_failure_without_killing_parent(tmp_path: Path) -> None:
    settings = json.loads(gts.SETTINGS_PATH.read_text())
    entry, err = gts.run_strategy_isolated(
        "btc_slapper",
        "BTC-USD",
        settings,
        tmp_path / "empty-cache",
        tmp_path / "out",
        cal_source="example",
    )
    assert entry is None
    assert err is not None and "no tearsheet produced" in err


# ---------------------------------------------------------------------------
# main() loop wiring: aggregation, exit code, index.json semantics
# ---------------------------------------------------------------------------


def _strategy_ids() -> list[str]:
    return list(json.loads(gts.SETTINGS_PATH.read_text())["strategies"])


def _patch_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep main() hermetic: no .env load, no Supabase probing."""
    import digiquant.strategies.calibrations_loader as cal_loader

    monkeypatch.setattr(gts, "load_repo_env", lambda: None)
    monkeypatch.setattr(cal_loader, "pick_calibration_source", lambda **_: "example")


def _fake_runner(fail: set[str]):
    calls: list[str] = []

    def runner(
        strategy: str,
        symbol: str,
        settings: dict,
        cache_dir: Path,
        output_dir: Path,
        *,
        cal_source: str,
        push_supabase: bool = False,
        signal_delay_days: int = 0,
    ) -> tuple[dict | None, str | None]:
        calls.append(strategy)
        if strategy in fail:
            return None, "backtest process died before reporting (killed by SIGABRT)"
        return {"strategy": strategy}, None

    return runner, calls


def test_main_isolates_failure_and_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    strategies = _strategy_ids()
    assert len(strategies) >= 3
    failing = strategies[1]  # a middle strategy: the rest must still run

    out = tmp_path / "out"
    out.mkdir()
    runner, calls = _fake_runner(fail={failing})
    _patch_environment(monkeypatch)
    monkeypatch.setattr(gts, "run_strategy_isolated", runner)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_tearsheets.py",
            "--allow-example-calibrations",
            "--cache-dir",
            str(tmp_path),
            "--output-dir",
            str(out),
        ],
    )

    caplog.set_level(logging.INFO)
    with pytest.raises(SystemExit) as exc:
        gts.main()

    assert exc.value.code == 1
    # One failing strategy must not stop the others from running.
    assert calls == strategies
    written = [e["strategy"] for e in json.loads((out / "index.json").read_text())]
    assert written == [s for s in strategies if s != failing]
    # Clear per-strategy summary lines.
    assert any("FAILED" in r.message and failing in r.getMessage() for r in caplog.records)


def test_main_partial_failure_keeps_prior_index_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    strategies = _strategy_ids()
    failing = strategies[1]

    out = tmp_path / "out"
    out.mkdir()
    # Prior nightly run published all strategies.
    (out / "index.json").write_text(
        json.dumps([{"strategy": s, "stale": True} for s in strategies])
    )

    runner, _ = _fake_runner(fail={failing})
    _patch_environment(monkeypatch)
    monkeypatch.setattr(gts, "run_strategy_isolated", runner)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_tearsheets.py",
            "--allow-example-calibrations",
            "--cache-dir",
            str(tmp_path),
            "--output-dir",
            str(out),
        ],
    )

    with pytest.raises(SystemExit):
        gts.main()

    index = {e["strategy"]: e for e in json.loads((out / "index.json").read_text())}
    assert set(index) == set(strategies)  # failed strategy's card is preserved
    assert index[failing].get("stale") is True
    for s in strategies:
        if s != failing:
            assert "stale" not in index[s]  # refreshed entries replaced the stale ones


def test_main_all_success_exits_zero_and_rewrites_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    strategies = _strategy_ids()

    out = tmp_path / "out"
    out.mkdir()
    # Full-run success rewrites index.json (removed strategies are dropped).
    (out / "index.json").write_text(json.dumps([{"strategy": "retired_strategy"}]))

    runner, calls = _fake_runner(fail=set())
    _patch_environment(monkeypatch)
    monkeypatch.setattr(gts, "run_strategy_isolated", runner)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_tearsheets.py",
            "--allow-example-calibrations",
            "--cache-dir",
            str(tmp_path),
            "--output-dir",
            str(out),
        ],
    )

    gts.main()  # must not raise

    assert calls == strategies
    written = [e["strategy"] for e in json.loads((out / "index.json").read_text())]
    assert written == strategies
