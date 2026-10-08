"""Unit tests for scripts/check_required_policy_checks.py (DIG-1982, DIG-2237).

The guard that lived in ``ci.yml`` alone compared ``required-checks.needs`` to
the jobs in ``ci.yml`` — so it was structurally incapable of failing on any
policy check that lives in another workflow file. These tests pin the two
failure modes the replacement has to catch, and the two it must *not* raise on
the repository's correct current setup.

DIG-2237 hardened that guard after review found three checks that did not cover
the properties they were relied on for: ``types:`` and ``branches-ignore:`` were
never parsed (so a workflow that stops re-reporting on the head SHA looked
reachable), ``tracked_workflows`` was a closed allowlist with no completeness
check, and ``advisory`` entries needed only a free-text reason and no owner. The
tests in the DIG-2237 sections below are those three, plus the two cheap ones
from the same review.

Every test here is written so that removing the corresponding guard rule makes
it fail. That is the only reason to believe a green run means anything: a test
that passes against a guard with the rule deleted is documenting nothing.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_required_policy_checks.py"
INVENTORY = REPO_ROOT / ".github" / "policy-checks.yml"
CONTEXTS = REPO_ROOT / ".github" / "required-contexts.txt"
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PR_HYGIENE_YML = REPO_ROOT / ".github" / "workflows" / "ci-pr-hygiene.yml"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

#: The live required contexts on develop as of 2026-10-07, read from
#: GET /repos/digithings-ai/digithings/branches/develop/protection. Two of
#: these are produced by workflows other than ci.yml, and that is correct —
#: they are the reason a ci.yml-only guard was the wrong inventory.
LIVE_CONTEXTS = ["Required checks passed", "doc-links + agents-init", "mypy — digibase + digikey"]


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("check_required_policy_checks", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_required_policy_checks"] = module
    spec.loader.exec_module(module)
    return module


guard = _load()


def _real_facts(workflows_dir: Path | None = None) -> dict[str, Any]:
    """Parse every tracked workflow from the actual repository."""
    root = workflows_dir or guard.WORKFLOWS_DIR
    _inventory, tracked = guard.load_inventory(INVENTORY)
    return {name: guard.read_workflow_facts(root / name, "develop") for name in tracked}


def _run(
    inventory: list[Any],
    tracked: list[str],
    contexts: list[str],
    branch: str = "develop",
    workflows_dir: Path | None = None,
    untracked_facts: dict[str, Any] | None = None,
):
    root = workflows_dir or guard.WORKFLOWS_DIR
    facts = {name: guard.read_workflow_facts(root / name, branch) for name in tracked}
    return guard.reconcile(
        inventory,
        tracked,
        facts,
        contexts,
        branch,
        untracked_facts or {},
        root,
    )


def _workflows_copy(tmp_path: Path) -> Path:
    """A writable copy of the whole workflows directory, for mutation."""
    import shutil

    target = tmp_path / "workflows"
    shutil.copytree(WORKFLOWS_DIR, target)
    return target


def _untracked_scan(tmp_path: Path, tracked: list[str] | None = None):
    root = _workflows_copy(tmp_path)
    if tracked is None:
        _inventory, tracked = guard.load_inventory(INVENTORY)
    return root, guard.scan_untracked_workflows(tracked, "develop", workflows_dir=root)


def _codes(findings: list[Any]) -> set[str]:
    return {f.code for f in findings}


def _subjects(findings: list[Any], code: str) -> set[str]:
    return {f.subject for f in findings if f.code == code}


# ── the guard passes on the repository's correct current setup ────────────────


def test_passes_on_this_repository_unchanged() -> None:
    """The whole point of reading the brief's trap: the two out-of-file required
    checks are required-and-out-of-file, which is correct, so nothing fires."""
    findings = _run(*guard.load_inventory(INVENTORY), guard.read_contexts_file(CONTEXTS))
    assert findings == [], [str(f) for f in findings]


def test_committed_contexts_match_the_dated_live_gate_read() -> None:
    """The snapshot is the guard's CI input, so it has to match reality. If this
    fails, someone changed branch protection without updating the file.

    Stated honestly, because the name used to claim more than it does: this
    compares the committed file to a *dated literal* transcribed on 2026-10-07.
    It makes no network call and cannot detect drift that happened after that
    date. What re-verifies the snapshot against the live gate is the scheduled
    ``--live`` job in ci-pr-hygiene.yml — see
    ``test_the_snapshot_is_reverified_by_a_scheduled_live_read`` — and the
    literal above is that job's human-readable statement of what it proved.
    """
    assert guard.read_contexts_file(CONTEXTS) == LIVE_CONTEXTS


def test_inventory_and_contexts_are_internally_consistent() -> None:
    inventory, tracked = guard.load_inventory(INVENTORY)
    required = [c.context for c in inventory if c.is_required]
    assert sorted(required) == sorted(LIVE_CONTEXTS)
    # Every tracked workflow must actually exist, or reconciliation 1 is vacuous.
    for name in tracked:
        assert (guard.WORKFLOWS_DIR / name).is_file(), name


# ── failure mode 2: a PR-triggered policy check that is required nowhere ─────


def test_removing_a_policy_check_from_the_inventory_fails() -> None:
    """DoD: take `All commits signed off` out and the guard fails.

    The check still reports on every PR. Deleting its inventory entry does not
    stop it reporting — it only stops anything recording that it ought to be a
    gate. That is the DIG-1952 bug in its purest form: the check goes red and
    the merge proceeds.
    """
    inventory, tracked = guard.load_inventory(INVENTORY)
    assert "All commits signed off" in {c.context for c in inventory}
    stripped = [c for c in inventory if c.context != "All commits signed off"]

    findings = _run(stripped, tracked, guard.read_contexts_file(CONTEXTS))

    assert "policy.ungated" in _codes(findings)
    assert "All commits signed off" in _subjects(findings, "policy.ungated")


def test_declaring_a_check_required_that_the_gate_does_not_hold_fails() -> None:
    """The other direction of the same bug: the inventory says a check gates the
    merge and branch protection disagrees."""
    inventory, tracked = guard.load_inventory(INVENTORY)
    mutated = [
        dataclasses.replace(c, enforcement="required")
        if c.context == "All commits signed off"
        else c
        for c in inventory
    ]

    findings = _run(mutated, tracked, guard.read_contexts_file(CONTEXTS))

    assert "policy.missing-required" in _codes(findings)
    assert "All commits signed off" in _subjects(findings, "policy.missing-required")


def test_every_ungated_policy_check_is_reported() -> None:
    """The five drift checks DIG-1952 names must all be visible, not just DCO."""
    inventory, _tracked = guard.load_inventory(INVENTORY)
    declared = {c.context: c for c in inventory}
    expected = {
        "All commits signed off",
        "gitleaks-scan",
        "All agent-task issues in TSV with real phase and valid model",
        "Validate PR title",
        "Every commit reaching main was reviewed",
    }
    assert expected <= set(declared)
    for context in expected:
        assert not declared[context].is_required, context
        assert declared[context].reason, f"{context} needs a reason"


def test_gitleaks_is_flagged_as_the_highest_value_ungated_check() -> None:
    """gitleaks-scan is secret scanning, and the brief says flag it hardest."""
    inventory, _tracked = guard.load_inventory(INVENTORY)
    gitleaks = next(c for c in inventory if c.context == "gitleaks-scan")
    assert gitleaks.enforcement == "advisory"
    assert "paths-ignore" in gitleaks.reason
    assert gitleaks.workflow == "security-gitleaks.yml"


# ── failure mode 1: a required context no PR-triggered workflow produces ─────


def test_requiring_gitleaks_while_it_is_path_filtered_fails() -> None:
    """The stall, end to end.

    `security-gitleaks.yml` carries a workflow-level `paths-ignore` of `**.md`
    and `docs/**`. Make `gitleaks-scan` required anyway — exactly what
    DIG-1952 child B would do — and docs-only PRs never start the workflow, so
    the check never reports and GitHub blocks them on "Waiting for status to be
    reported" forever. This is why the entry cannot simply be flipped to
    `required`.
    """
    contexts = [*LIVE_CONTEXTS, "gitleaks-scan"]

    findings = _run(*guard.load_inventory(INVENTORY), contexts)

    assert "policy.stall" in _codes(findings)
    assert "gitleaks-scan" in _subjects(findings, "policy.stall")


def test_a_required_context_from_a_non_pr_workflow_fails() -> None:
    """A context required on develop that only ever runs on a schedule cannot
    report for a PR, so requiring it hangs every PR."""
    facts = guard.WorkflowFacts(path="scheduled-only.yml", named_jobs={"nightly": "nightly"})
    ok, why = facts.reports_on_develop_pr("develop")
    assert not ok
    assert "no `pull_request:` trigger" in why


def test_a_required_context_filtered_to_another_branch_fails() -> None:
    """`ci-review-coverage.yml` is required on main and targets main only.
    Requiring it on develop is the same hang in a different costume."""
    facts = guard.read_workflow_facts(guard.WORKFLOWS_DIR / "ci-review-coverage.yml", "develop")
    ok, why = facts.reports_on_develop_pr("develop")
    assert not ok
    assert "does not include `develop`" in why

    # ...and on main, the same workflow is fine.
    ok_main, _ = facts.reports_on_develop_pr("main")
    assert ok_main


def test_stall_rule_covers_a_workflow_level_paths_filter() -> None:
    facts = guard.WorkflowFacts(
        path="x.yml",
        named_jobs={"c": "c"},
        pr_triggered=True,
        path_filter=("paths-ignore", ["**.md"]),
    )
    ok, why = facts.reports_on_develop_pr("develop")
    assert not ok
    assert "can skip the whole workflow" in why


# ── the required-and-out-of-file checks the brief warns about ────────────────


def test_the_two_out_of_file_required_checks_are_genuinely_required() -> None:
    """`doc-links + agents-init` and `mypy — digibase + digikey` live in
    ci-docs.yml and ci-type-check.yml, outside ci.yml's `needs`. Reconciling
    against ci.yml's job names — what DIG-1952 item 2 asked for literally —
    would demand they be added to `needs` and break the mechanism that works."""
    inventory, _tracked = guard.load_inventory(INVENTORY)
    by_context = {c.context: c for c in inventory}
    for context, workflow in (
        ("doc-links + agents-init", "ci-docs.yml"),
        ("mypy — digibase + digikey", "ci-type-check.yml"),
    ):
        check = by_context[context]
        assert check.is_required
        assert check.workflow == workflow
        assert check.workflow != "ci.yml"


# ── rename and shape detection ───────────────────────────────────────────────


def test_a_renamed_check_is_detected() -> None:
    """The declared context must still be the name the workflow reports."""
    facts = guard.read_workflow_facts(guard.WORKFLOWS_DIR / "ci-pr-title.yml", "develop")
    assert facts.named_jobs["Validate PR title"] == "lint-pr-title"

    inventory, tracked = guard.load_inventory(INVENTORY)
    mutated = [
        dataclasses.replace(c, job="some-other-job") if c.context == "Validate PR title" else c
        for c in inventory
    ]

    findings = _run(mutated, tracked, guard.read_contexts_file(CONTEXTS))
    assert "policy.renamed" in _codes(findings)


def test_an_undeclared_required_context_is_detected() -> None:
    """A live gate nobody has declared has no owner, so it can be renamed away
    and the branch will hang instead of failing."""
    contexts = [*LIVE_CONTEXTS, "a gate nobody declared"]

    findings = _run(*guard.load_inventory(INVENTORY), contexts)

    assert "policy.undeclared-gate" in _codes(findings)
    assert "a gate nobody declared" in _subjects(findings, "policy.undeclared-gate")


@pytest.mark.parametrize(
    "body",
    [
        "checks: []\n",  # no checks at all
        "tracked_workflows: []\nchecks:\n  - context: a\n    workflow: ci.yml\n"
        "    job: required-checks\n    enforcement: required\n    reason: r\n",
        "tracked_workflows: [ci.yml]\nchecks:\n  - context: a\n    workflow: ci.yml\n",
        "tracked_workflows: [ci.yml]\nchecks:\n  - context: a\n    workflow: ci.yml\n"
        "    job: required-checks\n    enforcement: nonsense\n    reason: r\n",
        "tracked_workflows: [ci.yml]\nchecks:\n  - context: a\n    workflow: ci.yml\n"
        "    job: required-checks\n    enforcement: required\n",  # no reason
    ],
)
def test_a_malformed_inventory_raises_rather_than_checking_nothing(tmp_path, body: str) -> None:
    """A guard that treats a broken inventory as "no checks declared" goes green
    having checked nothing. That is the exact false-green this leaf exists to
    stop, so shape errors raise."""
    path = tmp_path / "policy-checks.yml"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(guard.GuardError):
        guard.load_inventory(path)


def test_duplicate_contexts_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "policy-checks.yml"
    entry = "  - context: dup\n    workflow: ci.yml\n    job: required-checks\n    enforcement: required\n    reason: r\n"
    path.write_text(f"tracked_workflows: [ci.yml]\nchecks:\n{entry}{entry}", encoding="utf-8")
    with pytest.raises(guard.GuardError, match="duplicate"):
        guard.load_inventory(path)


# ── DIG-2237: the guard must cover the properties it is relied on for ─────────
#
# Three holes, in the order the brief puts them. Each test below fails if its
# rule is deleted, which is the standard this file states for itself.


def _synthetic_workflow(root: Path, name: str, trigger: str, job: str = "gate") -> Path:
    """Write a minimal but genuine workflow, so trigger parsing is exercised on a
    shape the repository does not currently contain — which is the whole point of
    the `types` and `branches-ignore` rules."""
    path = root / name
    path.write_text(
        f"name: t\non:\n  pull_request:\n{trigger}jobs:\n  {job}:\n"
        "    name: Synthetic gate\n    runs-on: ubuntu-latest\n    steps:\n      - run: true\n",
        encoding="utf-8",
    )
    return path


# `types` — the GATE. Required contexts are evaluated against the head SHA, so a
# workflow that never re-reports on `synchronize` stalls the PR forever while
# looking, to a trigger-only reader, perfectly reachable.


def test_a_types_filter_without_synchronize_is_not_reachable(tmp_path: Path) -> None:
    path = _synthetic_workflow(tmp_path, "t.yml", "    types: [opened]\n")
    facts = guard.read_workflow_facts(path, "develop")
    assert facts.pr_types == ["opened"]

    reachable, reason = facts.reports_on_develop_pr("develop")
    assert not reachable
    # The message has to teach, or the fix is a guess: which type is missing,
    # why it matters, and what the PR looks like while it is missing.
    assert "synchronize" in reason
    assert "head SHA" in reason
    assert "Waiting for status to be reported" in reason


@pytest.mark.parametrize(
    "types_line",
    [
        "    types: [opened, synchronize, reopened]\n",
        "    types: [opened, edited, synchronize, reopened]\n",
    ],
)
def test_a_types_filter_with_synchronize_is_reachable(tmp_path: Path, types_line: str) -> None:
    """The rule must not fire on the repo's own filters, so pin the two shapes
    that are actually safe today."""
    path = _synthetic_workflow(tmp_path, "t.yml", types_line)
    assert guard.read_workflow_facts(path, "develop").reports_on_develop_pr("develop") == (True, "")


def test_an_absent_types_filter_is_git_hubs_default_and_is_reachable(tmp_path: Path) -> None:
    """No `types:` key means [opened, synchronize, reopened], which includes
    synchronize. Reading an absent key as "no types" would fire on ci.yml."""
    path = _synthetic_workflow(tmp_path, "t.yml", "")
    facts = guard.read_workflow_facts(path, "develop")
    assert facts.pr_types is None
    assert facts.reports_on_develop_pr("develop") == (True, "")


def test_a_types_filter_narrowed_on_a_real_workflow_is_a_stall(tmp_path: Path) -> None:
    """The brief's trap, on the file it names: drop `edited` from ci-pr-title.yml,
    fix the title, push nothing. The check never re-runs."""
    root = _workflows_copy(tmp_path)
    path = root / "ci-pr-title.yml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "    types: [opened, edited, synchronize, reopened]",
            "    types: [opened, edited]",
        ),
        encoding="utf-8",
    )
    inventory, tracked = guard.load_inventory(INVENTORY)
    findings = _run(inventory, tracked, LIVE_CONTEXTS, workflows_dir=root)
    assert "Validate PR title" in _subjects(findings, "policy.stall")


def test_a_branches_ignore_filter_that_excludes_the_branch_is_not_reachable(tmp_path: Path) -> None:
    path = _synthetic_workflow(tmp_path, "t.yml", "    branches-ignore: [develop]\n")
    reachable, reason = guard.read_workflow_facts(path, "develop").reports_on_develop_pr("develop")
    assert not reachable
    assert "branches-ignore" in reason


def test_a_branches_ignore_glob_that_does_not_match_is_reachable(tmp_path: Path) -> None:
    """`branches-ignore` takes globs, so an exact-match reader would call
    `feature/*` a match for develop."""
    path = _synthetic_workflow(tmp_path, "t.yml", "    branches-ignore: ['feature/*']\n")
    assert guard.read_workflow_facts(path, "develop").reports_on_develop_pr("develop") == (True, "")


def test_a_branches_ignore_filter_on_a_required_context_is_a_stall(tmp_path: Path) -> None:
    """`branches` was already checked; `branches-ignore` is the same filter spelled
    as an exclusion, and skipping it left a required check silently unreportable."""
    root = _workflows_copy(tmp_path)
    path = root / "ci-docs.yml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "  pull_request: {}", "  pull_request:\n    branches-ignore: [develop]"
        ),
        encoding="utf-8",
    )
    inventory, tracked = guard.load_inventory(INVENTORY)
    findings = _run(inventory, tracked, LIVE_CONTEXTS, workflows_dir=root)
    assert "doc-links + agents-init" in _subjects(findings, "policy.stall")


# Untracked-workflow completeness.


def test_every_workflow_file_outside_the_allowlist_is_still_read(tmp_path: Path) -> None:
    """`tracked_workflows` may stay a short allowlist, but the directory is still
    scanned, so a new workflow is not invisible by construction."""
    _root, (facts, findings) = _untracked_scan(tmp_path)
    _inventory, tracked = guard.load_inventory(INVENTORY)
    on_disk = {p.name for p in WORKFLOWS_DIR.iterdir() if p.suffix in (".yml", ".yaml")}
    assert set(facts) == on_disk - set(tracked)
    assert findings == []
    assert len(tracked) < len(on_disk), "the allowlist is not actually narrower than the directory"


def test_a_new_untracked_workflow_carrying_a_gate_is_a_finding(tmp_path: Path) -> None:
    """`security-scc.yml` arrives with a real gate and an untracked name. Today
    that is out of scope entirely."""
    root = _workflows_copy(tmp_path)
    (root / "security-scc.yml").write_text(
        "name: scc\non:\n  pull_request:\njobs:\n  scc:\n    name: SCA policy gate\n"
        "    runs-on: ubuntu-latest\n    steps:\n      - run: true\n",
        encoding="utf-8",
    )
    inventory, tracked = guard.load_inventory(INVENTORY)
    untracked, unreadable = guard.scan_untracked_workflows(tracked, "develop", workflows_dir=root)
    assert "security-scc.yml" in untracked
    assert unreadable == []
    findings = _run(
        inventory,
        tracked,
        [*LIVE_CONTEXTS, "SCA policy gate"],
        workflows_dir=root,
        untracked_facts=untracked,
    )
    assert "SCA policy gate" in _subjects(findings, "policy.untracked-producer")


def test_an_untracked_producers_reachability_is_still_checked(tmp_path: Path) -> None:
    """The finding is not a substitute for the diagnosis: an untracked producer
    that cannot report is still a stall, and the message names the file."""
    root = _workflows_copy(tmp_path)
    (root / "security-scc.yml").write_text(
        "name: scc\non:\n  pull_request:\n    paths-ignore: ['**.md']\njobs:\n  scc:\n"
        "    name: SCA policy gate\n    runs-on: ubuntu-latest\n    steps:\n      - run: true\n",
        encoding="utf-8",
    )
    inventory, tracked = guard.load_inventory(INVENTORY)
    untracked, _ = guard.scan_untracked_workflows(tracked, "develop", workflows_dir=root)
    findings = _run(
        inventory,
        tracked,
        [*LIVE_CONTEXTS, "SCA policy gate"],
        workflows_dir=root,
        untracked_facts=untracked,
    )
    stalls = [f for f in findings if f.code == "policy.stall" and f.subject == "SCA policy gate"]
    assert len(stalls) == 1
    assert "security-scc.yml" in stalls[0].message


def test_an_inventory_entry_naming_an_untracked_workflow_is_a_finding(tmp_path: Path) -> None:
    """Declaring the check is not the same as tracking the workflow, and the gap
    used to be a silent pass."""
    root = _workflows_copy(tmp_path)
    (root / "security-scc.yml").write_text(
        "name: scc\non:\n  pull_request:\njobs:\n  scc:\n    name: SCA policy gate\n"
        "    runs-on: ubuntu-latest\n    steps:\n      - run: true\n",
        encoding="utf-8",
    )
    inventory, tracked = guard.load_inventory(INVENTORY)
    entry = dataclasses.replace(
        inventory[4], context="SCA policy gate", workflow="security-scc.yml", job="scc"
    )
    findings = _run([*inventory, entry], tracked, LIVE_CONTEXTS, workflows_dir=root)
    assert "SCA policy gate" in _subjects(findings, "policy.untracked-producer")


def test_an_untracked_workflow_that_cannot_be_parsed_is_reported_not_raised(tmp_path: Path) -> None:
    """Raising would hand any untracked workflow file a veto over the guard — and
    most of the 45 untracked files are not policy surfaces."""
    root = _workflows_copy(tmp_path)
    (root / "broken.yml").write_text("on: [this is not a mapping\n", encoding="utf-8")
    _inventory, tracked = guard.load_inventory(INVENTORY)
    facts, findings = guard.scan_untracked_workflows(tracked, "develop", workflows_dir=root)
    assert "broken.yml" not in facts
    assert "broken.yml" in _subjects(findings, "policy.unreadable-workflow")


def test_a_tracked_workflow_that_cannot_be_parsed_still_raises(tmp_path: Path) -> None:
    """The asymmetry is deliberate: a tracked file is a declared surface, so an
    unreadable one is a hard error, not a finding."""
    root = _workflows_copy(tmp_path)
    (root / "ci.yml").write_text("on: [this is not a mapping\n", encoding="utf-8")
    with pytest.raises(guard.GuardError):
        guard.read_workflow_facts(root / "ci.yml", "develop")


# Ownership: an escape hatch nobody owns is indistinguishable from one that is
# still justified, forever.


def test_every_non_required_entry_names_an_owner() -> None:
    inventory, _tracked = guard.load_inventory(INVENTORY)
    unowned = [c.context for c in inventory if c.enforcement != "required" and not c.owner]
    assert unowned == []


def test_every_advisory_entry_is_dated_tracked_or_provably_gated() -> None:
    """`reason:` records what was true when it was written. These three record who
    has to look again."""
    inventory, _tracked = guard.load_inventory(INVENTORY)
    for check in inventory:
        if check.enforcement == "advisory":
            assert check.needs_review_date, f"{check.context} has nobody on the hook"


def test_an_advisory_entry_without_an_owner_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "policy-checks.yml"
    path.write_text(
        "tracked_workflows: [ci.yml]\nchecks:\n  - context: b\n    workflow: ci.yml\n"
        "    job: required-checks\n    enforcement: advisory\n    reason: r\n"
        "    issue: DIG-1952\n",
        encoding="utf-8",
    )
    with pytest.raises(guard.GuardError, match="owner"):
        guard.load_inventory(path)


def test_an_advisory_entry_with_noone_on_the_hook_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "policy-checks.yml"
    path.write_text(
        "tracked_workflows: [ci.yml]\nchecks:\n  - context: b\n    workflow: ci.yml\n"
        "    job: required-checks\n    enforcement: advisory\n    reason: r\n    owner: DevOps\n",
        encoding="utf-8",
    )
    with pytest.raises(guard.GuardError, match="review_by"):
        guard.load_inventory(path)


def test_gated_by_must_name_a_declared_check(tmp_path: Path) -> None:
    """`gated_by:` is only honest if the named context is a real gate, so the
    reference is validated at load time rather than trusted. Pointing it at a
    context the inventory does not declare is the mistake worth catching first."""
    path = tmp_path / "policy-checks.yml"
    path.write_text(
        "tracked_workflows: [ci.yml]\n"
        "checks:\n"
        "  - context: Required checks passed\n    workflow: ci.yml\n    job: required-checks\n"
        "    enforcement: required\n    reason: r\n    owner: DevOps\n"
        "  - context: b\n    workflow: ci.yml\n    job: actionlint\n    enforcement: advisory\n"
        "    reason: r\n    owner: DevOps\n    gated_by: Required context not in this file\n",
        encoding="utf-8",
    )
    with pytest.raises(guard.GuardError, match="gated_by"):
        guard.load_inventory(path)


# Reachability has to cover declared checks, not just the ones in the gate.


def test_reachability_is_checked_for_advisory_entries_not_just_live_ones(tmp_path: Path) -> None:
    """The brief's false green: a workflow-level `paths-ignore` on a tracked
    advisory workflow. Nothing reports it, because nothing was waiting for it."""
    root = _workflows_copy(tmp_path)
    path = root / "ci-dco-sign-off.yml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "    types: [opened, synchronize, reopened]",
            "    paths-ignore: ['**.md']\n    types: [opened, synchronize, reopened]",
        ),
        encoding="utf-8",
    )
    inventory, tracked = guard.load_inventory(INVENTORY)
    findings = _run(inventory, tracked, LIVE_CONTEXTS, workflows_dir=root)
    assert "All commits signed off" in _subjects(findings, "policy.stall")


def test_a_known_gap_suppresses_reachability_only_while_the_entry_is_ungated() -> None:
    """gitleaks is the one entry with a genuine accepted gap, so it needs a
    documented one — and the documentation must expire at promotion."""
    inventory, tracked = guard.load_inventory(INVENTORY)
    assert _run(inventory, tracked, LIVE_CONTEXTS) == []

    promoted = _run(inventory, tracked, [*LIVE_CONTEXTS, "gitleaks-scan"])
    stalls = [f for f in promoted if f.code == "policy.stall" and f.subject == "gitleaks-scan"]
    assert len(stalls) == 1, [str(f) for f in promoted]


def test_a_gated_by_that_is_not_in_the_live_gate_is_a_finding() -> None:
    """`gated_by:` pointing at an advisory check is the same escape hatch with a
    citation on it."""
    inventory, tracked = guard.load_inventory(INVENTORY)
    assert _run(inventory, tracked, LIVE_CONTEXTS) == []

    swapped = [
        dataclasses.replace(c, gated_by="Validate PR title") if c.context == "actionlint" else c
        for c in inventory
    ]
    findings = _run(swapped, tracked, LIVE_CONTEXTS)
    assert "actionlint" in _subjects(findings, "policy.bad-gated-by")


# The snapshot has to be re-checked against reality on a clock.


def test_the_snapshot_is_reverified_by_a_scheduled_live_read() -> None:
    """Nothing re-reads the live gate, so invisible drift is the failure mode the
    renamed tautological test used to hide.

    Rides the existing digithings-cron dispatch rather than an `on.schedule:`
    trigger, which tests/scripts/test_no_gha_schedules.py forbids, and is unnamed
    so it does not become a policy surface the inventory has to list.
    """
    doc = yaml.safe_load(PR_HYGIENE_YML.read_text(encoding="utf-8"))
    job = doc["jobs"]["policy-gate-live"]
    assert "name" not in job, "a named job is a policy surface and must be declared"
    assert job["if"] == "github.event_name == 'workflow_dispatch'"
    assert "needs" not in job, "depending on the PR-only path-filter would skip this forever"
    assert job["environment"] == "cron", (
        "without it secrets.* resolves empty and the read never runs"
    )
    script = job["steps"][-1]["run"]
    assert "scripts/check_required_policy_checks.py --live" in script
    # An absent credential is unvalidated, never a failure — a canary that starts
    # red because it cannot read a secret is how a check becomes a silent stop.
    assert "::notice" in script and "exit 0" in script

    cron = (REPO_ROOT / "apps" / "digithings-cron" / "src" / "jobs.ts").read_text(encoding="utf-8")
    assert 'wd("ci-pr-hygiene"' in cron, "the dispatch this rides must still be scheduled"


def test_the_context_set_and_enforcement_values_are_unchanged_from_dig_1982() -> None:
    """DoD "exits 0 with the inventory unchanged" means the policy decisions are
    unchanged: same contexts, same workflows, same enforcement. Only the metadata
    this leaf adds (owner, issue, gated_by, known_gap) is new."""
    inventory, tracked = guard.load_inventory(INVENTORY)
    assert [(c.context, c.workflow, c.job, c.enforcement) for c in inventory] == [
        ("Required checks passed", "ci.yml", "required-checks", "required"),
        ("doc-links + agents-init", "ci-docs.yml", "docs-and-agents-init", "required"),
        ("mypy — digibase + digikey", "ci-type-check.yml", "mypy", "required"),
        ("All commits signed off", "ci-dco-sign-off.yml", "dco-sign-off", "advisory"),
        ("gitleaks-scan", "security-gitleaks.yml", "scan", "advisory"),
        (
            "All agent-task issues in TSV with real phase and valid model",
            "ci-pr-hygiene.yml",
            "coverage",
            "advisory",
        ),
        ("Validate PR title", "ci-pr-title.yml", "lint-pr-title", "advisory"),
        (
            "Every commit reaching main was reviewed",
            "ci-review-coverage.yml",
            "review-coverage",
            "other-branch",
        ),
        ("Frontend canon guard", "ci.yml", "frontend-canon", "advisory"),
        ("actionlint", "ci.yml", "actionlint", "advisory"),
    ]
    assert sorted(tracked) == [
        "ci-dco-sign-off.yml",
        "ci-docs.yml",
        "ci-pr-hygiene.yml",
        "ci-pr-title.yml",
        "ci-review-coverage.yml",
        "ci-type-check.yml",
        "ci.yml",
        "security-gitleaks.yml",
    ]


# ── the pre-existing in-file check is kept, not replaced ─────────────────────


def test_ci_yml_keeps_its_own_needs_staleness_check() -> None:
    """DoD: `Required checks passed` still reconciles against ci.yml's `needs`,
    and that check is kept rather than replaced by this script."""
    doc = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    steps = doc["jobs"]["required-checks"]["steps"]
    names = [s.get("name") for s in steps]
    assert "Verify needs list covers every job in this file" in names


def test_the_ci_yml_needs_check_is_green_on_this_repository() -> None:
    """Re-run ci.yml's own drift check verbatim so the kept check is proven, not
    merely asserted to exist."""
    doc = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    jobs = set(doc["jobs"]) - {"required-checks"}
    needs = set(doc["jobs"]["required-checks"]["needs"])
    assert jobs - needs == set(), f"stale needs list: {sorted(jobs - needs)}"
    assert needs - jobs == set(), f"phantom needs entries: {sorted(needs - jobs)}"


def test_this_script_does_not_duplicate_the_needs_check() -> None:
    """The guard reconciles the other two sets and only asserts the aggregator is
    accounted for. Re-implementing the third comparison here would give two
    places to update whenever a ci.yml job is added.

    Anchored on the job id as it appears in a code path: the script names the
    aggregator only through AGGREGATOR_CONTEXT and never reads `jobs[...]`."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert source.count("AGGREGATOR_CONTEXT") >= 3
    # It never reaches into ci.yml's job graph: no `jobs` subscript anywhere in
    # the code, so there is no second copy of the needs comparison to keep in
    # sync when a ci.yml job is added.
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    assert not re.search(r"""\[.jobs.\]""", code), "the guard must not read ci.yml's jobs"


