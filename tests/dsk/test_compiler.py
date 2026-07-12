"""compile_skill orchestration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from digiskills.compiler import _default_corpus_builder, compile_skill
from digiskills.ingest import LocalPathCorpusBuilder
from digiskills.models import Corpus, SkillSource, SourceDocument, SourceKind
from digiskills.synthesize import TemplateSynthesizer

pytestmark = pytest.mark.unit


def test_compile_local_path_end_to_end(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Acme\n\nUse get_widget().\n")

    source = SkillSource(kind=SourceKind.LOCAL_PATH, name="acme-sdk", local_path=tmp_path)
    result = compile_skill(source)

    assert result.document_count == 1
    assert result.package.manifest.name == "acme-sdk"
    assert result.warnings == []


def test_compile_empty_directory_warns(tmp_path: Path) -> None:
    source = SkillSource(kind=SourceKind.LOCAL_PATH, name="acme-sdk", local_path=tmp_path)
    result = compile_skill(source)

    assert result.document_count == 0
    assert any("no documents" in w for w in result.warnings)


def test_compile_truncation_warns(tmp_path: Path) -> None:
    for i in range(3):
        (tmp_path / f"doc{i}.md").write_text(f"content {i}\n")

    source = SkillSource(kind=SourceKind.LOCAL_PATH, name="acme-sdk", local_path=tmp_path)
    result = compile_skill(source, corpus_builder=LocalPathCorpusBuilder(max_files=1))

    assert result.document_count == 1
    assert any("truncated" in w for w in result.warnings)


def test_explicit_synthesizer_and_hint_used(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("a\n")
    source = SkillSource(
        kind=SourceKind.LOCAL_PATH,
        name="acme-sdk",
        local_path=tmp_path,
        description_hint="custom hint",
    )
    result = compile_skill(source, synthesizer=TemplateSynthesizer())
    assert result.package.manifest.description == "custom hint"


def test_default_builder_for_local_path(tmp_path: Path) -> None:
    source = SkillSource(kind=SourceKind.LOCAL_PATH, name="acme-sdk", local_path=tmp_path)
    builder = _default_corpus_builder(source)
    assert isinstance(builder, LocalPathCorpusBuilder)


def test_default_builder_for_urls() -> None:
    pytest.importorskip("digifetch")
    from digiskills.ingest_url import UrlCorpusBuilder

    source = SkillSource(kind=SourceKind.URLS, name="acme-sdk", urls=["https://example.com"])
    builder = _default_corpus_builder(source)
    assert isinstance(builder, UrlCorpusBuilder)


class _FixedCorpusBuilder:
    """Test double: hands compile_skill a pre-built Corpus, bypassing ingestion."""

    def __init__(self, corpus: Corpus) -> None:
        self._corpus = corpus

    def build(self, source: SkillSource) -> Corpus:
        return self._corpus


def _urls_source() -> SkillSource:
    return SkillSource(kind=SourceKind.URLS, name="acme-sdk", urls=["https://example.com"])


def test_untrusted_document_warns() -> None:
    corpus = Corpus(documents=[SourceDocument(origin="u", title="u", content="x", trusted=False)])
    result = compile_skill(_urls_source(), corpus_builder=_FixedCorpusBuilder(corpus))
    assert any("untrusted" in w for w in result.warnings)


def test_trusted_only_corpus_does_not_warn_untrusted() -> None:
    corpus = Corpus(documents=[SourceDocument(origin="a.md", title="a", content="x")])
    result = compile_skill(_urls_source(), corpus_builder=_FixedCorpusBuilder(corpus))
    assert not any("untrusted" in w for w in result.warnings)


def test_redacted_count_warns() -> None:
    corpus = Corpus(
        documents=[SourceDocument(origin="u", title="u", content="x", trusted=False)],
        redacted_count=2,
    )
    result = compile_skill(_urls_source(), corpus_builder=_FixedCorpusBuilder(corpus))
    assert any("2 likely secret" in w for w in result.warnings)


def test_injection_flags_warn() -> None:
    corpus = Corpus(
        documents=[SourceDocument(origin="u", title="u", content="x", trusted=False)],
        injection_flags=["u: ignore-instructions: 'ignore previous instructions'"],
    )
    result = compile_skill(_urls_source(), corpus_builder=_FixedCorpusBuilder(corpus))
    assert any("prompt-injection" in w for w in result.warnings)
