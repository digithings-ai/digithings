"""Unit tests for the DIG-4809 github app token rule in .gitleaks.toml.

Why these tests exist
---------------------
The CI seats mint one GitHub App installation token per run and it travels as
``ghs_<appid>_<jwt>``. gitleaks 8.30.1 was measured against that shape on this
branch: the two spellings that carry no credential label — the bare value on a
line, and the value inside a git URL — are structurally invisible to the
default ruleset, because ``generic-api-key`` needs a label and the default
``github-app-token`` rule expects the classic ``ghs_<36 base62 chars>`` token.

``.gitleaks.toml`` gained one additive rule, ``github-app-installation-token``,
that covers exactly that region: ``ghs_``, a numeric app id, an underscore, and
the token body in the base64url alphabet a JWT uses.

What these tests pin
--------------------
1. The rule exists, with ``keywords`` and ``regex``.
2. The regex catches the shapes that were measured to escape the default
   ruleset — bare value, value inside a URL, value behind a label. The
   fixtures are generated, never a real credential.
3. The regex does not catch the documented placeholder
   ``ghs_<appid>_<jwt>``, and does not catch the classic ``ghs_<36 chars>``
   token, which stays the default ``github-app-token`` rule's job.
4. End to end, when a gitleaks binary is available: a directory holding the
   true shapes reports the new rule, a directory holding the placeholder
   reports nothing, the classic token is still reported (by the default rule),
   and scanning this repository reports zero findings from the new rule.

Run: ``pytest tests/scripts/test_gitleaks_github_app_token_rule.py -m unit``

No credential value appears in this file. All fixtures are generated from a
fixed seed.
"""

from __future__ import annotations

import json
import random
import shutil
import string
import subprocess
import tomllib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONFIG = _REPO_ROOT / ".gitleaks.toml"

_RULE = "github-app-installation-token"
_DEFAULT_RULE = "github-app-token"

_SEED = 4809

_APP_ID = "12345678"
_PLACEHOLDER = "ghs_<appid>_<jwt>"


def _body(length: int) -> str:
    """A random base64url-ish run of exactly ``length`` characters."""
    rng = random.Random(_SEED + length)
    alphabet = string.ascii_letters + string.digits + "-_"
    return "".join(rng.choice(alphabet) for _ in range(length))


def _app_token(length: int = 40) -> str:
    """The documented shape: ``ghs_<appid>_<jwt body>``."""
    return "ghs_%s_%s" % (_APP_ID, _body(length))


def _classic_token() -> str:
    """The classic installation token: ``ghs_`` plus 36 base62 characters."""
    rng = random.Random(_SEED)
    alphabet = string.ascii_letters + string.digits
    return "ghs_" + "".join(rng.choice(alphabet) for _ in range(36))


def _rules() -> dict[str, dict]:
    with _CONFIG.open("rb") as handle:
        config = tomllib.load(handle)
    return {rule["id"]: rule for rule in config.get("rules", [])}


def _matches(rule: dict, text: str) -> bool:
    import re

    return re.search(rule["regex"], text) is not None


# The shapes measured to escape the default ruleset on this branch.
TRUE_SHAPES: dict[str, str] = {
    "bare_value": "%s\n" % _app_token(),
    "inside_a_url": "https://x-access-token:%s@github.com/acme/app.git\n" % _app_token(),
    "behind_a_label": "GITHUB_TOKEN=%s\n" % _app_token(),
    "long_body": "%s\n" % _app_token(120),
}


@pytest.mark.unit
def test_the_rule_is_present_with_the_expected_shape() -> None:
    rule = _rules().get(_RULE)
    assert rule is not None, f"{_RULE} is missing from .gitleaks.toml"
    assert rule["keywords"], f"{_RULE} needs a keyword prefilter"
    assert "ghs_" in rule["regex"], f"{_RULE} must look for the app token prefix"
    assert not rule["regex"].endswith("$"), f"{_RULE} must not be end-anchored"


