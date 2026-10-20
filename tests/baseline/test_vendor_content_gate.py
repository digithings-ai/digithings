"""Baseline tests for scripts/check_vendor_content.py (DIG-2583, lane S of DIG-1415).

These run the **real script** as a subprocess against a synthetic git repository
built in ``tmp_path``. Nothing here imports the gate's internals to assert on
them: the gate's behaviour is its exit code and its printed report, so that is
what is tested. A gate tested through its own helpers can pass while the script
an operator runs fails.

Three properties are load-bearing and each has a named negative control:

* **seen-pass** — a clean tree exits 0, and the PR #5157 redacted shape is clean.
* **seen-fail** — one line of method-shaped content exits 1, and the report names
  the path, the line and the owning rule.
* **fail closed** — a missing allowlist, an unparseable allowlist, an allowlist
  that approves a method rule, and an unresolvable base ref all exit 2. A gate
  that reports "clean" when it could not run is worse than no gate.

Each fixture asserts the harness *can* fail before asserting it passed: a
``{tmp}/repo`` whose scan is vacuous would make every assertion below meaningless.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/check_vendor_content.py"
ALLOWLIST = REPO_ROOT / "scripts/vendor_content_allowlist.json"
GIT = shutil.which("git")

pytestmark = pytest.mark.baseline

if GIT is None:  # pragma: no cover - a dev box with no git cannot run this gate
    pytest.skip("git is not installed; the vendor-content gate needs it", allow_module_level=True)


# The full recipe, verbatim in shape. It is the content Security's rule 3 calls
# "an instruction a reader with nothing else could execute".
RECIPE = """# Ops note

The Gloomberb session is acquired like this.

## Extract the session cookie

1. Signed in at https://term.gloom.sh/, open the browser devtools.
2. Go to Application/Storage -> Cookies -> term.gloom.sh.
3. Copy the value of __Secure-gloomberb.session_token.
"""

# The shape PR #5157 replaces it with: mechanism named, steps absent, every
# operational fact kept. If the gate fires on this it is flagging the compliant
# form, which is the one thing it must not do.
REDACTED_SHAPE = """# Ops note

## Redactions (2026-10-05, DIG-1194)

1. ~~The acquisition steps were removed from this plan on 2026-10-05.~~
   The mechanism was a human operator's own sign-in at the vendor's site, then
   reading the resulting credential out of a named browser storage slot. The
   acquisition procedure is not published in this repo. The upstream names are
   pinned at `client.py:403-407`. Show only `GLOOMBERB_SESSION_COOKIE=<cookie-value>`.
