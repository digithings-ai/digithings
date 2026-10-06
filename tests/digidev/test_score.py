"""Unit tests for ``digidev/scripts/score.py`` — the vendored digidev quality gate.

These are characterization tests: ``digidev/`` is a vendored distributable that
ships with zero tests, and its scorer is the only thing standing between a
staged change and a blind self-score. Each test asserts observable behaviour of
the gate (which findings it raises, which it stays quiet about, when it exits
non-zero) rather than the shape of the module.

Scope note for reviewers: the *rich* ``scripts/score.py`` that PR #2802 covered
was deleted from this repo in ``b0802d2ac chore(root): remove score gate,
review sole quality gate (#4868)``. It did not move here — ``digidev/scripts/
score.py`` is an unrelated, much smaller tool. This file therefore covers the
surface that actually exists.

Known gaps, pinned as-is so they are visible rather than accidental (each is a
one-line pattern fix in a *vendored* file, which is the EM's call, not this
leaf's — see DIG-1596):

* ``_OPT`` never fires on real ``git diff`` output. Both optimization patterns
  are written against bare source, but ``main()`` only ever passes
  ``staged_diff()``, whose added lines start with ``+``. The N+1 pattern also
  requires the loop body to *begin* with the call, so ``rows = await db.query(…)``
  is missed; the sequential-awaits pattern misses ``const b = await fetchOrders()``.
* ``_QUAL``'s "Line >120 chars added" fires from 123 characters, because
  ``^[+][^+].{121,}`` spends two characters on the diff marker.

The `_SEC` and `_QUAL` ``# TODO`` patterns require a space between the ``+`` and
the ``#``, which is what git emits for an indented comment.
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
SCRIPT = REPO_ROOT / "digidev" / "scripts" / "score.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("digidev_score_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["digidev_score_under_test"] = module
    spec.loader.exec_module(module)
    return module


score = _load()


# ── Security heuristics ───────────────────────────────────────────────────────

def test_security_flags_hardcoded_credential_but_not_env_placeholder() -> None:
    assert score.heuristic('+password = "hunter2xyz"\n', score._SEC) == [
        "Possible hardcoded credential"
    ]
    # Env-var indirection is the whole point of the pattern — "${…}" must not flag.
    assert score.heuristic('+password = "${SECRET}"\n', score._SEC) == []
    assert score.heuristic('+api_key = os.environ["API_KEY"]\n', score._SEC) == []
    # Below the 6-char floor the literal is too weak to call a credential.
    assert score.heuristic('+password = "short"\n', score._SEC) == []


def test_security_flags_shell_true_and_eval() -> None:
    diff = "+subprocess.run(cmd, shell=True)\n+result = eval(user_input)\n"
    assert score.heuristic(diff, score._SEC) == [
        "subprocess(shell=True) — command injection risk",
        "eval() call — code injection risk",
    ]


def test_security_bind_to_all_interfaces_is_addition_only() -> None:
    assert score.heuristic('+host = "0.0.0.0"\n', score._SEC) == [
        "Binding to 0.0.0.0 — broad network exposure"
    ]
    # Deleting the binding is the fix, not the offence.
    assert score.heuristic('-host = "0.0.0.0"\n', score._SEC) == []


def test_security_todo_is_addition_only_and_needs_a_security_word() -> None:
    # Pattern is ``^[+][^+].*#\s*TODO.*(auth|security|…)`` — the ``[^+]`` slot is
    # what forces a space between the diff marker and the comment.
    assert score.heuristic("+ # TODO: rotate the auth token\n", score._SEC) == [
        "Security TODO left unresolved in staged changes"
    ]
    assert score.heuristic("- # TODO: rotate the auth token\n", score._SEC) == []
    # A TODO with no security-relevant word is a quality finding, not a security one.
    assert score.heuristic("+ # TODO: tidy up imports\n", score._SEC) == []


# ── Quality heuristics ────────────────────────────────────────────────────────

def test_quality_flags_long_line_when_added() -> None:
    # Pattern is ``^[+][^+].{121,}``: the ``+`` and one further character are
    # consumed by the prefix slots, so the gate fires from 123 total characters,
    # while the message advertises ">120". Pinned here as-is (see module docstring).
    at_limit = "+" + "x" * 119  # 120 total — under the effective cut-off
    over_limit = "+" + "x" * 120  # 121 total — still under it
    assert len(at_limit) == 120
    assert score.heuristic(at_limit + "\n", score._QUAL) == []
    assert score.heuristic(over_limit + "\n", score._QUAL) == []
    assert score.heuristic("+" + "x" * 122 + "\n", score._QUAL) == ["Line >120 chars added"]
    # Removing a long line is not adding one.
    assert score.heuristic("-" + "x" * 200 + "\n", score._QUAL) == []


def test_quality_flags_todo_when_added_only() -> None:
    assert score.heuristic("+ # TODO: split this function\n", score._QUAL) == [
        "TODO added in staged changes"
    ]
    assert score.heuristic("- # TODO: split this function\n", score._QUAL) == []


# ── Optimization heuristics ───────────────────────────────────────────────────

def test_optimization_flags_query_inside_loop_for_a_bare_call_body() -> None:
    # The N+1 pattern is ``for\s+\w+\s+in\s+.{1,80}:\n(?:\s+.+\n){0,3}\s+(?:await\s+)?
    # (?:\w+\.)+(?:query|…)`` — the body line must *start* with the call, so this
    # shape is detected …
    assert score.heuristic("for user in users:\n    await db.query(user.id)\n", score._OPT) == [
        "Query inside loop — possible N+1"
    ]
    # … and these shapes are not. Pinned as-is; see "Known gaps" in the docstring.
    assert score.heuristic("for user in users:\n    rows = await db.query(user.id)\n", score._OPT) == []
    assert score.heuristic("for (const u of users) {\n  await db.execute(u)\n}\n", score._OPT) == []


def test_optimization_flags_two_adjacent_bare_awaits() -> None:
    assert score.heuristic(
        "await fetchProfile()\n  await fetchOrders()\n", score._OPT
    ) == ["Sequential awaits — consider gather/Promise.all"]


def test_optimization_misses_awaits_hidden_behind_a_diff_marker_or_assignment() -> None:
    # Both misses are real and both are pinned deliberately rather than papered
    # over: ``main()`` only ever passes a real ``git diff`` output, whose added
    # lines carry a leading ``+``. See "Known gaps" in the docstring.
    assert score.heuristic(
        "+const a = await fetchProfile()\n+await fetchOrders()\n", score._OPT
    ) == []
    assert score.heuristic(
        "const a = await fetchProfile()\nconst b = await fetchOrders()\n", score._OPT
    ) == []


def test_clean_diff_raises_nothing_in_any_dimension() -> None:
    clean = "+def add(a, b):\n+    return a + b\n"
    assert score.heuristic(clean, score._SEC) == []
    assert score.heuristic(clean, score._QUAL) == []
    assert score.heuristic(clean, score._OPT) == []
    assert score.test_coverage(["src/app.py", "tests/test_app.py"]) == []


# ── Coverage heuristic ────────────────────────────────────────────────────────

def test_test_coverage_flags_source_staged_without_any_test_file() -> None:
    assert score.test_coverage(["src/app.py"]) == [
        "Source files staged without test files — verify coverage exists"
    ]


def test_test_coverage_treats_spec_and_test_paths_as_tests() -> None:
    # A spec file beside its source satisfies the coverage heuristic …
    assert score.test_coverage(["src/app.ts", "src/app.spec.ts"]) == []
    assert score.test_coverage(["src/app.ts", "test/test_app.py"]) == []
    # … and a spec file *alone* is not staged-source-with-no-tests, which is the
    # branch that would otherwise fire the warning.
    assert score.test_coverage(["src/app.spec.ts"]) == []


def test_test_coverage_is_silent_for_a_test_only_change() -> None:
    assert score.test_coverage(["tests/test_app.py"]) == []


# ── Threshold loading ─────────────────────────────────────────────────────────

def test_get_thresholds_falls_back_to_defaults_without_agents_yml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert score.get_thresholds() == dict(score.DEFAULTS)


def test_get_thresholds_reads_agents_yml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "agents.yml").write_text(
        "scoring_thresholds:\n  security: 9\n  quality: 6\n  optimization: 5\n  accuracy: 4\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    assert score.get_thresholds() == {
        "security": 9,
        "quality": 6,
        "optimization": 5,
        "accuracy": 4,
    }


def test_get_thresholds_keeps_defaults_for_dimensions_agents_yml_omits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "agents.yml").write_text(
        "scoring_thresholds:\n  security: 9\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    thresholds = score.get_thresholds()
    assert thresholds["security"] == 9
    for dim in ("quality", "optimization", "accuracy"):
        assert thresholds[dim] == score.DEFAULTS[dim]


def test_get_thresholds_falls_back_to_regex_without_pyyaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "agents.yml").write_text(
        "scoring_thresholds:\n  security: 9\n  accuracy: 4\n", encoding="utf-8"
    )
    # A None entry in sys.modules makes `import yaml` raise ImportError.
    monkeypatch.setitem(sys.modules, "yaml", None)
    monkeypatch.chdir(tmp_path)
    thresholds = score.get_thresholds()
    assert thresholds["security"] == 9
    assert thresholds["accuracy"] == 4
    assert thresholds["quality"] == score.DEFAULTS["quality"]


def test_repo_agents_yml_agrees_with_module_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """The vendored defaults must match the thresholds this repo actually ships."""
    assert (REPO_ROOT / "agents.yml").exists()
    monkeypatch.chdir(REPO_ROOT)
    assert score.get_thresholds() == dict(score.DEFAULTS)


def test_every_dimension_has_a_threshold_on_the_ten_point_scale() -> None:
    assert sorted(score.DEFAULTS) == sorted(score.DIMENSIONS)
    assert all(0 <= v <= 10 for v in score.DEFAULTS.values())


# ── Rubric loading ────────────────────────────────────────────────────────────

def test_read_criteria_reports_a_missing_rubric(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert score.read_criteria("security") == [
        "(rubric missing — re-run installer to generate docs/scoring/SECURITY.md)"
    ]


def test_read_criteria_uppercases_the_dimension_for_the_rubric_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rubric path must be ``docs/scoring/<DIM>.md`` in upper case.

    Asserted on the *path the module builds*, not on a file it finds: on a
    case-insensitive filesystem (macOS, and this test was written on one) a
    lowercased ``dim.lower()`` still resolves ``SECURITY.md``, so probing the
    real filesystem cannot tell the two implementations apart.
    """
    seen: list[str] = []
    real_path = Path

    class RecordingPath(type(Path())):  # type: ignore[misc]
        def __new__(cls, *args: object, **kwargs: object) -> Any:
            p = real_path(*args, **kwargs)  # score:allow untyped any — test stub
            seen.append(str(p))
            return p

    monkeypatch.setattr(score, "Path", RecordingPath)
    monkeypatch.chdir(tmp_path)
    score.read_criteria("security")
    score.read_criteria("quality")
    assert seen == ["docs/scoring/SECURITY.md", "docs/scoring/QUALITY.md"]


