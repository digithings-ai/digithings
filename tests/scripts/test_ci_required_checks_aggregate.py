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


# ── The push tightening (DIG-2305) ───────────────────────────────────────────
# `skipped` is tolerated by design — it is what lets this aggregator exist at all,
# since no path-gated job can be named in develop's branch protection. The defect was
# that the tolerance also covered a lane which never ran on develop at all: npm-audit
# reported `skipped` while this gate reported `success`. That lane has since been
# deleted, so ALWAYS_EVALUATED_ON_PUSH is empty; these pin the mechanism with a
# stand-in lane name passed (or patched) in explicitly.

LANE = "always-on-push-lane"
ALWAYS = frozenset({LANE})


def test_declared_lane_skipped_blocks_on_a_push(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUSH_EVENT", "true")
    results = {LANE: {"result": "skipped"}, "changes": {"result": "success"}}
    blocking, advisory = agg.classify_needs(
        results, require_evaluated=True, always_evaluated=ALWAYS
    )
    assert list(blocking) == [LANE]
    assert advisory == {}


def test_declared_lane_skipped_is_tolerated_on_a_pull_request() -> None:
    results = {LANE: {"result": "skipped"}, "changes": {"result": "success"}}
    blocking, _ = agg.classify_needs(results, require_evaluated=False, always_evaluated=ALWAYS)
    assert blocking == {}


def test_declared_lane_success_still_passes_on_a_push() -> None:
    results = {LANE: {"result": "success"}, "changes": {"result": "success"}}
    blocking, _ = agg.classify_needs(results, require_evaluated=True, always_evaluated=ALWAYS)
    assert blocking == {}


def test_other_path_gated_skips_stay_tolerated_on_a_push() -> None:
    """Only the declared set tightens — the rest of ci.yml is still path-gated.

    Without this the fix could read as "no skips on develop", which would turn every
    docs-only push into a red required-checks.
    """
    results = {
        "digibase": {"result": "skipped"},
        "actionlint": {"result": "skipped"},
        LANE: {"result": "success"},
    }
    blocking, _ = agg.classify_needs(results, require_evaluated=True, always_evaluated=ALWAYS)
    assert blocking == {}


def test_main_reads_the_push_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(agg, "ALWAYS_EVALUATED_ON_PUSH", ALWAYS)
    monkeypatch.setenv(
        "RESULTS", json.dumps({LANE: {"result": "skipped"}, "changes": {"result": "success"}})
    )

    monkeypatch.setenv("PUSH_EVENT", "true")
    assert agg.main([]) == 1
    assert LANE in capsys.readouterr().out

    # GitHub renders a boolean context as the string "true"; a `false` push must not
    # inherit the tightening, and neither must an unset variable.
    monkeypatch.setenv("PUSH_EVENT", "false")
    assert agg.main([]) == 0
    monkeypatch.delenv("PUSH_EVENT")
    assert agg.main([]) == 0
