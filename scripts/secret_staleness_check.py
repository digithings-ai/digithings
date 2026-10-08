#!/usr/bin/env python3
"""Names-only ageing check for GitHub Actions secrets (#248).

`gh secret list` and `gh api .../actions/secrets` return a name and a
last-written date and never a value, so this check never reads a single
credential. That part is the point: the 90-day rotation rule in
`docs/ops/SECRETS_INVENTORY.md` was a memory exercise, and this turns it into a
control instead of an intention.

    python3 scripts/secret_staleness_check.py                     # report, no issue
    python3 scripts/secret_staleness_check.py --file-names a.txt   # offline, no `gh`
    python3 scripts/secret_staleness_check.py --open-issue         # file the tracker
    python3 scripts/secret_staleness_check.py --max-age-days 60
    python3 scripts/secret_staleness_check.py --gates-only         # gates only, no `gh`

Three levels are aged, because each has its own rotation blast radius:

    repo       a secret any workflow on any branch could read   (needs `repo` scope)
    org        inherited by every repo in the org              (needs `admin:org`)
    cron       the environment scope the CI reads moved to in #248

Every one of those endpoints needs a token with the `repo` or `admin:org` scope.
**A workflow's GITHUB_TOKEN has neither**: it is a GitHub App installation token,
and GitHub's `permissions:` vocabulary has no key for secrets at all, so no grant
in a workflow file can make these three listings readable. This was measured, not
assumed — run 37235973852 on `develop` had `actions: read` visibly granted and all
three listings still answered `Resource not accessible by integration (HTTP 403)`.
So run this from a shell that holds a token with those scopes — `gh auth` on
Chris's Mac already carries `repo` and `admin:org` — or pass `--file-names`. It
does NOT run from the Keymaster weekly key report, which is built from Bitwarden
and never reads this API.

Run from CI, it reads nothing. By decision (Paperclip DIG-477, option D, 2026-10-05)
the ageing half is not automated at all, so `secret-staleness-check.yml` invokes
this script with `--gates-only`, which skips the three listings entirely and does
only the environment-gate comparison described below. If it is nevertheless run in
full from CI, every level is reported as NOT CHECKED with the reason printed; see
`--strict-offline` for turning that into a non-zero exit when a report must not be
trusted.

Not a hard gate. `--fail-overdue` exits 1 when anything is overdue, which CI
does *not* use: a stale credential is a decision for a human (rotate now, or
record why not), and a red build is not that decision. Where a token does allow
the read — the manual `make secrets-staleness` run — it files or updates one
tracking issue, but it files nothing at all when not one level could be read,
because a monthly issue reading "I could not do my job" is noise wearing a
tracker's clothes.

Reading nothing from an operator shell does not close a tracker either, and
exits 2 rather than 0. CLOSE_NOTE explains the unreadable run as CI's missing
token scope, which is true of a CI run and false of a hand run whose `gh auth`
has gone stale; since option D the two are not the same event, because CI runs
`--gates-only` and never reaches this path. `--close-unmeasurable-tracker`
restores the close when an operator means it.

Offline switch: `--file-names` reads `SCOPE\\tNAME\\tUPDATED` lines so the
ageing logic can be tested without `gh`, and `--strict-offline` refuses to
report success when the input came from a file rather than the live API.

A second, sharper question rides along: **can the `cron` gate still stall?** The 32
jobs declared `environment: cron` in #248 are only safe because that environment
has no required reviewer and no wait timer. Both are armed from the GitHub UI,
where no test runs, and the failure mode is #2541 again — pipelines stop, with
every assertion still green. So this also reads
`.github/environments.json` (written by #248) and compares it to the live
protection rules, and **exits 1 on drift**. Drift is worth failing on where an
overdue secret is not: a stale credential is a human's decision, a stalled
automation is not.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: A repo secret on a pull-request branch is readable by anything that can push a
#: branch, so the bar for leaving one in place is 90 days.
DEFAULT_MAX_AGE_DAYS = 90

#: `gh secret list --org` needs `admin:org`. A workflow's GITHUB_TOKEN is a GitHub
#: App installation token and never has it, so the org level is best-effort from
#: CI and authoritative only from an operator's shell.
ORG_SCOPE_REQUIRES_ADMIN = "admin:org"

#: Why a level reads as unavailable, in the words a human needs at 06:17 on the 1st.
#: `GET .../actions/secrets` documents that it needs the `repo` scope, and
#: GITHUB_TOKEN is an installation token whose `permissions:` vocabulary has no key
#: for secrets at all — so from CI this is a certainty, not a suspicion. Run
#: 37235973852 measured it with `actions: read` visibly granted and all three
#: listings still 403. Naming the scope matters: the raw reason used to read
#: `repo secret list unavailable for digithings-ai/digithings`, which is true and
#: tells a reader nothing about what to do next.
SCOPE_NEEDS_TOKEN_SCOPE = (
    "needs a token with the `repo` scope, which a workflow's GITHUB_TOKEN never has "
    "(run 37235973852 measured this with `actions: read` granted); read it from an "
    "operator shell, where `gh auth` already has `repo` and `admin:org`"
)

SCOPES = ("repo", "org", "cron")

ISSUE_TITLE = "Ops: GitHub secrets past the 90-day rotation window"
ISSUE_MARKER = "<!-- secret-staleness-check -->"

#: Labels put on the tracker issue. `gh api`'s field flags only take strings, and a
#: string here is rejected as `For 'properties/labels', "ops" is not an array`
#: (HTTP 422) whatever the name is, so the array goes out as an explicit JSON body.
#: Every name must also already exist in the repo; there is no CI path that could
#: create a label first, and an unknown name fails the create on its own.
ISSUE_LABELS = ("security:finding",)

#: Order in which an overdue name is reported: widest blast radius first, so a
#: truncated issue body still leads with the worst of it. An org secret is
#: inherited by every repo in the org; a repo secret is readable by any workflow on
#: any branch of this repo; an environment secret is reachable only by jobs that
#: declare that environment, which after #248 is the CI read set.
SCOPE_ORDER = {"org": 0, "repo": 1, "cron": 2}

#: What `--gates-only` reports instead of an ageing verdict. Paperclip DIG-477,
#: option D (Chris, 2026-10-05): keep the drift check, drop the ageing from
#: automation. A monthly tracker that can never name a secret is noise wearing a
#: tracker's clothes, and giving CI a token that could read the listings means
#: standing up the exact category of repo-scoped credential #248 exists to
#: shrink. Rotation stays a human decision recorded in
#: `docs/ops/SECRETS_INVENTORY.md`, which already lists the 16 names measured
#: past the window on 2026-10-04.
#:
#: The wording is load-bearing. `ageing_verdict()`'s "nothing was read" branch is
#: *true* in gates-only mode and reads as a failure, which would put a
#: red-sounding sentence in a green run every month and train readers to ignore
#: it. Nothing is broken here, so nothing should read as though it were. Same
#: defect as #5078, opposite direction.
GATES_ONLY_NOTE = (
    "It is out of automation by decision (DIG-477, option D): the secret listings "
    "need a token carrying the `repo` scope, which no workflow grant can supply, so "
    "this half could only ever come back unread. Rotation is a human decision, "
    "recorded in `docs/ops/SECRETS_INVENTORY.md`. Run `make secrets-staleness` from "
    "a shell whose `gh auth` already has `repo` and `admin:org` to age the names by "
    "hand."
)


@dataclass(frozen=True)
class Secret:
    """One secret's name and last-written date. Never its value."""

    scope: str
    name: str
    updated_at: datetime

    @property
    def age_days(self) -> int:
        return max(0, (datetime.now(timezone.utc) - self.updated_at).days)


