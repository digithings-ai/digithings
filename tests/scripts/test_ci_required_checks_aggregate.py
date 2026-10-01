"""Unit tests for scripts/ci_required_checks_aggregate.py.

Pins that every ``required-checks`` dependency blocks the develop merge gate.
The former ``score`` advisory exception left with the score tooling (#4868).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci_required_checks_aggregate.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("ci_required_checks_aggregate", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["ci_required_checks_aggregate"] = module
    spec.loader.exec_module(module)
    return module


agg = _load()


def test_no_advisory_jobs_remain() -> None:
    assert agg.ADVISORY_JOBS == frozenset()


def test_any_failure_blocks() -> None:
    results = {
        "changes": {"result": "success"},
        "digigraph": {"result": "failure"},
        "ruff-and-scripts": {"result": "skipped"},
    }
    blocking, advisory = agg.classify_needs(results)
    assert blocking == {"digigraph": "failure"}
    assert advisory == {}


def test_component_failure_still_blocks() -> None:
    results = {
        "digigraph": {"result": "failure"},
        "ruff-and-scripts": {"result": "success"},
    }
    blocking, advisory = agg.classify_needs(results)
    assert blocking == {"digigraph": "failure"}
    assert advisory == {}


def test_cancelled_is_blocking_for_non_advisory() -> None:
    results = {"ruff-and-scripts": {"result": "cancelled"}}
    blocking, advisory = agg.classify_needs(results)
    assert blocking == {"ruff-and-scripts": "cancelled"}
    assert advisory == {}


def test_main_exits_zero_when_all_pass(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(
        "RESULTS",
        json.dumps({"digigraph": {"result": "success"}, "changes": {"result": "success"}}),
    )
    assert agg.main([]) == 0
    out = capsys.readouterr().out
    assert "All required jobs passed" in out


def test_main_exits_one_on_blocking_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(
        "RESULTS",
        json.dumps({"digibase": {"result": "failure"}, "changes": {"result": "success"}}),
    )
    assert agg.main([]) == 1
    assert "Failed or cancelled required jobs" in capsys.readouterr().out
