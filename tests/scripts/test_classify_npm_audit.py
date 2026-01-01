"""Contract tests for the npm-audit classifier (`scripts/classify_npm_audit.py`).

Two properties the `npm-audit` CI lane's safety rests on, both regressions found
in review of #4383:

* per-advisory ignore matching, so a new advisory on an already-accepted package
  still blocks; and
* fail-closed behaviour, so a registry error is never read as a clean audit.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "classify_npm_audit.py"

spec = importlib.util.spec_from_file_location("classify_npm_audit", SCRIPT)
assert spec and spec.loader
classify_npm_audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(classify_npm_audit)

classify = classify_npm_audit.classify
advisory_ids = classify_npm_audit.advisory_ids
load_ignored = classify_npm_audit.load_ignored
AuditError = classify_npm_audit.AuditError


def _advisory(ghsa: str, severity: str) -> dict[str, object]:
    return {
        "source": 1,
        "name": "next",
        "title": "example",
        "url": f"https://github.com/advisories/{ghsa}",
        "severity": severity,
        "range": "<16.3.5",
    }


def _package(advisories: list[dict[str, object]], severity: str, direct: bool = True) -> dict:
    return {"severity": severity, "isDirect": direct, "via": advisories, "effects": []}


def _audit(**packages: dict) -> dict:
    return {
        "auditReportVersion": 2,
        "vulnerabilities": packages,
        "metadata": {"vulnerabilities": {"high": 1}},
    }


@pytest.mark.unit
def test_advisory_ids_surfaces_the_bare_ghsa_from_the_url():
    ids = advisory_ids(_advisory("GHSA-8h8q-6873-q5fj", "critical"))
    # The ignore file documents bare ids; npm only gives a full URL.
    assert "GHSA-8h8q-6873-q5fj" in ids
    assert "https://github.com/advisories/GHSA-8h8q-6873-q5fj" in ids


@pytest.mark.unit
def test_a_fully_accepted_package_is_ignored_not_blocked():
    data = _audit(next=_package([_advisory("GHSA-aaaa-bbbb-cccc", "critical")], "critical"))
    blockers, warns, ignored = classify(data, {"GHSA-aaaa-bbbb-cccc"})
    assert blockers == []
    assert warns == []
    assert len(ignored) == 1


@pytest.mark.unit
def test_a_new_advisory_on_an_accepted_package_still_blocks():
    """The #4383 regression: package-level matching excused the whole package.

    `next` bundles two dozen accepted advisories; a *new* critical one must not
    ride along on their acceptance.
    """
    data = _audit(
        next=_package(
            [
                _advisory("GHSA-aaaa-bbbb-cccc", "critical"),  # accepted
                _advisory("GHSA-zzzz-yyyy-xxxx", "critical"),  # brand new
            ],
            "critical",
        )
    )
    blockers, warns, ignored = classify(data, {"GHSA-aaaa-bbbb-cccc"})
    assert len(blockers) == 1, "the unaccepted advisory must block"
    assert "next" in blockers[0] and "critical" in blockers[0]
    assert ignored == []
    assert warns == []


@pytest.mark.unit
def test_a_new_lower_severity_advisory_on_an_accepted_package_warns():
    data = _audit(
        next=_package(
            [
                _advisory("GHSA-aaaa-bbbb-cccc", "critical"),  # accepted
                _advisory("GHSA-zzzz-yyyy-xxxx", "moderate"),  # new, non-blocking
            ],
            "critical",
        )
    )
    blockers, warns, ignored = classify(data, {"GHSA-aaaa-bbbb-cccc"})
    assert blockers == []
    assert len(warns) == 1 and "moderate" in warns[0]


@pytest.mark.unit
def test_high_and_critical_block_but_moderate_only_warns():
    data = _audit(
        alpha=_package([_advisory("GHSA-1111-1111-1111", "high")], "high"),
        beta=_package([_advisory("GHSA-2222-2222-2222", "critical")], "critical"),
        gamma=_package([_advisory("GHSA-3333-3333-3333", "moderate")], "moderate"),
    )
    blockers, warns, ignored = classify(data, set())
    assert len(blockers) == 2
    assert len(warns) == 1 and "gamma [moderate]" in warns[0]


@pytest.mark.unit
def test_a_transitively_listed_package_is_not_double_counted():
    """`via` string entries name dependencies, not advisories."""
    data = _audit(meta={"severity": "high", "isDirect": False, "via": ["next"], "effects": []})
    blockers, warns, ignored = classify(data, set())
    assert (blockers, warns, ignored) == ([], [], [])


@pytest.mark.unit
def test_registry_error_body_fails_closed():
    """npm writes a valid JSON error to stdout when the registry fails."""
    payload = {
        "message": "request to http://127.0.0.1:1/-/npm/v1/security/advisories/bulk failed",
        "error": {"summary": "", "detail": ""},
    }
    with pytest.raises(AuditError):
        classify(payload, set())


@pytest.mark.unit
def test_missing_vulnerabilities_key_fails_closed():
    with pytest.raises(AuditError):
        classify({"auditReportVersion": 2}, set())


@pytest.mark.unit
def test_empty_vulnerabilities_object_is_a_genuinely_clean_audit():
    blockers, warns, ignored = classify({"vulnerabilities": {}}, set())
    assert (blockers, warns, ignored) == ([], [], [])


@pytest.mark.unit
def test_load_ignored_skips_comments_and_blank_lines(tmp_path: Path):
    path = tmp_path / "npm-audit-ignore.txt"
    path.write_text(
        "# a comment\n\nGHSA-aaaa-bbbb-cccc\nGHSA-dddd-eeee-ffff  # trailing note\n   \n",
        encoding="utf-8",
    )
    assert load_ignored(path) == {"GHSA-aaaa-bbbb-cccc", "GHSA-dddd-eeee-ffff"}


@pytest.mark.unit
def test_load_ignored_tolerates_a_missing_file(tmp_path: Path):
    assert load_ignored(tmp_path / "absent.txt") == set()


@pytest.mark.unit
def test_main_exits_nonzero_on_an_error_body(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps({"message": "boom", "error": {}}), encoding="utf-8")
    assert classify_npm_audit.main(["classify", str(audit), str(tmp_path / "none.txt")]) == 1
    assert "::error::" in capsys.readouterr().out


@pytest.mark.unit
def test_main_exits_zero_on_a_clean_audit(tmp_path: Path):
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps({"vulnerabilities": {}}), encoding="utf-8")
    assert classify_npm_audit.main(["classify", str(audit), str(tmp_path / "none.txt")]) == 0
