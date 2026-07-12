# DigiSkills – Architecture

`digiskills` compiles a source — a local codebase/docs path, or a list of
remote docs/OpenAPI URLs — into a standard, installable **Agent Skill**
package (`SKILL.md` + `references/`, the Anthropic Agent Skills format). The
compiled package is a plain directory or zip: no server, no registry, no new
runtime dependency for whoever installs it. Copy `<name>/` into any coding
agent's skills directory (e.g. a project's `.claude/skills/`) and it works
like any hand-authored skill.

Design decision record: [ADR-0023](../docs/adr/0023-digiskills-agent-skill-compiler.md).
Phase plan (P0 ADR → P1 compiler core → P2 dogfood → P3 external pilot → P4
hosted platform, explicitly deferred): tracking epic
[#1453](https://github.com/digithings-ai/digithings/issues/1453).

**Status:** P1 (skill compiler core) + P2 (dogfood) shipped. P3 pre-flight
hardening (SSRF, memory cap, secret redaction, untrusted-content flagging on
the remote-ingestion path) shipped ahead of any real external source being
run through the pipeline — see "Security hardening" below. No FastAPI
service, no MCP server, no hosted registry — those are unscoped follow-up
phases, not this module's job today.

---

## Non-negotiables

- Python 3.12, Pydantic v2, full type hints, ruff line-length 100.
- Core hard deps: `pydantic>=2`, `pyyaml>=6` only. `import digiskills` never
  imports FastAPI, `digifetch`, `digillm`, or `typer`.
- Result types are Pydantic models (`SkillSource`, `Corpus`, `SkillPackage`,
  `CompileResult`, …), never bare dicts.
- Every write path (`package.py`) is sandboxed to the package root —
  `SkillReference` rejects path traversal at construction time, and the
  writer re-checks the resolved path as defense in depth.
- `TemplateSynthesizer` (no LLM call) is the default synthesizer everywhere.
  A caller must explicitly pass `DigiLLMSynthesizer` to make a network/LLM
  call — no pipeline silently reaches out to a model.

## Module map

| Module | Responsibility |
|--------|----------------|
| `digiskills/models.py` | Pydantic v2 models: `SkillSource`, `SourceDocument`, `Corpus`, `SkillManifest`, `SkillReference`, `SkillPackage`, `CompileResult`. |
| `digiskills/frontmatter.py` | `render_skill_md` / `parse_skill_md` — the `SKILL.md` YAML-frontmatter format (`name` + `description` only). |
| `digiskills/ingest.py` | `LocalPathCorpusBuilder` — walks a local directory (ignore-list + size caps), zero extra dependencies. |
| `digiskills/ingest_url.py` | `UrlCorpusBuilder` — fetches docs/OpenAPI URLs via `digifetch.HttpFetcher`. Lazily imports `digifetch`; requires the `[ingest]` extra. Applies `digiskills.security` (SSRF allowlist, redaction, injection scan) to every fetch. |
| `digiskills/security.py` | Stdlib-only (no deps, no extra required): `is_allowed_scrape_url` (SSRF allowlist, mirrors digisearch REM-064), `redact_secrets`, `scan_for_prompt_injection`. Used by `ingest_url.py`. |
| `digiskills/synthesize.py` | `Synthesizer` protocol; `TemplateSynthesizer` (default, deterministic, no LLM) and `DigiLLMSynthesizer` (real prose via `digillm.completion`, lazily imported, requires `[llm]`). |
| `digiskills/compiler.py` | `compile_skill(source, ...)` — orchestrates a `CorpusBuilder` + `Synthesizer` into a `CompileResult`. Picks sane defaults from `source.kind` when not given explicitly. |
| `digiskills/package.py` | `write_skill_package` / `write_skill_zip` — writes a `SkillPackage` to disk as an installable directory or zip archive. |
| `digiskills/cli.py` | `digiskills compile <path> --name ... [--llm] [--zip] [--max-files N] [--max-file-chars N] [--max-total-chars N]` — Typer CLI, requires the `[cli]` extra. The `--max-*` flags override `LocalPathCorpusBuilder`'s caps (needed for large OpenAPI specs — a 484KB `public.json` exceeds the 200k-char per-file default and would ship truncated). |

## Public API (core)

```python
from digiskills import (
    SkillSource, SourceKind,          # what to compile
    compile_skill,                    # -> CompileResult
    write_skill_package, write_skill_zip,
    TemplateSynthesizer, DigiLLMSynthesizer,
    LocalPathCorpusBuilder, UrlCorpusBuilder,
)

source = SkillSource(
    kind=SourceKind.LOCAL_PATH,
    name="acme-sdk",                  # lowercase-hyphenated slug
    description_hint="How to integrate the Acme SDK",
    local_path=Path("./acme-sdk-repo"),
)
result = compile_skill(source)        # TemplateSynthesizer by default — no LLM call
write_skill_package(result.package, Path("./out"))
# ./out/acme-sdk/SKILL.md + ./out/acme-sdk/references/*
```

Pipeline shape: `SkillSource` → (`CorpusBuilder`) → `Corpus` → (`Synthesizer`)
→ `SkillPackage` → (`write_skill_package`/`write_skill_zip`) → installable
directory/zip. `compile_skill` wraps the middle two steps and reports
`warnings` (empty corpus, size-cap truncation) plus `document_count` via
`CompileResult`.

### Synthesizers

- **`TemplateSynthesizer`** (default): no LLM call. `description` comes from
  `source.description_hint`, or a generic placeholder naming the document
  count. `body` is a plain reference index. Every corpus document becomes one
  `references/<safe-name>.md` file — the *content* always comes straight from
  the corpus, never through a model, in both synthesizers, so long documents
  (code, API specs) are carried through verbatim rather than lossily
  paraphrased.
- **`DigiLLMSynthesizer`** (opt-in, requires `digiskills[llm]`): one structured
  completion via `digillm.completion` (`response_format` json_schema) drafts a
  concrete `description` (the agent-discovery trigger) and a `body`
  (step-by-step usage instructions) from a size-bounded excerpt of the corpus
  (`_MAX_PROMPT_CHARS`, currently 60k chars). Model defaults to
  `DIGISKILLS_SYNTHESIS_MODEL` env or `openrouter/auto`; pass `model=` to
  override per call.

### Corpus builders

- **`LocalPathCorpusBuilder`** (default for `SourceKind.LOCAL_PATH`): walks a
  directory (or reads a single file), skipping common noise directories
  (`.git`, `node_modules`, `.venv`, `__pycache__`, build/cache dirs) and
  non-text extensions. Bounded by `max_files` (500), `max_total_chars` (2M),
  `max_file_chars` (200k) — all overridable. Zero extra dependencies.
- **`UrlCorpusBuilder`** (default for `SourceKind.URLS`, requires
  `digiskills[ingest]`): fetches each URL via `digifetch.HttpFetcher`,
  extracting plain text from HTML via a stdlib `html.parser.HTMLParser`
  (no BeautifulSoup dependency — good enough for doc pages, not a general
  HTML→Markdown converter). A single URL failure is logged and skipped, not
  fatal to the whole build (mirrors `digillm.web_search`'s fail-soft
  convention). Accepts an injected `fetcher=` for tests (an
  `httpx.MockTransport`-backed `HttpFetcher`) — no real network calls in the
  unit suite. Every fetched `SourceDocument` is marked `trusted=False` — see
  "Security hardening" below.

## Design decisions

- **Static package, not a service.** Per ADR-0023, Phase 1 distribution is a
  plain directory/zip — not an MCP server or hosted registry. That decision
  is deliberately revisited only after the package format proves useful
  (Phase 4, unscoped).
- **`TemplateSynthesizer` is the safe default, not a stub to delete later.**
  It has a real, permanent use: a zero-configuration compile with no
  network/API-key dependency, and it's what every unit test exercises. Real
  synthesis is opt-in (`DigiLLMSynthesizer`), never implicit.
- **References carry raw corpus content, not model output.** Both
  synthesizers build `references/` the same way, straight from
  `Corpus.documents` — the model only ever drafts the manifest description
  and the body's prose, never the reference bodies. This bounds hallucination
  risk to the "how to use it" narrative, not the source material itself.
- **`SkillSource.kind` picks the default builder, but callers can override
  either half independently** (`compile_skill(source, corpus_builder=...,
  synthesizer=...)`) — e.g. a caller can build its own `Corpus` upstream
  (a future digisearch-backed builder for huge corpora) and still use either
  synthesizer unchanged.
- **No digisearch integration yet.** ADR-0023 names digisearch (chunk/embed/
  retrieve) as a building block for corpora that outgrow naive ingestion.
  P1 ships without it: `LocalPathCorpusBuilder`'s size caps and
  `UrlCorpusBuilder`'s per-URL fetch cover the initial use cases (a single
  codebase, a docs site) without a vector-DB dependency. Revisit if a real
  corpus needs retrieval-style ranking rather than "ingest everything under a
  cap."