@dataclass
class Report:
    """The ageing result, plus whatever could not be checked.

    `readable` is how many levels were actually served. It cannot be inferred from
    `secrets` and `unavailable`: `main()`'s `--file-names` path builds a report
    with both empty having read nothing at all, which is indistinguishable from a
    repo whose listings all came back empty. Deriving "nothing to age" from that
    produced a run that printed "Every level was readable" over a zero-byte file
    and exited 0. `None` means "not stated", so a hand-built report keeps working
    and only `collect()` — the one path that knows — asserts a number.
    """

    secrets: list[Secret] = field(default_factory=list)
    unavailable: dict[str, str] = field(default_factory=dict)
    readable: int = 0

    @property
    def read_any(self) -> bool:
        """Whether any level was actually served. False means no count is possible."""
        return self.readable > 0

    def overdue(self, max_age_days: int) -> list[Secret]:
        """Overdue names, widest scope first, then oldest first."""
        hits = [s for s in self.secrets if s.age_days > max_age_days]
        return sorted(hits, key=lambda s: (SCOPE_ORDER.get(s.scope, 99), -s.age_days, s.name))

    def by_scope(self) -> dict[str, list[Secret]]:
        grouped: dict[str, list[Secret]] = {}
        for secret in self.secrets:
            grouped.setdefault(secret.scope, []).append(secret)
        return grouped


def parse_timestamp(raw: str) -> datetime:
    """An API timestamp as an aware UTC datetime.

    GitHub returns `2026-09-05T21:11:19Z`; a hand-written offline fixture may omit
    the zone, which is read as UTC rather than as local time.
    """
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_tsv(raw: str) -> list[Secret]:
    """`SCOPE\\tNAME\\tUPDATED` lines into secrets. Blank lines are ignored.

    This is the `gh secret list` shape (tab separated) with a scope prefix, so an
    operator can paste one straight out of a shell.
    """
    out: list[Secret] = []
    for number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) != 3:
            raise ValueError(f"line {number}: expected 3 tab-separated fields, got {len(fields)}")
        scope, name, updated = (f.strip() for f in fields)
        if scope not in SCOPES:
            raise ValueError(f"line {number}: unknown scope {scope!r}, expected one of {SCOPES}")
        try:
            stamp = parse_timestamp(updated)
        except ValueError as exc:
            raise ValueError(f"line {number}: bad timestamp {updated!r}: {exc}") from exc
        out.append(Secret(scope=scope, name=name, updated_at=stamp))
    return out


def _gh_json(cmd: list[str], root: Path, stdin: str | None = None) -> object | None:
    """Parsed `gh` JSON, or None with a one-line reason on stderr.

    A paginated call is given `--slurp`, so it comes back as a list of pages rather
    than as one object. This is hardening rather than a fix for the 2026-10-04 false
    green: `--paginate` on its own prints one JSON document per page and `json.loads`
    cannot read that (`Extra data: line 1 column 244` on this repo's secrets listing
    at two per page). It had not bitten yet only because the 20 repo secrets fit one
    page of 30 and the 403 came first. gh rejects `--slurp` beside `--jq`, and
    requires it nowhere else, so a call that filtered server-side has to filter here.
    """
    if "--paginate" in cmd and ({"--jq", "--template"} & set(cmd)):
        # Stated as a rule in the docstring, enforced here because the alternative is
        # discovering it the way 2026-10-04 did: one bad call site, one hard gh error
        # inside CI, one silently dead check.
        raise ValueError(
            "gh refuses --slurp beside --jq/--template, so this call cannot both page "
            "and filter server-side. Filter the parsed pages here instead."
        )
    if "--paginate" in cmd and "--slurp" not in cmd:
        at = cmd.index("--paginate") + 1
        cmd = [*cmd[:at], "--slurp", *cmd[at:]]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, cwd=root, input=stdin
        )
    except FileNotFoundError:
        print("secret_staleness_check: `gh` not found on PATH", file=sys.stderr)
        return None
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        print(f"secret_staleness_check: `{' '.join(cmd)}` failed: {detail}", file=sys.stderr)
        return None
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        print(
            f"secret_staleness_check: could not parse `{' '.join(cmd)}` output: {exc}",
            file=sys.stderr,
        )
        return None


