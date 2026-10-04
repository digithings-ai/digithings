#!/usr/bin/env python3
"""Names-only ageing check for GitHub Actions secrets (#248).

`gh secret list` and `gh api .../actions/secrets` return a name and a
last-written date and never a value, so this whole check runs without reading a
single credential. That is the point: the 90-day rotation rule in
`docs/ops/SECRETS_INVENTORY.md` was a memory exercise, and this turns it into a
control that fires on its own.

    python3 scripts/secret_staleness_check.py                     # report, no issue
    python3 scripts/secret_staleness_check.py --file-names a.txt   # offline, no `gh`
    python3 scripts/secret_staleness_check.py --open-issue         # file the tracker
    python3 scripts/secret_staleness_check.py --max-age-days 60

Three levels are aged, because each has its own rotation blast radius:

    repo       a secret any workflow on any branch could read
    org        inherited by every repo in the org (`gh` needs `admin:org`)
    cron       the environment scope the CI reads moved to in #248

Not a hard gate. `--fail-overdue` exits 1 when anything is overdue, which CI
does *not* use: a stale credential is a decision for a human (rotate now, or
record why not), and a red build is not that decision. The monthly workflow
files or updates one tracking issue instead.

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

SCOPES = ("repo", "org", "cron")

ISSUE_TITLE = "Ops: GitHub secrets past the 90-day rotation window"
ISSUE_MARKER = "<!-- secret-staleness-check -->"

#: Order in which an overdue name is reported: widest blast radius first, so a
#: truncated issue body still leads with the worst of it. An org secret is
#: inherited by every repo in the org; a repo secret is readable by any workflow on
#: any branch of this repo; an environment secret is reachable only by jobs that
#: declare that environment, which after #248 is the CI read set.
SCOPE_ORDER = {"org": 0, "repo": 1, "cron": 2}


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
    """The ageing result, plus whatever could not be checked."""

    secrets: list[Secret] = field(default_factory=list)
    unavailable: dict[str, str] = field(default_factory=dict)

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


def _gh_json(cmd: list[str], root: Path) -> object | None:
    """Parsed `gh` JSON, or None with a one-line reason on stderr."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=root)
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


def _secret_entries(payload: object) -> list[dict] | None:
    """The `.secrets` list of a paginated listing, or None when it is not that shape."""
    if not isinstance(payload, dict) or not isinstance(payload.get("secrets"), list):
        return None
    return [e for e in payload["secrets"] if isinstance(e, dict)]


def repo_secrets(root: Path, repo: str) -> tuple[list[Secret], str | None]:
    """Repo-scope secrets with their last-written dates."""
    payload = _gh_json(["gh", "api", "--paginate", f"repos/{repo}/actions/secrets"], root)
    entries = _secret_entries(payload)
    if entries is None:
        return [], f"repo secret list unavailable for {repo}"
    return [
        Secret("repo", e["name"], parse_timestamp(e["updated_at"]))
        for e in entries
        if isinstance(e.get("name"), str) and isinstance(e.get("updated_at"), str)
    ], None


def org_secrets(root: Path, org: str) -> tuple[list[Secret], str | None]:
    """Org-scope secrets. Needs `admin:org`; a GITHUB_TOKEN will fail here."""
    payload = _gh_json(["gh", "api", "--paginate", f"orgs/{org}/actions/secrets"], root)
    entries = _secret_entries(payload)
    if entries is None:
        return [], f"org secret list unavailable (needs {ORG_SCOPE_REQUIRES_ADMIN})"
    return [
        Secret("org", e["name"], parse_timestamp(e["updated_at"]))
        for e in entries
        if isinstance(e.get("name"), str) and isinstance(e.get("updated_at"), str)
    ], None


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
        return [], f"environment {environment!r} secret list unavailable"
    return [
        Secret(environment, e["name"], parse_timestamp(e["updated_at"]))
        for e in entries
        if isinstance(e.get("name"), str) and isinstance(e.get("updated_at"), str)
    ], None


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