def test_read_criteria_parses_numbered_bold_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rubric = tmp_path / "docs" / "scoring"
    rubric.mkdir(parents=True)
    (rubric / "SECURITY.md").write_text(
        "1. **No hardcoded credentials** — use the vault.\n"
        "2. **Auth on every route** — see the checklist.\n"
        "3. A bare numbered item is not format 1.\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    assert score.read_criteria("security") == [
        "No hardcoded credentials",
        "Auth on every route",
    ]


def test_read_criteria_parses_table_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rubric = tmp_path / "docs" / "scoring"
    rubric.mkdir(parents=True)
    (rubric / "QUALITY.md").write_text(
        "| # | Criterion | Notes |\n"
        "|---|-----------|-------|\n"
        "| 1 | **Ruff clean** | run before push |\n"
        "| 2 | **Types annotated** | mypy gate |\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    assert score.read_criteria("quality") == ["Ruff clean", "Types annotated"]


def test_read_criteria_parses_bare_numbered_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rubric = tmp_path / "docs" / "scoring"
    rubric.mkdir(parents=True)
    (rubric / "ACCURACY.md").write_text(
        "1. Backtests reproduce on a fixed seed\n2. Assertions cover the regression\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    assert score.read_criteria("accuracy") == [
        "Backtests reproduce on a fixed seed",
        "Assertions cover the regression",
    ]


def test_read_criteria_caps_the_rubric_at_ten_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rubric = tmp_path / "docs" / "scoring"
    rubric.mkdir(parents=True)
    (rubric / "OPTIMIZATION.md").write_text(
        "".join(f"{i}. **Item {i}**\n" for i in range(1, 15)), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    criteria = score.read_criteria("optimization")
    assert len(criteria) == 10
    assert criteria[0] == "Item 1"
    assert criteria[-1] == "Item 10"


# ── main(): argument parsing and exit codes ───────────────────────────────────

def _stage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    argv: list[str],
    files: list[str] | None = None,
    diff: str = "+def add(a, b):\n+    return a + b\n",
) -> None:
    """Put main() in a sandbox: no git, no linters, no real agents.yml."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["score.py", *argv])
    monkeypatch.setattr(score, "staged_files", lambda: list(files if files is not None else ["tests/test_app.py"]))
    monkeypatch.setattr(score, "staged_diff", lambda: diff)
    monkeypatch.setattr(score, "run_lint", lambda _files: [])


def test_main_exits_zero_with_nothing_staged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stage(monkeypatch, tmp_path, [], files=[])
    with pytest.raises(SystemExit) as exc:
        score.main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "No staged changes" in out
    # Nothing staged means the gate stops there: it must not go on to lint,
    # report heuristic findings, or demand a self-score.
    assert "Lint clean" not in out
    assert "Submit your self-score" not in out
    assert not (tmp_path / ".score-last.json").exists()


def test_main_accepts_both_set_flag_forms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    passing = "security=8,quality=8,optimization=7,accuracy=9"
    for argv in (["--set", passing], ["--set=" + passing]):
        _stage(monkeypatch, tmp_path, argv)
        with pytest.raises(SystemExit) as exc:
            score.main()
        assert exc.value.code == 0, argv


def test_main_writes_results_and_passes_when_all_dimensions_meet_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage(monkeypatch, tmp_path, ["--set", "security=10,quality=9,optimization=8,accuracy=9"])
    with pytest.raises(SystemExit) as exc:
        score.main()
    assert exc.value.code == 0
    results = json.loads((tmp_path / ".score-last.json").read_text(encoding="utf-8"))
    assert results["security"] == {"score": 10, "threshold": 8, "passed": True}
    assert results["optimization"] == {"score": 8, "threshold": 7, "passed": True}


def test_main_fails_when_a_dimension_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stage(monkeypatch, tmp_path, ["--set", "security=10,quality=10,optimization=10"])
    with pytest.raises(SystemExit) as exc:
        score.main()
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "ACCURACY: not provided" in out
    assert not (tmp_path / ".score-last.json").exists()


def test_main_fails_when_a_score_is_below_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stage(monkeypatch, tmp_path, ["--set", "security=10,quality=10,optimization=2,accuracy=10"])
    with pytest.raises(SystemExit) as exc:
        score.main()
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "OPTIMIZATION: 2/10" in out
    assert "FAIL" in out
    assert not (tmp_path / ".score-last.json").exists()


def test_main_honours_thresholds_from_agents_yml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "agents.yml").write_text(
        "scoring_thresholds:\n  optimization: 9\n", encoding="utf-8"
    )
    _stage(monkeypatch, tmp_path, ["--set", "security=8,quality=8,optimization=8,accuracy=9"])
    with pytest.raises(SystemExit) as exc:
        score.main()
    assert exc.value.code == 1  # 8 < the repo's raised optimization threshold


def test_main_without_set_flag_prints_rubrics_and_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rubric = tmp_path / "docs" / "scoring"
    rubric.mkdir(parents=True)
    (rubric / "SECURITY.md").write_text("1. **No hardcoded credentials**\n", encoding="utf-8")
    _stage(monkeypatch, tmp_path, [], files=["src/app.py", "tests/test_app.py"])
    with pytest.raises(SystemExit) as exc:
        score.main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "No heuristic issues found" in out
    assert "No hardcoded credentials" in out
    assert "threshold: ≥8/10" in out


def test_main_surfaces_heuristic_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stage(
        monkeypatch,
        tmp_path,
        [],
        files=["src/app.py"],
        diff='+password = "hunter2xyz"\n',
    )
    with pytest.raises(SystemExit) as exc:
        score.main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "Security: Possible hardcoded credential" in out
    assert "Accuracy: Source files staged without test files" in out