"""Unit tests for scripts/enable_branch_protection.py (DIG-506).

The reason this script exists is that on a Free org the answer is "you cannot
have this feature", and the error says so in a way that reads like a permissions
problem: `Upgrade to GitHub Pro or make this repository public to enable this
feature.` Applied to `digithings-ai/twelve-x`, a private repo owned by a
one-seat Free org, that 403 cost an afternoon to diagnose against token scopes
and org settings that were both already correct. `digithings-ai/digithings` is
public in the *same* org under the *same* admin, and the identical ruleset call
succeeds there — plan and visibility are the only variables.

So two things need pinning, and they pull in opposite directions:

* The refusal must be a *diagnosis*, not a shrug. A preflight that fails closed
  with a named unblock action is the deliverable. `test_private_repo_on_a_free_plan_is_refused_before_any_write`
  is the test that would have saved that afternoon, so it asserts the absence of
  the write, not just the exit code.
* The refusal must not be a false negative. If the plan changes, or the repo is
  made public, or the API shape shifts, this must proceed — otherwise the script
  quietly becomes a no-op that still reports a diagnosis. Hence the plan-object
  test (reading `plan` as a string silently never matches, which would report
  every private repo as un-blockable) and the public-repo-passes test.

`gh` is stubbed on PATH throughout. An unstubbed `gh` here would PUT real branch
protection onto a real repository.

`allow_force_pushes` is worth its own test for a reason that has nothing to do
with plans: the API returns `{"enabled": false}`, which is truthy. Read with a
plain truth test it reports "allowed" on a branch that has force-pushes
*blocked* — the opposite of the guarantee, reported confidently.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.scripts.conftest import GhStub, gh_rule

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "enable_branch_protection.py"

EXIT_OK = 0
EXIT_OPERATIONAL = 1
EXIT_PLAN_BLOCKED = 3
EXIT_PERMISSION_BLOCKED = 4

PRO_403 = "Upgrade to GitHub Pro or make this repository public to enable this feature."


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("enable_branch_protection", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["enable_branch_protection"] = module
    spec.loader.exec_module(module)
    return module


ebp = _load()


def _repo_meta(*, private: bool, admin: bool = True) -> dict[str, Any]:
    return {"private": private, "permissions": {"admin": admin, "push": admin}}


def _org_plan(plan: str) -> dict[str, Any]:
    """The shape `GET /orgs/{org}` actually returns: `plan` is an object."""
    return {"login": "digithings-ai", "plan": {"name": plan, "seats": 0, "filled_seats": 1}}


def _run(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv],
        capture_output=True,
        text=True,
    )


def _preflight_stub(
    gh_stub: Any, *, private: bool, plan: str = "free", admin: bool = True
) -> GhStub:
    return gh_stub(
        gh_rule(r"^api repos/", stdout=_repo_meta(private=private, admin=admin)),
        gh_rule(r"^api orgs/", stdout=_org_plan(plan)),
    )


# --- the plan gate -------------------------------------------------------------


def test_the_org_plan_is_read_out_of_an_object_not_as_a_string(gh_stub: Any) -> None:
    """`plan` arrives as `{"name": "free", …}`.

    Compared against FREE_PLANS as a string it never matches, so every private
    repo reads as "not plan-blocked" and the diagnosis silently disappears — the
    script would then attempt the write and surface a raw 403, which is the
    behaviour it was written to replace.
    """
    _preflight_stub(gh_stub, private=True, plan="free")
    pf = ebp.preflight("digithings-ai/twelve-x")
    assert pf.plan == "free"
    assert pf.is_private is True
    assert pf.blocked_reason is not None
    assert not pf.can_apply


def test_an_unreadable_plan_does_not_block(gh_stub: Any) -> None:
    """A token without `admin:org` cannot read the plan.

    Guessing Free there would refuse a repo that could have been protected, so an
    unknown plan proceeds and lets the write settle it. Getting this backwards
    turns the script into a silent no-op.
    """
    gh_stub(
        gh_rule(r"^api repos/", stdout=_repo_meta(private=True)),
        gh_rule(r"^api orgs/", stderr="forbidden", exit_code=1),
    )
    pf = ebp.preflight("digithings-ai/twelve-x")
    assert pf.plan == "unknown"
    assert pf.can_apply


def test_private_repo_on_a_free_plan_is_refused_before_any_write(gh_stub: Any) -> None:
    """The twelve-x case, and the assertion that matters is the missing write.

    A preflight that prints the right diagnosis and then tries the PUT anyway
    would still end at the same 403, but it would have burned a call and, on a
    repo where the feature *was* available, would have applied something the
    operator was told they could not do.
    """
    stub = _preflight_stub(gh_stub, private=True, plan="free")
    stub.set_rules(
        gh_rule(r"^api repos/[^ ]+/[^/]+$", stdout=_repo_meta(private=True)),
        gh_rule(r"^api orgs/", stdout=_org_plan("free")),
        gh_rule(r"^api .*(protection|rulesets)$", stdout="{}", exit_code=1, stderr=PRO_403),
    )
    done = _run(
        "apply", "--repo", "digithings-ai/twelve-x", "--branch", "develop", "--check", "test"
    )
    assert done.returncode == EXIT_PLAN_BLOCKED
    assert "BLOCKED" in done.stdout
    assert "GitHub Pro" in done.stdout
    assert stub.matching("api repos/digithings-ai/twelve-x/branches/develop/protection PUT") == []
    assert not any("rulesets" in " ".join(c) for c in stub.calls)


def test_public_repo_on_a_free_plan_is_not_blocked(gh_stub: Any) -> None:
    """Protection is free on public repos, so the plan gate must not fire there.

    This is the `digithings-ai/digithings` case, and it is the guard against the
    script degrading into a permanent refusal: if the gate over-triggered, every
    repo would report "upgrade to Pro" no matter how accessible it already is.
    """
    _preflight_stub(gh_stub, private=False, plan="free")
    done = _run(
        "apply",
        "--repo",
        "digithings-ai/digithings",
        "--branch",
        "develop",
        "--check",
        "test",
        "--dry-run",
    )
    assert done.returncode == EXIT_OK, done.stderr
    assert "BLOCKED" not in done.stdout
    assert "visibility:  public" in done.stdout


def test_a_private_repo_on_pro_is_not_blocked(gh_stub: Any) -> None:
    _preflight_stub(gh_stub, private=True, plan="pro")
    done = _run(
        "apply",
        "--repo",
        "digithings-ai/twelve-x",
        "--branch",
        "develop",
        "--check",
        "test",
        "--dry-run",
    )
    assert done.returncode == EXIT_OK, done.stderr
    assert "BLOCKED" not in done.stdout


def test_a_non_admin_is_refused_with_the_permission_code(gh_stub: Any) -> None:
    _preflight_stub(gh_stub, private=True, plan="free", admin=False)
    done = _run("apply", "--repo", "o/r", "--branch", "develop", "--check", "test", "--dry-run")
    assert done.returncode == EXIT_PERMISSION_BLOCKED
    assert "not an admin" in done.stdout


def test_the_unblock_advice_names_a_billing_decision_not_a_config_tweak(gh_stub: Any) -> None:
    """The advice must not read as something the operator can just go do.

    Making a client repo public to dodge the paywall publishes the code and its
    history; the advice has to say that is never the agent's call, so nobody
    "unblocks" it under time pressure.
    """
    _preflight_stub(gh_stub, private=True, plan="free")
    done = _run("status", "--repo", "digithings-ai/twelve-x", "--branch", "develop")
    assert "billing decision" in done.stdout
    assert "never an agent's" in done.stdout
    assert "merge_queue.py" in done.stdout


def test_a_late_403_still_reports_the_plan_gate(gh_stub: Any) -> None:
    """Belt and braces: if the preflight passes but the write is refused, say so.

    The preflight is a prediction about the API; this is what happens when the
    prediction is wrong. Without this, the operator sees a bare 403 and is back to
    the afternoon of guessing.
    """
    stub = _preflight_stub(gh_stub, private=False, plan="free")
    stub.set_rules(
        gh_rule(r"^api repos/[^ /]+/[^ /]+$", stdout=_repo_meta(private=False)),
        gh_rule(r"^api orgs/", stdout=_org_plan("free")),
        # The write carries its method before the path (`api PUT repos/o/r/rulesets
        # --input -`), so the match has to tolerate it and must not anchor past the
        # trailing `--input -`.
        gh_rule(r"^api (PUT )?.*/rulesets", stdout=PRO_403, exit_code=1, stderr=PRO_403),
    )
    done = _run("apply", "--repo", "o/r", "--branch", "develop", "--check", "test")
    assert done.returncode == EXIT_PLAN_BLOCKED
    assert "REFUSED" in done.stdout
    assert "GitHub Pro" in done.stdout


# --- payload shape -------------------------------------------------------------


def test_the_ruleset_blocks_force_pushes_and_deletion() -> None:
    """Two of the CEO's four done-tests are exactly these two rules."""
    payload = ebp.ruleset_payload(
        "q",
        "develop",
        ["test"],
        1,
        strict=True,
        merge_queue=True,
        merge_method="squash",
        enforcement="active",
    )
    kinds = [r["type"] for r in payload["rules"]]
    assert "non_fast_forward" in kinds
    assert "deletion" in kinds