## Security hardening

P3 (external pilot, ADR-0023) is the point where third-party content — and
possibly credentials embedded in it — first enters the pipeline. A security
review ahead of P3 found four gaps in the remote-ingestion path
(`ingest_url.py`/`synthesize.py`), all fixed before any real external source
is run through the compiler:

1. **Compiled output wasn't flagged as untrusted.** `SKILL.md`/`references/`
   are literal instruction text a coding agent reads and acts on at install
   time — `CompileResult.warnings` (Python-side metadata) doesn't travel with
   the installed files, so a caller who discards warnings would ship an
   unflagged package. Fix: `SourceDocument.trusted` (default `True`, set
   `False` by `UrlCorpusBuilder`) — `synthesize.py` prepends an untrusted-
   content banner to any reference file and to `SkillPackage.body` built from
   untrusted content, and `DigiLLMSynthesizer`'s system prompt explicitly
   tells the model to treat corpus excerpts as untrusted data, never as
   instructions to follow or repeat.
2. **SSRF via redirects.** `digifetch.HttpFetcher`'s default client follows
   redirects with no host-pinning. Fix: `digiskills/security.py`'s
   `is_allowed_scrape_url` — a stdlib-only (`ipaddress`/`socket`/
   `urllib.parse`) duplicate of digisearch's proven `is_allowed_scrape_url`
   (REM-064; not imported, so `digiskills[ingest]` doesn't gain a digisearch
   dependency for one function) — validates every URL before fetching *and*
   the actually-fetched URL after, and `UrlCorpusBuilder`'s own default
   fetcher is built with `follow_redirects=False`, so a redirect is never
   actually requested (a 3xx response is simply skipped, not chased).
