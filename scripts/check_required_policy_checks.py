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
  * **untracked producer** — ``tracked_workflows`` is a hand-maintained
    allowlist, and an allowlist with no completeness check is not an inventory.
    Adding ``security-scc.yml`` carrying a real gate leaves this guard green,
    because it only ever looked at the eight files it was told about. So every
    ``*.yml`` under ``.github/workflows/`` is parsed, and a workflow that
    produces a live or declared context while sitting outside the allowlist is
    a finding. Before this rule, such a context drew
    ``policy.undeclared-gate`` and the stall analysis never ran on it — the
    right verdict from the wrong evidence.
  * **unreachable declared check** — reachability used to be checked only for
    contexts in the *live required* set, so a workflow-level ``paths-ignore``
    added to a tracked workflow whose checks are all ``advisory`` was a false
    green: nothing waits on those names yet, so the guard never asked whether
    they can report. It now asks for every declared non-``other-branch`` entry,
    which is what makes promoting one (DIG-1952 child B) safe to plan.
  * **unowned escape hatch** — ``advisory`` used to require a free-text
    ``reason`` and nothing else, and nothing ever checked the reason was still
    true. An entry that was right when written is now indistinguishable from one
    that is right today, forever. Every non-``required`` entry therefore names
    an ``owner``, and every ``advisory`` entry must also be dated
    (``review_by:``), tracked (``issue:``), or gated by a context that is
    genuinely in the gate (``gated_by:``).

The stall rule itself was also incomplete. ``read_workflow_facts`` read the
``pull_request`` trigger, ``paths``/``paths-ignore`` and ``branches``, and never
read ``types`` or ``branches-ignore``. Required status checks are evaluated
against the PR's **head SHA**, so a workflow on ``types: [opened]`` reports once
for the opening SHA and never again: fix the title, push, and the PR waits on
"Waiting for status to be reported" forever while this guard called the workflow
reachable. Both are parsed now, and the rule is spelled out in
``WorkflowFacts.reports_on_develop_pr``.

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
import fnmatch
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
INVENTORY_PATH = REPO_ROOT / ".github" / "policy-checks.yml"
CONTEXTS_PATH = REPO_ROOT / ".github" / "required-contexts.txt"

#: The check name. Its ``needs`` reconciliation is the
#: pre-existing in-file check; this script only asserts the name is accounted
#: for, and does not duplicate it.
AGGREGATOR_CONTEXT = "Required checks passed"

ENFORCEMENTS = frozenset({"required", "advisory", "other-branch"})

#: Activity types GitHub uses for ``pull_request`` when the workflow declares no
#: ``types:`` list. Declared here because the reachability rule is about the
#: *declared* list, and an absent list means "GitHub's default", not "nothing".
DEFAULT_PR_TYPES = ("opened", "synchronize", "reopened")

#: The activity type a required status check must survive. Required contexts are
#: evaluated against the PR head SHA, so the only event that re-reports on a new
#: push is ``synchronize``. A workflow without it goes silent after the opening
#: push and the merge button hangs.
REQUIRED_PR_TYPE = "synchronize"

