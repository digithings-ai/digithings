"""Unit tests for scripts/score_delta.py regression detection.

``make score-delta`` compares staged scores to the develop baseline and exits 1
on any dimension where current < baseline — even when both still pass absolute
thresholds. Without tests, a swap in comparison direction (``>`` vs ``<``) or a
silent "nothing staged → exit 0" short-circuit would let incremental quality
slippage through agent PR hygiene. Pure helpers are tested directly; ``main``
is exercised with git/score I/O mocked so the suite stays offline.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "score_delta.py"


def _load() -> Any:
    # score_delta imports sibling ``score`` via sys.path mutation — load once.
    name = "score_delta_under_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sd = _load()


def test_compute_regressions_empty_when_equal_or_improved() -> None:
    baseline = {d: 9 for d in sd.DIMENSIONS}
    current = {d: 9 for d in sd.DIMENSIONS}
    current["quality"] = 10
    assert sd._compute_regressions(baseline, current) == []


def test_compute_regressions_lists_only_dropped_dimensions() -> None:
    baseline = {"security": 9, "quality": 9, "optimization": 8, "accuracy": 10}
    current = {"security": 8, "quality": 9, "optimization": 7, "accuracy": 10}
    assert sd._compute_regressions(baseline, current) == ["security", "optimization"]


def test_compute_regressions_flags_drop_even_when_still_above_threshold() -> None:
    """Absolute pass is irrelevant — any drop vs baseline is a regression."""
    baseline = {"security": 10, "quality": 10, "optimization": 10, "accuracy": 10}
    current = {"security": 9, "quality": 10, "optimization": 10, "accuracy": 10}
    assert sd._compute_regressions(baseline, current) == ["security"]


def test_format_json_marks_regressed_dimensions() -> None:
    baseline = {"security": 9, "quality": 8, "optimization": 8, "accuracy": 10}
    current = {"security": 9, "quality": 7, "optimization": 8, "accuracy": 10}
    payload = json.loads(sd.format_json_output(baseline, current))
    assert payload["regression"] is True
    assert payload["regressed_dimensions"] == ["quality"]
    assert payload["dimensions"]["quality"]["delta"] == -1
    assert payload["dimensions"]["quality"]["regressed"] is True
    assert payload["dimensions"]["security"]["regressed"] is False


def test_format_table_includes_regressed_label() -> None:
    baseline = {d: 9 for d in sd.DIMENSIONS}
    current = dict(baseline)
    current["accuracy"] = 8
    text = sd.format_table(baseline, current)
    assert "REGRESSED" in text
    assert "accuracy" in text
    assert "REGRESSION detected" in text


def test_format_table_no_regression_message() -> None:
    scores = {d: 9 for d in sd.DIMENSIONS}
    text = sd.format_table(scores, scores)
    assert "No regression" in text
    assert "REGRESSION detected" not in text


def test_score_for_ref_defaults_to_ten_on_empty_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sd._score, "get_diff", lambda _ref: "")
    assert sd._score_for_ref("origin/develop") == {d: 10 for d in sd.DIMENSIONS}


def test_score_staged_reads_scan_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Dim:
        def __init__(self, score: int) -> None:
            self.score = score

    monkeypatch.setattr(sd._score, "get_diff", lambda _mode: "diff --git a/x b/x\n")
    monkeypatch.setattr(
        sd._score,
        "scan",
        lambda _diff: {
            "security": _Dim(8),
            "quality": _Dim(9),
            "optimization": _Dim(7),
            "accuracy": _Dim(10),
        },
    )
    assert sd._score_staged() == {
        "security": 8,
        "quality": 9,
        "optimization": 7,
        "accuracy": 10,
    }


def test_main_exits_zero_when_nothing_staged(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if cmd[:3] == ["git", "fetch", "origin"]:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[:3] == ["git", "diff", "--staged"]:
            return subprocess.CompletedProcess(cmd, 0, "", "")  # quiet success = empty
        raise AssertionError(cmd)

    monkeypatch.setattr(sd.subprocess, "run", _run)
    monkeypatch.setattr(sys, "argv", ["score_delta.py"])
    assert sd.main() == 0
    assert "nothing staged" in capsys.readouterr().out


def test_main_exits_one_on_regression(monkeypatch: pytest.MonkeyPatch) -> None:
    def _run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if cmd[:3] == ["git", "fetch", "origin"]:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[:3] == ["git", "diff", "--staged"]:
            return subprocess.CompletedProcess(cmd, 1, "", "")  # non-zero = has staged
        raise AssertionError(cmd)

    monkeypatch.setattr(sd.subprocess, "run", _run)
    monkeypatch.setattr(
        sd,
        "_score_for_ref",
        lambda _ref: {"security": 9, "quality": 9, "optimization": 8, "accuracy": 10},
    )
    monkeypatch.setattr(
        sd,
        "_score_staged",
        lambda: {"security": 8, "quality": 9, "optimization": 8, "accuracy": 10},
    )
    monkeypatch.setattr(sys, "argv", ["score_delta.py", "--format", "json"])
    assert sd.main() == 1


def test_main_exits_zero_when_staged_matches_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scores = {"security": 9, "quality": 9, "optimization": 8, "accuracy": 10}

    def _run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if cmd[:3] == ["git", "fetch", "origin"]:
            return subprocess.CompletedProcess(cmd, 1, "", "offline")  # warn path
        if cmd[:3] == ["git", "diff", "--staged"]:
            return subprocess.CompletedProcess(cmd, 1, "", "")
        raise AssertionError(cmd)

    monkeypatch.setattr(sd.subprocess, "run", _run)
    monkeypatch.setattr(sd, "_score_for_ref", lambda _ref: scores)
    monkeypatch.setattr(sd, "_score_staged", lambda: scores)
    monkeypatch.setattr(sys, "argv", ["score_delta.py"])
    assert sd.main() == 0
