# Atlas Data Wiring — Design Spec

*Date: 2026-06-08 · Issue: #566 (relates #565) · Author: cutover follow-up*

## Problem

After the xAI/Grok cutover (#627/#629/#635/#636/#637), the Atlas+Hermes pipeline runs
green end-to-end and publishes — but **every research segment reports "insufficient
data."** Root cause (documented on #566): the phases never receive market-data *values*
and cannot fetch any.

- `preflight._data_layer_snapshot()` builds `state.data_layer` as a **freshness probe
  only** (latest dates + counts + `fallback_used`), and `_node_factory._shared_context()`
  injects exactly that metadata into every phase. The actual technicals / macro / price
  values are never passed.
- `research_agent.run_research_agent()` calls the LLM with a single structured-output
  request **and no tools**, so the model cannot fetch anything itself.

Verified: with `price_history`/`macro_series`/`price_technicals` all fresh through
2026-06-08, a real Grok baseline still produced `regime: "Insufficient Data"`, 0 findings
across all 27 segments.

## Decision: unified tool-based grounding

Rather than pre-loading values into `phase_inputs`, **equip the research agent with tools
and let it ground itself**, driven by the phase prompts. Two tools:

1. **Grok Live Search (web)** — xAI's built-in live search, enabled per call, scoped to a
   **curated domain allowlist** so the day-to-day search flow is consistent. Covers the
   soft / non-resident signals (news, sentiment, CTA positioning, options flow,
   politician trades, institutional flows/13F color, international-M2 freshness).
2. **DigiQuant data tool (MCP + in-process)** — exposes the structured price/technicals
   and macro series **we already maintain in Supabase** as callable tools, so the agent
   queries real values on demand. Covers the quantitative core (macro, equities, sectors,
   asset classes, per-ticker analysts).

The phase **prompts** instruct the agent to use these tools to ground every claim on real
data + cite sources. This is the #565 "MCP data-source expansion" direction, realized for
our own data, and honors the repo's MCP-first principle.

**No new ingestion pipelines** — the data tool reads the existing tables; soft signals
come from Live Search. Deep historical ingestion of any soft series (COT, 13F, options,
politician trades) stays a #565 follow-up.

## The load-bearing change (and its resolution)

Function-calling tools and a strict `response_format=json_schema` are **mutually exclusive
in a single completion** (the existing `chat_completion` enforces this). So the research
agent moves from *single structured call* to **tool-loop → validate**:

- Run `chat_completion_with_tools(...)` (the existing tool loop) with the data tool +
  Live Search enabled; the model calls tools to gather grounding, then emits the final
  JSON object as text.
- `run_research_agent` validates that final text against the Pydantic `output_model` using
  its **existing `json.loads` + `model_validate` retry loop** (re-prompts on invalid
  JSON). The structured-output contract is preserved by prompt + validation rather than by
  `response_format`.

Grok Live Search is **orthogonal** to function-calling (it's server-side augmentation via
`search_parameters`, not a function tool), so it coexists with the tool loop.

## Components

### A. DigiQuant data tools (Supabase → MCP + in-process ToolDefinition)
- Shared query functions (`olympus/atlas/data/queries.py`): `get_price_technicals(ticker,
  lookback)`, `get_macro_series(series_ids, lookback)` (and `get_prices` if needed) —
  read the existing `price_technicals` / `macro_series_observations` tables, return
  compact JSON (latest + short window; selected indicator columns, not all 30+).
- **MCP exposure:** register them on the existing `digiquant/src/digiquant/mcp_server.py`
  (`FastMCP("DigiQuant")`) as `digiquant_get_price_technicals` / `digiquant_get_macro_series`
  — discoverable, MCP-first.
- **In-process exposure:** wrap the same functions as `ToolDefinition`s + an `execute_tool`
  dispatcher for the research agent's loop (the pattern the digigraph agent runners
  already use). One implementation, two surfaces.

### B. Grok Live Search enablement
- `digigraph/llm.py`: `chat_completion` and `chat_completion_with_tools` gain an optional
  `search_parameters: dict | None`, forwarded to the OpenAI client via
  `extra_body={"search_parameters": …}` — **xAI models only** (no-op + debug log
  otherwise; the local LM-Studio path is unaffected).
