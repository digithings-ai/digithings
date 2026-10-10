"""Tests for the production deploy gate-latency watchdog (DIG-1569).

The gate watchdog's whole value is that it is trusted. A watchdog that reports
"all clear" when it could not read the gate is worse than no watchdog — it
converts a blind spot into false assurance, which is exactly the failure mode the
DIG-1484 incident ran on for 19 hours. So the fail-closed path is tested as
carefully as the alerting path.

The pure core is tested without network, ``gh`` or secrets; only the shell that
wires it to GitHub is exercised separately, and only for the wiring.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

# `make test-unit` and ci.yml both run `-m unit`; an unmarked file is deselected
# entirely, so an unmarked test is a test that never runs.
pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "production_deploy_gate_latency.py"
WATCHDOG = REPO_ROOT / ".github" / "workflows" / "production-deploy-gate-watchdog.yml"

sys.path.insert(0, str(REPO_ROOT / "scripts"))

from production_deploy_gate_latency import (  # noqa: E402
    DEFAULT_MAX_AGE_MINUTES,
    ISSUE_MARKER,
    UNFINISHED_STATES,
    GateCheckFailed,
    apply_latest_statuses,
    file_or_update_issue,
    find_open_issue,
    is_unfinished,
    render_issue_body,
    stale_deployments,
)

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def _deployment(
    *,
    deployment_id: int = 1,
    state: str = "pending",
    minutes_old: int = 90,
    environment: str = "production",
    ref: str = "main",
    sha: str = "da88fa715e32a737572950ec46d0c0d6096614ac",
    creator: str = "chrisstefan",
) -> dict[str, Any]:
    created = NOW - timedelta(minutes=minutes_old)
    return {
        "id": deployment_id,
        "sha": sha,
        "ref": ref,
        "environment": environment,
        "state": state,
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "creator": {"login": creator},
    }


def _api_deployment(
    *,
    deployment_id: int = 6892915678,
    minutes_old: int = 90,
    environment: str = "production",
    ref: str = "main",
    sha: str = "da88fa715e32a737572950ec46d0c0d6096614ac",
    creator: str = "chrisstefan",
) -> dict[str, Any]:
    """A deployment row shaped like the real one from the digithings API.

    This fixture exists because the happy-path fixture above lied. ``_deployment``
    invents a ``state`` field that the actual endpoints never return: the list
    payload has no ``state`` key at all, and the per-deployment GET returns
    ``"state": null``. Every test built on the invented shape passed while the
    watchdog classified nothing, so the realistic shape is pinned here.
    """
    created = NOW - timedelta(minutes=minutes_old)
    return {
        "id": deployment_id,
        "sha": sha,
        "ref": ref,
        "environment": environment,
        "task": "deploy",
        "payload": {},
        "original_environment": environment,
        "transient_environment": False,
        "production_environment": True,
        "description": None,
        "creator": {"login": creator},
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "updated_at": created.isoformat().replace("+00:00", "Z"),
        "statuses_url": (
            "https://api.github.com/repos/digithings-ai/digithings"
            f"/deployments/{deployment_id}/statuses"
        ),
        "repository_url": "https://api.github.com/repos/digithings-ai/digithings",
        "url": (
            f"https://api.github.com/repos/digithings-ai/digithings/deployments/{deployment_id}"
        ),
        "performed_via_github_app": None,
    }


# ── classification ───────────────────────────────────────────────────────────


def test_a_fresh_pending_deployment_is_not_an_alert() -> None:
    assert stale_deployments([_deployment(minutes_old=5)], now=NOW) == []


def test_a_pending_deployment_past_the_threshold_is_an_alert() -> None:
    stale = stale_deployments([_deployment(minutes_old=90)], now=NOW)
    assert len(stale) == 1
    assert stale[0].age_minutes == 90
    assert stale[0].short_sha == "da88fa71"  # 8 chars, per the repo's review-coverage sha
    assert stale[0].ref == "main"


def test_the_digithings_case_alerts_at_the_default_threshold() -> None:
    """The three real deployments: 14.5h, 6h and 0h old.

    Two must alert at the default 60 minutes; the brand-new one must not, so the
    watchdog does not fire on every single merge.
    """
    rows = [
        _deployment(deployment_id=1, minutes_old=int(14.5 * 60)),
        _deployment(deployment_id=2, minutes_old=360),
        _deployment(deployment_id=3, minutes_old=0),
    ]
    stale = stale_deployments(rows, now=NOW)
    assert [d.deployment_id for d in stale] == [1, 2]
    assert stale[0].age_minutes == 870


def test_deployments_already_finished_are_never_alerts() -> None:
    """A finished deploy must not page anyone.

    Kept inside the lookback window on purpose: outside it the row would be skipped
    before classification and this assertion would pass without testing the state
    at all. The window's own behaviour is asserted separately below.
    """
    for state in ("success", "failure", "error", "inactive"):
        rows = [_deployment(minutes_old=200, state=state)]
        assert stale_deployments(rows, now=NOW) == [], state


@pytest.mark.parametrize(
    "state", ["pending", "queued", "in_progress", "waiting"]
)  # hardcoded, not UNFINISHED_STATES: a test parametrized from the constant it
# claims to pin stops asserting any state deleted from that constant.
def test_every_unfinished_state_is_caught(state: str) -> None:
    assert len(stale_deployments([_deployment(state=state, minutes_old=120)], now=NOW)) == 1


def test_the_hardcoded_state_list_matches_the_constant() -> None:
    """Keeps the hardcoded list above honest about the constant it duplicates."""
    assert {"pending", "queued", "in_progress", "waiting"} == set(UNFINISHED_STATES)


def test_a_deployment_on_another_environment_is_ignored() -> None:
    rows = [_deployment(environment="staging", minutes_old=600)]
    assert stale_deployments(rows, now=NOW) == []


def test_the_predicate_itself_treats_blank_as_unfinished() -> None:
    for blank in (None, "", "   "):
        assert is_unfinished(blank) is True, blank
    for done in ("success", "inactive", "failure", "error"):
        assert is_unfinished(done) is False, done


def test_a_deployment_from_before_the_lookback_window_is_not_reported_as_stalled() -> None:
    """The third DIG-1569 bug, found by running the script for real.

    Rows outside the lookback window never get a status read, so they arrive
    unresolved. An unresolved state counts as unfinished (fail closed), which is
    right for a row we failed to read and wrong for a row we deliberately skipped.
    Filtering after classification instead of before it reported **149** finished
    deployments on the first live run, the oldest 102 days old.
    """
    ancient = _api_deployment(deployment_id=5214938328, minutes_old=60 * 24 * 102)
    rows = apply_latest_statuses([ancient], {})  # {} — deliberately never read
    assert rows[0]["state"] == "unknown"
    assert stale_deployments(rows, now=NOW) == []


def test_the_lookback_window_is_configurable_and_defaults_to_a_day() -> None:
    from production_deploy_gate_latency import LOOKBACK_HOURS

    assert LOOKBACK_HOURS == 24
    ancient = _api_deployment(minutes_old=60 * 30)
    rows = apply_latest_statuses([ancient], {})
    assert stale_deployments(rows, now=NOW) == []
    assert len(stale_deployments(rows, now=NOW, lookback_hours=48)) == 1


def test_an_issue_api_outage_does_not_suppress_the_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The channels are independent: neither may take the other down with it."""
    import production_deploy_gate_latency as mod

    def boom(*a: object, **k: object) -> str:
        raise GateCheckFailed("GitHub Issues is down")

    monkeypatch.setattr(mod, "fetch_deployments", lambda *a, **k: [_deployment(minutes_old=870)])
    monkeypatch.setattr(mod, "file_or_update_issue", boom)
    emailed: list[str] = []
    monkeypatch.setattr(
        mod, "notify_email", lambda subject, body, *, dry_run: emailed.append(subject) or "sent"
    )
    assert mod.main(["--now", NOW.isoformat(), "--dry-run"]) == 2
    assert len(emailed) == 1, "the email must still fire when the issue write fails"


