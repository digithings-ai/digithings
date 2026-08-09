"""Pydantic models for the docs_onboard offline pipeline."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class PageClass(str, Enum):
    docs = "docs"
    pdf = "pdf"
    asset = "asset"
    skip = "skip"


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


def load_manifest(path: Path) -> OnboardManifest:
    """Load and validate an onboard YAML manifest."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Manifest must be a mapping: {path}")
    return OnboardManifest.model_validate(data)


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
    errors: tuple[str, ...] = ()
