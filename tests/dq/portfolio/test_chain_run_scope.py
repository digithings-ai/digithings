"""Where the run identifier enters the chain, and what happens when it cannot (#1978).

Detailed telemetry is keyed by the same run id the diagnostics row uses, so Task 1.5 can
reconcile the two. The interesting cases are the ones with no identifier: they must record
nothing rather than mint an identity that could silently join two unrelated runs.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from digiquant.research.graph import AtlasInput
from digiquant.portfolio import chain as chain_mod

pytestmark = pytest.mark.unit


def _atlas_input() -> AtlasInput:
    return AtlasInput(cadence="weekly", run_date=date(2026, 6, 20))


def test_resolve_run_id_prefers_github_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_RUN_ID", "99")
    assert chain_mod.resolve_run_id(_atlas_input()) == "99"


def test_resolve_run_id_falls_back_to_a_self_labelled_local_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    resolved = chain_mod.resolve_run_id(_atlas_input())
    assert resolved == "weekly-2026-06-20-local"
    # `-local` is a suffix no GitHub run id can carry, so an off-CI run can never be joined
    # to a CI run by mistake.
    assert resolved.endswith("-local")


def _capture_start(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    def _fake_start(**kwargs: Any) -> None:
        seen.update(kwargs)

    monkeypatch.setattr(chain_mod._usage, "start", _fake_start)
    monkeypatch.setattr(chain_mod._usage, "reset", lambda: None)
    return seen


def _run_beliefs_only(monkeypatch: pytest.MonkeyPatch, deps: Any) -> None:
    """Drive the shortest path through run_atlas_then_hermes that still calls _usage.start()."""
    monkeypatch.setattr(chain_mod, "_run_beliefs_fold", lambda *a, **k: None)
    monkeypatch.setattr(chain_mod, "_write_diagnostics_row", lambda *a, **k: None, raising=False)
    # `daily` is the only cadence AtlasResearchState accepts; the run must reach _usage.start().
    atlas_input = AtlasInput(cadence="daily", run_date=date(2026, 6, 20), refresh_scope="beliefs")
    try:
        chain_mod.run_atlas_then_hermes(atlas_input=atlas_input, deps=deps)
    except Exception:
        # The run may fail-soft further down; the assertion is only about what start() got.
        pass


def test_run_scope_uses_the_diagnostics_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _capture_start(monkeypatch)
    deps = chain_mod.ChainDeps(
        atlas=None,
        hermes=None,
        diagnostics=chain_mod.DiagnosticsDeps(client=None, run_id="gha-1978"),
    )
    _run_beliefs_only(monkeypatch, deps)
    assert seen == {"run_id": "gha-1978"}


def test_manage_usage_false_does_not_start_or_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Overlay cron owns WP1 capture; nested chain start/reset would wipe the ledger."""
    seen_start: list[object] = []
    seen_reset: list[object] = []
    monkeypatch.setattr(chain_mod._usage, "start", lambda **k: seen_start.append(k))
    monkeypatch.setattr(chain_mod._usage, "reset", lambda: seen_reset.append(1))
    monkeypatch.setattr(chain_mod, "_run_beliefs_fold", lambda *a, **k: None)
    deps = chain_mod.ChainDeps(atlas=None, hermes=None)
    atlas_input = AtlasInput(cadence="daily", run_date=date(2026, 6, 20), refresh_scope="beliefs")
    chain_mod.run_atlas_then_hermes(atlas_input=atlas_input, deps=deps, manage_usage=False)
    assert seen_start == []
    assert seen_reset == []


def test_run_scope_is_unavailable_without_diagnostics_deps(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _capture_start(monkeypatch)
    # diagnostics defaults to None for library and test callers. Unavailable, never fabricated:
    # such a run also writes no diagnostics row, so there is nothing to reconcile against.
    deps = chain_mod.ChainDeps(atlas=None, hermes=None)
    _run_beliefs_only(monkeypatch, deps)
    assert seen == {"run_id": None}


def test_fanout_ticker_reads_back_the_send_cursor() -> None:
    """The H5/H6 discriminator is the cursor `with_fanout_ticker` injected — nothing parsed."""
    from digiquant.portfolio.focus_roster import fanout_ticker, with_fanout_ticker
    from digiquant.portfolio.state import HermesState

    state = HermesState(run_type="delta", run_date=date(2026, 6, 20))
    assert fanout_ticker(state) is None, "no cursor means no key, never a fabricated one"
    assert fanout_ticker(with_fanout_ticker(state, "GLD")) == "GLD"


def test_h5_and_h6_fanouts_declare_the_telemetry_discriminator() -> None:
    """Without `item_key` the H5/H6 workers would record `fanout_key=None` for every ticker."""
    from digiquant.portfolio.focus_roster import fanout_ticker
    from digiquant.portfolio.phases import h5_asset_analyst, h6_deliberation

    h5 = h5_asset_analyst.build_h5_from_state(client=None)
    h6 = h6_deliberation.build_h6_from_state()
    assert h5.item_key is fanout_ticker
    assert h6.item_key is fanout_ticker
