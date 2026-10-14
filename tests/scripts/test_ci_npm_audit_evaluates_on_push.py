"""`npm-audit` must evaluate on every push to `develop`/`main`, not only on a diff that
touched a manifest (DIG-2305).

The path gate in `ci.yml`'s `changes` job answers *which files this commit touched*. The
question the audit answers is *what advisories exist right now*. Those are different
questions, and filtering one by the other is what let the lane go unreported indefinitely:

    npm-audit                   skipped   2026-10-07T23:38:10Z
    Required checks passed      success   2026-10-07T23:38:12Z

on develop head `e45b12e7`. A skipped lane cannot gate, and `required-checks` tolerates
`skipped` (it exists precisely because no path-gated job can be named in branch
protection), so the aggregate's `success` was a false negative — a lane reported as
passing that never evaluated anything. The cost was real rather than tidy: the five `next`
advisories published on 2026-10-07 had nowhere to land on develop, so they surfaced on
PR #5107, whose lockfile was strictly *better* than develop's (1 HIGH/CRITICAL versus 5),
and cost a full round of separate auditing of develop to disprove the PR as the cause.

So the invariant this file pins is narrow and mechanical: **on a push, `npm-audit` runs.**
On a `pull_request` it stays path-gated, because a doc-only PR should not pay for an audit.

The second half of the invariant — *reported `success` means it evaluated* — is held by
`scripts/ci_required_checks_aggregate.py`: on a push, a `skipped` npm-audit is a failure
rather than a tolerated skip. That guard is what stops a later edit from silently
reintroducing this, so it is wired here too.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
AGGREGATE_SCRIPT = REPO_ROOT / "scripts" / "ci_required_checks_aggregate.py"


def _load_aggregate() -> Any:
    spec = importlib.util.spec_from_file_location(
        "ci_required_checks_aggregate", AGGREGATE_SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["ci_required_checks_aggregate"] = module
    spec.loader.exec_module(module)
    return module


agg = _load_aggregate()


def _ci() -> dict[str, Any]:
    return yaml.safe_load(CI_YML.read_text(encoding="utf-8")) or {}


def _triggers() -> dict[str, Any]:
    ci = _ci()
    # PyYAML resolves a bare `on:` key to the boolean True (YAML 1.1), so accept either.
    return ci.get("on") or ci.get(True) or {}


def test_ci_still_runs_on_a_push_to_develop_and_main() -> None:
    """Without this the escape hatch below is vacuous — there would be no push to widen."""
    assert _triggers()["push"]["branches"] == ["main", "develop"]


def test_npm_audit_ignores_the_path_filter_on_a_push() -> None:
    where = "ci.yml: jobs.npm-audit.if"
    condition = str(_ci()["jobs"]["npm-audit"].get("if", ""))
    assert "github.event_name == 'push'" in condition, (
        f"{where} is {condition!r}. `npm-audit` is path-gated, so a push to develop that "
        "touched no manifest reports the lane as skipped while `Required checks passed` "
        "reports success — a green gate over a lane that never ran (DIG-2305)"
    )


def test_npm_audit_stays_path_gated_on_a_pull_request() -> None:
    where = "ci.yml: jobs.npm-audit.if"
    condition = str(_ci()["jobs"]["npm-audit"].get("if", ""))
    assert "needs.changes.outputs.npm_audit == 'true'" in condition, (
        f"{where} is {condition!r}. Dropping the filter outright would make every doc-only "
        "PR pay for an audit; the widening is meant to apply to pushes only (DIG-2305)"
    )


def test_the_push_guard_is_wired_to_the_push_event() -> None:
    """The guard must be armed by the push event, or it never fires."""
    steps = _ci()["jobs"]["required-checks"]["steps"]
    aggregate = next(
        step for step in steps if "ci_required_checks_aggregate.py" in str(step.get("run", ""))
    )
    env = aggregate["env"]
    assert "github.event_name == 'push'" in str(env.get("PUSH_EVENT", "")), (
        f"ci.yml: required-checks aggregate step env is {env!r}. Without the push event the "
        "aggregate cannot tell a tolerated PR skip from the skipped-on-develop lane that "
        "started this (DIG-2305)"
    )


def test_npm_audit_is_declared_always_evaluated_on_push() -> None:
    assert "npm-audit" in agg.ALWAYS_EVALUATED_ON_PUSH, (
        "scripts/ci_required_checks_aggregate.py no longer lists npm-audit in "
        f"ALWAYS_EVALUATED_ON_PUSH (currently {sorted(agg.ALWAYS_EVALUATED_ON_PUSH)}), so a "
        "skipped npm-audit on develop reads as success again (DIG-2305)"
    )


def test_every_declared_job_really_is_unconditional_on_a_push() -> None:
    """The reverse check, so the list cannot rot into a stale promise.

    `ALWAYS_EVALUATED_ON_PUSH` is a hand-maintained set; a job dropped from `ci.yml` (or
    re-path-gated) would leave an entry that guards nothing while reading as coverage.
    """
    jobs = _ci()["jobs"]
    for name in sorted(agg.ALWAYS_EVALUATED_ON_PUSH):
        assert name in jobs, (
            f"ALWAYS_EVALUATED_ON_PUSH names {name!r}, which is not a job in ci.yml — the "
            "entry guards nothing. Remove it or restore the job"
        )
        condition = str(jobs[name].get("if", ""))
        assert "github.event_name == 'push'" in condition, (
            f"ci.yml: jobs.{name}.if is {condition!r}, so the job can still report `skipped` "
            "on a push while the aggregate treats that skip as a failure. Either the job "
            "loses its path filter on push, or it leaves ALWAYS_EVALUATED_ON_PUSH"
        )