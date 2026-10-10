"""Pin the Gloomberb session-cookie runbook to the shipped code (#4099).

RED premise: at creation this module fails with ``FileNotFoundError`` — the
runbook does not exist yet (``docs/ops/gloomberb-session-cookie.md``). The
file-absence RED applies once; every assertion afterwards pins a fact the
code owns, so a doc edit that drifts from the implementation fails here
instead of misleading an operator. Pattern precedent:
``tests/scripts/test_mcp_container.py`` (header lines 9-14).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = REPO_ROOT / "docs" / "ops" / "gloomberb-session-cookie.md"

#: The only GLOOMBERB_* names the runbook may carry: the two env vars the
#: client reads (client.py) and the opt-in live-smoke marker
#: (tests/dq/test_gloomberb_live_smoke.py:18). The first two are cross-checked
#: against the module constants below so a rename fails here, not in prod.
ALLOWED_ENV_NAMES = frozenset(
    {"GLOOMBERB_ENABLED", "GLOOMBERB_SESSION_COOKIE", "GLOOMBERB_LIVE_SMOKE"}
)

#: Cross-references the runbook must carry: origin (#4069), coverage
#: expansion (#4110), and the post-deploy verification plan (#4101).
REQUIRED_ISSUE_REFS = ("#4069", "#4110", "#4101")

#: Documented sample values must be visibly placeholders.
PLACEHOLDER_PREFIXES = ("<", "$", "{")


def _text() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def test_runbook_names_only_real_env_vars() -> None:
    from digiquant.data.gloomberb.client import (
        GLOOMBERB_ENABLED_ENV,
        GLOOMBERB_SESSION_COOKIE_ENV,
    )

    assert {GLOOMBERB_ENABLED_ENV, GLOOMBERB_SESSION_COOKIE_ENV} <= ALLOWED_ENV_NAMES
    named = set(re.findall(r"\bGLOOMBERB_[A-Z0-9_]+\b", _text()))
    assert named, "runbook names no GLOOMBERB_* env var"
    assert named <= ALLOWED_ENV_NAMES, sorted(named - ALLOWED_ENV_NAMES)


def test_runbook_lists_every_cookie_gated_tool() -> None:
    from digiquant.data.gloomberb.entitlements import TOOL_ENTITLEMENTS

    gated = sorted(name for name, ent in TOOL_ENTITLEMENTS.items() if ent != "free")
    text = _text()
    missing = [name for name in gated if name not in text]
    assert not missing, missing
    named = set(re.findall(r"\bdigifetch_[a-z0-9_]+\b", text))
    assert named <= set(TOOL_ENTITLEMENTS), sorted(named - set(TOOL_ENTITLEMENTS))


def test_runbook_distinguishes_absent_session_from_missing_plan() -> None:
    text = _text()
    assert "auth_required" in text
    assert "pro_required" in text


def test_runbook_places_the_cookie_for_local_and_hosted_runs() -> None:
    text = _text()
    assert "DigiQuantMcpContainer" in text
    assert "wrangler secret put GLOOMBERB_SESSION_COOKIE" in text


def test_runbook_carries_the_cross_links() -> None:
    text = _text()
    for ref in REQUIRED_ISSUE_REFS:
        assert ref in text, ref


def test_runbook_never_contains_a_literal_cookie_value() -> None:
    text = _text()
    for value in re.findall(r"session_token=(\S+)", text):
        assert value.startswith(PLACEHOLDER_PREFIXES), value
    assert "never log" in text.lower()
    assert not re.search(r"eyJ[A-Za-z0-9_-]{10,}", text)


# --- DIG-2752: the deployer owns the cookie, and nothing committed holds one ----
#
# Two halves, and they are not the same claim. The runbook must describe the
# deployer-owned model; and the *repo* must carry no cookie value anywhere a
# deployment could pick one up. gitleaks cannot be the second gate: this repo's
# allowlist exempts ``^tests/`` and ``^docs/.*\.md$``, so a cookie committed in
# either would never be reported. These assertions are the real gate; the
# gitleaks rule added alongside them is defence in depth.

#: Deployment config that could carry a cookie value, by glob from the repo root.
CONFIG_GLOBS = (
    ".env",
    ".env.*",
    "**/.env",
    "**/.env.*",
    "**/wrangler.toml",
    "**/docker-compose*.yml",
    "**/docker-compose*.yaml",
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
)

#: Values that carry no secret: empty, quoted-empty, or an obvious reference.
_NON_VALUES = frozenset(
    {
        "",
        "''",
        '""',
        "<your-cookie>",
        "<cookie>",
        "<value>",
        "<paste-it-here>",
        "${GLOOMBERB_SESSION_COOKIE}",
        "$GLOOMBERB_SESSION_COOKIE",
        "secrets.GLOOMBERB_SESSION_COOKIE",
    }
)

#: The cookie's own env name is not a secret, so it is stripped before matching.
_ENV_NAME = "GLOOMBERB_SESSION_COOKIE"


def _config_files() -> list[Path]:
    """Every committed deployment-config file, de-duplicated, existing only."""
    seen: dict[str, Path] = {}
    for pattern in CONFIG_GLOBS:
        for candidate in REPO_ROOT.glob(pattern):
            if candidate.is_file():
                seen.setdefault(str(candidate), candidate)
    return sorted(seen.values())


def _cookie_value_hits(text: str) -> list[str]:
    """Assignments of the cookie env name whose right-hand side is a value.

    Skips comments, and accepts only the placeholder forms in
    :data:`_NON_VALUES`, so a real pasted cookie in a committed file fails here.
    """
    hits: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # Only the tail of the name may carry a value, so ``env.NAME`` used as a
        # lookup does not read as an assignment.
        for match in re.finditer(re.escape(_ENV_NAME) + r"(?![A-Z0-9_])([=:])(\S+)", stripped):
            raw = match.group(2).strip().strip("\"'")
            if raw not in _NON_VALUES:
                hits.append(f"line {lineno}: {stripped}")
    return hits


def test_no_committed_deployment_config_carries_a_cookie_value() -> None:
    """The tripwire: a deployer's secret must never land in the repository."""
    offenders: dict[str, list[str]] = {}
    for config in _config_files():
        try:
            text = config.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):  # pragma: no cover - binary or unreadable
            continue
        hits = _cookie_value_hits(text)
        if hits:
            offenders[str(config.relative_to(REPO_ROOT))] = hits
    assert not offenders, offenders


