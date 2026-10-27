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

The check ran on that clock until 2026-10-18. Chris retired it: the client
manages their own infrastructure, so we do not probe them on a schedule. The
workflow file stays — a human can still start it by hand, with no credential —
but the clock is gone (DIG-4435).

These pins therefore assert that the clock cannot dispatch anything:

* no ``[triggers] crons`` entry in ``wrangler.toml`` carries its cron, so the
  next deploy leaves the Worker without the trigger;
* the ``wd()`` row in ``jobs.ts`` that names the job is **disabled**, so the
  tick stays quiet (and the row leaves ``uniqueEnabledCrons()``, which is the
  set the deploy contract compares to ``wrangler.toml``);
* the retired cron is carried by no enabled row — the deployed Worker still
  holds the ``17 * * * *`` trigger until the next deploy, and a deployed cron
  that no job row claims at all is an ``unrecognised_cron`` violation, which
  would red local-ci and deadlock the merge that has to remove the clock.

The workflow keeps its ``workflow_dispatch``-only shape.

The second half of this file pins the step's *behaviour*: the S1 guard that
recovers a recipe's real exit code from make's. The DIG-1131 review deleted
that guard in a scratch clone and every suite still passed, which means the
guard had no behavioural coverage at all — so the tests below execute the
workflow's own shell rather than grep its text.

The third pin is the one input the job needs. The check refuses to leave the
host allowlist, so the workflow has to supply it, from a repository variable
and not from a literal: the embed host is the client's own hostname and
changes on every redeploy, and a hostname written into the workflow would be a
client literal in the public repository. The pin that used to forbid *any*
repository variable here was written when the check needed no configuration at
all; the half of it that forbids a secret still holds.
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


MONOREPO_SLUG = "digithings-ai/digithings"


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


def test_the_workflow_introduces_no_secret() -> None:
    """The token comes out of DataTap's own public page. No credential is needed.

    The host allowlist the check refuses to leave is configuration and not a
    credential: a hostname, held in a repository variable, that changes on
    every client redeploy. A secret here would be a credential in a workflow
    that does not need one, so the pin is on the secret and not on the
    variable.
    """
    body = WORKFLOW.read_text(encoding="utf-8")
    assert "secrets." not in body


def test_the_workflow_supplies_the_host_allowlist_the_check_needs() -> None:
    """The check refuses to leave the host allowlist, so the job has to set it.

    Without this the run carries an empty allowlist and exits 2 on every
    hour, with a reason naming a variable that nothing in the repository can
    set — a blind canary whose failure reads like the client's platform being
    down.

    The value is a repository variable and not a literal here, for two
    reasons: the embed host is the client's own hostname and changes on every
    redeploy, and a hostname written into this file would be a client literal
    in the public repository.
    """
    body = WORKFLOW.read_text(encoding="utf-8")
    assert "ANSWER_CHECK_EMBED_HOSTS" in body
    assert "vars.ANSWER_CHECK_EMBED_HOSTS" in body


# --------------------------------------------------------------------------- #
# The allowlist guard (DIG-5790). An unset repository variable used to reach the
# script, which left with "COULD NOT RUN … exit 2" — the same code a client
# platform that did not answer produces, so 115 consecutive runs could not be
# told apart from a real fabrication finding without reading each log. The guard
# is a separate first step, and these tests execute it rather than grep its text.
# --------------------------------------------------------------------------- #

GUARD_MARKER = "embed-host allowlist resolves to no host"


def _guard_step_index() -> int:
    steps = _workflow()["jobs"]["check"]["steps"]
    hits = [
        index
        for index, step in enumerate(steps)
        if isinstance(step.get("run"), str) and GUARD_MARKER in step["run"]
    ]
    assert hits, "the check job has no step that refuses an empty host allowlist"
    assert len(hits) == 1, f"expected exactly one allowlist guard, found {len(hits)}"
    return hits[0]


def _guard_script() -> str:
    steps = _workflow()["jobs"]["check"]["steps"]
    return steps[_guard_step_index()]["run"]


