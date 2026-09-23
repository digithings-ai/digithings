"""Pin the digifetch post-deploy verification doc (#4101) to the code.

RED premise: at creation this module fails with ``FileNotFoundError`` — the
doc does not exist yet (``docs/ops/digifetch-post-deploy-verification.md``).
After creation every assertion pins a fact the code owns (cohort names, the
served path, the smoke command, the escalation wording), so drift fails here
instead of in an operator's terminal. Pattern precedent:
``tests/scripts/test_mcp_container.py`` (header lines 9-14).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = REPO_ROOT / "docs" / "ops" / "digifetch-post-deploy-verification.md"

#: The #4069/#4101 phase-0 cohort: the 13 tools the post-deploy check must
#: find on the served surface (mcp_server.py:501-513). #4110 later grew the
#: family to 33 — the count is reported, the cohort is required.
PHASE0_COHORT = (
    "gloomberb_get_quote",
    "gloomberb_get_quotes_batch",
    "gloomberb_get_price_history",
    "gloomberb_get_ticker_financials",
    "gloomberb_get_options_chain",
    "gloomberb_get_sec_filings",
    "gloomberb_get_holders",
    "gloomberb_get_analyst_research",
    "gloomberb_get_corporate_actions",
    "yahoo_get_earnings_calendar",
    "gloomberb_get_exchange_rate",
    "gloomberb_search",
    "gloomberb_get_news",
)


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_doc_lists_the_phase0_cohort() -> None:
    text = _text()
    missing = [name for name in PHASE0_COHORT if name not in text]
    assert not missing, missing


def test_cohort_names_are_registered_read_scope_tools() -> None:
    pytest.importorskip("mcp.server.fastmcp")
    from digiquant.mcp_server import READ_SCOPE_TOOLS

    assert set(PHASE0_COHORT) <= READ_SCOPE_TOOLS
    assert (
        len(
            {
                n
                for n in READ_SCOPE_TOOLS
                if n.startswith("gloomberb_") or n == "yahoo_get_earnings_calendar"
            }
        )
        >= 13
    )


def test_doc_commands_match_the_shipped_serving_path() -> None:
    text = _text()
    assert "python -m digiquant.mcp_server --scope read" in text
    assert "http://127.0.0.1:8767/mcp" in text
    assert "GLOOMBERB_LIVE_SMOKE=1" in text
    assert "tests/dq/test_gloomberb_live_smoke.py" in text


def test_doc_records_results_on_the_issue() -> None:
    text = _text()
    assert "gh issue comment 4101" in text
    assert "#4101" in text


def test_doc_documents_drift_escalation() -> None:
    text = _text()
    assert "api.gloom.sh is an existing" in text
    assert "not new network exposure" in text


def test_doc_never_contains_a_literal_cookie_value() -> None:
    text = _text()
    for value in re.findall(r"session_token=(\S+)", text):
        assert value.startswith(("<", "$", "{")), value
    assert not re.search(r"eyJ[A-Za-z0-9_-]{10,}", text)
