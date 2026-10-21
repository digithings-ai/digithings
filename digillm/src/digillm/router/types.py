"""Request and decision models for digillm's router.

The router picks one model from a deployment's allowlist. It does not call a
provider. Decisions are Pydantic models so a caller cannot smuggle a bare dict
into the chat path.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RouterRoute(BaseModel):
    """One named category and, optionally, the model an operator pinned to it."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,32}$")
    label: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=240)
    model: str | None = Field(default=None, min_length=1, max_length=120)
    exemplars: list[str] = Field(default_factory=list, max_length=12)

    def exemplar_texts(self) -> list[str]:
        texts = [self.description, *self.exemplars]
        return [text.strip() for text in texts if text.strip()]


class RouterRequest(BaseModel):
    """What a non-Python consumer sends on stdin. ``routes`` omitted means the
    built-in Reasoning / Fast / Light policy."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(default="", max_length=8000)
    allowed: list[str] = Field(default_factory=list, max_length=64)
    fallback: str = Field(min_length=1, max_length=120)
    routes: list[RouterRoute] | None = None


class RouterDecision(BaseModel):
    """The model to call, and a short reason safe to show in the chat UI.

    ``reason`` describes the category. It never quotes the question.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    route_id: str
    label: str
    model: str
    reason: str = Field(min_length=1, max_length=240)
    confidence: float = Field(ge=0.0, le=1.0)


class RouterError(ValueError):
    """The request cannot be routed. Callers fail closed; they do not guess."""
