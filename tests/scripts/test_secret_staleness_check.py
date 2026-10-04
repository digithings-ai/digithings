"""Unit tests for scripts/secret_staleness_check.py (#248).

The property that matters here is not precision about dates: it is that nothing in
this path can emit a secret *value*. GitHub's Actions secrets API returns only names
and timestamps, so every fixture here is name-and-date shaped, and the tests assert
the emitted issue body carries nothing else.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "secret_staleness_check.py"


def _fake_gh(tmp_path: Path, stdout: str, returncode: int = 0, stderr: str = "") -> Path:
    """A `gh` on PATH that prints `stdout`, so the shell-out contract is tested.

    Every pre-#5057 test here stubbed `_gh_json` itself, which is exactly why the
    real `--paginate` parsing, the real `--jq`, and the real `-f labels=` call went
    untested and the job shipped green while reading nothing.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    (tmp_path / "stdout").write_text(stdout)
    (tmp_path / "stderr").write_text(stderr)
    (tmp_path / "args").write_text("")
    script = bindir / "gh"
    script.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$@" >> "{tmp_path / "args"}"\n'
        f'cat "{tmp_path / "stdout"}"\n'
        f'cat "{tmp_path / "stderr"}" >&2\n'
        f"exit {returncode}\n"
    )
    script.chmod(0o755)
    return bindir


def _gh_on_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stdout: str,
    returncode: int = 0,
    stderr: str = "",
) -> None:
    bindir = _fake_gh(tmp_path, stdout, returncode, stderr)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")


def _load() -> object:
    # `sys.modules` first: a `@dataclass` resolves its own module through it, and
    # Python 3.14 raises `AttributeError: 'NoneType' object has no attribute
    # '__dict__'` when a spec-loaded module was never registered.
    spec = importlib.util.spec_from_file_location("secret_staleness_check", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def checker() -> object:
    return _load()


def _age(checker: object, days: int, scope: str = "repo", name: str = "X") -> object:
    stamp = datetime.now(timezone.utc) - timedelta(days=days)
    return checker.Secret(scope, name, stamp)


@pytest.mark.unit
def test_ninety_days_is_overdue_and_ninety_is_not(checker: object) -> None:
    report = checker.Report(secrets=[_age(checker, 91), _age(checker, 90)])
    overdue = report.overdue(90)
    assert [s.name for s in overdue] == ["X"]
    assert overdue[0].age_days == 91


@pytest.mark.unit
def test_overdue_orders_widest_scope_first_then_oldest(checker: object) -> None:
    report = checker.Report(
        secrets=[
            _age(checker, 100, "repo", "repo-100"),
            _age(checker, 200, "repo", "repo-200"),
            _age(checker, 120, "org", "org-120"),
            _age(checker, 95, "cron", "cron-95"),
        ]
    )
    assert [s.name for s in report.overdue(90)] == [
        "org-120",
        "repo-200",
        "repo-100",
        "cron-95",
    ]


@pytest.mark.unit
def test_parse_tsv_reads_scope_name_and_timestamp(checker: object) -> None:
    raw = "repo\tDIGITHINGS_PROJECT_TOKEN\t2026-04-23T19:34:17Z\n\norg\tGROQ_API_KEY\t2026-05-01T02:40:58Z\n"
    parsed = checker.parse_tsv(raw)
    assert [s.scope for s in parsed] == ["repo", "org"]
    assert parsed[0].name == "DIGITHINGS_PROJECT_TOKEN"
    assert parsed[0].updated_at == datetime(2026, 4, 23, 19, 34, 17, tzinfo=timezone.utc)


@pytest.mark.unit
def test_parse_tsv_reads_a_naive_timestamp_as_utc(checker: object) -> None:
    (parsed,) = checker.parse_tsv("repo\tA\t2026-04-23T19:34:17")
    assert parsed.updated_at == datetime(2026, 4, 23, 19, 34, 17, tzinfo=timezone.utc)


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    [
        "repo\tA\n",  # two fields
        "nonsense\tA\t2026-04-23T19:34:17Z\n",  # unknown scope
        "repo\tA\tnot-a-date\n",  # unparseable timestamp
    ],
)
def test_parse_tsv_rejects_malformed_input(checker: object, raw: str) -> None:
    with pytest.raises(ValueError):
        checker.parse_tsv(raw)


