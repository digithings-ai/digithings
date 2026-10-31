"""Unit tests for scripts/check_required_policy_checks.py (DIG-1982, DIG-2237).

The guard that lived in ``ci.yml`` alone compared ``required-checks.needs`` to
the jobs in ``ci.yml`` — so it was structurally incapable of failing on any
policy check that lives in another workflow file. These tests pin the two
failure modes the replacement has to catch, and the two it must *not* raise on
the repository's correct current setup.

DIG-2237 hardened that guard after review found three checks that did not cover
the properties they were relied on for: ``types:`` and ``branches-ignore:`` were
never parsed (so a workflow that stops re-reporting on the merge commit looked
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
import shutil
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
    date. Nothing re-verifies the snapshot against the live gate on a clock —
    the guard compares the snapshot with the writer script that applies it, and
    the ``--live`` read against the inventory — so the literal above is a dated
    statement of what was true then, and a human runs the live read. See
    ``test_the_rejected_app_credential_design_stays_deleted``.
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
    """DoD: take `gitleaks-scan` out and the guard fails.

    The check still reports on every PR. Deleting its inventory entry does not
    stop it reporting — it only stops anything recording that it ought to be a
    gate. That is the DIG-1952 bug in its purest form: the check goes red and
    the merge proceeds.

    DIG-3683 note: this used `All commits signed off` as the example until the
    GHA DCO workflow was retired — DCO is now enforced by the `local-ci`
    required status check, so no entry here can own it.
    """
    inventory, tracked = guard.load_inventory(INVENTORY)
    assert "gitleaks-scan" in {c.context for c in inventory}
    stripped = [c for c in inventory if c.context != "gitleaks-scan"]

    findings = _run(stripped, tracked, guard.read_contexts_file(CONTEXTS))

    assert "policy.ungated" in _codes(findings)
    assert "gitleaks-scan" in _subjects(findings, "policy.ungated")


def test_declaring_a_check_required_that_the_gate_does_not_hold_fails() -> None:
    """The other direction of the same bug: the inventory says a check gates the
    merge and branch protection disagrees."""
    inventory, tracked = guard.load_inventory(INVENTORY)
    mutated = [
        dataclasses.replace(c, enforcement="required") if c.context == "gitleaks-scan" else c
        for c in inventory
    ]

    findings = _run(mutated, tracked, guard.read_contexts_file(CONTEXTS))

    assert "policy.missing-required" in _codes(findings)
    assert "gitleaks-scan" in _subjects(findings, "policy.missing-required")


def test_every_ungated_policy_check_is_reported() -> None:
    """The drift checks DIG-1952 names must all be visible. (DCO sign-off
    was a fifth until Chris dropped it entirely on 2026-10-15, DIG-3845, and the
    project-field coverage check went with ci-pr-hygiene.yml in the GHA exit.)"""
    inventory, _tracked = guard.load_inventory(INVENTORY)
    declared = {c.context: c for c in inventory}
    expected = {
        "gitleaks-scan",
        "Validate PR title",
        "Every commit reaching main was reviewed",
    }
    assert expected <= set(declared)
    assert "All commits signed off" not in declared
    assert "All agent-task issues in TSV with real phase and valid model" not in declared
    for context in expected:
        assert not declared[context].is_required, context
        assert declared[context].reason, f"{context} needs a reason"


def test_gitleaks_is_flagged_as_the_highest_value_ungated_check() -> None:
    """gitleaks-scan is secret scanning, and the brief says flag it hardest."""
    inventory, _tracked = guard.load_inventory(INVENTORY)
    gitleaks = next(c for c in inventory if c.context == "gitleaks-scan")
    assert gitleaks.enforcement == "advisory"
    assert "highest-value" in gitleaks.reason
    assert gitleaks.workflow == "security-gitleaks.yml"


# ── failure mode 1: a required context no PR-triggered workflow produces ─────


def test_requiring_gitleaks_without_a_path_filter_does_not_stall() -> None:
    """No stall once the workflow-level filter is gone.

    `security-gitleaks.yml` used to carry a workflow-level `paths-ignore` of
    `**.md` and `docs/**`, under which requiring `gitleaks-scan` hung
    docs-only PRs forever (failure mode 1). That filter was removed so the
    check reports on every PR: requiring the name now produces no stall
    finding. The stall logic itself stays pinned by
    `test_stall_rule_covers_a_workflow_level_paths_filter`, which feeds a
    synthetic filtered workflow rather than depending on this file's shape.
    """
    contexts = [*LIVE_CONTEXTS, "gitleaks-scan"]

    findings = _run(*guard.load_inventory(INVENTORY), contexts)

    assert "policy.stall" not in _codes(findings)
    facts = guard.read_workflow_facts(guard.WORKFLOWS_DIR / "security-gitleaks.yml", "develop")
    assert facts.path_filter is None


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
        + "    job: required-checks\n    enforcement: required\n    reason: r\n",
        "tracked_workflows: [ci.yml]\nchecks:\n  - context: a\n    workflow: ci.yml\n",
        "tracked_workflows: [ci.yml]\nchecks:\n  - context: a\n    workflow: ci.yml\n"
        + "    job: required-checks\n    enforcement: nonsense\n    reason: r\n",
        "tracked_workflows: [ci.yml]\nchecks:\n  - context: a\n    workflow: ci.yml\n"
        + "    job: required-checks\n    enforcement: required\n",  # no reason
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


# `types` — the GATE. For `pull_request`, `GITHUB_SHA` is the last merge commit on
# the PR merge branch and a required context has to report against that commit, so
# a workflow that never re-reports on `synchronize` stalls the PR forever while
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
    # The rationale the message has to carry: the commit a required context must
    # report against is the PR merge branch's merge commit, not the per-PR commit
    # the message used to name. Assert the corrected text and the removed text,
    # so a future edit cannot quietly put the false claim back.
    assert "GITHUB_SHA" in reason
    assert "merge commit" in reason
    assert "head SHA" not in reason
    assert "Waiting for status to be reported" in reason


def test_a_types_filter_missing_reopened_is_not_reachable(tmp_path: Path) -> None:
    """A-1 widening: the old gate only demanded `synchronize`, so
    `types: [opened, synchronize]` used to pass. Missing `reopened` must now
    fail, naming the missing type."""
    path = _synthetic_workflow(tmp_path, "t.yml", "    types: [opened, synchronize]\n")
    reachable, reason = guard.read_workflow_facts(path, "develop").reports_on_develop_pr("develop")
    assert not reachable
    assert "`reopened`" in reason
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


def test_an_unreadable_branches_ignore_filter_fails_closed(tmp_path: Path) -> None:
    """A filter nobody could read is a filter nobody can rule out, so the rule
    fails closed the same way an unreadable `types:` value does. Reading it as
    "absent" would call the check reachable on the strength of a value that was
    never understood."""
    path = _synthetic_workflow(tmp_path, "t.yml", "    branches-ignore: develop\n")
    reachable, reason = guard.read_workflow_facts(path, "develop").reports_on_develop_pr("develop")
    assert not reachable
    assert "unreadable" in reason


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
    most of the 58 untracked files are not policy surfaces."""
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
    path = root / "ci-pr-title.yml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "    types: [opened, edited, synchronize, reopened]",
            "    paths-ignore: ['**.md']\n    types: [opened, edited, synchronize, reopened]",
        ),
        encoding="utf-8",
    )
    inventory, tracked = guard.load_inventory(INVENTORY)
    findings = _run(inventory, tracked, LIVE_CONTEXTS, workflows_dir=root)
    assert "Validate PR title" in _subjects(findings, "policy.stall")


