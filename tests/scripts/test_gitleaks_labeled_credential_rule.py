"""Unit tests for the DIG-1723 labeled-credential rules in .gitleaks.toml.

Why these tests exist
--------------------
A live X-API-Key for a client MCP endpoint was found in a digithings-books
transcript that gitleaks reported as clean. The cause was not the allowlist: the
default ``generic-api-key`` rule cannot match a labeled credential whose value
is longer than ~150 characters, or whose value contains a character outside
``[A-Za-z0-9_-+/=]`` (a ``:`` anywhere in the value breaks the match entirely).
Both limits were measured on gitleaks 8.30.1 with synthetic fixtures.

``.gitleaks.toml`` gained two additive rules to cover exactly that region:
``labeled-credential-long-value`` (100+ char value) and
``labeled-credential-delimited-value`` (``<20+>:<20+>`` value).

What these tests pin
--------------------
1. Both rules exist, with ``keywords``, ``regex`` and ``secretGroup``.
2. The regexes catch the four shapes that were measured to escape the default
   ruleset. Fixtures are generated, never a real credential.
3. The regexes reject the reference-shaped text that a naive "label then value"
   rule sweeps up — ``os.environ/FOO_BAR_KEY``, ``process.env.X_API_KEY``, a
   bare ``_OPENAI_API_KEY`` name, a plain API URL. These are the false
   positives measured at 22-35 chars, and they are what the length floor and
   the two-sided delimiter pair exist to exclude.
4. End to end, when a gitleaks binary is available: a directory holding the
   true shapes reports the new rules, a directory holding the reference shapes
   reports nothing from them, and scanning this repository reports zero
   findings from the two new rules.

A 64-char colon-free labeled value is deliberately NOT expected to match: it
sits inside the region ``generic-api-key`` already covers.

Run: ``pytest tests/scripts/test_gitleaks_labeled_credential_rule.py -m unit``

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

_RULE_LONG = "labeled-credential-long-value"
_RULE_DELIMITED = "labeled-credential-delimited-value"

_SEED = 1723


def _token(length: int) -> str:
    """A random alphanumeric run of exactly ``length`` characters."""
    rng = random.Random(_SEED + length)
    alphabet = string.ascii_letters + string.digits
    return "".join(rng.choice(alphabet) for _ in range(length))


def _rules() -> dict[str, dict]:
    with _CONFIG.open("rb") as handle:
        config = tomllib.load(handle)
    return {rule["id"]: rule for rule in config.get("rules", [])}


def _matches(rule: dict, text: str) -> bool:
    import re

    return re.search(rule["regex"], text) is not None


# True shapes: all four escaped the default ruleset in DIG-1723. The first is
# the real shape, reproduced with a generated value.
TRUE_SHAPES: dict[str, str] = {
    "json_header_colon_pair": '{"type":"http","headers":{"X-API-Key":"%s:%s"}}'
    % (_token(36), _token(344)),
    "authorization_bearer_long": "Authorization: Bearer %s" % _token(200),
    "apikey_assign_64": "api_key = %s" % _token(64),
    "x_api_key_long": "x-api-key: %s" % _token(400),
}

# Which new rule is expected to catch each shape. The 64-char assign is caught
# by the default ruleset, not by these two.
EXPECTED_RULE: dict[str, str | None] = {
    "json_header_colon_pair": _RULE_DELIMITED,
    "authorization_bearer_long": _RULE_LONG,
    "apikey_assign_64": None,
    "x_api_key_long": _RULE_LONG,
}

# Shapes measured as false positives against a naive label-then-value rule.
FALSE_POSITIVE_SHAPES: dict[str, str] = {
    "env_reference": "api_key: os.environ/OPENAI_API_KEY\nx-api-key: ${DATATAP_API_KEY}\n",
    "process_env_reference": "const apiKey = process.env.DATATAP_MCP_API_KEY;\n",
    "bare_variable_name": 'api_key: _OPENAI_API_KEY\nbearer: os.getenv("X_API_KEY")\n',
    "api_url": "api_url: https://api.example.net/v1/endpoint\n",
}


@pytest.mark.unit
def test_both_rules_are_present_with_the_expected_shape() -> None:
    rules = _rules()
    for rule_id in (_RULE_LONG, _RULE_DELIMITED):
        assert rule_id in rules, f"{rule_id} is missing from .gitleaks.toml"
        rule = rules[rule_id]
        assert rule["keywords"], f"{rule_id} needs a keyword prefilter"
        assert rule["secretGroup"] == 1, f"{rule_id} must report group 1 as the secret"
        assert rule["regex"].startswith("(?i)"), f"{rule_id} must be case-insensitive"


@pytest.mark.unit
@pytest.mark.parametrize("shape", sorted(TRUE_SHAPES))
def test_true_shapes_are_caught(shape: str) -> None:
    text = TRUE_SHAPES[shape]
    caught = [rid for rid in (_RULE_LONG, _RULE_DELIMITED) if _matches(_rules()[rid], text)]
    expected = EXPECTED_RULE[shape]
    if expected is None:
        assert not caught, f"{shape} is the default ruleset's job, but {caught} matched"
    else:
        assert expected in caught, f"{shape} should match {expected}, got {caught or 'nothing'}"


@pytest.mark.unit
@pytest.mark.parametrize("shape", sorted(FALSE_POSITIVE_SHAPES))
def test_reference_shapes_are_not_caught(shape: str) -> None:
    text = FALSE_POSITIVE_SHAPES[shape]
    caught = [rid for rid in (_RULE_LONG, _RULE_DELIMITED) if _matches(_rules()[rid], text)]
    assert not caught, f"{shape} is a reference, not a credential, but {caught} matched"


def _gitleaks() -> str | None:
    return shutil.which("gitleaks")


def _scan(path: Path) -> list[dict]:
    report = path.parent / "report.json"
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
    )
    assert result.returncode in (0, 1), result.stderr
    if not report.exists():
        return []
    findings = json.loads(report.read_text() or "[]")
    report.unlink()
    return findings


@pytest.mark.unit
@pytest.mark.skipif(_gitleaks() is None, reason="gitleaks binary not installed")
def test_gitleaks_reports_the_true_shapes_in_a_directory(tmp_path: Path) -> None:
    """A single-file `gitleaks dir` scans ~0 bytes, so the fixtures go in a dir."""
    target = tmp_path / "true"
    target.mkdir()
    for name, text in TRUE_SHAPES.items():
        (target / name).write_text(text)
    rules_hit = {f["RuleID"] for f in _scan(target)}
    assert _RULE_LONG in rules_hit
    assert _RULE_DELIMITED in rules_hit


@pytest.mark.unit
@pytest.mark.skipif(_gitleaks() is None, reason="gitleaks binary not installed")
def test_gitleaks_is_silent_on_the_reference_shapes(tmp_path: Path) -> None:
    target = tmp_path / "false-positives"
    target.mkdir()
    for name, text in FALSE_POSITIVE_SHAPES.items():
        (target / name).write_text(text)
    rules_hit = {f["RuleID"] for f in _scan(target)}
    assert not rules_hit & {_RULE_LONG, _RULE_DELIMITED}


@pytest.mark.unit
@pytest.mark.skipif(_gitleaks() is None, reason="gitleaks binary not installed")
def test_repository_has_no_findings_from_the_new_rules(tmp_path: Path) -> None:
    """The FP control that matters: this repo is large and reference-heavy."""
    rules_hit = {f["RuleID"] for f in _scan(_REPO_ROOT)} & {_RULE_LONG, _RULE_DELIMITED}
    assert not rules_hit, f"the two rules must not fire anywhere in this repository, got {rules_hit}"