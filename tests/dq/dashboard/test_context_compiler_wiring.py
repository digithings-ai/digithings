"""WP14.1 context capsule wiring into the analyst and deliberation prompts.

Red coverage: the rollout modes, the prompt byte delta, the escape hatch and
the strict bundle-state pinning on the live path."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from digiquant.dashboard.research_retrieval.store import LoadedResearchState, ResearchStateStore

from tests.dq.dashboard.context_compiler_support import (
    _TICKER,
    _TS,
    _belief,
    _bundle,
    _evidence,
    _loaded_state,
)

pytestmark = pytest.mark.unit


def _store_with_state(state: LoadedResearchState) -> ResearchStateStore:
    store = ResearchStateStore()
    for record in state.evidence:
        store.append_evidence(record)
    for belief in state.beliefs:
        store.append_belief(belief)
    for event in state.expected_events:
        store.append_expected_event(event)
    for patch in state.patches:
        store.append_patch(patch)
    known_times = [state.version.known_at]
    known_times.extend(record.known_at for record in state.evidence)
    known_times.extend(belief.known_at for belief in state.beliefs)
    known_times.extend(event.known_at for event in state.expected_events)
    known_times.extend(patch.known_at for patch in state.patches)
    version = state.version.model_copy(
        update={
            "known_at": max(known_times),
            "recorded_at": _TS,
        }
    )
    store.append_state_version(version)
    return store


def _seed_loaded_state(
    loaded: LoadedResearchState,
) -> tuple[ResearchStateStore, dict[str, str], UUID]:
    store = _store_with_state(loaded)
    version_id = next(iter(store._versions))
    return store, {"state_version_id": str(version_id)}, version_id


def test_wire_analyst_off_leaves_incumbent_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_CONTEXT_COMPILER_MODE", "off")
    ev = _evidence(summary="Filed 8-K")
    loaded = _loaded_state(evidence=(ev,))
    store, pin, version_id = _seed_loaded_state(loaded)
    bundle = _bundle(state_version_id=version_id)
    incumbent = {
        "ticker": _TICKER,
        "prior_book": [{"ticker": "MSFT", "weight_pct": 5.0}],
        "active_theses": [{"thesis_id": "t1"}],
    }
    from digiquant.dashboard.research_retrieval.context_wiring import wire_analyst_phase_inputs

    result = wire_analyst_phase_inputs(
        incumbent,
        ticker=_TICKER,
        bundle=bundle,
        research_state_pin=pin,
        research_state_store=store,
    )
    assert result.capsule is None
    assert result.manifest is None
    assert result.phase_inputs == incumbent


def test_wire_analyst_shadow_records_manifest_beside_incumbent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIGIQUANT_CONTEXT_COMPILER_MODE", "shadow")
    ev = _evidence(summary="Filed 8-K")
    loaded = _loaded_state(evidence=(ev,))
    store, pin, version_id = _seed_loaded_state(loaded)
    bundle = _bundle(state_version_id=version_id)
    incumbent = {"ticker": _TICKER, "prior_book": [{"ticker": "MSFT"}]}
    from digiquant.dashboard.research_retrieval.context_wiring import wire_analyst_phase_inputs

    result = wire_analyst_phase_inputs(
        incumbent,
        ticker=_TICKER,
        bundle=bundle,
        research_state_pin=pin,
        research_state_store=store,
        changed_evidence_ids=frozenset({ev.evidence_id}),
    )
    assert result.capsule is not None
    assert result.manifest is not None
    assert result.phase_inputs["prior_book"] == incumbent["prior_book"]
    # #4609: shadow blobs no longer ride in the uncached prompt block — the
    # capsule/manifest objects on the result carry the data.
    assert "context_capsule_shadow" not in result.phase_inputs
    assert "context_manifest_shadow" not in result.phase_inputs
    assert result.phase_inputs["context_manifest_id"] == str(result.manifest.manifest_id)


def test_wire_h5_shadow_omits_capsule_from_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#4609: the shadow capsule/manifest must not be re-serialized into the
    uncached ``phase_inputs`` prompt block — the objects on the result carry them."""
    monkeypatch.setenv("DIGIQUANT_CONTEXT_COMPILER_MODE", "shadow")
    monkeypatch.delenv("DIGIQUANT_CONTEXT_SHADOW_IN_PROMPT", raising=False)
    ev = _evidence(summary="Filed 8-K")
    loaded = _loaded_state(evidence=(ev,))
    store, pin, version_id = _seed_loaded_state(loaded)
    bundle = _bundle(state_version_id=version_id)
    incumbent = {"ticker": _TICKER, "prior_book": [{"ticker": "MSFT"}]}
    from digiquant.dashboard.research_retrieval.context_wiring import wire_analyst_phase_inputs

    result = wire_analyst_phase_inputs(
        incumbent,
        ticker=_TICKER,
        bundle=bundle,
        research_state_pin=pin,
        research_state_store=store,
        changed_evidence_ids=frozenset({ev.evidence_id}),
    )
    assert result.capsule is not None
    assert result.manifest is not None
    assert "context_capsule_shadow" not in result.phase_inputs
    assert "context_manifest_shadow" not in result.phase_inputs
    # Linkage still present (cheap ids, not the blob).
    assert result.phase_inputs["context_capsule_id"] == str(result.capsule.capsule_id)
    assert result.phase_inputs["context_manifest_id"] == str(result.manifest.manifest_id)


