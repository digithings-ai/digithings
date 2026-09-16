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
