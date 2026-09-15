# OSS Web Search Phase B — Web Research Turn + Cited Answers (Implementation Spec)

**Status:** spec only — research + write, no implementation in this phase.
**Scope:** Phase B only. Phase A (landed `digisearch.web_search` provider
surface: SearXNG/ddgs providers, extractor, URL ingest) and Phases C/D
(pipeline consumers) are out of scope except as declared contracts.

**Erratum (2026-09-15, post-Phase-A landing):** the consumed surfaces below
were corrected to the landed `digisearch.web_search.*` API (Phase A merged on
`origin/module/digisearch`, #4055/#4061). Earlier drafts named a planned
provider package that Phase A did not ship; that package does not exist and
MUST NOT be created. `digisearch.web_search.*` EXISTS and is the only OSS
web-provider surface (EXA lives separately in `digisearch/web_exa.py`, behind
`POST /v1/digisearch_web_search`). The landed retrieval models are
`WebSearchResponse` / `WebSearchResult`; the `WebSearchData` envelope split is
stated under Consumes below. Rulings R1–R10 from the SDD ledger
(`.superpowers/sdd/2026-09-14-oss-websearch-phaseB-web-research-turn/progress.md`)
are applied.

## Consumes / Produces

- **CONSUMES (Phase A contracts — landed on `origin/module/digisearch`):**
  `digisearch.web_search.service.search_web(req: WebSearchRequest,
  config: WebSearchConfig | None = None) -> WebSearchResponse` (public wrapper
  added in Task 0, delegating to the existing `_search_only` failover:
  `auto|searxng|ddgs`) /
  `digisearch.web_search.models.WebSearchRequest` / `WebSearchResponse` /
  `WebSearchResult` (retrieval-surface rows `{url, title, snippet, score,
  engine}`) /
  `digisearch.web_search.searxng_provider.SearXNGWebSearchProvider.search(req)`
  (the primary provider behind the failover — consumed via `search_web`, never
  constructed directly by Phase B) /
  `digisearch.web_search.extractor.extract_markdown(html, url="") -> str`
  (trafilatura primary, readability fallback) /
  `digisearch.web_search.fetch.fetch_markdown(url, *, timeout, allowed_hosts,
  fetcher=None) -> str` (new Task 0, non-indexing) /
  `digisearch.web_search.citation.Citation` + `normalize_url` (new Task 0).
  `digisearch.pipeline.url_ingest.ingest_url(url, ...) -> UrlIngestResult` is
  deliberately NOT consumed by Phase B: it indexes into a corpus index and
  would violate the no-corpus-mixing rule — Task 1's `_fetch` uses
  `fetch_markdown` instead.
  Phase B MUST NOT re-implement these; it adapts them behind a narrow seam
  (Task 1: `digisearch.web.retrieve`, the ONLY place that imports
  `digisearch.web_search.*`) so a Phase A shape change touches exactly
  one file. Direct import within `digisearch`; HTTP only at
  process/component boundaries (digigraph, digichat, digiclaw call
  `POST /v1/research_turn` / `POST /v1/orchestrator_invoke` with service JWT).
- **Envelope split (R1):** `digisearch.web_exa.WebSearchData`
  (`{results, output, search_type, cost_dollars}`) remains the turn /
  interchange OUTPUT envelope used for `output.content` /
  `output.grounding`-shaped results and consumed by HTTP/MCP/orchestrator
  surfaces; `WebSearchResponse` / `WebSearchResult` are the retrieval-surface
  rows. Conversion from retrieval rows to the envelope happens in the seam
  (`web/retrieve.py` + Task 3/4 assembly) — provider modules never import
  `web_exa`.
- **PRODUCES (for Phases C/D):** `grounded_answer()` + `structured_synthesis()`
  in `digisearch.web`, both returning `WebSearchData`-compatible payloads;
  the `research_turn` web branch (`plan → web_retrieve → web_aggregate`);
  effort modes (`fast` / `thorough`); per-turn cost/latency accounting.
  Phases C/D build pipeline consumers on these without touching synthesis.

## Goal

Extend `research_turn` (`plan → retrieve → aggregate` in
`digisearch/src/digisearch/agent/pipeline.py`, exposed via
`POST /v1/research_turn` and MCP `digisearch_research_turn`) with an explicit
web branch that implements the Perplexica loop (33k stars, MIT — reference
implementation for the prompt/citation loop only, not vendored code):

1. Live query via Task 0 `search_web()` (landed
   `SearXNGWebSearchProvider.search(req)` behind the `auto|searxng|ddgs`
   failover, returning `WebSearchResponse` rows).
2. Fetch top-N pages via Task 0 `fetch_markdown()` (non-indexing; the landed
   `extract_markdown -> str` runs trafilatura primary, readability fallback).
   `ingest_url()` is NOT used — it indexes a corpus index.
3. BGE rerank (already in `digisearch[rerank]`, `search/reranker.py`) +
   BM25 query-filtering (`search/keyword.py`) to cut fetched pages to the
   cited set.
4. `digillm` synthesis with inline `[n]` citations
   (Perplexica-style: numbered sources, every factual claim cited).
5. Structured synthesis with EXA-shaped grounding: EXA's
   `output.content` + `output.grounding[{field, citations[{url,title,`
   `excerpt}], confidence}]` design adapted as a required-keys-checked
   contract (see Task 4 — strict `json_schema` forces the wrapper
   `{content: <output_schema>, grounding: [...]}`, so it is NOT verbatim
   EXA; full JSON-Schema validation would need a new dependency and is out
   of scope), with a verification pass (EXA's live fields are loose — see
   below): uncited entries are flagged `unverified` (kept, never silently
   dropped), echo-detected fields are downgraded one level.
6. Effort modes (`fast` vs `thorough`) and per-turn cost/latency accounting
   mirroring EXA's `costDollars` / `usage` reporting. Cost `total` is
   advisory-only: OSS reports `{total: 0.0, provider, breakdown, note}` and
   `total` MUST NOT drive budget/routing gates alone (per R6 below); any
   comparison copy MUST say "OSS total excludes LLM spend".

**EXA stays** as the paid alternative behind the same `WebSearchData`
interface (`digisearch/web_exa.py` untouched). OSS synthesis output MUST be
`WebSearchData`-compatible so EXA/OSS stay interchangeable at every surface
(HTTP, MCP, orchestrator manifest).

**Observed live EXA behavior this spec designs against**
(`s4_deep_structured.json`, `g2_agent_done.json` in `/tmp/exa-review/`):

- `s4`: `costDollars{total: 0.012}` shallow structured search;
  `output.content{companies[{name, launcher}]}` +
  `output.grounding[{field: "companies[i].name", citations[{url,title}],`
  `confidence: "high"}]` — but `launcher` echoes the company name verbatim
  (loose field, still marked `high`). Hence the verification step: citations
  required per field, confidence downgrade when uncited or echo-detected.
- `g2`: agent run `output{text, structured, grounding}` +
  `usage{agentComputeUnits, searches, emails, phoneNumbers}` +
  `costDollars{total: 0.2642, agentCompute, search, ...}` (~$0.26 deep run
  vs ~$0.007–0.012 shallow). Hence effort modes + advisory cost/latency
  fields. All dollar figures and `/tmp/exa-review/` fixtures are
  single-key, single-day scaffolding anchors for Task 6 harness shape —
  NOT SLO constants; Task 6 records per-environment re-measurements before
  any SLO is written from them.

**Consolidation with prior web-search plans (no contradictions):**

- `2026-09-10-web-search-mcp-tool.md` — Phase A owner of the
  `digisearch.web_search` surface (SearXNG/ddgs providers, extractor, URL
  ingest), now landed. Phase B consumes it, never forks it; the single
  adaptation seam is Task 1 (`digisearch.web.retrieve`, importing
  `digisearch.web_search.*` only).
- `2026-09-11-web-search-default-on-tool-only.md` — pipeline is tool-only +
  fail-hard (any web-dependency failure raises `WebResearchError`,
  surfaced as `error` on the turn state, never a silent fallback or an
  uncited synthesis). Tool-only is superseded ONLY for explicitly requested
  web turns (R5, see Architecture): `source` defaults to `corpus`, so every
  existing caller keeps the tool-only posture unless it opts in.
  Phase B web branch follows the same fail-hard rule: any web-dependency
  failure raises (surfaced as `error` on the turn state, aborting the
  branch), never an uncited synthesis.
- `2026-09-12-web-search-followups.md` — fail-closed catch behavior, public
  wrapper naming, docs consistency. Phase B keeps fail-closed everywhere and
  pins the fail-hard shape in a test (Task 5).

## Architecture

```
POST /v1/research_turn {user_message, source: "corpus"|"web"|"auto", effort, ...}
  │  source="corpus" (default) → existing plan → retrieve → aggregate (unchanged)
  │  source="web"|"auto" (explicit opt-in) → plan → web_retrieve → web_aggregate
  ▼
web_retrieve:
  search_web (Task 0 wrapper over the landed web_search.service failover
              auto|searxng|ddgs → WebSearchResponse rows)
    → fetch top-N pages (Task 0 fetch_markdown → str; landed extract_markdown
      is trafilatura primary, readability fallback; ingest_url is NEVER used
      — it indexes)
    → chunk (get_document_chunker, no segment wrapper — research flat payloads)
    → BM25 query-filter (search/keyword.py, drop zero-score pages)
    → BGE rerank (search/reranker.py provider="bge", top_n = cited set)
    → normalized web hits [{url, title, snippet≤2000c, score, engine}]
web_aggregate:
  digillm.completion(messages=[system+numbered sources+question]) → answer [n]
    → structured path: response_format=json_schema({content:<output_schema>,
      grounding:[...]}) — wrapper object, NOT caller schema at top level
      (strict json_schema cannot return caller-schema content AND a
      grounding key side by side)
      → verify_grounding (flag uncited UNVERIFIED, echo-detected downgrade)
    → WebSearchData{results, output{content, grounding, text}, search_type,
                    cost_dollars{total, provider, breakdown, note}}
    → (WebSearchData, TurnUsage) tuple — usage travels as an explicit
      second return value onto turn state, NEVER via model_extra
      (`WebSearchData` is `extra="ignore"` and drops extras)
    → ResearchTurnOutput.{results, rag_sources, formatted_context} rebuilt
      from web hits (corpus shape preserved for digigraph/digichat)
```

- **No corpus mixing:** web hits never enter `SearchResponse` / owned indexes,
  and the branch never calls `ingest_url` (it indexes; R3 — fetch goes through
  Task 0 `fetch_markdown`). `backend="web-oss"` on the turn output;
  `evidence_tier="External"` on every web `rag_sources` entry (matches the
  09-10 External-tier rule).
- **Opt-in only (R5):** `source` defaults to `"corpus"`; the web branch runs
  ONLY when the caller explicitly passes `source="web"` or `source="auto"`.
  This preserves the #3420 invariant and is orthogonal to the 09-11
  chat-toggle defaults (those control UI prefs, not the `research_turn`
  default). It deliberately supersedes the #3859 "grounding is tool-only"
  policy ONLY for explicitly requested web turns — no existing caller and no
  digigraph delegate default changes; Task 6 records the supersession note in
  `digisearch/ARCHITECTURE.md`.
- **Fail-hard:** any failure in live query, fetch-all-fail, rerank import
  failure, or `digillm` failure sets `state.error` and ends the turn with
  `error` set — never a citation-free answer. Zero fetchable pages is an
  error, not an empty answer.
- **digillm stays behind a lazy import** inside `digisearch.web` synthesis
  functions so the digisearch base install never hard-depends on it; missing
  `digillm` raises a clear error naming the missing extra.
- **digigraph never imports digisearch** (unchanged): it keeps calling
  `POST /v1/research_turn` / `POST /v1/orchestrator_invoke`.

## Tech Stack

Python 3.12, Pydantic v2 (strict, `extra="forbid"` on new models),
`digisearch[agent]` (langgraph) + `digisearch[rerank]` (sentence-transformers,
`BAAI/bge-reranker-v2-m3`) + `digillm.client.completion` with
`response_format` json_schema structured output, `rank_bm25` via the existing
`BM25Searcher` import guard, `httpx` only for any new transport (none new —
Task 0 `fetch_markdown` sits on digifetch + the landed extractor, and Task 0
`citation.py` is pydantic-only), ruff line-length 100.

## File Structure

Exact paths (all relative to repo root). **Task 0 is a prep step** that adds
the landed-surface atoms (`citation.py`, `fetch.py`, public `search_web`)
before Tasks 1–6; it changes no existing behavior.

| Path | Action | Contents |
|------|--------|----------|
| `digisearch/src/digisearch/web_search/citation.py` | Create | Task 0 prep: `Citation` pydantic model (`extra="forbid"`, `{url,title="",excerpt=""}`) + `normalize_url()` (lowercase host, strip fragment, drop default port, trim trailing slash) |
| `digisearch/src/digisearch/web_search/fetch.py` | Create | Task 0 prep: `fetch_markdown(url, *, timeout, allowed_hosts, fetcher=None) -> str` — digifetch `HttpFetcher.download()` + landed `extract_markdown`; no indexing |
| `digisearch/src/digisearch/web_search/service.py` | Modify | Task 0 prep: add public `search_web(req, config=None) -> WebSearchResponse` delegating to the existing `_search_only` (no behavior change; keeps `auto|searxng|ddgs` failover) |
| `digisearch/src/digisearch/web_search/__init__.py` | Modify | Task 0 prep: re-export `Citation` + `normalize_url` |
| `digisearch/src/digisearch/web/__init__.py` | Create | Lazy exports: `grounded_answer`, `structured_synthesis`, `verify_grounding`, grounding models, `WebResearchConfig`, accounting helpers |
| `digisearch/src/digisearch/web/grounding_models.py` | Create | `GroundingCitation` (re-export of the landed `web_search.citation.Citation`), `FieldGrounding{field,citations,min 1,confidence}`, `StructuredSynthesis{content:dict,text:str,grounding:list}`, `Confidence(str Enum: high,medium,low,unverified)`, `EffortMode(str Enum: fast,thorough)`, `WebResearchConfig`, `TurnUsage`, `TurnCost{total,provider,breakdown,note}` |
| `digisearch/src/digisearch/web/accounting.py` | Create | `StageTimer` helpers: `start_clock()`, `record_stage()`, `finalize_usage()`, `estimate_cost()` — pure functions over a small `StageTimer` dataclass (no wall-clock in return values except measured ms) |
| `digisearch/src/digisearch/web/answer.py` | Create | `grounded_answer()` (Perplexica loop, markdown + `[n]` citations) |
| `digisearch/src/digisearch/web/structured.py` | Create | `structured_synthesis()` + `verify_grounding()` (EXA-shaped contract + verification pass) |
| `digisearch/src/digisearch/web/retrieve.py` | Create | **Sole web_search adaptation seam:** `live_search()` + `fetch_pages()` wrappers mapping landed `search_web` rows (`WebSearchResult`) / Task 0 `fetch_markdown` pages to `FetchedPage`; every other Phase B file imports the provider surface only through here (imports `digisearch.web_search.*`; never calls `ingest_url` — it indexes) |
| `digisearch/src/digisearch/agent/pipeline_models.py` | Modify | Additive-only fields on `ResearchTurnState`/`ResearchTurnOutput`/`ResearchTurnRequest` (web branch slots; corpus fields untouched; `ResearchTurnOutput` MUST declare every new field — FastAPI `response_model` + `_output_from_state` drop undeclared keys, R10) |
| `digisearch/src/digisearch/agent/web_branch.py` | Create | `node_web_retrieve`, `node_web_aggregate`, `resolve_web_config()` (R9 precedence); `run_web_research_turn()` helper |
| `digisearch/src/digisearch/agent/pipeline.py` | Modify | Wire web nodes + `source in {"web","auto"}` routing; thread new state keys through `_state_from_initial` AND `_output_from_state`; existing node behavior unchanged |
| `digisearch/src/digisearch/server.py` | Modify | `ResearchTurnRequest` gains `source`, `effort`, `output_schema`, `cited_top_n`; response carries `WebSearchData`-compatible `output`/`cost_dollars`/`usage` (declared on `ResearchTurnOutput`, R10) |
| `digisearch/src/digisearch/mcp_server.py` | Modify | `digisearch_research_turn` gains `source`/`effort` passthrough (no `output_schema` this phase, R7) |
| `digisearch/src/digisearch/orchestrator_tools.py` | Modify | Research-delegate tool schema gains `source`/`effort` (+ `output_schema` passthrough) |
| `digisearch/ARCHITECTURE.md` | Modify | Web-branch section (Task 6 only; incl. #3859 supersession note) |
| `digisearch/tests/test_web_search_citation.py` | Create | Task 0 tests (`Citation` + `normalize_url`) |
| `digisearch/tests/test_web_search_fetch.py` | Create | Task 0 tests (`fetch_markdown`, non-indexing pin) |
| `digisearch/tests/test_web_search_service.py` | Modify | Task 0 tests (`search_web` delegation; next to the landed provider suite, R8) |
| `tests/ds/test_web_grounding_models.py` | Create | Task 1 tests |
| `tests/ds/test_web_accounting.py` | Create | Task 2 tests |
| `tests/ds/test_web_answer.py` | Create | Task 3 tests (all external boundaries mocked) |
| `tests/ds/test_web_structured.py` | Create | Task 4 tests (incl. echo-fixture from `s4` + `g2` shapes) |
| `tests/ds/test_research_turn_web_branch.py` | Create | Task 5 tests (graph routing, fail-hard pin, R9/R10 pins, HTTP/MCP shape) |
| `tests/ds/test_web_eval_live.py` | Create | Task 6 eval harness (mocked by default; live behind `DIGISEARCH_WEB_SEARCH_LIVE=1`) |

Provider-suite tests (Task 0 atoms) live in `digisearch/tests/` next to the
landed suite; the web-branch suite lives in `tests/ds/`; both roots are wired
via `pytest.ini` (R8) and both must be run.

Synthesis output MUST be `WebSearchData`-compatible: `results` = web hits as
`{title,url,snippet,score,engine}` dicts; `output` =
`{text, content, grounding[{field,citations[{url,title,excerpt}],confidence}]}`;
`search_type` = `"web-<effort>"`; `cost_dollars` =
`{total: 0.0, provider: "web-oss", breakdown{searches,pages_fetched,llm_calls},
note}` (advisory-only; "OSS total excludes LLM spend"); `usage` travels as a
separate `TurnUsage` return value / turn-state key, never inside
`WebSearchData` (which is `extra="ignore"` and drops extras).
EXA (`web_exa.py`) and OSS (`web/`) therefore stay interchangeable at
`POST /v1/digisearch_web_search`-shaped consumers. Note: `format_web_results` reads
`title/url/publishedDate/author/highlights/text` keys — OSS web hits carry
`snippet` (not `highlights`/`text`), so OSS payloads render Title/URL-only
through it; `node_web_aggregate` therefore builds its own numbered
`formatted_context` lines and does not route OSS output through
`format_web_results`.

## Interfaces

PRODUCED signatures (exact — Phases C/D program to these):

```python
# digisearch.web_search.citation (Task 0 prep — the shared atom, R2)
class Citation(BaseModel):  # extra="forbid"
    url: str
    title: str = ""
    excerpt: str = ""

def normalize_url(url: str) -> str:
    """Lowercase host, strip fragment, drop default port, trim trailing slash."""
    # http://Example.COM:80/a/?x=1#frag -> http://example.com/a?x=1
```

```python
# digisearch.web.grounding_models
# GroundingCitation is a RE-EXPORT of the landed atom above (single shape,
# never a fork — R2/R4):
from digisearch.web_search.citation import Citation as GroundingCitation
# Citation: extra="forbid", {url, title="", excerpt=""}; excerpt carries the
# supporting snippet so B-grounded fields feed Phase D admissibility without
# lossy translation.

class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNVERIFIED = "unverified"

class FieldGrounding(BaseModel):  # extra="forbid"
    field: str  # dotted path, e.g. "rounds[1].amount"
    citations: list[GroundingCitation] = Field(min_length=1)
    confidence: Confidence = Confidence.HIGH

class StructuredSynthesis(BaseModel):  # extra="forbid"
    content: dict[str, Any]  # validates against caller output_schema
    text: str = ""
    grounding: list[FieldGrounding] = Field(default_factory=list)

class EffortMode(str, Enum):
    FAST = "fast"
    THOROUGH = "thorough"

class WebResearchConfig(BaseModel):  # extra="forbid"
    effort: EffortMode = EffortMode.FAST
    live_top_n: int = 8       # search hits requested (fast)
    fetch_top_n: int = 5      # pages fetched (fast)
    cited_top_n: int = 5      # sources passed to synthesis (fast)
    synthesis_model: str = ""  # resolved from DIGISEARCH_SYNTHESIS_MODEL
    max_synthesis_chars: int = 12000

EFFORT_PRESETS: dict[EffortMode, WebResearchConfig]  # thorough: 20/10/8

class TurnUsage(BaseModel):  # extra="forbid", mirrors EXA usage
    searches: int = 0
    pages_fetched: int = 0
    pages_cited: int = 0
    llm_calls: int = 0
    search_ms: int = 0
    fetch_ms: int = 0
    rerank_ms: int = 0
    synthesis_ms: int = 0
    total_ms: int = 0

class TurnCost(BaseModel):  # extra="forbid", mirrors EXA costDollars
    total: float = 0.0  # ADVISORY-ONLY. OSS has no metered dollar cost;
                        # MUST NOT drive budget/routing gates alone (R6).
                        # Gates MUST include stage-ms and
                        # breakdown.llm_calls > 0 ⇒ consult digillm telemetry.
    provider: str = "web-oss"
    breakdown: dict[str, int] = Field(default_factory=dict)
    note: str = "oss-synthesis; llm spend metered in digillm telemetry, not here"
    # note is a REAL field: extra="forbid" rejects model_extra, so it cannot
    # ride along undeclared. Any comparison copy MUST say
    # "OSS total excludes LLM spend".
```

```python
# digisearch.web.answer
def grounded_answer(
    question: str,
    *,
    config: WebResearchConfig | None = None,
) -> tuple[WebSearchData, TurnUsage]: ...
# Perplexica loop: live_search → fetch_pages → BM25 filter → BGE rerank →
# digillm synthesis with inline [n] citations. Retrieval rows are the landed
# WebSearchResult; the returned envelope stays web_exa.WebSearchData (R1).
# Returns the WebSearchData payload AND the TurnUsage (explicit tuple —
# WebSearchData is extra="ignore" and drops extras, so usage MUST NOT ride
# model_extra).
# Raises WebResearchError on any dependency failure or zero cited pages.
# Trigger split (M8): ZERO cited pages after fetch+filter+rerank → raise
# WebResearchError. NON-EMPTY cited set the model cannot support → return
# the literal "insufficient sources" sentence WITH the numbered source list
# (still cited, still WebSearchData — never an uncited answer).

# digisearch.web.structured
def structured_synthesis(
    question: str,
    *,
    output_schema: dict[str, Any],
    config: WebResearchConfig | None = None,
) -> tuple[WebSearchData, TurnUsage]: ...
# Same retrieval as grounded_answer, then digillm structured call whose
# response_format wraps the caller schema:
# {"type":"json_schema","json_schema":{"name":"web_structured","schema":
#   {"type":"object","properties":{"content":<output_schema>,
#    "grounding":{"type":"array","items":{...FieldGrounding...}}},
#    "required":["content","grounding"],"additionalProperties":False}}}
# (strict json_schema cannot return caller-schema content AND a grounding
# key side by side at top level). output={"content","grounding","text"}.
# Every grounding entry passes through verify_grounding before return.

def verify_grounding(
    content: dict[str, Any],
    grounding: list[FieldGrounding],
    *,
    cited_urls: set[str],
) -> list[FieldGrounding]: ...
# Pure function. What the rules actually enforce (no stronger claim):
# (1) entry whose citations are all outside cited_urls → confidence=UNVERIFIED
# (kept and flagged, never silently dropped); (2) field value that
# string-echoes a sibling field value (case-insensitive containment, e.g. s4
# launcher==name) → downgrade one level (HIGH→MEDIUM→LOW, LOW→UNVERIFIED);
# (3) entries for fields absent from content are dropped. Cited-but-irrelevant
# entries stay at their model-assigned confidence — this pass does NOT detect
# irrelevance. Cross-phase binding: Phases C/D MUST hide or explicitly flag
# UNVERIFIED-grounded fields (never render them as verified); until a
# consumer spec pins that rule, no cross-phase correctness guarantee is
# claimed. Never raises on loose input.

# digisearch.web.retrieve (sole web_search adaptation seam — the ONLY place
# importing digisearch.web_search.*)
from digisearch.web_search.models import WebSearchResult

def live_search(query: str, *, top_n: int) -> list[WebSearchResult]: ...
def fetch_pages(hits: list[WebSearchResult], *, top_n: int) -> list[FetchedPage]: ...
# FetchedPage{url,title,markdown}.
# Internals (the mock seams pinned by Task 1 tests):
#   _live(query, top_n) -> WebSearchResponse — calls Task 0 search_web(
#       WebSearchRequest(query=query, max_results=top_n)); rows keep the
#       landed {url,title,snippet,score,engine} shape (no `highlights` key).
#   _fetch(hits, top_n) -> list[FetchedPage] — calls Task 0 fetch_markdown(url)
#       per hit and drops empty markdown; MUST NEVER call ingest_url (it
#       indexes — no-corpus-mixing rule; pinned by a source-level test).
# NOTE: web_search.models (pydantic-only) may import at module scope; the
# service/fetch imports stay inside the seam functions so the base install
# imports retrieve.py with no digifetch/[web-search] extra.
```

```python
# digisearch.agent.web_branch
def node_web_retrieve(state: ResearchTurnState) -> dict[str, Any]: ...
def node_web_aggregate(state: ResearchTurnState) -> dict[str, Any]: ...
def resolve_web_config(*, effort: str, cited_top_n: int | None) -> WebResearchConfig: ...
    # explicit request cited_top_n wins over the effort preset (R9)
def run_web_research_turn(initial: dict[str, Any]) -> dict[str, Any]: ...
# State additions (pipeline_models, additive only):
#   source: str = "corpus"            # "corpus" | "web" | "auto"
#   effort: str = "fast"              # "fast" | "thorough"
#   output_schema: dict | None = None # structured path when set
#   cited_top_n: int | None = None    # explicit request wins over preset (R9)
#   web_output: dict | None = None    # WebSearchData.output mirror
#   cost_dollars: dict | None = None  # TurnCost dump
#   usage: dict | None = None         # TurnUsage dump
# Every key above MUST also be declared on ResearchTurnOutput (R10) and
# threaded through _state_from_initial + _output_from_state (Task 5).
```

## Global Constraints

- Python 3.12, Pydantic v2 everywhere, strict typing, ruff line-length 100;
  `ruff check digisearch/ && ruff format --check digisearch/` zero errors.
- Lowercase digi names in prose/docs/commits (`digisearch`, `digillm`,
  `digigraph`, `digichat`).
- No pandas (Polars-only); no new hard dependencies — `digillm`,
  `sentence-transformers` (`[rerank]`), `langgraph` (`[agent]`), `rank_bm25`
  all lazy-imported with clear missing-extra errors.
- Scope enforcement: no new public route; extended `POST /v1/research_turn`
  keeps `digisearch:query` via `DigiAuthMiddleware`; MCP stays loopback-only.
- No full doc bodies in digismith spans: trace details carry counts, urls,
  and stage ms only — snippets/answer text never enter
  `ResearchTurnTraceStep.detail`.
- Scope: research + implement per this spec only; update
  `digisearch/ARCHITECTURE.md` on interface change; every change traces to its
  tracking issue; human gate applies (new synthesis path over external web
  content — do not merge without review).
- `digisearch/web_exa.py` is read-only for Phase B (EXA stays the paid
  alternative; zero changes to its wrapper, routes, or manifest gating).
- Access pattern: direct import within `digisearch` (`web_search.*` only via
  `web/retrieve.py`); HTTP only at process/component boundaries.
- Extractor contract is the landed `extract_markdown(html, url="") -> str`
  (trafilatura primary, readability fallback — `web_search/extractor.py`);
  `fetch_markdown`/`fetch_pages` consume the string directly. A future
  extractor swap (e.g. Crawl4AI) is out of Phase B scope and MUST NOT change
  this seam's signature.

---

## Task 0: prep atoms (landed-surface prerequisites)

**Files:**

- Create: `digisearch/src/digisearch/web_search/citation.py`
- Create: `digisearch/src/digisearch/web_search/fetch.py`
- Modify: `digisearch/src/digisearch/web_search/service.py` (add public
  `search_web`)
- Modify: `digisearch/src/digisearch/web_search/__init__.py` (re-export
  `Citation`, `normalize_url`)
- Create: `digisearch/tests/test_web_search_citation.py`
- Create: `digisearch/tests/test_web_search_fetch.py`
- Modify: `digisearch/tests/test_web_search_service.py` (add `search_web`
  delegation test)

**Interfaces:**

- Consumes: landed Phase A (`web_search.service._search_only`,
  `web_search.extractor.extract_markdown`, digifetch `HttpFetcher`).
- Produces: `Citation`, `normalize_url()` (shared atom, R2; also consumed by
  Phase D), `fetch_markdown()` (non-indexing fetch, R3), `search_web()`
  (public retrieval wrapper) — all used by Task 1+.

- [ ] **Step 1: Write the failing tests**

```python
# digisearch/tests/test_web_search_citation.py
import pytest

from digisearch.web_search.citation import Citation, normalize_url


def test_citation_shape_forbids_extras():
    from pydantic import ValidationError

    c = Citation(url="https://A.com/x#frag", title="A", excerpt="e")
    assert c.excerpt == "e"
    with pytest.raises(ValidationError):
        Citation(url="https://a.com", bogus="x")


def test_normalize_url_semantics():
    assert normalize_url("https://Example.COM:443/Path/?x=1#frag") == (
        "https://example.com/Path?x=1"
    )
    assert normalize_url("http://Example.com:80/a/") == "http://example.com/a"
    assert normalize_url("https://example.com/") == "https://example.com/"
```

```python
# digisearch/tests/test_web_search_fetch.py
def test_fetch_markdown_decodes_and_extracts(monkeypatch):
    from digifetch import DownloadResult

    from digisearch.web_search import fetch as mod

    seen: dict[str, str] = {}

    def fake_extract(html: str, url: str = "") -> str:
        seen["html"], seen["url"] = html, url
        return "# body"

    monkeypatch.setattr(mod, "extract_markdown", fake_extract)

    class _FakeFetcher:
        def download(self, url: str) -> DownloadResult:
            return DownloadResult(
                status_code=200,
                url=url,
                content="<html><body><p>café</p></body></html>".encode(),
                content_type="text/html; charset=utf-8",
            )

    assert mod.fetch_markdown("https://a.com/1", fetcher=_FakeFetcher()) == "# body"
    assert "café" in seen["html"] and seen["url"] == "https://a.com/1"


def test_fetch_module_is_non_indexing():
    import inspect

    from digisearch.web_search import fetch as mod

    src = inspect.getsource(mod)
    assert "ingest_url" not in src
    assert "ingest_source" not in src
```

```python
# digisearch/tests/test_web_search_service.py (add)
def test_search_web_delegates_to_search_only(monkeypatch):
    from digisearch.web_search import service as mod
    from digisearch.web_search.models import WebSearchRequest, WebSearchResponse

    seen: dict[str, object] = {}

    def fake_search_only(req, config):
        seen["query"] = req.query
        return WebSearchResponse(query=req.query, provider="searxng")

    monkeypatch.setattr(mod, "_search_only", fake_search_only)
    resp = mod.search_web(WebSearchRequest(query="q"))
    assert resp.provider == "searxng" and seen["query"] == "q"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest digisearch/tests/test_web_search_citation.py
digisearch/tests/test_web_search_fetch.py
digisearch/tests/test_web_search_service.py -v`
Expected: ERROR at collection — `ModuleNotFoundError: No module named
'digisearch.web_search.citation'` / `...fetch` (the Step-1 files exist, the
modules do not yet), and `AttributeError: module
'digisearch.web_search.service' has no attribute 'search_web'` for the
delegation test. If pytest instead reports `file or directory not found`, the
Step-1 file was not created — fix that first; it is a different failure.

- [ ] **Step 3: Write minimal implementation**

`citation.py`: `Citation` pydantic model (`extra="forbid"`,
`{url: str, title: str = "", excerpt: str = ""}`) and
`normalize_url(url) -> str` (docstring pins the semantics: lowercase host,
strip fragment, drop default port, trim trailing slash except root).
`fetch.py`: `fetch_markdown(url, *, timeout: float = 15.0, allowed_hosts:
Iterable[str] = (), fetcher: HttpFetcher | None = None) -> str` — one
SSRF-guarded digifetch `HttpFetcher.download()` (owned fetcher when `fetcher`
is None, reusing `web_search.service.WebSearchConfig.from_env()` timeout/
allowed hosts like `url_ingest` does), charset-aware decode, then landed
`extract_markdown`; returns `""` when nothing is extractable. No indexing:
never imports or calls `ingest_source`/`ingest_url`.
`service.py`: public `search_web(req: WebSearchRequest, config:
WebSearchConfig | None = None) -> WebSearchResponse` that resolves
`config = config or WebSearchConfig.from_env()` and returns
`_search_only(req, config)` — no behavior change, keeps the
`auto|searxng|ddgs` failover (`run_web_search` still owns fetch enrichment).
`__init__.py`: re-export `Citation` + `normalize_url`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest digisearch/tests/test_web_search_citation.py
digisearch/tests/test_web_search_fetch.py
digisearch/tests/test_web_search_service.py -v`
Expected: PASS (landed service tests remain green — no behavior change)
Run: `ruff check digisearch/src/digisearch/web_search/ digisearch/tests/test_web_search_citation.py digisearch/tests/test_web_search_fetch.py digisearch/tests/test_web_search_service.py && ruff format --check digisearch/src/digisearch/web_search/ digisearch/tests/test_web_search_citation.py digisearch/tests/test_web_search_fetch.py digisearch/tests/test_web_search_service.py`
Expected: zero errors

- [ ] **Step 5: Verify deliverable independently**

Run: `pytest digisearch/tests/ -v`
Deliverable: Task 0 atoms importable and tested next to the landed provider
suite (R8): `Citation`/`normalize_url` shape + semantics pinned,
`fetch_markdown` decode/extract pinned, non-indexing source pin green,
`search_web` delegation pinned.

---

## Task 1: Grounding models + landed web_search adaptation seam

**Files:**

- Create: `digisearch/src/digisearch/web/__init__.py`
- Create: `digisearch/src/digisearch/web/grounding_models.py`
- Create: `digisearch/src/digisearch/web/retrieve.py`
- Create: `tests/ds/test_web_grounding_models.py`

**Interfaces:**

- Consumes: Task 0 `search_web()` + `fetch_markdown()` + landed
  `digisearch.web_search.models.WebSearchResult` (adapted ONLY in
  `retrieve.py`).
- Produces: `Confidence`, `GroundingCitation` (re-export of
  `digisearch.web_search.citation.Citation`), `FieldGrounding`,
  `StructuredSynthesis`, `EffortMode`, `WebResearchConfig`,
  `EFFORT_PRESETS`, `TurnUsage`, `TurnCost`, `WebResearchError`,
  `FetchedPage`, `live_search()`, `fetch_pages()` — used by Tasks 2–5.

- [ ] **Step 1: Write the failing test**

```python
from digisearch.web.grounding_models import (
    EffortMode,
    FieldGrounding,
    GroundingCitation,
    StructuredSynthesis,
    WebResearchConfig,
    EFFORT_PRESETS,
)

def test_effort_presets_order():
    fast = EFFORT_PRESETS[EffortMode.FAST]
    thorough = EFFORT_PRESETS[EffortMode.THOROUGH]
    assert fast.fetch_top_n <= thorough.fetch_top_n
    assert fast.cited_top_n <= thorough.cited_top_n

def test_field_grounding_requires_citation():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        FieldGrounding(field="rounds[0].company", citations=[])

def test_grounding_citation_is_landed_atom():
    from digisearch.web_search.citation import Citation
    assert GroundingCitation is Citation  # re-export, never a fork

def test_structured_synthesis_exa_shape():
    s = StructuredSynthesis(
        content={"rounds": [{"company": "Wafer"}]},
        text="Three recent Series A rounds.",
        grounding=[{
            "field": "rounds[0].company",
            "citations": [{"url": "https://a.com/1", "title": "A"}],
            "confidence": "high",
        }],
    )
    assert s.grounding[0].citations[0].url == "https://a.com/1"

def test_retrieve_seam_maps_landed_rows(monkeypatch):
    from digisearch.web import retrieve as ret
    from digisearch.web_search.models import WebSearchResponse, WebSearchResult
    fake = WebSearchResponse(
        query="q",
        provider="searxng",
        results=[WebSearchResult(url="https://a.com/1", title="A",
                                 snippet="s", score=0.9, engine="searxng")],
    )
    monkeypatch.setattr(ret, "_live", lambda q, top_n: fake)
    hits = ret.live_search("q", top_n=4)
    assert hits[0].url == "https://a.com/1"
    assert hits[0].snippet == "s"  # landed rows carry snippet, never highlights

def test_fetch_seam_returns_fetched_pages(monkeypatch):
    from digisearch.web import retrieve as ret
    from digisearch.web_search.models import WebSearchResult
    page = ret.FetchedPage(url="https://a.com/1", title="A", markdown="# body")
    monkeypatch.setattr(ret, "_fetch", lambda hits, top_n: [page])
    hits = [WebSearchResult(url="https://a.com/1", title="A", snippet="s")]
    assert ret.fetch_pages(hits, top_n=4)[0].markdown == "# body"

def test_retrieve_module_never_indexes():
    import inspect
    from digisearch.web import retrieve as ret
    assert "ingest_url" not in inspect.getsource(ret)  # it indexes (R3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ds/test_web_grounding_models.py -v`
Expected: ERROR at collection — `ModuleNotFoundError: No module named
'digisearch.web'` (the Step-1 file exists, the package does not yet). If
pytest instead reports `file or directory not found`, the Step-1 file was
not created — fix that first; it is a different failure.

- [ ] **Step 3: Write minimal implementation**

`grounding_models.py`: the models from Interfaces above, all
`extra="forbid"`; `GroundingCitation` is the landed
`digisearch.web_search.citation.Citation` re-exported (single shape
`{url,title="",excerpt=""}` — never a fork); `EFFORT_PRESETS = {FAST:
WebResearchConfig(...8/5/5...), THOROUGH: WebResearchConfig(effort=THOROUGH,
live_top_n=20, fetch_top_n=10, cited_top_n=8)}`; `WebResearchError(RuntimeError)`;
`TurnUsage`/`TurnCost` per Interfaces (`TurnCost` carries real
`provider`/`breakdown`/`note` fields — never model_extra).
`retrieve.py`: `FetchedPage` pydantic model + `live_search()`/`fetch_pages()`
that call the Task 0 atoms through two private seams `_live` / `_fetch`
(pinned by the Step-1 tests): `_live` lazy-imports
`digisearch.web_search.service.search_web` and calls it with
`WebSearchRequest(query=query, max_results=top_n)`, returning the landed
`WebSearchResponse`; `live_search` returns `resp.results` (landed
`WebSearchResult` rows, `snippet` key — never `highlights`) and raises
`WebResearchError` on failure. `_fetch` lazy-imports Task 0
`fetch_markdown(url)` per hit, drops empty markdown, and raises
`WebResearchError` on failure; it MUST NEVER call `ingest_url` (it indexes —
no-corpus-mixing rule, source-pinned by test). `web_search.models`
(pydantic-only) may import at module scope; the `service`/`fetch` imports
stay inside the seam functions so the base install imports `retrieve.py`
cleanly. `__init__.py` re-exports the public names.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ds/test_web_grounding_models.py -v`
Expected: PASS
Run: `ruff check digisearch/src/digisearch/web/ tests/ds/test_web_grounding_models.py && ruff format --check digisearch/src/digisearch/web/ tests/ds/test_web_grounding_models.py`
Expected: zero errors

- [ ] **Step 5: Verify deliverable independently**

Run: `pytest tests/ds/test_web_grounding_models.py -v`
Deliverable: grounding-model contracts + landed-surface seam importable
standalone (`python -c "from digisearch.web import grounding_models,
retrieve"` with base install only — no `digillm`/`langgraph`/digifetch import
at module scope).

---

## Task 2: Cost/latency accounting (EXA `costDollars`/`usage` mirror)

**Files:**

- Create: `digisearch/src/digisearch/web/accounting.py`
- Create: `tests/ds/test_web_accounting.py`

**Interfaces:**

- Consumes: Task 1 `TurnUsage`, `TurnCost`, `WebResearchConfig`.
- Produces: `StageTimer`, `start_clock()`, `record_stage()`,
  `finalize_usage()`, `estimate_cost()` used by Tasks 3–5.

Accounting model (OSS has no per-call dollar cost, so report honestly):
`breakdown = {"searches": <n>, "pages_fetched": <n>, "llm_calls": <n>}` plus
`total = 0.0`, `provider = "web-oss"`, and
`note = "oss-synthesis; llm spend metered in digillm telemetry, not here"`.
`total` is advisory-only: NO budget/routing gate may branch on `total`
alone — gates MUST include stage-ms and
`breakdown["llm_calls"] > 0 ⇒ consult digillm telemetry`. Stage timers
record integer ms per stage (`search_ms`, `fetch_ms`, `rerank_ms`,
`synthesis_ms`) and `total_ms`.

- [ ] **Step 1: Write the failing test**

```python
from digisearch.web.accounting import (
    estimate_cost, finalize_usage, record_stage, start_clock)

def test_stages_sum_to_total():
    t = start_clock()
    record_stage(t, "search_ms", 120)
    record_stage(t, "fetch_ms", 300)
    u = finalize_usage(t, searches=1, pages_fetched=5,
                       pages_cited=3, llm_calls=1)
    assert u.search_ms == 120
    assert u.total_ms == 420
    assert u.pages_cited == 3

def test_cost_shape_is_advisory_only():
    c = estimate_cost(searches=1, pages_fetched=5, llm_calls=1)
    assert c.total == 0.0
    assert c.provider == "web-oss"
    assert c.breakdown == {"searches": 1, "pages_fetched": 5,
                           "llm_calls": 1}
    assert "digillm" in c.note
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ds/test_web_accounting.py -v`
Expected: ERROR at collection — `ModuleNotFoundError: No module named
'digisearch.web.accounting'` (the Step-1 file exists, the module does not
yet). If pytest instead reports `file or directory not found`, the Step-1
file was not created — fix that first; it is a different failure.

- [ ] **Step 3: Write minimal implementation**

`StageTimer` dataclass `{stages: dict[str,int]}`; `start_clock()` returns one;
`record_stage(timer, name, ms)` accumulates; `finalize_usage(...)` builds
`TurnUsage` with `total_ms=sum(stages)`; `estimate_cost(...)` builds
`TurnCost(total=0.0, provider="web-oss", breakdown={...counts},
note=<real field per Interfaces>)`.
No wall-clock reads inside `finalize_usage`/`estimate_cost` (pure, testable);
callers measure with `time.perf_counter` and pass ms in.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ds/test_web_accounting.py tests/ds/test_web_grounding_models.py -v`
Expected: PASS
Run: `ruff check digisearch/src/digisearch/web/accounting.py tests/ds/test_web_accounting.py && ruff format --check digisearch/src/digisearch/web/accounting.py tests/ds/test_web_accounting.py`
Expected: zero errors

- [ ] **Step 5: Verify deliverable independently**

Run: `pytest tests/ds/test_web_accounting.py -v`
Deliverable: `TurnUsage`/`TurnCost` dicts dump to the exact EXA-mirroring
keys (`searches`, `pages_fetched`, `total_ms`; `total`, `provider`,
`breakdown`, `note`).

---

## Task 3: `grounded_answer()` — Perplexica loop with inline citations

**Files:**

- Create: `digisearch/src/digisearch/web/answer.py`
- Create: `tests/ds/test_web_answer.py`

**Interfaces:**

- Consumes: Task 1 (`live_search`, `fetch_pages`, `WebResearchConfig`,
  `EFFORT_PRESETS`, `WebResearchError`) + Task 2 accounting +
  `search/reranker.py Reranker(provider="bge")` +
  `digisearch.chunking.factory.get_document_chunker()` +
  `search/keyword.py BM25Searcher` + `digillm.client.completion`
  (lazy import, `usage_kind="web_search"`, model from
  `DIGISEARCH_SYNTHESIS_MODEL`) + `web_exa.WebSearchData` as the return
  envelope (R1: retrieval rows stay landed `WebSearchResult`).
- Produces: `grounded_answer(question, *, config)
  -> tuple[WebSearchData, TurnUsage]` used by Task 5 `node_web_aggregate`
  (markdown path).

Loop (Perplexica prompt/citation pattern, original wording):

1. `live_search(question, top_n=config.live_top_n)` → hits (landed
   `WebSearchResult` rows via Task 0 `search_web`).
2. `fetch_pages(hits, top_n=config.fetch_top_n)` → markdown pages (Task 0
   `fetch_markdown`, non-indexing — `ingest_url` is never called); empty
   markdown pages dropped; zero surviving pages → raise `WebResearchError`.
3. Chunk each page via `digisearch.chunking.factory.get_document_chunker()`
   (research flat payloads, no segment wrapper), build one `Result` per chunk
   (metadata carries `source_url`, `title`, `evidence_tier="External"`).
4. BM25 query-filter: `BM25Searcher([chunk contents]).search(Query(text))`;
   keep chunks with score > 0 (cap `cited_top_n * 4` for the rerank input).
   `rank_bm25` missing → skip filter, keep rerank (log once, never fail).
5. BGE rerank `Reranker(provider="bge").rerank(question, chunks,
   top_n=config.cited_top_n)`; rerank import failure → raise
   `WebResearchError` (cited set must be ranked, never arbitrary).
   Fail-hard placement: `_rank()` opens its BGE stage with an explicit
   pre-import guard (`importlib.util.find_spec("sentence_transformers")`
   is None → raise `WebResearchError` naming `digisearch[rerank]`) BEFORE
   touching `Reranker`, because the landed `Reranker._rerank_bge` try/excepts
   everything and falls back to original order — its fallback MUST NOT be
   reachable from this path.
6. Number surviving sources `[1..N]`; `digillm.completion(model,
   messages=[system(citation rules) + numbered sources (snippet ≤2000 chars
   each, total ≤ max_synthesis_chars) + question], usage_kind="web_search")`;
   system prompt rules: answer ONLY from numbered sources; every factual
   claim ends with `[n]`; no uncited claims. Trigger split: if the cited
   set is non-empty but cannot support an answer, return the literal
   sentence "insufficient sources" WITH the numbered source list (still
   cited, still `WebSearchData`) — this sentence path requires ≥1 cited
   page; zero cited pages is always the `WebResearchError` path.
7. Return `(WebSearchData(results=[{title,url,snippet,score,engine}...],
   output={"text": answer}, search_type=f"web-{effort}",
   cost_dollars={total: 0.0, provider: "web-oss", breakdown, note}),
   TurnUsage(...))`. Usage travels as the explicit second tuple element
   onto turn state — NEVER via model_extra (`WebSearchData` is
   `extra="ignore"` and silently drops undeclared extras).

- [ ] **Step 1: Write the failing test**

```python
def test_grounded_answer_cites_every_claim(monkeypatch):
    from digisearch.web import answer as mod
    from digisearch.web.grounding_models import WebResearchConfig
    from digisearch.web.retrieve import FetchedPage
    from digisearch.web_search.models import WebSearchResult
    from digisearch import web_exa
    monkeypatch.setattr(mod, "_live", lambda q, top_n: [
        WebSearchResult(url="https://a.com/1", title="A", snippet="s1",
                        score=0.9, engine="searxng"),
        WebSearchResult(url="https://b.com/2", title="B", snippet="s2",
                        score=0.8, engine="searxng"),
    ])
    monkeypatch.setattr(mod, "_fetch", lambda hits, top_n: [
        FetchedPage(url=h.url, title=h.title,
                    markdown=f"page body for {h.url}") for h in hits
    ])
    monkeypatch.setattr(mod, "_rank", lambda q, pages, top_n: pages[:1])
    monkeypatch.setattr(mod, "_synthesize", lambda q, pages, cfg: (
        "Wafer raised $40M [1].", {"llm_calls": 1}))
    data, usage = mod.grounded_answer("Series A AI infra rounds",
                                      config=WebResearchConfig())
    assert isinstance(data, web_exa.WebSearchData)
    assert "[1]" in str(data.output.get("text"))
    assert data.results[0]["url"] == "https://a.com/1"
    assert usage.llm_calls == 1

def test_grounded_answer_raises_on_zero_pages(monkeypatch):
    import pytest
    from digisearch.web import answer as mod
    from digisearch.web.grounding_models import WebResearchError
    monkeypatch.setattr(mod, "_live", lambda q, top_n: [])
    with pytest.raises(WebResearchError):
        mod.grounded_answer("anything")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ds/test_web_answer.py -v`
Expected: ERROR at collection — `ModuleNotFoundError: No module named
'digisearch.web.answer'` (the Step-1 file exists, the module does not
yet). If pytest instead reports `file or directory not found`, the Step-1
file was not created — fix that first; it is a different failure.

- [ ] **Step 3: Write minimal implementation**

Structure `answer.py` around four private seams (`_live`, `_fetch`,
`_rank`, `_synthesize`) so tests mock boundaries, not internals; the public
`grounded_answer()` orchestrates only. `_live`/`_fetch` delegate to Task 1
`retrieve.live_search`/`retrieve.fetch_pages`. `_rank` holds steps 3–5
(chunk → BM25 → BGE, opening the BGE stage with the `find_spec` pre-import
guard from Interfaces step 5). `_synthesize(question, pages, cfg)` holds the
lazy `digillm` import + prompt build + `completion()` call
(`usage_kind="web_search"`) and returns `(answer_text, counts)` — it does
NOT assemble the envelope; `grounded_answer()` owns `WebSearchData` assembly
(results/output/search_type/cost_dollars) plus `TurnUsage`, returning both
as a tuple. `DIGISEARCH_SYNTHESIS_MODEL` env resolves the model at call time
(empty → raise `WebResearchError` naming the env var).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ds/test_web_answer.py tests/ds/test_web_accounting.py tests/ds/test_web_grounding_models.py -v`
Expected: PASS
Run: `ruff check digisearch/src/digisearch/web/answer.py tests/ds/test_web_answer.py && ruff format --check digisearch/src/digisearch/web/answer.py tests/ds/test_web_answer.py`
Expected: zero errors

- [ ] **Step 5: Verify deliverable independently**

Run: `pytest tests/ds/test_web_answer.py -v`
Deliverable: mocked end-to-end Perplexica loop returning a
`WebSearchData` with `[n]`-cited text; fail-hard on zero pages proven.

---

## Task 4: `structured_synthesis()` + `verify_grounding()` (EXA-shaped contract)

**Files:**

- Create: `digisearch/src/digisearch/web/structured.py`
- Create: `tests/ds/test_web_structured.py`

**Interfaces:**

- Consumes: Task 1 (models, `WebResearchError`; `GroundingCitation` =
  re-exported `digisearch.web_search.citation.Citation` — single shape
  `{url,title,excerpt}`) + Task 3 retrieval (`_live`, `_fetch`, `_rank`
  reused via import from `answer.py` — no copy) +
  `digillm.client.completion(..., response_format=json_schema)` (lazy).
- Produces: `structured_synthesis(question, *, output_schema, config)
  -> tuple[WebSearchData, TurnUsage]` + `verify_grounding(content,
  grounding, *, cited_urls)` used by Task 5 (structured path).

Contract (EXA-shaped, adapted from live EXA `s4`/`g2` — required-keys
checked, NOT verbatim EXA and NOT full JSON-Schema validation):

- Request carries caller `output_schema` (JSON Schema dict, e.g.
  `{"type":"object","required":["rounds"],"properties":{"rounds":{...}}}`).
- `digillm` call uses the WRAPPER schema from the top-level Interfaces
  (`{"content": <output_schema>, "grounding": [...]}` under
  `response_format={"type":"json_schema","json_schema":`
  `{"name":"web_structured","schema":<wrapper>}}`) and instructs the model
  to return one grounding entry per leaf field of `content`, citations
  restricted to the numbered source urls (each carrying `url`, `title`,
  `excerpt`), `confidence` one of high/medium/low.
- Response parsed into `StructuredSynthesis` (citations parse as the landed
  `Citation` atom); `content` checked against
  `output_schema` REQUIRED KEYS ONLY (missing required key →
  `WebResearchError`, never a partial `content`; deeper JSON-Schema
  validation is explicitly out of scope — it would need a new dependency);
  then `verify_grounding()` applied; verified grounding serialized into
  `WebSearchData.output =
  {"content":...,"grounding":[{field,citations,confidence}...],"text":...}`.

`verify_grounding` rules (pure function — the pass the live `s4` payload
shows is necessary; stated exactly as enforced):

1. Drop entries for fields absent from `content` (dotted-path lookup).
2. Entries with zero citations pointing at `cited_urls` →
   `confidence=UNVERIFIED` (kept, flagged — never silently dropped).
3. Echo detection: leaf string value that case-insensitively contains (or is
   contained in) a sibling leaf value under the same parent object
   (e.g. `launcher == name`) → downgrade one level
   (`high→medium→low→unverified`).
4. Cited-but-irrelevant entries are NOT detected and keep their
   model-assigned confidence. Phases C/D MUST hide or explicitly flag
   UNVERIFIED-grounded fields (never render them as verified); until a
   consumer spec pins that rule, no cross-phase correctness guarantee is
   claimed.
5. Never raises on loose input; returns the verified list.

- [ ] **Step 1: Write the failing test**

```python
def test_verify_downgrades_echo_and_flags_uncited():
    from digisearch.web.structured import verify_grounding
    content = {"companies": [{"name": "SpaceX", "launcher": "SpaceX"}]}
    grounding = [
        {"field": "companies[0].name",
         "citations": [{"url": "https://a.com/1", "title": "A"}],
         "confidence": "high"},
        {"field": "companies[0].launcher",
         "citations": [{"url": "https://a.com/1", "title": "A"}],
         "confidence": "high"},
        {"field": "companies[0].vehicles",
         "citations": [{"url": "https://ghost.example/x", "title": "X"}],
         "confidence": "high"},
    ]
    out = verify_grounding(content, grounding, cited_urls={"https://a.com/1"})
    by_field = {g["field"] if isinstance(g, dict) else g.field: g for g in out}
    def conf(g):
        return g["confidence"] if isinstance(g, dict) else g.confidence.value
    assert conf(by_field["companies[0].launcher"]) == "medium"
    assert conf(by_field["companies[0].vehicles"]) == "unverified"
    assert conf(by_field["companies[0].name"]) == "high"

def test_structured_synthesis_rejects_partial_content(monkeypatch):
    import pytest
    from digisearch.web import structured as mod
    from digisearch.web.grounding_models import WebResearchError
    pages = [{"url": "https://a.com/1", "title": "A",
              "markdown": "page body"}]
    # Retrieval SUCCEEDS (non-empty cited set) so the test exercises the
    # missing-required-key path — NOT the zero-pages raise.
    monkeypatch.setattr(mod, "_retrieve_cited",
                        lambda q, cfg: (pages, {"https://a.com/1"}))
    monkeypatch.setattr(mod, "_synthesize_structured",
                        lambda q, pages, schema, cfg: (
                            {"other": []},  # missing required "rounds"
                            [{"field": "other[0]",
                              "citations": [{"url": "https://a.com/1",
                                             "title": "A", "excerpt": "e"}],
                              "confidence": "high"}],
                            "text",
                        ))
    with pytest.raises(WebResearchError):
        mod.structured_synthesis("q", output_schema={"required": ["rounds"]})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ds/test_web_structured.py -v`
Expected: ERROR at collection — `ModuleNotFoundError: No module named
'digisearch.web.structured'` (the Step-1 file exists, the module does not
yet). If pytest instead reports `file or directory not found`, the Step-1
file was not created — fix that first; it is a different failure.

- [ ] **Step 3: Write minimal implementation**

`structured.py`: `_retrieve_cited(question, config)` reusing Task 3
pipeline through `_rank` (returns `(cited_pages, cited_urls)`; zero pages →
raise); `_synthesize_structured(question, pages, schema, config)` doing the
`digillm` wrapped-schema structured call + required-keys check (missing key
→ `WebResearchError`) + `verify_grounding`, returning
`(content, verified_grounding, text)` — it does NOT assemble the envelope;
`structured_synthesis()` owns `WebSearchData` + `TurnUsage` assembly
(`output={"content","grounding","text": model text or ""}`,
`search_type=f"web-{effort}"`, Task 2 cost) and returns both as a tuple.
`verify_grounding` accepts `FieldGrounding` or plain dicts (tests use dicts)
and returns the same element type it received; citations validate against
the landed `digisearch.web_search.citation.Citation` (import from there —
never a local fork).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ds/test_web_structured.py tests/ds/test_web_answer.py tests/ds/test_web_accounting.py tests/ds/test_web_grounding_models.py -v`
Expected: PASS
Run: `ruff check digisearch/src/digisearch/web/structured.py tests/ds/test_web_structured.py && ruff format --check digisearch/src/digisearch/web/structured.py tests/ds/test_web_structured.py`
Expected: zero errors

- [ ] **Step 5: Verify deliverable independently**

Run: `pytest tests/ds/test_web_structured.py -v`
Deliverable: EXA-shaped `output.content + output.grounding` proven against
the `s4`-style echo fixture (downgraded, not echoed as `high`) and the
`g2`-style multi-field fixture (all six field entries keep cited urls).

---

## Task 5: `research_turn` web branch wiring (graph + HTTP + MCP + manifest)

**Files:**

- Modify: `digisearch/src/digisearch/agent/pipeline_models.py` (additive:
  state fields `source`, `effort`, `output_schema`, `cited_top_n`,
  `web_output`, `cost_dollars`, `usage` AND the same web fields on
  `ResearchTurnOutput` — R10)
- Create: `digisearch/src/digisearch/agent/web_branch.py`
- Modify: `digisearch/src/digisearch/agent/pipeline.py` (route `plan` →
  `web_retrieve` when `source in {"web","auto"}`; register `web_retrieve`,
  `web_aggregate` nodes; thread every new key through `_state_from_initial`
  AND `_output_from_state`)
- Modify: `digisearch/src/digisearch/server.py` (`ResearchTurnRequest`:
  `source: Literal["corpus","web","auto"] = "corpus"`, `effort`,
  `output_schema`, `cited_top_n`; response passthrough of `web_output`,
  `cost_dollars`, `usage`)
- Modify: `digisearch/src/digisearch/mcp_server.py`
  (`digisearch_research_turn(..., source="corpus", effort="fast")`)
- Modify: `digisearch/src/digisearch/orchestrator_tools.py`
  (research-delegate schema gains `source`/`effort`/`output_schema`)
- Create: `tests/ds/test_research_turn_web_branch.py`

**Interfaces:**

- Consumes: Tasks 1–4 (`grounded_answer`, `structured_synthesis`,
  accounting) + existing `node_plan`, `rag_sources_from_hits`,
  `ResearchTurnTraceStep`.
- Produces: the web research-turn capability Phases C/D build on;
  `resolve_web_config(*, effort, cited_top_n)` (R9 precedence); corpus
  path behavior unchanged (proven by existing suite).
- Opt-in contract (R5): `source` defaults to `"corpus"`; the web branch runs
  ONLY when the caller explicitly passes `source="web"` or `source="auto"`.
  This deliberately supersedes the #3859 "grounding is tool-only" policy
  ONLY for explicitly requested web turns — existing callers (and the
  digigraph delegate default) keep the tool-only posture unchanged; the
  supersession is recorded in `digisearch/ARCHITECTURE.md` in Task 6.
- Precedence (R9): when the request provides `cited_top_n`, it wins over the
  effort preset; when unset, the effort preset value is used. Both paths are
  test-pinned.
- Output declaration (R10): `ResearchTurnOutput` MUST declare every new field
  (`web_output`, `cost_dollars`, `usage`, plus `backend` already declared) —
  FastAPI `response_model` and `_output_from_state` drop undeclared keys.

Routing: `plan` keeps its validation; new `_route_after_plan` sends
`source in {"web","auto"}` to `web_retrieve`, else `retrieve` — the
`source="corpus"` default never enters the web branch (R5).
`node_web_retrieve`: validates `effort` (`fast`/`thorough`, invalid →
`error`), resolves config via `resolve_web_config(effort=..., cited_top_n=
state.cited_top_n)` (R9), runs Task 3 retrieval through `_rank` storing cited
web hits + usage in state, trace step
`web_retrieve{status:ok,total:cited}` (counts + urls only — never snippets).
`node_web_aggregate`: markdown path →
`grounded_answer`; `output_schema` set → `structured_synthesis`; rebuilds
`results` (normalized web-hit dicts with `metadata.evidence_tier =
"External"`), `rag_sources` via `rag_sources_from_hits` ONLY after the
URL-preserving mapping `_web_hit_to_rag_row()` in `web_branch.py` maps each
web hit `{url,title,snippet,score,engine}` to
`{doc_id:url, content:snippet, score, rank,
metadata:{source_url:url, title, engine, evidence_tier:"External"}}`
(routing raw web hits straight into `rag_sources_from_hits` yields
citation-free entries with no URL, because it reads
`content`/`doc_id`/`chunk_id` keys web hits lack), and
`formatted_context` as numbered `[n] url — title — snippet` lines built
directly (NOT via `format_web_results`, which never renders OSS `snippet`
keys — Title/URL-only degradation); sets `backend="web-oss"`,
`web_output`, `cost_dollars` (full `{total: 0.0, provider: "web-oss",
breakdown, note}` shape — never a bare `{"total": 0.0}`), `usage`; trace
step `web_aggregate`.
Any `WebResearchError` → `state.error` + failed trace step, END (fail-hard
pin below).

- [ ] **Step 1: Write the failing test**

```python
def test_web_branch_routes_and_labels_external(monkeypatch):
    from digisearch.agent import web_branch as mod
    from digisearch.agent.pipeline_models import ResearchTurnState
    pages = [{"url": "https://a.com/1", "title": "A",
              "snippet": "s", "score": 1.0, "engine": "searxng"}]
    monkeypatch.setattr(mod, "node_web_retrieve",
                        lambda s: {"web_hits": pages})
    monkeypatch.setattr(mod, "node_web_aggregate", lambda s: {
        "results": [{**pages[0], "metadata": {"evidence_tier": "External"}}],
        "formatted_context": "[1] https://a.com/1 — A",
        "web_output": {"text": "answer [1]"},
        "cost_dollars": {"total": 0.0, "provider": "web-oss",
                         "breakdown": {"searches": 1, "pages_fetched": 1,
                                       "llm_calls": 1},
                         "note": "oss-synthesis; llm spend metered in "
                                 "digillm telemetry, not here"},
        "usage": {"searches": 1},
    })
    state = ResearchTurnState(user_message="q", source="web", effort="fast")
    out = mod.run_web_research_turn(state.model_dump())
    assert out["backend"] == "web-oss"
    assert out["results"][0]["metadata"]["evidence_tier"] == "External"
    assert out["cost_dollars"]["provider"] == "web-oss"
    assert "llm_calls" in out["cost_dollars"]["breakdown"]

def test_web_branch_fail_hard_pin(monkeypatch):
    import pytest
    from digisearch.agent import web_branch as mod
    from digisearch.web.grounding_models import WebResearchError
    def boom(state):
        raise WebResearchError("searxng down")
    monkeypatch.setattr(mod, "node_web_retrieve", boom)
    out = mod.run_web_research_turn({"user_message": "q", "source": "web"})
    assert out["error"] is not None and "searxng down" in out["error"]

def test_source_defaults_to_corpus_and_routes():
    from digisearch.agent.pipeline import _route_after_plan
    from digisearch.agent.pipeline_models import ResearchTurnState
    assert _route_after_plan(ResearchTurnState(user_message="q")) == "retrieve"
    assert _route_after_plan(
        ResearchTurnState(user_message="q", source="web")) == "web_retrieve"
    assert _route_after_plan(
        ResearchTurnState(user_message="q", source="auto")) == "web_retrieve"

def test_cited_top_n_request_wins_over_preset():
    from digisearch.agent.web_branch import resolve_web_config
    from digisearch.web.grounding_models import EFFORT_PRESETS, EffortMode
    assert resolve_web_config(effort="fast", cited_top_n=3).cited_top_n == 3
    assert resolve_web_config(effort="fast", cited_top_n=None).cited_top_n == (
        EFFORT_PRESETS[EffortMode.FAST].cited_top_n)

def test_state_and_output_thread_web_keys():
    from digisearch.agent.pipeline import _output_from_state, _state_from_initial
    state = _state_from_initial({"user_message": "q", "source": "web",
                                 "effort": "thorough", "cited_top_n": 3})
    assert state.source == "web" and state.cited_top_n == 3
    out = _output_from_state(state.model_copy(update={
        "backend": "web-oss",
        "web_output": {"text": "answer [1]"},
        "cost_dollars": {"total": 0.0, "provider": "web-oss"},
        "usage": {"searches": 1},
    }))
    dumped = out.model_dump(mode="json")
    assert dumped["backend"] == "web-oss"
    assert dumped["web_output"] == {"text": "answer [1]"}
    assert dumped["cost_dollars"]["provider"] == "web-oss"
    assert dumped["usage"] == {"searches": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ds/test_research_turn_web_branch.py -v`
Expected: ERROR at collection — `ModuleNotFoundError: No module named
'digisearch.agent.web_branch'` (the Step-1 file exists, the module does
not yet). If pytest instead reports `file or directory not found`, the
Step-1 file was not created — fix that first; it is a different failure.

- [ ] **Step 3: Write minimal implementation**

Per file list. `web_branch.py` owns `node_web_retrieve`,
`node_web_aggregate`, `_web_hit_to_rag_row()`, `resolve_web_config()`
(R9), and `run_web_research_turn()` (the ONLY seams the Task 5 tests patch).
`pipeline.py` change is routing-only plus state/output threading: after
`node_plan`, `state.source in {"web","auto"}` →
`web_retrieve → web_aggregate → END`, else the existing chain;
`_state_from_initial` copies every new request key (`source`, `effort`,
`output_schema`, `cited_top_n`) into state and `_output_from_state` copies
every new state key (`web_output`, `cost_dollars`, `usage`) onto
`ResearchTurnOutput` — undeclared keys are silently dropped by both the
FastAPI `response_model` and `_output_from_state`, so `ResearchTurnOutput`
MUST declare each new field (R10), and `ResearchTurnState` MUST declare each
request key (R10). `server.py`/`mcp_server.py`/`orchestrator_tools.py` are
thin passthroughs (no new auth — `digisearch:query` already covers
`/v1/research_turn`; no new MCP port; MCP defers `output_schema` this phase,
R7). Keep `GET /azure_status` scoping,
`DIGISEARCH_ALLOW_STUB` test-only rule, and corpus `formatted_context`
shape untouched.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ds/test_research_turn_web_branch.py tests/ds/test_web_structured.py tests/ds/test_web_answer.py -v`
Expected: PASS
Run: `pytest tests/ -m unit -k "digisearch" -v`
Expected: PASS (corpus research-turn suite green — no regression)
Run: `ruff check digisearch/ && ruff format --check digisearch/`
Expected: zero errors

- [ ] **Step 5: Verify deliverable independently**

Run: `pytest tests/ -m unit -k "digisearch and research" -v`
Deliverable: `POST /v1/research_turn {source:"web", effort:"fast"}`
returns `backend="web-oss"` + cited `results` + `cost_dollars`/`usage`;
`{source:"corpus"}` (or omitted) byte-identical to pre-change behavior;
fail-hard pin green (error surfaced, never an uncited answer); R9
(`cited_top_n` wins) and R10 (state/output threading) pins green.

---

## Task 6: Live verification record + ARCH docs

**Files:**

- Modify: `digisearch/ARCHITECTURE.md` (web-branch section: envelope split
  (retrieval rows vs `WebSearchData` output), loop diagram, `WebSearchData`
  interchange table EXA-vs-OSS, effort presets, accounting keys,
  `DIGISEARCH_SYNTHESIS_MODEL` + `DIGISEARCH_RERANK_ENABLED` ops notes, and
  the #3859 "grounding is tool-only" supersession note for explicitly
  requested web turns, R5)
- Create: `tests/ds/test_web_eval_live.py` (research-turn eval harness:
  mocked by default, live behind `DIGISEARCH_WEB_SEARCH_LIVE=1`; asserts
  every answer line carries `[n]`, every structured field has ≥1 citation,
  `usage`/`cost_dollars` present)
- Modify: `digisearch/tests/web_search_eval_cases.py` (EXTEND the landed
  20-case module with `RESEARCH_CASES` — do not fork a parallel case module,
  R6)

**Interfaces:**

- Consumes: Tasks 0–5.
- Produces: shippable Phase B with measured fast/thorough latency + cited
  answer quality; the record Phases C/D budget against.

- [ ] **Step 1: Write the failing eval test**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]
                       / "digisearch" / "tests"))

