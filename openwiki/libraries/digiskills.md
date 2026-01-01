---
type: library-guide
title: digiskills Library
description: digiskills agent-skill compiler — corpus builders, synthesizers, packaging, and remote-ingest security.
tags: [digiskills, agent-skills, compiler, library]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-09T14:37:17.158Z
sources:
  - id: openwiki-source-cbdb08219f90905f9b1f840d
    resource: repo://digiskills/ARCHITECTURE.md
  - id: openwiki-source-a268f7fc8520af12a968a39c
    resource: repo://digiskills/src/digiskills/compiler.py
  - id: openwiki-source-c07c9827dd93623091863cf0
    resource: repo://digiskills/src/digiskills/security.py
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digiskills Library

digiskills compiles a source — a local codebase/docs path or remote
docs/OpenAPI URLs — into a standard installable Agent Skill package
(`SKILL.md` + `references/`, the Anthropic format): a plain directory or
zip with no server, registry, or runtime dependency. Status: compiler
core (P1) + dogfood (P2) shipped; hosted platform (P4) deferred.

## Pipeline

`compile_skill(source, ...)` orchestrates a `CorpusBuilder` plus a
`Synthesizer` into a `CompileResult`, then `write_skill_package` /
`write_skill_zip` materialize it. Builders: `LocalPathCorpusBuilder`
(ignore-list + size caps, zero extra deps) and `UrlCorpusBuilder` (via
`digifetch.HttpFetcher`, lazily imported, `[ingest]` extra).
Synthesizers: `TemplateSynthesizer` (default — deterministic, **no LLM
call**) with explicit opt-in `DigiLLMSynthesizer` (via `digillm`,
`[llm]` extra) for real prose. No pipeline silently reaches a model.

## Models and packaging

Pydantic results throughout (`SkillSource`, `Corpus`, `SkillPackage`,
`CompileResult`, …). `SKILL.md` frontmatter carries `name` + `description`
only. Writes sandbox to the package root — `SkillReference` rejects
traversal at construction with a defense-in-depth recheck at write time.

## Security hardening

Remote ingestion applies `digiskills.security` (stdlib-only) to every
fetch: `is_allowed_scrape_url` SSRF allowlist, `redact_secrets`, and
`scan_for_prompt_injection` flagging untrusted content — shipped before
any real external source ran through the pipeline.

Core deps are `pydantic` + `pyyaml` only; `import digiskills` never pulls
FastAPI, `digifetch`, `digillm`, or typer.
