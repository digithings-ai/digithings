"""Turns an ingested :class:`~digiskills.models.Corpus` into a :class:`SkillPackage`.

Two synthesizers are provided:

- :class:`TemplateSynthesizer` — the default. Deterministic, no LLM call, no
  extra dependency. Produces an honest but plain SKILL.md (an index over the
  ingested references) — safe to run with zero configuration.
- :class:`DigiLLMSynthesizer` — drafts a real description + usage body via
  ``digillm.completion``. Requires the ``digiskills[llm]`` extra; lazily
  imports ``digillm`` so ``import digiskills.synthesize`` never requires it.

Both build the same ``references/`` files directly from corpus content (never
through the model), so long documents — code, API specs — are carried through
verbatim rather than lossily paraphrased.
"""

from __future__ import annotations

import json
import os
import re
from typing import Protocol

from digiskills.models import (
    Corpus,
    SkillManifest,
    SkillPackage,
    SkillReference,
    SkillSource,
    SourceDocument,
)

_UNSAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9._-]")

_LANGUAGE_BY_CONTENT_TYPE: dict[str, str] = {
    "text/x-python": "python",
    "text/x-typescript": "typescript",
    "text/javascript": "javascript",
    "application/json": "json",
    "application/yaml": "yaml",
    "application/toml": "toml",
}


class Synthesizer(Protocol):
    """Turns a corpus into a :class:`SkillPackage` for the given source."""

    def synthesize(self, corpus: Corpus, source: SkillSource) -> SkillPackage:
        pass


def _safe_reference_filename(origin: str, used: set[str]) -> str:
    """Derive a collision-free, traversal-safe filename under ``references/``."""
    flattened = origin.replace("\\", "/").replace("/", "__").strip("_") or "document"
    sanitized = _UNSAFE_CHARS_RE.sub("_", flattened)
    if not sanitized.endswith(".md"):
        sanitized = f"{sanitized}.md"
    candidate = sanitized
    counter = 2
    while candidate in used:
        candidate = f"{sanitized[:-3]}-{counter}.md"
        counter += 1
    used.add(candidate)
    return candidate


def _wrap_reference_content(doc: SourceDocument) -> str:
    """Render one corpus document as a self-contained reference file."""
    header = f"# {doc.title}\n\nSource: `{doc.origin}`\n\n"
    if doc.content_type in ("text/markdown", "text/plain"):
        return f"{header}{doc.content}\n"
    lang = _LANGUAGE_BY_CONTENT_TYPE.get(doc.content_type, "")
    return f"{header}```{lang}\n{doc.content}\n```\n"


def _build_references(corpus: Corpus, *, max_docs: int = 200) -> list[SkillReference]:
    used: set[str] = set()
    refs: list[SkillReference] = []
    for doc in corpus.documents[:max_docs]:
        filename = _safe_reference_filename(doc.origin, used)
        refs.append(
            SkillReference(
                relative_path=f"references/{filename}", content=_wrap_reference_content(doc)
            )
        )
    return refs


class TemplateSynthesizer:
    """Deterministic, LLM-free synthesizer — the safe zero-configuration default.

    Produces a minimal, honest SKILL.md: a description built from
    ``source.description_hint`` (or a generic placeholder) and a body that
    indexes the ingested references. Callers that want a richer, prose body
    should pass a :class:`DigiLLMSynthesizer` instead.
    """

    def synthesize(self, corpus: Corpus, source: SkillSource) -> SkillPackage:
        references = _build_references(corpus)
        description = source.description_hint or (
            f"Skill compiled from {len(corpus.documents)} document(s) under '{source.name}'. "
            "Auto-generated placeholder description — replace with a concise, specific "
            "trigger description before shipping."
        )
        manifest = SkillManifest(name=source.name, description=description[:1024])
        lines = [
            f"# {source.name}",
            "",
            f"Compiled from {len(corpus.documents)} document(s)"
            + (" (corpus truncated by size caps)." if corpus.truncated else "."),
            "",
            "## Reference index",
            "",
        ]
        if references:
            for ref, doc in zip(references, corpus.documents, strict=False):
                lines.append(f"- `{ref.relative_path}` — {doc.title}")
        else:
            lines.append("_No documents were ingested._")
        body = "\n".join(lines)
        return SkillPackage(manifest=manifest, body=body, references=references)