def _pages(payload: object) -> list[object]:
    """A `--slurp` result as its pages; an unpaginated object as a single page."""
    return payload if isinstance(payload, list) else [payload]


def _secret_entries(payload: object) -> list[dict] | None:
    """Every `.secrets` entry across the pages, or None when it is not that shape.

    None is the important return: the caller turns it into "unavailable", and
    "unavailable" must never be reported to a human as an empty list, because an
    empty list reads as "nothing is overdue".
    """
    entries: list[dict] = []
    pages = _pages(payload)
    if not pages:
        return None
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("secrets"), list):
            return None
        entries.extend(e for e in page["secrets"] if isinstance(e, dict))
    return entries


def _aged(entries: list[dict], scope: str) -> tuple[list[Secret], str | None]:
    """Turn listing entries into `Secret`s, or explain why an entry could not be aged.

    An entry whose date will not parse is a reason, not a row to drop. Dropping it
    would shrink the denominator and let the run say "nothing is overdue" while a
    name it could not date went unmentioned.
    """
    out: list[Secret] = []
    for entry in entries:
        name, updated = entry.get("name"), entry.get("updated_at")
        label = name if isinstance(name, str) else "<unnamed>"
        if not isinstance(name, str) or not isinstance(updated, str):
            return [], f"{scope} secret {label} has no readable name or updated_at"
        try:
            out.append(Secret(scope, name, parse_timestamp(updated)))
        except ValueError as exc:
            return [], f"{scope} secret {name} has an unreadable updated_at: {exc}"
    return out, None


def repo_secrets(root: Path, repo: str) -> tuple[list[Secret], str | None]:
    """Repo-scope secrets with their last-written dates."""
    payload = _gh_json(["gh", "api", "--paginate", f"repos/{repo}/actions/secrets"], root)
    entries = _secret_entries(payload)
    if entries is None:
        return [], f"repo secret list unavailable for {repo}: {SCOPE_NEEDS_TOKEN_SCOPE}"
    return _aged(entries, "repo")


def org_secrets(root: Path, org: str) -> tuple[list[Secret], str | None]:
    """Org-scope secrets. Needs `admin:org`, so it never works from CI."""
    payload = _gh_json(["gh", "api", "--paginate", f"orgs/{org}/actions/secrets"], root)
    entries = _secret_entries(payload)
    if entries is None:
        return [], (
            f"org secret list unavailable: needs {ORG_SCOPE_REQUIRES_ADMIN}, "
            f"which a workflow's GITHUB_TOKEN never has"
        )
    return _aged(entries, "org")


def environment_secrets(root: Path, repo: str, environment: str) -> tuple[list[Secret], str | None]:
    """Environment-scope secrets, aged like the others.

    After #248 this is where every CI read lives, so ageing it is how we notice a
    name that came back to repo scope.
    """
    payload = _gh_json(
        [
            "gh",
            "api",
            "--paginate",
            f"repos/{repo}/environments/{environment}/secrets",
        ],
        root,
    )
    entries = _secret_entries(payload)
    if entries is None:
        return [], (
            f"environment {environment!r} secret list unavailable: {SCOPE_NEEDS_TOKEN_SCOPE}"
        )
    return _aged(entries, environment)


ENVIRONMENT_MANIFEST = REPO_ROOT / ".github" / "environments.json"

#: The rules that decide whether a job gated on an environment can sit in a queueing
#: concurrency group (#2541). Required reviewers and a wait timer both hold the run;
#: a branch policy instead *skips* the job on a non-matching ref, which is loud.
GATE_RULES = ("wait_timer_minutes", "required_reviewers", "deployment_branches")


def load_manifest(path: Path | None = None) -> dict[str, object]:
    """The environment manifest, or an empty mapping when it cannot be read."""
    try:
        raw = (path or ENVIRONMENT_MANIFEST).read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def manifest_environments(path: Path | None = None) -> dict[str, dict]:
    """The `environments` map from the manifest."""
    environments = load_manifest(path).get("environments")
    if not isinstance(environments, dict):
        return {}
    return {str(k): v for k, v in environments.items() if isinstance(v, dict)}


def can_wait(rules: dict) -> bool:
    """Whether a run gated on this environment can linger in the approval gate.

    Shared with ``tests/scripts/test_workflow_environment_concurrency.py``, which uses
    it to decide which gated jobs are allowed to share a queueing `concurrency` group.
    Both callers reading one implementation is the point: a test and a report that
    disagree about what is safe is how a gate quietly becomes armed.
    """
    return bool(rules.get("required_reviewers")) or int(rules.get("wait_timer_minutes") or 0) > 0


