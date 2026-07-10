"""Pydantic v2 model validation tests for digiskills.models."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from digiskills.models import (
    CompileResult,
    Corpus,
    SkillManifest,
    SkillPackage,
    SkillReference,
    SkillSource,
    SourceDocument,
    SourceKind,
)

pytestmark = pytest.mark.unit


def test_local_path_source_requires_local_path() -> None:
    with pytest.raises(ValidationError):
        SkillSource(kind=SourceKind.LOCAL_PATH, name="acme-sdk")


def test_local_path_source_rejects_urls() -> None:
    with pytest.raises(ValidationError):
        SkillSource(
            kind=SourceKind.LOCAL_PATH,
            name="acme-sdk",
            local_path=Path("."),
            urls=["https://example.com"],
        )


def test_urls_source_requires_urls() -> None:
    with pytest.raises(ValidationError):
        SkillSource(kind=SourceKind.URLS, name="acme-sdk")


def test_urls_source_rejects_local_path() -> None:
    with pytest.raises(ValidationError):
        SkillSource(
            kind=SourceKind.URLS,
            name="acme-sdk",
            urls=["https://example.com"],
            local_path=Path("."),
        )


def test_source_name_must_be_slug() -> None:
    with pytest.raises(ValidationError):
        SkillSource(kind=SourceKind.URLS, name="Acme SDK", urls=["https://example.com"])


def test_source_valid() -> None:
    source = SkillSource(kind=SourceKind.URLS, name="acme-sdk", urls=["https://example.com"])
    assert source.name == "acme-sdk"
    assert source.kind is SourceKind.URLS


def test_manifest_name_must_be_slug() -> None:
    with pytest.raises(ValidationError):
        SkillManifest(name="Not A Slug", description="x")


def test_manifest_valid() -> None:
    manifest = SkillManifest(name="acme-sdk", description="How to integrate the Acme SDK")
    assert manifest.name == "acme-sdk"


def test_reference_rejects_traversal() -> None:
    with pytest.raises(ValidationError):
        SkillReference(relative_path="../escape.md", content="x")


def test_reference_rejects_absolute_path() -> None:
    with pytest.raises(ValidationError):
        SkillReference(relative_path="/etc/passwd", content="x")


def test_reference_accepts_nested_path() -> None:
    ref = SkillReference(relative_path="references/nested/doc.md", content="x")
    assert ref.relative_path == "references/nested/doc.md"


def test_corpus_total_chars() -> None:
    corpus = Corpus(
        documents=[
            SourceDocument(origin="a.md", title="a", content="12345"),
            SourceDocument(origin="b.md", title="b", content="12"),
        ]
    )
    assert corpus.total_chars == 7


def test_corpus_default_empty() -> None:
    corpus = Corpus()
    assert corpus.documents == []
    assert corpus.truncated is False
    assert corpus.total_chars == 0


def test_compile_result_document_count_must_be_non_negative() -> None:
    manifest = SkillManifest(name="acme-sdk", description="x")
    package = SkillPackage(manifest=manifest, body="body")
    source = SkillSource(kind=SourceKind.URLS, name="acme-sdk", urls=["https://example.com"])
    with pytest.raises(ValidationError):
        CompileResult(package=package, source=source, document_count=-1)


def test_compile_result_valid() -> None:
    manifest = SkillManifest(name="acme-sdk", description="x")
    package = SkillPackage(manifest=manifest, body="body")
    source = SkillSource(kind=SourceKind.URLS, name="acme-sdk", urls=["https://example.com"])
    result = CompileResult(package=package, source=source, document_count=0)
    assert result.warnings == []
