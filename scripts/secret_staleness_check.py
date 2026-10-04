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
        return sorted(
            hits, key=lambda s: (SCOPE_ORDER.get(s.scope, 99), -s.age_days, s.name)
        )

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
            raise ValueError(
                f"line {number}: expected 3 tab-separated fields, got {len(fields)}"
            )
        scope, name, updated = (f.strip() for f in fields)
        if scope not in SCOPES:
            raise ValueError(
                f"line {number}: unknown scope {scope!r}, expected one of {SCOPES}"
            )
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
    payload = _gh_json(
        ["gh", "api", "--paginate", f"repos/{repo}/actions/secrets"], root
    )
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
    payload = _gh_json(
        ["gh", "api", "--paginate", f"orgs/{org}/actions/secrets"], root
    )
    entries = _secret_entries(payload)
    if entries is None:
        return [], f"org secret list unavailable (needs {ORG_SCOPE_REQUIRES_ADMIN})"
    return [
        Secret("org", e["name"], parse_timestamp(e["updated_at"]))
        for e in entries
        if isinstance(e.get("name"), str) and isinstance(e.get("updated_at"), str)
    ], None


def environment_secrets(
    root: Path, repo: str, environment: str
) -> tuple[list[Secret], str | None]:
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


def collect(
    root: Path, repo: str, org: str, environment: str = "cron"
) -> Report:
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


def markdown(report: Report, max_age_days: int) -> str:
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
        lines += [
            f"- `{scope}` — {reason}" for scope, reason in sorted(report.unavailable.items())
        ]
    return "\n".join(lines) + "\n"


def ordered_scopes(report: Report) -> list[str]:
    """Every level the report actually holds, widest blast radius first.

    A level that read successfully but holds nothing still prints, as `0 name(s)`:
    for the `cron` environment that is the signal the migration has not landed yet,
    and silence would read as "nothing to see".
    """
    present = {secret.scope for secret in report.secrets}
    return sorted(present, key=lambda scope: (SCOPE_ORDER.get(scope, 99), scope))


def render(report: Report, max_age_days: int) -> str:
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
            f"[.[] | select(.state == \"open\") | select(.title == \"{ISSUE_TITLE}\")] | .[0].number",
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
    payload = _gh_json(
        ["gh", "repo", "view", "--json", "owner,name"], root
    )
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
    args = parser.parse_args(argv)

    root = REPO_ROOT
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

    body = markdown(report, args.max_age_days)
    print(render(report, args.max_age_days))

    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(body, encoding="utf-8")

    if args.open_issue and not args.file_names:
        slug = repo_slug(root)
        if slug is None:
            print("secret_staleness_check: cannot resolve the repository", file=sys.stderr)
            return 2
        print(file_or_update_issue(root, f"{slug[0]}/{slug[1]}", body))

    if args.fail_overdue and report.overdue(args.max_age_days):
        return 1
    if args.strict_offline and report.unavailable:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())