def protection_rules(payload: object, branches: list[str] | None = None) -> dict[str, object]:
    """Normalise a `GET .../environments/{name}` payload to the manifest shape.

    `branches` comes from the separate `deployment-branch-policies` endpoint, which
    404s when no policy is configured; that is read as `None` (no restriction) rather
    than as an error. `[]` means a policy exists with no branch allowed.
    """
    if not isinstance(payload, dict):
        return {}
    rules = payload.get("protection_rules")
    wait_timer = 0
    reviewers: list[str] = []
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            if rule.get("type") == "wait_timer":
                try:
                    wait_timer = max(wait_timer, int(rule.get("wait_timer") or 0))
                except (TypeError, ValueError):
                    continue
            elif rule.get("type") == "required_reviewers":
                # Each entry is `{"type": "User", "reviewer": {...user object...}}`, so
                # the login is one level down. Reading `entry["login"]` yields `[]` and
                # the environment then looks unreviewed — which is the one direction of
                # error that fails open, so it is asserted against in the tests.
                for entry in rule.get("reviewers") or []:
                    if not isinstance(entry, dict):
                        continue
                    user = entry.get("reviewer")
                    login = user.get("login") if isinstance(user, dict) else None
                    if isinstance(login, str):
                        reviewers.append(login)
    return {
        "wait_timer_minutes": wait_timer,
        "required_reviewers": sorted(reviewers),
        "deployment_branches": None if branches is None else sorted(branches),
    }


def branch_policy_names(payload: object) -> list[str] | None:
    """Branch names from a `deployment-branch-policies` payload, or None when absent.

    None is the meaningful value: GitHub 404s this endpoint for an environment with no
    branch policy, and a manifest that says `null` has to be able to tell that apart
    from a policy that is configured but empty.
    """
    if not isinstance(payload, dict) or payload.get("branch_policies") is None:
        return None
    policies = payload.get("branch_policies")
    if not isinstance(policies, list):
        return None
    return sorted(
        str(p["name"]) for p in policies if isinstance(p, dict) and isinstance(p.get("name"), str)
    )


def gate_drift(expected: dict, actual: dict) -> list[str]:
    """Human-readable differences between manifest rules and the live ones."""
    out: list[str] = []
    for rule in GATE_RULES:
        want = expected.get(rule)
        got = actual.get(rule)
        if want != got:
            out.append(f"{rule}: manifest {want!r}, live {got!r}")
    return out


def environment_gate_status(
    root: Path, repo: str, manifest_path: Path | None = None
) -> tuple[list[dict[str, object]], dict[str, str]]:
    """Live protection rules per manifest environment, plus the drift found.

    The second return value maps an environment name to the reason it could not be
    read, so a missing `admin:org`-style permission is reported rather than read as
    "unchanged".
    """
    rows: list[dict[str, object]] = []
    unavailable: dict[str, str] = {}
    for name, expected in manifest_environments(manifest_path).items():
        payload = _gh_json(["gh", "api", f"repos/{repo}/environments/{name}"], root)
        if not isinstance(payload, dict) or payload.get("name") != name:
            unavailable[name] = f"environment {name!r} could not be read"
            continue
        # The inline `deployment_branch_policy` decides whether a second call is worth
        # making: it is `null` when there is no branch policy at all, so `copilot` and
        # `cron` never hit the `deployment-branch-policies` endpoint (which 404s for
        # them). That also keeps "no policy" from being inferred from a failed request.
        branches = None
        policy = payload.get("deployment_branch_policy")
        if isinstance(policy, dict) and policy.get("custom_branch_policies") is True:
            listed = _gh_json(
                [
                    "gh",
                    "api",
                    f"repos/{repo}/environments/{name}/deployment-branch-policies",
                ],
                root,
            )
            branches = branch_policy_names(listed)
            if branches is None:
                unavailable[name] = (
                    f"environment {name!r} has custom branch policies but their names "
                    "could not be read"
                )
                continue
        actual = protection_rules(payload, branches)
        rows.append(
            {
                "name": name,
                "expected": expected,
                "actual": actual,
                "can_wait": can_wait(actual),
                "drift": gate_drift(expected, actual),
            }
        )
    return rows, unavailable


def collect(root: Path, repo: str, org: str, environment: str = "cron") -> Report:
    """Read every level. A level that cannot be read is recorded, not fatal."""
    report = Report()
    for scope, reader in (
        ("repo", lambda: repo_secrets(root, repo)),
        ("org", lambda: org_secrets(root, org)),
        ("cron", lambda: environment_secrets(root, repo, environment)),
    ):
        secrets, reason = reader()
        report.secrets.extend(secrets)
        if reason:
            report.unavailable[scope] = reason
        else:
            report.readable += 1
    return report


def gate_markdown(
    gates: tuple[list[dict[str, object]], dict[str, str]] | None,
) -> list[str]:
    """The environment-gate section of the report, empty when it was not checked."""
    if gates is None:
        return []
    rows, unavailable = gates
    lines = ["", "## Environment gates", ""]
    if not rows and not unavailable:
        lines.append(
            "No environment manifest found at `.github/environments.json`, so no gate "
            "was checked. Treat the gate as unverified until that file exists."
        )
        return lines
    lines += [
        "| Environment | Live rules | Can a run wait? | Manifest agrees? |",
        "|---|---|---|---|",
    ]
    for row in rows:
        actual = row["actual"] if isinstance(row["actual"], dict) else {}
        waits = "yes" if row["can_wait"] else "no"
        agrees = "yes" if not row["drift"] else "**NO**"
        lines.append(
            f"| `{row['name']}` | {', '.join(f'{k}={v!r}' for k, v in sorted(actual.items()))} "
            f"| {waits} | {agrees} |"
        )
    for name, reason in sorted(unavailable.items()):
        lines.append(f"- `{name}` — NOT CHECKED, {reason}")
    drift = {str(row["name"]): row["drift"] for row in rows if row["drift"]}
    if drift:
        lines += [
            "",
            "**Drift.** A `cron` environment that gained a required reviewer or a wait "
            "timer does not fail a build; it makes every job gated on it stop silently "
            "(#2541). Fix the environment, then re-run to refresh "
            "`.github/environments.json`.",
            "",
        ]
        for name, lines_for in sorted(drift.items()):
            for line in lines_for or ["unknown drift"]:
                lines.append(f"- `{name}`: {line}")
    return lines


