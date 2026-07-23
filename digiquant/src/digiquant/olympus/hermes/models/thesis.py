"""Pydantic contracts for thesis-track Hermes phases (H1–H4)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, constr, model_validator

ThesisStatus = Literal[
    "ACTIVE", "MONITORING", "CHALLENGED", "CLOSED", "INVALIDATED", "PAUSED", "NEW"
]


class ThesisStatusUpdate(BaseModel):
    thesis_id: str
    prior_status: ThesisStatus | None = None
    new_status: ThesisStatus
    evidence: list[str] = Field(default_factory=list)
    challenged_by: list[str] | None = None
    resolution: Literal["win", "loss"] | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _closed_requires_resolution(self) -> "ThesisStatusUpdate":
        if self.new_status == "CLOSED":
            if not self.evidence:
                raise ValueError("CLOSED requires evidence")
            if self.resolution not in ("win", "loss"):
                raise ValueError("CLOSED requires resolution win|loss")
        if self.new_status == "INVALIDATED" and not self.reason:
            raise ValueError("INVALIDATED requires reason")
        return self


class ThesisReviewOutput(BaseModel):
    reviewed_theses: list[ThesisStatusUpdate] = Field(default_factory=list)
    new_candidate_theses: list[str] = Field(default_factory=list)
    notes: str = ""


class ThesisProposal(BaseModel):
    thesis_id: constr(max_length=32)  # type: ignore[valid-type]
    topic_key: constr(  # type: ignore[valid-type]
        max_length=64,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    action: Literal["create", "update"]
    existing_thesis_id: constr(max_length=32) | None = None  # type: ignore[valid-type]
    title: constr(max_length=200)  # type: ignore[valid-type]
    direction: str
    statement: constr(max_length=4000)  # type: ignore[valid-type]
    validation_criteria: list[str] = Field(min_length=1)
    invalidation_criteria: list[str] = Field(min_length=1)
    headwinds: list[str] = Field(default_factory=list)
    tailwinds: list[str] = Field(default_factory=list)
    bull_case: list[str] | None = None
    bear_case: list[str] | None = None
    horizon: Literal["short_term", "long_term"] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_identity_action(self) -> "ThesisProposal":
        if self.action == "update" and self.existing_thesis_id != self.thesis_id:
            raise ValueError("action=update requires matching existing_thesis_id and thesis_id")
        if self.action == "create" and self.existing_thesis_id is not None:
            raise ValueError("action=create cannot set existing_thesis_id")
        return self


class MarketThesisExplorationBody(BaseModel):
    executive_digest_pointer: str = ""
    deeper_dives: list[str] = Field(default_factory=list)
    theses: list[ThesisProposal] = Field(default_factory=list)


class MarketThesisExplorationOutput(BaseModel):
    executive_digest_pointer: str = ""
    deeper_dives: list[str] = Field(default_factory=list)
    theses: list[ThesisProposal] = Field(default_factory=list)


class ThesisVehicleMapping(BaseModel):
    thesis_id: str
    candidate_tickers: list[constr(max_length=12)] = Field(min_length=1)  # type: ignore[valid-type]
    rationale: str = ""
    exclusion_reasons: list[str] = Field(default_factory=list)
    user_mandate_notes: list[str] = Field(default_factory=list)


class ThesisVehicleMapOutput(BaseModel):
    mappings: list[ThesisVehicleMapping] = Field(default_factory=list)


class RosterPick(BaseModel):
    ticker: str
    rank: int = Field(ge=1)
    score: float = Field(ge=0.0, le=1.0, default=0.5)
    source_thesis_ids: list[str] = Field(default_factory=list)
    rationale: str = ""


class OpportunityScreenOutput(BaseModel):
    roster: list[RosterPick] = Field(default_factory=list)
    excluded: list[dict[str, str]] = Field(default_factory=list)
    notes: str = ""