def test_the_config_scan_can_actually_fail() -> None:
    """Positive control: a planted cookie value must be caught.

    Without this, an empty ``_config_files()`` would make the guard above pass
    for the wrong reason, which is the failure mode this guard exists to avoid.
    """
    sample = f'{_ENV_NAME}="pasted-value-that-must-be-caught"\n'
    assert _cookie_value_hits(sample), "the config scanner no longer detects a value"
    assert not _cookie_value_hits(f"{_ENV_NAME}=\n")
    assert not _cookie_value_hits(f"# {_ENV_NAME}=a-commented-secret-is-not-live\n")
    assert not _cookie_value_hits(f'wrangler.EnvVars.get("{_ENV_NAME}")\n')
    assert _config_files(), "no deployment config was found to scan"


def test_gitleaks_carries_a_cookie_rule_as_defence_in_depth() -> None:
    """gitleaks is the second line, not the first (see the allowlist above).

    The rule matches our own env name only. An earlier draft also matched the
    vendor's own cookie-slot spellings, but spelling a vendor storage slot in
    this repository is itself a DIG-1415 vendor-content finding and only
    Security and Counsel may approve that. The arm was dropped, not hidden, and
    the comment above the rule records it.
    """
    config = (REPO_ROOT / ".gitleaks.toml").read_text(encoding="utf-8")
    assert 'id = "gloomberb-deployer-session-cookie"' in config
    assert _ENV_NAME in config
    assert "session_token" not in config, "the vendor storage slot was reintroduced"


def test_runbook_states_the_deployer_owns_the_cookie() -> None:
    """The ownership model inverted on 10 Oct 2026; the doc must say so."""
    text = _text()
    assert "whoever deploys the digithings stack" in text
    assert "Bring your own Gloomberb account" in text
    # The retired store must be named as retired, not as the source of truth.
    assert "retired" in text.lower()
    assert "single-owner rule" in text


def test_runbook_documents_the_validation_gate_and_its_fail_closed_rule() -> None:
    text = _text()
    for marker in ("DIG-2752", "fails closed", "no HTTP request"):
        assert marker in text, marker


def test_runbook_documents_the_onboarding_cli_end_to_end() -> None:
    text = _text()
    for command in (
        "digiquant gloomberb login",
        "digiquant gloomberb status",
        "digiquant gloomberb logout",
        "digiquant gloomberb shell",
    ):
        assert command in text, command
    assert "--store cloudflare" in text


def test_runbook_documents_rotation_and_the_terms_note() -> None:
    text = _text()
    assert "Rotate or expire" in text
    assert "npx wrangler secret delete GLOOMBERB_SESSION_COOKIE" in text
    assert "DIG-1233" in text
