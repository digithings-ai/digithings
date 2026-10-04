"""Unit tests for scripts/check_workflow_tokens.py (#3522).

The canary's whole value is that it is *honest* about what it can and cannot
verify without spend. These tests pin that contract:

* a verifiable credential that fails to authenticate is a failure (exit 1);
* an unverifiable agent token is never a failure, even when absent — claiming
  otherwise would file a tracker for a known, accepted gap;
* the probe distinguishes "absent" from "invalid" for verifiable credentials;
* a probe that cannot run (gh missing) is exit 2, not a fabricated verdict.

DIG-362 adds the Issues-grant proof. The load-bearing case is the downgrade:
a token narrowed to read-only still satisfies an ``issues: read`` probe, so the
paired read probe alone would report OK on exactly the state that silently
breaks DIG-71's alarm. The write probe is what catches it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_workflow_tokens.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_workflow_tokens_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve cls.__module__ via sys.modules
    spec.loader.exec_module(module)
    return module


cwt = _load_module()


def test_missing_verifiable_credential_is_a_failure() -> None:
    cred = cwt.check_github_pat("DIGITHINGS_PROJECT_TOKEN", None)
    assert cred.status == "absent"
    assert cred.is_failure is True


def test_unverifiable_token_present_is_not_a_failure() -> None:
    cred = cwt.check_unverifiable("CLAUDE_CODE_OAUTH_TOKEN", "x" * 40, "no endpoint")
    assert cred.status == "unvalidated-by-design"
    assert cred.is_failure is False


def test_unverifiable_token_absent_is_not_a_failure() -> None:
    cred = cwt.check_unverifiable("CURSOR_API_KEY", None, "no endpoint")
    assert cred.status == "absent"
    # Still not a failure: presence of a token we cannot validate is not our
    # signal to raise. The known gap is recorded in the status, not an issue.
    assert cred.is_failure is False


def test_implausibly_short_unverifiable_token_is_flagged_absent() -> None:
    cred = cwt.check_unverifiable("CURSOR_API_KEY", "short", "no endpoint")
    assert cred.status == "absent"
    assert "implausibly short" in cred.detail


def test_valid_github_pat_is_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cwt, "_gh_api", lambda endpoint, token, jq=".login": (0, ""))
    cred = cwt.check_github_pat("DIGITHINGS_PROJECT_TOKEN", "tok")
    assert cred.status == "valid"
    assert cred.is_failure is False


def test_rejected_github_pat_is_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cwt, "_gh_api", lambda endpoint, token, jq=".login": (1, "HTTP 401"))
    cred = cwt.check_github_pat("DIGITHINGS_PROJECT_TOKEN", "tok")
    assert cred.status == "invalid"
    assert cred.is_failure is True


def test_probe_error_is_not_a_credential_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cwt, "_gh_api", lambda endpoint, token, jq=".login": (cwt.PROBE_ERROR, "no gh")
    )
    cred = cwt.check_github_pat("DIGITHINGS_PROJECT_TOKEN", "tok")
    assert cred.status == "probe-error"
    assert cred.is_failure is False


def test_gh_dispatch_token_probes_actions_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def fake(endpoint: str, token: str, jq: str = ".login"):
        seen["endpoint"] = endpoint
        return 0, ""

    monkeypatch.setattr(cwt, "_gh_api", fake)
    cwt.check_github_pat(
        "GH_DISPATCH_TOKEN",
        "tok",
        endpoint="/repos/digithings-ai/digithings/actions/runs?per_page=1",
        jq=".total_count",
    )
    # A fine-grained Actions-only PAT may not authenticate /user, so the probe
    # must not use it. It must also avoid /actions/permissions, which is gated on
    # Administration: read rather than the Actions: write grant the token has.
    assert seen["endpoint"].endswith("/actions/runs?per_page=1")
    assert "/actions/permissions" not in seen["endpoint"]


def _armed(monkeypatch: pytest.MonkeyPatch, *, issue: str = "4242") -> None:
    monkeypatch.setenv("TOKEN_CANARY_PROBE_ISSUE", issue)
    monkeypatch.setenv("TOKEN_CANARY_PROBE_WEEKDAY", str(_forced_probe_day().isoweekday()))


def _forced_probe_day() -> datetime:
    """A UTC datetime that lands on the probe weekday, for gating tests."""
    # 2026-10-04 is a Sunday (ISO weekday 7).
    return datetime(2026, 10, 4, 6, 41, tzinfo=timezone.utc)


def test_issues_write_probe_posts_then_deletes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The happy path must leave no artifact: one POST, one DELETE, nothing else."""
    calls: list[tuple[str, str]] = []

    def fake_write(endpoint, token, *, method, fields=None):
        calls.append((method, endpoint))
        if method == "POST":
            return 0, json.dumps({"id": 999}), ""
        return 0, "", ""

    monkeypatch.setattr(cwt, "_gh_api_write", fake_write)
    cred = cwt.probe_issues_write_grant("P", "tok", "digithings-ai/digithings", 4242)

    assert cred.status == "valid"
    assert [m for m, _ in calls] == ["POST", "DELETE"]
    assert calls[0][1].endswith("/repos/digithings-ai/digithings/issues/4242/comments")
    assert calls[1][1].endswith("/issues/comments/999")


