"""Regression tests for score:allow pragma keys in scripts/score.py."""

# score:allow notimplementederror stub, todo, pandas
# test fixtures embed synthetic anti-pattern diffs by design

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "score.py"
TARGET_FILE = "tests/scripts/fixtures/score_allow_pragma_target.py"


def _load_score():
    mod_name = "score_allow_pragma_test"
    spec = importlib.util.spec_from_file_location(mod_name, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


score = _load_score()


def _unified_diff(added_lines: list[str]) -> str:
    body = "\n".join(f"+{line}" for line in added_lines)
    return (
        f"--- a/{TARGET_FILE}\n"
        f"+++ b/{TARGET_FILE}\n"
        "@@ -1,2 +1,3 @@\n"
        " def stub():\n"
        "     pass\n"
        f"{body}\n"
    )


@pytest.fixture
def target_path():
    path = REPO_ROOT / TARGET_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    score._FILE_ALLOW_CACHE.clear()
    yield path
    score._FILE_ALLOW_CACHE.clear()
    if path.exists():
        path.unlink()


def test_notimplementederror_stub_suppressed_with_pragma(target_path):
    target_path.write_text(
        "# score:allow notimplementederror stub\n"
        "# intentional broker stub (human gate)\n"
        "def stub():\n"
        "    pass\n",
        encoding="utf-8",
    )
    results = score.scan(_unified_diff(["    raise NotImplementedError"]))
    findings = [
        f
        for f in results["accuracy"].findings
        if f.file == TARGET_FILE and "notimplementederror" in f.description.lower()
    ]
    assert findings == []


def test_notimplementederror_stub_fires_without_pragma(target_path):
    target_path.write_text("def stub():\n    pass\n", encoding="utf-8")
    results = score.scan(_unified_diff(["    raise NotImplementedError"]))
    findings = [
        f
        for f in results["accuracy"].findings
        if f.file == TARGET_FILE and "notimplementederror" in f.description.lower()
    ]
    assert len(findings) == 1


def test_notimplementederror_pragma_does_not_suppress_pandas(target_path):
    target_path.write_text(
        "# score:allow notimplementederror stub\n"
        "# reason: broker boundary stub only\n"
        "def stub():\n"
        "    pass\n",
        encoding="utf-8",
    )
    results = score.scan(_unified_diff(["import pandas as pd"]))
    findings = [
        f
        for f in results["security"].findings
        if f.file == TARGET_FILE and "pandas" in f.description.lower()
    ]
    assert len(findings) == 1


def test_notimplementederror_emdash_reason_on_pragma_line_is_no_op(target_path):
    target_path.write_text(
        "# score:allow notimplementederror stub — reason\n"
        "def stub():\n"
        "    pass\n",
        encoding="utf-8",
    )
    results = score.scan(_unified_diff(["    raise NotImplementedError"]))
    findings = [
        f
        for f in results["accuracy"].findings
        if f.file == TARGET_FILE and "notimplementederror" in f.description.lower()
    ]
    assert len(findings) == 1


def test_todo_suppressed_with_pragma(target_path):
    target_path.write_text(
        "# score:allow todo\n"
        "# intentional deferred marker (human gate)\n"
        "def stub():\n"
        "    pass\n",
        encoding="utf-8",
    )
    results = score.scan(_unified_diff(["    # TODO: wire broker adapter"]))
    findings = [
        f
        for f in results["accuracy"].findings
        if f.file == TARGET_FILE and "todo" in f.description.lower()
    ]
    assert findings == []


def test_todo_fires_without_pragma(target_path):
    target_path.write_text("def stub():\n    pass\n", encoding="utf-8")
    results = score.scan(_unified_diff(["    # TODO: wire broker adapter"]))
    findings = [
        f
        for f in results["accuracy"].findings
        if f.file == TARGET_FILE and "todo" in f.description.lower()
    ]
    assert len(findings) == 1


def test_todo_pragma_does_not_suppress_pandas(target_path):
    target_path.write_text(
        "# score:allow todo\n"
        "# reason: deliberate TODO marker only\n"
        "def stub():\n"
        "    pass\n",
        encoding="utf-8",
    )
    results = score.scan(_unified_diff(["import pandas as pd"]))
    findings = [
        f
        for f in results["security"].findings
        if f.file == TARGET_FILE and "pandas" in f.description.lower()
    ]
    assert len(findings) == 1


def test_todo_emdash_reason_on_pragma_line_is_no_op(target_path):
    target_path.write_text(
        "# score:allow todo — reason\n"
        "def stub():\n"
        "    pass\n",
        encoding="utf-8",
    )
    results = score.scan(_unified_diff(["    # TODO: wire broker adapter"]))
    findings = [
        f
        for f in results["accuracy"].findings
        if f.file == TARGET_FILE and "todo" in f.description.lower()
    ]
    assert len(findings) == 1
