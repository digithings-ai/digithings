"""PM skill prompt documents the prior_analyst_gaps carry-forward (#937).

The Phase 7D PM node injects ``prior_analyst_gaps`` into ``phase_inputs`` for held
tickers that carry a prior analyst summary but have no fresh ``analyst_payloads``
entry this run. The ``pm-rebalance-decision`` skill prompt must document that input
and instruct the PM not to auto-exit a held name solely because it is absent from
``analyst_payloads`` — otherwise the carry-forward is silently ignored.
"""

from __future__ import annotations

import pytest

from digiquant.olympus.hermes.skills import load_skill_with_frontmatter

pytestmark = pytest.mark.unit


def _pm_skill_body() -> str:
    fm, body = load_skill_with_frontmatter("pm-rebalance-decision")
    assert fm.get("name") == "pm-rebalance-decision"
    return body


class TestPriorAnalystGapsDocumented:
    def test_input_listed(self) -> None:
        body = _pm_skill_body()
        # Documented as an input alongside analyst_payloads / prior_book.
        assert "prior_analyst_gaps" in body
        assert "- `prior_analyst_gaps`" in body

    def test_no_auto_exit_on_gap_rule(self) -> None:
        body = _pm_skill_body()
        # The rule must reference the input and forbid exiting on slate absence alone.
        assert "prior_analyst_gaps" in body
        assert "analyst_payloads" in body
        lowered = body.lower()
        assert "must not exit" in lowered
        assert "absent from" in lowered