DEFAULT_SYNTHESIS_MODEL_ENV = "DIGISKILLS_SYNTHESIS_MODEL"
DEFAULT_SYNTHESIS_MODEL = "openrouter/auto"

# Keeps the synthesis prompt bounded regardless of how large the ingested corpus is.
_MAX_PROMPT_CHARS = 60_000

_RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "digiskills_synthesis",
        "schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "One to two sentences: when an agent should reach for this skill.",
                },
                "body": {
                    "type": "string",
                    "description": "Markdown instructions telling an agent how to use this skill.",
                },
            },
            "required": ["description", "body"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}


class DigiLLMSynthesizer:
    """LLM-backed synthesizer using ``digillm.completion`` (requires the ``[llm]`` extra).

    Drafts a natural-language ``description`` (the agent-discovery trigger) and
    ``body`` (usage instructions) from the ingested corpus via a single
    structured-output completion. References are built identically to
    :class:`TemplateSynthesizer` — straight from corpus content, never through
    the model — so long documents are carried through verbatim.
    """

    def __init__(self, *, model: str | None = None, temperature: float = 0.2) -> None:
        self.model = model or os.environ.get(DEFAULT_SYNTHESIS_MODEL_ENV, DEFAULT_SYNTHESIS_MODEL)
        self.temperature = temperature

    def synthesize(self, corpus: Corpus, source: SkillSource) -> SkillPackage:
        import digillm  # lazy: requires the `digiskills[llm]` extra

        references = _build_references(corpus)
        prompt = self._build_prompt(corpus, source)
        messages = [
            {
                "role": "system",
                "content": (
                    "You write Agent Skill files (SKILL.md) in the Anthropic Agent Skills "
                    "format. Given excerpts from a codebase/docs corpus, produce a concise "
                    "'description' (when an agent should use this skill — used for automatic "
                    "discovery, so be concrete and specific, not generic) and a 'body' "
                    "(step-by-step markdown instructions an agent follows to use the "
                    "referenced material). Refer to files under references/ by name where "
                    "relevant; do not invent APIs or files not present in the excerpts."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        response = digillm.completion(
            self.model,
            messages,
            temperature=self.temperature,
            response_format=_RESPONSE_SCHEMA,
        )
        content = response.choices[0].message.content or "{}"
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"synthesis model returned non-JSON content: {content!r}") from exc

        description = (
            str(data.get("description") or "").strip()
            or source.description_hint
            or f"Skill compiled from {len(corpus.documents)} document(s) under '{source.name}'."
        )
        body = str(data.get("body") or "").strip() or f"# {source.name}\n\nNo body was generated."
        manifest = SkillManifest(name=source.name, description=description[:1024])
        return SkillPackage(manifest=manifest, body=body, references=references)

    def _build_prompt(self, corpus: Corpus, source: SkillSource) -> str:
        header = f"Skill name: {source.name}\n"
        if source.description_hint:
            header += f"Author-provided hint: {source.description_hint}\n"
        header += f"Document count: {len(corpus.documents)}\n\n"
        budget = _MAX_PROMPT_CHARS - len(header)
        parts: list[str] = []
        used = 0
        for doc in corpus.documents:
            snippet = f"--- {doc.title} ({doc.origin}) ---\n{doc.content}\n"
            if used + len(snippet) > budget:
                remaining = budget - used
                if remaining > 0:
                    parts.append(snippet[:remaining])
                break
            parts.append(snippet)
            used += len(snippet)
        return header + "\n".join(parts)