def ageing_verdict(report: Report, max_age_days: int, per_level_position: str) -> str:
    """The one sentence that says what this run concluded about staleness.

    Both renderers call this, because they were two hand-maintained copies of the
    same judgement and they disagreed: `markdown()` keyed "nothing could be aged"
    on `report.secrets` while `render()` added `and report.unavailable`, so a
    report where every level was readable but held nothing printed a bare
    `0 of 0 listed` on stdout while the summary claimed nothing had been read.
    Neither was right — every level *had* been read, and the honest answer for an
    empty repo is that there is nothing to age.

    A shared function is the only version of "the two must agree" that a
    reviewer does not have to take on trust. `per_level_position` is "above" from
    `render()` and "below" from `markdown()`, because only `render()` lists the
    unread levels ahead of this line; hard-coding one of them was a sentence that
    was simply false in the other renderer.
    """
    overdue = report.overdue(max_age_days)
    if not report.secrets:
        if report.read_any:
            return (
                f"Every level was readable and none of them holds a secret, so there "
                f"is nothing to age. All {report.readable} level(s) were served."
            )
        if not report.unavailable:
            # Nothing was listed and nothing failed, so naming a count of unread
            # levels would read as "0 of 0 could not be read", i.e. a clean bill.
            # This is the `--file-names` case: a hand-made list, never an API read.
            return (
                "No secrets could be aged: nothing was read, so no count is possible. "
                "This run did not read the live secret listings."
            )
        return (
            f"No secrets could be aged: {len(report.unavailable)} level(s) could "
            f"not be read, so no count is possible. The per-level reason is "
            f"{per_level_position}."
        )
    if report.unavailable:
        return (
            f"{len(overdue)} name(s) past {max_age_days} days among the "
            f"{len(report.secrets)} that could be read; {len(report.unavailable)} "
            "level(s) could not be read. That is not a clean bill of health."
        )
    if overdue:
        return f"{len(overdue)} name(s) past {max_age_days} days of {len(report.secrets)} listed."
    return (
        f"{len(overdue)} name(s) past {max_age_days} days of {len(report.secrets)} "
        "listed. No action needed."
    )


def markdown(
    report: Report,
    max_age_days: int,
    gates: tuple[list[dict[str, object]], dict[str, str]] | None = None,
    gates_only: bool = False,
) -> str:
    """The issue body. Names and ages only — no value ever reaches this string."""
    overdue = report.overdue(max_age_days)
    if gates_only:
        # DIG-477 option D. The ageing section is replaced rather than reported as
        # an empty failure: an empty `report` here means "not attempted", which is a
        # decision, not a failed read, and the two must not look alike on the run
        # page. `gates_markdown` still runs below, so the drift table is unchanged.
        return (
            "\n".join(
                [
                    ISSUE_MARKER,
                    "",
                    "Environment-gate drift check only — `scripts/secret_staleness_check.py"
                    " --gates-only` (#248, DIG-477).",
                    "",
                    "## Secret ageing",
                    "",
                    f"**Secret ageing was NOT RUN.** {GATES_ONLY_NOTE}",
                    "",
                ]
                + gate_markdown(gates)
            )
            + "\n"
        )
    lines = [
        ISSUE_MARKER,
        "",
        "Opened automatically by `scripts/secret_staleness_check.py` (#248).",
        "Names and last-written dates only: GitHub never returns a secret value here.",
        "",
    ]
    if report.secrets:
        listed = f"**{len(report.secrets)}** listed secrets"
        # On a partial read the denominator is the count that was read, so it must
        # say so here rather than only in the trailing `## Levels not checked`.
        if report.unavailable:
            listed += " (of the levels that could be read)"
        lines += [
            f"**{len(overdue)}** of {listed} are past",
            f"**{max_age_days} days** since last written.",
            "",
        ]
    else:
        # "0 of 0 listed secrets are past 90 days" is a positive claim about an empty
        # set, and it was the exact sentence a run printed while every listing 403'd.
        # Appended rather than added to the list, because a wrapped string literal
        # inside a list is implicit concatenation, which CodeQL reads as a lost comma.
        # `readable` distinguishes "every level was served and holds nothing" from
        # "nothing was served", which read identically from the two containers alone.
        lines.append(
            f"**Every level was readable and none of them holds a secret.** All "
            f"{report.readable} level(s) were served and came back empty, so there is "
            "nothing to age. That is a real answer rather than a failed read."
            if report.read_any
            else "**No secrets could be aged.** Nothing below says anything about "
            "whether a secret is stale, because nothing was read."
        )
        lines.append("")
    if overdue:
        lines += ["| Scope | Name | Age (days) | Last written |", "|---|---|---|---|"]
        for secret in overdue:
            lines.append(
                f"| `{secret.scope}` | `{secret.name}` | {secret.age_days} "
                f"| {secret.updated_at.date().isoformat()} |"
            )
        lines.append("")
        lines.append(
            "Rotate, or record here why a name is deliberately long-lived. A name "
            "only counts as rotated when its **last-written date** moves."
        )
    # The verdict closes the report whether or not anything is overdue. It used to
    # sit in an `elif` behind `if overdue:`, which made the partial-read qualifier
    # unreachable in exactly the case it exists for — an overdue name plus an
    # unread level printed a bare `1 of 1 listed` and disclosed the gap only in the
    # trailing `## Levels not checked`. This is the artefact a human reads first,
    # so it is the one that must not overstate.
    lines.append(ageing_verdict(report, max_age_days, "below"))
    if report.unavailable:
        lines += ["", "## Levels not checked", ""]
        lines += [f"- `{scope}` — {reason}" for scope, reason in sorted(report.unavailable.items())]
    lines += gate_markdown(gates)
    return "\n".join(lines) + "\n"


