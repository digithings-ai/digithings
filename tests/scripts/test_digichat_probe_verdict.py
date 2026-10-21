"""The digichat publish probe contract: one helper, both lanes, pinned by behaviour.

Both publish lanes - the GitHub workflow and the local rehearsal - judge a
booted image with ``scripts/digichat_probe_verdict.mjs``. They used to keep
their own copy of the rules and drifted: the local lane never read the status
code the CI lane read, so a rehearsal passed where the release failed.

The rules are therefore driven here, against the bodies the health route can
produce. Widening the tolerated set, dropping a requirement or moving the
success sentinel into a payload value all fail these tests, and a lane that
stopped calling the helper fails the cross-lane test.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / "scripts" / "digichat_probe_verdict.mjs"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish-digichat-image.yml"
LOCAL_LANE = REPO_ROOT / "scripts" / "local-deploy" / "publish_image.sh"

VERSION = "2.6.4"


def _verdict(
    body: str, status: str = "503", version: str = VERSION
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(HELPER), "--status", status, "--version", version],
        input=body,
        capture_output=True,
        text=True,
        check=False,
    )


def _bare_body() -> dict:
    """The body a standalone container answers with: no ecosystem services to reach."""
    return {
        "version": VERSION,
        "checks": {
            "service": "ok",
            "database": "skipped",
            "digraph": "unreachable",
            "digisearch": "unreachable",
            "digiquant": "unreachable",
            "digitrace": "unreachable",
        },
    }


def test_the_helper_accepts_the_bare_container_degradation() -> None:
    """503 with four unreachable services is the truth, not a fault.

    A standalone container has no digigraph, digisearch, digiquant or
    digitrace to reach, so the health route answers 503 and says exactly
    which checks could not be reached. Demanding a 200 here is what killed
    the v2.6.4 tag push (run 39541165954).
    """
    if shutil.which("node") is None:
        pytest.skip("node is needed to drive the probe verdict helper")
    result = _verdict(json.dumps(_bare_body()))
    assert result.returncode == 0, result.stdout
    assert result.stdout.startswith(f"OK version={VERSION} status=503 tolerated=")
    assert "digraph=unreachable" in result.stdout


def test_the_helper_accepts_the_healthy_body() -> None:
    """200 with every check ok is the other honest answer."""
    if shutil.which("node") is None:
        pytest.skip("node is needed to drive the probe verdict helper")
    body = {"version": VERSION, "checks": {"service": "ok", "database": "ok"}}
    result = _verdict(json.dumps(body), status="200")
    assert result.returncode == 0, result.stdout
    assert result.stdout.startswith(f"OK version={VERSION} status=200")


def test_the_helper_refuses_a_status_it_cannot_trust() -> None:
    """Only 200 and 503 are honest answers; anything else is a fault.

    A 500 from a route regression that still serialises the version would
    otherwise pass a probe that only looks at the body.
    """
    if shutil.which("node") is None:
        pytest.skip("node is needed to drive the probe verdict helper")
    for status in ("500", "502", "404", "000"):
        result = _verdict(json.dumps(_bare_body()), status=status)
        assert result.returncode == 1, f"status {status} was accepted: {result.stdout}"
        assert result.stdout.startswith("REFUSE "), result.stdout


def test_the_helper_refuses_an_upstream_that_answered() -> None:
    """Only a fetch that never completed is the degradation this probe allows.

    The health route records an upstream that answered with a non-2xx as
    ``http_<status>``; that is a real fault, not an unreachable service.
    """
    if shutil.which("node") is None:
        pytest.skip("node is needed to drive the probe verdict helper")
    body = {
        "version": VERSION,
        "checks": {"service": "ok", "database": "skipped", "digraph": "http_500"},
    }
    result = _verdict(json.dumps(body))
    assert result.returncode == 1, result.stdout
    assert "digraph=http_500" in result.stdout


def test_the_helper_refuses_a_broken_service_or_database() -> None:
    """The service must be ok, the database ok or skipped, and checks must exist."""
    if shutil.which("node") is None:
        pytest.skip("node is needed to drive the probe verdict helper")
    for checks in (
        {"service": "error", "database": "skipped"},
        {"service": "ok", "database": "error"},
        {"database": "skipped"},
        {},
    ):
        body = {"version": VERSION, "checks": checks}
        result = _verdict(json.dumps(body))
        assert result.returncode == 1, f"{checks} was accepted: {result.stdout}"
    # A body with no checks block at all is the same fault.
    result = _verdict(json.dumps({"version": VERSION}))
    assert result.returncode == 1, result.stdout


def test_the_helper_refuses_a_wrong_or_missing_version() -> None:
    """The version the image serves is what catches a stale layer."""
    if shutil.which("node") is None:
        pytest.skip("node is needed to drive the probe verdict helper")
    result = _verdict(json.dumps({"version": "2.5.0"}))
    assert result.returncode == 1, result.stdout
    assert "2.5.0" in result.stdout and "2.6.4" in result.stdout
    # No version at all, a body that is not JSON, and an empty body are three
    # different faults and must not be reported as one.
    for body in (json.dumps({"status": "ok"}), "<html>gateway error</html>", ""):
        result = _verdict(body)
        assert result.returncode == 1, f"{body!r} was accepted: {result.stdout}"


def test_the_helper_refuses_a_check_that_collides_with_the_success_sentinel() -> None:
    """The verdict must not hang on a magic string the payload can produce.

    The old local probe took "ok" as the success sentinel, so a check
    literally named "ok" made a broken image look clean.
    """
    if shutil.which("node") is None:
        pytest.skip("node is needed to drive the probe verdict helper")
    body = {
        "version": VERSION,
        "checks": {"service": "ok", "database": "skipped", "ok": "error"},
    }
    result = _verdict(json.dumps(body))
    assert result.returncode == 1, result.stdout


def test_a_failing_check_cannot_hide_behind_a_newline() -> None:
    """A value that carries a newline must not hide the entry behind it."""
    if shutil.which("node") is None:
        pytest.skip("node is needed to drive the probe verdict helper")
    body = {
        "version": VERSION,
        "checks": {"service": "ok", "database": "skipped", "digraph": "unreachable\ndigraph=ok"},
    }
    result = _verdict(json.dumps(body))
    assert result.returncode == 1, result.stdout


def test_both_lanes_judge_with_the_same_helper() -> None:
    """The rules live in one place, and both lanes have to call it.

    The workflow used to keep its own copy of the rules and the local lane
    kept another; the two drifted, and the drift is what let a rehearsal
    pass where the release failed. A lane that stops calling the helper
    starts keeping its own copy again, so the call is asserted in both.
    """
    helper = "scripts/digichat_probe_verdict.mjs"
    assert helper in WORKFLOW.read_text(), "the GitHub lane must judge with the shared helper"
    assert helper in LOCAL_LANE.read_text(), "the local rehearsal must judge with the shared helper"
    assert HELPER.is_file(), f"missing {HELPER}"


def test_the_helper_refuses_an_unknown_argument() -> None:
    """A typo in the call must fail the lane, not pass it."""
    if shutil.which("node") is None:
        pytest.skip("node is needed to drive the probe verdict helper")
    result = subprocess.run(
        ["node", str(HELPER), "--statuss", "503", "--version", VERSION],
        input=json.dumps(_bare_body()),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout


def test_a_missing_version_is_a_usage_error() -> None:
    result = subprocess.run(
        ["node", str(HELPER), "--status", "503"],
        input=json.dumps({"version": VERSION, "checks": {"service": "ok"}}),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert result.stdout.startswith("REFUSE")
    assert "--version" in result.stdout


def test_a_body_without_a_version_is_refused() -> None:
    result = _verdict(json.dumps({"checks": {"service": "ok", "database": "skipped"}}))
    assert result.returncode != 0
    assert result.stdout.startswith("REFUSE")


def test_a_body_with_an_empty_version_is_refused() -> None:
    body = {"version": "", "checks": {"service": "ok", "database": "skipped"}}
    result = _verdict(json.dumps(body))
    assert result.returncode != 0
    assert result.stdout.startswith("REFUSE")


def test_an_extra_check_that_is_ok_is_tolerated() -> None:
    body = {
        "version": VERSION,
        "checks": {"service": "ok", "database": "skipped", "redis": "ok"},
    }
    result = _verdict(json.dumps(body))
    assert result.returncode == 0
    assert "tolerated=none" in result.stdout


def test_a_skipped_service_is_refused() -> None:
    body = {"version": VERSION, "checks": {"service": "skipped", "database": "skipped"}}
    result = _verdict(json.dumps(body))
    assert result.returncode != 0
    assert result.stdout.startswith("REFUSE")