"""

# One rule per fixture, deliberately. `PRIMEMARKET_USERNAME` trips V1 *and* V4
# (the brand-word pattern matches the prefix), so a fixture using it would fail
# for two rules and could not tell which one an allowlist entry was covering.
ENV_NAME_ONLY = "The stage id PMT_RETAIL_BOOK selects the retail book stage.\n"
ENDPOINT_ONLY = "Probe https://api.gloom.sh/health for the endpoint inventory.\n"

# The acquisition act named, with no click path and no instruction to copy. This
# trips M5 alone, so a pending entry for M5 is the only thing under test.
SESSION_STEPS = (
    "## Extract the session cookie\n"
    "\n"
    "The Gloomberb operator signs in by hand.\n"
)


def _git(*args: str, cwd: Path) -> str:
    proc = subprocess.run(
        [GIT, *args], cwd=cwd, capture_output=True, text=True, errors="replace"
    )
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"
    return proc.stdout


def _write_allowlist(repo: Path, *, approved: list[dict] | None = None,
                     pending: list[dict] | None = None, raw: str | None = None) -> None:
    path = repo / "scripts" / "vendor_content_allowlist.json"
    if raw is not None:
        path.write_text(raw, encoding="utf-8")
        return
    path.write_text(
        json.dumps({"schema_version": 1, "approved": approved or [], "pending": pending or []},
                   indent=2),
        encoding="utf-8",
    )


def _make_repo(tmp_path: Path) -> Path:
    """A synthetic repo with the gate installed and one clean commit on `main`."""
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "docs").mkdir()
    shutil.copy(SCRIPT, repo / "scripts/check_vendor_content.py")
    _write_allowlist(repo)
    (repo / "docs/ops.md").write_text("# Ops\n\nNothing to see.\n", encoding="utf-8")
    subprocess.run([GIT, "init", "-b", "main", str(repo)], check=True, capture_output=True)
    _git("add", "-A", cwd=repo)
    _git("-c", "user.email=t@example.invalid", "-c", "user.name=t",
         "commit", "-m", "base", cwd=repo)
    _git("checkout", "-b", "feature", cwd=repo)
    return repo


def _land_on_main(repo: Path, rel: str, body: str, message: str) -> None:
    """Commit ``body`` on ``main``, then branch, so it is NOT a new occurrence."""
    _stage(repo, rel, body)
    _git("checkout", "main", cwd=repo)
    _git("-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-m", message, cwd=repo)
    _git("checkout", "-b", "feature-after-base", cwd=repo)


def _run(repo: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(repo / "scripts/check_vendor_content.py"),
         "--base-ref", "main", *extra],
        cwd=repo, capture_output=True, text=True, errors="replace",
    )


def _stage(repo: Path, rel: str, body: str) -> None:
    """Write a file and ``git add`` it.

    The gate enumerates with ``git ls-files``, which reads the **index**. A file
    that was written but never added is invisible to it, so an un-staged fixture
    would make every assertion below pass for the wrong reason.
    """
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    _git("add", rel, cwd=repo)


# --------------------------------------------------------------------------
# seen-pass
# --------------------------------------------------------------------------


def test_clean_tree_exits_zero(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    proc = _run(repo)
    assert proc.returncode == 0, proc.stdout
    assert "0 failing" in proc.stdout


def test_redacted_shape_is_not_a_finding(tmp_path: Path) -> None:
    """Security's approved redaction shape must not fire (DIG-1418 rule 3)."""
    repo = _make_repo(tmp_path)
    _stage(repo, "docs/session.md", REDACTED_SHAPE)
    proc = _run(repo)
    assert proc.returncode == 0, proc.stdout
    assert "FAIL" not in proc.stdout


