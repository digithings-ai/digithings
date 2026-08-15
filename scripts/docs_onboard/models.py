"""Pydantic models for the docs_onboard offline pipeline."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PageClass(str, Enum):
    docs = "docs"
    pdf = "pdf"
    asset = "asset"
    skip = "skip"
    openapi = "openapi"
    repo_doc = "repo_doc"


class RepoSource(BaseModel):
    """Monorepo or GitHub documentation source (Stage 3b)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["local", "github"] = "local"
    path: str | None = None  # local monorepo root (relative or absolute)
    globs_file: str | None = None  # YAML with ``globs:`` list
    globs: tuple[str, ...] = ()
    github_repo: str | None = None  # owner/name
    ref: str = "HEAD"

    @model_validator(mode="after")
    def _require_locator(self) -> RepoSource:
        if self.kind == "local" and not (self.path or "").strip():
            raise ValueError("repo_source.kind=local requires path")
        if self.kind == "github" and not (self.github_repo or "").strip():
            raise ValueError("repo_source.kind=github requires github_repo")
        return self


class OnboardManifest(BaseModel):
    """Per-client crawl + sink configuration (from ``onboard.yaml``)."""

    model_config = ConfigDict(extra="forbid")

    client: str
    seed_url: str
    allowed_hosts: tuple[str, ...] = ()
    max_pages: int = Field(default=100, ge=1, le=5000)
    max_depth: int = Field(default=3, ge=0, le=20)
    sinks: tuple[str, ...] = ("vault",)  # vault | search
    digisearch_index: str = "default"
    vault_subdir: str = "corpus"
    docs_path_prefixes: tuple[str, ...] = ()
    skip_path_prefixes: tuple[str, ...] = ()
    # Extensions (optional paths relative to repo root unless absolute)
    static_sources: str | None = None
    openapi_sources: str | None = None
    repo_source: RepoSource | None = None
    vault_url: str | None = None  # digivault HTTP base (POST /v1/notes)


def load_manifest(path: Path) -> OnboardManifest:
    """Load and validate an onboard YAML manifest."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Manifest must be a mapping: {path}")
    return OnboardManifest.model_validate(data)


class StaticSourcesConfig(BaseModel):
    """YAML list of globs for static file ingest."""

    model_config = ConfigDict(extra="ignore")

    globs: tuple[str, ...] = ()
    description: str = ""


class OpenApiSourcesConfig(BaseModel):
    """YAML list of OpenAPI/Swagger files."""

    model_config = ConfigDict(extra="ignore")

    files: tuple[str, ...] = ()
    kinds: tuple[str, ...] = ("openapi", "swagger")
    vault_note_type: str = "api_reference"


def load_static_sources(path: Path) -> StaticSourcesConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"static_sources must be a mapping: {path}")
    return StaticSourcesConfig.model_validate(data)


def load_openapi_sources(path: Path) -> OpenApiSourcesConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"openapi_sources must be a mapping: {path}")
    return OpenApiSourcesConfig.model_validate(data)


class DiscoveredPage(BaseModel):
    """A URL discovered during the crawl (HTML or linked asset)."""

    model_config = ConfigDict(extra="forbid")

    url: str
    final_url: str
    content_type: str = ""
    title: str = ""
    depth: int = 0
    link_text: str = ""
    discovered_from: str | None = None
    html_path: str | None = None  # relative to workspace root when HTML was saved
    local_path: str | None = None  # workspace-relative path for static/repo/openapi files


class ClassifiedPage(BaseModel):
    """A discovered page with docs-priority classification."""

    model_config = ConfigDict(extra="forbid")

    page: DiscoveredPage
    page_class: PageClass
    score: float = 0.0
    reasons: tuple[str, ...] = ()


class SourceMapEntry(BaseModel):
    """Maps a local workdir file back to its origin URL."""

    model_config = ConfigDict(extra="forbid")

    local_path: str
    source_url: str
    content_type: str = ""


class OnboardResult(BaseModel):
    """Summary of a full ``run_onboard`` execution."""

    model_config = ConfigDict(extra="forbid")

    pages_seen: int = 0
    docs_kept: int = 0
    skipped: int = 0
    vault_notes: int = 0
    search_docs: int = 0
    static_files: int = 0
    openapi_files: int = 0
    repo_files: int = 0
    dry_run: bool = False
    errors: tuple[str, ...] = ()
