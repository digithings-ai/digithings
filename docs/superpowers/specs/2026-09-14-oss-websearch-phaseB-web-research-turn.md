# OSS Web Search Phase B — Web Research Turn + Cited Answers (Implementation Spec)

**Status:** spec only — research + write, no implementation in this phase.
**Scope:** Phase B only. Phase A (SearXNGBackend live query + URL ingest) and
Phases C/D (pipeline consumers) are out of scope except as declared contracts.

## Consumes / Produces

- **CONSUMES (Phase A contracts — planned, not yet in tree):**
  `digisearch.web_providers.searxng.SearXNGBackend.query(query, *,
  num_results=8, include_domains=None, exclude_domains=None, category=None,
  timeout_s=None) -> WebSearchData` (the `digisearch.web_exa.WebSearchData`
  envelope: `{results, output, search_type, cost_dollars}`) /
  `digisearch.pipeline.url_ingest.ingest_url(url, ...) -> str` (page markdown
  via the Phase A extractor) /
  `extract_markdown(html, url) -> tuple[str, str]` returning
  `(markdown, extractor_name)` (Crawl4AI default per Phase A canonical
  contract). Shapes per Phase A spec
  `docs/superpowers/specs/2026-09-14-oss-websearch-phaseA-url-ingest.md`.
  Phase B MUST NOT re-implement these; it adapts them behind a narrow seam
  (Task 1: `digisearch.web.retrieve`, the ONLY place that imports
  `digisearch.web_providers.*`) so a Phase A shape change touches exactly
  one file. Direct import within `digisearch`; HTTP only at
  process/component boundaries (digigraph, digichat, digiclaw call
  `POST /v1/research_turn` / `POST /v1/orchestrator_invoke` with service JWT).
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

1. Live query via Phase A `SearXNGBackend.query()` in
   `digisearch.web_providers.searxng` (returns `WebSearchData` hits).
2. Fetch top-N pages via Phase A `ingest_url()` (markdown + extractor name).
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

- `2026-09-10-web-search-mcp-tool.md` — Phase A owner of
  `digisearch.web_providers` (SearXNG backend, URL ingest, extractor).
  Phase B consumes it, never forks it; the single adaptation seam is Task 1
  (`digisearch.web.retrieve`, importing `digisearch.web_providers.*` only).
- `2026-09-11-web-search-default-on-tool-only.md` — pipeline is tool-only +
  fail-hard (any web-dependency failure raises `WebResearchError`,
  surfaced as `error` on the turn state, never a silent fallback or an
  uncited synthesis).
  Phase B web branch follows the same rule: any web-dependency failure raises
  (surfaced as `error` on the turn state, aborting the branch), never an
  uncited synthesis.
- `2026-09-12-web-search-followups.md` — fail-closed catch behavior, public
  wrapper naming, docs consistency. Phase B keeps fail-closed everywhere and
  pins the fail-hard shape in a test (Task 5).

## Architecture

