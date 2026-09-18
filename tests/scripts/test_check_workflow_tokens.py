"""Unit tests for scripts/check_workflow_tokens.py (#3522).

The canary's whole value is that it is *honest* about what it can and cannot
verify without spend. These tests pin that contract:

* a verifiable credential that fails to authenticate is a failure (exit 1);
* an unverifiable agent token is never a failure, even when absent — claiming
  otherwise would file a tracker for a known, accepted gap;
* the probe distinguishes "absent" from "invalid" for verifiable credentials;
* a probe that cannot run (gh missing) is exit 2, not a fabricated verdict.
"""

from __future__ import annotations

import importlib.util
import sys
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


def test_gh_dispatch_token_probes_actions_permissions(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def fake(endpoint: str, token: str, jq: str = ".login"):
        seen["endpoint"] = endpoint
        return 0, ""

    monkeypatch.setattr(cwt, "_gh_api", fake)
    cwt.check_github_pat(
        "GH_DISPATCH_TOKEN",
        "tok",
        endpoint="/repos/digithings-ai/digithings/actions/permissions",
        jq=".enabled",
    )
    # A fine-grained Actions-only PAT may not authenticate /user, so the probe
    # must not use it.
    assert seen["endpoint"].endswith("/actions/permissions")


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
