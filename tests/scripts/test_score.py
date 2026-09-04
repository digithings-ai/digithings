"""Unit tests for scripts/score.py — the 4-dimension self-score gate.

``make score`` / CI scoring is a heuristic checklist agents rely on before PRs.
It previously had zero unit coverage. These tests pin the load-bearing rules:

- thresholds (Security ≥8, Quality ≥8, Optimization ≥7, Accuracy ≥9)
- unified-diff line numbering for added vs removed lines
- anti-patterns only fire on *added* lines when ``only_added`` is set
- path skip fragments, legacy path suppressions, and ``# score:allow`` pragmas
- test-fixture hardcoded-secret exemption
- empty / clean diffs pass; findings drop the dimension score by 1 each
"""

# score:allow pandas, pd., todo
# fixtures embed synthetic anti-pattern diffs by design

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "score.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("score_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Unique name so concurrent suites (or score_delta imports) do not collide.
    sys.modules["score_under_test"] = module
    spec.loader.exec_module(module)
    return module


score = _load()


def _unified(path: str, body: str, start: int = 1) -> str:
    """Build a minimal unified diff for one file with ``body`` as hunk content."""
    removed = sum(1 for line in body.splitlines() if line.startswith("-"))
    # Context / other lines count toward new-file span roughly as added-side lines.
    new_span = max(1, sum(1 for line in body.splitlines() if not line.startswith("-")))
    old_span = max(1, removed) if removed else 0
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -{start},{old_span} +{start},{new_span} @@\n"
        f"{body}"
    )


# ── thresholds & scoring math ────────────────────────────────────────────────


def test_thresholds_match_documented_gates() -> None:
    assert score.THRESHOLDS == {
        "security": 8,
        "quality": 8,
        "optimization": 7,
        "accuracy": 9,
    }


def test_dimension_score_drops_one_per_finding() -> None:
    result = score.DimensionResult("security", 8)
    assert result.score == 10
    assert result.passed
    result.findings.append(
        score.Finding("security", "pandas import (use Polars)", "x.py", 1, "import pandas")
    )
    assert result.score == 9
    assert result.passed  # still ≥ 8
    for _ in range(2):
        result.findings.append(
            score.Finding("security", "pandas import (use Polars)", "x.py", 1, "import pandas")
        )
    assert result.score == 7
    assert not result.passed


# ── parse_diff_lines ─────────────────────────────────────────────────────────


def test_parse_diff_lines_numbers_added_and_skips_removed() -> None:
    diff = _unified(
        "pkg/mod.py",
        "+alpha\n-gone\n+beta\n",
        start=10,
    )
    entries = score.parse_diff_lines(diff)
    added = [(ln, content) for _f, ln, content, is_added in entries if is_added]
    removed = [(ln, content) for _f, ln, content, is_added in entries if not is_added]
    assert added == [(10, "alpha"), (11, "beta")]
    # Removed lines keep the pre-increment cursor (still at the last added line).
    assert removed == [(10, "gone")]


# ── scan: pattern detection ──────────────────────────────────────────────────


def test_scan_flags_pandas_import_on_added_python_line() -> None:
    diff = _unified("digisearch/src/digisearch/x.py", "+import pandas as pd\n")
    results = score.scan(diff)
    assert any("pandas" in f.description.lower() for f in results["security"].findings)
    assert results["security"].score < 10


def test_scan_ignores_pandas_on_removed_line() -> None:
    diff = _unified(
        "digisearch/src/digisearch/x.py", "-import pandas as pd\n+import polars as pl\n"
    )
    results = score.scan(diff)
    pandas_hits = [
        f for dim in results.values() for f in dim.findings if "pandas" in f.description.lower()
    ]
    assert pandas_hits == []


def test_scan_skips_pandas_check_on_non_python_files() -> None:
    diff = _unified("README.md", "+import pandas as pd\n")
    results = score.scan(diff)
    pandas_hits = [
        f for dim in results.values() for f in dim.findings if "pandas" in f.description.lower()
    ]
    assert pandas_hits == []


def test_scan_flags_hardcoded_secret_but_not_env_var_placeholder() -> None:
    bad = _unified(
        "digigraph/src/digigraph/cfg.py",
        '+API_KEY = "sk-live-abcdefghijklmnop"\n',
    )
    ok = _unified(
        "digigraph/src/digigraph/cfg.py",
        '+API_KEY = "$GROQ_API_KEY"\n',
    )
    bad_findings = score.scan(bad)["security"].findings
    ok_findings = score.scan(ok)["security"].findings
    assert any("hardcoded secret" in f.description for f in bad_findings)
    assert not any("hardcoded secret" in f.description for f in ok_findings)


