from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest
from digiquant.research.snapshot import DigestPayload
from digiquant.stages import (
    ConsensusTimeframe,
    ExecutionOptInRequired,
    LevelStatus,
    ResearchDigest,
    TradeIdeaLevels,
    TradeIdeaSnapshot,
    refuse_order_intent,
    research_digest_from_digest_payload,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def _minimal_idea() -> TradeIdeaSnapshot:
    return TradeIdeaSnapshot(
        run_date=date(2026, 9, 29),
        rank=1,
        pair="USD/JPY",
        direction="long",
        title="t",
        thesis="th",
        catalyst="c",
        consensus_timeframe=ConsensusTimeframe.MEDIUM,
    )


def test_research_digest_from_digest_payload() -> None:
    payload = DigestPayload(date=date(2026, 9, 29), body="hello", regime_label="Risk-on")
    digest = research_digest_from_digest_payload(payload)
    assert digest.run_date == date(2026, 9, 29)
    assert digest.body == "hello"
    assert digest.regime_label == "Risk-on"
    assert digest.source == "digiquant.research"
    assert digest.composition_id == "digiquant-baseline"


def test_empty_body_payload_raises() -> None:
    # body="" with no date and no legacy sections: the briefing has no date,
    # so the handoff refuses rather than inventing one.
    payload = DigestPayload.model_construct(body="")
    with pytest.raises(ValueError, match="missing date or body"):
        research_digest_from_digest_payload(payload)


def test_research_digest_rejects_unknown_composition() -> None:
    with pytest.raises(ValidationError):
        ResearchDigest(
            run_date=date(2026, 9, 29),
            body="hello",
            regime_label="Risk-on",
            source="digiquant.research",
            composition_id="other",  # type: ignore[arg-type]
        )


def test_refuse_order_intent_raises() -> None:
    with pytest.raises(ExecutionOptInRequired, match="does not execute"):
        refuse_order_intent(_minimal_idea())


def test_stages_tree_has_no_execution_imports() -> None:
    root = Path("digiquant/src/digiquant/stages")
    assert root.is_dir()
    banned = (
        "digiquant.execution",
        "digiquant.brokers",
        "digiquant.portfolio.models.portfolio_ledger",
    )
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            module: str | None = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(b in alias.name for b in banned):
                        offenders.append(f"{path}:{node.lineno}:{alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if any(b in module for b in banned):
                    offenders.append(f"{path}:{node.lineno}:{module}")
    assert offenders == []


def test_levels_reject_unknown_provenance() -> None:
    with pytest.raises(ValidationError):
        TradeIdeaLevels(
            targets=[
                {"value": "1.0", "provenance": "guessed", "source_ref": "x"},
            ],
            status=LevelStatus.COMPLETE,
        )
