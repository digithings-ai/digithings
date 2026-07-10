"""DigiSkills — compiles a codebase/docs source into an installable Agent Skill.

Pipeline: :class:`SkillSource` (what to compile) -> a *corpus builder*
(:class:`~digiskills.ingest.LocalPathCorpusBuilder` for a local path,
:class:`~digiskills.ingest_url.UrlCorpusBuilder` for remote docs/OpenAPI
URLs) -> a *synthesizer* (:class:`TemplateSynthesizer` by default, or
:class:`DigiLLMSynthesizer` for LLM-drafted prose) -> :class:`SkillPackage`
-> :func:`~digiskills.package.write_skill_package` writes it to disk in the
Anthropic Agent Skills format (``SKILL.md`` + ``references/``), installable
into any coding agent's skills directory exactly like a hand-authored skill.

The core library (this module, ``models``, ``frontmatter``, ``ingest``,
``synthesize``, ``compiler``, ``package``) depends only on ``pydantic`` and
``pyyaml`` — no FastAPI, no digifetch, no digillm. Remote-URL ingestion
(``ingest_url``) and LLM synthesis (``DigiLLMSynthesizer``) lazily import
``digifetch`` / ``digillm`` respectively, gated behind the ``[ingest]`` /
``[llm]`` extras.

See ``digiskills/ARCHITECTURE.md`` and ADR-0023
(``docs/adr/0023-digiskills-agent-skill-compiler.md``) for the full design.
"""

from __future__ import annotations

from digiskills.compiler import CorpusBuilder, compile_skill
from digiskills.frontmatter import parse_skill_md, render_skill_md
from digiskills.ingest import LocalPathCorpusBuilder
from digiskills.ingest_url import UrlCorpusBuilder
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
from digiskills.package import write_skill_package
from digiskills.synthesize import DigiLLMSynthesizer, Synthesizer, TemplateSynthesizer

__version__ = "0.1.0"  # x-release-please-version

__all__ = [
    "CompileResult",
    "Corpus",
    "CorpusBuilder",
    "DigiLLMSynthesizer",
    "LocalPathCorpusBuilder",
    "SkillManifest",
    "SkillPackage",
    "SkillReference",
    "SkillSource",
    "SourceDocument",
    "SourceKind",
    "Synthesizer",
    "TemplateSynthesizer",
    "UrlCorpusBuilder",
    "__version__",
    "compile_skill",
    "parse_skill_md",
    "render_skill_md",
    "write_skill_package",
]