def test_a_recovered_gate_closes_the_issue_it_filed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Otherwise the first true positive mutes the watchdog permanently."""
    import production_deploy_gate_latency as mod

    monkeypatch.setattr(
        mod, "fetch_deployments", lambda *a, **k: [_deployment(minutes_old=2, state="success")]
    )
    filed: list[bool] = []
    monkeypatch.setattr(
        mod, "resolve_watchdog_issue", lambda repo, tok, *, dry_run: filed.append(True) or "closed"
    )
    assert mod.main(["--now", NOW.isoformat(), "--dry-run"]) == 0
    assert filed == [True]


def test_the_email_client_is_called_with_the_signature_it_actually_has(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`send_message` requires `html_body` positionally; omitting it always raises."""
    import production_deploy_gate_latency as mod

    seen: dict[str, Any] = {}

    class _Client:
        def send_message(self, **kwargs: Any) -> None:
            seen.update(kwargs)

    class _Notifier:
        NotifyNotConfiguredError = mod.GateCheckFailed

    monkeypatch.setenv("GATE_ALERT_EMAIL", "ops@example.test")
    monkeypatch.setitem(
        __import__("sys").modules,
        "digiquant.notify.cloudflare_email",
        type(
            "m",
            (),
            {
                "NotifyNotConfiguredError": _Notifier.NotifyNotConfiguredError,
                "build_email_client": staticmethod(lambda: _Client()),
                "format_notify_not_configured": staticmethod(lambda missing: "unset"),
                "missing_notify_env_names": staticmethod(lambda: ()),
            },
        ),
    )
    assert "email sent" in mod.notify_email("s", "b", dry_run=False)
    assert set(seen) == {"to", "subject", "text_body", "html_body"}