def test_scan_exempts_hardcoded_secret_in_test_fixtures() -> None:
    diff = _unified(
        "tests/dg/test_auth.py",
        '+TOKEN = "sk-live-abcdefghijklmnop"\n',
    )
    findings = score.scan(diff)["security"].findings
    assert not any("hardcoded secret" in f.description for f in findings)


def test_scan_skips_score_py_and_design_fragments() -> None:
    for path in (
        "scripts/score.py",
        "frontend/digiweb/design/terminal/highlight-dom.js",
        "package-lock.json",
    ):
        # Concatenate so this source line does not contain a call-shaped token.
        payload = "+" + "TO" + "DO fix me later X" + "XX\n+" + "ev" + "al(user_input)\n"
        diff = _unified(path, payload)
        results = score.scan(diff)
        assert all(len(r.findings) == 0 for r in results.values()), path


def test_scan_respects_legacy_path_suppression_for_pandas() -> None:
    diff = _unified(
        "digiquant/scripts/research/preload-history.py",
        "+import pandas\n+x = pd.DataFrame()\n",
    )
    results = score.scan(diff)
    pandas_hits = [
        f
        for dim in results.values()
        for f in dim.findings
        if "pandas" in f.description.lower() or "pd." in f.description.lower()
    ]
    assert pandas_hits == []


def test_scan_respects_file_score_allow_pragma() -> None:
    """``# score:allow pandas`` in the file head suppresses pandas findings."""
    rel = "tmp_score_allow_fixture.py"
    target = REPO_ROOT / rel
    target.write_text("# score:allow pandas, pd.\nimport os\n", encoding="utf-8")
    try:
        score._FILE_ALLOW_CACHE.clear()
        diff = _unified(rel, "+import pandas\n")
        results = score.scan(diff)
        pandas_hits = [
            f for dim in results.values() for f in dim.findings if "pandas" in f.description.lower()
        ]
        assert pandas_hits == []
    finally:
        target.unlink(missing_ok=True)
        score._FILE_ALLOW_CACHE.clear()


def test_clean_diff_passes_all_thresholds() -> None:
    diff = _unified("digibase/src/digibase/x.py", '+x = 1\n+print("ok")\n')
    results = score.scan(diff)
    assert all(r.passed for r in results.values())
    assert all(r.score == 10 for r in results.values())


def test_format_json_reports_passed_and_findings() -> None:
    # Accuracy threshold is 9 — two TODO/FIXME markers → score 8 → fail the gate.
    diff = _unified("digibase/src/digibase/x.py", "+TODO one\n+FIXME two\n")
    results = score.scan(diff)
    payload = json.loads(score.format_json(results))
    assert payload["passed"] is False
    assert payload["dimensions"]["accuracy"]["passed"] is False
    assert payload["dimensions"]["accuracy"]["findings"]
    assert "file" in payload["dimensions"]["accuracy"]["findings"][0]


def test_format_json_includes_security_findings_when_present() -> None:
    diff = _unified("digisearch/src/digisearch/x.py", "+import pandas\n")
    results = score.scan(diff)
    payload = json.loads(score.format_json(results))
    assert payload["dimensions"]["security"]["findings"]
    assert payload["dimensions"]["security"]["score"] == 9
    # One security hit still clears the ≥8 threshold.
    assert payload["dimensions"]["security"]["passed"] is True


def test_main_diff_file_empty_exits_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = tmp_path / "empty.diff"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["score.py", "--diff-file", str(empty), "--format", "json"],
    )
    code = score.main()
    assert code == 0


def test_main_diff_file_with_violation_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Accuracy threshold is 9 — a single TODO drops score to 9 (still pass).
    # Stack enough accuracy hits to fail (≥2 TODOs → score 8 < 9).
    body = "+TODO one\n+FIXME two\n"
    diff_path = tmp_path / "bad.diff"
    diff_path.write_text(_unified("digibase/src/digibase/x.py", body), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["score.py", "--diff-file", str(diff_path), "--format", "json"],
    )
    code = score.main()
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert out["passed"] is False
    assert out["dimensions"]["accuracy"]["score"] <= 8


def test_scan_todo_requires_word_boundary() -> None:
    """``TODO_TOOL`` must not match the TODO/FIXME accuracy heuristic (#3528)."""
    identifier = _unified(
        "digigraph/src/digigraph/orchestration/builtin.py",
        "+TODO_TOOL = {}\n+register(TODO_TOOL)\n",
    )
    comment = _unified(
        "digigraph/src/digigraph/orchestration/builtin.py",
        "+# TODO: wire remaining tools\n",
    )
    id_hits = score.scan(identifier)["accuracy"].findings
    comment_hits = score.scan(comment)["accuracy"].findings
    assert not any("TODO/FIXME" in f.description for f in id_hits)
    assert any("TODO/FIXME" in f.description for f in comment_hits)
