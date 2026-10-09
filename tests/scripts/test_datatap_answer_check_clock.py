"""Pin: the DataTap answer integrity check runs hourly, with no secret (#DIG-306).

The brief asked for ``on: schedule`` with ``cron: '17 * * * *'`` inside the
workflow. develop cannot carry that: ``tests/scripts/test_no_gha_schedules.py``
fails any workflow whose ``on`` contains ``schedule``, because every clock for
this repo lives on the digithings-cron Worker (``apps/digithings-cron``) and a
GitHub cron on develop would double-fire with it. ``secret-staleness`` is the
precedent: a ``workflow_dispatch``-only workflow whose clock is a ``wd()`` row
plus a ``[triggers] crons`` entry in ``wrangler.toml``.

Same outcome the brief wants — hourly at minute 17, zero credentials — on the
one clock the repo actually owns.

The second half of this file pins the step's *behaviour*: the S1 guard that
recovers a recipe's real exit code from make's. The DIG-1131 review deleted
that guard in a scratch clone and every suite still passed, which means the
guard had no behavioural coverage at all — so the tests below execute the
workflow's own shell rather than grep its text.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "datatap-answer-check.yml"
JOBS_SOURCE = REPO_ROOT / "apps" / "digithings-cron" / "src" / "jobs.ts"
JOBS_TEST = REPO_ROOT / "apps" / "digithings-cron" / "src" / "jobs.test.ts"
WRANGLER = REPO_ROOT / "apps" / "digithings-cron" / "wrangler.toml"

CRON = "17 * * * *"
JOB_ID = "datatap-answer-check"
MAKE_TARGET = "make datatap-answer-check"


def _workflow() -> dict:
    assert WORKFLOW.exists(), f"{WORKFLOW.relative_to(REPO_ROOT)} is the second line of defence"
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _on(doc: dict) -> object:
    if "on" in doc:
        return doc["on"]
    if True in doc:  # YAML 1.1 parses a bare `on:` key as the boolean True
        return doc[True]
    raise AssertionError("workflow missing on:")


def test_the_clock_workflow_exists() -> None:
    _workflow()


def test_the_workflow_has_no_github_schedule_because_develop_forbids_one() -> None:
    """develop carries no on.schedule. The clock is the Worker's wd() row."""
    on = _on(_workflow())
    rendered = yaml.safe_dump(on)
    assert "schedule" not in rendered


def test_the_workflow_is_workflow_dispatch_only() -> None:
    on = _on(_workflow())
    rendered = yaml.safe_dump(on)
    assert "workflow_dispatch" in rendered


def test_the_workflow_runs_the_check_through_the_make_target() -> None:
    """One source of truth: the same command the developer and the routine run."""
    body = WORKFLOW.read_text(encoding="utf-8")
    assert MAKE_TARGET in body


def test_the_workflow_does_not_swallow_the_exit_code() -> None:
    """Exit 1 and exit 2 must both surface. `continue-on-error` or `|| true`
    would turn a real fabrication signal, and a blind check, into green."""
    body = WORKFLOW.read_text(encoding="utf-8")
    assert "continue-on-error" not in body
    assert "|| true" not in body
    assert "|| exit 0" not in body


def test_the_workflow_introduces_no_secret_and_no_repo_variable() -> None:
    """The token comes out of DataTap's own public page. No credential is needed."""
    body = WORKFLOW.read_text(encoding="utf-8")
    assert "secrets." not in body
    assert "vars." not in body


def test_the_clock_is_registered_on_the_cron_worker() -> None:
    text = JOBS_SOURCE.read_text(encoding="utf-8")
    assert re.search(
        rf'wd\(\s*"{re.escape(JOB_ID)}"\s*,\s*"{re.escape(CRON)}"',
        text,
    ), f'no wd("{JOB_ID}", "{CRON}", …) row in jobs.ts'


def test_the_clock_row_targets_this_workflow_on_develop() -> None:
    text = JOBS_SOURCE.read_text(encoding="utf-8")
    row = re.search(rf'wd\(\s*"{re.escape(JOB_ID)}"(?P<args>[^)]*)\)', text, flags=re.DOTALL)
    assert row, f"no wd() row for {JOB_ID}"
    args = row.group("args")
    assert "DIGITHINGS" in args
    assert "datatap-answer-check.yml" in args
    assert "enabled: false" not in args, "the clock must actually be enabled"