def test_the_ruleset_scopes_to_the_named_branch() -> None:
    """A ruleset that matched every branch would quietly protect `main` too."""
    payload = ebp.ruleset_payload(
        "q",
        "develop",
        ["test"],
        0,
        strict=True,
        merge_queue=False,
        merge_method="squash",
        enforcement="active",
    )
    assert payload["conditions"]["ref_name"]["include"] == ["refs/heads/develop"]


def test_status_checks_are_not_enforced_on_branch_creation() -> None:
    """Without this the ruleset blocks creating the branch in the first place.

    A brand-new branch has never reported a check, so a ruleset that enforces
    required checks on create makes the branch un-creatable.
    """
    payload = ebp.ruleset_payload(
        "q",
        "develop",
        ["test"],
        0,
        strict=True,
        merge_queue=False,
        merge_method="squash",
        enforcement="active",
    )
    rule = next(r for r in payload["rules"] if r["type"] == "required_status_checks")
    assert rule["parameters"]["do_not_enforce_on_create"] is True
    assert rule["parameters"]["required_status_checks"] == [{"context": "test"}]
    assert rule["parameters"]["strict_required_status_checks_policy"] is True


def test_the_merge_queue_group_is_allgreen() -> None:
    """HEADGREEN lets a green last commit carry a red earlier PR in the same group.

    That is precisely the "landed untested" outcome this whole change exists to
    stop, so the queue rule must not be configured in the mode that permits it.
    """
    payload = ebp.ruleset_payload(
        "q",
        "develop",
        ["test"],
        0,
        strict=True,
        merge_queue=True,
        merge_method="squash",
        enforcement="active",
    )
    rule = next(r for r in payload["rules"] if r["type"] == "merge_queue")
    assert rule["parameters"]["grouping_strategy"] == "ALLGREEN"
    assert rule["parameters"]["max_entries_to_merge"] == 1


