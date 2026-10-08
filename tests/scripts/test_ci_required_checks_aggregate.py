"""Unit tests for scripts/ci_required_checks_aggregate.py.

Pins that every ``required-checks`` dependency blocks the develop merge gate.
The former ``score`` advisory exception left with the score tooling (#4868).

Also pins the ``skipped`` split (#2371): a skip is tolerated for a job a path
filter could legitimately switch off, and it blocks for a job with no gate at
all — including the npm audit lane, whose path filter used to let develop go
green with the lane unrun.
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


# ── skipped vs succeeded (#2371) ────────────────────────────────────────────


def _ci() -> dict[str, Any]:
    yaml = pytest.importorskip("yaml")
    with (REPO_ROOT / ".github" / "workflows" / "ci.yml").open() as handle:
        return yaml.safe_load(handle)


def test_must_run_jobs_match_ungated_jobs_in_ci() -> None:
    """MUST_RUN_JOBS is derived, not curated: the set must equal ci.yml's ungated jobs.

    If a future job is added without an ``if:`` gate it must block on a skip, and
    if a job here is re-gated its skip becomes legitimate again. Either drift is
    a silent wrong answer, so the suite holds the set against the file.
    """
    ungated = {
        name
        for name, job in _ci()["jobs"].items()
        # required-checks gates itself on always() so it survives a cancelled
        # dependency; it is the aggregator, not something it aggregates.
        if name != "required-checks" and "if" not in job
    }
    assert agg.MUST_RUN_JOBS == frozenset(ungated)
    # Guard against a vacuous pin: an empty ungated set would make the
    # assertion above true for an empty MUST_RUN_JOBS too.
    assert "npm-audit" in agg.MUST_RUN_JOBS


def test_npm_audit_lane_runs_unconditionally() -> None:
    """The headline defect: develop pushes must not be able to skip the audit."""
    jobs = _ci()["jobs"]
    assert "if" not in jobs["npm-audit"], "npm-audit is path-gated again"
    assert "needs" not in jobs["npm-audit"], "npm-audit is conditioned on changes again"
    assert "npm_audit" not in jobs["changes"]["outputs"], "dead output still declared"
    filters = next(
        step["with"]["filters"]
        for step in jobs["changes"]["steps"]
        if "with" in step and "filters" in step["with"]
    )
    assert "npm_audit" not in filters, "npm_audit path filter is still generated"
    yaml = pytest.importorskip("yaml")
    with (REPO_ROOT / "scripts" / "ci_paths.yaml").open() as handle:
        assert "npm_audit" not in yaml.safe_load(handle), "filter source still has it"


def test_skipped_must_run_job_blocks() -> None:
    results = {
        "npm-audit": {"result": "skipped"},
        "changes": {"result": "success"},
        "digibase": {"result": "skipped"},
    }
    blocking, advisory = agg.classify_needs(results)
    # The ungated npm audit never ran -> a failure the gate must see.
    assert blocking == {"npm-audit": "skipped"}
    assert advisory == {}


def test_skipped_path_gated_job_is_still_tolerated() -> None:
    """Mirror-image guard: a doc-only PR skips every gated lane, and that is fine."""
    results = {
        "digibase": {"result": "skipped"},
        "digigraph": {"result": "skipped"},
        "ruff-and-scripts": {"result": "skipped"},
        "changes": {"result": "success"},
        "npm-audit": {"result": "success"},
    }
    blocking, advisory = agg.classify_needs(results)
    assert blocking == {}
    assert advisory == {}


def test_main_exits_one_when_must_run_job_did_not_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(
        "RESULTS",
        json.dumps({"npm-audit": {"result": "skipped"}, "digibase": {"result": "success"}}),
    )
    assert agg.main([]) == 1
    out = capsys.readouterr().out
    # Names the job, and says it did not run — "skipped" alone reads as "fine".
    assert "npm-audit" in out
    assert "did not run" in out
    assert "::error::npm-audit" in out


def test_must_run_skip_never_reads_as_the_success_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(
        "RESULTS",
        json.dumps({"npm-audit": {"result": "skipped"}, "changes": {"result": "success"}}),
    )
    assert agg.main([]) == 1
    out = capsys.readouterr().out
    assert "All required jobs passed" not in out