def test_a_known_gap_suppresses_reachability_only_while_the_entry_is_ungated() -> None:
    """The `known_gap:` mechanism, pinned on the one entry that carries a real
    gap.

    `Workflow secret references (PR reporter)` runs from
    `security-workflow-secret-refs.yml`, which is path-filtered at the workflow
    level on the workflow tree, the manifest and the script. So it reports on
    the PRs that touch those paths and on no others, and it can never be a
    required context: GitHub would block every other PR on a status that never
    arrives. That is exactly what `known_gap:` records — an accepted gap while
    the entry stays advisory. Promote it and the gap becomes a `policy.stall`
    again, which is the whole point: the acceptance expires at promotion."""
    inventory, tracked = guard.load_inventory(INVENTORY)
    reporter = next(c for c in inventory if c.context == "Workflow secret references (PR reporter)")
    assert reporter.known_gap, "the gap this workflow really has must be recorded"
    facts = guard.read_workflow_facts(
        guard.WORKFLOWS_DIR / "security-workflow-secret-refs.yml", "develop"
    )
    assert facts.path_filter is not None, "the gap is really there"

    assert _run(inventory, tracked, LIVE_CONTEXTS) == []

    promoted = _run(
        inventory, tracked, [*LIVE_CONTEXTS, "Workflow secret references (PR reporter)"]
    )
    stalls = [
        f
        for f in promoted
        if f.code == "policy.stall" and f.subject == "Workflow secret references (PR reporter)"
    ]
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


