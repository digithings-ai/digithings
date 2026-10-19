"""DIG-1600: the two measures behind ``docs/ops/branch-hygiene-policy.md``.

The policy's § 2 measure and § 3 population are only as good as two pure
functions in ``scripts/branch_census.py``, and both were wrong before this:

* ``count_unmerged_patches`` was spelled ``stdout.count("\\n+")`` in the first
  census and read **119** where the correct answer is **162** -- off by exactly
  one on each of the 43 resolvable T2 branches, because ``git cherry``'s first
  output line has no preceding newline. A uniform one-per-branch delta is the
  signature of a counting bug, not of drift between two measurements.
* "landed" was read off ``merge_commit_sha``, which GitHub populates on a
  closed-unmerged PR with the test merge it computed. Six of the 42 census PRs
  read ``merged=false`` with a non-NULL sha, so that flag marks shipped work
  that never shipped.

So these tests pin the *counters and the classifier*, not the population. A
number that moves when ``develop`` moves is a census result, not a regression;
an off-by-one that follows the data around is a bug, and only a pinned
counter can tell the two apart.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_census():
    """Import ``scripts/branch_census.py`` by path.

    ``scripts/`` is not a package and the repo root is not on ``sys.path`` under
    pytest, so this loads by file location. Registered in ``sys.modules`` first:
    ``dataclasses`` resolves ``sys.modules[cls.__module__].__dict__`` when it
    decides whether a field is ``kw_only``, and a module that was never
    inserted raises ``AttributeError: 'NoneType' object has no attribute
    '__dict__'`` -- inside the ``@dataclass`` under test, which reads as a defect
    in the code being reviewed.
    """
    spec = importlib.util.spec_from_file_location(
        "branch_census", _REPO_ROOT / "scripts" / "branch_census.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["branch_census"] = mod
    spec.loader.exec_module(mod)
    return mod


bc = _load_census()


# ---------------------------------------------------------------- the measure


def test_cherry_first_line_plus_is_counted():
    """A ``+`` in the FIRST position has no preceding newline to match ``\\n+``.

    This is the regression. ``git cherry`` emits one line per commit as
    ``+ <sha>`` or ``- <sha>``, and the first line of the stream is bare. The
    substring spelling drops it, so any branch whose tip is unmerged reads one
    patch short -- which is every branch a human would look at first.
    """
    first_line_plus = "+ abc123\n- def456\n"
    assert bc.count_unmerged_patches(first_line_plus) == 1
    assert bc.count_applied_patches(first_line_plus) == 1

    # The instrument the census is NOT allowed to use, and the gap it leaves.
    assert first_line_plus.count("\n+") == 0, (
        "if this starts failing, the fixture no longer has a first-line '+'; "
        "keep a case that separates the two counters"
    )
    assert bc.count_unmerged_patches(first_line_plus) != first_line_plus.count("\n+")


def test_cherry_counts_every_line_position():
    """All three shapes, and the empty stream."""
    out = "+ one\n+ two\n- three\n+ four\n- five\n"
    assert bc.count_unmerged_patches(out) == 3
    assert bc.count_applied_patches(out) == 2
    assert bc.count_unmerged_patches("") == 0
    assert bc.count_applied_patches("") == 0
    # A line that merely CONTAINS a plus is not a verdict line.
    assert bc.count_unmerged_patches("+++ b/some/file\n") == 0
    assert bc.count_unmerged_patches("  + indented\n") == 0


def test_cherry_total_is_stable_across_line_endings():
    """Same content, LF and CRLF: the count must not move."""
    lf = "+ a\n- b\n+ c\n"
    crlf = lf.replace("\n", "\r\n")
    assert bc.count_unmerged_patches(lf) == bc.count_unmerged_patches(crlf) == 2


# --------------------------------------------------------------- the classifier


@pytest.mark.parametrize(
    ("patches", "expected"),
    [
        (0, "T0"),
        (1, "T1"),
        (2, "T1"),
        (3, "T2"),
        (10, "T2"),
        (11, "T3"),
        (12, "T3"),
        (10_000, "T3"),
    ],
)
def test_tier_boundaries_are_inclusive_on_both_ends(patches, expected):
    assert bc.classify_tier(patches) == expected


def test_an_unmeasurable_branch_is_not_t0():
    """``None`` is "cannot be measured", never "measured, zero patches".

    T0 is the free tier: it licenses deletion with no approval, on the grounds
    that by definition nothing is lost. A branch whose ref has been deleted from
    the remote cannot be shown to carry nothing -- it can only be shown to be
    unmeasurable. Returning ``T0`` for it would hand a deletion pass a licence
    the census never earned.
    """
    assert bc.classify_tier(None) is None
    assert bc.classify_tier(None) != bc.classify_tier(0)


def test_every_nonnegative_patch_count_lands_in_exactly_one_tier():
    """No gap and no overlap across the whole measured range.

    A hole in the tier table would raise; an overlap would make the classifier
    order-dependent, which is invisible in a single-case test.
    """
    seen: dict[str, int] = {}
    for n in range(0, 200):
        label = bc.classify_tier(n)
        assert label is not None
        seen[label] = seen.get(label, 0) + 1
    assert seen == {"T0": 1, "T1": 2, "T2": 8, "T3": 189}


# ------------------------------------------------------------------ exclusions


@pytest.mark.parametrize(
    ("branch", "expected"),
    [
        ("main", "main/develop"),
        ("develop", "main/develop"),
        ("module/digiquant", "module/**"),
        ("module/digiclaw", "module/**"),
        ("chore/sync-module-develop", "chore/sync-module-*"),
        ("release/v0.1.0", "release/v*"),
        # Not excluded -- the control that makes the five above mean something.
        ("task/4311-gitleaks-env-example-gap", None),
        ("cursor/stripe-three-tiers-3d52", None),
        # Near misses: a prefix that is not the excluded prefix.
        ("modules/digiquant", None),
        ("chore/sync-develop", None),
        ("release-candidate/1.0", None),
    ],
)
def test_section_5_exclusions(branch, expected):
    assert bc.exclusion_for(branch) == expected


# ------------------------------------------------------------- the landed signal


def test_merge_commit_sha_alone_does_not_mean_landed():
    """A closed-unmerged PR still carries a ``merge_commit_sha``.

    That is GitHub's *test* merge commit for the PR, recorded whether or not the
    merge happened. Gating the landed verdict on the field's presence marks
    shipped work that never shipped -- and the census has 6 such PRs, so the
    error is not hypothetical.
    """
    closed_with_shas = {"merged": False, "merge_commit_sha": "f" * 40, "on_own_base": True}
    assert bc.pr_land_state(**closed_with_shas) == "not-landed"

    # Control: the same sha on a PR that really did merge IS landed. Without
    # this, "not-landed" would pass for a constant that always answers that.
    merged_same_shas = {"merged": True, "merge_commit_sha": "f" * 40, "on_own_base": True}
    assert bc.pr_land_state(**merged_same_shas) == "landed"


def test_landed_is_measured_against_the_prs_own_base():
    """``merged=true`` but the merge commit is not on the base is not landed.

    A rebase or a revert after the merge leaves the PR marked merged while its
    commit is absent from the base it merged into. That is a different fact from
    "the PR merged", and the policy needs the second one.
    """
    assert bc.pr_land_state(merged=True, merge_commit_sha="a" * 40, on_own_base=False) == (
        "merged-not-on-base"
    )


def test_merged_without_a_merge_commit_is_recorded_not_inferred():
    """Never guess in either direction when the merge commit is missing."""
    assert bc.pr_land_state(merged=True, merge_commit_sha=None, on_own_base=False) == (
        "merged-no-merge-commit"
    )
    # And it must not collapse into the landed bucket the census sums on.
    assert bc.pr_land_state(merged=True, merge_commit_sha=None, on_own_base=False) not in (
        "landed",
        "not-landed",
    )


# -------------------------------------------------------------- ref resolution


def test_archive_refs_resolve_so_archived_work_is_still_measurable():
    """§ 4 clause 5 pushes a discarded branch to ``refs/archive/<branch>``.

    That is the whole point of archiving: without it the branch stops being
    measurable and the patches become unrecoverable. Resolution order is live
    first, archive second, and a branch present both ways reports live so the
    reader knows it is still on the branch list.
    """
    refs = {"github/archive/task/9999-rescued", "github/task/8888-live"}
    assert bc.resolve_ref("task/8888-live", refs) == "github/task/8888-live"
    assert bc.resolve_ref("task/9999-rescued", refs) == "github/archive/task/9999-rescued"

    both = set(refs) | {"github/task/9999-rescued"}
    assert bc.resolve_ref("task/9999-rescued", both) == "github/task/9999-rescued"

    assert bc.resolve_ref("task/7777-gone", refs) is None


# ------------------------------------------------------------------- summary


def _row(**kw):
    base = dict(
        branch="b",
        recorded_tier="T2-decide",
        pr_number="1",
        recorded_commits=0,
        ref="github/b",
        patches=0,
        landed="not-landed",
        pr_base="develop",
        exclusion=None,
        notes=[],
    )
    base.update(kw)
    return bc.BranchRow(**base)


def test_summary_separates_unresolvable_from_zero_and_landed_from_recoverable():
    """The three numbers a reader must never confuse.

    * an unresolvable branch counts in ``branches`` and adds **0** to
      ``patches_measurable`` -- never a fabricated count, never a silent zero;
    * ``patches_unlanded`` excludes patches on branches whose PR landed, which
      is the only number disposal can act on.
    """
    rows = [
        _row(branch="landed-1", patches=100, landed="landed"),
        _row(branch="live-1", patches=7, landed="not-landed"),
        _row(branch="live-2", patches=3, landed="not-landed"),
        _row(branch="stackbase", patches=5, landed="no-pr"),
        _row(branch="gone", patches=None, landed="unresolved", ref=None),
        _row(branch="excluded", patches=2, landed="not-landed", exclusion="module/**"),
    ]
    s = bc.summarise(rows)
    assert s["branches"] == 6
    assert s["measured"] == 5
    assert s["unresolvable"] == 1
    assert s["patches_measurable"] == 117  # 100+7+3+5+2
    assert s["patches_on_excluded"] == 2
    # 7 + 3 + 5 + 2 -- the landed branch's 100 patches are excluded.
    assert s["patches_unlanded"] == 17


def test_a_census_of_only_unresolvable_branches_reports_no_patches():
    """All-unmeasured is a valid answer, and it must not read as "clean".

    This is the shape that makes the inflated § 3 figure possible: if
    unresolvable branches were scored 0, a census with almost nothing measurable
    would report a reassuringly small patch total.
    """
    rows = [
        _row(branch=f"gone-{i}", patches=None, landed="unresolved", ref=None)
        for i in range(10)
    ]
    s = bc.summarise(rows)
    assert s["branches"] == 10
    assert s["measured"] == 0
    assert s["unresolvable"] == 10
    assert s["patches_measurable"] == 0
    assert s["patches_unlanded"] == 0
    # The tier bucket must be labelled "unmeasured", not folded into T0.
    assert set(s["by_tier"]) == {"unmeasured"}
    assert bc.classify_tier(0) == "T0"
    assert bc.classify_tier(None) is None


def test_markdown_prints_the_bounds_not_just_the_total():
    """The renderer must carry the unresolvable count and the landed split.

    A summary that prints one total invites the reader to quote it as the
    population. The bound and the unlanded figure have to be on the page.
    """
    rows = [
        _row(branch="landed-1", patches=100, landed="landed"),
        _row(branch="live-1", patches=7, landed="not-landed"),
        _row(branch="gone", patches=None, landed="unresolved", ref=None),
    ]
    md = bc.markdown(rows, bc.summarise(rows))
    for needle in ("lower bound", "unresolvable", "never landed", "107"):
        assert needle in md, f"markdown omitted {needle!r}"


def test_markdown_carries_both_the_recorded_and_the_measured_tier_table():
    """Policy section 3 publishes the recorded view; disposal needs the measured one.

    If the renderer emitted only one of them then one of the two claims section
    3 makes about it -- "the published table is reproducible", and "it reports
    drift against the recorded tier" -- would be a claim no command supports.
    """
    rows = [
        _row(branch="landed-1", patches=100, landed="landed", recorded_tier="T3-cto"),
        _row(branch="live-1", patches=7, landed="not-landed", recorded_tier="T2-decide"),
    ]
    md = bc.markdown(rows, bc.summarise(rows))
    for needle in (
        "| Recorded tier | Census rows |",
        "| Measured tier | Branches |",
        "| T2 | 1 | 1 | 7 |",  # recorded view: 7 patches under the recorded T2
        "| T3 | 1 | 100 |",  # measured view: 100 patches under the measured T3
    ):
        assert needle in md, f"markdown omitted {needle!r}"


# ----------------------------------------------- recorded tier vs measured tier


def test_short_tier_strips_the_census_suffix_and_refuses_an_unknown_label():
    """The TSV writes ``T2-decide``; policy section 3's table reads ``T2``.

    An unreadable label must not be folded into a real tier: a row whose tier
    nobody can read is a gap in the census, and quietly counting it as T0 is
    how an unclassified branch acquires a free-tier deletion licence.
    """
    assert bc.short_tier("T0-free") == "T0"
    assert bc.short_tier("T1-small") == "T1"
    assert bc.short_tier("T2-decide") == "T2"
    assert bc.short_tier("T3-cto") == "T3"
    assert bc.short_tier("t2-decide") == "T2"  # case-insensitive
    assert bc.short_tier("T4-unknown") == "?"
    assert bc.short_tier("") == "?"
    assert bc.short_tier(None) == "?"


def test_summary_by_recorded_tier_keys_on_the_recorded_label_not_the_measured_one():
    """The two views must disagree when a branch drifted, or they are one view.

    Both rows are recorded ``T2-decide`` and both measure 1 patch, which the
    policy's own thresholds put in T1. If the recorded view were silently
    keyed on the measured tier it would report T1, and the drift report would
    have nothing to report.
    """
    rows = [
        _row(branch="a", recorded_tier="T2-decide", patches=1),
        _row(branch="b", recorded_tier="T2-decide", patches=1),
    ]
    s = bc.summarise(rows)
    assert s["by_recorded_tier"]["T2"]["census_rows"] == 2
    assert s["by_recorded_tier"]["T2"]["patches"] == 2
    assert "T1" not in s["by_recorded_tier"], "recorded view leaked the measured tier"
    assert s["by_tier"]["T1"]["patches"] == 2
    assert "T2" not in s["by_tier"], "measured view leaked the recorded tier"


def test_summary_by_recorded_tier_separates_no_pr_from_a_pr_that_never_landed():
    """Section 3's largest open question is the no-PR mass; it needs its own bucket.

    ``no-pr`` and ``not-landed`` are both "not landed", so a summary that keeps
    one bucket cannot answer "how much work has no PR to be landed or discarded
    through at all" -- which is the question the section-3 correction asks.
    """
    rows = [
        _row(branch="stack-base", recorded_tier="T3-cto", patches=5, landed="no-pr"),
        _row(branch="rejected", recorded_tier="T3-cto", patches=7, landed="not-landed"),
        _row(branch="shipped", recorded_tier="T3-cto", patches=11, landed="landed"),
    ]
    a = bc.summarise(rows)["by_recorded_tier"]["T3"]
    assert (a["nopr_branches"], a["nopr_patches"]) == (1, 5)
    assert (a["unlanded_branches"], a["unlanded_patches"]) == (1, 7)
    assert (a["landed_branches"], a["landed_patches"]) == (1, 11)
    assert a["census_rows"] == 3 and a["measurable"] == 3 and a["patches"] == 23


def test_drift_lists_only_measurable_rows_whose_tier_moved():
    """Drift is a report about measurement, so unmeasured rows cannot be in it.

    Three exclusions, each a different failure: a branch that still measures in
    the recorded tier has not drifted; a branch with no ref has no tier to
    re-derive; and a row whose recorded label is unreadable has no recorded
    tier to have drifted away from.
    """
    rows = [
        _row(branch="moved", recorded_tier="T1-small", patches=5),
        _row(branch="steady", recorded_tier="T2-decide", patches=5),
        _row(branch="gone", recorded_tier="T1-small", patches=None, landed="unresolved", ref=None),
        _row(branch="unreadable", recorded_tier="mystery", patches=5),
    ]
    drift = bc.summarise(rows)["drift"]
    assert [d["branch"] for d in drift] == ["moved"]
    assert drift[0]["recorded_tier"] == "T1"
    assert drift[0]["measured_tier"] == "T2"
    assert drift[0]["patches"] == 5
    # The unreadable row is a census gap, surfaced under "?" and not as drift.
    assert bc.summarise(rows)["by_recorded_tier"]["?"]["census_rows"] == 1


def test_drift_is_empty_when_nothing_moved():
    """The negative arm: without it, a drift report that always lists nothing
    is indistinguishable from a drift report that cannot detect movement."""
    rows = [
        _row(branch="t0", recorded_tier="T0-free", patches=0),
        _row(branch="t1", recorded_tier="T1-small", patches=2),
        _row(branch="t2", recorded_tier="T2-decide", patches=10),
        _row(branch="t3", recorded_tier="T3-cto", patches=4000),
    ]
    assert bc.summarise(rows)["drift"] == []


def test_markdown_totals_row_is_summed_not_transcribed():
    """Section 3's headline numbers live in a totals row, so it must be computed.

    A hand-added totals row is how a table comes to quote 826 in the total and
    833 in the cells. The columns are checked here against a census whose cells
    sum to a deliberately non-obvious total.
    """
    rows = [
        _row(branch="a", recorded_tier="T2-decide", patches=7, landed="landed"),
        _row(branch="b", recorded_tier="T2-decide", patches=5, landed="not-landed"),
        _row(branch="c", recorded_tier="T3-cto", patches=30, landed="no-pr"),
        _row(branch="d", recorded_tier="T1-small", patches=None, landed="unresolved", ref=None),
    ]
    md = bc.markdown(rows, bc.summarise(rows))
    total = "| **Total** | **4** | **3** | **42** | **1 / 7** | **1 / 30** | **1 / 5** |"
    assert total in md, f"markdown omitted {total!r}"
    # The unmeasurable row is counted in census rows and in nothing else.
    assert "| T1 | 1 | 0 | 0 | 0 / 0 | 0 / 0 | 0 / 0 |" in md


def test_markdown_prints_no_totals_row_for_an_empty_census():
    """Without this, a zero-row census prints a row of zeros that reads as a result."""
    md = bc.markdown([], bc.summarise([]))
    assert "**Total**" not in md
    assert "- census rows: **0**" in md


# ------------------------------------------------- one real-git control path


def _git(*args: str) -> tuple[int, str]:
    p = subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=_REPO_ROOT, check=False
    )
    return p.returncode, p.stdout


@pytest.mark.skipif(
    _git("rev-parse", "--git-dir")[0] != 0, reason="not inside a git checkout"
)
def test_measure_patches_against_a_bogus_ref_is_unmeasurable_not_zero():
    """A ref git cannot resolve is ``(None, reason)``, never ``(0, 0)``.

    Returning 0 for an unreadable ref is the specific error that turns 224
    vanished branches into "224 branches with nothing on them" -- a free-tier
    deletion licence issued by a measurement that never happened.
    """
    patches, applied = bc.measure_patches("refs/remotes/github/no-such-branch-xyz", "develop")
    assert patches is None
    assert applied is not None  # the reason travels with the None
    assert bc.classify_tier(patches) is None


@pytest.mark.skipif(
    _git("rev-parse", "--git-dir")[0] != 0, reason="not inside a git checkout"
)
def test_cherry_against_develop_is_nonnegative_on_a_real_ref():
    """Live control: the counter runs on real ``git cherry`` output.

    Guards the other direction -- that the two counters together account for
    every line git emits, so a format change in git surfaces here rather than
    as a silently shifted total in the policy.
    """
    rc, out = _git("cherry", "github/develop", "github/develop")
    if rc != 0:
        pytest.skip("github/develop not fetched in this checkout")
    lines = [L for L in out.splitlines() if L[:1] in ("+", "-")]
    assert bc.count_unmerged_patches(out) + bc.count_applied_patches(out) == len(lines)
    # develop against itself is fully applied.
    assert bc.count_unmerged_patches(out) == 0
