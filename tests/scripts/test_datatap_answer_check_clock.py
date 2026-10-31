"""Pin: the retired DataTap answer integrity check stays retired (#DIG-306, DIG-4435).

The check ran hourly at minute 17 on the digithings-cron Worker until
2026-10-18, when Chris retired it: the client manages their own
infrastructure, so we do not probe them on a schedule. The Worker row went
once the 2026-10-27 deploy dropped the trigger, and the workflow file itself
was deleted with the GHA exit ledger. ``make datatap-answer-check`` and
``scripts/datatap_answer_integrity_check.py`` stay for a human to run by hand.

These pins assert that nothing can dispatch it again:

* the workflow file is gone;
* no ``[triggers] crons`` entry in ``wrangler.toml`` carries its cron;
* no ``wd()`` row in ``jobs.ts`` names the job or the file;
* the retired cron is claimed by no row.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "datatap-answer-check.yml"
JOBS_SOURCE = REPO_ROOT / "apps" / "digithings-cron" / "src" / "jobs.ts"
WRANGLER = REPO_ROOT / "apps" / "digithings-cron" / "wrangler.toml"

CRON = "17 * * * *"
JOB_ID = "datatap-answer-check"


def test_the_workflow_file_is_gone() -> None:
    """Deleted with the GHA exit ledger; a human runs the make target instead."""
    assert not WORKFLOW.exists(), (
        f"{WORKFLOW.relative_to(REPO_ROOT)} is back: the retired check has a dispatch target again"
    )


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


def test_the_clock_row_is_gone_from_the_cron_worker() -> None:
    """Retired 2026-10-18 (Chris); deleted once the deploy dropped its trigger.

    The row stayed as a disabled tombstone only while the deployed Worker still
    carried the `17 * * * *` trigger, because the deployed-trigger contract
    fails a deployed cron that no job row claims and the merge that removes the
    trigger could not land with the row gone. The digithings-cron deploy of
    2026-10-27T01:26:47Z dropped the trigger and no :17 dispatch has fired
    since, so the tombstone has no claim left to hold.
    """
    assert not _retired_row(), (
        f'jobs.ts still carries a wd("{JOB_ID}", …) row: the retired check has a claimant again'
    )


def test_no_clock_row_targets_this_workflow() -> None:
    """No Worker row may name this workflow file any more."""
    text = _jobs_code()
    assert "datatap-answer-check.yml" not in text, (
        "a jobs.ts row names that workflow file: it would dispatch the retired check"
    )


def test_the_retired_cron_is_claimed_by_no_row() -> None:
    """The retired cron belongs to no Worker row and no trigger."""
    claims = _jobs_code().count('"' + CRON + '"')
    assert claims == 0, (
        f'the retired cron "{CRON}" is claimed by {claims} rows; '
        "any claim would keep dispatching it"
    )


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
    other. The retired check's own minute-17 clock and the tombstone that
    claimed it are both gone (DIG-4435), so `CRON` here is pinned as claimed by
    no row and absent from `wrangler.toml`.

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