# The live gate may only be read by the one dispatch-only workflow, and the
# rejected credential design may never come back.


def test_the_rejected_app_credential_design_stays_deleted() -> None:
    """The GitHub App design was rejected on 2026-10-07: its manifest, its
    minting script and its tests were deleted by that same change. The
    credential the registry actually names is a fine-grained PAT
    (`POLICY_CHECK_READER_TOKEN`, docs/ops/policy-check-credential.md), and it
    needs no app id and no installation id.

    A job that reads the deleted design can never work: the minting script does
    not exist, and the secret it wanted was never provisioned. So no workflow
    may name any of it again.
    """
    banned = (
        "mint_policy_check_token",
        "POLICY_CHECK_APP_PRIVATE_KEY",
        "POLICY_CHECK_APP_ID",
        "POLICY_CHECK_INSTALLATION_ID",
    )
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        for name in banned:
            assert name not in text, f"{path.name} still uses the rejected design: {name}"
    assert not (REPO_ROOT / "scripts" / "mint_policy_check_token.py").exists()


#: The one file allowed to reach the live gate. It must stay dispatch-only:
#: the read needs a human-only credential, so it may not ride the PR path, and
#: it may not carry a schedule (tests/scripts/test_no_gha_schedules.py enforces
#: that globally, this test enforces the rest of the shape).
LIVE_WORKFLOW = "policy-gate-live.yml"


def test_only_the_dispatch_only_workflow_reads_the_live_gate() -> None:
    """DIG-5536 replaced the blocked state with one deliberate dispatch lane.

    Before this leaf nothing re-read the gate, and the gap was named in prose.
    Now exactly one workflow may run the read, and only on `workflow_dispatch`:
    it declares `environment: cron` so the PAT resolves, and it does not appear
    on `pull_request`, `push` or `schedule`. A second workflow reaching for the
    read — or the same one gaining a trigger — is how the credential gets in
    front of every merge, so that is a failure here rather than a review note.
    """
    readers: list[str] = []
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        # Either spelling reaches the read: the guard directly, or the wrapper
        # that owns the skip contract. Both count.
        if "check_required_policy_checks.py --live" in text or "policy_gate_live.py" in text:
            readers.append(path.name)
            doc = yaml.safe_load(text) or {}
            on = doc.get("on") if "on" in doc else doc.get(True)
            assert isinstance(on, dict), f"{path.name} has no readable `on:` block"
            assert set(on) == {"workflow_dispatch"}, (
                f"{path.name} must be dispatch-only; it declares {sorted(on)}. The live "
                "read carries a human-only credential and cannot sit on the merge path "
                "or on a clock"
            )
            jobs = doc.get("jobs") or {}
            gated = [
                name
                for name, job in jobs.items()
                if isinstance(job, dict) and job.get("environment") == "cron"
            ]
            assert gated, (
                f"{path.name} reads the PAT but declares no `environment: cron`; the "
                "secret is environment-scoped and would resolve to empty"
            )
    assert readers == [LIVE_WORKFLOW], (
        f"expected exactly {LIVE_WORKFLOW} to read the live gate, found {readers}"
    )

    cron = (REPO_ROOT / "apps" / "digithings-cron" / "src" / "jobs.ts").read_text(encoding="utf-8")
    # ci-pr-hygiene.yml and its held-off clock were deleted (GHA exit ledger), so
    # there is no other lane the live read could ride.
    assert not (WORKFLOWS_DIR / "ci-pr-hygiene.yml").exists()
    assert 'wd("ci-pr-hygiene"' not in cron, "the deleted workflow's clock must stay gone"


