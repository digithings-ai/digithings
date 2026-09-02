"""Checkpointer acquisition is best-effort (#667) — a bad URI must not crash the run.

Also covers WP4.1 (#2628): resume preserves the pinned ``knowledge_cutoff_at``
and missing cutoffs fail closed for new readers.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("openai")  # chain -> atlas.graph -> digigraph.llm needs openai

from digiquant.olympus.atlas.state import AtlasResearchState
from digiquant.olympus.hermes import chain
from digiquant.olympus.temporal import KnowledgeCutoffError, require_knowledge_cutoff_at


@pytest.mark.unit
def test_acquire_none_when_env_unset(monkeypatch):
    monkeypatch.delenv("DIGI_CHECKPOINTER", raising=False)
    assert chain._acquire_checkpointer() is None


@pytest.mark.unit
def test_acquire_returns_saver_when_available(monkeypatch):
    monkeypatch.setenv("DIGI_CHECKPOINTER", "postgres")
    sentinel = object()
    with patch("digigraph.graph.graph.get_checkpointer", return_value=sentinel):
        assert chain._acquire_checkpointer() is sentinel


@pytest.mark.unit
def test_acquire_degrades_to_none_on_init_failure(monkeypatch):
    # Bad URI / unreachable Postgres → setup() raises → must degrade to None, not crash.
    monkeypatch.setenv("DIGI_CHECKPOINTER", "postgres")
    with patch(
        "digigraph.graph.graph.get_checkpointer",
        side_effect=RuntimeError("could not connect to server"),
    ):
        assert chain._acquire_checkpointer() is None


@pytest.mark.unit
def test_resume_preserves_checkpointed_knowledge_cutoff() -> None:
    """Resuming invoke(None) keeps the checkpoint cutoff — no wall-clock re-pin."""
    pinned = datetime(2026, 4, 26, 8, 0, 0, tzinfo=UTC)
    checkpointed = AtlasResearchState(
        run_type="baseline",
        run_date=date(2026, 4, 26),
        knowledge_cutoff_at=pinned,
    )
    # Fresh state that would re-pin a different cutoff if resume wrongly used it.
    fresh = AtlasResearchState(
        run_type="baseline",
        run_date=date(2026, 4, 26),
        knowledge_cutoff_at=datetime(2026, 4, 26, 23, 59, 59, tzinfo=UTC),
    )

    checkpointer = SimpleNamespace(get_tuple=MagicMock(return_value=object()))
    graph = MagicMock()
    graph.invoke.return_value = checkpointed

    result = chain._invoke_resumable(
        graph,
        fresh,
        checkpointer,
        thread_base="run-abc",
        suffix="atlas",
    )

    graph.invoke.assert_called_once_with(
        None,
        {"configurable": {"thread_id": "run-abc::atlas"}},
    )
    assert require_knowledge_cutoff_at(result) == pinned
    assert result.knowledge_cutoff_at != fresh.knowledge_cutoff_at


@pytest.mark.unit
def test_resume_missing_cutoff_fails_closed_for_readers() -> None:
    """Legacy checkpoint without cutoff must not invent now() for new readers."""
    legacy = AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))
    assert legacy.knowledge_cutoff_at is None

    checkpointer = SimpleNamespace(get_tuple=MagicMock(return_value=object()))
    graph = MagicMock()
    graph.invoke.return_value = legacy

    result = chain._invoke_resumable(
        graph,
        AtlasResearchState(
            run_type="baseline",
            run_date=date(2026, 4, 26),
            knowledge_cutoff_at=datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC),
        ),
        checkpointer,
        thread_base="run-legacy",
        suffix="hermes",
    )

    with pytest.raises(KnowledgeCutoffError, match="no now\\(\\) fallback"):
        require_knowledge_cutoff_at(result)


@pytest.mark.unit
def test_resume_preserves_checkpointed_research_state_pin() -> None:
    """Resuming invoke(None) keeps the research-state pin — no re-select (#2863)."""
    pinned_cutoff = datetime(2026, 4, 26, 8, 0, 0, tzinfo=UTC)
    pin_dump = {
        "run_id": "run-abc",
        "attempt_id": "1",
        "state_version_id": "11111111-1111-4111-8111-111111111111",
        "knowledge_cutoff_at": pinned_cutoff.isoformat().replace("+00:00", "Z"),
        "requested_as_of": pinned_cutoff.isoformat().replace("+00:00", "Z"),
        "pinned_at": pinned_cutoff.isoformat().replace("+00:00", "Z"),
    }
    checkpointed = AtlasResearchState(
        run_type="baseline",
        run_date=date(2026, 4, 26),
        knowledge_cutoff_at=pinned_cutoff,
        research_state_pin=pin_dump,
        research_state_status="pinned",
    )
    fresh = AtlasResearchState(
        run_type="baseline",
        run_date=date(2026, 4, 26),
        knowledge_cutoff_at=datetime(2026, 4, 26, 23, 59, 59, tzinfo=UTC),
        research_state_status=None,
        research_state_pin=None,
    )

    checkpointer = SimpleNamespace(get_tuple=MagicMock(return_value=object()))
    graph = MagicMock()
    graph.invoke.return_value = checkpointed

    result = chain._invoke_resumable(
        graph,
        fresh,
        checkpointer,
        thread_base="run-abc",
        suffix="atlas",
    )

    graph.invoke.assert_called_once_with(
        None,
        {"configurable": {"thread_id": "run-abc::atlas"}},
    )
    assert result.research_state_status == "pinned"
    assert result.research_state_pin == pin_dump
    assert result.research_state_pin != fresh.research_state_pin