def test_downgraded_to_read_only_is_a_failure_not_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The acceptance case: read passes, write 403s — that is a downgrade.

    This is the exact state DIG-93 believed GH_DISPATCH_TOKEN was in. A read
    probe alone reports OK here; the canary must not.
    """
    monkeypatch.setenv("GH_DISPATCH_TOKEN", "tok")
    _armed(monkeypatch)
    # Read probe succeeds — the grant was narrowed, not removed.
    monkeypatch.setattr(cwt, "_gh_api", lambda endpoint, token, jq=".login": (0, ""))
    # Write probe is rejected: read-only tokens cannot POST comments.
    monkeypatch.setattr(
        cwt,
        "_gh_api_write",
        lambda endpoint, token, *, method, fields=None: (
            (cwt.FAIL, "", "HTTP 403: Resource not accessible by personal access token")
        ),
    )

    cred = cwt._issues_grant_probe("digithings-ai/digithings")

    assert cred.status == "invalid"
    assert cred.is_failure is True
    assert "write grant LOST" in cred.detail
    # The downgrade is named explicitly, not left as a bare 403.
    assert "DOWNGRADED to read-only" in cred.detail


def test_grant_removed_reports_read_probe_failure_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read fails too => the grant is gone, which the detail must not call a downgrade."""
    monkeypatch.setenv("GH_DISPATCH_TOKEN", "tok")
    _armed(monkeypatch)
    monkeypatch.setattr(
        cwt, "_gh_api", lambda endpoint, token, jq=".login": (cwt.FAIL, "HTTP 403")
    )
    monkeypatch.setattr(
        cwt,
        "_gh_api_write",
        lambda endpoint, token, *, method, fields=None: (cwt.FAIL, "", "HTTP 403"),
    )

    cred = cwt._issues_grant_probe("digithings-ai/digithings")

    assert cred.status == "invalid"
    assert "DOWNGRADED" not in cred.detail


def test_failed_delete_is_a_failure_so_the_marker_is_not_left_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A marker left on the pinned issue breaks the probe's promise — be loud."""
    def fake_write(endpoint, token, *, method, fields=None):
        if method == "POST":
            return 0, json.dumps({"id": 777}), ""
        return cwt.FAIL, "", "HTTP 500"

    monkeypatch.setattr(cwt, "_gh_api_write", fake_write)
    cred = cwt.probe_issues_write_grant("P", "tok", "digithings-ai/digithings", 4242)

    assert cred.status == "invalid"
    assert cred.is_failure is True
    assert "must be removed by hand" in cred.detail