def test_a_state_we_do_not_recognise_alerts_rather_than_passing() -> None:
    """An unknown state is not evidence of success.

    The deny-list in ``is_unfinished`` exists for this: a new GitHub state must show
    up in an alert, not silently read as "done".
    """
    assert (
        len(stale_deployments([_deployment(state="cancelled_by_gate", minutes_old=120)], now=NOW))
        == 1
    )


# ── reading progress off a real API payload (DIG-1569) ───────────────────────
#
# Two defects shipped past a green test run here, both found by running the script
# against the live API rather than by reading it:
#   1. `gh api` turns any `-f/--raw-field` into a POST, so the deployments query was
#      hitting create-deployment and failing 422 on every run.
#   2. The classification read `deployment["state"]`, which is null on every
#      digithings deployment. Progress lives on the deployment's latest *status*.
# Both are pinned below, plus the end-to-end shape the watchdog actually sees.


def test_the_deployments_query_asks_for_a_get_and_not_a_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: without ``--method GET`` this becomes a create-deployment call.

    ``gh api`` switches to POST as soon as any ``-f`` is present, so the filter
    arguments below silently turned the read into a write that fails 422.
    """
    import production_deploy_gate_latency as mod

    seen: dict[str, Any] = {}

    def spy(args: list[str], **kwargs: Any) -> str:
        seen["argv"] = args
        return "[]"

    monkeypatch.setattr(mod, "_gh", spy)
    mod.fetch_deployments("digithings-ai/digithings", "production", "tok")
    argv = seen["argv"]
    assert "--method" in argv and argv[argv.index("--method") + 1] == "GET"
    assert "environment=production" in argv


def test_the_status_query_asks_for_a_get_too(monkeypatch: pytest.MonkeyPatch) -> None:
    import production_deploy_gate_latency as mod

    seen: dict[str, Any] = {}

    def spy(args: list[str], **kwargs: Any) -> str:
        seen["argv"] = args
        return "[]"

    monkeypatch.setattr(mod, "_gh", spy)
    mod.resolve_status_states([_api_deployment()], "tok", now=NOW)
    argv = seen["argv"]
    assert "--method" in argv and argv[argv.index("--method") + 1] == "GET"
    assert argv[argv.index("--method") + 1 + 1].startswith("https://api.github.com/repos/")


def test_a_deployment_with_a_null_state_is_classified_from_its_latest_status() -> None:
    """The regression that mattered: a waiting deploy looked finished.

    Reproduces DIG-1484's shape — a deployment sitting on the ``production`` gate
    whose only evidence of progress is a ``waiting`` status.
    """
    rows = apply_latest_statuses([_api_deployment(minutes_old=870)], {6892915678: "waiting"})
    stale = stale_deployments(rows, now=NOW)
    assert len(stale) == 1
    assert stale[0].state == "waiting"
    assert stale[0].age_minutes == 870


def test_a_raw_row_with_no_state_is_never_silently_healthy() -> None:
    """A row straight off the API must not read as 'all clear'."""
    rows = apply_latest_statuses([_api_deployment(minutes_old=870)], {})
    stale = stale_deployments(rows, now=NOW)
    assert len(stale) == 1
    assert stale[0].state == "unknown"


@pytest.mark.parametrize(
    ("latest_status_state", "expected_alert"),
    [
        ("success", False),
        ("inactive", False),
        ("failure", False),
        ("error", False),
        ("waiting", True),
        ("pending", True),
        ("queued", True),
        ("in_progress", True),
        ("", True),
    ],
)
def test_the_real_status_states_map_to_the_right_verdict(
    latest_status_state: str, expected_alert: bool
) -> None:
    rows = apply_latest_statuses(
        [_api_deployment(minutes_old=870)], {6892915678: latest_status_state}
    )
    assert bool(stale_deployments(rows, now=NOW)) is expected_alert, latest_status_state


def test_apply_latest_statuses_does_not_mutate_the_rows_it_is_given() -> None:
    original = _api_deployment(minutes_old=870)
    apply_latest_statuses([original], {6892915678: "waiting"})
    assert "state" not in original


def test_a_deployment_older_than_the_lookback_window_is_never_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The per-status calls are bounded; a year-old deploy is not on the gate."""
    import production_deploy_gate_latency as mod

    calls: list[str] = []
    monkeypatch.setattr(mod, "_gh", lambda args, **kwargs: calls.append(" ".join(args)) or "[]")
    recent = _api_deployment(deployment_id=1, minutes_old=30)
    old = _api_deployment(deployment_id=2, minutes_old=60 * 24 * 30)
    states = mod.resolve_status_states([recent, old], "tok", now=NOW)
    assert set(states) == {1}
    assert len(calls) == 1


