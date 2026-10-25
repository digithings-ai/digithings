"""Run the policy gate's ``--live`` read, or say visibly why it could not run.

WHY THIS EXISTS
``scripts/check_required_policy_checks.py`` reads develop's required status
contexts from a committed snapshot (``.github/required-contexts.txt``), because
no workflow token can read branch protection: ``administration`` is not a
permission ``GITHUB_TOKEN`` can hold. That leaves one gap. A branch-protection
edit nobody re-read the API after changes the live gate while the snapshot stays
put, and the guard goes on checking a fiction. The PR path cannot close it —
putting the read there would put a human-only credential in front of every
merge (``docs/ops/policy-check-credential.md`` §1).

So the live read runs **off the PR path, on demand**, and this script is the one
entry point for it. It is deliberately not a second copy of the guard: it takes
the credential, hands it to the guard through ``GH_TOKEN``, and turns the
guard's answer into a scheduling decision.

THE CREDENTIAL
``POLICY_CHECK_READER_TOKEN`` — the fine-grained PAT registered in
``docs/ops/policy-check-credential.md``: one repository, ``Administration:
read`` only, 90-day expiry. It is the only credential that can read develop's
protection, and it is never printed, logged or passed as an argv value: the
guard sees it in its environment and nowhere else.

A SKIP IS NOT A GREEN
When the token is absent this run exits 0 with a ``SKIPPED`` line naming what
was not checked, because a check that fails for want of its own secret is a
check somebody switches off — the lesson of #2541 and the reason
``docs/ops/policy-check-credential.md`` § *Staleness detector* asks for
*unvalidated*, never *failed*. The line is loud on purpose: exit 0 means "did
not run", never "agreed". A token that is present and **cannot read** is not a
skip — it exits 2, because a credential that stopped working is a real red and
must not be mistaken for a quiet day.

A VERDICT, NOT JUST AN EXIT CODE
An uncaught exception in the guard also exits 1, which is the drift code. So
this script captures the guard's output and accepts exit 1 as drift only when
the guard printed its ``policy-gate-verdict: drift`` marker; anything else is
"could not run" (2). A crashed guard must never be recorded as a policy
finding, and the reverse — a real finding recorded as a crash — loses the one
line a reader needs.

WHAT A RUN RECORDS
Every verdict line carries a UTC timestamp and the run's identity: the Actions
run id and URL inside Actions, the hostname on a plain host. That is what makes
a green run citable after the log has scrolled away, and it is the evidence
DIG-5536 asks for.

EXIT CODES
0    the gate ran and agreed — or the run skipped for want of the credential
     (the printed line says which; ``SKIPPED`` is never a green)
1    the gate ran and found drift between the live gate and the inventory
2    the gate could not run: the credential could not read, the guard raised,
     or the guard exited 1 without printing a drift verdict

USAGE
    python3 scripts/policy_gate_live.py
    POLICY_CHECK_READER_TOKEN=... python3 scripts/policy_gate_live.py \\
        --repo digithings-ai/digithings --branch develop
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "check_required_policy_checks.py"

#: The guard's last line. Present only when the guard reached a verdict, so it
#: is what separates "drift" from "the guard crashed on its way to one".
GUARD_VERDICT_PREFIX = "policy-gate-verdict:"

#: The name, never the value. The registry document owns the credential; this
#: module only knows where to look for it.
TOKEN_ENV = "POLICY_CHECK_READER_TOKEN"

#: The one line a reader (and a log search) can rely on. `SKIPPED` is spelled in
#: full so a green run and a skip cannot be confused in a step summary.
PREFIX = "policy-gate-live:"

Runner = Callable[..., subprocess.CompletedProcess[str]]


def _step_summary(line: str) -> None:
    """Append a line to the Actions step summary when there is one.

    The GitHub summary is where a dispatch is read, and a skip that lives only
    in a log line scrolls away. Outside Actions this writes nothing, so the
    script stays a plain command on a host.
    """
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line.rstrip("\n") + "\n")
    except OSError:
        # A summary that will not open must not change the verdict of the read.
        return


def _identity(env: Mapping[str, str], *, now: datetime | None = None) -> str:
    """`<UTC timestamp> on <run or host>` — the citation a verdict line carries.

    Inside Actions the run id and URL are strictly more useful than the runner's
    ephemeral hostname, so both are printed; on a plain host the hostname is the
    only identity there is. The timestamp is always UTC so two runs on different
    machines cannot look ordered when they are not.
    """
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    timestamp = stamp.strftime("%Y-%m-%dT%H:%M:%SZ")
    host = socket.gethostname() or "unknown-host"
    run_id = (env.get("GITHUB_RUN_ID") or "").strip()
    server = (env.get("GITHUB_SERVER_URL") or "https://github.com").rstrip("/")
    repo = (env.get("GITHUB_REPOSITORY") or "").strip()
    if run_id and repo:
        return f"{timestamp} on {host} (run {run_id}: {server}/{repo}/actions/runs/{run_id})"
    return f"{timestamp} on {host}"


def _announce_skip(env: Mapping[str, str]) -> int:
    """Report a run that could not happen, loudly, and exit 0.

    Exit 0 because the PR path and the dispatch both stay green when the
    credential is absent — the leaf's constraint — and because a red for a
    missing secret trains people to ignore the check. Loud because the
    alternative failure mode is a check that has never run reading as healthy.
    """
    lines = [
        f"{PREFIX} SKIPPED at {_identity(env)} — {TOKEN_ENV} is not set, so develop's "
        "live gate was NOT read.",
        f"{PREFIX} this run proves nothing about drift: it did not reach the API.",
        f"{PREFIX} provision the credential per docs/ops/policy-check-credential.md "
        "(Provisioning, steps 1-2), then run this again.",
    ]
    for line in lines:
        print(line, file=sys.stderr)
    print(f"::warning::policy-gate-live skipped: {TOKEN_ENV} is not provisioned, "
          "so the snapshot was not checked against the live gate")
    _step_summary(
        "### policy-gate-live: SKIPPED\n\n"
        f"{_identity(env)}\n\n"
        f"`{TOKEN_ENV}` is not set, so develop's live branch protection was **not** read. "
        "This run says nothing about drift. See `docs/ops/policy-check-credential.md`.\n"
    )
    return 0


def _child_env(env: Mapping[str, str], token: str) -> dict[str, str]:
    """The environment the guard runs in: the token under `GH_TOKEN`, nothing else new.

    `GITHUB_TOKEN` is dropped rather than left in place. Two credentials in one
    environment is how a run reads as the wrong identity: `gh` prefers
    `GH_TOKEN`, and a reader of the log should not have to know that to say
    which credential made the call.
    """
    child = dict(env)
    child.pop("GITHUB_TOKEN", None)
    child["GH_TOKEN"] = token
    return child


def _verdict(stdout: str) -> str:
    """The guard's own verdict word, or an empty string when it printed none.

    Last match wins so a guard that somehow printed both cannot be read as
    agreement. Exact-word parsing keeps `drift` from matching a word that merely
    contains it.
    """
    written = [
        line.strip().removeprefix(GUARD_VERDICT_PREFIX).strip()
        for line in stdout.splitlines()
        if line.strip().startswith(GUARD_VERDICT_PREFIX)
    ]
    return written[-1] if written else ""


def run(
    *,
    repo: str,
    branch: str,
    token: str,
    env: Mapping[str, str] | None = None,
    runner: Runner | None = None,
    guard: Path = GUARD,
) -> int:
    """Run the guard's `--live` read once, and return its verdict as this script's.

    The guard's output is captured, echoed in full, and then inspected for its
    own verdict marker. Capturing is what makes the exit code honest: Python
    exits 1 on an uncaught exception, so treating a bare 1 as drift would let a
    crashed guard masquerade as a policy finding.
    """
    resolved = env if env is not None else os.environ
    child = _child_env(resolved, token)
    command = [
        sys.executable,
        str(guard),
        "--live",
        "--repo",
        repo,
        "--branch",
        branch,
    ]
    completed = (runner or subprocess.run)(
        command, env=child, check=False, capture_output=True, text=True
    )
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    if stdout:
        print(stdout, end="", file=sys.stdout)
    if stderr:
        print(stderr, end="", file=sys.stderr)
    # The verdict must read *after* the evidence it summarises. stdout is block
    # buffered when the log is piped, so without this the one-line verdict can
    # appear above the guard output it refers to.
    sys.stdout.flush()
    sys.stderr.flush()
    code = completed.returncode
    verdict = _verdict(stdout)
    identity = _identity(resolved)
    if code == 0 and verdict == "agree":
        print(
            f"{PREFIX} GREEN at {identity} — the live gate agrees with the "
            f"inventory ({repo}@{branch}).",
            file=sys.stderr,
        )
        _step_summary(
            f"### policy-gate-live: GREEN\n\n"
            f"{identity}\n\n"
            f"The live required checks on `{repo}@{branch}` agree with "
            "`.github/policy-checks.yml` and with the committed snapshot.\n"
        )
        return 0
    if code == 1 and verdict == "drift":
        print(
            f"{PREFIX} DRIFT at {identity} — the live gate and the inventory "
            f"disagree ({repo}@{branch}). Every disagreement is listed above.",
            file=sys.stderr,
        )
        _step_summary(
            f"### policy-gate-live: DRIFT\n\n"
            f"{identity}\n\n"
            f"`{repo}@{branch}` disagrees with `.github/policy-checks.yml` or the "
            "committed snapshot. The log above names each disagreement.\n"
        )
        return 1
    print(
        f"{PREFIX} could not run at {identity}: the guard exited {code} with "
        f"verdict {verdict or 'absent'} ({repo}@{branch}). A credential that "
        "cannot read is not a skip, and a crashed guard is not drift.",
        file=sys.stderr,
    )
    _step_summary(
        f"### policy-gate-live: COULD NOT RUN\n\n"
        f"{identity}\n\n"
        f"The guard exited `{code}` with verdict `{verdict or 'absent'}`. This is "
        "not a drift verdict and not a skip: the live gate was not reconciled.\n"
    )
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the policy gate's live branch-protection read."
    )
    parser.add_argument("--repo", default="digithings-ai/digithings", help="owner/name")
    parser.add_argument("--branch", default="develop", help="branch whose gate is read")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    runner: Runner | None = None,
    guard: Path = GUARD,
) -> int:
    args = build_parser().parse_args(argv)
    resolved = os.environ if env is None else env
    token = (resolved.get(TOKEN_ENV) or "").strip()
    if not token:
        return _announce_skip(resolved)
    return run(
        repo=args.repo,
        branch=args.branch,
        token=token,
        env=resolved,
        runner=runner,
        guard=guard,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