def test_post_ok_but_no_id_is_probe_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never report OK on a probe whose outcome is unknown."""
    monkeypatch.setattr(
        cwt, "_gh_api_write", lambda endpoint, token, *, method, fields=None: (0, "", "")
    )
    cred = cwt.probe_issues_write_grant("P", "tok", "digithings-ai/digithings", 4242)
    assert cred.status == "probe-error"
    assert cred.is_failure is False


def test_write_probe_is_weekly_not_daily(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the probe weekday may post and delete a real comment."""
    monkeypatch.setenv("GH_DISPATCH_TOKEN", "tok")
    monkeypatch.setenv("TOKEN_CANARY_PROBE_ISSUE", "4242")
    monkeypatch.setenv("TOKEN_CANARY_PROBE_WEEKDAY", "7")

    posted: list[str] = []
    monkeypatch.setattr(cwt, "_gh_api", lambda endpoint, token, jq=".login": (0, ""))

    def fake_write(endpoint, token, *, method, fields=None):
        posted.append(method)
        return (0, json.dumps({"id": 1}), "") if method == "POST" else (0, "", "")

    monkeypatch.setattr(cwt, "_gh_api_write", fake_write)

    # Saturday (2026-10-03): no write.
    monkeypatch.setattr(cwt, "_probe_day_due", lambda now=None: False)
    cred = cwt._issues_grant_probe("digithings-ai/digithings")
    assert cred.status == "skipped-by-design"
    assert cred.is_failure is False
    assert posted == []

    # Probe weekday: write.
    monkeypatch.setattr(cwt, "_probe_day_due", lambda now=None: True)
    cred = cwt._issues_grant_probe("digithings-ai/digithings")
    assert cred.status == "valid"
    assert posted == ["POST", "DELETE"]


def test_unarmed_probe_is_skipped_and_never_files_a_tracker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Not pinning an issue is an accepted gap, not a credential regression."""
    monkeypatch.setenv("GH_DISPATCH_TOKEN", "tok")
    monkeypatch.delenv("TOKEN_CANARY_PROBE_ISSUE", raising=False)

    def explode(*a, **k):  # pragma: no cover - must never run
        raise AssertionError("write probe ran while unarmed")

    monkeypatch.setattr(cwt, "_gh_api_write", explode)
    cred = cwt._issues_grant_probe("digithings-ai/digithings")
    assert cred.status == "skipped-by-design"
    assert cred.is_failure is False


def test_actions_probe_is_unchanged_by_the_write_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Acceptance: the Actions probe stays. It is cheap and correct."""
    monkeypatch.setenv("DIGITHINGS_PROJECT_TOKEN", "a")
    monkeypatch.setenv("GH_DISPATCH_TOKEN", "b")
    monkeypatch.setenv("TOKEN_CANARY_PROBE_ISSUE", "4242")
    monkeypatch.setattr(cwt, "_probe_day_due", lambda now=None: True)
    monkeypatch.setattr(cwt, "_gh_api", lambda endpoint, token, jq=".login": (0, ""))
    monkeypatch.setattr(
        cwt,
        "_gh_api_write",
        lambda endpoint, token, *, method, fields=None: (
            (0, json.dumps({"id": 1}), "") if method == "POST" else (0, "", "")
        ),
    )

    creds = {c.name: c for c in cwt.collect("digithings-ai/digithings")}

    actions = creds["GH_DISPATCH_TOKEN"]
    assert actions.status == "valid"
    assert "actions/runs?per_page=1" in actions.detail
    assert creds["GH_DISPATCH_TOKEN (issues: write)"].status == "valid"


def test_main_exit_codes_are_wired_to_the_verdict(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        cwt,
        "collect",
        lambda repo=None: [cwt.Credential("X", "invalid", "expired")],
    )
    monkeypatch.setattr(sys, "argv", ["check_workflow_tokens.py"])
    assert cwt.main() == cwt.FAIL


def test_main_is_zero_when_only_unvalidated_tokens_remain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cwt,
        "collect",
        lambda repo=None: [
            cwt.Credential("X", "valid", "ok"),
            cwt.Credential(
                "CLAUDE_CODE_OAUTH_TOKEN", "unvalidated-by-design", "no endpoint", verifiable=False
            ),
        ],
    )
    monkeypatch.setattr(sys, "argv", ["check_workflow_tokens.py"])
    assert cwt.main() == cwt.OK