def test_the_cron_is_in_the_wrangler_trigger() -> None:
    """Each enabled job.cron must appear in wrangler.toml [triggers] crons."""
    text = WRANGLER.read_text(encoding="utf-8")
    block = text.split("[triggers]", 1)[1]
    entry = next(line for line in block.splitlines() if line.strip().startswith(f'"{CRON}"'))
    assert f"# {JOB_ID}" in entry, "keep the job id as the trailing comment, like its neighbours"


def test_the_pinned_cron_set_is_updated() -> None:
    """jobs.test.ts asserts uniqueEnabledCrons() by exact ordered equality."""
    text = JOBS_TEST.read_text(encoding="utf-8")
    assert f'"{CRON}"' in text, "ENABLED_CRONS must gain the new clock at its JOBS position"


def test_no_two_clocks_share_an_exact_cron_string() -> None:
    """Exact-string duplicates only — deliberately narrower than the old name.

    The old test was called `..._does_not_collide_with_an_existing_one` and its
    docstring promised a minute-level invariant it never checked: the body only
    compared whole strings. Minute-level overlap is *not* a defect here — five
    enabled clocks already fire on minute 17 (`17 6 * * *`, `17 6 1 * *`,
    `17 9 * * MON`, `17 12 * * MON-FRI`, `17 * * * *`) and CTO condition D8.5
    accepted it, since two jobs on one minute share a runner rather than
    delaying each other. Moving the clock is not on the table either: `CRON` is
    pinned against `jobs.ts`, `wrangler.toml` and `jobs.test.ts`.

    A test that fails on ratified behaviour trains people to ignore it, so this
    pins the invariant the repo can actually keep — the same exact string
    `jobs.test.ts` asserts by ordered equality — and says so in its name.
    """
    block = WRANGLER.read_text(encoding="utf-8").split("[triggers]", 1)[1]
    crons = [
        line.split("#")[0].strip() for line in block.splitlines() if line.strip().startswith('"')
    ]
    assert len(crons) == len(set(crons)), "two jobs on one cron will queue on a shared runner"


# --------------------------------------------------------------------------- #
# Behaviour of the step's own shell. Everything below executes the workflow.
#
# These tests deliberately do not re-implement the step or assert on its source
# text: the DIG-1131 review deleted the S1 guard in a scratch clone and every
# suite stayed green, because nothing tested behaviour, only prose. A grep for
# `exit "$rc"` would also have been satisfiable by the comment that quotes that
# very line. Executing the block cannot be satisfied by a comment.
# --------------------------------------------------------------------------- #

# GNU make's contract, which the workflow's own comment relies on: a failing
# recipe makes make exit 2, never the recipe's code, and a missing target is
# also 2. The shim stands in for make so a scenario can pick rc and log
# independently; what is under test is the step, not make.
_FAKE_MAKE = """#!/bin/sh
printf '%s' "$FAKE_MAKE_LOG"
exit "${FAKE_MAKE_RC:-0}"
"""

# The S1 guard, matched so the mutation test can delete exactly it.
_S1_GUARD = re.compile(r'^if \[ "\$rc" -ne 0 \].*?^fi$\n?', flags=re.DOTALL | re.MULTILINE)


def _step_script() -> str:
    """The last `run:` block of the check job, read out of the YAML.

    `yaml.safe_load` is the only source here — hand-copying the shell would let
    the tests pass against a workflow nobody ships.
    """
    steps = _workflow()["jobs"]["check"]["steps"]
    bodies = [step["run"] for step in steps if isinstance(step.get("run"), str)]
    assert bodies, "the check job has no run: step"
    body = bodies[-1]
    assert MAKE_TARGET in body, (
        "the last run: step does not invoke make — a step was appended and these "
        "tests would now pin the wrong shell"
    )
    return body


def _run_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    log: str,
    make_rc: int,
    body: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the workflow's step script and return the real CompletedProcess.

    `bash --noprofile --norc -eo pipefail {0}` is the command GitHub Actions runs
    for `shell: bash`, byte for byte, including the `-e` the block does not set.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    fake_make = bindir / "make"
    fake_make.write_text(_FAKE_MAKE)
    fake_make.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_MAKE_LOG", log)
    monkeypatch.setenv("FAKE_MAKE_RC", str(make_rc))

    script = tmp_path / "step.sh"
    script.write_text(_step_script() if body is None else body)
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=tmp_path,
    )