- A checked-in **domain allowlist** (`olympus/atlas/config/search_domains.yaml`) maps to
  xAI `sources[].allowed_websites` (e.g. reuters.com, apnews.com, sec.gov,
  federalreserve.gov, cftc.gov, treasury.gov, finance.yahoo.com, capitoltrades.com, …).
  `search_parameters` = `{mode:"on", sources:[{type:"web",allowed_websites:[…]},
  {type:"news"},{type:"x"}], from_date:<run_date-N>, return_citations:true,
  max_search_results:<cap>}`.

### C. `run_research_agent` → tool-enabled
- Switch the LLM call to `chat_completion_with_tools` with `tools=[data tools]`,
  `execute_tool=<dispatcher>`, and `search_parameters` when the phase enables search.
- Keep the existing validate-and-retry to coerce the final text to `output_model`.
- A per-phase `inputs_builder` still supplies the scope/segment context (which ticker,
  which series, upstream phase outputs); the agent then pulls the live values via tools.

### D. Prompts / skills
- `ANALYST_SYSTEM` updated: "Use the DigiQuant data tools for prices/technicals/macro;
  use web search for news/sentiment/positioning/flows. Ground every quantitative claim on
  a tool result. Cite sources in the `sources` field. If a tool returns nothing, say so."
- Per-phase SKILL.md updated to name the specific signals each phase should fetch.

## Data flow

```
preflight (freshness probe kept; no pre-loaded values)
  ↓ phase node: inputs_builder → scope/segment context in phase_inputs
run_research_agent → chat_completion_with_tools(tools=[data tools], search_parameters=…)
  ├─ model calls digiquant_get_price_technicals / get_macro_series → real values
  ├─ model uses Grok Live Search (curated domains) → news/sentiment/flows + citations
  └─ model emits final JSON → validate against output_model (retry on invalid)
  ↓ existing publish path (documents + daily_snapshot) — unchanged
```

## Error handling / freshness / cost

- Tool failure (Supabase read error, search timeout): the dispatcher returns an error
  string the model can react to; the run fails soft (phase returns empty findings) rather
  than crashing — matches today's behaviour.
- Stale Supabase series: the data tool returns the latest available + its date; the model
  notes staleness. (Freshness probe stays for triage.)
- Cost/latency: Live Search is billed per source and tool loops add round-trips — cap
  `max_search_results` and `max_tool_rounds`; gate Live Search to phases that need it
  (soft + macro fallback), data-tool to all research phases.
- **Local e2e:** if the local model (LM-Studio gemma) can't tool-call, the loop degrades
  to a tool-less answer and validate-retry still yields (thin) structured output — the
  local plumbing test still completes; substance is validated on a real Grok run.

## Testing

- Unit: data query functions (shape, window, staleness) against a fixture client.
- Unit: `chat_completion_with_tools` forwards `search_parameters` via `extra_body` only for
  xAI models; the `execute_tool` dispatcher routes to the right query fn.
- Unit: MCP tool registration (the two new tools resolve + return JSON).
- Phase test (mocked tool loop): assert the agent calls the data tool and the final output
  validates against the schema. Live search + tools mocked in CI.

## Out of scope (follow-ups)

- Historical ingestion to Supabase for COT/13F/options/politician/flows/intl-M2 (#565),
  added behind the same data-tool surface if deep history is needed.
- Cache persistence for the prices job (#465/#563); migration squash-to-baseline (#524).

## Risks / assumptions

- **Verified (xAI docs, 2026-06):** Live Search is API-available with `sources`
  (incl. `allowed_websites`), `from_date`/`to_date`, `return_citations`. First plan step:
  confirm `search_parameters` rides our OpenAI-compatible client via `extra_body`, and that
  it can be combined with function-tools in the same request (else: run a search-only pass
  then a tool pass).
- Moving research phases onto a tool loop changes their LLM-call shape; validate the
  retry-to-structured-output path holds under tool use (the defensive tuple-handling in
  `run_research_agent` already anticipates a tools path).
- Live-search substance for niche signals (politician trades, CTA) is unproven — validate
  on a real Grok run before declaring soft phases done; some may still need ingestion (#565).
