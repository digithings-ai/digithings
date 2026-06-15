"""Chain safety net (Pillar 1B).

A failing terminal phase (risk-sizing / publish / materialize) or a graph-level crash must
be recorded and swallowed so the run still reaches the remaining phases + the diagnostics
write — never a hard abort that leaves the dashboard stale.
"""

from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.atlas.state import AtlasResearchState
from digiquant.olympus.hermes.chain import _record_chain_error, _run_terminal_phase

pytestmark = pytest.mark.unit


def _state() -> AtlasResearchState:
    return AtlasResearchState(
        run_type="delta", run_date=date(2026, 6, 12), baseline_date=date(2026, 6, 9)
    )


def test_terminal_phase_none_deps_is_noop() -> None:
    state = _state()
    assert _run_terminal_phase(None, lambda _d: None, state, "publish") is state
    assert state.errors == []


def test_terminal_phase_swallows_failure_and_records_error() -> None:
    state = _state()

    def _boom(_deps):
        raise RuntimeError("publish exploded")

    out = _run_terminal_phase(object(), _boom, state, "publish")
    assert out is state  # last-good state returned, not raised
    # Chain-level errors are marked phase="chain" (node = which stage) so the diagnostics
    # gate can distinguish them from node-level errors.
    assert [(e.phase, e.node) for e in state.errors] == [("chain", "publish")]
    assert "publish exploded" in state.errors[0].message


def test_record_chain_error_appends_phase_error() -> None:
    state = _state()
    _record_chain_error(state, "atlas", RuntimeError("graph crash"))
    assert state.errors[-1].phase == "chain"
    assert state.errors[-1].node == "atlas"
    assert "graph crash" in state.errors[-1].message