@pytest.mark.unit
@pytest.mark.parametrize("shape", sorted(TRUE_SHAPES))
def test_true_shapes_are_caught(shape: str) -> None:
    assert _matches(_rules()[_RULE], TRUE_SHAPES[shape]), f"{shape} escaped {_RULE}"


@pytest.mark.unit
def test_the_documented_placeholder_is_not_caught() -> None:
    assert not _matches(_rules()[_RULE], "%s\n" % _PLACEHOLDER)


@pytest.mark.unit
def test_the_classic_token_stays_the_default_rule_job() -> None:
    assert not _matches(_rules()[_RULE], "%s\n" % _classic_token())


def _gitleaks() -> str | None:
    return shutil.which("gitleaks")


def _scan(path: Path, report: Path, cwd: Path | None = None) -> list[dict]:
    result = subprocess.run(
        [
            _gitleaks(), "dir", str(path),
            "--config", str(_CONFIG),
            "--redact", "--no-banner",
            "--report-format", "json",
            "--report-path", str(report),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd) if cwd is not None else None,
    )
    assert result.returncode in (0, 1), result.stderr
    if not report.exists():
        return []
    findings = json.loads(report.read_text() or "[]")
    report.unlink()
    return findings


@pytest.mark.unit
@pytest.mark.skipif(_gitleaks() is None, reason="gitleaks binary not installed")
def test_gitleaks_reports_the_true_shapes(tmp_path: Path) -> None:
    """A single-file `gitleaks dir` scans ~0 bytes, so the fixtures go in a dir."""
    target = tmp_path / "true"
    target.mkdir()
    for name, text in TRUE_SHAPES.items():
        (target / name).write_text(text)
    rules_hit = {f["RuleID"] for f in _scan(target, tmp_path / "report.json")}
    assert _RULE in rules_hit, f"{_RULE} did not fire, got {rules_hit}"


@pytest.mark.unit
@pytest.mark.skipif(_gitleaks() is None, reason="gitleaks binary not installed")
def test_gitleaks_is_silent_on_the_placeholder(tmp_path: Path) -> None:
    target = tmp_path / "placeholder"
    target.mkdir()
    (target / "placeholder.txt").write_text("%s\n" % _PLACEHOLDER)
    findings = _scan(target, tmp_path / "report.json")
    assert not findings, f"the placeholder must not be reported, got {findings}"


@pytest.mark.unit
@pytest.mark.skipif(_gitleaks() is None, reason="gitleaks binary not installed")
def test_gitleaks_still_reports_the_classic_token(tmp_path: Path) -> None:
    target = tmp_path / "classic"
    target.mkdir()
    (target / "classic.txt").write_text("%s\n" % _classic_token())
    rules_hit = {f["RuleID"] for f in _scan(target, tmp_path / "report.json")}
    assert _DEFAULT_RULE in rules_hit, f"the default rule stopped firing, got {rules_hit}"


@pytest.mark.unit
@pytest.mark.skipif(_gitleaks() is None, reason="gitleaks binary not installed")
def test_repository_has_no_findings_from_the_new_rule(tmp_path: Path) -> None:
    """The FP control that matters: this repo is large and reference-heavy.

    The scan is repository-relative on purpose. The allowlist paths in
    ``.gitleaks.toml`` are written relative to the repository root
    (``^tests/``, ``^docs/.*\\.md$``, ...), so an absolute scan path would not
    match them and the test fixtures themselves would be reported. That is also
    how CI scans: gitleaks walks the git history, where every path is relative
    to the repository root.
    """
    findings = _scan(Path("."), tmp_path / "report.json", cwd=_REPO_ROOT)
    rules_hit = {f["RuleID"] for f in findings} & {_RULE}
    assert not rules_hit, f"{_RULE} must not fire anywhere in this repository, got {rules_hit}"
