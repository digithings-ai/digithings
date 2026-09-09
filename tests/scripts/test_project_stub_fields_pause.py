"""Pin the project-stub-fields pause gate (#2566) and reap safety rails (#2476).

``stub-tsv`` / ``stub-tsv-phase`` used to open one ``bot/stub-tsv-<N>`` PR per
labeled issue and cluttered the queue. #2566 paused those jobs behind
``vars.STUB_TSV_ENABLED == 'true'`` (unset/empty → skip). A bare ``if: false``
was rejected by actionlint, so the gate is a repo var comparison — easy to
drop by accident when restoring label conditions.

The reap job must stay *ungated* by that var: leftover stub branches still
need deletion when their PRs close. Its branch match is exact
``^bot/stub-tsv-[0-9]+$`` so a mistyped head ref is never deleted.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "project-stub-fields.yml"

STUB_JOBS = ("stub-tsv", "stub-tsv-phase")
REAP_JOB = "reap-stub-branch"
ENABLED_GATE = "vars.STUB_TSV_ENABLED == 'true'"
# Verbatim from the workflow shell — the delete refuse arm keys on this.
REAP_BRANCH_RE = re.compile(r"\^bot/stub-tsv-\[0-9\]\+\$")


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def jobs(workflow: dict) -> dict:
    return workflow["jobs"]


@pytest.mark.parametrize("job_id", STUB_JOBS)
def test_stub_jobs_require_explicit_enable_var(jobs: dict, job_id: str) -> None:
    """Without STUB_TSV_ENABLED=true the stub jobs must not run."""
    assert job_id in jobs, f"expected job {job_id} in project-stub-fields.yml"
    raw_if = jobs[job_id].get("if")
    assert raw_if is not None, f"{job_id} lost its if: — stubs would fire unconditionally"
    # YAML may keep a multi-line expression as a folded string; normalize whitespace.
    cond = " ".join(str(raw_if).split())
    assert ENABLED_GATE in cond, (
        f"{job_id} if: must require {ENABLED_GATE!r} so an unset repo var keeps "
        f"stubs paused; got {raw_if!r}"
    )


def test_reap_job_is_not_paused_by_stub_enable_var(jobs: dict) -> None:
    """Closing leftover stub PRs must still delete branches while stubs are paused."""
    assert REAP_JOB in jobs, f"expected job {REAP_JOB}"
    raw_if = jobs[REAP_JOB].get("if", "")
    cond = " ".join(str(raw_if).split())
    assert "STUB_TSV_ENABLED" not in cond, (
        f"{REAP_JOB} must not depend on STUB_TSV_ENABLED — pause must not strand "
        f"bot/stub-tsv-* branches; got {raw_if!r}"
    )
    assert "bot/stub-tsv-" in cond, (
        f"{REAP_JOB} must still key on bot/stub-tsv-* head refs; got {raw_if!r}"
    )


def test_reap_refuses_non_exact_stub_branch_names(jobs: dict) -> None:
    """Delete only ``bot/stub-tsv-<digits>`` — refuse lookalikes before ``gh api -X DELETE``."""
    steps = jobs[REAP_JOB]["steps"]
    bodies = [str(s.get("run", "")) for s in steps if s.get("run")]
    assert bodies, f"{REAP_JOB} has no run: steps"
    combined = "\n".join(bodies)
    assert REAP_BRANCH_RE.search(combined), (
        f"{REAP_JOB} must keep the exact ^bot/stub-tsv-[0-9]+$ guard before delete; "
        f"missing from:\n{combined}"
    )
    assert "refusing to touch it" in combined or "Refusing" in combined, (
        f"{REAP_JOB} must loudly refuse a non-matching branch name"
    )