def ordered_scopes(report: Report) -> list[str]:
    """Every level the report actually holds, widest blast radius first.

    A level that read successfully but holds nothing does not appear here, and
    cannot: `Report` carries `secrets` and `unavailable` only, so a scope that
    returned an empty list lands in neither. An earlier version of this docstring
    claimed such a scope printed as `0 name(s)` and used that as its reason to
    exist — a claim `Report` cannot represent, and one the test at
    `test_secret_staleness_check.py` asserts against (`assert "cron:" not in out`).
    The empty-but-readable case is handled by `ageing_verdict` instead, which can
    see it, because it reads `secrets` and `unavailable` together.
    """
    present = {secret.scope for secret in report.secrets}
    return sorted(present, key=lambda scope: (SCOPE_ORDER.get(scope, 99), scope))


def render(
    report: Report,
    max_age_days: int,
    gates: tuple[list[dict[str, object]], dict[str, str]] | None = None,
    gates_only: bool = False,
) -> str:
    """Human-readable stdout, grouped by scope and oldest first."""
    out: list[str] = []
    if gates_only:
        # DIG-477 option D. Nothing was attempted here, so the per-scope listing and
        # the ageing verdict are both skipped rather than reported as an empty
        # result — see `markdown()` for why the two must not look alike.
        out.append("secret ageing: NOT RUN (--gates-only)")
        out.append(GATES_ONLY_NOTE)
    else:
        grouped = report.by_scope()
        for scope in ordered_scopes(report):
            secrets = sorted(grouped.get(scope, []), key=lambda s: -s.age_days)
            out.append(f"{scope}: {len(secrets)} name(s)")
            for secret in secrets:
                marker = "OVERDUE" if secret.age_days > max_age_days else "ok"
                out.append(
                    f"  {marker:>7} {secret.age_days:>5}d  {secret.updated_at.date()}  {secret.name}"
                )
        for scope, reason in sorted(report.unavailable.items()):
            out.append(f"{scope}: NOT CHECKED — {reason}")
        out.append("")
        out.append(ageing_verdict(report, max_age_days, "above"))
    if gates is not None:
        rows, unavailable = gates
        out.append("")
        out.append(f"environment gates: {len(rows)} checked")
        for row in rows:
            mark = "DRIFT" if row["drift"] else "ok"
            waits = "can wait" if row["can_wait"] else "cannot wait"
            out.append(f"  {mark:>5}  {row['name']} ({waits})")
            for line in row["drift"] or []:
                out.append(f"           {line}")
        for name, reason in sorted(unavailable.items()):
            out.append(f"  NOT CHECKED  {name} — {reason}")
    return "\n".join(out)


class TrackerUnreadable(RuntimeError):
    """The open-issue list could not be read, so it is not known whether one is open."""


def _issue_exists(root: Path, repo: str) -> str | None:
    """The number of the open tracker issue, if one is already open.

    Filtering happens here rather than in a `--jq` expression for two reasons. gh
    rejects `--slurp` beside `--jq`, and `--jq` alone under `--paginate` emits one
    value *per page*: with no match on any of three pages it printed three empty
    lines, which `json.loads` refused with `Expecting value: line 3 column 1`. That
    is why the update branch was unreachable and every run tried to create an issue.

    A failed read raises rather than returning None. None means "no tracker is open",
    and on that reading the caller files a fresh one, so a 5xx would duplicate the
    tracker this function exists to keep unique.
    """
    payload = _gh_json(["gh", "api", "--paginate", f"repos/{repo}/issues"], root)
    if payload is None:
        raise TrackerUnreadable(f"could not list issues on {repo}")
    for page in _pages(payload):
        if not isinstance(page, list):
            continue
        for issue in page:
            if not isinstance(issue, dict):
                continue
            if issue.get("state") == "open" and issue.get("title") == ISSUE_TITLE:
                number = issue.get("number")
                if isinstance(number, int):
                    return str(number)
    return None


CLOSE_NOTE = f"""{ISSUE_MARKER}
This tracker cannot be refreshed from CI, so it is being closed rather than left
open and wrong.

The ageing half of `secret-staleness-check` reads the GitHub Actions secret
listings, and those endpoints need a token with the `repo` scope. A workflow's
`GITHUB_TOKEN` is a GitHub App installation token and GitHub's `permissions:`
vocabulary has no key for secrets, so no grant in a workflow file can supply it.
Every level comes back `403 Resource not accessible by integration`.

Leaving this open would be the worst of both: a `security:finding` that claims to
be watching a rotation window it cannot see. The environment-gate half of the same
job needs only `contents: read` and does work — it compares
`.github/environments.json` against live protection rules on every run.

The real rotation state is recorded by hand in `docs/ops/SECRETS_INVENTORY.md`.
As of 2026-10-04, 16 of 33 secret names were past the 90-day window; the oldest
were `CURSOR_API_KEY` and `FRED_API_KEY` at 165 days.

Give the ageing half a credential and the next run files a fresh tracker with real
names in it."""