def test_wire_h5_shadow_escape_hatch_restores_in_prompt_blobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#4609 escape hatch: truthy ``DIGIQUANT_CONTEXT_SHADOW_IN_PROMPT`` restores
    the pre-diet in-prompt shadow blobs."""
    monkeypatch.setenv("DIGIQUANT_CONTEXT_COMPILER_MODE", "shadow")
    monkeypatch.setenv("DIGIQUANT_CONTEXT_SHADOW_IN_PROMPT", "1")
    ev = _evidence(summary="Filed 8-K")
    loaded = _loaded_state(evidence=(ev,))
    store, pin, version_id = _seed_loaded_state(loaded)
    bundle = _bundle(state_version_id=version_id)
    incumbent = {"ticker": _TICKER, "prior_book": [{"ticker": "MSFT"}]}
    from digiquant.dashboard.research_retrieval.context_wiring import wire_analyst_phase_inputs

    result = wire_analyst_phase_inputs(
        incumbent,
        ticker=_TICKER,
        bundle=bundle,
        research_state_pin=pin,
        research_state_store=store,
        changed_evidence_ids=frozenset({ev.evidence_id}),
    )
    assert "context_capsule_shadow" in result.phase_inputs
    assert "context_manifest_shadow" in result.phase_inputs


def test_wire_h6_shadow_omits_capsule_and_keeps_incumbent_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#4609: the deliberation (H6) shadow blob is also dropped, and the incumbent
    ``base_evidence_bundle`` it was compiled from is left in place."""
    monkeypatch.setenv("DIGIQUANT_CONTEXT_COMPILER_MODE", "shadow")
    monkeypatch.delenv("DIGIQUANT_CONTEXT_SHADOW_IN_PROMPT", raising=False)
    ev = _evidence(summary="Bundle evidence")
    loaded = _loaded_state(evidence=(ev,))
    store, pin, version_id = _seed_loaded_state(loaded)
    bundle = _bundle(state_version_id=version_id)
    incumbent = {
        "ticker": _TICKER,
        "analyst_payload": {"stance": "buy", "ticker": _TICKER},
        "transcript": [{"role": "pm", "message": "challenge"}],
        "base_evidence_bundle": bundle.model_dump(mode="json"),
    }
    from digiquant.dashboard.research_retrieval.context_wiring import wire_deliberation_phase_inputs

    result = wire_deliberation_phase_inputs(
        incumbent,
        ticker=_TICKER,
        bundle=bundle,
        research_state_pin=pin,
        research_state_store=store,
    )
    assert result.capsule is not None
    assert result.manifest is not None
    assert "context_capsule_shadow" not in result.phase_inputs
    assert "context_manifest_shadow" not in result.phase_inputs
    assert result.phase_inputs["base_evidence_bundle"] == incumbent["base_evidence_bundle"]


