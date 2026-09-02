"""H5 evidence-bundle build + publish (#2892 / WP11.2).

Red coverage: canonical dedupe; event/known/source times; conflicts/missing
fields; forecast cites bundle/evidence IDs; durable writer disable retains
typed in-run bundle. H5 provider-path wiring lives in ``tests/dq/portfolio/``
(atlas-graph CI has digigraph deps).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import UUID

import pytest
from digiquant.portfolio.models.forecast import ForecastTerms
from digiquant.dashboard.research_retrieval.models import (
    TypedProvenance,
    evidence_content_hash,
    evidence_record_id,
)
from digiquant.dashboard.research_retrieval.store import EvidenceBundleStore
from pydantic import ValidationError

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 26, 16, 0, tzinfo=UTC)
_STATE = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
_PROV = TypedProvenance(
    source_run_id="run-wp112",
    attempt_id="1",
    artifact_id="artifact-h5-AAPL",
)


def _terms(**overrides: object) -> ForecastTerms:
    fields: dict[str, object] = dict(
        horizon_sessions=21,
        half_life_sessions=10,
        bear_return="-0.05",
        base_return="0.03",
        bull_return="0.08",
        bear_probability="0.25",
        base_probability="0.50",
        bull_probability="0.25",
        thesis_valid_probability="0.6",
        raw_uncertainty="medium",
        evidence_ids=(),
        counter_evidence_ids=(),
        assumptions=("carry prior",),
        invalidation_rules=("break below support",),
    )
    fields.update(overrides)
    return ForecastTerms.model_validate(fields)


def test_build_dedupes_identical_facts() -> None:
    from digiquant.dashboard.research_retrieval.evidence_bundle import (
        H5EvidenceFact,
        build_h5_evidence_bundle,
    )

    fact = H5EvidenceFact(
        source="https://example.com/a",
        authority="web_grounding",
        summary="AAPL beat estimates",
        event_time=_TS - timedelta(hours=3),
        effective_as_of=_TS - timedelta(hours=2),
        known_at=_TS - timedelta(hours=1),
    )
    built = build_h5_evidence_bundle(
        ticker="aapl",
        source_run_id="run-wp112",
        attempt_id="1",
        state_version_id=_STATE,
        facts=(fact, fact),
        recorded_at=_TS,
        provenance=_PROV,
    )
    assert len(built.evidence) == 1
    assert len(built.bundle.evidence_ids) == 1
    assert built.conflicts == ()


def test_build_records_conflicts_and_missing_fields() -> None:
    from digiquant.dashboard.research_retrieval.evidence_bundle import (
        H5EvidenceFact,
        build_h5_evidence_bundle,
    )

    left = H5EvidenceFact(
        source="reuters",
        authority="web_grounding",
        summary="guidance raised",
        event_time=_TS - timedelta(hours=4),
        effective_as_of=_TS - timedelta(hours=3),
        known_at=_TS - timedelta(hours=2),
    )
    right = H5EvidenceFact(
        source="reuters",
        authority="web_grounding",
        summary="guidance cut",
        event_time=_TS - timedelta(hours=3),
        effective_as_of=_TS - timedelta(hours=2),
        known_at=_TS - timedelta(hours=1),
    )
    built = build_h5_evidence_bundle(
        ticker="AAPL",
        source_run_id="run-wp112",
        attempt_id="1",
        state_version_id=_STATE,
        facts=(left, right),
        recorded_at=_TS,
        provenance=_PROV,
        missing_fields=("web_grounding.sources",),
    )
    assert len(built.evidence) == 2
    assert len(built.conflicts) == 1
    assert built.conflicts[0].reason == "same_source_authority_divergent_summary"
    assert built.missing_fields[0].field == "web_grounding.sources"
    # Bundle times span earliest event → latest known → recorded.
    assert built.bundle.event_time == left.event_time
    assert built.bundle.known_at == right.known_at
    assert built.bundle.recorded_at == _TS
    assert built.bundle.source == "h5:base"


def test_facts_from_phase_inputs_skip_portfolio_leakage() -> None:
    from digiquant.dashboard.research_retrieval.evidence_bundle import facts_from_phase_inputs

    facts, missing = facts_from_phase_inputs(
        ticker="AAPL",
        phase_inputs={
            "web_grounding": {
                "summary": "chip demand firm",
                "sources": ["https://reuters.com/a"],
                "as_of": "2026-08-26",
            },
            "price_deltas": {"AAPL": 0.02},
            "held_in_prior_book": True,
            "active_theses": [{"thesis_id": "t1"}],
            "bias_row": {"regime": "risk_on"},
        },
        knowledge_cutoff_at=_TS,
    )
    sources = {f.source for f in facts}
    authorities = {f.authority for f in facts}
    assert "https://reuters.com/a" in sources or "web_grounding" in authorities
    assert "price_delta" in authorities
    assert "bias_row" in authorities
    assert "held_in_prior_book" not in authorities
    assert "active_theses" not in authorities
    assert "portfolio" not in " ".join(authorities).lower()
    assert missing == ()


def test_publish_persists_when_writer_on() -> None:
    from digiquant.dashboard.research_retrieval.evidence_bundle import (
        H5EvidenceFact,
        build_h5_evidence_bundle,
        publish_h5_evidence_bundle,
    )

    fact = H5EvidenceFact(
        source="https://example.com/a",
        authority="web_grounding",
        summary="one",
        event_time=_TS - timedelta(hours=2),
        effective_as_of=_TS - timedelta(hours=1),
        known_at=_TS - timedelta(minutes=30),
    )
    built = build_h5_evidence_bundle(
        ticker="AAPL",
        source_run_id="run-wp112",
        attempt_id="1",
        state_version_id=_STATE,
        facts=(fact,),
        recorded_at=_TS,
        provenance=_PROV,
    )
    store = EvidenceBundleStore()
    with patch.dict("os.environ", {"OLYMPUS_EVIDENCE_BUNDLE_WRITER": "on"}, clear=False):
        published = publish_h5_evidence_bundle(built=built, store=store)
    assert published.bundle_id == built.bundle.bundle_id
    assert (
        store.base_bundle_count_for(
            run_id="run-wp112", ticker="AAPL", content_hash=built.bundle.content_hash
        )
        == 1
    )


def test_publish_skips_store_when_writer_off_retains_typed() -> None:
    from digiquant.dashboard.research_retrieval.evidence_bundle import (
        H5EvidenceFact,
        build_h5_evidence_bundle,
        publish_h5_evidence_bundle,
    )

    fact = H5EvidenceFact(
        source="https://example.com/a",
        authority="web_grounding",
        summary="one",
        event_time=_TS - timedelta(hours=2),
        effective_as_of=_TS - timedelta(hours=1),
        known_at=_TS - timedelta(minutes=30),
    )
    built = build_h5_evidence_bundle(
        ticker="AAPL",
        source_run_id="run-wp112",
        attempt_id="1",
        state_version_id=_STATE,
        facts=(fact,),
        recorded_at=_TS,
        provenance=_PROV,
    )
    store = EvidenceBundleStore()
    with patch.dict("os.environ", {"OLYMPUS_EVIDENCE_BUNDLE_WRITER": "off"}, clear=False):
        published = publish_h5_evidence_bundle(built=built, store=store)
    assert published.bundle_id == built.bundle.bundle_id
    assert (
        store.base_bundle_count_for(
            run_id="run-wp112", ticker="AAPL", content_hash=built.bundle.content_hash
        )
        == 0
    )


def test_cite_forecast_includes_bundle_and_evidence_ids() -> None:
    from digiquant.dashboard.research_retrieval.evidence_bundle import (
        H5EvidenceFact,
        build_h5_evidence_bundle,
        cite_evidence_bundle_on_forecast,
    )

    fact = H5EvidenceFact(
        source="https://example.com/a",
        authority="web_grounding",
        summary="one",
        event_time=_TS - timedelta(hours=2),
        effective_as_of=_TS - timedelta(hours=1),
        known_at=_TS - timedelta(minutes=30),
    )
    built = build_h5_evidence_bundle(
        ticker="AAPL",
        source_run_id="run-wp112",
        attempt_id="1",
        state_version_id=_STATE,
        facts=(fact,),
        recorded_at=_TS,
        provenance=_PROV,
    )
    terms = cite_evidence_bundle_on_forecast(_terms(evidence_ids=("llm-cite",)), built.bundle)
    assert "llm-cite" in terms.evidence_ids
    assert str(built.bundle.bundle_id) in terms.evidence_ids
    assert str(built.bundle.evidence_ids[0]) in terms.evidence_ids


def test_evidence_record_ids_reuse_wp12_helpers() -> None:
    """Bundle evidence leaves use WP12 EvidenceRecord identity — no parallel scheme."""
    from digiquant.dashboard.research_retrieval.evidence_bundle import (
        H5EvidenceFact,
        build_h5_evidence_bundle,
    )

    fact = H5EvidenceFact(
        source="https://example.com/a",
        authority="web_grounding",
        summary="one",
        event_time=_TS - timedelta(hours=2),
        effective_as_of=_TS - timedelta(hours=1),
        known_at=_TS - timedelta(minutes=30),
    )
    built = build_h5_evidence_bundle(
        ticker="AAPL",
        source_run_id="run-wp112",
        attempt_id="1",
        state_version_id=_STATE,
        facts=(fact,),
        recorded_at=_TS,
        provenance=_PROV,
    )
    ev = built.evidence[0]
    digest = evidence_content_hash(
        source=ev.source,
        authority=ev.authority,
        summary=ev.summary,
        contradiction_of=ev.contradiction_of,
    )
    assert ev.content_hash == digest
    assert ev.evidence_id == evidence_record_id(
        source=ev.source, authority=ev.authority, content_hash=digest
    )


def test_h5_evidence_fact_rejects_blank_summary() -> None:
    from digiquant.dashboard.research_retrieval.evidence_bundle import H5EvidenceFact

    with pytest.raises(ValidationError):
        H5EvidenceFact(
            source="x",
            authority="web_grounding",
            summary="  ",
            event_time=_TS,
            effective_as_of=_TS,
            known_at=_TS,
        )


def test_facts_from_phase_inputs_preserves_long_web_grounding_summary() -> None:
    """Long web_grounding prose must pass without max_length/truncate (#3063)."""
    from digiquant.dashboard.research_retrieval.evidence_bundle import (
        H5EvidenceFact,
        facts_from_phase_inputs,
    )

    long_summary = (
        "Here are the key findings from overnight macro desks. " * 20
        + "https://dailymarket.report/"
    )
    assert len(long_summary) > 500

    facts, missing = facts_from_phase_inputs(
        ticker="SPY",
        phase_inputs={
            "web_grounding": {
                "summary": long_summary,
                "sources": ["https://dailymarket.report/"],
                "as_of": "2026-08-27",
            },
            "price_deltas": {"SPY": -0.004},
        },
        knowledge_cutoff_at=_TS,
    )
    web_facts = [f for f in facts if f.authority == "web_grounding"]
    assert len(web_facts) == 1
    assert web_facts[0].summary == long_summary.strip()
    assert len(web_facts[0].summary) == len(long_summary.strip())
    assert missing == ()

    direct = H5EvidenceFact(
        source="https://example.com",
        authority="web_grounding",
        summary=long_summary,
        event_time=_TS,
        effective_as_of=_TS,
        known_at=_TS,
    )
    assert direct.summary == long_summary.strip()
