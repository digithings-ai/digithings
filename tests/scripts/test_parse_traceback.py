"""Unit tests for scripts/parse_traceback.py — stack-trace → component routing.

Agents use ``make parse-error`` / this script to map a crash onto the right
``{component}/AGENTS.md``. Wrong component routing wastes a full session.
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
SCRIPT = REPO_ROOT / "scripts" / "parse_traceback.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("parse_traceback_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["parse_traceback_under_test"] = module
    spec.loader.exec_module(module)
    return module


pt = _load()


DIGIGRAPH_TRACE = """\
Traceback (most recent call last):
  File "/workspace/digigraph/src/digigraph/server.py", line 120, in handle
    return await run()
  File "/workspace/digigraph/src/digigraph/workflow.py", line 55, in run
    raise ValueError("no tools bound")
ValueError: no tools bound
"""


def test_identify_component_prefers_src_prefix() -> None:
    assert pt.identify_component("digigraph/src/digigraph/workflow.py") == "digigraph"
    assert pt.identify_component("digikey/src/digikey/jwt.py") == "digikey"
    assert pt.identify_component("scripts/score.py") == "scripts"
    assert pt.identify_component("frontend/dashboard/lib/x.ts") == "unknown"


def test_identify_component_handles_absolute_and_windows_paths() -> None:
    abs_path = str(REPO_ROOT / "digisearch" / "src" / "digisearch" / "ingest.py")
    assert pt.identify_component(abs_path) == "digisearch"
    assert pt.identify_component(r"digiquant\src\digiquant\dashboard\portfolio\state.py") == "digiquant"


def test_parse_traceback_extracts_last_frame_and_component() -> None:
    result = pt.parse_traceback(DIGIGRAPH_TRACE)
    assert result is not None
    assert result["component"] == "digigraph"
    assert result["file"].endswith("digigraph/src/digigraph/workflow.py")
    assert result["line"] == 55
    assert result["error_type"] == "ValueError"
    assert result["message"] == "no tools bound"


def test_parse_traceback_error_only_without_frames() -> None:
    text = "RuntimeError: boom without frames\n"
    result = pt.parse_traceback(text)
    assert result is not None
    assert result["component"] == "unknown"
    assert result["file"] == ""
    assert result["line"] == 0
    assert result["error_type"] == "RuntimeError"
    assert result["message"] == "boom without frames"


def test_parse_traceback_returns_none_for_unrelated_text() -> None:
    assert pt.parse_traceback("all green, nothing to see") is None


def test_main_json_omits_full_trace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "tb.txt"
    path.write_text(DIGIGRAPH_TRACE, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["parse_traceback.py", "--input", str(path), "--format", "json"])
    code = pt.main()
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["component"] == "digigraph"
    assert "full_trace" not in payload
    assert payload["error_type"] == "ValueError"


def test_main_missing_input_still_exits_zero(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["parse_traceback.py", "--input", "/no/such/traceback.txt", "--format", "json"],
    )
    code = pt.main()
    err = capsys.readouterr().err
    assert code == 0
    assert "file not found" in err