def _run_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str | None
) -> subprocess.CompletedProcess[str]:
    """Run the guard as Actions would, with the allowlist as the only input.

    `None` removes the variable from the environment entirely, which is what an
    unset repository variable looks like to the step; `""` and separator-only
    strings are the present-but-useless cases.
    """
    if value is None:
        monkeypatch.delenv("ANSWER_CHECK_EMBED_HOSTS", raising=False)
    else:
        monkeypatch.setenv("ANSWER_CHECK_EMBED_HOSTS", value)

    script = tmp_path / "guard.sh"
    script.write_text(_guard_script())
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=tmp_path,
    )


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(None, id="unset"),
        pytest.param("", id="empty"),
        pytest.param("   ", id="whitespace-only"),
        pytest.param(",", id="one-separator"),
        pytest.param(" , , ", id="separators-and-space"),
    ],
)
def test_the_guard_fails_closed_on_an_unusable_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    """An allowlist with no host in it must never reach the probe.

    Exit 2 and not 1 on purpose: the script's contract says 1 only ever means a
    fabrication finding, and a missing variable is the check being blind.
    """
    result = _run_guard(tmp_path, monkeypatch, value)
    assert result.returncode == 2, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "::error::" in result.stdout, result.stdout
    assert GUARD_MARKER in result.stdout, result.stdout
    assert "repository variable" in result.stdout, result.stdout
    assert "configuration gap, not a finding" in result.stdout, result.stdout


def test_the_guard_passes_a_configured_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real list reaches the probe: the guard reads the value, it does not vet it.

    Vetting is the script's job (it compares the host the page named against this
    list and refuses a miss), and doing it twice would be a second source of truth.
    The value is counted and never echoed: the log is public, and this workflow's
    own header says the host name stays out of the repository.
    """
    host = "embed.example.test"
    result = _run_guard(tmp_path, monkeypatch, host)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "resolves to 1 host(s)" in result.stdout, result.stdout
    assert host not in result.stdout, "the allowlist value reached the public log"
    assert "::error::" not in result.stdout, result.stdout


def test_the_guard_cannot_be_used_to_forge_an_annotation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dispatch input is free text; a line break in it must not become a command.

    Actions reads `::…::` at the start of a line as a workflow command, so a value
    echoed raw would let a dispatcher mint a passing annotation. The count line is
    the only place the value is touched.
    """
    result = _run_guard(tmp_path, monkeypatch, "embed.example.test\n::error::forged")
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "::error::forged" not in result.stdout, result.stdout
    assert "resolves to 1 host(s)" in result.stdout, result.stdout


def test_the_guard_runs_before_the_probe() -> None:
    """The point is refusing *before* the probe spends a client turn."""
    steps = _workflow()["jobs"]["check"]["steps"]
    probe = [
        index
        for index, step in enumerate(steps)
        if isinstance(step.get("run"), str) and MAKE_TARGET in step["run"]
    ]
    assert probe, "the check job has no step that runs the probe"
    assert _guard_step_index() < probe[0], (
        "the allowlist guard runs after the probe: an empty list would still spend "
        "a probe before failing"
    )


def test_a_dispatch_can_name_the_allowlist_without_the_variable() -> None:
    """The variable is the default; one dispatch may override it (DIG-5790).

    The workflow is manual only and the host changes when the client redeploys,
    so a run must be able to name the host it is testing without a repository
    admin setting a variable first. The default is still the variable, so an
    ordinary dispatch needs nothing typed.
    """
    doc = _workflow()
    on = _on(doc)
    assert isinstance(on, dict), "on: must be a mapping to declare an input"
    inputs = on["workflow_dispatch"]["inputs"]
    assert "embed_host" in inputs, "the dispatch declares no embed_host input"
    assert inputs["embed_host"].get("required") is False, (
        "a required input would make an ordinary dispatch impossible to run from "
        "the default"
    )

    env = doc["jobs"]["check"]["env"]
    expression = env["ANSWER_CHECK_EMBED_HOSTS"]
    assert "inputs.embed_host" in expression, "the input is declared but not read"
    assert "vars.ANSWER_CHECK_EMBED_HOSTS" in expression, (
        "the repository variable is no longer the default: an ordinary dispatch "
        "would now need the host typed in"
    )
    assert expression.index("inputs.embed_host") < expression.index(
        "vars.ANSWER_CHECK_EMBED_HOSTS"
    ), "the variable must be the fallback, not the override"


