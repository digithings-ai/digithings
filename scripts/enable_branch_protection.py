#!/usr/bin/env python3
"""Report or apply branch protection, with a plan preflight that fails loudly.

Branch protection and repository rulesets are a paid feature for *private*
repositories: available on public repos at any plan, private repos only from
GitHub Pro up. Merge queue is configured through a ruleset, so it inherits the
same gate. On a Free org the API refuses with HTTP 403 and a message that reads
like a permissions problem but is not:

    Upgrade to GitHub Pro or make this repository public to enable this feature.

That is why this script exists as more than a ``gh api`` one-liner. The raw 403
spends an afternoon of guessing at token scopes and org settings, and the
diagnosis is one request away. ``status`` and ``apply`` both preflight, print
*why* a repo cannot be protected when it cannot, and only then make the call.

This script never guesses a required check name. A required check that does not
report on some PR shape blocks those PRs forever — the failure mode
``docs/BRANCH_PROTECTION.md`` documents for ``gitleaks-scan`` — so the caller
names the checks and is responsible for having seen them report. See that doc
before adding one.

Usage::

    python3 scripts/enable_branch_protection.py status --repo digithings-ai/twelve-x --branch develop
    python3 scripts/enable_branch_protection.py apply  --repo digithings-ai/digithings --branch develop \\
        --check 'Required checks passed' --check 'doc-links + agents-init' --mode classic --dry-run
    python3 scripts/enable_branch_protection.py apply  --repo digithings-ai/twelve-x --branch develop \\
        --check test --require-approvals 1 --mode ruleset --merge-queue
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

# GitHub's plan names as they arrive from `GET /orgs/{org}`. `free for
# organizations` is the legacy value; current Free orgs report `free`.
FREE_PLANS: frozenset[str] = frozenset({"free", "free for organizations"})

PRO_REQUIRED_MARKERS: tuple[str, ...] = ("upgrade to github pro", "make this repository public")

EXIT_OK = 0
EXIT_OPERATIONAL = 1
EXIT_PLAN_BLOCKED = 3
EXIT_PERMISSION_BLOCKED = 4

PRO_UNBLOCK_ADVICE = (
    "Unblocking this is a billing decision, not a config change:\n"
    "  1. Upgrade the owning org to GitHub Pro. This is the supported route and it\n"
    "     also unblocks the server-side merge queue for every private repo in the org.\n"
    "  2. Making the repository public unblocks protection on the Free plan, but it\n"
    "     publishes the code and the history — never a client repo's decision to take\n"
    "     here, and never an agent's.\n"
    "Until one of those happens, use scripts/merge_queue.py: it applies the same gates\n"
    "on the merge path, under a named merge-authority role, but it cannot stop a\n"
    "direct push to the branch."
)


class ProtectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Preflight:
    """What the API is willing to let this token do to this repo, and why."""

    repo: str
    is_private: bool
    plan: str
    has_admin: bool
    blocked_reason: str | None

    @property
    def can_apply(self) -> bool:
        return self.blocked_reason is None


def _gh_json(*args: str, method: str = "GET") -> Any:
    cmd = ["gh", "api", *args]
    if method != "GET":
        cmd = [method, *cmd]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise ProtectionError(f"gh api {' '.join(args)} failed: {proc.stderr.strip()}")
    try:
        return json.loads(proc.stdout or "null")
    except json.JSONDecodeError as exc:
        raise ProtectionError(f"gh api {' '.join(args)} returned non-JSON") from exc


def _gh_api_status(*args: str, method: str = "GET", payload: dict[str, Any] | None = None) -> str:
    """Like _gh_json, but returns the error body instead of raising on 4xx."""
    cmd = ["gh", "api"]
    if method != "GET":
        cmd.append(method)
    cmd.extend(args)
    if payload is not None:
        cmd.extend(["--input", "-"])
    proc = subprocess.run(
        cmd,
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return ""
    return (proc.stderr or proc.stdout).strip()


def preflight(repo: str) -> Preflight:
    """Ask the API what is possible before promising anything.

    Plan is read from the owning org and treated as advisory when unreadable (a
    token without `admin:org` gets a 403 here). An unknown plan is not treated as
    Free: guessing wrong in the safe direction would refuse a repo that could have
    been protected. The apply call is what settles it.
    """
    if repo.count("/") != 1 or repo.startswith("/") or repo.endswith("/"):
        raise ProtectionError(f"--repo must be owner/name, got {repo!r}")
    owner = repo.split("/", 1)[0]

    meta = _gh_json(f"repos/{repo}")
    if not isinstance(meta, dict):
        raise ProtectionError(f"could not read repo metadata for {repo}")
    is_private = bool(meta.get("private"))
    permissions = meta.get("permissions") or {}
    has_admin = bool(permissions.get("admin"))

    plan = "unknown"
    try:
        org = _gh_json(f"orgs/{owner}")
        if isinstance(org, dict) and org.get("plan"):
            # `plan` comes back as an object (`{"name": "free", "seats": 0, …}`) from
            # the REST endpoint, and as a bare string from some org endpoints. Reading
            # it as a string would compare a dict against FREE_PLANS, never match, and
            # report every private repo as unprotected-by-plan when it is not.
            raw_plan = org["plan"]
            plan = str(raw_plan.get("name") or "") if isinstance(raw_plan, dict) else str(raw_plan)
            if not plan:
                plan = "unknown"
    except ProtectionError:
        pass

    blocked: str | None = None
    if not has_admin:
        blocked = (
            "the authenticated user is not an admin on this repo, so branch protection "
            "cannot be applied at all"
        )
    elif is_private and plan.lower() in FREE_PLANS:
        blocked = (
            f"{repo} is private and org '{owner}' is on the '{plan}' plan; branch "
            "protection, rulesets and the server-side merge queue all require GitHub Pro "
            "for private repositories"
        )

    return Preflight(
        repo=repo, is_private=is_private, plan=plan, has_admin=has_admin, blocked_reason=blocked
    )


def print_preflight(pf: Preflight) -> None:
    print(f"repo:        {pf.repo}")
    print(f"visibility:  {'private' if pf.is_private else 'public'}")
    print(f"org plan:    {pf.plan}")
    print(f"admin:       {'yes' if pf.has_admin else 'no'}")
    if pf.blocked_reason:
        print(f"\nBLOCKED: {pf.blocked_reason}")
        print(f"\n{PRO_UNBLOCK_ADVICE}")


def classic_payload(checks: list[str], approvals: int, *, strict: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "required_status_checks": {"strict": strict, "contexts": checks},
        # false on purpose, matching docs/BRANCH_PROTECTION.md: an admin can bypass
        # in a genuine emergency rather than being locked out of a hotfix.
        "enforce_admins": False,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "required_linear_history": False,
        "allow_fork_syncing": True,
    }
    if approvals > 0:
        payload["required_pull_request_reviews"] = {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": False,
            "required_approving_review_count": approvals,
        }
    return payload


def ruleset_payload(
    name: str,
    branch: str,
    checks: list[str],
    approvals: int,
    *,
    strict: bool,
    merge_queue: bool,
    merge_method: str,
    enforcement: str,
) -> dict[str, Any]:
    """A ruleset is the only way to get a server-side merge queue.

    `non_fast_forward` blocks force-pushes and `deletion` blocks branch deletion,
    the two rules the CEO's done-test calls out; classic branch protection carries
    the same guarantees as booleans, a ruleset carries them as rules, so the
    evidence a reviewer reads back is the same either way.
    """
    rules: list[dict[str, Any]] = [
        {"type": "non_fast_forward"},
        {"type": "deletion"},
    ]
    if checks:
        rules.append(
            {
                "type": "required_status_checks",
                "parameters": {
                    "required_status_checks": [{"context": c} for c in checks],
                    "strict_required_status_checks_policy": strict,
                    # A branch is created before its first CI run reports, so without
                    # this the ruleset blocks creation of every new protected branch.
                    "do_not_enforce_on_create": True,
                },
            }
        )
    if approvals > 0:
        rules.append(
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": approvals,
                    "dismiss_stale_reviews_on_push": True,
                    "require_code_owner_review": False,
                    "require_last_push_approval": True,
                    "required_review_thread_resolution": True,
                },
            }
        )
    if merge_queue:
        rules.append(
            {
                "type": "merge_queue",
                "parameters": {
                    "check_response_timeout_minutes": 60,
                    # ALLGREEN: every PR in the group must be green, not only the head
                    # of the group. HEADGREEN lets a green last commit carry a red
                    # earlier PR, which is the failure this queue exists to prevent.
                    "grouping_strategy": "ALLGREEN",
                    "max_entries_to_build": 5,
                    "max_entries_to_merge": 1,
                    "merge_method": merge_method.upper(),
                    "min_entries_to_merge": 1,
                    "min_entries_to_merge_wait_minutes": 5,
                },
            }
        )
    return {
        "name": name,
        "target": "branch",
        "enforcement": enforcement,
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": [f"refs/heads/{branch}"]}},
        "rules": rules,
    }


def _enabled(body: dict[str, Any], key: str) -> bool:
    """Read a protection toggle that the API returns as `{"enabled": bool}`.

    `allow_force_pushes`, `allow_deletions` and `enforce_admins` all come back as
    wrapper objects, not bare booleans. Reading them with a plain truth test reports
    `{"enabled": false}` as *allowed* — the exact opposite of what the repo is
    doing — so every "did we block force-pushs?" claim has to go through here.
    """
    value = body.get(key)
    if isinstance(value, dict):
        return bool(value.get("enabled"))
    return bool(value)


def cmd_status(args: argparse.Namespace) -> int:
    try:
        pf = preflight(args.repo)
    except ProtectionError as exc:
        print(f"enable_branch_protection: {exc}", file=sys.stderr)
        return EXIT_OPERATIONAL

    print_preflight(pf)
    print()
    protection_err = _gh_api_status(f"repos/{args.repo}/branches/{args.branch}/protection")
    if protection_err:
        print(f"protection on {args.branch}: NOT READABLE — {protection_err.splitlines()[0]}")
    else:
        body = _gh_json(f"repos/{args.repo}/branches/{args.branch}/protection") or {}
        status = body.get("required_status_checks") or {}
        reviews = body.get("required_pull_request_reviews") or {}
        print(f"protection on {args.branch}: active")
        print(
            f"  required checks:   {status.get('contexts') or 'none'} (strict={status.get('strict')})"
        )
        print(f"  approving reviews: {reviews.get('required_approving_review_count', 0)}")
        print(f"  enforce admins:    {'yes' if _enabled(body, 'enforce_admins') else 'no'}")
        print(
            f"  force pushes:      {'allowed' if _enabled(body, 'allow_force_pushes') else 'blocked'}"
        )
        print(
            f"  branch deletion:   {'allowed' if _enabled(body, 'allow_deletions') else 'blocked'}"
        )

    rulesets = _gh_api_status(f"repos/{args.repo}/rulesets")
    if rulesets:
        print(f"rulesets: NOT READABLE — {rulesets.splitlines()[0]}")
    else:
        listed = _gh_json(f"repos/{args.repo}/rulesets") or []
        # Guard the shape rather than trusting it: iterating a dict would yield its
        # keys and crash on the first string, and an unreadable response should read
        # as "state unknown" instead of a traceback.
        if not isinstance(listed, list):
            listed = []
        if not listed:
            print("rulesets: none")
        for r in listed:
            if isinstance(r, dict):
                print(f"ruleset: {r.get('name')} ({r.get('target')}, {r.get('enforcement')})")

    if pf.can_apply and not protection_err:
        checks = (body.get("required_status_checks") or {}).get("contexts") or []
        if not checks:
            print(
                f"\nnote: {args.branch} is protected but requires no status check. A branch "
                "with no required check enforces nothing; name the checks its CI reports."
            )
    return EXIT_OK


def cmd_apply(args: argparse.Namespace) -> int:
    try:
        pf = preflight(args.repo)
    except ProtectionError as exc:
        print(f"enable_branch_protection: {exc}", file=sys.stderr)
        return EXIT_OPERATIONAL

    print_preflight(pf)
    if not pf.can_apply:
        return EXIT_PLAN_BLOCKED if pf.has_admin else EXIT_PERMISSION_BLOCKED

    steps: list[tuple[str, str, dict[str, Any]]] = []
    if args.mode in ("classic", "both"):
        steps.append(
            (
                "classic",
                f"repos/{args.repo}/branches/{args.branch}/protection",
                classic_payload(args.check, args.require_approvals, strict=args.strict),
            )
        )
    if args.mode in ("ruleset", "both"):
        steps.append(
            (
                "ruleset",
                f"repos/{args.repo}/rulesets",
                ruleset_payload(
                    args.ruleset,
                    args.branch,
                    args.check,
                    args.require_approvals,
                    strict=args.strict,
                    merge_queue=args.merge_queue,
                    merge_method=args.merge_method,
                    enforcement="active",
                ),
            )
        )

    if args.dry_run:
        for kind, endpoint, payload in steps:
            print(f"\nwould PUT {endpoint} ({kind}):")
            print(json.dumps(payload, indent=2, sort_keys=True))
        print("\ndry run — nothing was changed.")
        return EXIT_OK

    failures = 0
    for kind, endpoint, payload in steps:
        print(f"\napplying {kind} to {args.repo}:{args.branch}")
        err = _gh_api_status(endpoint, method="PUT", payload=payload)
        if err:
            failures += 1
            if any(m in err.lower() for m in PRO_REQUIRED_MARKERS):
                print(f"  REFUSED — {err}")
                print(f"\n{PRO_UNBLOCK_ADVICE}")
                return EXIT_PLAN_BLOCKED
            print(f"  FAILED — {err}", file=sys.stderr)
        else:
            print("  applied")
    if failures:
        print(
            f"\n{failures} of {len(steps)} change(s) did not apply. Verify with "
            f"`status --repo {args.repo} --branch {args.branch}` before trusting the state.",
            file=sys.stderr,
        )
        return EXIT_OPERATIONAL
    print(f"\napplied. Verify with `status --repo {args.repo} --branch {args.branch}`.")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["status", "apply"])
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--branch", required=True, help="branch to protect")
    parser.add_argument(
        "--check",
        action="append",
        default=[],
        help="required check context; repeatable. Must be a name this branch's CI reports.",
    )
    parser.add_argument(
        "--require-approvals", type=int, default=0, help="approving reviews required (0 = none)"
    )
    parser.add_argument(
        "--mode",
        choices=["classic", "ruleset", "both"],
        default="ruleset",
        help="ruleset (default) is the only mode that can carry a merge queue",
    )
    parser.add_argument("--ruleset", default="develop-merge-queue", help="ruleset name")
    parser.add_argument(
        "--merge-queue", action="store_true", help="require merges via the merge queue (ruleset)"
    )
    parser.add_argument("--merge-method", choices=["merge", "squash", "rebase"], default="squash")
    parser.add_argument(
        "--strict",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="require the branch to be up to date with its base before merging",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the payload; change nothing")
    args = parser.parse_args(argv)

    if args.require_approvals < 0:
        print("enable_branch_protection: --require-approvals must be >= 0", file=sys.stderr)
        return EXIT_OPERATIONAL
    if args.merge_queue and args.mode == "classic":
        print(
            "enable_branch_protection: --merge-queue needs --mode ruleset; classic branch "
            "protection has no merge-queue field.",
            file=sys.stderr,
        )
        return EXIT_OPERATIONAL
    # Local argument checks come before the preflight. A malformed invocation should
    # not spend an API round trip to find out, and on a plan-blocked repo it would
    # otherwise be masked by the plan refusal — the operator fixes the plan, runs
    # again, and only then learns their `--check` was missing.
    if args.command == "apply" and not args.check:
        print(
            "enable_branch_protection: refusing to apply with no --check. A branch with no "
            "required check looks protected and enforces nothing; name the checks this "
            "branch's CI reports.",
            file=sys.stderr,
        )
        return EXIT_OPERATIONAL

    try:
        return cmd_status(args) if args.command == "status" else cmd_apply(args)
    except ProtectionError as exc:
        print(f"enable_branch_protection: {exc}", file=sys.stderr)
        return EXIT_OPERATIONAL


if __name__ == "__main__":
    raise SystemExit(main())