#: Suffixes GitHub reads as workflow definitions. ``.yaml`` is rare here but the
#: completeness scan must not be narrower than the directory.
WORKFLOW_SUFFIXES = (".yml", ".yaml")


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
    #: Who answers for this entry. Required on every non-``required`` entry,
    #: because "deliberately not a gate" with no name on it is how an escape
    #: hatch outlives the decision that justified it.
    owner: str | None = None
    #: When this decision must be looked at again (YYYY-MM-DD).
    review_by: str | None = None
    #: The issue that tracks closing the gap (DIG-NNNN).
    issue: str | None = None
    #: A context that is ``required`` in this inventory *and* present in the live
    #: gate. Says "this still blocks a merge, just not directly", which is a
    #: fact the guard checks rather than a claim it takes on trust.
    gated_by: str | None = None
    #: An accepted, written-down reachability gap for an entry that is not a
    #: gate. Suppresses the reachability finding *only* while the entry is not
    #: in the live required set: promote it and the gap becomes a stall.
    known_gap: str | None = None

    @property
    def is_required(self) -> bool:
        return self.enforcement == "required"

    @property
    def needs_review_date(self) -> bool:
        """Is this entry dated, tracked, or gated — i.e. is someone on the hook?"""
        return bool(self.review_by or self.issue or self.gated_by)


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
    #: ``pull_request.branches-ignore``, which removes the workflow from the
    #: stated branches rather than restricting it to them.
    branch_ignore: list[str] | None = None
    #: ``pull_request.types``. ``None`` means the key is absent, which GitHub
    #: reads as DEFAULT_PR_TYPES — that *does* include ``synchronize``, so an
    #: absent key is reachable. A declared list without ``synchronize`` is not.
    pr_types: list[str] | None = None

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
        if self.branch_ignore is not None and _branch_matches(branch, self.branch_ignore):
            return False, (
                f"the workflow-level `pull_request:` branches-ignore filter "
                f"({self.branch_ignore}) excludes `{branch}`, so this check never "
                f"reports on a PR into `{branch}`"
            )
        if self.pr_types is not None and REQUIRED_PR_TYPE not in self.pr_types:
            return False, (
                f"the workflow-level `pull_request:` types filter "
                f"({self.pr_types or 'empty or unreadable'}) has no "
                f"`{REQUIRED_PR_TYPE}`. Required status checks are evaluated against "
                "the PR's head SHA, and `synchronize` is the only event that "
                "re-reports on a new push, so this workflow reports for the opening "
                "SHA and never again: after the first push the PR waits on "
                '"Waiting for status to be reported" forever, with no failing check '
                "to explain why. Add `synchronize` to types, or drop the filter so "
                f"GitHub applies its default ({', '.join(DEFAULT_PR_TYPES)})"
            )
        return True, ""


def _branch_matches(branch: str, patterns: list[str]) -> bool:
    """Is ``branch`` caught by a ``branches-ignore`` pattern list?"""
    return any(branch == str(p) or fnmatch.fnmatch(branch, str(p)) for p in patterns)


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
    if not isinstance(pr, dict):
        return facts
    for key, label in (("paths", "paths"), ("paths-ignore", "paths-ignore")):
        if key in pr:
            facts.path_filter = (label, pr[key])
            break
    branches = pr.get("branches")
    if isinstance(branches, list):
        facts.branch_filter = [str(b) for b in branches]
    ignored = pr.get("branches-ignore")
    if isinstance(ignored, list):
        facts.branch_ignore = [str(b) for b in ignored]
    # A declared `types:` list is the whole reachability story, because required
    # contexts are evaluated against the head SHA and only `synchronize` re-reports
    # on a new push. An absent key is GitHub's default, which includes it. A
    # present-but-unreadable value becomes the empty list so the rule fails closed
    # rather than passing on a value nobody could read.
    if "types" in pr:
        types = pr["types"]
        facts.pr_types = [str(t) for t in types] if isinstance(types, list) else []
    return facts