def markdown(
    report: Report,
    max_age_days: int,
    gates: tuple[list[dict[str, object]], dict[str, str]] | None = None,
) -> str:
    """The issue body. Names and ages only — no value ever reaches this string."""
    overdue = report.overdue(max_age_days)
    lines = [
        ISSUE_MARKER,
        "",
        "Opened automatically by `scripts/secret_staleness_check.py` (#248).",
        "Names and last-written dates only: GitHub never returns a secret value here.",
        "",
        f"**{len(overdue)}** of **{len(report.secrets)}** listed secrets are past",
        f"**{max_age_days} days** since last written.",
        "",
    ]
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
    else:
        lines.append(f"Nothing is past {max_age_days} days. No action needed.")
    if report.unavailable:
        lines += ["", "## Levels not checked", ""]
        lines += [f"- `{scope}` — {reason}" for scope, reason in sorted(report.unavailable.items())]
    lines += gate_markdown(gates)
    return "\n".join(lines) + "\n"


def ordered_scopes(report: Report) -> list[str]:
    """Every level the report actually holds, widest blast radius first.

    A level that read successfully but holds nothing still prints, as `0 name(s)`:
    for the `cron` environment that is the signal the migration has not landed yet,
    and silence would read as "nothing to see".
    """
    present = {secret.scope for secret in report.secrets}
    return sorted(present, key=lambda scope: (SCOPE_ORDER.get(scope, 99), scope))


def render(
    report: Report,
    max_age_days: int,
    gates: tuple[list[dict[str, object]], dict[str, str]] | None = None,
) -> str:
    """Human-readable stdout, grouped by scope and oldest first."""
    grouped = report.by_scope()
    out: list[str] = []
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
    overdue = report.overdue(max_age_days)
    out.append("")
    out.append(f"{len(overdue)} name(s) past {max_age_days} days of {len(report.secrets)} listed.")
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


def _issue_exists(root: Path, repo: str) -> str | None:
    """The number of the open tracker issue, if one is already open."""
    payload = _gh_json(
        [
            "gh",
            "api",
            "--paginate",
            f"repos/{repo}/issues",
            "--jq",
            f'[.[] | select(.state == "open") | select(.title == "{ISSUE_TITLE}")] | .[0].number',
        ],
        root,
    )
    if isinstance(payload, list) and payload and isinstance(payload[0], int):
        return str(payload[0])
    if isinstance(payload, int):
        return str(payload)
    return None


def file_or_update_issue(root: Path, repo: str, body: str) -> str:
    """Open the tracker, or update the one already open. Never files a duplicate."""
    existing = _issue_exists(root, repo)
    if existing is None:
        _gh_json(
            [
                "gh",
                "api",
                "--method",
                "POST",
                f"repos/{repo}/issues",
                "-f",
                f"title={ISSUE_TITLE}",
                "-f",
                f"body={body}",
                "-f",
                "labels=ops",
            ],
            root,
        )
        return "opened a new tracking issue"
    _gh_json(
        [
            "gh",
            "api",
            "--method",
            "PATCH",
            f"repos/{repo}/issues/{existing}",
            "-f",
            f"body={body}",
        ],
        root,
    )
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
    args = parser.parse_args(argv)

    root = REPO_ROOT
    gates: tuple[list[dict[str, object]], dict[str, str]] | None = None
    if args.file_names:
        try:
            report = Report(secrets=parse_tsv(args.file_names.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            print(f"secret_staleness_check: {exc}", file=sys.stderr)
            return 2
    else:
        slug = repo_slug(root)
        if slug is None:
            print("secret_staleness_check: cannot resolve the repository", file=sys.stderr)
            return 2
        owner, name = slug
        report = collect(root, f"{owner}/{name}", owner, args.environment)
        if not args.skip_environment_gates:
            gates = environment_gate_status(root, f"{owner}/{name}")

    body = markdown(report, args.max_age_days, gates)
    print(render(report, args.max_age_days, gates))

    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(body, encoding="utf-8")

    if args.open_issue and not args.file_names:
        slug = repo_slug(root)
        if slug is None:
            print("secret_staleness_check: cannot resolve the repository", file=sys.stderr)
            return 2
        print(file_or_update_issue(root, f"{slug[0]}/{slug[1]}", body))

    if gates is not None and any(row["drift"] for row in gates[0]):
        # Deliberately unconditional, unlike `--fail-overdue`. A drifted gate does not
        # fail a build, it silently stops every pipeline gated on it.
        return 1
    if args.fail_overdue and report.overdue(args.max_age_days):
        return 1
    if args.strict_offline and report.unavailable:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
