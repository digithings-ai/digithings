"""Unit tests for scripts/fetch_repo_activity.py.

The script feeds figures onto digithings.ai's homepage, which promises "no
asterisks — every figure is countable in the repo". Two failure modes matter more
than the rest, and both have precedent in this repo:

* **a figure that is quietly the wrong measurement.** The first draft read
  ``repo.open_issues_count`` for "issues open" — a field that counts open issues
  *plus* open PRs, so it reported 203 where the truth was 197 issues and 6 PRs, and
  the page would have shown it beside a ``is:issue``-scoped closed count. Same class
  as 6e3b6d1a, which found one claim contradicting itself in four places.
* **a module silently dropping out.** digivault shipped for months while being
  absent from the module registry, because nothing asserted the registry and the
  filesystem agreed. ``_module_paths`` now raises instead, and that is pinned here.

No test here touches the network: ``collect()`` is the only function that calls
``gh``, and everything under it is pure or reads the working tree.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "fetch_repo_activity.py"
REFRESH_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "refresh-repo-activity.yml"
WEB_LANE = REPO_ROOT / ".github" / "workflows" / "test-web.yml"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("fetch_repo_activity", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["fetch_repo_activity"] = module
    spec.loader.exec_module(module)
    return module


fra = _load()


def _commit(subject: str, date: str = "2026-08-06T10:00:00Z") -> dict[str, Any]:
    return {"commit": {"message": f"{subject}\n\nbody text", "committer": {"date": date}}}


def _snapshot(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "generatedAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "windowDays": 30,
        "branch": "main",
        "commits": 770,
        "pullsMerged": 337,
        "issuesClosed": 151,
        "pullsOpen": 4,
        "issuesOpen": 197,
        "features": [{"scope": "ci", "summary": "a thing", "pr": 1, "date": None}],
        "mergedPulls": [
            {
                "number": 1,
                "title": "a thing",
                "url": "https://github.com/digithings-ai/digithings/pull/1",
                "mergedAt": "2026-08-06T10:00:00Z",
            }
        ],
        "openIssues": [
            {
                "number": 2,
                "title": "an issue",
                "url": "https://github.com/digithings-ai/digithings/issues/2",
                "updatedAt": "2026-08-06T10:00:00Z",
            }
        ],
        "latestRelease": None,
        "modules": {"digigraph": {"path": "digigraph", "lastCommit": None, "files": 1, "lines": 2}},
    }
    base.update(over)
    return base


def _check(data: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **kw: Any) -> int:
    out = tmp_path / "repo-activity.json"
    out.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(fra, "OUT", out)
    return fra.check(**kw)


# ── the committed snapshot itself ────────────────────────────────────────────


@pytest.mark.unit
def test_the_committed_snapshot_passes_its_own_check() -> None:
    """The artifact the site imports must be valid without regenerating it."""
    assert fra.check() == 0


@pytest.mark.unit
def test_the_committed_snapshot_measures_issues_the_same_way_on_both_sides() -> None:
    """Open and closed must both be issue-only counts, never issues+PRs.

    A repo merging hundreds of PRs a month has a nonzero open-PR count, so the two
    definitions diverge and the page would render a pair that does not compare.
    """
    source = SCRIPT.read_text(encoding="utf-8")
    # The field name still appears in prose explaining why it is not used; what must
    # not appear is a read of it.
    assert 'get("open_issues_count"' not in source, (
        "open_issues_count counts open issues PLUS open PRs — use the is:issue search"
    )
    assert "is:issue+is:open" in source


@pytest.mark.unit
def test_the_windowed_and_unwindowed_queries_stay_deliberately_different() -> None:
    """Closed issues carry a date bound; open issues must NOT — and vice versa.

    This asymmetry looks like an oversight and is not, so it is pinned in both
    directions. `issuesClosed` is "closed in the last 30 days" and needs its
    `closed:>=`. `issuesOpen` is the whole live backlog: bounding it would answer
    "opened in the last 30 days and still open", which was 30 against a real backlog
    of 197 and is a question nobody asked.

    The first draft rendered the unbounded figure under a `// last 30 days` heading,
    presenting a lifetime count as a monthly one. A future edit that "fixes" the
    inconsistency in either direction breaks a page claim, so it breaks here first.
    """
    source = SCRIPT.read_text(encoding="utf-8")
    closed = next(line for line in source.splitlines() if "is:issue+is:closed" in line)
    opened = next(line for line in source.splitlines() if "is:issue+is:open&" in line)
    assert "closed:>=" in closed, "issuesClosed must stay windowed"
    assert "created:" not in opened and "since" not in opened, (
        "issuesOpen must stay unbounded — it is current state, not velocity"
    )


@pytest.mark.unit
def test_open_prs_are_unwindowed_current_state() -> None:
    """Open PRs are the live queue, not 'opened in the last 30 days'."""
    source = SCRIPT.read_text(encoding="utf-8")
    opened = next(line for line in source.splitlines() if "is:pr+is:open" in line)
    assert "created:" not in opened and "merged:>=" not in opened
    assert "is:pr+is:open" in source


@pytest.mark.unit
def test_recent_lists_come_from_search_items_not_commit_subjects() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    merged = next(line for line in source.splitlines() if "is:pr+is:merged" in line)
    assert "per_page=6" in merged and "sort=updated" in merged
    issues = next(line for line in source.splitlines() if "is:issue+is:open&" in line)
    assert "sort=updated" in issues


@pytest.mark.unit
def test_search_items_keeps_number_title_and_url() -> None:
    rows = fra._search_items(
        {
            "items": [
                {
                    "number": 9,
                    "title": "hello",
                    "html_url": "https://github.com/digithings-ai/digithings/pull/9",
                    "updated_at": "2026-09-02T00:00:00Z",
                    "closed_at": "2026-09-01T00:00:00Z",
                },
                {"number": 10},
            ]
        },
        6,
    )
    assert rows == [
        {
            "number": 9,
            "title": "hello",
            "url": "https://github.com/digithings-ai/digithings/pull/9",
            "updatedAt": "2026-09-02T00:00:00Z",
            "closedAt": "2026-09-01T00:00:00Z",
        }
    ]


# ── shape validation ─────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize("banned", ["stars", "stargazers", "forks", "watchers", "subscribers"])
def test_check_refuses_a_vanity_metric(
    banned: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _check(_snapshot(**{banned: 1}), tmp_path, monkeypatch) == 1


@pytest.mark.unit
@pytest.mark.parametrize("missing", ["commits", "pullsMerged", "issuesClosed", "features"])
def test_check_refuses_a_missing_figure(
    missing: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _snapshot()
    del data[missing]
    assert _check(data, tmp_path, monkeypatch) == 1


@pytest.mark.unit
def test_check_refuses_a_missing_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = _snapshot()
    del data["mergedPulls"]
    assert _check(data, tmp_path, monkeypatch) == 1


@pytest.mark.unit
def test_check_refuses_an_empty_module_map(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _check(_snapshot(modules={}), tmp_path, monkeypatch) == 1


@pytest.mark.unit
def test_check_refuses_unparseable_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = tmp_path / "repo-activity.json"
    out.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(fra, "OUT", out)
    assert fra.check() == 1


@pytest.mark.unit
def test_check_refuses_a_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fra, "OUT", tmp_path / "absent.json")
    assert fra.check() == 1


# ── the freshness asymmetry ──────────────────────────────────────────────────


@pytest.mark.unit
def test_a_stale_snapshot_passes_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Staleness must NOT fail an ordinary check.

    This is deliberate, not an oversight: --check runs on website PRs, and a hard
    staleness gate would turn "the refresh cron did not fire" into a red build on
    unrelated work — the kind of unrelated-red that gets a check deleted. The page
    prints the snapshot date, so an old snapshot reads as dated to a human instead.
    """
    old = (datetime.now(UTC) - timedelta(days=400)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert _check(_snapshot(generatedAt=old), tmp_path, monkeypatch) == 0


@pytest.mark.unit
def test_a_stale_snapshot_fails_when_a_max_age_is_demanded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = (datetime.now(UTC) - timedelta(days=9)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert _check(_snapshot(generatedAt=old), tmp_path, monkeypatch, max_age_days=3) == 1
    assert _check(_snapshot(generatedAt=old), tmp_path, monkeypatch, max_age_days=30) == 0


@pytest.mark.unit
def test_check_refuses_a_malformed_timestamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _check(_snapshot(generatedAt="last Tuesday"), tmp_path, monkeypatch) == 1


# ── feature extraction ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_features_reads_scope_summary_and_pr_from_a_squash_subject() -> None:
    feats = fra._features(
        [_commit("feat(design-system): put digivault in the module registry (#1930)")]
    )
    assert feats == [
        {
            "scope": "design-system",
            "summary": "put digivault in the module registry",
            "pr": 1930,
            "date": "2026-08-06T10:00:00Z",
        }
    ]


@pytest.mark.unit
def test_features_keeps_unscoped_and_breaking_feats() -> None:
    feats = fra._features(
        [_commit("feat: a bare feature (#12)"), _commit("feat(api)!: broke it (#13)")]
    )
    assert [(f["scope"], f["pr"]) for f in feats] == [(None, 12), ("api", 13)]


@pytest.mark.unit
@pytest.mark.parametrize(
    "subject",
    [
        "fix(byok): refuse a key digigraph cannot spend (#1929)",
        "chore(website): refresh the snapshot (#1940)",
        "docs: rewrite the readme (#1941)",
        "test(byok): pin the 400 at the middleware (#1942)",
        "Merge pull request #1936 from digithings-ai/chore/promote",
    ],
)
def test_features_ignores_every_type_that_is_not_feat(
    subject: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fra, "_pr_for_commit", lambda sha: 999)
    assert fra._features([_commit(subject)]) == []


@pytest.mark.unit
def test_features_resolves_the_pr_for_a_merge_committed_feat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A subject with no `(#N)` must still get its PR, not be dropped.

    Only a SQUASH merge leaves the number in the subject. Requiring it silently hid
    every merge-committed feature — real case: PR #1911 landed four `feat(digichat)`
    commits newer than three of the six rows the page was showing, which made
    "the most recent features to land on main" false.
    """
    monkeypatch.setattr(fra, "_pr_for_commit", lambda sha: 1911)
    feats = fra._features([_commit("feat(digichat): enforce chat quota server-side")])
    assert [(f["scope"], f["summary"], f["pr"]) for f in feats] == [
        ("digichat", "enforce chat quota server-side", 1911)
    ]


@pytest.mark.unit
def test_features_drops_a_feat_whose_pr_cannot_be_resolved(monkeypatch: pytest.MonkeyPatch) -> None:
    """The page states every row is a PR you can open, so a row without one is a lie.

    Also the guard against rendering `/pull/undefined`.
    """
    monkeypatch.setattr(fra, "_pr_for_commit", lambda sha: None)
    assert fra._features([_commit("feat: pushed straight to a branch")]) == []


@pytest.mark.unit
def test_features_dedupes_one_row_per_pr_across_a_merge(monkeypatch: pytest.MonkeyPatch) -> None:
    """A merge-committed PR contributes several feats; it must not fill the list."""
    monkeypatch.setattr(fra, "_pr_for_commit", lambda sha: 1911)
    commits = [_commit(f"feat(digichat): part {i}") for i in range(4)]
    feats = fra._features(commits)
    assert len(feats) == 1
    assert feats[0]["summary"] == "part 0", "the newest commit represents the PR"


@pytest.mark.unit
def test_features_dedupes_by_pr_and_honours_the_limit() -> None:
    commits = [_commit(f"feat(x): thing {n} (#{n})") for n in range(100, 110)]
    commits.append(_commit("feat(x): thing 100 again (#100)"))
    feats = fra._features(commits, limit=4)
    assert len(feats) == 4
    assert len({f["pr"] for f in feats}) == 4


# ── registry / filesystem agreement ─────────────────────────────────────────


@pytest.mark.unit
def test_every_shipping_module_in_the_registry_has_a_directory() -> None:
    """The digivault-gap guard, run against the real registry."""
    paths = fra._module_paths()
    assert "digivault" in paths, "digivault ships a service on 8004 and must be counted"
    assert paths["digichat"] == "frontend/digichat", "frontend modules live one level down"
    for mid, path in paths.items():
        assert (REPO_ROOT / path).is_dir(), f"{mid} -> {path}"


@pytest.mark.unit
def test_roadmap_modules_are_excluded_rather_than_zeroed() -> None:
    paths = fra._module_paths()
    assert "digistore" not in paths
    assert "digilink" not in paths


@pytest.mark.unit
def test_module_paths_refuses_a_registry_whose_entries_it_cannot_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A zero denominator must raise too, not pass by short-circuit.

    The guard was once `if declared and len(found) != declared`, which meant a
    `declared` of 0 skipped the comparison entirely — so reindenting modules.ts past
    the `^\\s{4}id: "` pattern would disable the very check meant to catch a module
    dropping out of the band.
    """
    fake = tmp_path / "modules.ts"
    fake.write_text(
        "export const modules = [\n"
        '  {\n        id: "digigraph",\n        name: "digigraph",\n'
        '        tier: "core",\n  },\n'
        "];\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(fra, "MODULES_TS", fake)
    with pytest.raises(SystemExit):
        fra._module_paths()


@pytest.mark.unit
def test_module_paths_refuses_a_registry_it_cannot_fully_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A drifted entry shape must raise, not silently return fewer modules."""
    fake = tmp_path / "modules.ts"
    fake.write_text(
        "export const modules = [\n"
        '  {\n    id: "digigraph",\n    name: "digigraph",\n    tier: "core",\n  },\n'
        '  {\n    id: "digighost",\n    name: "digighost",\n    role: "x",\n  },\n'
        "];\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(fra, "MODULES_TS", fake)
    with pytest.raises(SystemExit):
        fra._module_paths()


# ── line counting ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_text_lines_counts_a_trailing_line_without_a_newline(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("one\ntwo\nthree", encoding="utf-8")
    assert fra._text_lines(tmp_path / "a.py") == 3
    (tmp_path / "b.py").write_text("one\ntwo\n", encoding="utf-8")
    assert fra._text_lines(tmp_path / "b.py") == 2


@pytest.mark.unit
def test_text_lines_scores_binaries_and_unreadable_paths_as_zero(tmp_path: Path) -> None:
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\xff" * 200)
    assert fra._text_lines(tmp_path / "logo.png") == 0
    assert fra._text_lines(tmp_path / "does-not-exist") == 0
    (tmp_path / "empty.py").write_text("", encoding="utf-8")
    assert fra._text_lines(tmp_path / "empty.py") == 0


# ── wiring ──────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_the_refresh_workflow_opens_a_pr_instead_of_pushing_to_develop() -> None:
    """develop requires a PR, so a direct push could only ever fail."""
    wf = REFRESH_WORKFLOW.read_text(encoding="utf-8")
    assert "--base develop" in wf
    assert "chore/repo-activity-" in wf, "chore/* is what bypasses the linkage gate"
    assert "github-actions[bot]" in wf, "the author must be in check_review_coverage BOT_AUTHORS"
    assert 'git push -u origin "$BRANCH"' in wf
    assert "--max-age-days" in wf, "the job must assert its own output is current"

    # Commands only — the file's own comments say the words "git add -A" while
    # explaining why they are not used, and matching prose would fail on the
    # explanation rather than on the behaviour.
    commands = "\n".join(line for line in wf.splitlines() if not line.lstrip().startswith("#"))
    assert "git add -A" not in commands, "stage by path — a workflow tree can lag its own HEAD"
    assert 'git add "$SNAPSHOT"' in commands


@pytest.mark.unit
def test_the_bot_author_is_actually_exempt_from_the_review_gate() -> None:
    """Asserted against the gate itself, not against a comment claiming it."""
    gate = (REPO_ROOT / "scripts" / "check_review_coverage.py").read_text(encoding="utf-8")
    assert "github-actions[bot]" in gate


@pytest.mark.unit
def test_the_web_lane_runs_the_site_test_suite() -> None:
    """A vitest file no lane executes cannot fail, so it is not a test."""
    lane = WEB_LANE.read_text(encoding="utf-8")
    assert "npm run test --workspace digithings-web" in lane
    # The digichat and olympus lanes also install rolldown at 1.0.0-rc.16, which the
    # locked rolldown 1.2.2 has moved off — a stale duplicate. This lane must not
    # acquire it by someone copying that step across. Commands only: the lane's own
    # comment names that version while explaining why it is not installed.
    commands = "\n".join(line for line in lane.splitlines() if not line.lstrip().startswith("#"))
    assert "1.0.0-rc.16" not in commands, "npm ci already installs the locked Linux rolldown"
    # This assertion used to run the other way, requiring the lane to hand-install
    # @tailwindcss/oxide-linux-x64-gnu because the lock carried oxide-darwin-arm64
    # alone. The lock now carries all eleven installable oxide platform entries with
    # their libc fields, so npm ci supplies the right one and the step was removed.
    # Inverted rather than deleted: it is the ratchet that stops the hand-install
    # being reintroduced, which would pin a binding the lock already resolves.
    assert "@tailwindcss/oxide" not in commands, (
        "the lock carries every installable oxide platform entry — do not hand-install it"
    )
    # Shape validation of the snapshot the homepage imports, but NOT a freshness gate:
    # a missed cron run must not redden an unrelated website PR. Commands again — the
    # step's comment says "no --max-age-days" in prose.
    assert "fetch_repo_activity.py --check" in commands
    assert "--max-age-days" not in commands, "freshness belongs to the refresh job alone"
