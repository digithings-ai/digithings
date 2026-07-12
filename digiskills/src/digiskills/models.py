"""Pydantic v2 data models for the digiskills compiler pipeline.

Pipeline shape: :class:`SkillSource` (what to compile) -> :class:`Corpus`
(ingested documents) -> :class:`SkillPackage` (a synthesized, installable
Agent Skill) -> :class:`CompileResult` (package + provenance for the caller).
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class SourceKind(str, Enum):
    """Where a :class:`SkillSource` pulls its content from."""

    LOCAL_PATH = "local_path"
    URLS = "urls"


class SkillSource(BaseModel):
    """Describes what to compile a skill from.

    Exactly one of ``local_path`` (for ``LOCAL_PATH``) or ``urls`` (for
    ``URLS``) must be populated, matching ``kind``.
    """

    kind: SourceKind
    name: str = Field(min_length=1, max_length=64)
    description_hint: str | None = Field(default=None, max_length=1024)
    local_path: Path | None = None
    urls: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def _check_kind_matches_payload(self) -> "SkillSource":
        if not _SLUG_RE.match(self.name):
            raise ValueError(
                f"name {self.name!r} must be a lowercase hyphenated slug (e.g. 'acme-api')"
            )
        if self.kind is SourceKind.LOCAL_PATH:
            if self.local_path is None:
                raise ValueError("local_path is required when kind is LOCAL_PATH")
            if self.urls:
                raise ValueError("urls must be empty when kind is LOCAL_PATH")
        elif self.kind is SourceKind.URLS:
            if not self.urls:
                raise ValueError("urls is required when kind is URLS")
            if self.local_path is not None:
                raise ValueError("local_path must be unset when kind is URLS")
        return self


class SourceDocument(BaseModel):
    """A single ingested unit of content — one file or one fetched URL.

    ``trusted`` is True for content the caller controls directly (local
    files) and False for content pulled from a third party at ingestion
    time (e.g. :class:`~digiskills.ingest_url.UrlCorpusBuilder` fetches) —
    surfaced to the compiled package as an untrusted-content banner and to
    the caller as a :class:`CompileResult` warning.
    """

    origin: str = Field(min_length=1)
    title: str = Field(min_length=1)
    content: str
    content_type: str = "text/plain"
    trusted: bool = True


class Corpus(BaseModel):
    """The ingested documents for one compile run."""

    documents: list[SourceDocument] = Field(default_factory=list)
    # True when a size/count cap cut the corpus short — surfaced as a compile warning.
    truncated: bool = False
    # Count of likely-secret substrings redacted from ingested content (see
    # digiskills.security.redact_secrets) — surfaced as a compile warning.
    redacted_count: int = 0
    # Heuristic prompt-injection flags from ingested content (see
    # digiskills.security.scan_for_prompt_injection) — surfaced as a compile warning.
    injection_flags: list[str] = Field(default_factory=list)

    @property
    def total_chars(self) -> int:
        return sum(len(d.content) for d in self.documents)


class SkillManifest(BaseModel):
    """The SKILL.md YAML frontmatter — name + description drive agent discovery."""

    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=1024)

    @model_validator(mode="after")
    def _check_name_slug(self) -> "SkillManifest":
        if not _SLUG_RE.match(self.name):
            raise ValueError(
                f"name {self.name!r} must be a lowercase hyphenated slug (e.g. 'acme-api')"
            )
        return self


class SkillReference(BaseModel):
    """A supporting file bundled into the package (e.g. ``references/auth.md``)."""

    relative_path: str = Field(min_length=1)
    content: str

    @model_validator(mode="after")
    def _check_no_traversal(self) -> "SkillReference":
        p = Path(self.relative_path)
        if p.is_absolute() or ".." in p.parts:
            raise ValueError(
                f"relative_path {self.relative_path!r} must not escape the package root"
            )
        return self


class SkillPackage(BaseModel):
    """A fully synthesized, installable Agent Skill (SKILL.md + references)."""

    manifest: SkillManifest
    body: str = Field(min_length=1)
    references: list[SkillReference] = Field(default_factory=list)


class CompileResult(BaseModel):
    """The output of :func:`digiskills.compiler.compile_skill`."""

    package: SkillPackage
    source: SkillSource
    document_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
