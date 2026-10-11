#!/usr/bin/env python3
"""Reconcile declared policy checks against develop's merge gate.

The drift guard that lives in ``ci.yml`` ("Verify needs list covers every job
in this file") compares ``required-checks.needs`` against the jobs defined in
``ci.yml``. That is a real staleness check and it stays. It is also pointed at
the wrong inventory: it can only see ``ci.yml``, so it is green today and would
stay green no matter which policy check lives in another workflow file. That is
not a weak guard, it is a guard that cannot fail on the bugs it exists for.

This script is the corrected inventory. It reconciles three sets:

  1. ``.github/policy-checks.yml``  vs  the jobs the workflows actually define
  2. ``.github/policy-checks.yml``  vs  develop's required status-check contexts
  3. ``Required checks passed``     vs  ``required-checks.needs`` (done in ci.yml)

and it fails on exactly the two failure modes where a policy gate and the gate
list disagree:

  * **silent stall** — a required context that no PR-triggered workflow
    guarantees will report. The gate names a check that will never arrive, so
    every PR waits forever. This is what happens if ``gitleaks-scan`` is made
    required while ``security-gitleaks.yml`` still carries its workflow-level
    ``paths-ignore``: docs-only PRs never start the workflow, never report, and
    hang. ``docs/BRANCH_PROTECTION.md`` warns about this in prose; here it is a
    test.
  * **ungated policy check** — a check that reports on PRs and is required
    nowhere. It runs, it goes red, and merges continue. Five of these exist
    right now (DCO sign-off, gitleaks, PR hygiene, PR title, and, on main,
    review coverage); they are declared in the inventory so they are visible in
    one place instead of inferred from 53 workflow files.

WHY A DECLARED INVENTORY AND NOT A NAME PATTERN
DIG-1952 proposed matching job names against a required-check list. Job names
cannot be classified that way — ``score`` is a policy check and ``npm-audit``
might be. A pattern is wrong the first time a lane is named ``policy-something``.
So the policy set is declared in ``.github/policy-checks.yml`` and this script
reads it. The cost is that adding a named job to a tracked workflow is a
one-line inventory edit; that edit is the point, not a tax.

WHY THE CONTEXTS COME FROM A FILE
Reading branch protection needs ``administration: read``, which cannot be
granted to ``GITHUB_TOKEN``, so no workflow can read it. CI therefore checks a
committed snapshot (``.github/required-contexts.txt``) and ``--live`` verifies
that snapshot against the API using the same ``enable_branch_protection.py``
read the human runbook uses. Refusing to guess is the whole discipline here: a
required context that will never report blocks every merge behind it, so an
unknown state must read as a failure, never as green.

Scope: this detects. It does not change branch protection, any ruleset, or any
workflow trigger. Closing the gate is DIG-1952 child B, a human-only
repo-settings write, sequenced behind this on purpose.

Usage::

    python3 scripts/check_required_policy_checks.py
    python3 scripts/check_required_policy_checks.py --live \\
        --repo digithings-ai/digithings --branch develop
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
INVENTORY_PATH = REPO_ROOT / ".github" / "policy-checks.yml"
CONTEXTS_PATH = REPO_ROOT / ".github" / "required-contexts.txt"

#: The ci.yml aggregator's check name. Its ``needs`` reconciliation is the
#: pre-existing in-file check; this script only asserts the name is accounted
#: for, and does not duplicate it.
AGGREGATOR_CONTEXT = "Required checks passed"

ENFORCEMENTS = frozenset({"required", "advisory", "other-branch"})


class GuardError(RuntimeError):
    """Raised when an input cannot be read at all, as opposed to mismatching."""


@dataclass(frozen=True)
class PolicyCheck:
    """One declared policy check."""

    context: str
    workflow: str
    job: str
    enforcement: str
    reason: str

    @property
    def is_required(self) -> bool:
        return self.enforcement == "required"


@dataclass
class WorkflowFacts:
    """What one workflow file actually does on a pull request into develop."""

    path: str
    #: check name -> job id, for jobs that carry an explicit ``name:``.
    named_jobs: dict[str, str] = field(default_factory=dict)
    #: True when ``on.pull_request`` exists at all.
    pr_triggered: bool = False
    #: Workflow-level filters that can stop the workflow starting on some PRs.
    #: A *skipped workflow* reports nothing; a skipped *job* reports Success.
    path_filter: str | None = None
    branch_filter: list[str] | None = None

    def reports_on_develop_pr(self, branch: str) -> tuple[bool, str]:
        """Can this workflow be relied on to report for every PR into ``branch``?"""
        if not self.pr_triggered:
            return False, "the workflow has no `pull_request:` trigger"
        if self.path_filter is not None:
            kind, _paths = self.path_filter
            return False, (
                f"the workflow-level `pull_request:` {kind} filter can skip the whole "
                "workflow, so its checks never report on the PRs it skips — GitHub "
                "then blocks those PRs waiting for a status that will never arrive. "
                "Move the skip to a job-level `if:` (a skipped job reports Success) "
                "or drop the filter"
            )
        if self.branch_filter is not None and branch not in self.branch_filter:
            return False, (
                f"the workflow-level `pull_request:` branches filter "
                f"({self.branch_filter}) does not include `{branch}`, so this check "
                f"never reports on a PR into `{branch}`"
            )
        return True, ""


@dataclass(frozen=True)
class Finding:
    code: str
    subject: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - formatting only
        return f"[{self.code}] {self.subject}: {self.message}"


# ── inputs ──────────────────────────────────────────────────────────────────


def _workflow_on(doc: dict[str, Any]) -> dict[str, Any]:
    """The `on:` block. PyYAML parses a bare `on` key as the boolean True."""
    value = doc.get(True, doc.get("on"))
    return value if isinstance(value, dict) else {}


def read_workflow_facts(path: Path, branch: str) -> WorkflowFacts:
    """Parse one workflow file into the facts the reconciler needs."""
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise GuardError(f"{path.name} is not parseable YAML: {exc}") from exc
    if not isinstance(doc, dict):
        raise GuardError(f"{path.name} did not parse to a mapping")

    facts = WorkflowFacts(path=path.name)

    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        return facts
    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue
        name = job.get("name")
        if isinstance(name, str) and name.strip():
            facts.named_jobs[name] = str(job_id)

    on = _workflow_on(doc)
    # `pull_request:` with no value, and `pull_request: {}`, both mean "every
    # PR". Only an absent key means no trigger at all, so test membership rather
    # than truthiness — ci.yml writes the bare form and ci-docs.yml writes `{}`.
    if "pull_request" not in on:
        return facts
    facts.pr_triggered = True
    pr = on.get("pull_request")
    if isinstance(pr, dict):
        for key, label in (("paths", "paths"), ("paths-ignore", "paths-ignore")):
            if key in pr:
                facts.path_filter = (label, pr[key])
                break
        branches = pr.get("branches")
        if isinstance(branches, list):
            facts.branch_filter = [str(b) for b in branches]
    return facts


def load_inventory(path: Path = INVENTORY_PATH) -> tuple[list[PolicyCheck], list[str]]:
    """Read the declared policy inventory. Raises on a malformed inventory.

    Shape errors are raised rather than reported as findings: a guard that
    silently treats a broken inventory as "no checks declared" would go green
    having checked nothing, which is the exact false-green this issue exists to
    stop.
    """
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise GuardError(f"{path} is not parseable YAML: {exc}") from exc
    if not isinstance(doc, dict):
        raise GuardError(f"{path} did not parse to a mapping")

    tracked = doc.get("tracked_workflows")
    if not isinstance(tracked, list) or not tracked:
        raise GuardError(f"{path}: 'tracked_workflows' must be a non-empty list")

    raw_checks = doc.get("checks")
    if not isinstance(raw_checks, list) or not raw_checks:
        raise GuardError(f"{path}: 'checks' must be a non-empty list")

    checks: list[PolicyCheck] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw_checks):
        where = f"{path}: checks[{index}]"
        if not isinstance(entry, dict):
            raise GuardError(f"{where} is not a mapping")
        missing = [k for k in ("context", "workflow", "job", "enforcement") if not entry.get(k)]
        if missing:
            raise GuardError(f"{where} is missing required key(s): {', '.join(missing)}")
        context = str(entry["context"])
        if context in seen:
            raise GuardError(f"{where}: duplicate context {context!r}")
        seen.add(context)
        enforcement = str(entry["enforcement"])
        if enforcement not in ENFORCEMENTS:
            raise GuardError(
                f"{where}: enforcement {enforcement!r} is not one of "
                f"{', '.join(sorted(ENFORCEMENTS))}"
            )
        reason = str(entry.get("reason") or "").strip()
        if not reason:
            raise GuardError(f"{where} ({context}): every entry needs a 'reason'")
        checks.append(
            PolicyCheck(
                context=context,
                workflow=str(entry["workflow"]),
                job=str(entry["job"]),
                enforcement=enforcement,
                reason=" ".join(reason.split()),
            )
        )
    return checks, [str(name) for name in tracked]


def read_contexts_file(path: Path = CONTEXTS_PATH) -> list[str]:
    """Read develop's required contexts from the committed snapshot."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GuardError(f"{path} is unreadable: {exc}") from exc
    contexts = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not contexts:
        raise GuardError(f"{path} lists no required contexts")
    return contexts