def test_wire_shadow_prompt_byte_delta(monkeypatch: pytest.MonkeyPatch) -> None:
    """#4609 byte yardstick: the shadow blob is real serialized weight in the
    uncached prompt block — turning the escape hatch on puts it back."""
    import json

    ev = _evidence(summary="Bundle evidence")
    loaded = _loaded_state(evidence=(ev,))
    store, pin, version_id = _seed_loaded_state(loaded)
    bundle = _bundle(state_version_id=version_id)
    incumbent = {
        "ticker": _TICKER,
        "analyst_payload": {"stance": "buy", "ticker": _TICKER},
        "transcript": [{"role": "pm", "message": "challenge"}],
        "base_evidence_bundle": bundle.model_dump(mode="json"),
    }
    from digiquant.dashboard.research_retrieval.context_wiring import wire_deliberation_phase_inputs

    monkeypatch.setenv("DIGIQUANT_CONTEXT_COMPILER_MODE", "shadow")

    def _size() -> int:
        result = wire_deliberation_phase_inputs(
            incumbent,
            ticker=_TICKER,
            bundle=bundle,
            research_state_pin=pin,
            research_state_store=store,
        )
        return len(json.dumps(result.phase_inputs, default=str, sort_keys=True))

    monkeypatch.delenv("DIGIQUANT_CONTEXT_SHADOW_IN_PROMPT", raising=False)
    diet_size = _size()
    monkeypatch.setenv("DIGIQUANT_CONTEXT_SHADOW_IN_PROMPT", "1")
    legacy_size = _size()
    # Exact sizes are pinned so the numbers quoted in
    # docs/research/token-budget.md (#4609) stay reproducible from this fixture.
    assert diet_size == 1_219
    assert legacy_size == 2_785
    assert legacy_size > diet_size


def test_wire_analyst_enforce_strips_portfolio_and_injects_capsule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIGIQUANT_CONTEXT_COMPILER_MODE", "enforce")
    ev = _evidence(summary="Filed 8-K")
    belief = _belief(evidence=ev, statement="Base intact")
    loaded = _loaded_state(evidence=(ev,), beliefs=(belief,))
    store, pin, version_id = _seed_loaded_state(loaded)
    bundle = _bundle(state_version_id=version_id)
    incumbent = {
        "ticker": _TICKER,
        "prior_book": [{"ticker": "MSFT"}],
        "active_theses": [{"thesis_id": "t1"}],
        "held_in_prior_book": True,
        "weight_pct": 12.0,
    }
    from digiquant.dashboard.research_retrieval.context_wiring import wire_analyst_phase_inputs

    result = wire_analyst_phase_inputs(
        incumbent,
        ticker=_TICKER,
        bundle=bundle,
        research_state_pin=pin,
        research_state_store=store,
        changed_evidence_ids=frozenset({ev.evidence_id}),
    )
    assert "prior_book" not in result.phase_inputs
    assert "active_theses" not in result.phase_inputs
    assert "weight_pct" not in result.phase_inputs
    assert result.phase_inputs["structured_context"] == result.capsule.body
    assert f"evidence:{ev.evidence_id}" in result.manifest.included_entity_ids


def test_wire_deliberation_enforce_allows_transcript_and_analyst_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIGIQUANT_CONTEXT_COMPILER_MODE", "enforce")
    ev = _evidence(summary="Bundle evidence")
    loaded = _loaded_state(evidence=(ev,))
    store, pin, version_id = _seed_loaded_state(loaded)
    bundle = _bundle(state_version_id=version_id)
    incumbent = {
        "ticker": _TICKER,
        "analyst_payload": {"stance": "buy", "ticker": _TICKER},
        "transcript": [{"role": "pm", "message": "challenge"}],
        "prior_book": [{"ticker": "MSFT"}],
        "base_evidence_bundle": bundle.model_dump(mode="json"),
    }
    from digiquant.dashboard.research_retrieval.context_wiring import wire_deliberation_phase_inputs

    result = wire_deliberation_phase_inputs(
        incumbent,
        ticker=_TICKER,
        bundle=bundle,
        research_state_pin=pin,
        research_state_store=store,
    )
    assert "prior_book" not in result.phase_inputs
    assert "base_evidence_bundle" not in result.phase_inputs
    assert result.phase_inputs["analyst_payload"]["stance"] == "buy"
    assert result.phase_inputs["transcript"]
    assert result.phase_inputs["structured_context"]


def test_wire_deliberation_rejects_unpinned_bundle_state_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIGIQUANT_CONTEXT_COMPILER_MODE", "enforce")
    ev = _evidence(summary="Bundle evidence")
    loaded = _loaded_state(evidence=(ev,))
    wrong_bundle = _bundle(state_version_id=uuid4())
    store, pin, _version_id = _seed_loaded_state(loaded)
    from digiquant.dashboard.research_retrieval.context_wiring import wire_deliberation_phase_inputs

    with pytest.raises(ValueError, match="state_version_id"):
        wire_deliberation_phase_inputs(
            {"ticker": _TICKER},
            ticker=_TICKER,
            bundle=wrong_bundle,
            research_state_pin=pin,
            research_state_store=store,
        )