def test_the_context_set_and_enforcement_values_are_unchanged_from_dig_1982() -> None:
    """DoD "exits 0 with the inventory unchanged" means the policy decisions are
    unchanged: same contexts, same workflows, same enforcement. Only the metadata
    this leaf adds (owner, issue, gated_by, known_gap) is new.

    The census is develop's current inventory, not the one DIG-1982 first
    wrote: the base moved on while this leaf sat on the older
    `feat/dig-1982-policy-drift-guard` tip, and it dropped DCO sign-off
    entirely (DIG-3845), added the ci.yml lanes below, and added the
    path-filtered PR reporter. Reconciling the base's evolved files is the
    rebase-with-resolution this leaf owes the branch — the policy decisions in
    it are still develop's, and this leaf adds only metadata to them."""
    inventory, tracked = guard.load_inventory(INVENTORY)
    assert [(c.context, c.workflow, c.job, c.enforcement) for c in inventory] == [
        ("Required checks passed", "ci.yml", "required-checks", "required"),
        ("doc-links + agents-init", "ci-docs.yml", "docs-and-agents-init", "required"),
        ("mypy — digibase + digikey", "ci-type-check.yml", "mypy", "required"),
        ("gitleaks-scan", "security-gitleaks.yml", "scan", "advisory"),
        ("Validate PR title", "ci-pr-title.yml", "lint-pr-title", "advisory"),
        (
            "Every commit reaching main was reviewed",
            "ci-review-coverage.yml",
            "review-coverage",
            "other-branch",
        ),
        ("Frontend canon guard", "ci.yml", "frontend-canon", "advisory"),
        ("actionlint", "ci.yml", "actionlint", "advisory"),
        ("GLOOMBERB deployed-config guard", "ci.yml", "gloomberb-ci-guard", "advisory"),
        ("Vendor-content gate", "ci.yml", "vendor-content-gate", "advisory"),
        ("Example-credentials guard", "ci.yml", "example-credentials-guard", "advisory"),
        ("Plaintext credential guard", "ci.yml", "plaintext-credential-guard", "advisory"),
        (
            "R0 client-literal baseline growth guard",
            "ci.yml",
            "r0-client-literals-baseline-growth",
            "advisory",
        ),
        # DIG-2887 S0: the Supabase exit's usage freeze, same shape as R0 growth.
        (
            "Supabase usage freeze (exit in progress)",
            "ci.yml",
            "supabase-freeze",
            "advisory",
        ),
        ("Workflow secret references", "ci.yml", "workflow-secret-refs", "advisory"),
        (
            "Workflow secret references (PR reporter)",
            "security-workflow-secret-refs.yml",
            "check",
            "advisory",
        ),
        ("wrangler deploy --dry-run", "ci.yml", "worker-build", "advisory"),
    ]
    assert sorted(tracked) == [
        "ci-docs.yml",
        "ci-pr-title.yml",
        "ci-review-coverage.yml",
        "ci-type-check.yml",
        "ci.yml",
        "security-gitleaks.yml",
        "security-workflow-secret-refs.yml",
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
    # The machine-readable verdict is the contract `policy_gate_live.py` needs
    # to tell a real drift (exit 1) from a crashed guard (also exit 1).
    assert f"{guard.VERDICT_PREFIX} agree" in proc.stdout


def test_script_exits_nonzero_when_the_inventory_is_mutated(tmp_path: Path) -> None:
    """The DoD test, run through the real CLI rather than only in-process."""
    inventory, tracked = guard.load_inventory(INVENTORY)
    stripped = [c for c in inventory if c.context != "gitleaks-scan"]
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

    assert "gitleaks-scan" in proc.stdout


# ── the writer and the snapshot are coupled (DIG-2223) ───────────────────────
#
# Before this, develop's required contexts had two committed sources: the
# snapshot the guard reads, and a hardcoded list inside the writer. Nothing
# compared them. `gitleaks-scan` sat in the second one for six days — not live,
# declared `advisory` in the inventory, and one command away from becoming a gate
# enforced against nothing. These pin the fix, and each one fails if the coupling
# arm is deleted.


def test_writer_and_snapshot_agree_on_this_repository() -> None:
    """The positive case, read off the real script rather than a list held here.

    Executing the writer is the point. Diffing two committed files would still
    pass if the writer had grown a payload of its own that happened to match
    today, which is the state this issue was filed against.
    """
    snapshot = guard.read_contexts_file(CONTEXTS)
    emitted = guard.read_writer_contexts()
    assert emitted == snapshot
    assert guard.check_writer_coupling(snapshot, emitted) == []


def test_the_writer_body_names_no_context_literal() -> None:
    """It must hold no list of its own; the snapshot is the only source.

    Scanned over the executable body only. The header quotes context names in
    prose ('gitleaks-scan left this file on 2026-10-14'), so a whole-file scan
    would be measuring the documentation rather than the code — and a guard that
    fires on its own documentation is a guard nobody leaves switched on.
    """
    text = guard.WRITER_SCRIPT.read_text(encoding="utf-8")
    marker = "set -euo pipefail"
    assert marker in text, "the writer's body marker moved; re-point this scan"
    body = text[text.index(marker) :]
    for context in guard.read_contexts_file(CONTEXTS) + ["gitleaks-scan"]:
        assert f'"{context}"' not in body, f"the writer body hardcodes {context!r}"


def test_a_writer_that_would_apply_an_undeclared_context_is_caught(tmp_path: Path) -> None:
    """A list bolted onto a writer is caught by running it, not by diffing files."""
    stub = tmp_path / "set-branch-protection.sh"
    contexts = guard.read_contexts_file(CONTEXTS) + ["gitleaks-scan"]
    stub.write_text(
        "#!/usr/bin/env bash\n"
        "# a writer that names contexts itself: the shape this leaf removes\n"
        "printf '%s\\n' " + " ".join(f'"{c}"' for c in contexts) + "\n",
        encoding="utf-8",
    )
    findings = guard.check_writer_coupling(
        guard.read_contexts_file(CONTEXTS), guard.read_writer_contexts(stub)
    )
    assert _codes(findings) == {"writer.snapshot-drift"}
    message = str(findings[0])
    assert "gitleaks-scan" in message
    assert "snapshot" in message


def test_a_writer_that_would_drop_a_declared_context_is_caught() -> None:
    """Drift the other way: a gate that is declared and then never enforced."""
    snapshot = guard.read_contexts_file(CONTEXTS)
    assert len(snapshot) > 1, "need at least two contexts for the drop to mean anything"
    dropped = [c for c in guard.read_writer_contexts() if c != snapshot[0]]
    findings = guard.check_writer_coupling(snapshot, dropped)
    assert _codes(findings) == {"writer.snapshot-drift"}
    message = str(findings[0])
    assert "would not apply" in message
    assert snapshot[0] in message


def test_a_writer_that_prints_nothing_raises_rather_than_passing(tmp_path: Path) -> None:
    """An unreadable writer must fail the guard, not read as 'in sync'."""
    stub = tmp_path / "silent.sh"
    stub.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    with pytest.raises(guard.GuardError):
        guard.read_writer_contexts(stub)


def test_a_missing_writer_raises(tmp_path: Path) -> None:
    """No writer means no owner. Silence here would be a green guard."""
    with pytest.raises(guard.GuardError):
        guard.read_writer_contexts(tmp_path / "absent.sh")


def test_a_failing_writer_raises_naming_its_own_stderr(tmp_path: Path) -> None:
    stub = tmp_path / "broken.sh"
    stub.write_text(
        '#!/usr/bin/env bash\necho "ERROR: snapshot is missing." >&2\nexit 1\n',
        encoding="utf-8",
    )
    with pytest.raises(guard.GuardError, match="snapshot is missing"):
        guard.read_writer_contexts(stub)


def test_the_real_writer_refuses_to_apply_without_the_snapshot(tmp_path: Path) -> None:
    """Run against a copy of the real script, so this is the wrapper's own behaviour.

    It matters because the wrapper's alternative to reading the snapshot is a
    baked-in list, and a fallback that quietly still works is exactly how a
    snapshot could go missing with nothing noticing.
    """
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / ".github").mkdir(parents=True)
    name = guard.WRITER_SCRIPT.name
    shutil.copy(guard.WRITER_SCRIPT, repo / "scripts" / name)
    shutil.copy(guard.REPO_ROOT / "scripts" / "enable_branch_protection.py", repo / "scripts")

    without = subprocess.run(
        ["bash", str(repo / "scripts" / name), "--print-contexts"],
        capture_output=True,
        text=True,
    )
    assert without.returncode != 0, without.stdout
    assert "required-contexts.txt" in without.stderr

    # Control: the same command on a tree that HAS the snapshot emits, so the
    # refusal above is the snapshot's absence and not bash failing to run at all.
    shutil.copy(guard.CONTEXTS_PATH, repo / ".github" / "required-contexts.txt")
    with_snapshot = subprocess.run(
        ["bash", str(repo / "scripts" / name), "--print-contexts"],
        capture_output=True,
        text=True,
    )
    assert with_snapshot.returncode == 0, with_snapshot.stderr
    assert with_snapshot.stdout.strip().splitlines() == guard.read_contexts_file(CONTEXTS)


