"""PM direction skill prompt documents held-name carry-forward (#937, PR 4c).

H7 injects ``prior_analyst_gaps`` into ``phase_inputs`` for held tickers without a
fresh H5 payload. The ``pm-direction`` skill must document that input and instruct
the PM not to auto-flat a held name solely because it is absent from
``analyst_payloads``.
"""

from __future__ import annotations

import pytest

from digiquant.olympus.hermes.skills import load_skill_full

pytestmark = pytest.mark.unit


def _pm_skill_body() -> str:
    return load_skill_full("pm-direction")


class TestPriorAnalystGapsDocumented:
    def test_input_listed(self) -> None:
        body = _pm_skill_body()
        assert "prior_analyst_gaps" in body
        assert "- `prior_analyst_gaps`" in body or "`prior_analyst_gaps`" in body

    def test_no_auto_exit_on_gap_rule(self) -> None:
        body = _pm_skill_body()
        assert "prior_analyst_gaps" in body
        assert "analyst_payloads" in body
        lowered = body.lower()
        assert "flat" in lowered or "exit" in lowered

    def test_skill_full_loads(self) -> None:
        body = load_skill_full("pm-direction")
        assert "conviction_rank" in body
        assert "MUST NOT" in body or "Prohibited" in body or "prohibited" in body.lower()
