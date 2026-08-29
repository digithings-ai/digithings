"""Shared research corpus identity + publish-if-missing (Track B / #2613).

Tenant-agnostic keys ``theme:`` / ``asset:`` / ``segment:`` identify shared research
pins. The digithings house run writes defaults; overlays may only
``publish_if_missing`` — they never fork a per-user key namespace or replace the
house run.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal, Mapping
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CORPUS_KEY_KINDS = frozenset({"theme", "asset", "segment"})
_CORPUS_VERSION_NS = uuid5(NAMESPACE_URL, "digithings.olympus.research_corpus")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,198}$")
# Reject tenant / profile markers in slug material (anti-fork).
_TENANT_MARKER_RE = re.compile(
    r"(?:^|[/_.-])(?:user|profile|tenant|overlay)(?:$|[/_.:-])",
    re.IGNORECASE,
)


class ResearchCorpusMissingError(LookupError):
    """Raised when an exact corpus pin cannot be resolved."""


class ResearchCorpusKeyError(ValueError):
    """Raised when a corpus key is malformed or tenant-bearing."""


class CorpusKeyKind(StrEnum):
    THEME = "theme"
    ASSET = "asset"
    SEGMENT = "segment"


class CorpusKey(BaseModel):
    """Tenant-agnostic shared corpus key (kind + slug → ``kind:slug``)."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    kind: CorpusKeyKind
    slug: str = Field(..., min_length=1, max_length=200)

    @field_validator("slug")
    @classmethod
    def _normalize_slug(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not _SLUG_RE.fullmatch(cleaned):
            raise ValueError(
                f"corpus slug must be lowercase alphanumeric with . _ / - (got {value!r})"
            )
        if _TENANT_MARKER_RE.search(cleaned):
            raise ValueError(
                "corpus slug must be tenant-agnostic (no user/profile/tenant/overlay markers)"
            )
        return cleaned

    @property
    def key(self) -> str:
        return f"{self.kind.value}:{self.slug}"

    @classmethod
    def parse(cls, raw: str) -> CorpusKey:
        """Parse ``theme:…`` / ``asset:…`` / ``segment:…``; fail closed otherwise."""
        text = raw.strip()
        if ":" not in text:
            raise ResearchCorpusKeyError(f"corpus key missing kind prefix: {raw!r}")
        kind_raw, _, slug = text.partition(":")
        kind_norm = kind_raw.strip().lower()
        if kind_norm not in CORPUS_KEY_KINDS:
            raise ResearchCorpusKeyError(
                f"corpus key kind must be one of {sorted(CORPUS_KEY_KINDS)}; got {kind_raw!r}"
            )
        try:
            return cls(kind=CorpusKeyKind(kind_norm), slug=slug)
        except ValueError as exc:
            raise ResearchCorpusKeyError(str(exc)) from exc


def corpus_pin_version_id(corpus_key: str, schema_version: int = 1) -> UUID:
    """Deterministic pin id for a logical corpus key + schema version."""
    return uuid5(_CORPUS_VERSION_NS, f"{corpus_key}:v{schema_version}")


WriterRole = Literal["house", "overlay_request"]


class ResearchCorpusPin(BaseModel):
    """Versioned shared corpus pin (payload is research identity, not portfolio)."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    version_id: UUID
    corpus_key: str = Field(..., min_length=3, max_length=220)
    schema_version: int = Field(default=1, ge=1)
    writer_role: WriterRole
    label: str = Field(..., min_length=1, max_length=200)
    summary: str = Field(default="")
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("corpus_key")
    @classmethod
    def _validate_corpus_key(cls, value: str) -> str:
        return CorpusKey.parse(value).key

    @field_validator("payload")
    @classmethod
    def _payload_forbids_tenant(cls, value: dict[str, Any]) -> dict[str, Any]:
        forbidden = {"user_id", "profile_id", "tenant_id", "profile_key"}
        overlap = forbidden.intersection(value)
        if overlap:
            raise ValueError(f"corpus payload must not carry tenant fields: {sorted(overlap)}")
        return value

    @model_validator(mode="after")
    def _version_matches_key(self) -> ResearchCorpusPin:
        expected = corpus_pin_version_id(self.corpus_key, self.schema_version)
        if self.version_id != expected:
            raise ValueError(
                f"version_id {self.version_id} must equal "
                f"corpus_pin_version_id({self.corpus_key!r}, {self.schema_version})"
            )
        return self


def house_corpus_pin(
    corpus_key: str,
    *,
    label: str,
    summary: str = "",
    payload: Mapping[str, Any] | None = None,
    schema_version: int = 1,
) -> ResearchCorpusPin:
    """Build a house-authored pin for a tenant-agnostic corpus key."""
    key = CorpusKey.parse(corpus_key).key
    return ResearchCorpusPin(
        version_id=corpus_pin_version_id(key, schema_version),
        corpus_key=key,
        schema_version=schema_version,
        writer_role="house",
        label=label,
        summary=summary,
        payload=dict(payload or {}),
    )


class ResearchCorpusStore:
    """In-memory shared corpus store (mirrors DB exact-id + publish-if-missing)."""

    def __init__(self) -> None:
        self._by_version: dict[str, ResearchCorpusPin] = {}
        self._by_key: dict[str, str] = {}  # corpus_key -> version_id str

    def load_by_version_id(self, version_id: UUID) -> ResearchCorpusPin:
        key = str(version_id)
        if key not in self._by_version:
            raise ResearchCorpusMissingError(f"research_corpus pin {version_id} not found")
        return self._by_version[key]

    def get_by_key(self, corpus_key: str) -> ResearchCorpusPin | None:
        key = CorpusKey.parse(corpus_key).key
        vid = self._by_key.get(key)
        if vid is None:
            return None
        return self._by_version[vid]

    def publish_if_missing(
        self,
        pin: ResearchCorpusPin,
        *,
        allow_overlay: bool = False,
    ) -> ResearchCorpusPin:
        """Insert when key absent; return existing pin when present (idempotent).

        House writers may always publish. Overlay requests require
        ``allow_overlay=True`` and ``writer_role='overlay_request'``.
        """
        if pin.writer_role == "overlay_request" and not allow_overlay:
            raise ResearchCorpusKeyError("overlay publish_if_missing requires allow_overlay=True")
        if pin.writer_role == "house" and allow_overlay:
            # Defensive: house writes should not be marked as overlay path.
            raise ResearchCorpusKeyError("house corpus pins must not use allow_overlay=True")

        existing = self.get_by_key(pin.corpus_key)
        if existing is not None:
            return existing

        vid = str(pin.version_id)
        self._by_version[vid] = pin
        self._by_key[pin.corpus_key] = vid
        return pin
