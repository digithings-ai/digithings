"""H7 fail-soft (#1665): an LLM-output failure carries the prior memo, never raises.

Three runs in two days (2026-07-21/22) died with ``chain/hermes: Expecting value: …``
— a research-agent JSON failure escaping a hermes node, marking the run failed and
burning ~$1.2–3.6 per outer retry. Every hermes LLM node is now fail-soft; this file
pins the H7 memo node (the highest-stakes one: no memo → no PM direction).
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from digiquant.olympus.atlas.state import AtlasResearchState, PriorContext
from digiquant.olympus.hermes.phases.h7_pm_direction import NODE_ID, _h7_node

pytestmark = pytest.mark.unit

RUN_DATE = date(2026, 7, 23)
PRIOR_MEMO_PAYLOAD = {
    "schema_version": "1.0",
    "date": "2026-07-22",
    "roster": [
        {"ticker": "SPY", "direction": "long", "conviction_rank": 1},
        {"ticker": "TLT", "direction": "flat", "conviction_rank": 2},
    ],
    "memo": "prior direction",
}


def _state(*, with_prior_memo: bool) -> AtlasResearchState:
    latest = {"pm-direction-memo": {"payload": dict(PRIOR_MEMO_PAYLOAD)}} if with_prior_memo else {}
    return AtlasResearchState(
        run_type="delta",
        run_date=RUN_DATE,
        baseline_date=date(2026, 7, 21),
        prior_context=PriorContext(latest_segments=latest),
    )


class TestH7FailSoft:
    def test_llm_failure_carries_prior_memo_without_raising(self) -> None:
        state = _state(with_prior_memo=True)
        with patch(
            "digiquant.olympus.hermes.phases.h7_pm_direction.run_research_agent",
            side_effect=ValueError("Expecting value: line 201 column 1 (char 1100)"),
        ):
            out = _h7_node(state)

        memo = out["phase_hermes"].pm_direction_memo
        assert memo is not None, "prior memo must be carried"
        assert memo.date == RUN_DATE, "carried memo must be re-dated to today"
        assert [e.ticker for e in memo.roster] == ["SPY", "TLT"]
        errors = out.get("errors") or []
        assert len(errors) == 1
        assert errors[0].phase != "chain", "must be a node-level error, not chain-fatal"
        assert errors[0].node == NODE_ID
        assert errors[0].retryable is False

    def test_llm_failure_without_prior_memo_degrades_to_none(self) -> None:
        state = _state(with_prior_memo=False)
        with patch(
            "digiquant.olympus.hermes.phases.h7_pm_direction.run_research_agent",
            side_effect=ValueError("Expecting value: line 1 column 1 (char 0)"),
        ):
            out = _h7_node(state)

        assert out["phase_hermes"].pm_direction_memo is None, "no prior → legacy sizing path"
        errors = out.get("errors") or []
        assert len(errors) == 1 and errors[0].phase != "chain"