def scan_untracked_workflows(
    tracked: list[str],
    branch: str,
    workflows_dir: Path | None = None,
) -> tuple[dict[str, WorkflowFacts], list[Finding]]:
    """Parse every workflow file that ``tracked_workflows`` does not name.

    ``tracked_workflows`` is an allowlist, and an allowlist nobody checks for
    completeness is not an inventory: a brand-new workflow carrying a real gate is
    invisible to this guard by construction. So the directory is scanned too, and
    the caller treats an untracked producer of a live or declared context as a
    finding.

    An untracked file that will not parse is reported, not raised. Raising would
    let any workflow file on ``develop`` — most of which are not policy surfaces —
    take the guard down with an unreadable error instead of a diagnosis.
    """
    root = workflows_dir or WORKFLOWS_DIR
    known = set(tracked)
    facts: dict[str, WorkflowFacts] = {}
    findings: list[Finding] = []
    for path in sorted(root.glob("*")):
        if not path.is_file() or path.suffix not in WORKFLOW_SUFFIXES:
            continue
        if path.name in known:
            continue
        try:
            facts[path.name] = read_workflow_facts(path, branch)
        except GuardError as exc:
            findings.append(
                Finding(
                    "policy.unreadable-workflow",
                    path.name,
                    f"is not tracked and could not be parsed, so any check it produces "
                    f"cannot be reconciled against the inventory: {exc}. If it is a "
                    "policy surface, add it to tracked_workflows",
                )
            )
    return facts, findings


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
        # Ownership. `advisory` is an escape hatch that stays open forever unless
        # someone is on the hook for it: a free-text reason that was true when
        # written is indistinguishable from one that is true now. `owner:` is
        # mandatory off the gate, and an advisory entry must additionally be
        # dated, tracked, or provably gated behind a context that really is in the
        # gate — three ways of naming whoever revisits it.
        owner = str(entry.get("owner") or "").strip()
        if enforcement != "required" and not owner:
            raise GuardError(
                f"{where} ({context}): every non-required entry needs an 'owner'. An "
                "advisory entry with no owner is an escape hatch nobody is on the hook "
                "for, so the reason it was written stays true forever or stops being "
                "true, and nothing notices"
            )
        if enforcement == "required" and entry.get("owner") is not None and not owner:
            raise GuardError(f"{where} ({context}): 'owner' must be a non-empty string")
        checks.append(
            PolicyCheck(
                context=context,
                workflow=str(entry["workflow"]),
                job=str(entry["job"]),
                enforcement=enforcement,
                reason=" ".join(reason.split()),
                owner=owner or None,
                review_by=_clean_optional(entry.get("review_by")),
                issue=_clean_optional(entry.get("issue")),
                gated_by=_clean_optional(entry.get("gated_by")),
                known_gap=_clean_optional(entry.get("known_gap")),
            )
        )
    checks_by_context = {check.context: check for check in checks}
    for check in checks:
        where = f"{path}: {check.context}"
        if check.enforcement != "advisory":
            continue
        if not check.needs_review_date:
            raise GuardError(
                f"{where}: an advisory entry must also carry one of 'review_by' "
                "(a date to revisit it), 'issue' (DIG-NNNN tracking the gap), or "
                "'gated_by' (a context that is really in the gate). Without one, "
                "nothing ever re-reads the reason"
            )
        if check.gated_by and check.gated_by not in checks_by_context:
            raise GuardError(
                f"{where}: gated_by {check.gated_by!r} is not declared in this "
                "inventory, so it names no check and gates nothing"
            )
    return checks, [str(name) for name in tracked]