def read_live_contexts(repo: str, branch: str) -> list[str]:
    """Read the required contexts from the live API.

    Deliberately goes through ``enable_branch_protection.py``'s own ``gh api``
    helper rather than a fresh call, so the guard and the human runbook cannot
    drift in how they read the gate.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import enable_branch_protection as bp
    except ImportError as exc:  # pragma: no cover - repo layout breakage
        raise GuardError(f"cannot import scripts/enable_branch_protection.py: {exc}") from exc

    try:
        body = bp._gh_json(f"repos/{repo}/branches/{branch}/protection") or {}
    except bp.ProtectionError as exc:
        raise GuardError(f"reading protection on {repo}@{branch} failed: {exc}") from exc

    status = body.get("required_status_checks") or {}
    contexts = status.get("contexts")
    if not isinstance(contexts, list):
        # A branch with no required_status_checks at all reports no contexts.
        # That is a real finding, not an error — hand back the empty list and
        # let the reconciler name every gate as missing.
        return []
    return [str(c) for c in contexts]


# ── reconciliation ──────────────────────────────────────────────────────────


def reconcile(
    inventory: list[PolicyCheck],
    tracked: list[str],
    facts_by_workflow: dict[str, WorkflowFacts],
    required_contexts: list[str],
    branch: str,
) -> list[Finding]:
    """The three-way reconciliation. Returns every disagreement found."""
    findings: list[Finding] = []
    by_context = {check.context: check for check in inventory}
    live = list(required_contexts)

    def produce(context: str) -> tuple[WorkflowFacts, str] | None:
        for name in tracked:
            facts = facts_by_workflow.get(name)
            if facts and context in facts.named_jobs:
                return facts, facts.named_jobs[context]
        return None

    # ── 1. inventory vs the workflows ─────────────────────────────────────────
    for check in inventory:
        facts = facts_by_workflow.get(check.workflow)
        if facts is None:
            findings.append(
                Finding(
                    "policy.unknown-workflow",
                    check.context,
                    f"names workflow {check.workflow!r}, which is not a readable tracked "
                    "workflow file",
                )
            )
            continue
        job_id = facts.named_jobs.get(check.context)
        if job_id is None:
            actual = sorted(facts.named_jobs) or "no named jobs"
            findings.append(
                Finding(
                    "policy.renamed",
                    check.context,
                    f"no job in {check.workflow} reports this name. Named jobs there: "
                    f"{actual}. Either the job was renamed or its `name:` was dropped, "
                    "which turns a declared context into a job-id context",
                )
            )
            continue
        if job_id != check.job:
            findings.append(
                Finding(
                    "policy.renamed",
                    check.context,
                    f"declares job {check.job!r} but {check.workflow} reports this name "
                    f"from job {job_id!r}",
                )
            )

    # Every named job in a tracked workflow must be accounted for. This is what
    # makes removing an inventory entry a failure instead of silence: the check
    # still exists, still reports on PRs, and now nothing says what it is.
    declared_contexts = set(by_context)
    for name in tracked:
        facts = facts_by_workflow.get(name)
        if facts is None:
            findings.append(
                Finding(
                    "policy.unknown-workflow",
                    name,
                    "is listed in tracked_workflows but is not a readable workflow file",
                )
            )
            continue
        for context in sorted(facts.named_jobs):
            if context in declared_contexts:
                continue
            findings.append(
                Finding(
                    "policy.ungated",
                    context,
                    f"is produced by {name} (job {facts.named_jobs[context]!r}) but is "
                    "declared nowhere in the policy inventory. A check that reports on "
                    "PRs and is declared nowhere is required nowhere: it goes red and "
                    "merges continue. Declare it with its enforcement and a reason",
                )
            )

    # ── 2. inventory vs develop's required contexts ───────────────────────────
    for check in inventory:
        if check.is_required and check.context not in live:
            findings.append(
                Finding(
                    "policy.missing-required",
                    check.context,
                    "is declared `required` but does not appear in "
                    f"{branch}'s required status-check contexts. The check runs and its "
                    "failure blocks nothing",
                )
            )

    for context in live:
        if context in declared_contexts:
            continue
        findings.append(
            Finding(
                "policy.undeclared-gate",
                context,
                f"is required on {branch} but is declared nowhere in the policy "
                "inventory. Nothing here says which workflow must keep producing it, "
                "so it can be renamed or deleted and the gate will hang instead of "
                "failing",
            )
        )

    # ── 3. every live context must be safe to wait on ─────────────────────────
    # Run this over the *live* required set, whatever the inventory claims. This
    # is what catches `gitleaks-scan` being added to branch protection while its
    # workflow still carries a workflow-level paths-ignore — the guard has to be
    # able to fail on a gate nobody declared, not only on declared gates.
    for context in live:
        produced = produce(context)
        if produced is None:
            continue  # already reported as policy.undeclared-gate
        facts, _job_id = produced
        ok, why = facts.reports_on_develop_pr(branch)
        if not ok:
            findings.append(
                Finding(
                    "policy.stall",
                    context,
                    f"is required on {branch} but {facts.path} cannot be relied on to "
                    f"report for every PR into {branch}: {why}",
                )
            )

    # ── the aggregator is reconciled in ci.yml; only assert it is accounted for ─
    if AGGREGATOR_CONTEXT not in declared_contexts:
        findings.append(
            Finding(
                "policy.undeclared-gate",
                AGGREGATOR_CONTEXT,
                "is develop's aggregator context but is declared nowhere in the policy "
                "inventory, so its `needs` reconciliation has no declared owner",
            )
        )

    return findings


def report(findings: list[Finding], inventory: list[PolicyCheck], live: list[str]) -> str:
    """Human-readable summary: what is gated, what is not, and what broke."""
    lines: list[str] = []
    gated = [c.context for c in inventory if c.is_required]
    ungated = [
        (c.context, c.enforcement) for c in inventory if not c.is_required and c.context not in live
    ]
    lines.append(
        f"policy inventory: {len(inventory)} declared check(s), "
        f"{len(gated)} required, {len(ungated)} ungated by decision"
    )
    for context, enforcement in ungated:
        lines.append(f"  ungated ({enforcement}): {context}")
    if findings:
        lines.append("")
        lines.append(f"{len(findings)} policy-gate disagreement(s):")
        lines.extend(f"  ::error::{finding}" for finding in findings)
    else:
        lines.append("policy gate agrees with the workflows and with branch protection")
    return "\n".join(lines)


# ── entry point ─────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--branch", default="develop", help="branch whose gate is checked")
    parser.add_argument(
        "--live",
        action="store_true",
        help="read the required contexts from the API instead of the committed snapshot",
    )
    parser.add_argument("--repo", default="digithings-ai/digithings", help="owner/name")
    parser.add_argument(
        "--inventory", type=Path, default=INVENTORY_PATH, help="policy inventory path"
    )
    parser.add_argument(
        "--contexts", type=Path, default=CONTEXTS_PATH, help="required-contexts snapshot path"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        inventory, tracked = load_inventory(args.inventory)
        contexts = (
            read_live_contexts(args.repo, args.branch)
            if args.live
            else read_contexts_file(args.contexts)
        )
        facts_by_workflow = {
            name: read_workflow_facts(WORKFLOWS_DIR / name, args.branch)
            for name in tracked
            if (WORKFLOWS_DIR / name).is_file()
        }
    except GuardError as exc:
        print(f"check_required_policy_checks: {exc}", file=sys.stderr)
        return 2

    findings = reconcile(inventory, tracked, facts_by_workflow, contexts, args.branch)
    print(report(findings, inventory, contexts))
    return 1 if findings else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
