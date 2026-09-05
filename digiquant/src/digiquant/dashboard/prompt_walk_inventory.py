"""Prompt / structured-output walk inventory for digiquant nodes (#3424).

Static catalog used while Chris walks each node with digigraph product-graph
scaffolding (#3415). This is not a second orchestration layer — it names the
current contract so the walk can mark keep / reconsider / prose without
re-deriving phase builders.

Naming: digiquant research / portfolio only (no Olympus/Atlas/Hermes/Kairos).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

StructuredOutputStance = Literal["keep", "reconsider", "prose_preferred", "n_a"]


class PromptWalkNode(BaseModel):
    """One pipeline node in the prompt + structured-output walk."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    job: Literal["research", "portfolio"]
    phase: str
    output_model: str | None = None
    skill_slug: str | None = None
    structured_output: StructuredOutputStance
    walk_note: str = ""


# Seed inventory for the Chris walk. Update rows when a node contract changes;
# do not invent replacement brand names in ``walk_note``.
PROMPT_WALK_NODES: tuple[PromptWalkNode, ...] = (
    PromptWalkNode(
        node_id="research/preflight",
        job="research",
        phase="A0",
        output_model=None,
        structured_output="n_a",
        walk_note="Deterministic loads; no LLM.",
    ),
    PromptWalkNode(
        node_id="research/triage",
        job="research",
        phase="A0",
        output_model="TriagePlan",
        structured_output="keep",
        walk_note="skip/edit/full is the cost contract.",
    ),
    PromptWalkNode(
        node_id="research/phase1-sentiment",
        job="research",
        phase="A1",
        output_model="SentimentNewsReport",
        skill_slug="alt-data-sentiment",
        structured_output="reconsider",
        walk_note="SegmentReport-shaped JSON; WP-C already pushed memos toward markdown.",
    ),
    PromptWalkNode(
        node_id="research/phase7-digest",
        job="research",
        phase="A4",
        output_model="DigestSnapshot",
        skill_slug="digest",
        structured_output="reconsider",
        walk_note="Operator wants report prose; keep ids/bias as structured fields.",
    ),
    PromptWalkNode(
        node_id="portfolio/h5-asset-analyst",
        job="portfolio",
        phase="H5",
        output_model="AnalystPayload",
        structured_output="reconsider",
        walk_note="Evidence + forecast must survive; dumpable JSON is not the UX.",
    ),
    PromptWalkNode(
        node_id="portfolio/h6-deliberation",
        job="portfolio",
        phase="H6",
        output_model="DeliberationPmTurn|DeliberationAnalystTurn",
        structured_output="prose_preferred",
        walk_note=(
            "2026-08-06 review: structured summary collapses disagreement "
            "(OLY-REV-004). Prefer conversation transcript + disputed claims."
        ),
    ),
    PromptWalkNode(
        node_id="portfolio/h7-pm-direction",
        job="portfolio",
        phase="H7",
        output_model="PMDirectionMemo",
        structured_output="keep",
        walk_note="Direction + rank + confidence are the H8 contract; no weights.",
    ),
    PromptWalkNode(
        node_id="portfolio/h8-risk-sizing",
        job="portfolio",
        phase="H8",
        output_model=None,
        structured_output="keep",
        walk_note="Deterministic sizer; weights are the contract.",
    ),
    PromptWalkNode(
        node_id="portfolio/h9-commit-run",
        job="portfolio",
        phase="H9",
        output_model=None,
        structured_output="keep",
        walk_note="Booker terminal — ids, weights, orders only.",
    ),
)


class PromptWalkInventory(BaseModel):
    """Versioned inventory returned to digigraph / tests."""

    model_config = ConfigDict(extra="forbid")

    version: int = 1
    issue: str = "3424"
    nodes: list[PromptWalkNode] = Field(default_factory=lambda: list(PROMPT_WALK_NODES))


def prompt_walk_inventory() -> PromptWalkInventory:
    """Return the current walk catalog (copy-safe via model_validate)."""
    return PromptWalkInventory(nodes=list(PROMPT_WALK_NODES))
