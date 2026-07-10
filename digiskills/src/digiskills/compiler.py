"""Orchestrates a corpus builder + synthesizer into a :class:`CompileResult`.

:func:`compile_skill` is the single public entry point most callers need: pick
a builder/synthesizer explicitly, or let it default from ``source.kind``
(:class:`~digiskills.ingest.LocalPathCorpusBuilder` for ``LOCAL_PATH``,
:class:`~digiskills.ingest_url.UrlCorpusBuilder` for ``URLS``) and always
default to :class:`~digiskills.synthesize.TemplateSynthesizer` — no hidden LLM
call happens unless the caller explicitly passes a
:class:`~digiskills.synthesize.DigiLLMSynthesizer`.
"""

from __future__ import annotations

from typing import Protocol

from digiskills.ingest import LocalPathCorpusBuilder
from digiskills.models import CompileResult, Corpus, SkillSource, SourceKind
from digiskills.synthesize import Synthesizer, TemplateSynthesizer


class CorpusBuilder(Protocol):
    """Turns a :class:`SkillSource` into a :class:`Corpus`."""

    def build(self, source: SkillSource) -> Corpus:
        pass


def _default_corpus_builder(source: SkillSource) -> CorpusBuilder:
    if source.kind is SourceKind.LOCAL_PATH:
        return LocalPathCorpusBuilder()
    if source.kind is SourceKind.URLS:
        from digiskills.ingest_url import UrlCorpusBuilder  # requires the `[ingest]` extra

        return UrlCorpusBuilder()
    raise ValueError(f"no default corpus builder for kind={source.kind}")  # pragma: no cover


def compile_skill(
    source: SkillSource,
    *,
    corpus_builder: CorpusBuilder | None = None,
    synthesizer: Synthesizer | None = None,
) -> CompileResult:
    """Compile ``source`` into an installable :class:`~digiskills.models.SkillPackage`.

    Defaults to a zero-configuration, zero-LLM-call pipeline: the corpus
    builder is picked from ``source.kind`` and the synthesizer is
    :class:`~digiskills.synthesize.TemplateSynthesizer`. Pass a
    :class:`~digiskills.synthesize.DigiLLMSynthesizer` explicitly to opt into
    real LLM-drafted prose (requires the ``digiskills[llm]`` extra).
    """
    builder = corpus_builder or _default_corpus_builder(source)
    synth = synthesizer or TemplateSynthesizer()

    corpus = builder.build(source)
    package = synth.synthesize(corpus, source)

    warnings: list[str] = []
    if not corpus.documents:
        warnings.append("no documents were ingested — the compiled skill has no references")
    if corpus.truncated:
        warnings.append("corpus was truncated by a size/count cap; some source content was dropped")

    return CompileResult(
        package=package,
        source=source,
        document_count=len(corpus.documents),
        warnings=warnings,
    )
