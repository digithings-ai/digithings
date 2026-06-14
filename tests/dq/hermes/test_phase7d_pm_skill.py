"""Phase 7D PM skill selection + cash-first decision contract (#713).

The PM node must load the DB-first ``pm-rebalance-decision`` skill. The book is
the PM's conviction holdings only; the residual is CASH (a first-class defensive
position materialized downstream), never padded with a cash-proxy ETF. An empty
recommended_portfolio is a valid 100%-cash stance and passes through untouched.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any  # noqa: F401 — fake-completion dict shape
from unittest.mock import patch

import pytest

from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState
from digiquant.olympus.hermes.phases.phase7d_pm import _load_pm_skill, _pm_node
from digiquant.olympus.hermes.skills import SkillNotFoundError

pytestmark = pytest.mark.unit


# ── skill selection ──────────────────────────────────────────────────────────


def _loader_missing(*missing: str):
    """Fake skill loader that raises SkillNotFoundError for ``missing`` slugs."""

    def _load(slug: str) -> str:
        if slug in missing:
            raise SkillNotFoundError(slug)
        return f"<skill:{slug}>"

    return _load


class TestLoadPmSkill:
    def test_prefers_pm_rebalance_decision(self) -> None:
        assert _load_pm_skill(_loader_missing()) == "<skill:pm-rebalance-decision>"

    def test_falls_back_to_portfolio_manager(self) -> None:
        assert (
            _load_pm_skill(_loader_missing("pm-rebalance-decision")) == "<skill:portfolio-manager>"
        )

    def test_falls_back_to_legacy_memo_last(self) -> None:
        loader = _loader_missing("pm-rebalance-decision", "portfolio-manager")
        assert _load_pm_skill(loader) == "<skill:pm-allocation-memo>"

    def test_raises_when_all_missing(self) -> None:
        loader = _loader_missing("pm-rebalance-decision", "portfolio-manager", "pm-allocation-memo")
        with pytest.raises(RuntimeError, match="no PM skill found"):
            _load_pm_skill(loader)

    def test_pm_rebalance_decision_skill_file_present(self) -> None:
        from digiquant.olympus.hermes.skills import load_skill_with_frontmatter

        fm, body = load_skill_with_frontmatter("pm-rebalance-decision")
        assert fm.get("name") == "pm-rebalance-decision"
        assert "recommended_portfolio" in body
        # The skill must teach the cash-first residual, not cash-proxy padding.
        assert "100% cash" in body or "100 % cash" in body


# ── node decision contract ───────────────────────────────────────────────────


def _pm_state() -> AtlasResearchState:
    state = AtlasResearchState(
        run_type="baseline",
        run_date=date(2026, 6, 13),
        config=AtlasConfigBundle(watchlist=["SPY", "GLD"]),
    )
    state.phase6_bias_row = {"date": "2026-06-13", "equity_bias": "neutral"}
    state.phase7c_analysts = {"SPY": {"ticker": "SPY", "conviction_score": 0, "stance": "hold"}}
    return state


class TestPmNodeContract:
    def test_empty_book_passes_through_as_cash(self) -> None:
        # A no-conviction run → empty recommended_portfolio, untouched (no BIL pad).
        with patch(
            "digigraph.graph.research_agent.completion_text",
            return_value=json.dumps(
                {"recommended_portfolio": [], "actions": [], "notes": "defensive: 100% cash"}
            ),
        ):
            update = _pm_node(_pm_state())
        rebalance = update["phase7d_rebalance"]
        assert rebalance["recommended_portfolio"] == []
        assert rebalance["notes"] == "defensive: 100% cash"  # unchanged, no auto-suffix

    def test_conviction_book_passes_through_unchanged(self) -> None:
        with patch(
            "digigraph.graph.research_agent.completion_text",
            return_value=json.dumps(
                {
                    "recommended_portfolio": [{"ticker": "SPY", "target_pct": 40}],
                    "actions": [],
                    "notes": "40% SPY, 60% cash",
                }
            ),
        ):
            update = _pm_node(_pm_state())
        book = {
            w["ticker"]: w["target_pct"]
            for w in update["phase7d_rebalance"]["recommended_portfolio"]
        }
        assert book == {"SPY": 40.0}  # residual left as implicit cash, no BIL injected