@pytest.mark.unit
def test_markdown_lists_only_names_and_ages(checker: object) -> None:
    report = checker.Report(secrets=[_age(checker, 164, "repo", "DIGITHINGS_PROJECT_TOKEN")])
    body = checker.markdown(report, 90)
    assert "DIGITHINGS_PROJECT_TOKEN" in body
    assert "164" in body
    assert checker.ISSUE_MARKER in body
    # The only per-secret interpolation is scope, name, age and date, so the row
    # has exactly four cells. A value could not fit without a fifth.
    row = next(line for line in body.splitlines() if "DIGITHINGS_PROJECT_TOKEN" in line)
    cells = [cell.strip() for cell in row.strip("|").split("|")]
    assert len(cells) == 4
    assert cells[0] == "`repo`"
    assert cells[1] == "`DIGITHINGS_PROJECT_TOKEN`"
    assert cells[2] == "164"
    # The date column is a plain calendar date, so parse it as one. `date` has no
    # timezone by construction, which keeps ruff DTZ007 quiet without a noqa.
    date.fromisoformat(cells[3])


@pytest.mark.unit
def test_a_level_that_read_empty_still_prints(checker: object) -> None:
    # An empty `cron` environment is the signal that #248's migration has not
    # landed, so silence would read as "nothing to see".
    report = checker.Report(secrets=[_age(checker, 10, "repo", "A")])
    out = checker.render(report, 90)
    assert "repo: 1 name(s)" in out
    assert "cron:" not in out  # never collected, so nothing is claimed about it

    migrated = checker.Report(
        secrets=[_age(checker, 10, "repo", "A"), _age(checker, 10, "cron", "B")]
    )
    assert "cron: 1 name(s)" in checker.render(migrated, 90)


@pytest.mark.unit
def test_render_leads_with_the_widest_scope(checker: object) -> None:
    report = checker.Report(
        secrets=[
            _age(checker, 95, "cron", "c"),
            _age(checker, 95, "repo", "r"),
            _age(checker, 95, "org", "o"),
        ]
    )
    lines = [line for line in checker.render(report, 90).splitlines() if ": " in line]
    assert lines[0].startswith("org:")
    assert lines[1].startswith("repo:")
    assert lines[2].startswith("cron:")


@pytest.mark.unit
def test_markdown_says_so_when_nothing_is_overdue(checker: object) -> None:
    report = checker.Report(secrets=[_age(checker, 10)])
    assert "No action needed" in checker.markdown(report, 90)


@pytest.mark.unit
def test_markdown_names_a_level_it_could_not_read(checker: object) -> None:
    report = checker.Report(secrets=[_age(checker, 200)], unavailable={"org": "needs admin:org"})
    body = checker.markdown(report, 90)
    assert "Levels not checked" in body
    assert "admin:org" in body


@pytest.mark.unit
def test_file_or_update_issue_updates_instead_of_duplicating(
    checker: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[list[str], str | None]] = []
    monkeypatch.setattr(
        checker,
        "_gh_json",
        lambda cmd, root, stdin=None: (calls.append((cmd, stdin)), {"number": 1})[1],
    )
    monkeypatch.setattr(checker, "_issue_exists", lambda root, repo: "412")

    result = checker.file_or_update_issue(checker.REPO_ROOT, "o/r", "body")

    assert result == "updated the open tracking issue #412"
    assert len(calls) == 1
    assert calls[0][0][:3] == ["gh", "api", "--method"]
    assert "PATCH" in calls[0][0]
    assert "repos/o/r/issues/412" in calls[0][0]
    assert json.loads(calls[0][1] or "") == {"body": "body"}


@pytest.mark.unit
def test_file_or_update_issue_opens_when_none_is_open(
    checker: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[list[str], str | None]] = []
    monkeypatch.setattr(
        checker,
        "_gh_json",
        lambda cmd, root, stdin=None: (calls.append((cmd, stdin)), {"number": 1})[1],
    )
    monkeypatch.setattr(checker, "_issue_exists", lambda root, repo: None)

    result = checker.file_or_update_issue(checker.REPO_ROOT, "o/r", "body")

    assert result == "opened a new tracking issue"
    assert "POST" in calls[0][0]
    assert "repos/o/r/issues" in calls[0][0]
    assert json.loads(calls[0][1] or "") == {
        "title": checker.ISSUE_TITLE,
        "body": "body",
        "labels": list(checker.ISSUE_LABELS),
    }