# ── the script runs end to end ───────────────────────────────────────────────


def test_script_exits_zero_on_this_repository() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, cwd=REPO_ROOT
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "policy gate agrees" in proc.stdout


def test_script_exits_nonzero_when_the_inventory_is_mutated(tmp_path: Path) -> None:
    """The DoD test, run through the real CLI rather than only in-process."""
    inventory, tracked = guard.load_inventory(INVENTORY)
    stripped = [c for c in inventory if c.context != "All commits signed off"]
    path = tmp_path / "policy-checks.yml"
    # yaml.dump, not f-strings: several reasons contain apostrophes and colons
    # that hand-quoting mangles into unparseable YAML.
    path.write_text(
        yaml.safe_dump(
            {
                "tracked_workflows": tracked,
                "checks": [
                    {
                        "context": c.context,
                        "workflow": c.workflow,
                        "job": c.job,
                        "enforcement": c.enforcement,
                        "reason": c.reason,
                        # Carried through so this test keeps asserting what it is
                        # about — a dropped declaration, not an unowned entry.
                        **{
                            "owner": c.owner,
                            "review_by": c.review_by,
                            "issue": c.issue,
                            "gated_by": c.gated_by,
                            "known_gap": c.known_gap,
                        },
                    }
                    for c in stripped
                ],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--inventory", str(path)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "policy.ungated" in proc.stdout
    assert "All commits signed off" in proc.stdout