3. **Unbounded memory.** `HttpFetcher.fetch()` buffers the full decoded
   response with no byte cap; only the streamed `download()` enforces
   `DEFAULT_MAX_BYTES` (32 MiB). Fix: `UrlCorpusBuilder` now calls
   `download()` and decodes the returned bytes itself (`_decode_bytes`,
   charset from the response's `content-type`, utf-8 fallback) instead of
   `fetch()`.
4. **No secret redaction.** Scraped content could carry API keys/tokens into
   a reference file or into a `DigiLLMSynthesizer` prompt sent to a
   third-party model. Fix: `security.redact_secrets` — pattern-based
   (AWS/GitHub/Slack/OpenAI-style keys, PEM private-key blocks, JWTs, bearer
   tokens, generic `key=`/`secret=`/`token=`/`password=` assignments) —
   applied to every fetched document before it becomes a `SourceDocument`.
   Best-effort only, not a substitute for the source not containing secrets.

`security.scan_for_prompt_injection` complements (1): a best-effort,
non-blocking heuristic scan for injection-style phrasing (`"ignore previous
instructions"`, fake `system:`/`assistant:` turns, etc.) in fetched content.
It never mutates or strips content — regex heuristics are too false-positive/
negative-prone for that — it only adds to `Corpus.injection_flags`, which
`compile_skill` surfaces as a `CompileResult` warning alongside the untrusted
and redaction-count warnings.

Scope: this hardening covers `UrlCorpusBuilder` (the only builder that pulls
third-party content today). `LocalPathCorpusBuilder` ingests a path the
*caller* already controls (its own repo, or a corpus staged locally) and is
out of scope — `SourceDocument.trusted` defaults `True` there. If a future
source routes third-party content through `LocalPathCorpusBuilder` (e.g. a
pre-scraped local mirror), revisit whether it needs the same redaction/
trust-flagging pass.

## Environment variables

| Variable | Used by | Purpose |
|----------|---------|---------|
| `DIGISKILLS_SYNTHESIS_MODEL` | `DigiLLMSynthesizer` | Default model string (falls back to `openrouter/auto`); pass `model=` to override per instance. |

No other configuration — the core library and `LocalPathCorpusBuilder` need
no environment variables at all.

## Versioning & consumption

`digiskills` is versioned by release-please on the `module/digiskills` branch
(`release-please-digiskills.yml`, mirroring digichat's setup — see #1343 for why
module-branch rather than `main`). Releases tag `digiskills-vX.Y.Z`; the Python
release-type bumps `pyproject.toml`, and an `extra-files` generic updater bumps
`__version__` in `src/digiskills/__init__.py` (annotated
`# x-release-please-version`) so the two never drift.

Because the digithings repo is public, an external consumer installs a pinned
version straight from a tag — no PyPI publish, no registry:

```bash
pip install "digiskills[cli] @ git+https://github.com/digithings-ai/digithings.git@digiskills-v0.2.0#subdirectory=digiskills"
```

**Dependency-confusion caveat:** the `[ingest]` extra declares `digifetch>=0.1.0`,
a monorepo sibling that is **not** published to PyPI. A plain
`pip install "digiskills[ingest] @ git+..."` would try to resolve `digifetch`
from PyPI and either fail or (worse) pull an unrelated package of that name.
Only the `[cli]` install above (core + typer, both on PyPI) is safe to consume
from a git tag. If remote-URL ingestion is ever needed off-repo, install
`digifetch` from its own git subdirectory first.

## Testing

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
```

`tests/dsk/test_ingest_url.py` and the `DigiLLMSynthesizer` cases in
`test_synthesize.py` are skipped (`pytest.importorskip`) when `digifetch` /
`digillm` aren't installed, and never make a real HTTP or LLM call even when
they are — `httpx.MockTransport` and a monkeypatched `digillm.completion`
stand in. `tests/dsk/test_security.py` (stdlib-only, always runs) covers the
SSRF allowlist, redaction, and injection-scan functions directly;
`test_ingest_url.py` covers them wired into `UrlCorpusBuilder` (blocked URLs
never reach the fetcher, a redirect that an injected fetcher does follow is
still caught by the post-fetch host re-check, the byte cap trips via
`download()`, secrets get redacted, injection phrasing gets flagged not
stripped).

`tests/dsk/test_dogfood.py` (P2) compiles every DigiThings module's real
`ARCHITECTURE.md`/`AGENTS.md` (digigraph, digiquant, digisearch, digismith,
digiclaw, digibase, digikey, digivault, digifetch, digillm, digiskills,
digichat) through the full pipeline with `TemplateSynthesizer`, asserting a
clean compile (no truncation warnings — real module docs stay well under the
size caps) and a well-formed, round-trippable `SKILL.md`. This validates
ingestion/packaging against real content on every CI run; it does not
validate `DigiLLMSynthesizer` prose quality, which needs a live model and is
a manual check.

## Monorepo integration

- Registered in `agents.yml` under `components:` (`agents_doc`, `arch_doc`,
  `test_cmd: pytest -m unit -k digiskills -v`).
- `pytest.ini`'s root `pythonpath` includes `digiskills/src` so
  `import digiskills` resolves without an editable install during `pytest`
  from the repo root.
- No Docker image, no compose service, no published port — this module has
  no network-facing surface today.

## Phase 2+ gaps and roadmap

Per ADR-0023's phase plan:

| Gap | Phase | Notes |
|-----|-------|-------|
| Dogfood against DigiThings' own modules | P2 (done) | `tests/dsk/test_dogfood.py` compiles `ARCHITECTURE.md`/`AGENTS.md` from every module as a known-good validation corpus. MCP tool manifests (live `/v1/orchestrator_tools` responses) are **not** included — that needs running services, not a static-file corpus; still a gap. |
| External pilot against a real client's docs/API | P3 | Pre-flight hardening done (see "Security hardening" above: SSRF, memory cap, redaction, untrusted/injection flagging). Actually running a real client source through the pipeline is still pending a go/no-go decision on which builder/source to use. |
| digisearch-backed corpus builder | Follow-up | For corpora that outgrow naive ingestion (huge codebases/doc sites) — chunk/embed/retrieve instead of "ingest everything under a cap." |
| Hosted platform / registry / live MCP distribution | P4 (unscoped) | Explicitly deferred in ADR-0023; revisit only after the static package format is proven useful. |
| Prompt-quality tuning for `DigiLLMSynthesizer` | Ongoing | P1 ships a working structured-output integration, not a tuned prompt — expect iteration once real corpora are run through it. |
