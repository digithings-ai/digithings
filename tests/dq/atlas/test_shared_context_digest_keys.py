"""Regression coverage for #1270.

`_shared_context`'s `context_keys` whitelist filters `prior_context.latest_segments`
(one entry per literal `document_key` string) down to what a phase actually
consumes. The digest is published as `digest` on baseline runs and `digest-delta`
on delta runs (`atlas/phases/publish_phase.py`), so a whitelist missing either
real key — or listing a key nothing ever writes, like the old `digest-baseline` —
silently drops or keeps-stale the wrong digest instead of raising.
"""

from __future__ import annotations

import pathlib
from datetime import date

import pytest

import digiquant.olympus.hermes.phases as hermes_phases_pkg
from digiquant.olympus.atlas.phases._node_factory import _shared_context
from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState, PriorContext


def _state_with_latest_segments(latest_segments: dict) -> AtlasResearchState:
    return AtlasResearchState(
        run_type="delta",
        run_date=date(2026, 6, 8),
        config=AtlasConfigBundle(watchlist=["AAPL"]),
        prior_context=PriorContext(latest_segments=latest_segments),
    )


@pytest.mark.unit
def test_shared_context_keeps_both_digest_keys_when_whitelisted():
    state = _state_with_latest_segments(
        {
            "digest": {"headline": "baseline digest"},
            "digest-delta": {"headline": "delta digest"},
            "pm-rebalance": {"actions": []},
        }
    )
    ctx = _shared_context(state, context_keys=("pm-rebalance", "digest", "digest-delta"))
    assert set(ctx["prior_context"]["latest_segments"]) == {
        "digest",
        "digest-delta",
        "pm-rebalance",
    }


@pytest.mark.unit
def test_shared_context_drops_digest_when_key_missing_from_whitelist():
    """Reproduces the bug: a whitelist missing the real key silently loses that
    digest, even when it's the freshest row in `latest_segments`."""
    state = _state_with_latest_segments(
        {
            "digest": {"headline": "baseline digest"},
            "digest-delta": {"headline": "stale digest-delta from last week"},
        }
    )
    # The old H7 tuple: ("pm-rebalance", "digest-delta", "digest-baseline") —
    # "digest-baseline" is never written by anything, so the day after a
    # baseline run this kept the stale digest-delta row instead of the fresh
    # baseline one.
    buggy_ctx = _shared_context(
        state, context_keys=("pm-rebalance", "digest-delta", "digest-baseline")
    )
    assert set(buggy_ctx["prior_context"]["latest_segments"]) == {"digest-delta"}

    fixed_ctx = _shared_context(state, context_keys=("pm-rebalance", "digest", "digest-delta"))
    assert set(fixed_ctx["prior_context"]["latest_segments"]) == {"digest", "digest-delta"}


@pytest.mark.unit
def test_live_h_phases_never_reference_dead_digest_baseline_key():
    """`digest-baseline` is never published by anything. Guard against the typo
    reappearing in the live H1-H9 phase modules. `phase7d_pm.py` is deliberately
    excluded — confirmed unreachable from any production graph builder
    (`hermes/graph.py::build_hermes_phases` aliases to the thesis-first graph,
    never `phase7d_pm.build_phase7d_pm`), so it isn't fixed as part of #1270.
    """
    phases_dir = pathlib.Path(hermes_phases_pkg.__file__).parent
    live_h_files = sorted(phases_dir.glob("h*.py"))
    assert live_h_files, "expected to find the h1..h9 phase modules"

    # Match the quoted string literal, not the bare phrase — code comments are
    # free to *discuss* the dead key (as h7_pm_direction.py's now does) without
    # tripping this guard; only an actual `"digest-baseline"` tuple element should.
    offenders = [f.name for f in live_h_files if '"digest-baseline"' in f.read_text()]
    assert offenders == []