def test_the_gate_alerts_on_a_waiting_deployment_and_stays_quiet_when_it_lands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end over the realistic payload, through ``main``'s own wiring."""
    import production_deploy_gate_latency as mod

    stuck = _api_deployment(deployment_id=6892915678, minutes_old=870)
    landed = _api_deployment(deployment_id=6884868789, minutes_old=870)
    monkeypatch.setattr(mod, "fetch_deployments", lambda *a, **k: [stuck, landed])
    monkeypatch.setattr(
        mod,
        "resolve_status_states",
        lambda *a, **k: {6892915678: "waiting", 6884868789: "success"},
    )
    filed: list[str] = []
    monkeypatch.setattr(
        mod, "file_or_update_issue", lambda repo, body, tok, *, dry_run: filed.append(body) or "url"
    )
    assert mod.main(["--now", NOW.isoformat(), "--dry-run"]) == 0
    assert len(filed) == 1
    assert "6892915678" in filed[0]
    assert "6884868789" not in filed[0]
    assert "688879" not in filed[0]


def test_stale_deployments_are_ordered_oldest_first() -> None:
    rows = [
        _deployment(deployment_id=1, minutes_old=120),
        _deployment(deployment_id=2, minutes_old=1000),
        _deployment(deployment_id=3, minutes_old=300),
    ]
    # oldest (1000 min) → newest of the stale set (120 min): the top row is the one
    # that has been waiting longest, which is what a human needs to act on first.
    assert [d.deployment_id for d in stale_deployments(rows, now=NOW)] == [2, 3, 1]