def test_applying_with_no_required_check_is_refused(gh_stub: Any) -> None:
    """A branch with no required check looks protected and enforces nothing."""
    # Stubbed even though nothing should reach the API: the validation lives before
    # the preflight precisely so a bad invocation cannot be masked by a live lookup,
    # and a test that depends on that order must not be allowed to phone home.
    gh_stub(gh_rule(r"^api ", stdout="{}", exit_code=1, stderr="should not be called"))
    done = _run("apply", "--repo", "o/r", "--branch", "develop", "--dry-run")
    assert done.returncode == EXIT_OPERATIONAL
    assert "no --check" in done.stderr
    assert "enforces nothing" in done.stderr


def test_merge_queue_with_classic_mode_is_refused() -> None:
    """Classic branch protection has no merge-queue field, so the ask would be silently dropped."""
    done = _run(
        "apply",
        "--repo",
        "o/r",
        "--branch",
        "develop",
        "--check",
        "test",
        "--merge-queue",
        "--mode",
        "classic",
    )
    assert done.returncode == EXIT_OPERATIONAL
    assert "--mode ruleset" in done.stderr


def test_classic_payload_omits_the_review_block_when_zero_approvals() -> None:
    """`required_pull_request_reviews: null` is not the same as "no review required".

    Sending a review block with `required_approving_review_count: 0` is rejected by
    the API, so the key is only present when reviews are actually being demanded.
    """
    assert "required_pull_request_reviews" not in ebp.classic_payload(["test"], 0, strict=True)
    payload = ebp.classic_payload(["test"], 1, strict=True)
    assert payload["required_pull_request_reviews"]["required_approving_review_count"] == 1
    assert payload["required_pull_request_reviews"]["dismiss_stale_reviews"] is True