@pytest.mark.baseline
@pytest.mark.skipif(
    not os.environ.get("GH_TOKEN") and not os.environ.get("GITHUB_TOKEN"),
    reason="needs an authenticated gh to read the live label list; CI has no token",
)
def test_every_tracker_label_exists_in_the_repo(checker: object) -> None:
    """A label name that does not exist fails the create on its own.

    Run it with `GH_TOKEN=... pytest tests/scripts/test_secret_staleness_check.py -k label`.
    It is not a unit test because it cannot be: `ci.yml` runs `-m "unit or baseline"`
    with no token, so a live call in either lane turns `ruff-and-scripts` red.
    """
    listed = subprocess.run(
        [
            "gh",
            "label",
            "list",
            "--repo",
            "digithings-ai/digithings",
            "--limit",
            "300",
            "--json",
            "name",
            "--jq",
            ".[].name",
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=checker.REPO_ROOT,
    ).stdout
    known = {line.strip() for line in listed.splitlines() if line.strip()}
    assert known, "label list came back empty, so this test would pass vacuously"
    assert not set(checker.ISSUE_LABELS) - known


@pytest.mark.unit
def test_offline_mode_never_calls_gh(
    checker: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    def explode(*args, **kwargs):  # pragma: no cover - the assertion is the point
        raise AssertionError("offline mode must not call gh")

    monkeypatch.setattr(checker, "_gh_json", explode)
    monkeypatch.setattr(checker, "repo_slug", explode)
    names = tmp_path / "names.tsv"
    names.write_text("repo\tOLD\t2026-01-01T00:00:00Z\n", encoding="utf-8")

    code = checker.main(["--file-names", str(names)])

    assert code == 0
    assert "1 name(s) past 90 days" in capsys.readouterr().out


@pytest.mark.unit
def test_fail_overdue_is_opt_in_and_defaults_to_success(
    checker: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(checker, "_gh_json", lambda cmd, root: None)
    monkeypatch.setattr(checker, "repo_slug", lambda root: ("o", "r"))
    names = tmp_path / "names.tsv"
    names.write_text("repo\tOLD\t2026-01-01T00:00:00Z\n", encoding="utf-8")

    assert checker.main(["--file-names", str(names)]) == 0
    assert checker.main(["--file-names", str(names), "--fail-overdue", "--max-age-days", "1"]) == 1


@pytest.mark.unit
def test_strict_offline_flags_an_unreadable_level(
    checker: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(checker, "_gh_json", lambda cmd, root: None)
    monkeypatch.setattr(checker, "repo_slug", lambda root: ("o", "r"))
    names = tmp_path / "names.tsv"
    names.write_text("repo\tFRESH\t2026-01-01T00:00:00Z\n", encoding="utf-8")

    # Every `gh` read comes back None, so no level resolves.
    assert checker.main(["--file-names", str(names), "--strict-offline"]) == 0


# --- environment gates -------------------------------------------------------
# The manifest in `.github/environments.json` is what lets a job share a queueing
# `concurrency` group, and the live comparison is what stops it being a stale excuse.
# The reviewer shape is asserted first because it is the one that fails open: read at
# the wrong depth the environment looks unreviewed, which is exactly the conclusion
# that would let a stall through.

_PRODUCTION_PAYLOAD = {
    "name": "production",
    "deployment_branch_policy": {
        "custom_branch_policies": True,
        "protected_branches": False,
    },
    "protection_rules": [
        {
            "id": 61518665,
            "prevent_self_review": False,
            "type": "required_reviewers",
            "reviewers": [{"type": "User", "reviewer": {"login": "chrizefan", "type": "User"}}],
        },
        {"id": 61518666, "type": "branch_policy"},
    ],
}

_CRON_PAYLOAD = {"name": "cron", "deployment_branch_policy": None, "protection_rules": []}


@pytest.mark.unit
def test_protection_rules_reads_the_nested_reviewer_login(checker: object) -> None:
    rules = checker.protection_rules(_PRODUCTION_PAYLOAD, ["main"])
    assert rules == {
        "wait_timer_minutes": 0,
        "required_reviewers": ["chrizefan"],
        "deployment_branches": ["main"],
    }
    assert checker.can_wait(rules) is True


@pytest.mark.unit
def test_an_unreadable_environment_is_not_mistaken_for_an_unreviewable_one(
    checker: object,
) -> None:
    # Fails *open* if the login were read at the wrong depth, which is why it is a
    # dedicated test rather than an assertion inside the one above.
    shallow = {
        "protection_rules": [{"type": "required_reviewers", "reviewers": [{"type": "User"}]}]
    }
    assert checker.protection_rules(shallow)["required_reviewers"] == []


@pytest.mark.unit
def test_a_wait_timer_alone_also_means_a_run_can_wait(checker: object) -> None:
    rules = checker.protection_rules(
        {"protection_rules": [{"type": "wait_timer", "wait_timer": 5}]}, None
    )
    assert rules["wait_timer_minutes"] == 5
    assert checker.can_wait(rules) is True


@pytest.mark.unit
def test_cron_has_no_protection_rules_at_all(checker: object) -> None:
    rules = checker.protection_rules(_CRON_PAYLOAD, None)
    assert rules == {
        "wait_timer_minutes": 0,
        "required_reviewers": [],
        "deployment_branches": None,
    }
    assert checker.can_wait(rules) is False


@pytest.mark.unit
def test_branch_policy_names_separates_absent_from_empty(checker: object) -> None:
    assert checker.branch_policy_names(None) is None
    assert checker.branch_policy_names({}) is None
    assert checker.branch_policy_names({"branch_policies": []}) == []
    listed = checker.branch_policy_names(
        {"branch_policies": [{"name": "main", "type": "branch"}, {"name": "develop"}]}
    )
    assert listed == ["develop", "main"]


@pytest.mark.unit
def test_drift_names_the_rule_that_changed(checker: object) -> None:
    expected = {
        "wait_timer_minutes": 0,
        "required_reviewers": [],
        "deployment_branches": None,
    }
    assert checker.gate_drift(expected, expected) == []
    drift = checker.gate_drift(expected, dict(expected, required_reviewers=["chrizefan"]))
    assert drift == ["required_reviewers: manifest [], live ['chrizefan']"]


@pytest.mark.unit
def test_the_committed_manifest_matches_what_the_tests_believe(checker: object) -> None:
    """The real file, not a fixture — this is the artefact #2541's exemption rests on."""
    environments = checker.manifest_environments()
    assert "cron" in environments, "the `cron` environment gate is missing from the manifest"
    assert checker.can_wait(environments["cron"]) is False
    assert checker.can_wait(environments["production"]) is True


@pytest.mark.unit
def test_gate_drift_fails_the_run_even_though_no_secret_is_overdue(
    checker: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stale secret is a human's decision; a stalled gate is not.

    Driven through `main` rather than a helper because the property under test is the
    exit code, and `--fail-overdue` must stay off to prove the drift is what failed it.
    """
    gate = {
        "name": "cron",
        "expected": {},
        "actual": {},
        "can_wait": True,
        "drift": ["required_reviewers: manifest [], live ['chrizefan']"],
    }
    monkeypatch.setattr(checker, "repo_slug", lambda root: ("o", "r"))
    monkeypatch.setattr(checker, "collect", lambda root, repo, org, environment: checker.Report())

    def status(root: Path, repo: str, manifest_path: Path | None = None) -> object:
        return ([dict(gate)], {})

    monkeypatch.setattr(checker, "environment_gate_status", status)
    assert checker.main([]) == 1

    monkeypatch.setattr(
        checker, "environment_gate_status", lambda root, repo, manifest_path=None: ([], {})
    )
    assert checker.main([]) == 0


@pytest.mark.unit
def test_offline_mode_does_not_consult_the_live_gate(
    checker: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--file-names` means no `gh` at all, so it must not silently gate on nothing."""
    monkeypatch.setattr(
        checker,
        "environment_gate_status",
        lambda *a, **k: pytest.fail("offline mode must not call the environments API"),
    )
    names = tmp_path / "names.tsv"
    names.write_text("repo\tFRESH\t2026-01-01T00:00:00Z\n", encoding="utf-8")
    assert checker.main(["--file-names", str(names)]) == 0


@pytest.mark.unit
def test_a_missing_manifest_is_reported_as_unverified(checker: object) -> None:
    body = "\n".join(checker.gate_markdown(([], {})))
    assert "unverified" in body


# --- The shell-out contract -----------------------------------------------------
# Everything below drives the real `_gh_json`, through a fake `gh` on PATH, because
# that is the layer the 2026-10-04 false green lived in and no test reached it.

_SECRETS = {"name": "A_SECRET", "updated_at": "2026-01-02T03:04:05Z"}


@pytest.mark.unit
def test_a_secret_listing_spanning_many_pages_is_read_in_full(
    checker: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--paginate` alone prints one JSON document per page, which `json.loads` rejects.

    The live listing is 20 repo secrets; at two per page that is ten documents and
    `Extra data: line 1 column 244`. Every level therefore read as unavailable, and
    unavailable was rendered to the human as "0 of 0 listed secrets".
    """
    pages = [{"secrets": [{**_SECRETS, "name": f"S{page}"}]} for page in range(10)]
    _gh_on_path(monkeypatch, tmp_path, json.dumps(pages))

    secrets, reason = checker.repo_secrets(checker.REPO_ROOT, "o/r")

    assert reason is None
    assert [s.name for s in secrets] == [f"S{page}" for page in range(10)]
    args = (tmp_path / "args").read_text().split()
    assert "--paginate" in args
    assert "--slurp" in args


@pytest.mark.unit
def test_pages_concatenated_without_slurp_are_unavailable_and_not_empty(
    checker: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The old failure mode, pinned: unparseable must read as unavailable, never as empty."""
    _gh_on_path(monkeypatch, tmp_path, json.dumps({"secrets": [_SECRETS]}) * 3)

    secrets, reason = checker.repo_secrets(checker.REPO_ROOT, "o/r")

    assert secrets == []
    assert reason is not None and "unavailable" in reason


@pytest.mark.unit
def test_an_unpaginated_call_gets_no_slurp_and_still_parses(
    checker: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """gh rejects `--slurp` without `--paginate`, so it may only be added to a paged call."""
    _gh_on_path(monkeypatch, tmp_path, json.dumps({"total_count": 1, "secrets": [_SECRETS]}))

    payload = checker._gh_json(["gh", "api", "repos/o/r/actions/secrets"], checker.REPO_ROOT)

    assert "--slurp" not in (tmp_path / "args").read_text().split()
    assert checker._secret_entries(payload) == [_SECRETS]


@pytest.mark.unit
def test_a_server_side_filter_on_a_paged_call_is_refused_not_just_documented(
    checker: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of gh's `--slurp` rule, and the one that bites silently.

    `--slurp` is injected next to every `--paginate`, and gh hard-errors when it finds
    `--jq` or `--template` beside it. A call site that filters server-side would
    therefore die inside CI rather than in a test, which is exactly how the 2026-10-04
    false green happened: correct-looking code, no signal until a run was inspected.
    """
    _gh_on_path(monkeypatch, tmp_path, "{}")
    before = (tmp_path / "args").read_text() if (tmp_path / "args").exists() else ""

    for flag in ("--jq", "--template"):
        with pytest.raises(ValueError, match="--slurp"):
            checker._gh_json(
                ["gh", "api", "--paginate", flag, ".[]", "repos/o/r/issues"],
                checker.REPO_ROOT,
            )

    after = (tmp_path / "args").read_text() if (tmp_path / "args").exists() else ""
    assert after == before, "gh must not be invoked for a command that cannot work"


@pytest.mark.unit
def test_the_tracker_is_found_on_a_page_after_the_first(
    checker: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The old `--jq '[...] | .[0].number'` emitted one `null` per page, so it never found
    the tracker, so the update branch was unreachable and every run tried to create one."""
    pages = [
        [{"number": 1, "state": "open", "title": "unrelated"}],
        [{"number": 412, "state": "open", "title": checker.ISSUE_TITLE}],
        [{"number": 500, "state": "open", "title": "another"}],
    ]
    _gh_on_path(monkeypatch, tmp_path, json.dumps(pages))

    assert checker._issue_exists(checker.REPO_ROOT, "o/r") == "412"


@pytest.mark.unit
def test_no_open_tracker_reads_as_none_rather_than_raising(
    checker: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three pages, no match: the old code handed `json.loads` an empty line per page
    and raised `Expecting value: line 3 column 1`, which is the run log's error."""
    pages = [[{"number": 1, "state": "open", "title": "unrelated"}] for _ in range(3)]
    _gh_on_path(monkeypatch, tmp_path, json.dumps(pages))

    assert checker._issue_exists(checker.REPO_ROOT, "o/r") is None


@pytest.mark.unit
def test_a_closed_tracker_is_not_the_open_one(
    checker: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pages = [[{"number": 7, "state": "closed", "title": checker.ISSUE_TITLE}]]
    _gh_on_path(monkeypatch, tmp_path, json.dumps(pages))

    assert checker._issue_exists(checker.REPO_ROOT, "o/r") is None


@pytest.mark.unit
def test_the_create_body_is_json_with_a_label_array(
    checker: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`-f labels=ops` sent a string and `ops` does not exist, so the create 400'd with
    only `Invalid request` and the tracker never appeared. The body is JSON now."""
    _gh_on_path(monkeypatch, tmp_path, json.dumps([[]]))
    sent: list[str] = []
    real = checker._gh_json

    def spy(cmd: list[str], root: Path, stdin: str | None = None) -> object:
        if stdin is not None:
            sent.append(stdin)
        return real(cmd, root, stdin)

    monkeypatch.setattr(checker, "_gh_json", spy)

    checker.file_or_update_issue(checker.REPO_ROOT, "o/r", "body")

    assert len(sent) == 1
    body = json.loads(sent[0])
    assert body["title"] == checker.ISSUE_TITLE
    assert isinstance(body["labels"], list)
    assert body["labels"] == list(checker.ISSUE_LABELS)


@pytest.mark.unit
def test_markdown_never_calls_an_unread_level_clean(checker: object) -> None:
    report = checker.Report(secrets=[_age(checker, 10)], unavailable={"cron": "HTTP 403"})
    body = checker.markdown(report, 90)

    assert "No action needed" not in body
    assert "not a clean bill of health" in body
    assert "`cron`" in body


@pytest.mark.unit
def test_the_workflow_does_not_claim_a_permission_that_cannot_read_secrets(checker: object) -> None:
    """`actions: read` was granted in #5063 and proved useless by run 37235973852.

    The Actions secrets endpoints need a token carrying the `repo` scope.
    GITHUB_TOKEN is a GitHub App installation token and the `permissions:`
    vocabulary has no key for secrets, so `Actions: read` appeared in the job
    banner and every listing still answered 403. Asserting it is absent keeps a
    future run from re-adding a permission that widens the token and buys
    nothing, and keeps the comment beside it honest.
    """
    workflow = yaml.safe_load(
        (_REPO_ROOT / ".github" / "workflows" / "secret-staleness-check.yml").read_text()
    )
    permissions = workflow["permissions"]

    assert "actions" not in permissions
    assert permissions.get("contents") == "read"
    assert permissions.get("issues") == "write"


@pytest.mark.unit
def test_the_workflow_says_the_secret_listings_cannot_be_read_here(checker: object) -> None:
    """The header is the only place a reader learns why the ageing half is absent.

    Before 2026-10-04 it claimed the job "needs no credential beyond the
    automatic GITHUB_TOKEN", which is what sent #5063 looking for a permission
    that does not exist. The proof is the run id, so the claim is pinned to it.
    """
    text = (_REPO_ROOT / ".github" / "workflows" / "secret-staleness-check.yml").read_text()

    assert "37235973852" in text
    assert "CANNOT be read from this workflow" in text
    assert "needs no credential" not in text


@pytest.mark.unit
def test_a_run_that_aged_nothing_opens_no_tracker(
    checker: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every level unread is the normal case from CI.

    Filing a tracker whose body is "I read nothing" reads like a working
    rotation control and is not one. A monthly issue that only ever says it
    could not do its job also trains readers to ignore the one issue that would
    carry real names.

    The assertion is on the call, not on stdout. Asserting the issue title was
    absent from stdout passed even when filing was unconditional, because the
    fake `gh` never prints the title it was sent.
    """
    _gh_on_path(
        monkeypatch,
        tmp_path,
        stdout="",
        returncode=1,
        stderr="gh: Resource not accessible by integration (HTTP 403)",
    )
    monkeypatch.setattr(checker, "repo_slug", lambda root: ("o", "r"))
    opened: list[str] = []
    monkeypatch.setattr(
        checker, "file_or_update_issue", lambda root, slug, body: opened.append(slug) or "opened"
    )
    cleared: list[str] = []
    monkeypatch.setattr(
        checker,
        "close_unmeasurable_tracker",
        lambda root, slug: cleared.append(slug) or "no tracker is open",
    )

    code = checker.main(["--skip-environment-gates", "--open-issue"])

    assert code == 0
    assert opened == []
    assert cleared == ["o/r"]


@pytest.mark.unit
def test_an_unmeasurable_tracker_is_annotated_and_closed_not_left_open(
    checker: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Skipping the write was not enough on its own.

    The tracker opened by run 37235973852 was already open and empty when this
    was written, carrying `security:finding` and a body saying nothing had been
    read. A guard that only stops *new* empty trackers leaves that one sitting
    forever while the docs claim the clock files none. Silence here is
    indistinguishable from "still running".
    """
    monkeypatch.setattr(checker, "repo_slug", lambda root: ("o", "r"))
    posted: list[tuple[str, str]] = []

    def fake_gh_json(cmd, root, stdin=None):
        # Every secret listing is a plain `--paginate` read with no `--method`, and
        # an unreadable one has to answer None. Only the writes are recorded.
        if "--method" not in cmd:
            return None
        verb = cmd[cmd.index("--method") + 1]
        target = next(a for a in cmd if a.startswith("repos/") and "/issues" in a)
        if verb == "POST" and target.endswith("/comments"):
            posted.append(("comment", json.loads(stdin)["body"]))
            return {"id": 1}
        if verb == "PATCH":
            posted.append(("close", target))
            return {"number": 5065}
        return None

    monkeypatch.setattr(checker, "_gh_json", fake_gh_json)
    monkeypatch.setattr(checker, "_issue_exists", lambda root, repo: "5065")

    code = checker.main(["--skip-environment-gates", "--open-issue"])

    assert code == 0
    kinds = [kind for kind, _ in posted]
    assert kinds == ["comment", "close"], posted
    note = posted[0][1]
    assert "security:finding" in note
    assert "SECRETS_INVENTORY.md" in note
    assert "repo` scope" in note
    assert "closed" in capsys.readouterr().out


@pytest.mark.unit
def test_an_unmeasurable_tracker_is_left_open_when_the_note_cannot_be_written(
    checker: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Closing without the explanation would be worse than staying open.

    The comment lands before the close on purpose. If it cannot be written, the
    issue keeps counting as an open finding and the operator can see that
    something is still wrong, rather than finding a closed issue that never
    says why.
    """
    _gh_on_path(
        monkeypatch,
        tmp_path,
        stdout="",
        returncode=1,
        stderr="gh: Resource not accessible by integration (HTTP 403)",
    )
    monkeypatch.setattr(checker, "repo_slug", lambda root: ("o", "r"))
    seen: list[str] = []
    monkeypatch.setattr(
        checker,
        "_gh_json",
        lambda cmd, root, stdin=None: (seen.append(cmd[3]), None)[1],
    )
    monkeypatch.setattr(checker, "_issue_exists", lambda root, repo: "5065")

    checker.main(["--skip-environment-gates", "--open-issue"])

    assert "PATCH" not in seen, "must not close when the note did not land"
    out = capsys.readouterr().out
    assert "FAILED" in out
    assert "left open" in out


@pytest.mark.unit
def test_a_run_that_aged_something_does_file_the_tracker(
    checker: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The converse, so the guard above cannot be satisfied by never filing.

    This is the path the operator shell and the Keymaster report take, and it is
    the only one that has ever produced a useful tracker.
    """
    _gh_on_path(monkeypatch, tmp_path, stdout=json.dumps([{"secrets": [_SECRETS]}]))
    monkeypatch.setattr(checker, "repo_slug", lambda root: ("o", "r"))
    filed: list[str] = []
    monkeypatch.setattr(
        checker, "file_or_update_issue", lambda root, slug, body: filed.append(slug) or "opened"
    )

    code = checker.main(["--skip-environment-gates", "--open-issue"])

    assert code == 0
    assert filed == ["o/r"]
    assert "filed nothing" not in capsys.readouterr().out


@pytest.mark.unit
@pytest.mark.parametrize(
    ("call", "args", "scope", "cites_run"),
    [
        ("repo_secrets", ("o/r",), "`repo` scope", True),
        ("org_secrets", ("o",), "admin:org", False),
        ("environment_secrets", ("o/r", "cron"), "`repo` scope", True),
    ],
)
def test_an_unreadable_level_says_which_scope_would_fix_it(
    checker: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    call: str,
    args: tuple[str, ...],
    scope: str,
    cites_run: bool,
) -> None:
    """`repo secret list unavailable for o/r` is true and actionable for nobody.

    The Actions secrets endpoints need the `repo` scope. A reader seeing the old
    reason has no way to know that no `permissions:` grant can supply it, which is
    what sent #5063 hunting for a permission that does not exist.

    All three levels are pinned. Pinning only `repo` left the `org` and `cron`
    reasons free to rot back to their bare form with the suite still green.
    """
    _gh_on_path(
        monkeypatch,
        tmp_path,
        stdout="",
        returncode=1,
        stderr="gh: Resource not accessible by integration (HTTP 403)",
    )

    secrets, reason = getattr(checker, call)(checker.REPO_ROOT, *args)

    assert secrets == []
    assert reason is not None
    # Each level names the scope that level actually needs: the org listing is
    # gated on `admin:org`, not on `repo`, so it does not cite the run either.
    assert scope in reason
    assert ("37235973852" in reason) is cites_run


@pytest.mark.unit
def test_a_secret_with_an_unreadable_date_is_reported_not_dropped(
    checker: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dropping it would shrink the denominator and let the run say nothing is overdue."""
    pages = [{"secrets": [_SECRETS, {"name": "ODD", "updated_at": "never"}]}]
    _gh_on_path(monkeypatch, tmp_path, json.dumps(pages))

    secrets, reason = checker.repo_secrets(checker.REPO_ROOT, "o/r")

    assert secrets == []
    assert reason is not None and "ODD" in reason


@pytest.mark.unit
def test_a_secret_with_no_date_at_all_is_reported_not_dropped(
    checker: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pages = [{"secrets": [{"name": "ODD", "updated_at": None}]}]
    _gh_on_path(monkeypatch, tmp_path, json.dumps(pages))

    secrets, reason = checker.repo_secrets(checker.REPO_ROOT, "o/r")

    assert secrets == []
    assert reason is not None and "ODD" in reason


@pytest.mark.unit
def test_an_unreadable_issue_list_files_nothing_rather_than_a_duplicate(
    checker: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """None means "no tracker is open". A failed read must not be read that way."""
    posted: list[list[str]] = []
    _gh_on_path(monkeypatch, tmp_path, "", returncode=1)
    real = checker._gh_json

    def spy(cmd: list[str], root: Path, stdin: str | None = None) -> object:
        if "--method" in cmd:
            posted.append(cmd)
        return real(cmd, root, stdin)

    monkeypatch.setattr(checker, "_gh_json", spy)

    result = checker.file_or_update_issue(checker.REPO_ROOT, "o/r", "body")

    assert "filed nothing" in result
    assert posted == []


@pytest.mark.unit
def test_a_refused_create_is_reported_as_failed(
    checker: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The create used to claim success on a 422, so the tracker silently never existed."""
    monkeypatch.setattr(checker, "_gh_json", lambda cmd, root, stdin=None: None)
    monkeypatch.setattr(checker, "_issue_exists", lambda root, repo: None)

    assert "FAILED" in checker.file_or_update_issue(checker.REPO_ROOT, "o/r", "body")


@pytest.mark.unit
def test_a_refused_update_is_reported_as_failed(
    checker: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(checker, "_gh_json", lambda cmd, root, stdin=None: None)
    monkeypatch.setattr(checker, "_issue_exists", lambda root, repo: "412")

    result = checker.file_or_update_issue(checker.REPO_ROOT, "o/r", "body")

    assert "FAILED" in result and "412" in result


@pytest.mark.unit
def test_the_stdin_body_reaches_gh_rather_than_being_dropped(
    checker: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_gh_json` gaining a `stdin` argument is plumbing; this is what proves it is wired."""
    body = tmp_path / "bin" / "gh"
    _gh_on_path(monkeypatch, tmp_path, "{}")
    body.write_text(
        body.read_text().replace(
            f'cat "{tmp_path / "stderr"}" >&2',
            f'cat >> "{tmp_path / "seen"}"',
        )
    )
    body.chmod(0o755)

    checker._gh_json(["gh", "api", "repos/o/r"], checker.REPO_ROOT, stdin='{"title":"x"}')

    assert (tmp_path / "seen").read_text() == '{"title":"x"}'


@pytest.mark.unit
def test_no_summary_counts_zero_of_zero_as_a_clean_result(checker: object) -> None:
    """ "0 of 0 listed secrets are past 90 days" is a claim about an empty set."""
    report = checker.Report(unavailable={"cron": "HTTP 403", "org": "needs admin:org"})
    body = checker.markdown(report, 90)

    assert "0 of 0" not in body.replace("**", "")
    assert "No secrets could be aged" in body
    assert "No action needed" not in body


@pytest.mark.unit
def test_the_summary_still_reassures_when_everything_was_read(
    checker: object,
) -> None:
    body = checker.markdown(checker.Report(secrets=[_age(checker, 10)]), 90)

    assert "No action needed" in body
    assert "of **1** listed secrets" in body