def test_the_cli_fails_when_the_writer_and_snapshot_drift(tmp_path: Path) -> None:
    """The DoD test for the coupling, run through the real CLI.

    A mutated snapshot plus a writer stub is the only way to drive the drift
    through main(), since the real writer reads the real snapshot by path. The
    finding text is asserted so this cannot pass by exiting non-zero for an
    unrelated reason.
    """
    mutated = tmp_path / "required-contexts.txt"
    mutated.write_text(
        "# a snapshot with one gate too many\n"
        + "".join(f"{c}\n" for c in guard.read_contexts_file(CONTEXTS) + ["gitleaks-scan"]),
        encoding="utf-8",
    )
    # --contexts redirects the snapshot the writer coupling is checked against.
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--contexts", str(mutated)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "writer.snapshot-drift" in proc.stdout


# ── DIG-2237 C-1: review horizons on the issue-alone advisories ───────────────

#: The advisory entries whose only support is `issue:` (DIG-2098 rev 8,
#: correction 1). There were three until the project-field coverage entry went
#: with ci-pr-hygiene.yml (GHA exit ledger). The ci.yml lanes carry `gated_by:` and the PR reporter
#: carries `known_gap:`, so neither class takes a date. `gitleaks-scan` used to
#: carry a `known_gap:` too, and stopped when the workflow-level
#: `paths-ignore` was removed upstream (#5318) — the gap went with the filter,
#: so the entry is issue-alone now and takes a date like the others.
REVIEW_BY_CONTEXTS = [
    "gitleaks-scan",
    "Validate PR title",
]