def test_classic_payload_keeps_admins_able_to_bypass() -> None:
    """`enforce_admins: false` is the documented emergency bypass, on purpose.

    docs/BRANCH_PROTECTION.md is explicit that an admin locked out of a hotfix is
    the worse outcome, and the merge queue refuses to pass `--admin` itself so the
    bypass stays a deliberate human act.
    """
    payload = ebp.classic_payload(["test"], 0, strict=True)
    assert payload["enforce_admins"] is False
    assert payload["allow_force_pushes"] is False
    assert payload["allow_deletions"] is False


# --- reading live state --------------------------------------------------------


def test_a_wrapped_disabled_toggle_reads_as_blocked_not_allowed() -> None:
    """The API returns `{"enabled": false}` — a truthy dict.

    Reported through a plain truth test it says force-pushes are *allowed* on a
    branch that has them blocked, which is a security claim stated backwards.
    """
    body = {"allow_force_pushes": {"enabled": False}, "allow_deletions": {"enabled": False}}
    assert ebp._enabled(body, "allow_force_pushes") is False
    assert ebp._enabled(body, "allow_deletions") is False


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"allow_force_pushes": {"enabled": True}}, True),
        ({"allow_force_pushes": {"enabled": False}}, False),
        ({"allow_force_pushes": False}, False),
        ({"allow_force_pushes": True}, True),
        ({}, False),
    ],
)
def test_toggles_read_correctly_in_both_shapes(body: dict[str, Any], expected: bool) -> None:
    assert ebp._enabled(body, "allow_force_pushes") is expected


def test_status_reports_a_protected_branch_accurately(gh_stub: Any) -> None:
    """End-to-end on the one repo that is protected: `digithings-ai/digithings`.

    This doubles as a check on the whole reading path — the live response has
    wrapped toggles, a strict required-checks block, and no review block at all.
    """
    protection = {
        "required_status_checks": {"strict": True, "contexts": ["Required checks passed"]},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
        "enforce_admins": {"enabled": False},
    }
    gh_stub(
        # The character classes exclude `/` on purpose. `[^ ]+` happily crosses a
        # path separator, so the repo-meta pattern would also swallow
        # `repos/o/r/rulesets` and answer it with the repo dict — which is how this
        # test once died iterating a dict's keys.
        gh_rule(r"^api repos/[^ /]+/[^ /]+$", stdout=_repo_meta(private=False)),
        gh_rule(r"^api orgs/", stdout=_org_plan("free")),
        gh_rule(r"/protection$", stdout=protection),
        gh_rule(
            r"/rulesets$",
            stdout=[{"name": "m", "target": "branch", "enforcement": "active"}],
        ),
    )
    done = _run("status", "--repo", "digithings-ai/digithings", "--branch", "develop")
    assert done.returncode == EXIT_OK, done.stderr
    assert "protection on develop: active" in done.stdout
    assert "force pushes:      blocked" in done.stdout
    assert "branch deletion:   blocked" in done.stdout
    assert "approving reviews: 0" in done.stdout
    # A protected branch must not be reported as unprotected.
    assert "protection is absent" not in done.stdout


def test_a_malformed_repo_argument_is_rejected() -> None:
    with pytest.raises(ebp.ProtectionError, match="owner/name"):
        ebp.preflight("not-a-repo")


def test_dry_run_prints_the_payload_and_writes_nothing(gh_stub: Any) -> None:
    stub = _preflight_stub(gh_stub, private=False, plan="free")
    done = _run(
        "apply",
        "--repo",
        "o/r",
        "--branch",
        "develop",
        "--check",
        "test",
        "--mode",
        "ruleset",
        "--merge-queue",
        "--dry-run",
    )
    assert done.returncode == EXIT_OK, done.stderr
    assert "nothing was changed" in done.stdout
    assert "merge_queue" in done.stdout
    assert not any("rulesets" in " ".join(c) for c in stub.calls)


def test_the_dry_run_payload_is_valid_json(gh_stub: Any) -> None:
    """Reviewable payloads are the point of --dry-run; an unparseable one is useless."""
    _preflight_stub(gh_stub, private=False, plan="free")
    done = _run(
        "apply",
        "--repo",
        "o/r",
        "--branch",
        "develop",
        "--check",
        "test",
        "--mode",
        "both",
        "--merge-queue",
        "--dry-run",
    )
    body = done.stdout.split("would PUT ", 1)[1]
    blocks = body.split("\n\n", 1)
    assert json.loads(blocks[0].split("(", 1)[1].split("):", 1)[1])
    assert json.loads(blocks[1].split("):", 1)[1].split("dry run")[0].strip())