from web_search_eval_cases import CASES, RESEARCH_CASES  # noqa: E402

def test_eval_harness_runs_offline():
    assert len(CASES) >= 20           # landed provider cases, untouched
    assert len(RESEARCH_CASES) >= 10  # Phase B research-turn additions
    assert all(c.get("must_cite", True) for c in RESEARCH_CASES)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ds/test_web_eval_live.py -v`
Expected: ERROR at collection — `ImportError: cannot import name
'RESEARCH_CASES'` (the Step-1 file exists and the landed case module is
importable, but the Phase B research cases do not exist yet; they are added
in Step 3). If pytest instead reports `file or directory not found`, the
Step-1 file was not created — fix that first; it is a different failure.

- [ ] **Step 3: Write minimal implementation**

Extend `digisearch/tests/web_search_eval_cases.py` (landed 20 search
cases/fixture stay untouched) with `RESEARCH_CASES: list[dict]` — ≥10
web-research queries across news/macro/docs/earnings, each with `must_cite`
and `must_contain` substrings; harness runs `grounded_answer` + one
`structured_synthesis` per case against mocks offline; with
`DIGISEARCH_WEB_SEARCH_LIVE=1` it hits SearXNG + `digillm` and records
p50 stage ms + citation coverage into the ARCH section. Both test roots are
in play (R8): provider-suite tests stay in `digisearch/tests/`, the
web-branch suite lives in `tests/ds/`, and both are wired via `pytest.ini`.
The live gate is SCAFFOLDING: its dollar/latency anchors are single-key,
single-day samples (see Goal), not SLO constants — Step 4 MUST re-measure
per environment and record the numbers with date/key-tier before any SLO is
written. ARCH edit per file list (no code-doc drift: every named interface
matches Tasks 0–5, including the #3859 supersession note from R5).

- [ ] **Step 4: Run all gates to verify they pass**

```bash
pytest tests/ds/test_web_grounding_models.py tests/ds/test_web_accounting.py tests/ds/test_web_answer.py tests/ds/test_web_structured.py tests/ds/test_research_turn_web_branch.py -v
pytest digisearch/tests/test_web_search_citation.py digisearch/tests/test_web_search_fetch.py digisearch/tests/test_web_search_service.py -v
pytest tests/ -m unit -k "digisearch" -v
ruff check digisearch/ && ruff format --check digisearch/
```

Expected: PASS, zero ruff errors. Then live (requires SearXNG sidecar +
`digillm` key): `DIGISEARCH_WEB_SEARCH_LIVE=1 pytest
tests/ds/test_web_eval_live.py -v` → record fast/thorough p50 +
citation coverage; confirm zero `Traceback`; confirm EXA-paid path untouched
(`POST /v1/digisearch_web_search` still EXA-gated).

- [ ] **Step 5: Verify deliverable independently**

Run: `rg -n "TBD|TODO|FIXME" docs/superpowers/specs/2026-09-14-oss-websearch-phaseB-web-research-turn.md digisearch/src/digisearch/web/ digisearch/src/digisearch/agent/web_branch.py`
Expected: zero matches. Deliverable: spec has no placeholders; ARCH section
carries measured numbers; OSS/EXA interchange proven by rendering one OSS
`WebSearchData` through `format_web_results`.

---

## Self-Review

1. **Spec coverage:** web branch Perplexica loop (T0+T3+T5) ✓; EXA-shaped
   grounding adapted (NOT verbatim — strict-`json_schema` wrapper) +
   required-keys-checked (T1+T4; full JSON-Schema validation out of scope,
   no new dep) ✓; verification pass for loose fields incl. `s4` echo case
   — uncited→UNVERIFIED flag, echo→downgrade, cited-but-irrelevant stays
   high, C/D bound to must-hide-UNVERIFIED (T4) ✓; effort modes (T1)
   + advisory-only cost/latency accounting (`{total: 0.0, provider,
   breakdown, note}`, no `total`-alone gates) with live scaffolding
   anchors (re-measured per environment, never SLOs) (T2+T6) ✓;
   `WebSearchData` interchange so EXA stays a drop-in paid alternative
   (Goal + T3–T5; envelope split R1: landed `WebSearchResult` retrieval
   rows, `WebSearchData` output envelope; `format_web_results` Title/URL-only
   degradation for OSS `snippet` keys documented, own `formatted_context`
   lines built) ✓; Task 0 landed-surface atoms (`Citation`, `fetch_markdown`,
   `search_web`) ✓; R5 (`source` defaults `corpus`, explicit `web|auto`
   only), R9 (`cited_top_n` wins), R10 (state+output declaration/threading)
   ✓.
2. **Placeholder scan:** every task names exact files, exact signatures,
   exact commands, expected outputs; Task 6 Step 5 gates zero placeholders.
3. **Landed-surface check:** every consumed symbol exists on
   `origin/module/digisearch` (`search_web` is the Task 0 addition; landed
   surfaces: `WebSearchRequest`/`WebSearchResponse`/`WebSearchResult`,
   `SearXNGWebSearchProvider.search`, `extract_markdown -> str`,
   `run_web_search`); no reference to a non-landed provider package, and the
   branch never calls the indexing `ingest_url` (R3).
4. **Type consistency:** `FieldGrounding{field,citations,min-1,confidence}` +
   `StructuredSynthesis{content,text,grounding}` used identically in
   T1/T4/T5; `GroundingCitation` is the landed
   `digisearch.web_search.citation.Citation` re-export (single shape
   `{url,title,excerpt}`, never a fork); retrieval rows are landed
   `WebSearchResult` (`snippet`, never `highlights`) — no twin model;
   `TurnUsage`/`TurnCost{total,provider,breakdown,note}` keys match T2/T5/T6;
   synthesis returns `(WebSearchData, TurnUsage)` tuples in T3–T5 (never
   model_extra); `WebResearchConfig` effort presets shared by T3–T5;
   `node_web_retrieve`/`node_web_aggregate` are the only T5 seams;
   `ResearchTurnState` additions are additive-only (corpus path untouched)
   and mirrored on `ResearchTurnOutput` (R10).