def test_an_unparseable_created_at_does_not_crash_the_watchdog() -> None:
    """Garbage from the API must not take down the check."""
    row = _deployment(minutes_old=9999)
    row["created_at"] = "not-a-timestamp"
    assert stale_deployments([row], now=NOW) == []


def test_a_row_missing_the_sha_does_not_crash_the_renderer() -> None:
    row = _deployment(minutes_old=120)
    row["sha"] = ""
    stale = stale_deployments([row], now=NOW)
    assert stale[0].short_sha == "unknown"


def test_the_threshold_is_configurable() -> None:
    rows = [_deployment(minutes_old=30)]
    assert stale_deployments(rows, now=NOW) == []
    assert len(stale_deployments(rows, now=NOW, max_age_minutes=15)) == 1


# ── issue body ───────────────────────────────────────────────────────────────


def test_the_issue_body_carries_the_dedup_marker_and_the_waiting_ages() -> None:
    stale = stale_deployments([_deployment(minutes_old=870)], now=NOW)
    body = render_issue_body(
        stale, max_age_minutes=DEFAULT_MAX_AGE_MINUTES, repo="digithings-ai/digithings"
    )
    assert ISSUE_MARKER in body
    assert "870 min" in body
    assert "da88fa71" in body
    # The body must say what is blocked, not only what is late.
    assert "not live" in body.lower()
    assert "Approve or reject" in body


def test_the_issue_body_is_deterministic() -> None:
    stale = stale_deployments([_deployment(minutes_old=200)], now=NOW)
    args = (stale,)
    kwargs = {"max_age_minutes": 60, "repo": "digithings-ai/digithings"}
    assert render_issue_body(*args, **kwargs) == render_issue_body(*args, **kwargs)


# ── dedup: one open issue, not one per tick ──────────────────────────────────


