# DigiSkills – Agent guide

## Purpose

DigiSkills compiles a source (a local codebase/docs path, or remote docs/
OpenAPI URLs) into a standard, installable Agent Skill package (`SKILL.md` +
`references/`). A pure-Python core library plus optional `cli`/`ingest`/`llm`
extras — no FastAPI service yet.

## Read first

1. `digiskills/ARCHITECTURE.md` — module map, public API, design decisions.
2. Root `AGENTS.md` and `CLAUDE.md` — stack-wide non-negotiables.
3. [ADR-0023](../docs/adr/0023-digiskills-agent-skill-compiler.md) — why this
   module exists, what's explicitly deferred (external ingestion, hosted
   platform, live MCP distribution).
4. `digivault/AGENTS.md` — the library-conventions reference this mirrors.

## Pre-flight checklist

- [ ] `import digiskills` stays dependency-light (core depends only on
      `pydantic` + `pyyaml`) — no `digifetch`, `digillm`, `typer`, or `fastapi`
      at module import time anywhere in `models.py`, `frontmatter.py`,
      `ingest.py`, `compiler.py`, `package.py`, or `__init__.py`.
- [ ] New result data is a Pydantic v2 model in `models.py`, not a bare dict.
- [ ] Any new write path in `package.py` stays sandboxed to the package root
      (resolve the destination path and check it under the package dir before
      writing — see the existing traversal guard).
- [ ] `TemplateSynthesizer` stays the default everywhere (`compiler.py`,
      `cli.py`). Never make `DigiLLMSynthesizer` (or any network/LLM call) the
      implicit default — callers opt in explicitly.
- [ ] Both synthesizers keep building `references/` straight from
      `Corpus.documents` — never let a model paraphrase reference *content*
      (only the manifest description / body prose is model-drafted).
- [ ] `render_skill_md(parse_skill_md(text)) `round-trips: `SkillManifest`
      fields survive; don't add frontmatter fields beyond `name`/`description`
      without checking the Anthropic Agent Skills format actually supports
      them.

## Non-negotiable rules

- Do **not** hard-import `digifetch` or `digillm` at module scope anywhere
  outside their own dedicated modules (`ingest_url.py`, `synthesize.py`) —
  and even there, only inside method bodies (lazy import), matching the
  `[ingest]`/`[llm]` extras being optional.
- `SkillSource.name` / `SkillManifest.name` must stay a lowercase-hyphenated
  slug (`_SLUG_RE` in `models.py`) — it becomes both the frontmatter `name`
  and the on-disk package directory name.
- A single URL fetch failure in `UrlCorpusBuilder` must not abort the whole
  build (skip + mark `truncated`, matching `digillm.web_search`'s fail-soft
  convention) — don't change this to fail-fast.
- Do not add a FastAPI service, MCP server, or hosted registry without first
  updating ADR-0023 (or filing a new ADR) — those are explicitly deferred
  phases (P4), a novel-architecture decision requiring human sign-off per
  `AGENT_WORKFLOW.md` §1.5.
- Do not run the compiler against a real third party's docs/API/codebase
  (P3 in ADR-0023) without a security review first — new trust boundary
  (external content, possibly credentials in scraped docs).

## Anti-patterns

- ❌ Importing `digifetch`/`digillm`/`typer` from `digiskills/__init__.py`,
  `models.py`, `frontmatter.py`, `ingest.py`, `compiler.py`, or `package.py`.
- ❌ Returning dicts from any public function (use the `models.py` types).
- ❌ Making `compile_skill` call `DigiLLMSynthesizer` by default — it must
  stay an explicit, opt-in choice.
- ❌ Writing a reference file without going through `SkillReference`'s
  traversal validation (or `package.py`'s defense-in-depth re-check).
- ❌ Adding a live network call to a unit test (`tests/dsk/`) — mock
  `digillm.completion` / inject an `httpx.MockTransport`-backed
  `HttpFetcher`, as the existing tests do.

## Test commands

```bash
# Core only (pydantic + pyyaml):
pip install -e ./digiskills
pytest tests/dsk -m unit

# Full (cli + ingest + llm extras):
pip install -e ./digiskills[dev] -e ./digifetch -e ./digillm
pytest tests/dsk -m unit
ruff check digiskills/src tests/dsk && ruff format --check digiskills/src tests/dsk

# Import-cost guard (must not pull digifetch/digillm/typer):
python -c "import sys, digiskills; assert not ({'digifetch','digillm','typer'} & set(sys.modules))"

# CLI smoke test:
digiskills compile ./some-repo --name acme-sdk --description "How to use it" --out ./out
```