@pytest.mark.parametrize(
    ("log", "make_rc", "expected"),
    [
        pytest.param("datatap-answer-check: exit 0\n", 0, 0, id="the-only-path-to-green"),
        pytest.param("datatap-answer-check: exit 1\n", 2, 1, id="rc2-report-1"),
        pytest.param("datatap-answer-check: exit 2\n", 2, 2, id="rc2-report-2"),
        pytest.param("datatap-answer-check: exit 7\n", 2, 7, id="report-7"),
        pytest.param("datatap-answer-check: exit 139\n", 2, 139, id="report-139-segv"),
        pytest.param(
            "make: *** No rule to make target 'datatap-answer-check'.  Stop.\n",
            2,
            2,
            id="no-such-target",
        ),
        pytest.param("", 2, 2, id="make-printed-nothing"),
        pytest.param(
            "datatap-answer-check: exit 0\n",
            2,
            2,
            id="report-0-make-failed-fails-closed",
        ),
        pytest.param(
            "Traceback (most recent call last):\nFalse\ndatatap-answer-check: exit 0\n",
            2,
            2,
            id="report-0-child-failed-false",
        ),
        pytest.param(
            "datatap-answer-check: exit 0\n",
            1,
            1,
            id="report-0-make-rc1-guard-propagates-rc",
        ),
        pytest.param(
            "datatap-answer-check: exit 0\nstdout: ok\ndatatap-answer-check: exit 1\n",
            2,
            1,
            id="lookalike-0-before-real-1-last-match-wins",
        ),
        pytest.param(
            "datatap-answer-check: exit 0 and it was fine\n",
            0,
            2,
            id="trailing-text-rejected",
        ),
        pytest.param("  datatap-answer-check: exit 0\n", 0, 2, id="indented-rejected"),
        pytest.param("datatap-answer-check: exit 0\r\n", 0, 2, id="cr-terminated-rejected"),
        pytest.param(
            "warning: datatap-answer-check: exit 0\n",
            0,
            2,
            id="warning-prefix-rejected",
        ),
    ],
)
def test_the_step_surfaces_the_reported_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    log: str,
    make_rc: int,
    expected: int,
) -> None:
    """Each way the log and make's exit code can disagree maps to one step code.

    Two rows carry the load. `rc2-report-1` must stay 1: make cannot return 1
    for a failing recipe, so a step that turned rc=2 into a plain failure would
    throw away the distinction between a blind check and a real fabrication
    signal. `report-0-make-failed-fails-closed` must stay non-zero: make failed
    and the recipe still claimed success, so the only honest code is a failure.
    The rest are malformed status lines that must never be read as a pass.
    """
    result = _run_step(tmp_path, monkeypatch, log, make_rc)
    assert result.returncode == expected, f"stdout={result.stdout!r} stderr={result.stderr!r}"


def test_the_s1_guard_is_load_bearing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard is what stops a false success report from shipping green.

    Proven by execution in both directions, which is the whole point: the
    DIG-1131 review deleted these three lines and the suite did not notice. The
    mutation is asserted to have changed the text, so a refactor that moves the
    guard out of the matched span fails loudly instead of quietly passing.
    """
    log = "datatap-answer-check: exit 0\n"

    guarded = _run_step(tmp_path, monkeypatch, log, make_rc=2)
    assert guarded.returncode == 2, guarded.stdout + guarded.stderr
    assert "::error::make exited 2 while the recipe reported" in guarded.stdout

    mutated, removed = _S1_GUARD.subn("", _step_script())
    assert removed == 1, f"expected exactly one S1 guard, deleted {removed}"
    assert mutated != _step_script(), "the mutation was a no-op"

    unguarded = _run_step(tmp_path, monkeypatch, log, make_rc=2, body=mutated)
    assert unguarded.returncode == 0, (
        "with the S1 guard deleted this scenario goes green — that is the defect "
        "these tests exist to pin"
    )


def test_a_missing_status_line_explains_the_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A step that fails closed must say which half of the contract broke."""
    result = _run_step(
        tmp_path,
        monkeypatch,
        "make: *** No rule to make target 'datatap-answer-check'.  Stop.\n",
        make_rc=2,
    )
    assert result.returncode == 2
    assert (
        "::error::make exited 2 without datatap-answer-check reporting a status" in result.stdout
    ), result.stdout