def _in_ci() -> bool:
    """Whether this process is a GitHub Actions job.

    Read from the environment rather than inferred from whether the listings worked.
    That inference is what option D invalidated: it used to be true that only CI ran
    this and could read nothing, and now the reverse holds — CI runs `--gates-only`
    and the only caller that ages anything is a person. `GITHUB_ACTIONS` is set to
    the literal string `"true"` by the runner, so this is a presence test on a name
    the workflow platform guarantees, not a heuristic about the host.
    """
    return bool(os.environ.get("GITHUB_ACTIONS"))


def close_unmeasurable_tracker(root: Path, repo: str) -> str:
    """Close an open tracker when nothing could be aged, recording why.

    Skipping the write was not enough on its own. The tracker opened by run
    37235973852 was already open and empty when this was written, carrying
    `security:finding` and a body saying nothing had been read. A guard that only
    prevents *new* empty trackers leaves that one sitting forever, and the docs
    claim the clock files no tracker while a tracker is open. Silence here is
    indistinguishable from "still running".

    The comment lands before the close, so the reason is on the record before the
    issue stops counting as an open finding. If the comment cannot be written the
    issue is left open, because closing it without the explanation would be worse.
    """
    try:
        existing = _issue_exists(root, repo)
    except TrackerUnreadable as exc:
        return f"filed nothing: {exc}"
    if existing is None:
        return "filed nothing: no tracker is open"
    noted = _gh_json(
        [
            "gh",
            "api",
            "--method",
            "POST",
            f"repos/{repo}/issues/{existing}/comments",
            "--input",
            "-",
        ],
        root,
        stdin=json.dumps({"body": CLOSE_NOTE}),
    )
    if noted is None:
        return f"FAILED to record why on #{existing}; left open (see stderr)"
    closed = _gh_json(
        [
            "gh",
            "api",
            "--method",
            "PATCH",
            f"repos/{repo}/issues/{existing}",
            "--input",
            "-",
        ],
        root,
        stdin=json.dumps({"state": "closed"}),
    )
    if closed is None:
        return f"recorded why on #{existing} but FAILED to close it (see stderr)"
    return f"recorded why on #{existing} and closed it"


def file_or_update_issue(root: Path, repo: str, body: str) -> str:
    """Open the tracker, or update the one already open. Never files a duplicate.

    Every outcome is reported from what actually happened. The create used to claim
    "opened a new tracking issue" whether or not the POST landed — it 422'd on
    `labels` being a string — so the tracker did not exist for the whole time the job
    was reporting green.
    """
    try:
        existing = _issue_exists(root, repo)
    except TrackerUnreadable as exc:
        return f"filed nothing: {exc}"
    if existing is None:
        written = _gh_json(
            [
                "gh",
                "api",
                "--method",
                "POST",
                f"repos/{repo}/issues",
                "--input",
                "-",
            ],
            root,
            stdin=json.dumps({"title": ISSUE_TITLE, "body": body, "labels": list(ISSUE_LABELS)}),
        )
        if written is None:
            return "FAILED to open the tracking issue (see stderr)"
        return "opened a new tracking issue"
    written = _gh_json(
        [
            "gh",
            "api",
            "--method",
            "PATCH",
            f"repos/{repo}/issues/{existing}",
            "--input",
            "-",
        ],
        root,
        stdin=json.dumps({"body": body}),
    )
    if written is None:
        return f"FAILED to update the open tracking issue #{existing} (see stderr)"
    return f"updated the open tracking issue #{existing}"