```
POST /v1/research_turn {user_message, source: "corpus"|"web", effort, ...}
  │  source="corpus" (default) → existing plan → retrieve → aggregate (unchanged)
  │  source="web" (explicit opt-in) → plan → web_retrieve → web_aggregate
  ▼
web_retrieve:
  SearXNGBackend.query (Phase A `digisearch.web_providers.searxng`, live query)
    → fetch top-N pages (Phase A ingest_url → markdown; extractor returns
      (markdown, extractor_name), Crawl4AI default)
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

- **No corpus mixing:** web hits never enter `SearchResponse` / owned indexes.
  `backend="web-oss"` on the turn output; `evidence_tier="External"` on every
  web `rag_sources` entry (matches the 09-10 External-tier rule).
- **Opt-in only:** `source="web"` is explicit per request; default stays
  corpus-only. This preserves the #3420 invariant and is orthogonal to the
  09-11 chat-toggle defaults (those control UI prefs, not the
  `research_turn` default).
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
`BM25Searcher` import guard, `httpx` only for any new transport (none
expected — Phase A owns fetch), ruff line-length 100.

## File Structure

Exact paths (all under repo root; `digisearch/` prefix = `digisearch/`):

| Path | Action | Contents |
|------|--------|----------|
| `digisearch/src/digisearch/web/__init__.py` | Create | Lazy exports: `grounded_answer`, `structured_synthesis`, `verify_grounding`, grounding models, `WebResearchConfig`, accounting helpers |
| `digisearch/src/digisearch/web/grounding_models.py` | Create | `GroundingCitation{url,title,excerpt}`, `FieldGrounding{field,citations,min 1,confidence}`, `StructuredSynthesis{content:dict,text:str,grounding:list}`, `Confidence(str Enum: high,medium,low,unverified)`, `EffortMode(str Enum: fast,thorough)`, `WebResearchConfig`, `TurnUsage`, `TurnCost{total,provider,breakdown,note}` |
| `digisearch/src/digisearch/web/accounting.py` | Create | `StageTimer` helpers: `start_clock()`, `record_stage()`, `finalize_usage()`, `estimate_cost()` — pure functions over a small `StageTimer` dataclass (no wall-clock in return values except measured ms) |
| `digisearch/src/digisearch/web/answer.py` | Create | `grounded_answer()` (Perplexica loop, markdown + `[n]` citations) |
| `digisearch/src/digisearch/web/structured.py` | Create | `structured_synthesis()` + `verify_grounding()` (EXA-shaped contract + verification pass) |
| `digisearch/src/digisearch/web/retrieve.py` | Create | **Sole Phase A adaptation seam:** `live_search()` + `fetch_pages()` wrappers mapping Phase A `WebSearchData` results / `ingest_url` markdown pages to `web.retrieve.WebHit`; every other Phase B file imports Phase A only through here (imports `digisearch.web_providers.*`, never `digisearch.web_search.*` — that module does not exist) |
| `digisearch/src/digisearch/agent/pipeline_models.py` | Modify | Additive-only fields on `ResearchTurnState`/`ResearchTurnOutput`/`ResearchTurnRequest` (web branch slots; corpus fields untouched) |
| `digisearch/src/digisearch/agent/web_branch.py` | Create | `node_web_retrieve`, `node_web_aggregate`, `route_after_plan` extension; `run_web_research_turn()` helper |
| `digisearch/src/digisearch/agent/pipeline.py` | Modify | Wire web nodes + routing only; existing nodes byte-identical behavior |
| `digisearch/src/digisearch/server.py` | Modify | `ResearchTurnRequest` gains `source`, `effort`, `output_schema`, `cited_top_n`; response carries `WebSearchData`-compatible `output`/`cost_dollars`/`usage` |
| `digisearch/src/digisearch/mcp_server.py` | Modify | `digisearch_research_turn` gains `source`/`effort` passthrough |
| `digisearch/src/digisearch/orchestrator_tools.py` | Modify | Research-delegate tool schema gains `source`/`effort` (+ `output_schema` passthrough) |
| `digisearch/ARCHITECTURE.md` | Modify | Web-branch section (Task 6 only) |
| `tests/ds/test_web_grounding_models.py` | Create | Task 1 tests |
| `tests/ds/test_web_accounting.py` | Create | Task 2 tests |
| `tests/ds/test_web_answer.py` | Create | Task 3 tests (all external boundaries mocked) |
| `tests/ds/test_web_structured.py` | Create | Task 4 tests (incl. echo-fixture from `s4` + `g2` shapes) |
| `tests/ds/test_research_turn_web_branch.py` | Create | Task 5 tests (graph routing, fail-hard pin, HTTP/MCP shape) |

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
# digisearch.web.grounding_models
class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNVERIFIED = "unverified"

class GroundingCitation(BaseModel):  # extra="forbid"
    url: str
    title: str = ""
    excerpt: str = ""  # shared Phase A Citation atom {url,title,excerpt};
                        # carries the supporting snippet so B-grounded fields
                        # feed Phase D admissibility without lossy translation

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
    live_top_n: int = 8       # SearXNG hits requested (fast)
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
# digillm synthesis with inline [n] citations. Returns the WebSearchData
# payload AND the TurnUsage (explicit tuple — WebSearchData is
# extra="ignore" and drops extras, so usage MUST NOT ride model_extra).
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

# digisearch.web.retrieve (sole Phase A seam — the ONLY place importing
# digisearch.web_providers.*)
def live_search(query: str, *, top_n: int) -> list[WebHit]: ...
def fetch_pages(hits: list[WebHit], *, top_n: int) -> list[FetchedPage]: ...
# WebHit{url,title,snippet,score,engine}; FetchedPage{url,title,markdown}.
# live_search calls SearXNGBackend.query() and maps WebSearchData.results
# rows (url/title/highlights-snippet/engine) to WebHit. fetch_pages calls
# ingest_url() per hit and takes the markdown half of the
# (markdown, extractor_name) extractor tuple.
```

