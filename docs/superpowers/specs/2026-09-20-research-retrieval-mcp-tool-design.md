# Research Retrieval MCP Tool — Design

Date: 2026-09-20
Status: proposed (awaiting implementation)
Owners: digiquant
Related: #3780 (R2 market-data cutover), #4295 (table rename), `2026-09-09-r2-checkpoint-document-archive-design.md`, `2026-06-20-olympus-daily-thesis-design.md` §5.6/§6.1

## 1. Problem

Agents and chat surfaces cannot read the research the pipeline already produced. Today:

- The MCP tool `digiquant_query_data` is a **generic book/portfolio table reader** (`ALLOWED_READ_TABLES` = positions, nav_history, theses, thesis_vehicles, position_events, portfolio_metrics, trading_calendar). It cannot read `documents` — the published research bodies — which is walled off by a deliberate, human-gated security decision (`tests/dq/test_mcp_data_tools.py:38-46`). It also has no text/sector/subject/date-range search, no pagination, and no R2 read-through.
- A purpose-built toolkit already exists at `digiquant/src/digiquant/dashboard/research_retrieval/` (`query_research`, `fetch_prior_document`, `query_portfolio`, blinding, R2 archive read-through) but it is **in-pipeline-only**, narrow (`document_key` / `segment` / single `as_of_date` only), and registered on no MCP surface.
- The user's premise — "the research pipeline is the primary source; the model should be able to query everything stored as research and analysis, including former analysis on its own ticker and other tickers" — is not met by either tool.

## 2. Findings that shape the design

1. **`query_data` is not the research tool.** It is the portfolio/book reader; `documents` is intentionally excluded from it.
2. **`documents.content` is never archived to R2.** R2 (`digithings-archive`) holds market data, checkpoint blobs, and archived *older* `documents.payload` only. Historical research bodies are read from Supabase and stay there; R2 read-through applies to `payload` and market history.
3. **The cumulative research DB is schema-only.** `research_corpus`, `research_evidence`, `research_belief_versions`, `ticker_evidence_bundles`, `outcome_episodes`, etc. (migrations 076/088/090/093) have **no writer** — in-memory stores only. They are not a queryable source today.
4. **`run_type` exists on `documents`** (`documents` columns: `id,date,title,doc_type,phase,category,segment,sector,run_type,document_key,content,payload,workspace_id`). There is no `run_id` column and no `ticker` column on `documents`; ticker joins go through `thesis_vehicles.ticker` → `theses` → `documents`, `analyst_coverage.ticker` → `documents`, `decision_log.ticker`, and `documents` keys `deep-dives/<X>` / `custom-research/*`.
5. **R2 document read-through already exists** in the toolkit: `_hydrate_archived_row` → `checkpoint_archive.read_archived_document` → `resolve_payload` (pointer → R2 GET → sha256 → zstd).
6. **MCP exposure is one edit away.** Registering a tool in `digiquant/src/digiquant/mcp_server.py` and adding it to `READ_SCOPE_TOOLS` makes it reachable by the digichat pop-up (digichat embed → digigraph MCP enumeration, prefixed `digiquant_<tool>`) and by the read-scope public host, with no digichat code change. The public `mcp.digithings.ai` route is reserved/human-gated.

## 3. Design

### 3.1 One tool, typed datasets, clean parameters

Replace the arbitrary-`table` surface of `query_data` with a typed `dataset` enum and well-named filters. Tool name: **`query_research`** (extend the existing toolkit name so in-pipeline and MCP surfaces share one schema).

Parameters:

| Param | Type | Default | Meaning |
|---|---|---|---|
| `dataset` | enum | `documents` | `documents`, `theses`, `thesis_vehicles`, `positions`, `nav_history`, `portfolio_metrics`, `position_events`, `decision_log`, `daily_snapshots` |
| `run_type` | str | `baseline` | Which pipeline produced the research; `baseline` by default, any other run type on request |
| `run_id` | str | null | Optional precise run filter (where the dataset carries a run id: `decision_log`, telemetry) |
| `date_from` | ISO date | null | Inclusive lower bound on the dataset's date column |
| `date_to` | ISO date | null | Inclusive upper bound |
| `document_key` | str | null | Exact key (e.g. `deep-dives/AAPL`, `custom-research/…`) |
| `segment` | str | null | Alias of `document_key` (kept for backward compatibility) |
| `ticker` | str | null | Resolved via the joins in §2.4 |
| `sector` | str | null | `documents.sector` |
| `subject` | str | null | Maps to `documents` `category`/`topic_key`/title match |
| `doc_type` | str | null | `documents.doc_type` |
| `phase` | enum | `research_edit` | Retrieval/blinding phase (`RetrievalPhase`); gates what the caller may see, not a `documents` column (#4467) |
| `include_prior` | bool | `false` | Opt-in self-read of prior-day documents for continuity |
| `as_of_date` | ISO date | null | Anchor; defaults to the dispatcher's `run_date` |
| `limit` | int | 50 | Rows per page (clamped `[1,500]`) |
| `offset` | int | 0 | Pagination offset |
| `full_content` | bool | `false` | When false, `content` is truncated to a bounded preview |

Keep `fetch_prior_document` (exact single-document fetch) as-is. Fold `query_portfolio` into `dataset=positions`.

### 3.2 Storage routing (transparent to the caller)

- Live rows: Supabase (`documents` payload+content, `theses`, `thesis_vehicles`, `positions`, `nav_history`, `portfolio_metrics`, `position_events`, `decision_log`, `daily_snapshots`).
- Archived older `documents.payload`: R2 read-through via the existing `_hydrate_archived_row` / `resolve_payload` path.
- Market history (`price_history`, `price_technicals`, `macro_series_observations`): unchanged — still served only by the dedicated `get_price_technicals` / `get_macro_series` tools and the `get_*` readers; the new tool does not expose them.
- No raw-table parameter, no arbitrary column filters, no PostgREST embedding. This removes the injection surface that `query_data`'s `eq/gte/lte/in_/order` grammar carried.

### 3.3 Module layout

Extend `digiquant/src/digiquant/dashboard/research_retrieval/`:

- `queries.py` — add `search_research(client, *, run_type, run_id, date_from, date_to, document_key, segment, ticker, sector, subject, doc_type, retrieval_phase, include_prior, as_of_date, limit, offset, full_content, …) -> dict` alongside the existing narrow `query_research`, reusing `_query_documents_row`, `_hydrate_archived_row`, and the join helpers. Add pagination.
- `tools.py` — extend `RESEARCH_TOOLS` schema for `query_research`; route the new params in `build_research_tool_dispatcher`.
- `blinding.py` — keep the phase-scoped category gate; add the `include_prior` path through the same gate so a phase cannot read what it is not allowed to see.

### 3.4 In-pipeline wiring

`build_grounding` (`research/phases/_node_factory.py:230-257`) already attaches `RESEARCH_TOOLS` for H1–H7/H6. Extend attachment to:

- `build_segment_node` (`_node_factory.py:954`) so research segments can read prior research (`include_prior`).
- `phase7d_pm._pm_tools` (`phase7d_pm.py:48-54`) so the PM can read analysis/portfolio research.

Agents get the tool; `include_prior` stays opt-in per call.

### 3.5 MCP exposure

In `digiquant/src/digiquant/mcp_server.py`:

- Register `digiquant_query_research` via `@_maybe_tool(...)` inside `create_mcp_server`.
- Add it to `READ_SCOPE_TOOLS` so the hosted read-scope container (`DIGIQUANT_MCP_SCOPE=read`) exposes it to the pop-up chat and public MCP.
- Remove the `digiquant_query_data` registration (superseded).

This reaches the pop-up chat automatically through digichat's operator MCP row → digigraph MCP enumeration. No digichat code change is required.

### 3.6 Removing `query_data`

Refactor `query_data` into the new tool and remove the old surface:

- Delete `query_data` from `DATA_TOOLS` (`research/data/tools.py`) and its dispatcher branch.
- Remove `query_data` from `queries.py` public readers and the `digiquant_query_data` MCP registration.
- Keep `ALLOWED_READ_TABLES` only if a non-`query_data` reader still needs it; otherwise retire it with the tool. Book tables are now reached through typed `dataset` values on `query_research`.
- Update `ARCHITECTURE.md` (the "all six data tools" note is stale) and the tests listed in §4.

## 4. Tests

- Extend `tests/dq/dashboard/test_research_retrieval.py` with cases for each new filter, date-range, pagination, `include_prior`, `full_content` truncation, and R2 payload read-through.
- Add an MCP registration test asserting `digiquant_query_research` is present and `digiquant_query_data` is gone.
- Update `tests/dq/research/data/test_tools.py`, `test_queries_derived.py`, `test_mcp_data_tools.py`, `test_market_data_parity.py` for the removed `query_data`.
- Assert market-history tables remain unreachable through the new tool.

## 5. Human gate

The new tool reads `documents` — the very surface a prior human-gated decision deliberately excluded from `query_data`. This change therefore **requires human review** before merge, and must document the reversal of that gate explicitly in the PR.

## 6. Out of scope

- Writing the cumulative research DB (`research_corpus`/evidence/outcome tables) — no writer exists; separate effort.
- Archiving `documents.content` to R2 — content stays in Supabase.
- Semantic/full-text search via digisearch (`research_ingest.py` has no production caller).