def test_find_open_issue_matches_on_the_body_marker_not_the_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale title with no marker must not be adopted as the watchdog issue.

    Dedup keys on the marker so the watchdog cannot hijack an unrelated issue
    that happens to share the title prefix.
    """
    import production_deploy_gate_latency as mod

    monkeypatch.setattr(
        mod,
        "_gh",
        lambda *a, **k: json.dumps(
            [
                {"number": 7, "body": "an unrelated issue with a similar title"},
                {"number": 42, "body": f"preamble\n{ISSUE_MARKER}\nrest"},
            ]
        ),
    )
    assert find_open_issue("digithings-ai/digithings", "tok") == 42


def test_find_open_issue_returns_none_when_nothing_is_open(monkeypatch: pytest.MonkeyPatch) -> None:
    import production_deploy_gate_latency as mod

    monkeypatch.setattr(mod, "_gh", lambda *a, **k: "[]")
    assert find_open_issue("digithings-ai/digithings", "tok") is None


def test_an_existing_issue_is_edited_rather_than_duplicated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import production_deploy_gate_latency as mod

    calls: list[list[str]] = []

    def fake_gh(args: list[str], **kwargs: Any) -> str:
        calls.append(args)
        if args[:2] == ["issue", "list"]:
            return json.dumps([{"number": 42, "body": ISSUE_MARKER}])
        return "https://github.com/digithings-ai/digithings/issues/42"

    monkeypatch.setattr(mod, "_gh", fake_gh)
    result = file_or_update_issue("digithings-ai/digithings", "body", "tok", dry_run=False)
    assert "42" in result
    assert any(c[:2] == ["issue", "edit"] for c in calls)
    assert not any(c[:2] == ["issue", "create"] for c in calls)


def test_dry_run_touches_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    import production_deploy_gate_latency as mod

    def explode(*a: object, **k: object) -> str:
        raise AssertionError("dry-run must not call gh")

    monkeypatch.setattr(mod, "_gh", explode)
    assert "dry-run" in file_or_update_issue("r", "b", "tok", dry_run=True)


# ── fail closed ──────────────────────────────────────────────────────────────


def test_a_failed_gh_call_raises_gate_check_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    import production_deploy_gate_latency as mod

    class _Proc:
        returncode = 1
        stdout = ""
        stderr = "gh: HTTP 403: Resource not accessible\n"

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Proc())
    with pytest.raises(GateCheckFailed):
        mod.fetch_deployments("digithings-ai/digithings", "production", "tok")


def test_unparseable_api_json_raises_rather_than_reporting_a_healthy_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import production_deploy_gate_latency as mod

    monkeypatch.setattr(mod, "_gh", lambda *a, **k: "<html>rate limited</html>")
    with pytest.raises(GateCheckFailed):
        mod.fetch_deployments("digithings-ai/digithings", "production", "tok")


def test_main_exits_2_when_the_gate_cannot_be_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """The load-bearing assertion of this file.

    An unreadable gate must not exit 0. Exit 0 from `main` is what the schedule
    records as "watchdog ran, gate fine"; returning it on an API failure is how
    the 19-hour blind spot was allowed to look healthy.
    """
    import production_deploy_gate_latency as mod

    def boom(*a: object, **k: object) -> list[dict[str, Any]]:
        raise GateCheckFailed("simulated API failure")

    monkeypatch.setattr(mod, "fetch_deployments", boom)
    assert mod.main(["--dry-run"]) == 2


def test_main_exits_0_when_the_gate_is_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    import production_deploy_gate_latency as mod

    monkeypatch.setattr(mod, "fetch_deployments", lambda *a, **k: [_deployment(minutes_old=2)])
    assert mod.main(["--now", NOW.isoformat(), "--dry-run"]) == 0


def test_main_exits_0_and_alerts_when_the_gate_is_stalled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import production_deploy_gate_latency as mod

    monkeypatch.setattr(
        mod,
        "fetch_deployments",
        lambda *a, **k: [_deployment(minutes_old=870)],
    )
    filed: list[str] = []
    monkeypatch.setattr(
        mod, "file_or_update_issue", lambda repo, body, tok, *, dry_run: filed.append(body) or "url"
    )
    assert mod.main(["--now", NOW.isoformat(), "--dry-run"]) == 0
    assert ISSUE_MARKER in filed[0]


def test_the_token_is_never_passed_in_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Secrets go through the environment; argv is world-readable in the log."""
    import production_deploy_gate_latency as mod

    seen: dict[str, Any] = {}

    def spy(args: list[str], **kwargs: Any) -> Any:
        seen["argv"] = args
        seen["env"] = kwargs.get("env") or {}

        class _Proc:
            returncode = 0
            stdout = "[]"
            stderr = ""

        return _Proc()

    monkeypatch.setattr(mod.subprocess, "run", spy)
    mod.fetch_deployments("r", "production", "super-secret-token")
    assert "super-secret-token" not in " ".join(seen["argv"])
    assert seen["env"].get("GH_TOKEN") == "super-secret-token"