```python
# digisearch.agent.web_branch
def node_web_retrieve(state: ResearchTurnState) -> dict[str, Any]: ...
def node_web_aggregate(state: ResearchTurnState) -> dict[str, Any]: ...
def run_web_research_turn(initial: dict[str, Any]) -> dict[str, Any]: ...
# State additions (pipeline_models, additive only):
#   source: str = "corpus"            # "corpus" | "web"
#   effort: str = "fast"              # "fast" | "thorough"
#   output_schema: dict | None = None # structured path when set
#   web_output: dict | None = None    # WebSearchData.output mirror
#   cost_dollars: dict | None = None  # TurnCost dump
#   usage: dict | None = None         # TurnUsage dump
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
- Access pattern: direct import within `digisearch` (`web_providers.*`
  only via `web/retrieve.py`); HTTP only at process/component boundaries.
- Extractor default is Crawl4AI per the Phase A canonical contract
  (`-> tuple[str, str]`); no trafilatura/readability fallback chain in
  Phase B — `fetch_pages` takes the markdown half of the tuple at the seam.

---

## Task 1: Grounding models + Phase A adaptation seam

**Files:**

- Create: `digisearch/src/digisearch/web/__init__.py`
- Create: `digisearch/src/digisearch/web/grounding_models.py`
- Create: `digisearch/src/digisearch/web/retrieve.py`
- Create: `tests/ds/test_web_grounding_models.py`

**Interfaces:**

- Consumes: Phase A `SearXNGBackend.query()` + `ingest_url()` +
  `extract_markdown() -> tuple[str, str]` (adapted ONLY in `retrieve.py`).
- Produces: `Confidence`, `GroundingCitation`, `FieldGrounding`,
  `StructuredSynthesis`, `EffortMode`, `WebResearchConfig`,
  `EFFORT_PRESETS`, `TurnUsage`, `TurnCost`, `WebResearchError`,
  `WebHit`, `FetchedPage`, `live_search()`, `fetch_pages()` — used by
  Tasks 2–5.

- [ ] **Step 1: Write the failing test**

```python
from digisearch.web.grounding_models import (
    EffortMode,
    FieldGrounding,
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

def test_retrieve_seam_maps_phase_a(monkeypatch):
    from digisearch.web import retrieve as ret
    from digisearch.web_exa import WebSearchData
    fake = WebSearchData(
        search_type="web-fast",
        results=[{"url": "https://a.com/1", "title": "A",
                  "highlights": ["s"], "engine": "x"}],
        cost_dollars={"total": 0.0, "provider": "searxng",
                      "breakdown": {}, "note": "n"},
    )
    monkeypatch.setattr(ret, "_phase_a_query", lambda q, top_n: fake)
    hits = ret.live_search("q", top_n=4)
    assert hits[0].url == "https://a.com/1"

def test_grounding_citation_carries_excerpt():
    from digisearch.web.grounding_models import GroundingCitation
    c = GroundingCitation(url="https://a.com/1", title="A",
                          excerpt="supporting snippet")
    assert c.excerpt == "supporting snippet"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ds/test_web_grounding_models.py -v`
Expected: ERROR at collection — `ModuleNotFoundError: No module named
'digisearch.web'` (the Step-1 file exists, the package does not yet). If
pytest instead reports `file or directory not found`, the Step-1 file was
not created — fix that first; it is a different failure.

- [ ] **Step 3: Write minimal implementation**

`grounding_models.py`: the dataclasses from Interfaces above, all
`extra="forbid"`; `EFFORT_PRESETS = {FAST: WebResearchConfig(...8/5/5...),
THOROUGH: WebResearchConfig(effort=THOROUGH, live_top_n=20, fetch_top_n=10,
cited_top_n=8)}`; `WebResearchError(RuntimeError)`;
`TurnUsage`/`TurnCost` per Interfaces (`TurnCost` carries real
`provider`/`breakdown`/`note` fields — never model_extra).
`retrieve.py`: `WebHit`/`FetchedPage`
pydantic models + `live_search()`/`fetch_pages()` that call Phase A through
two private helpers `_phase_a_query` / `_phase_a_fetch` (the ONLY places
that import `digisearch.web_providers.*`: `SearXNGBackend.query()` and
`ingest_url()`; the extractor half of the `(markdown, extractor_name)`
tuple is unwrapped here), mapping to `WebHit`/`FetchedPage`
and raising `WebResearchError` on failure. `__init__.py` re-exports the
public names.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ds/test_web_grounding_models.py -v`
Expected: PASS
Run: `ruff check digisearch/src/digisearch/web/ tests/ds/test_web_grounding_models.py && ruff format --check digisearch/src/digisearch/web/ tests/ds/test_web_grounding_models.py`
Expected: zero errors

- [ ] **Step 5: Verify deliverable independently**

Run: `pytest tests/ds/test_web_grounding_models.py -v`
Deliverable: grounding-model contracts + Phase A seam importable standalone
(`python -c "from digisearch.web import grounding_models, retrieve"` with
base install only — no `digillm`/`langgraph` import at module scope).

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
  `search/keyword.py BM25Searcher` + `digillm.client.completion`
  (lazy import) + `web_exa.WebSearchData` as the return envelope.
- Produces: `grounded_answer(question, *, config)
  -> tuple[WebSearchData, TurnUsage]` used by Task 5 `node_web_aggregate`
  (markdown path).

Loop (Perplexica prompt/citation pattern, original wording):

1. `live_search(question, top_n=config.live_top_n)` → hits.
2. `fetch_pages(hits, top_n=config.fetch_top_n)` → markdown pages; empty
   markdown pages dropped; zero surviving pages → raise `WebResearchError`.
3. Chunk each page via `get_document_chunker()` (research flat payloads, no
   segment wrapper), build one `Result` per chunk (metadata carries
   `source_url`, `title`, `evidence_tier="External"`).
4. BM25 query-filter: `BM25Searcher([chunk contents]).search(Query(text))`;
   keep chunks with score > 0 (cap `cited_top_n * 4` for the rerank input).
   `rank_bm25` missing → skip filter, keep rerank (log once, never fail).
5. BGE rerank `Reranker(provider="bge").rerank(question, chunks,
   top_n=config.cited_top_n)`; rerank import failure → raise
   `WebResearchError` (cited set must be ranked, never arbitrary).
   Fail-hard placement: `_rank()` opens its BGE stage with an explicit
   pre-import guard (`importlib.util.find_spec("sentence_transformers")`
   is None → raise `WebResearchError` naming `digisearch[rerank]`) BEFORE
   touching `Reranker`, because `Reranker._rerank_bge` try/excepts everything
   and falls back to original order — its fallback MUST NOT be reachable
   from this path.
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
    from digisearch import web_exa
    monkeypatch.setattr(mod, "_live", lambda q, top_n: [
        {"url": "https://a.com/1", "title": "A", "snippet": "s1",
         "score": 0.9, "engine": "searxng"},
        {"url": "https://b.com/2", "title": "B", "snippet": "s2",
         "score": 0.8, "engine": "searxng"},
    ])
    monkeypatch.setattr(mod, "_fetch", lambda hits, top_n: [
        {"url": h["url"], "title": h["title"],
         "markdown": f"page body for {h['url']}"} for h in hits
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
`grounded_answer()` orchestrates only. `_rank` holds steps 3–5 (chunk →
BM25 → BGE, opening the BGE stage with the `find_spec` pre-import guard
from Interfaces step 5). `_synthesize(question, pages, cfg)` holds the lazy
`digillm` import + prompt build + `completion()` call and returns
`(answer_text, counts)` — it does NOT assemble the envelope;
`grounded_answer()` owns `WebSearchData` assembly (results/output/
search_type/cost_dollars) plus `TurnUsage`, returning both as a tuple.
`DIGISEARCH_SYNTHESIS_MODEL` env resolves the model at call time (empty →
raise `WebResearchError` naming the env var).

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

- Consumes: Task 1 (models, `WebResearchError`) + Task 3 retrieval
  (`_live`, `_fetch`, `_rank` reused via import from `answer.py` — no copy)
  + `digillm.client.completion(..., response_format=json_schema)` (lazy).
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
- Response parsed into `StructuredSynthesis`; `content` checked against
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
and returns the same element type it received.

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
  `source`, `effort`, `output_schema`, `web_output`, `cost_dollars`, `usage`)
- Create: `digisearch/src/digisearch/agent/web_branch.py`
- Modify: `digisearch/src/digisearch/agent/pipeline.py` (route `plan` →
  `web_retrieve` when `source == "web"`; register `web_retrieve`,
  `web_aggregate` nodes)
- Modify: `digisearch/src/digisearch/server.py` (`ResearchTurnRequest`:
  `source: Literal["corpus","web"] = "corpus"`, `effort`, `output_schema`,
  `cited_top_n`; `ResearchTurnOutput` passthrough of `web_output`,
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
- Produces: the web research-turn capability Phases C/D build on; corpus
  path behavior unchanged (proven by existing suite).

Routing: `plan` keeps its validation; new `_route_after_plan` sends
`source == "web"` to `web_retrieve`, else `retrieve`.
`node_web_retrieve`: validates `effort` (`fast`/`thorough`, invalid →
`error`), runs Task 3 retrieval through `_rank` storing cited web hits +
usage in state, trace step `web_retrieve{status:ok,total:cited}` (counts +
urls only — never snippets). `node_web_aggregate`: markdown path →
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ds/test_research_turn_web_branch.py -v`
Expected: ERROR at collection — `ModuleNotFoundError: No module named
'digisearch.agent.web_branch'` (the Step-1 file exists, the module does
not yet). If pytest instead reports `file or directory not found`, the
Step-1 file was not created — fix that first; it is a different failure.

- [ ] **Step 3: Write minimal implementation**

Per file list. `web_branch.py` owns `node_web_retrieve`,
`node_web_aggregate`, `_web_hit_to_rag_row()`, and
`run_web_research_turn()` (the ONLY seams the Task 5 tests patch).
`pipeline.py` change is routing-only: after `node_plan`,
`state.source == "web"` → `web_retrieve → web_aggregate → END`, else the
existing chain. `server.py`/`mcp_server.py`/`orchestrator_tools.py` are
thin passthroughs (no new auth — `digisearch:query` already covers
`/v1/research_turn`; no new MCP port). Keep `GET /azure_status` scoping,
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
`{source:"corpus"}` byte-identical to pre-change behavior; fail-hard pin
green (error surfaced, never an uncited answer).

---

## Task 6: Live verification record + ARCH docs

**Files:**

- Modify: `digisearch/ARCHITECTURE.md` (web-branch section: loop diagram,
  `WebSearchData` interchange table EXA-vs-OSS, effort presets, accounting
  keys, `DIGISEARCH_SYNTHESIS_MODEL` + `DIGISEARCH_RERANK_ENABLED` ops notes)
- Create: `tests/ds/test_web_eval_live.py` (10-query harness:
  mocked by default, live behind `DIGISEARCH_WEB_LIVE=1`; asserts every
  answer line carries `[n]`, every structured field has ≥1 citation,
  `usage`/`cost_dollars` present)

**Interfaces:**

- Consumes: Tasks 1–5.
- Produces: shippable Phase B with measured fast/thorough latency + cited
  answer quality; the record Phases C/D budget against.

- [ ] **Step 1: Write the failing eval test**

```python
def test_eval_harness_runs_offline():
    from tests.ds.web_eval_cases import CASES
    assert len(CASES) >= 10
    assert all(c.get("must_cite", True) for c in CASES)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/ds/test_web_eval_live.py -v`
Expected: ERROR at collection — `ModuleNotFoundError: No module named
'tests.ds.web_eval_cases'` (the Step-1 file exists, `web_eval_cases.py`
does not yet — it is created in Step 3). If pytest instead reports `file
or directory not found`, the Step-1 file was not created — fix that
first; it is a different failure.

- [ ] **Step 3: Write minimal implementation**

Create `tests/ds/web_eval_cases.py` (10 queries across
news/macro/docs/earnings, each with `must_contain` substrings); harness runs
`grounded_answer` + one `structured_synthesis` per case against mocks
offline; with `DIGISEARCH_WEB_LIVE=1` it hits SearXNG + `digillm` and records
p50 stage ms + citation coverage into the ARCH section. The live gate is
SCAFFOLDING: its dollar/latency anchors are single-key, single-day samples
(see Goal), not SLO constants — Step 4 MUST re-measure per environment and
record the numbers with date/key-tier before any SLO is written. ARCH edit
per file list (no code-doc drift: every named interface matches Tasks 1–5).

- [ ] **Step 4: Run all gates to verify they pass**

```bash
pytest tests/ds/test_web_grounding_models.py tests/ds/test_web_accounting.py tests/ds/test_web_answer.py tests/ds/test_web_structured.py tests/ds/test_research_turn_web_branch.py -v
pytest tests/ -m unit -k "digisearch" -v
ruff check digisearch/ && ruff format --check digisearch/
```

Expected: PASS, zero ruff errors. Then live (requires SearXNG sidecar +
`digillm` key): `DIGISEARCH_WEB_LIVE=1 pytest
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

1. **Spec coverage:** web branch Perplexica loop (T3+T5) ✓; EXA-shaped
   grounding adapted (NOT verbatim — strict-`json_schema` wrapper) +
   required-keys-checked (T1+T4; full JSON-Schema validation out of scope,
   no new dep) ✓; verification pass for loose fields incl. `s4` echo case
   — uncited→UNVERIFIED flag, echo→downgrade, cited-but-irrelevant stays
   high, C/D bound to must-hide-UNVERIFIED (T4) ✓; effort modes (T1)
   + advisory-only cost/latency accounting (`{total: 0.0, provider,
   breakdown, note}`, no `total`-alone gates) with live scaffolding
   anchors (re-measured per environment, never SLOs) (T2+T6) ✓;
   `WebSearchData` interchange so EXA stays a drop-in paid alternative
   (Goal + T3–T5; `format_web_results` Title/URL-only degradation for OSS
   `snippet` keys documented, own `formatted_context` lines built) ✓.
2. **Placeholder scan:** every task names exact files, exact signatures,
   exact commands, expected outputs; Task 6 Step 5 gates zero placeholders.
3. **Type consistency:** `FieldGrounding{field,citations,min-1,confidence}` +
   `StructuredSynthesis{content,text,grounding}` used identically in
   T1/T4/T5; `GroundingCitation` carries `{url,title,excerpt}` (Phase A
   atom) everywhere; `TurnUsage`/`TurnCost{total,provider,breakdown,note}`
   keys match T2/T5/T6; synthesis returns `(WebSearchData, TurnUsage)`
   tuples in T3–T5 (never model_extra); `WebResearchConfig` effort presets
   shared by T3–T5; `node_web_retrieve`/`node_web_aggregate` are the only
   T5 seams; `ResearchTurnState` additions are additive-only (corpus path
   untouched).