def _jobs_code() -> str:
    """jobs.ts with `//` comments stripped, so a pin counts rows, not prose.

    The tombstone comment quotes the retired cron on purpose; a pin that read
    the raw file would count that quote as a second claimant. No string
    literal in jobs.ts contains `//`, so stripping comment lines cannot eat
    code.
    """
    text = JOBS_SOURCE.read_text(encoding="utf-8")
    return re.sub(r"//[^\n]*", "", text)


def _retired_row() -> str:
    f"""The `wd("{JOB_ID}", …)` call in jobs.ts, or "" when absent."""
    match = re.search(
        rf'wd\(\s*"{re.escape(JOB_ID)}".*?\)\s*,',
        _jobs_code(),
        flags=re.DOTALL,
    )
    return match.group(0) if match else ""


def test_the_clock_row_is_disabled_in_the_cron_worker() -> None:
    """Retired 2026-10-18 (Chris). The row may stay, but it may not dispatch.

    The row is a tombstone, not a deletion. The deployed Worker still carries
    the `17 * * * *` trigger until the next digithings-cron deploy, and the
    deployed-trigger contract fails a deployed cron that no job row claims —
    deleting the row would red local-ci and deadlock the merge. A disabled row
    still claims its cron, and the tick stays quiet.
    """
    row = _retired_row()
    assert row, f'jobs.ts carries no wd("{JOB_ID}", …) row at all: the retired check lost its tombstone'
    assert "enabled: false" in row, (
        f'jobs.ts still enables wd("{JOB_ID}", …): the retired check would keep dispatching'
    )
    assert f'"{CRON}"' in row, "the tombstone row no longer carries the retired cron"


def test_no_clock_row_targets_this_workflow() -> None:
    """No enabled Worker row may dispatch this workflow file any more."""
    text = _jobs_code()
    assert text.count("datatap-answer-check.yml") == 1, (
        "more than one jobs.ts row names that workflow file: an enabled row "
        "would still dispatch the retired check"
    )
    assert "enabled: false" in _retired_row(), "the only row naming the workflow is enabled"


def test_the_retired_cron_is_carried_by_no_enabled_row() -> None:
    """The retired cron may only be claimed by the disabled tombstone row."""
    text = _jobs_code()
    claims = text.count('"' + CRON + '"')
    assert claims == 1, (
        f'the retired cron "{CRON}" is claimed by {claims} rows; '
        "an enabled claim would keep dispatching it"
    )
    assert '"' + CRON + '"' in _retired_row()


def test_the_cron_is_not_in_the_wrangler_trigger() -> None:
    """A trigger without a row is dead weight, and the trigger is the dispatcher."""
    text = WRANGLER.read_text(encoding="utf-8")
    block = text.split("[triggers]", 1)[1]
    assert not any(
        line.strip().startswith(f'"{CRON}"') for line in block.splitlines()
    ), "the retired clock is still listed in wrangler.toml [triggers] crons"


# NOTE (batch fold): test_the_pinned_cron_set_is_updated lived here on #5202's
# branch, asserting the new clock appears by exact string in jobs.test.ts. That
# file no longer hardcodes any cron string -- the 40-expression list was removed
# upstream as a second source of truth (see its own comment), and the membership
# pin is now the generic `every enabled job cron is listed in uniqueEnabledCrons`
# case in that same file, which covers every enabled job like any other.
# Re-adding the exact-string assertion here would require
# re-adding the list there, against the repo's documented direction, so the
# test is retired rather than re-pointed.
def test_no_two_clocks_share_an_exact_cron_string() -> None:
    """Exact-string duplicates only — deliberately narrower than the old name.

    The old test was called `..._does_not_collide_with_an_existing_one` and its
    docstring promised a minute-level invariant it never checked: the body only
    compared whole strings. Minute-level overlap is *not* a defect here — four
    enabled clocks still fire on minute 17 (`17 6 * * *`, `17 6 1 * *`,
    `17 9 * * MON`, `17 12 * * MON-FRI`) and CTO condition D8.5 accepted it,
    since two jobs on one minute share a runner rather than delaying each
    other. The retired check's own minute-17 clock is gone (DIG-4435), so
    `CRON` here is pinned as claimed only by the disabled tombstone row and
    absent from `wrangler.toml`.

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