def repo_slug(root: Path) -> tuple[str, str] | None:
    """`(owner, repo)` from `gh repo view`, or None with a reason."""
    payload = _gh_json(["gh", "repo", "view", "--json", "owner,name"], root)
    if not isinstance(payload, dict):
        return None
    owner = payload.get("owner")
    name = payload.get("name")
    if not isinstance(owner, dict) or not isinstance(owner.get("login"), str):
        return None
    if not isinstance(name, str):
        return None
    return owner["login"], name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=DEFAULT_MAX_AGE_DAYS,
        help=f"rotation window in days (default {DEFAULT_MAX_AGE_DAYS})",
    )
    parser.add_argument(
        "--environment",
        default="cron",
        help="environment whose secrets are aged (default cron)",
    )
    parser.add_argument(
        "--file-names",
        type=Path,
        help="offline input: SCOPE<TAB>NAME<TAB>UPDATED lines, no `gh` call",
    )
    parser.add_argument(
        "--open-issue",
        action="store_true",
        help="open or update the tracking issue",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        help="also write the markdown report here (for a step summary)",
    )
    parser.add_argument(
        "--fail-overdue",
        action="store_true",
        help="exit 1 when any name is overdue (not used by CI)",
    )
    parser.add_argument(
        "--strict-offline",
        action="store_true",
        help="exit 1 when a level could not be read",
    )
    parser.add_argument(
        "--skip-environment-gates",
        action="store_true",
        help="do not compare `.github/environments.json` to the live protection rules",
    )
    parser.add_argument(
        "--gates-only",
        action="store_true",
        help=(
            "only run the environment-gate drift check; never read the secret listings "
            "and never touch a tracker (DIG-477 option D, what CI runs)"
        ),
    )
    parser.add_argument(
        "--close-unmeasurable-tracker",
        action="store_true",
        help=(
            "retire an open tracker deliberately when this run read nothing. Without "
            "it, only a CI run closes one: CLOSE_NOTE blames CI, so closing it from an "
            "operator shell records a false cause and discards real names. Ignored when "
            "the listings were read, since the tracker is then refreshed normally."
        ),
    )
    args = parser.parse_args(argv)

    root = REPO_ROOT
    gates: tuple[list[dict[str, object]], dict[str, str]] | None = None
    read_from_file = bool(args.file_names)
    if args.gates_only:
        if args.file_names:
            parser.error("--gates-only and --file-names are mutually exclusive")
        # An empty report with `readable` left at 0, which now means "not attempted"
        # rather than "attempted and found nothing" — the distinction `readable`
        # exists to carry. `collect()` is skipped entirely rather than called and
        # allowed to fail, so a gates-only run spends no doomed API calls.
        report = Report()
        slug = repo_slug(root)
        if slug is None:
            print("secret_staleness_check: cannot resolve the repository", file=sys.stderr)
            return 2
        if not args.skip_environment_gates:
            gates = environment_gate_status(root, f"{slug[0]}/{slug[1]}")
    elif args.file_names:
        try:
            report = Report(secrets=parse_tsv(args.file_names.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            print(f"secret_staleness_check: {exc}", file=sys.stderr)
            return 2
        # `readable` stays 0: the file is a hand-made list, not a served listing, and
        # reporting its contents as "every level was readable" would claim an API read
        # that never happened.
    else:
        slug = repo_slug(root)
        if slug is None:
            print("secret_staleness_check: cannot resolve the repository", file=sys.stderr)
            return 2
        owner, name = slug
        report = collect(root, f"{owner}/{name}", owner, args.environment)
        if not args.skip_environment_gates:
            gates = environment_gate_status(root, f"{owner}/{name}")

    body = markdown(report, args.max_age_days, gates, gates_only=args.gates_only)
    print(render(report, args.max_age_days, gates, gates_only=args.gates_only))

    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(body, encoding="utf-8")

    # Gated on `not args.gates_only` as well as on `--open-issue`: a gates-only run has
    # no ageing result to publish, and the tracker it would open could only ever say
    # "I read nothing". DIG-477 option D is precisely to stop opening that.
    if args.open_issue and not args.file_names and not args.gates_only:
        slug = repo_slug(root)
        if slug is None:
            print("secret_staleness_check: cannot resolve the repository", file=sys.stderr)
            return 2
        if not report.read_any:
            # Keyed on `read_any`, not `secrets`: a run where the listings were served and
            # came back empty did measure something, and closing its tracker on the note
            # below — which asserts every level 403'd — would put a false claim on the
            # permanent record next to a stdout that says the opposite.
            #
            # Closing is refused unless this run is *in CI*, because CLOSE_NOTE asserts a
            # CI cause and CI is the only context in which that assertion is true. Before
            # option D this was safe by accident: the one caller that could not read
            # anything was the CI job, so "read nothing" implied "run from CI". Option D
            # inverted that. CI now runs `--gates-only` and never reaches this branch at
            # all, which leaves `make secrets-staleness` — a person on the Mac — as the
            # only caller, and a person whose token has lost `repo` scope reads nothing
            # for a reason that has nothing to do with CI.
            #
            # That combination was destructive, and reachable: this repo is public, so
            # `repo_slug()` still resolves it without `repo`, and the run proceeds to
            # close a tracker carrying real names while printing a note saying CI did it.
            # Exit 0 makes it worse — DIG-668's monthly run would report success having
            # deleted the record it exists to refresh. The repo is public so this needs
            # no credential to exploit; the read simply needs a token without `repo`.
            #
            # So an operator run that read nothing reports why and exits non-zero,
            # leaving the tracker and its last real contents standing. An operator who
            # means to retire a stale tracker says so explicitly, and then the close
            # happens whatever the context — the flag is the consent, not the setting.
            if not _in_ci() and not args.close_unmeasurable_tracker:
                print(
                    "secret_staleness_check: nothing could be aged, so no tracker was "
                    "opened, updated or closed. Leaving any open tracker as it is: this "
                    "was a run from an operator shell, so the CI explanation in "
                    "CLOSE_NOTE would be false, and a tracker holding real names must not "
                    "be closed by a run that could not read them. Check that `gh auth` "
                    "still carries `repo` and `admin:org` (see `gh auth status`), then "
                    "re-run. To retire a stale tracker deliberately, pass "
                    "--close-unmeasurable-tracker.",
                    file=sys.stderr,
                )
                return 2
            # Every level being unreadable is the normal case from CI, where the
            # listings need a token the job cannot have — see SCOPE_NEEDS_TOKEN_SCOPE.
            # So a run that aged nothing opens nothing, and clears up any tracker an
            # earlier run already left open.
            print(close_unmeasurable_tracker(root, f"{slug[0]}/{slug[1]}"))
        else:
            if args.close_unmeasurable_tracker:
                print(
                    "secret_staleness_check: --close-unmeasurable-tracker was passed but "
                    "this run read the listings, so the tracker is refreshed, not closed",
                    file=sys.stderr,
                )
            print(file_or_update_issue(root, f"{slug[0]}/{slug[1]}", body))

    if gates is not None and any(row["drift"] for row in gates[0]):
        # Deliberately unconditional, unlike `--fail-overdue`. A drifted gate does not
        # fail a build, it silently stops every pipeline gated on it.
        return 1
    if args.fail_overdue and report.overdue(args.max_age_days):
        return 1
    if args.strict_offline and report.unavailable:
        return 1
    if args.strict_offline and read_from_file:
        # The module docstring promises this refuses to report success when the input
        # came from a file, and the previous check (`report.unavailable`) could never
        # fire on that path because the offline report has no unread levels. A file
        # read is not evidence about the live API, so it fails here too.
        print(
            "secret_staleness_check: --strict-offline with --file-names cannot verify "
            "the live API; refusing to report success",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