def test_vendor_identifier_present_at_base_is_not_new(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _land_on_main(repo, "docs/vendor.md", ENV_NAME_ONLY, "vendor note lands on main")
    proc = _run(repo)
    assert proc.returncode == 0, proc.stdout


def test_approved_vendor_entry_does_not_fail(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _write_allowlist(repo, approved=[{
        "rule": "V1", "path": "docs/vendor.md", "symbol": "PMT_",
        "owner": "Security b14d7a18 + Counsel 0e57e884", "ticket": "DIG-1418 rule 2",
        "reason": "our own stage id; rule 2 keeps our own names",
    }])
    _stage(repo, "docs/vendor.md", ENV_NAME_ONLY)
    proc = _run(repo)
    assert proc.returncode == 0, proc.stdout
    assert "ALLOWLISTED" in proc.stdout
    assert "b14d7a18" in proc.stdout, "an allowlisted hit must name its approver"


# --------------------------------------------------------------------------
# seen-fail
# --------------------------------------------------------------------------


def test_method_shape_fails_with_path_line_and_rule(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _stage(repo, "docs/ops/session.md", RECIPE)
    proc = _run(repo)
    assert proc.returncode == 1, proc.stdout
    assert "docs/ops/session.md:5" in proc.stdout, proc.stdout
    assert "[M5 session-extraction-prose]" in proc.stdout, proc.stdout
    assert "[M2 devtools-to-storage-steps]" in proc.stdout, proc.stdout
    assert "[M3 application-storage-navigation]" in proc.stdout, proc.stdout


def test_method_shape_is_not_grandfathered_by_the_baseline(tmp_path: Path) -> None:
    """The recipe landing on `main` does not make it acceptable on a branch."""
    repo = _make_repo(tmp_path)
    _land_on_main(repo, "docs/ops/session.md", RECIPE, "recipe lands on main")
    proc = _run(repo)
    assert proc.returncode == 1, proc.stdout
    assert "M5" in proc.stdout


def test_new_vendor_identifier_since_base_fails(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _stage(repo, "docs/vendor.md", ENV_NAME_ONLY)
    proc = _run(repo)
    assert proc.returncode == 1, proc.stdout
    assert "docs/vendor.md:1" in proc.stdout, proc.stdout
    assert "[V1 vendor-session-env-names]" in proc.stdout, proc.stdout


def test_added_line_beside_a_baselined_one_fails(tmp_path: Path) -> None:
    """Newness is per line, so editing one line into a clean file is caught."""
    repo = _make_repo(tmp_path)
    _land_on_main(repo, "docs/vendor.md", ENDPOINT_ONLY, "endpoint note lands on main")
    _stage(repo, "docs/vendor.md", ENDPOINT_ONLY + "Probe https://api.gloom.sh/quotes too.\n")
    proc = _run(repo)
    assert proc.returncode == 1, proc.stdout
    assert re.search(r"^  docs/vendor\.md:2  FAIL", proc.stdout, re.M), proc.stdout
    assert not re.search(r"^  docs/vendor\.md:1  FAIL", proc.stdout, re.M), proc.stdout


def test_first_party_ordinary_code_is_not_a_finding(tmp_path: Path) -> None:
    """`localStorage.getItem('theme')` and "Dev tool" are first-party, not a recipe."""
    repo = _make_repo(tmp_path)
    _stage(repo, "web/theme.ts", (
        "export const theme = localStorage.getItem('theme');\n"
        "const devToolLabel = 'Dev tool';\n"
    ))
    proc = _run(repo)
    assert proc.returncode == 0, proc.stdout


# --------------------------------------------------------------------------
# fail closed
# --------------------------------------------------------------------------


def test_missing_allowlist_exits_two(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    (repo / "scripts/vendor_content_allowlist.json").unlink()
    proc = _run(repo)
    assert proc.returncode == 2, proc.stdout
    assert "FAIL (tool error)" in proc.stdout


def test_unparseable_allowlist_exits_two(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _write_allowlist(repo, raw="{not json")
    proc = _run(repo)
    assert proc.returncode == 2, proc.stdout
    assert "FAIL (tool error)" in proc.stdout


def test_wrong_schema_version_exits_two(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _write_allowlist(repo, raw=json.dumps({"schema_version": 2, "approved": [], "pending": []}))
    proc = _run(repo)
    assert proc.returncode == 2, proc.stdout


def test_approved_entry_naming_a_method_rule_exits_two(tmp_path: Path) -> None:
    """The brief's hard rule: exceptions only for vendor identifiers, never for methods."""
    repo = _make_repo(tmp_path)
    _write_allowlist(repo, approved=[{
        "rule": "M2", "path": "docs/ops/session.md", "symbol": "devtools",
        "owner": "someone", "ticket": "DIG-9999", "reason": "we want it",
    }])
    _stage(repo, "docs/ops/session.md", RECIPE)
    proc = _run(repo)
    assert proc.returncode == 2, proc.stdout
    assert "M2" in proc.stdout


def test_entry_missing_an_owner_exits_two(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _write_allowlist(repo, approved=[{
        "rule": "V1", "path": "docs/vendor.md", "symbol": "PRIMEMARKET_",
        "ticket": "DIG-1418", "reason": "no owner named",
    }])
    proc = _run(repo)
    assert proc.returncode == 2, proc.stdout
    assert "owner" in proc.stdout


def test_unresolvable_base_ref_exits_two(tmp_path: Path) -> None:
    """A shallow or single-commit checkout cannot baseline 'new'; it must not pass."""
    repo = _make_repo(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(repo / "scripts/check_vendor_content.py"),
         "--base-ref", "no-such-ref"],
        cwd=repo, capture_output=True, text=True, errors="replace")
    assert proc.returncode == 2, proc.stdout
    assert "FAIL (tool error)" in proc.stdout


# --------------------------------------------------------------------------
# the pending tier and the real allowlist
# --------------------------------------------------------------------------


# The vendor word sits 8 lines above the hit, inside the same `#` section. The
# tight window alone (hit-3 .. hit+2) cannot see it; the section scope must.
RECIPE_IN_A_SECTION = """# Gloomberb session

The Gloomberb session is obtained by hand at the vendor site and is stored nowhere else.

Filler one.

Filler two.

Filler three.

Filler four.

The operator then extracts the session token by hand.
"""

# The counter. Same shape, but the vendor section is closed off by a heading, so
# nothing in the recipe's own section names the vendor. One vendor mention
# elsewhere in the file must not license a method hit here.
RECIPE_WITH_NO_VENDOR_SECTION = """# Gloomberb session

The Gloomberb session is obtained by hand at the vendor site.

## Dashboard notes

The dashboard reads localStorage.getItem('theme') on load.

Filler one.

Filler two.

Filler three.

Filler four.

The operator then extracts the session token by hand.
"""


def test_vendor_mention_outside_the_line_window_still_counts(tmp_path: Path) -> None:
    """The vendor word is >3 lines above the hit, in the same markdown section.

    Pinned because the tight window alone missed exactly this: a recipe written
    as "see the note above" is still a recipe.
    """
    repo = _make_repo(tmp_path)
    _stage(repo, "docs/ops/session.md", RECIPE_IN_A_SECTION)
    proc = _run(repo)
    assert proc.returncode == 1, proc.stdout
    assert "[M5 session-extraction-prose]" in proc.stdout, proc.stdout


def test_a_vendor_section_does_not_license_an_unrelated_section(tmp_path: Path) -> None:
    """The counter to the test above: scope widens to a section, never the file."""
    repo = _make_repo(tmp_path)
    _stage(repo, "docs/ops/session.md", RECIPE_WITH_NO_VENDOR_SECTION)
    proc = _run(repo)
    assert proc.returncode == 0, proc.stdout
    assert "FAIL" not in proc.stdout


def test_pending_entry_does_not_fail_but_prints_not_approved(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _write_allowlist(repo, pending=[{
        "rule": "M5", "path": "docs/ops/session.md", "match": "Extract the session",
        "owner": "Security b14d7a18", "ticket": "DIG-1434 / PR #5157",
        "reason": "removed by PR #5157",
    }])
    _stage(repo, "docs/ops/session.md", SESSION_STEPS)
    proc = _run(repo)
    assert proc.returncode == 0, proc.stdout
    assert "allowlisted: NO" in proc.stdout
    assert "DIG-1434" in proc.stdout


def test_pending_entry_retires_when_its_content_goes(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _write_allowlist(repo, pending=[{
        "rule": "M5", "path": "docs/ops/session.md", "match": "Extract the session",
        "owner": "Security b14d7a18", "ticket": "DIG-1434 / PR #5157",
        "reason": "removed by PR #5157",
    }])
    _stage(repo, "docs/ops/session.md", "# Ops\n\nNothing to see.\n")
    proc = _run(repo)
    assert proc.returncode == 0, proc.stdout
    assert "RETIRED M5" in proc.stdout, proc.stdout


def test_repository_allowlist_loads_and_approves_no_method_rule() -> None:
    """The shipped allowlist, reviewed like code."""
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        import importlib

        spec = importlib.util.spec_from_file_location("cvc_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        loaded = module.load_allowlist(ALLOWLIST)
    finally:
        sys.path.remove(str(SCRIPT.parent))

    method_ids = {r.id for r in module.METHOD_RULES}
    assert not [e for e in loaded.approved if e["rule"] in method_ids]
    assert loaded.approved, "DIG-1418 rule 2 keeps two things; both must be recorded"
    for entry in loaded.approved:
        assert "Security" in entry["owner"], entry
        assert "Counsel" in entry["owner"], entry
        assert entry["ticket"], entry
        assert entry["reason"], entry
    assert loaded.pending, "pending is the queue of decisions nobody has taken yet"
    for entry in loaded.pending:
        assert entry["match"], entry
        assert entry["owner"] and entry["ticket"], entry
# --------------------------------------------------------------------------
# pending is report-only, including when its recorded text drifts
# --------------------------------------------------------------------------
#
# Board decision 2026-10-09 (DIG-2583): a pending entry is content nobody has
# ruled on, so it must never block a PR. It used to be suppressed only while its
# `match` needle was a substring of the text the rule matched, so a cosmetic
# reword by an unrelated PR ended the suppression and the recorded finding became
# a hard FAIL. The fix scopes suppression to rule + path and reports a stale
# entry as `pending-drift` instead of blocking on it.
#
# The teeth are the other half and are pinned here too: a hit with NO pending
# entry for that rule at that path is new content and still fails.

#: The reword. M5 matches `\bextract(?:s|ed|ing)?\s+the\s+(?:session|cookie|...)s?\b`,
#: so "Extracting the session cookie" still trips it — but the recorded needle
#: "Extract the session" is no longer a substring of the matched text. That is the
#: whole scenario: a docs edit no one would think twice about, same rule, and the
#: old suppression ends. Derived by substitution rather than retyped, so it cannot
#: silently stop being a reword if the fixture above it changes.
DRIFTED_STEPS = SESSION_STEPS.replace("Extract the session cookie", "Extracting the session cookie")

DRIFT_ENTRY = {
    "rule": "M5",
    "path": "docs/ops/session.md",
    "match": "Extract the session",
    "owner": "Security b14d7a18",
    "ticket": "DIG-1434 / PR #5157",
    "reason": "removed by PR #5157",
}


def _drift_fixture(tmp_path: Path) -> Path:
    """A repo whose pending entry for M5 has gone stale against the content."""
    assert "Extract the session" not in DRIFTED_STEPS, (
        "the drifted fixture must NOT contain the recorded needle, or the drift "
        "tests below would pass without ever exercising drift"
    )
    assert "Extract the session" in SESSION_STEPS, (
        "the un-drifted fixture must contain the recorded needle, or test 1 "
        "would be measuring drift and calling it a match"
    )
    repo = _make_repo(tmp_path)
    _write_allowlist(repo, pending=[dict(DRIFT_ENTRY)])
    _stage(repo, "docs/ops/session.md", DRIFTED_STEPS)
    return repo


def test_pending_entry_matches_when_its_recorded_text_is_present(tmp_path: Path) -> None:
    """The control: needle present is `pending`, not `pending-drift`."""
    repo = _make_repo(tmp_path)
    _write_allowlist(repo, pending=[dict(DRIFT_ENTRY)])
    _stage(repo, "docs/ops/session.md", SESSION_STEPS)
    proc = _run(repo)
    assert proc.returncode == 0, proc.stdout
    assert "allowlisted: NO" in proc.stdout
    assert "PENDING-DRIFT" not in proc.stdout, proc.stdout


def test_pending_entry_does_not_block_when_its_recorded_text_drifts(tmp_path: Path) -> None:
    """The load-bearing case: a reword must not turn a record into a block."""
    proc = _run(_drift_fixture(tmp_path))
    assert proc.returncode == 0, proc.stdout
    assert "FAIL" not in proc.stdout
    assert "PENDING-DRIFT" in proc.stdout, proc.stdout


def test_pending_drift_still_reports_allowlisted_no(tmp_path: Path) -> None:
    """Drift changes the urgency of the report, never its approval."""
    proc = _run(_drift_fixture(tmp_path))
    assert "allowlisted: NO" in proc.stdout, proc.stdout
    assert "DIG-1434" in proc.stdout, proc.stdout


def test_pending_drift_emits_a_workflow_annotation(tmp_path: Path) -> None:
    """Report-only means visible on the PR page, not buried in the log."""
    proc = _run(_drift_fixture(tmp_path))
    assert "::warning title=PENDING-DRIFT" in proc.stdout, proc.stdout
    assert "::error" not in proc.stdout, proc.stdout


def test_drift_does_not_weaken_a_hit_with_no_pending_entry(tmp_path: Path) -> None:
    """The teeth. Identical content, no pending entry: still a hard failure."""
    repo = _make_repo(tmp_path)
    _write_allowlist(repo)
    _stage(repo, "docs/ops/session.md", DRIFTED_STEPS)
    proc = _run(repo)
    assert proc.returncode == 1, proc.stdout
    assert "docs/ops/session.md" in proc.stdout, proc.stdout


def test_drift_does_not_weaken_a_hit_on_an_uncovered_path(tmp_path: Path) -> None:
    """A pending entry covers rule + path, and nothing outside them."""
    repo = _make_repo(tmp_path)
    _write_allowlist(repo, pending=[dict(DRIFT_ENTRY)])
    _stage(repo, "docs/ops/elsewhere.md", DRIFTED_STEPS)
    proc = _run(repo)
    assert proc.returncode == 1, proc.stdout
    assert "docs/ops/elsewhere.md" in proc.stdout, proc.stdout


def test_enforce_pending_makes_a_drifting_pending_entry_block(tmp_path: Path) -> None:
    """Security's restore path is one flag, and it really blocks."""
    proc = _run(_drift_fixture(tmp_path), "--enforce-pending")
    assert proc.returncode == 1, proc.stdout
    assert "::error title=PENDING-DRIFT" in proc.stdout, proc.stdout


def test_enforce_pending_makes_a_matched_pending_entry_block(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _write_allowlist(repo, pending=[dict(DRIFT_ENTRY)])
    _stage(repo, "docs/ops/session.md", SESSION_STEPS)
    proc = _run(repo, "--enforce-pending")
    assert proc.returncode == 1, proc.stdout
    assert "--enforce-pending is set" in proc.stdout, proc.stdout


def test_enforce_pending_does_not_block_an_allowlisted_entry(tmp_path: Path) -> None:
    """An approved entry is a decision already taken; the flag must not undo it."""
    repo = _make_repo(tmp_path)
    _write_allowlist(
        repo,
        approved=[
            {
                "rule": "V1",
                "path": "docs/vendor.md",
                "symbol": "PMT_",
                "owner": "Security b14d7a18",
                "ticket": "DIG-1418 rule 2",
                "reason": "our own stage id; rule 2 keeps our own names",
            }
        ],
    )
    _stage(repo, "docs/vendor.md", ENV_NAME_ONLY)
    proc = _run(repo, "--enforce-pending")
    assert proc.returncode == 0, proc.stdout


def test_json_marks_pending_report_only_and_carries_the_drift_flag(tmp_path: Path) -> None:
    proc = _run(_drift_fixture(tmp_path), "--json")
    assert proc.returncode == 0, proc.stdout
    payload = json.loads(proc.stdout[proc.stdout.index("{") :])
    assert payload["enforce_pending"] is False
    assert payload["fails"] == []
    drifted = [p for p in payload["pending"] if p["rule"] == "M5"]
    assert drifted, proc.stdout
    assert drifted[0]["drift"] is True
    assert drifted[0]["allowlisted"] is False


def test_json_under_enforce_pending_still_reports_pending_as_pending(tmp_path: Path) -> None:
    """`--json` describes what was found; the exit code is what enforces."""
    proc = _run(_drift_fixture(tmp_path), "--json", "--enforce-pending")
    assert proc.returncode == 1
    payload = json.loads(proc.stdout[proc.stdout.index("{") :])
    assert payload["enforce_pending"] is True
    assert payload["fails"] == []
    assert any(p["drift"] for p in payload["pending"])