def _clean_optional(value: Any) -> str | None:
    """Normalise an optional scalar metadata field to a stripped string."""
    text = str(value or "").strip()
    return " ".join(text.split()) or None


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
    untracked_facts: dict[str, WorkflowFacts] | None = None,
    workflows_dir: Path | None = None,
) -> list[Finding]:
    """The three-way reconciliation. Returns every disagreement found."""
    findings: list[Finding] = []
    by_context = {check.context: check for check in inventory}
    live = list(required_contexts)
    root = workflows_dir or WORKFLOWS_DIR
    # Untracked workflows are parsed so that producer resolution can name the file
    # that actually reports a context. They are deliberately *not* candidates for
    # `policy.ungated`: an untracked workflow is by definition not yet declared to
    # be a policy surface, and reporting all 45 of them would bury the real
    # finding under noise nobody would read.
    untracked_facts = untracked_facts or {}

    def produce(context: str) -> tuple[WorkflowFacts, str, bool] | None:
        """(facts, job id, is_tracked) for whoever reports ``context``."""
        for name in tracked:
            facts = facts_by_workflow.get(name)
            if facts and context in facts.named_jobs:
                return facts, facts.named_jobs[context], True
        for name in sorted(untracked_facts):
            facts = untracked_facts[name]
            if context in facts.named_jobs:
                return facts, facts.named_jobs[context], False
        return None

    # ── 1. inventory vs the workflows ─────────────────────────────────────────
    for check in inventory:
        facts = facts_by_workflow.get(check.workflow)
        if facts is None:
            if (root / check.workflow).is_file():
                findings.append(
                    Finding(
                        "policy.untracked-producer",
                        check.context,
                        f"names workflow {check.workflow!r}, which exists but is not "
                        "in tracked_workflows. The allowlist has no completeness "
                        "check, so an untracked file is out of scope: nothing checks "
                        "that its named jobs are declared or that it can report. Add "
                        "it to tracked_workflows",
                    )
                )
            else:
                findings.append(
                    Finding(
                        "policy.unknown-workflow",
                        check.context,
                        f"names workflow {check.workflow!r}, which is not a readable "
                        "tracked workflow file",
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
        # `gated_by:` is only honest if the named context really is in the gate.
        # Checking it here, against the same live set as everything else, is what
        # stops it from becoming a fresh escape hatch with extra steps.
        if check.gated_by and check.gated_by not in live:
            findings.append(
                Finding(
                    "policy.bad-gated-by",
                    check.context,
                    f"claims gated_by {check.gated_by!r}, but that context is not in "
                    f"{branch}'s required status-check contexts. Nothing waits on it, "
                    "so this entry blocks no merge",
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
    #
    # `produce` now also resolves untracked producers, so this loop runs on the
    # workflow that really reports the context. It used to skip undeclared gates
    # entirely, which is how a gate nobody declared drew the right verdict from
    # no evidence at all: `policy.undeclared-gate` fired and the stall question
    # was never asked.
    for context in live:
        produced = produce(context)
        if produced is None:
            continue  # already reported as policy.undeclared-gate
        facts, _job_id, is_tracked = produced
        if not is_tracked:
            findings.append(
                Finding(
                    "policy.untracked-producer",
                    context,
                    f"is required on {branch} but is produced by {facts.path}, which "
                    "is not in tracked_workflows. An untracked producer is out of "
                    "scope for the allowlist check, so its jobs are never reconciled "
                    "against the inventory: they can be renamed, dropped, or made "
                    "unreachable and nothing here would say so. Track the file",
                )
            )
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

    # ── 4. declared entries nobody gates yet must still be reachable ───────────
    # Reachability used to be checked only for the live required set, so a
    # workflow-level `paths-ignore` on a tracked workflow whose checks are all
    # advisory was a false green: nothing waits on those names, so the guard never
    # asked whether they can report — and the day one is promoted (DIG-1952 child
    # B) every PR it does not cover hangs. `other-branch` is excluded because its
    # whole purpose is to gate a branch this guard is not looking at.
    for check in inventory:
        if check.enforcement == "other-branch" or check.context in live:
            continue  # live contexts are covered above; no double-reporting
        facts = facts_by_workflow.get(check.workflow)
        if facts is None:
            continue  # already reported
        if check.known_gap:
            continue
        ok, why = facts.reports_on_develop_pr(branch)
        if not ok:
            findings.append(
                Finding(
                    "policy.stall",
                    check.context,
                    f"is declared `{check.enforcement}` and gates nothing today, but "
                    f"{facts.path} cannot be relied on to report for every PR into "
                    f"{branch}: {why}. This is the hole DIG-1952 child B would walk "
                    "into when it promotes this entry. Fix the filter, or record a "
                    "`known_gap:` on the entry saying the gap is accepted — which "
                    "stops applying the moment the entry reaches the live gate",
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
        (c.context, c.enforcement, c.owner or "UNOWNED", c.issue or c.review_by or c.gated_by)
        for c in inventory
        if not c.is_required and c.context not in live
    ]
    lines.append(
        f"policy inventory: {len(inventory)} declared check(s), "
        f"{len(gated)} required, {len(ungated)} ungated by decision"
    )
    for context, enforcement, owner, follow_up in ungated:
        hook = f" [{follow_up}]" if follow_up else ""
        lines.append(f"  ungated ({enforcement}, owner {owner}{hook}): {context}")
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
        # Completeness: `tracked_workflows` is an allowlist, so parse the rest of
        # the directory too. Without this the allowlist is the guard's whole view
        # of the repository and a new workflow carrying a gate is invisible.
        untracked_facts, untracked_findings = scan_untracked_workflows(tracked, args.branch)
    except GuardError as exc:
        print(f"check_required_policy_checks: {exc}", file=sys.stderr)
        return 2

    findings = untracked_findings + reconcile(
        inventory, tracked, facts_by_workflow, contexts, args.branch, untracked_facts
    )
    print(report(findings, inventory, contexts))
    return 1 if findings else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