def test_exactly_the_issue_alone_advisories_carry_review_by() -> None:
    """Correction 1 as a pin: the dates land on exactly these entries."""
    inventory, _tracked = guard.load_inventory(INVENTORY)
    dated = {c.context: c.review_by for c in inventory if c.review_by}
    assert sorted(dated) == sorted(REVIEW_BY_CONTEXTS), dated
    assert set(dated.values()) == {"2027-04-13"}, dated
    by_context = {c.context: c for c in inventory}
    assert by_context["gitleaks-scan"].issue == "DIG-1952"
    assert by_context["gitleaks-scan"].known_gap is None
    assert by_context["Frontend canon guard"].review_by is None
    assert by_context["actionlint"].review_by is None
    assert by_context["Workflow secret references (PR reporter)"].review_by is None


def test_a_past_review_by_is_a_warning_not_a_finding() -> None:
    """Staged rollout: staleness surfaces as a `::warning::` line while the
    guard stays green. Removing the warning emission must fail this test."""
    inventory, tracked = guard.load_inventory(INVENTORY)
    assert _run(inventory, tracked, LIVE_CONTEXTS) == []
    aged = [
        dataclasses.replace(c, review_by="2000-01-01") if c.context == "Validate PR title" else c
        for c in inventory
    ]
    assert guard.stale_advisories(aged) != []
    assert _run(aged, tracked, LIVE_CONTEXTS) == []
    text = guard.report([], aged, LIVE_CONTEXTS)
    assert "::warning::[policy.stale-advisory]" in text, text
    assert "Validate PR title" in text


def test_a_future_review_by_is_silent() -> None:
    """A horizon that has not passed changes nothing in the output."""
    inventory, _tracked = guard.load_inventory(INVENTORY)
    assert guard.stale_advisories(inventory) == []
    text = guard.report([], inventory, LIVE_CONTEXTS)
    assert "policy.stale-advisory" not in text, text
    assert "policy gate agrees" in text


def test_a_malformed_review_by_is_rejected_at_load(tmp_path: Path) -> None:
    """A horizon nobody can parse would read as "not yet due" forever."""
    path = tmp_path / "policy-checks.yml"
    path.write_text(
        "tracked_workflows: [ci.yml]\nchecks:\n  - context: b\n    workflow: ci.yml\n"
        "    job: required-checks\n    enforcement: advisory\n    reason: r\n"
        "    owner: DevOps\n    review_by: soon\n",
        encoding="utf-8",
    )
    with pytest.raises(guard.GuardError, match="review_by"):
        guard.load_inventory(path)
