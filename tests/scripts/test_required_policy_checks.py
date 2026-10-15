"""Unit tests for scripts/check_required_policy_checks.py (DIG-1982).

The guard that lived in ``ci.yml`` alone compared ``required-checks.needs`` to
the jobs in ``ci.yml`` — so it was structurally incapable of failing on any
policy check that lives in another workflow file. These tests pin the two
failure modes the replacement has to catch, and the two it must *not* raise on
the repository's correct current setup.

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


def _real_facts() -> dict[str, Any]:
    """Parse every tracked workflow from the actual repository."""
    _inventory, tracked = guard.load_inventory(INVENTORY)
    return {
        name: guard.read_workflow_facts(guard.WORKFLOWS_DIR / name, "develop") for name in tracked
    }


def _run(inventory: list[Any], tracked: list[str], contexts: list[str], branch: str = "develop"):
    return guard.reconcile(inventory, tracked, _real_facts(), contexts, branch)


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


def test_committed_contexts_match_the_live_gate() -> None:
    """The snapshot is the guard's CI input, so it has to equal reality. If this
    fails, someone changed branch protection without updating the file — which
    is precisely the drift class this leaf exists to catch."""
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
    facts = guard.read_workflow_facts(
        guard.WORKFLOWS_DIR / "security-gitleaks.yml", "develop"
    )
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
