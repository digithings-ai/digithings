"""Pin: `make datatap-answer-check` reports the script's exit code on a text line.

This line is an API contract with exactly one consumer and, until now, no test.

`.github/workflows/datatap-answer-check.yml` runs `make datatap-answer-check`
and then recovers the script's real status out of the captured log with

    real=$(awk '/^datatap-answer-check: exit [0-9]+$/ { code = $NF } END { print code }' "$LOG")

It has to, and it should keep having to. GNU make returns 2 for *any* failing
recipe and can never return 1 (a child exiting 1 and a child exiting 2 both
surface as make exit 2), so make's own status cannot separate the two hours that
mean opposite things: exit 1 is a fabrication found, exit 2 is a check that could
not see the answer at all. The recipe echoes the real code on a
`datatap-answer-check: exit N` line because that line is the only channel which
carries it.

The failure this file exists to prevent: someone renames or rewords the echoed
line, and every hourly dispatch of the check starts failing at exit 2 with
`::error::make exited N without datatap-answer-check reporting a status` — which
is indistinguishable from DataTap being unreachable, and points at the wrong
file. Nothing else in the suite noticed, because nothing else read the line.

So the pin is deliberately two-sided. `test_the_recipe_echoes_the_exit_status_on_the_report_line`
fixes the recipe's wording; `test_the_workflow_parses_that_exact_pattern` fixes
the workflow's; and `test_both_sides_agree_on_the_line_for_every_status` reads
the wording out of the recipe, the pattern out of the workflow, and checks the
two really do agree for every status the check can return. A coordinated change
to both sides stays legal — the pair is the contract, not either half alone.

Deliberately a `make -n` dry run: it pins the recipe's text without running the
probe, so this file touches no network and DataTap production (the same reason
the workflow's own awk works on a log it has already captured).

Two things about that spellings pin are deliberate, because both look like
pedantry and neither is:

* It matches `echo "…$code"` with **double** quotes only. With single quotes the
  shell prints a literal `$code`, the workflow's `[0-9]+` never matches, and the
  real status is silently read as "could not see the answer" — the exact failure
  this file exists to prevent, and one no dry run can show you.
* It is otherwise an exact match, so moving the recipe to `printf`, or quoting
  differently, goes red. That is on purpose: a spelling change is a moment to
  confirm by hand that the new spelling still prints the same line, and to move
  the pin in the same commit. Note the dry run prints the recipe *expanded*, so
  `$$code` arrives here as `$code`.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "datatap-answer-check.yml"

TARGET = "datatap-answer-check"
#: What the recipe prints, and the workflow's pattern over it. Both sides of the
#: same contract; neither is allowed to drift from the other on its own.
ECHOED = 'datatap-answer-check: exit $code'
REPORT_PATTERN = r"/^datatap-answer-check: exit [0-9]+$/"

#: The only three statuses the check can return. `test_datatap_answer_integrity_check.py`
#: pins each of them against the script's own `OK` / `FAIL` / `COULD_NOT_RUN`.
STATUSES = (0, 1, 2)


def _recipe() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


def _dry_run() -> str:
    """`make -n`: the recipe as make would run it, with nothing actually run."""
    if not shutil.which("make"):
        pytest.skip("make is not on PATH; the report line is emitted by make")
    out = subprocess.run(
        ["make", "-n", TARGET],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert out.returncode == 0, f"make -n {TARGET} failed:\n{out.stderr}"
    return out.stdout


def _awk_pattern() -> str:
    """The pattern the workflow recovers the status with, read out of the workflow.

    Comment lines are skipped. Leaving the old pattern behind in a comment while
    loosening the live awk is the sneakiest way to break this contract, and a
    plain whole-file search would keep reading the comment and call it fine.
    """
    body = WORKFLOW.read_text(encoding="utf-8")
    live = "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )
    found = re.search(r"awk\s+'/(?P<pattern>[^/]+)/", live)
    assert found, (
        "the workflow no longer recovers the status with an awk '/…/' pattern; "
        "make's own exit code cannot carry it, so the log is the only channel"
    )
    return found.group("pattern")


def test_the_make_target_exists() -> None:
    """Fixture guard: every pin below is about this target, so it must be there."""
    assert re.search(rf"^{re.escape(TARGET)}:", _recipe(), flags=re.MULTILINE), (
        f"the Makefile has no `{TARGET}` target; nothing below has anything to pin"
    )


def test_the_recipe_echoes_the_exit_status_on_the_report_line() -> None:
    """The workflow recovers the script's exit code from this exact line.

    Pinned on `make -n` rather than on the Makefile's source text, so the
    assertion is about the line make actually emits — which is what lands in the
    log the workflow greps — instead of about indentation or line continuation.
    """
    dry = _dry_run()
    assert re.search(rf'echo\s+"{re.escape(ECHOED)}"', dry), (
        f"the {TARGET} recipe no longer echoes `{ECHOED}` with double quotes, and the "
        f"workflow reads that line and nothing else carries the script's real status. "
        f"If the spelling changed deliberately, confirm the new spelling still prints "
        f"`datatap-answer-check: exit N` and move this pin in the same commit. "
        f"make -n said:\n{dry}"
    )


def test_the_workflow_parses_that_exact_pattern() -> None:
    """The consumer half. Loosening the awk pattern breaks the contract silently."""
    pattern = _awk_pattern()
    assert pattern == REPORT_PATTERN.strip("/"), (
        f"the workflow parses /{pattern}/, not {REPORT_PATTERN}; it must keep matching "
        "the line the recipe prints, or a real exit code is read as 'no status'"
    )


def test_the_recipe_still_fails_so_make_never_reports_a_dirty_check_green() -> None:
    """The other half of the reason the workflow reads the log at all.

    A plausible response to the report line breaking is to make the target
    succeed — but a green make over a failed probe is the one outcome worth
    failing closed for, and the workflow's make-versus-report reconciliation
    (fail when make failed but the line claims 0) only fires when make failed.
    Anchored to the line start on purpose: an unanchored `exit $code` also matches
    `echo "exit $code"`, which reports success over a detected fabrication while
    this test stays green.
    """
    dry = _dry_run()
    assert re.search(r'(?m)^[ \t]*exit[ \t]+"?\$code"?[ \t]*;?[ \t]*$', dry), (
        f"the {TARGET} recipe must exit with the script's own status so make reports "
        f"failure; make -n said:\n{dry}"
    )


def test_both_sides_agree_on_the_line_for_every_status() -> None:
    """The contract itself: recipe wording and workflow pattern, read from the files.

    This is the test that survives a half-finished edit. Renaming the prefix in
    the recipe leaves the workflow's pattern matching nothing; loosening the
    workflow's pattern leaves it no longer reading the recipe's line. Either way
    one of the two drift tests above fires too — this one says *which pair* broke.
    The echo is selected by the contract's own prefix so that an unrelated
    diagnostic echo added to the recipe does not trip this.
    """
    dry = _dry_run()
    echoed = re.search(rf'echo\s+"(?P<line>{re.escape(TARGET)}[^"]*)"', dry)
    assert echoed, (
        f"the {TARGET} recipe echoes no line starting with `{TARGET}`; make -n said:\n{dry}"
    )

    compiled = re.compile(_awk_pattern())
    for code in STATUSES:
        # `$$code` and `$code` both print the same line; make expands one of them.
        printed = re.sub(r"\$\$?code\b", str(code), echoed.group("line"))
        assert compiled.match(printed), (
            f"the {TARGET} recipe prints `{printed}` for exit {code}, which the "
            "workflow's awk pattern does not match, so a real exit code would be "
            "read as DataTap being unreachable"
        )


def test_a_reworded_report_line_is_invisible_to_the_workflow() -> None:
    """Negative control, so the pins above cannot pass vacuously.

    `test_the_workflow_parses_that_exact_pattern` already catches a straight
    `/.*/`, so what this adds is the sneakier version: the awk loosened while the
    old literal is left behind in a comment, where the exact-string pin still
    finds it. The workflow only benefits from the pattern's shape because `^` and
    `$` anchor it and the status has to be digits, so that is what is pinned.
    """
    compiled = re.compile(_awk_pattern())

    assert not compiled.match("datatap-answer-check: exited 2"), (
        "the workflow would accept a line the recipe no longer prints"
    )
    assert not compiled.match("datatap-answer-check: exit two"), (
        "the workflow would read a non-numeric status as a number"
    )
    assert not compiled.match("COULD NOT RUN: exit 2"), (
        "the workflow would accept a line with no target prefix"
    )
    assert not compiled.match("datatap-answer-check: exit 2 (see log)"), (
        "the workflow must reject trailing text, or a reworded line keeps matching"
    )