def test_the_cli_runs_standalone_with_no_imports_beyond_the_stdlib() -> None:
    """`--help` must work in a bare checkout (no digiquant, no uv)."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "--max-age-minutes" in proc.stdout


# ── the watchdog workflow wiring ─────────────────────────────────────────────


def _watchdog() -> dict[str, Any]:
    return yaml.safe_load(WATCHDOG.read_text(encoding="utf-8"))


def test_the_watchdog_schedules_far_often_enough_to_bound_the_blind_spot() -> None:
    triggers = _watchdog().get("on") or _watchdog().get(True)
    crons = [entry["cron"] for entry in triggers["schedule"]]
    assert crons, "a watchdog with no schedule never runs"
    # Every 30 minutes: the incident was a ~19h stall nobody saw.
    assert any(re.fullmatch(r"\d+,\d+ \* \* \* \*", cron) for cron in crons), crons


def test_the_watchdog_is_not_on_the_top_of_the_hour() -> None:
    """Every other scheduled workflow in this repo fires on :00 — do not pile on."""
    triggers = _watchdog().get("on") or _watchdog().get(True)
    for entry in triggers["schedule"]:
        minutes = {int(part) for part in entry["cron"].split()[0].split(",")}
        assert 0 not in minutes, f"schedule {entry['cron']} fires on the hour"


def test_the_watchdog_can_also_be_dispatched() -> None:
    triggers = _watchdog().get("on") or _watchdog().get(True)
    assert "workflow_dispatch" in triggers


def test_the_watchdog_declares_the_permissions_its_script_actually_uses() -> None:
    """`issues: write` is the one that is load-bearing.

    `deployments: read` is declared for documentation, not because the script
    consumes it: the script authenticates with a PAT (``DIGITHINGS_PROJECT_TOKEN``
    or ``GH_TOKEN``) passed to ``gh`` as an env var, never with ``GITHUB_TOKEN``,
    so the workflow token's scopes are not what authorises the deployments read.
    Kept because it costs nothing and names the intent; kept honest so nobody later
    removes ``issues: write`` believing the PAT covers issue creation too.
    """
    permissions = _watchdog()["permissions"]
    assert permissions.get("deployments") == "read"
    assert permissions.get("issues") == "write"
    assert permissions.get("contents") == "read"


def test_the_watchdog_supplies_the_pat_the_script_actually_authenticates_with() -> None:
    """The real permission question: is the token the script reads present?"""
    env = _watchdog()["jobs"]["gate-latency"]["env"]
    assert env.get("GH_TOKEN"), "the script reads GH_TOKEN and nothing else"
    secrets = env["GH_TOKEN"]
    assert "secrets." in str(secrets) and "vars." not in str(secrets)


def test_the_watchdog_does_not_serialise_against_itself_across_ticks() -> None:
    """cancel-in-progress: true would kill the tick that is filing the alert."""
    assert _watchdog()["concurrency"]["cancel-in-progress"] is False


def test_the_watchdog_wires_the_threshold_from_its_dispatch_input() -> None:
    triggers = _watchdog().get("on") or _watchdog().get(True)
    assert "max_age_minutes" in triggers["workflow_dispatch"]["inputs"]
    env = _watchdog()["jobs"]["gate-latency"]["env"]
    assert "inputs.max_age_minutes" in env["GATE_ALERT_MAX_AGE_MINUTES"]


def test_the_watchdog_reads_the_issue_token_and_the_notify_token_from_secrets() -> None:
    env = _watchdog()["jobs"]["gate-latency"]["env"]
    assert env["GH_TOKEN"] == "${{ secrets.DIGITHINGS_PROJECT_TOKEN }}"
    assert env["CLOUDFLARE_EMAIL_API_TOKEN"] == "${{ secrets.CLOUDFLARE_EMAIL_API_TOKEN }}"
    assert env["NOTIFY_FROM"] == "${{ secrets.NOTIFY_FROM }}"


def test_the_watchdog_runs_the_script_it_tests() -> None:
    """The workflow must invoke the same script the tests cover."""
    scripts = [step.get("run", "") for step in _watchdog()["jobs"]["gate-latency"]["steps"]]
    assert any("scripts/production_deploy_gate_latency.py" in s for s in scripts)
