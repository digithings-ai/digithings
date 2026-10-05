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
def test_a_level_that_was_never_collected_does_not_print(checker: object) -> None:
    # A level absent from `secrets` is one that was never collected, so nothing is
    # claimed about it either way. The name used to be `..._still_prints` with a
    # comment saying silence would read as "nothing to see", which asserted the
    # opposite of what the line below checks: an uncollected `cron` is silent.
    # Whether a served-but-empty level should print is not answerable from `Report`
    # without `readable`, and `ageing_verdict` is what covers that case now.
    report = checker.Report(secrets=[_age(checker, 10, "repo", "A")], readable=1)
    out = checker.render(report, 90)
    assert "repo: 1 name(s)" in out
    assert "cron:" not in out  # never collected, so nothing is claimed about it

    migrated = checker.Report(
        secrets=[_age(checker, 10, "repo", "A"), _age(checker, 10, "cron", "B")], readable=2
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

    # Every `gh` read comes back None, so no level resolves. `--file-names` still
    # means the live API was never consulted, so `--strict-offline` refuses it
    # rather than reporting success off a hand-made file.
    assert checker.main(["--file-names", str(names), "--strict-offline"]) == 1
    # Without the flag the file is just a list to age, which is what the flag is for.
    assert checker.main(["--file-names", str(names), "--strict-offline"]) != checker.main(
        ["--file-names", str(names)]
    )


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
    # `issues: write` was asserted here while the ageing half still filed a tracker.
    # DIG-477 option D removed the ageing, so nothing in the job writes an issue and
    # the grant is gone — `test_the_workflow_runs_the_gates_only_mode_and_needs_no_issues_scope`
    # pins that it stays gone.
    assert "issues" not in permissions


@pytest.mark.unit
def test_the_workflow_says_the_secret_listings_cannot_be_read_here(checker: object) -> None:
    """The header is the only place a reader learns why the ageing half is absent.

    Before 2026-10-04 it claimed the job "needs no credential beyond the
    automatic GITHUB_TOKEN", which is what sent #5063 looking for a permission
    that does not exist. The proof is the run id, so the claim is pinned to it.
    """
    text = (_REPO_ROOT / ".github" / "workflows" / "secret-staleness-check.yml").read_text()

    assert "37235973852" in text
    assert "CANNOT be read from a workflow" in text
    assert "needs no credential" not in text
    # Option D kept this header honest by inverting its purpose: the ageing half is
    # gone from CI by decision, so the header has to say which half runs and why
    # the other cannot, not merely that something failed.
    assert "DIG-477" in text
    assert "One thing" in text


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

    This is the path the operator shell on the Mac takes, and it is the only one
    that has ever produced a useful tracker. It is NOT the Keymaster weekly key
    report: that report is built from Bitwarden and never reads this API.
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


@pytest.mark.unit
def test_stdout_does_not_count_zero_of_zero_as_a_clean_result(checker: object) -> None:
    """`render()` printed `0 name(s) past 90 days of 0 listed` while every level 403'd.

    The summary half of this was already fixed; the console half was not, so the run
    log still ended on a zero count. Both renderers have to agree.
    """
    report = checker.Report(unavailable={"cron": "HTTP 403", "org": "needs admin:org"})
    out = checker.render(report, 90)

    assert "of 0 listed" not in out
    assert "0 name(s) past 90 days of 0" not in out
    assert "No secrets could be aged" in out
    # The per-level reasons still print, so the reader learns *why* nothing aged.
    assert "NOT CHECKED" in out


@pytest.mark.unit
def test_stdout_count_is_qualified_when_only_some_levels_read(checker: object) -> None:
    """A partial read must not print a bare count either: 1 read of 2 levels is not a verdict."""
    report = checker.Report(secrets=[_age(checker, 200)], unavailable={"org": "needs admin:org"})
    out = checker.render(report, 90)

    assert "1 name(s) past 90 days of 1 listed" not in out
    assert "among the 1 that could be read" in out
    assert "not a clean bill of health" in out


@pytest.mark.unit
def test_stdout_qualifies_a_partial_read_when_nothing_is_overdue(checker: object) -> None:
    """The zero-overdue partial read is the shape closest to the original bug.

    Nothing is overdue, so the count reads `0`, and a bare `0 name(s) past 90
    days` line is exactly what a skimming reader parses as a clean result.
    """
    report = checker.Report(secrets=[_age(checker, 10)], unavailable={"org": "needs admin:org"})
    out = checker.render(report, 90)

    assert "0 name(s) past 90 days of 1 listed" not in out
    assert "among the 1 that could be read" in out
    assert "not a clean bill of health" in out


@pytest.mark.unit
def test_a_partial_read_with_something_overdue_is_qualified_in_the_summary(checker: object) -> None:
    """An overdue name plus an unread level must not lead with a bare `1 of 1`.

    The partial-read qualifier used to sit behind `if overdue:`, so it was
    unreachable in precisely this case and the summary — the artefact a human
    reads first — disclosed the missing level only in the trailing section.
    """
    report = checker.Report(secrets=[_age(checker, 200)], unavailable={"org": "needs admin:org"})
    body = checker.markdown(report, 90)

    assert "not a clean bill of health" in body
    assert "of the levels that could be read" in body


@pytest.mark.unit
def test_an_empty_but_readable_repo_is_not_reported_as_a_failed_read(checker: object) -> None:
    """Every level readable, none holding a secret: a real answer, not a 0-of-0.

    `collect()` returns `([], None)` for a level that reads but is empty, so this
    lands in neither `secrets` nor `unavailable` and is reachable. The old code
    printed `0 name(s) past 90 days of 0 listed` on stdout and claimed on the
    summary that nothing had been read — both false.
    """
    report = checker.Report(readable=3)

    out = checker.render(report, 90)
    assert "of 0 listed" not in out
    assert "Every level was readable" in out

    body = checker.markdown(report, 90)
    assert "No secrets could be aged" not in body
    assert "because nothing was read" not in body
    assert "Every level was readable" in body


@pytest.mark.unit
def test_an_offline_report_never_claims_a_level_was_read(checker: object) -> None:
    """`--file-names` reads a hand-made list, not the API. That is not a served level.

    With no `readable` count and nothing in `unavailable`, an earlier version
    printed "Every level was readable and none of them holds a secret" over a
    zero-byte file and exited 0 — a clean bill of health for a measurement that
    never happened, which is the exact class of bug this change exists to remove.
    """
    report = checker.Report(readable=0)

    assert not report.read_any
    assert "readable" not in checker.render(report, 90)
    assert "readable" not in checker.markdown(report, 90)
    assert "No secrets could be aged" in checker.render(report, 90)


@pytest.mark.unit
def test_a_served_but_empty_run_files_a_tracker_instead_of_closing_one(
    checker: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run that measured something must not close the tracker on the "read nothing" note.

    `CLOSE_NOTE` asserts, permanently and in the repo's voice, that every level came
    back 403. A run where the listings were served and came back empty prints
    "Every level was readable" on stdout — so closing it on that note would put two
    mutually exclusive claims in the same run, one of them permanent.
    """
    served_but_empty = checker.Report(readable=3)
    acted: list[str] = []

    monkeypatch.setattr(checker, "repo_slug", lambda root: ("o", "r"))
    monkeypatch.setattr(checker, "collect", lambda *a, **k: served_but_empty)
    monkeypatch.setattr(checker, "environment_gate_status", lambda *a, **k: None)
    monkeypatch.setattr(
        checker, "close_unmeasurable_tracker", lambda root, repo: acted.append("close") or ""
    )
    monkeypatch.setattr(
        checker, "file_or_update_issue", lambda root, repo, body: acted.append("file") or ""
    )

    checker.main(["--open-issue", "--skip-environment-gates"])

    assert acted == ["file"]


@pytest.mark.unit
def test_a_run_that_read_nothing_still_closes_the_tracker(
    checker: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard the test above pins: the unreadable case must keep closing."""
    unreadable = checker.Report(unavailable={"cron": "403", "org": "403", "repo": "403"})
    acted: list[str] = []

    monkeypatch.setattr(checker, "repo_slug", lambda root: ("o", "r"))
    monkeypatch.setattr(checker, "collect", lambda *a, **k: unreadable)
    monkeypatch.setattr(checker, "environment_gate_status", lambda *a, **k: None)
    monkeypatch.setattr(
        checker, "close_unmeasurable_tracker", lambda root, repo: acted.append("close") or ""
    )
    monkeypatch.setattr(
        checker, "file_or_update_issue", lambda root, repo, body: acted.append("file") or ""
    )

    checker.main(["--open-issue", "--skip-environment-gates"])

    assert acted == ["close"]


@pytest.mark.unit
def test_the_two_renderers_never_disagree_about_the_verdict(checker: object) -> None:
    """The invariant both renderers must satisfy, over every reachable shape.

    They were two hand-maintained copies of one judgement and they drifted, so the
    agreement is pinned here rather than asserted in a comment. Each renderer is
    given the position word its own layout needs, because one shared sentence
    cannot be true in both orderings.
    """
    old, fresh = _age(checker, 200), _age(checker, 10)
    unread = {"cron": "403", "org": "403", "repo": "403"}
    shapes = {
        "nothing readable": checker.Report(unavailable=unread),
        "offline file, empty": checker.Report(readable=0),
        "partial, nothing overdue": checker.Report(
            secrets=[fresh], unavailable={"org": "403"}, readable=2
        ),
        "partial, overdue": checker.Report(secrets=[old], unavailable={"org": "403"}, readable=2),
        "full read, nothing overdue": checker.Report(secrets=[fresh], readable=3),
        "full read, overdue": checker.Report(secrets=[old], readable=3),
        "full read, empty": checker.Report(readable=3),
    }

    for label, report in shapes.items():
        on_stdout = checker.ageing_verdict(report, 90, "above")
        in_summary = checker.ageing_verdict(report, 90, "below")

        assert on_stdout in checker.render(report, 90), label
        assert in_summary in checker.markdown(report, 90), label

        # The "per-level reason is above/below" clause only exists when the reasons
        # are listed at all, i.e. when nothing could be read. Where some level did
        # read, the partial-read sentence carries the disclosure instead.
        # The position word is only carried in the "nothing could be aged at all" shape,
        # the one that names per-level reasons. A partial read discloses the gap in its
        # own sentence, and a fully-read or fully-offline run has no reasons to point at.
        if report.unavailable and not report.read_any:
            assert "The per-level reason is above." in checker.render(report, 90), label
            assert "The per-level reason is below." in checker.markdown(report, 90), label

        if not report.read_any or report.unavailable:
            assert "No action needed" not in checker.markdown(report, 90), label


@pytest.mark.unit
def test_stdout_still_counts_when_every_level_read(checker: object) -> None:
    """The fix must not cost the ordinary case its count line."""
    report = checker.Report(secrets=[_age(checker, 200)])
    out = checker.render(report, 90)

    assert "1 name(s) past 90 days of 1 listed" in out
    assert "No secrets could be aged" not in out


# ---------------------------------------------------------------------------
# DIG-477 option D: the ageing half is out of automation by decision.
#
# Chris, 2026-10-05, chose D: keep the drift check, drop the ageing. So the CI
# path must not attempt the three secret listings at all. Every test below fails
# against the pre-D behaviour, because pre-D the workflow *did* call them and
# printed three NOT CHECKED lines every run.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_gates_only_never_collects_or_opens_a_tracker(
    checker: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    def explode_collect(*args, **kwargs):  # pragma: no cover - the assertion is the point
        raise AssertionError("--gates-only must not call collect()")

    def explode_issue(*args, **kwargs):  # pragma: no cover - the assertion is the point
        raise AssertionError("--gates-only must not touch a tracker")

    monkeypatch.setattr(checker, "collect", explode_collect)
    monkeypatch.setattr(checker, "file_or_update_issue", explode_issue)
    monkeypatch.setattr(checker, "close_unmeasurable_tracker", explode_issue)
    monkeypatch.setattr(checker, "repo_slug", lambda root: ("o", "r"))
    monkeypatch.setattr(
        checker,
        "environment_gate_status",
        lambda root, slug: ([{"name": "cron", "actual": {}, "can_wait": False, "drift": []}], {}),
    )

    assert checker.main(["--gates-only"]) == 0

    out = capsys.readouterr().out
    assert "environment gates: 1 checked" in out
    assert "NOT RUN" in out


@pytest.mark.unit
def test_gates_only_still_fails_on_gate_drift(
    checker: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dropping the ageing must not soften the half that works.

    DIG-248 depends on this drift check, and it is the reason the workflow
    exists. A drifted gate silently stops every pipeline gated on it, so it
    exits 1 unconditionally.
    """
    monkeypatch.setattr(checker, "collect", lambda *a, **k: checker.Report())
    monkeypatch.setattr(checker, "repo_slug", lambda root: ("o", "r"))
    monkeypatch.setattr(
        checker,
        "environment_gate_status",
        lambda root, slug: (
            [{"name": "cron", "actual": {}, "can_wait": True, "drift": ["reviewer armed"]}],
            {},
        ),
    )

    assert checker.main(["--gates-only"]) == 1


@pytest.mark.unit
def test_gates_only_does_not_sound_like_a_failure(checker: object) -> None:
    """A monthly green run must not read as a red one.

    `ageing_verdict`'s "nothing was read" branch is true in gates-only mode and
    reads as a failure, which would put a red-sounding sentence on the run page
    every month and train readers to ignore it. Same defect as #5078, opposite
    direction.
    """
    report = checker.Report()
    gates = ([{"name": "cron", "actual": {}, "can_wait": False, "drift": []}], {})
    body = checker.markdown(report, 90, gates, gates_only=True)

    assert "NOT RUN" in body
    assert "No secrets could be aged" not in body
    # No level may be *reported* as unchecked. The phrase `NOT CHECKED` appears in
    # the note that explains why nothing was attempted, so assert on the per-level
    # reporting form the renderers actually emit, not on the bare phrase.
    assert "## Levels not checked" not in body
    assert "NOT CHECKED —" not in body
    assert "docs/ops/SECRETS_INVENTORY.md" in body


@pytest.mark.unit
def test_the_workflow_runs_the_gates_only_mode_and_needs_no_issues_scope(
    checker: object,
) -> None:
    """The workflow is the thing that has to change for D to be true.

    Pre-D it passed `--open-issue` and `issues: write`, which bought a job
    token permission to write an issue that can only ever say "I read nothing".
    With the ageing gone, nothing in the job writes an issue, so the grant is
    dead weight on the same token that #5063 proved cannot read secrets.
    """
    workflow = yaml.safe_load(
        (_REPO_ROOT / ".github" / "workflows" / "secret-staleness-check.yml").read_text()
    )
    text = (_REPO_ROOT / ".github" / "workflows" / "secret-staleness-check.yml").read_text()

    run_steps = " ".join(str(step.get("run", "")) for step in workflow["jobs"]["check"]["steps"])

    assert "--gates-only" in run_steps
    assert "--open-issue" not in run_steps
    assert "issues" not in workflow["permissions"]
    # The ageing input is meaningless once nothing is aged.
    assert "max_age_days" not in text
    assert "DIG-477" in text
