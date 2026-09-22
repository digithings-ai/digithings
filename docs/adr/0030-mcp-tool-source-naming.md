# ADR 0030: MCP tool names identify the direct data source, not the hosting module

**Status:** proposed
**Date:** 2026-09-22

## Context

DigiQuant's MCP server (`digiquant/src/digiquant/mcp_server.py`) hosts 59 tools
behind three different prefix conventions, chosen at different times for
different (and inconsistent) reasons:

- `digiquant_*` (20 tools) — DigiQuant's own compute and storage: backtests,
  optimization, the strategy engine, precomputed price/macro reads, and
  source-specific fetchers (`digiquant_fetch_coinbase_ohlcv`,
  `digiquant_fetch_bitview_series`, `digiquant_fetch_bgeometrics_series`,
  `digiquant_fetch_coinmetrics_series`).
- `digifetch_*` (34 tools) — all of Gloomberb Cloud (`api.gloom.sh`). Named
  `digifetch_*` **despite living entirely in `digiquant/data/gloomberb/`**, not
  in the `digifetch` package. The digifetch-scoping design doc
  ([`docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md`](../superpowers/specs/2026-09-12-digifetch-scoping-design.md))
  states this was "a deliberate naming/ownership split to keep discovery
  aligned with the data-fetch family" — i.e. the name signals "this is a fetch
  tool," not which module hosts it, and not which upstream it calls.
- `dashboard_*` (5 tools) — policy replay/gate tools, a genuinely separate
  consuming subsystem. Not in scope here; already named correctly.

Auditing the other MCP servers in the monorepo (digigraph, digillm,
digisearch) found **none of them prefix tool names with the module name** —
digigraph exposes `chat`, `workflow`, `thread_state`; digisearch exposes
`semantic`, `web_search`, `monitors_create_watch`, `websets_create`. DigiQuant
prefixing everything with `digiquant_`/`digifetch_` is not a stack-wide
convention; it appears to be DigiQuant-specific drift, not a deliberate rule
documented anywhere outside the one Gloomberb naming note above.

This matters because **all of these MCP servers are mounted together behind
Cloudflare** — callers see one flat tool namespace, not one server per module.
A name has to be self-explanatory in that flat namespace without leaning on
"which repo directory is this file in," which the caller cannot see anyway.

Separately, `digifetch_*` names actively mislead about what's being called.
Per the design doc's own source inventory (§6): every one of the 34
`digifetch_*` tools calls Gloomberb Cloud directly. None of them calls Yahoo
or FRED directly — Gloomberb is an aggregator that happens to source some of
its own quote/history data from Yahoo internally, but DigiQuant only ever
talks to `api.gloom.sh`, and inherits *Gloomberb's* rate limits, 15-minute
delay, and session-cookie gating — not Yahoo's or FRED's. A caller reading
`digifetch_price_history` has no way to know it's bound by Gloomberb's terms,
not a name that says so.

We verified one candidate exception before finalizing this: `digiquant_get_macro_series`
looked like it might be a direct FRED/yfinance call. It is not — it reads
from DigiQuant's own precomputed Supabase/R2 store, populated offline by a
separate ingest job (`macro_ingest.py`, which is the actual `fredapi`/`yfinance`
consumer). At MCP-call time there is no live external source at all, so it
correctly belongs in the "DigiQuant's own compute" bucket, not a
source-prefixed one.

## Decision

Name every MCP tool for **the direct integration boundary it calls at
request time** — the thing whose outages, rate limits, and auth actually
bound the tool's behavior — never for a further-upstream provenance, and
never for the module directory that happens to host the code.

Two tiers:

1. **Live external fetch** → `<source>_<verb>_<noun>`, source = the literal
   direct dependency:
   - `gloomberb_*` — the 34 current `digifetch_*` tools (e.g.
     `digifetch_price_history` → `gloomberb_get_price_history`,
     `digifetch_econ_series` → `gloomberb_get_econ_series`,
     `digifetch_screener` → `gloomberb_run_screener`). Full 34-row mapping in
     the closeout PR, not restated here — see Consequences for why.
   - `coinbase_fetch_ohlcv` (was `digiquant_fetch_coinbase_ohlcv`)
   - `bitview_fetch_series` (was `digiquant_fetch_bitview_series`)
   - `bgeometrics_fetch_series` (was `digiquant_fetch_bgeometrics_series`)
   - `coinmetrics_fetch_series`, `coinmetrics_list_catalog` (was
     `digiquant_fetch_coinmetrics_series`, `digiquant_list_coinmetrics_catalog`)

2. **DigiQuant's own compute/storage** — no live external call at request
   time, so no source name applies → `<verb>_<noun>`, unprefixed, matching
   every other module's convention:
   - `list_strategies`, `run_backtest`, `run_optimize`, `export`,
     `run_pipeline`, `get_price_technicals`, `get_macro_series`,
     `get_trade_levels`, `query_research`, `fit_btc_power_law`,
     `build_sdca_risk_index`, `fit_sdca_weights`,
     `generate_slapper_tearsheet`, `validate_slapper_vs_tradingview`
     (all currently `digiquant_*`)

`dashboard_*` is unchanged.

**New-source template.** When DigiQuant grows another live time-series
integration (on-chain, macro, alt-data — expansion of this kind is already
planned), the new tools are named `<source>_<verb>_<noun>` from day one using
this same rule: name the thing you're actually calling over the network right
now, not its further-upstream provenance, and not the module that hosts the
code. This makes the naming question a non-decision for every future source
instead of a fresh debate each time.

## Consequences

**Positive:**
- A caller reading the tool name can infer the actual failure/rate-limit
  domain without reading source.
- Removes a name that is actively wrong today (`digifetch_*` implying a
  `digifetch`-package or direct-Yahoo/FRED dependency that doesn't exist).
- Matches the convention already used by every other MCP server in the
  monorepo (digigraph, digillm, digisearch) — DigiQuant stops being the
  outlier.
- Establishes a standing rule for future sources, so this doesn't reopen.

**Negative / tradeoffs — this is a heavy, coordinated rename, not a
find-and-replace:**

- **Every tool name is duplicated in at least 3 places per tool**, all of
  which must change atomically:
  - `_maybe_tool("...")` decorator in `digiquant/src/digiquant/mcp_server.py`
  - a `build_digifetch_<name>_tool()` factory + `"name": "..."` literal in
    `digiquant/src/digiquant/orchestrator_tools.py`
  - a dict key in `digiquant/src/digiquant/data/gloomberb/entitlements.py`
    (`TOOL_ENTITLEMENTS`)
- **Cross-module callers**, not just digiquant-internal code:
  - `digiquant/src/digiquant/server.py`
  - `digiquant/src/digiquant/research/phases/phase3_macro.py`,
    `phase5_equities.py`, `_node_factory.py`
  - `digiquant/src/digiquant/portfolio/phases/portfolio_common.py`
  - `digiquant/src/digiquant/sdca_mcp.py`,
    `strategies/sdca/risk_index.py`, `strategies/sdca/providers.py`,
    `strategies/sdca/btc_power_law.py`
  - digichat's Gloomberb surfacing work
    ([`docs/superpowers/specs/2026-09-16-digichat-gloomberb-surfacing-design.md`](../superpowers/specs/2026-09-16-digichat-gloomberb-surfacing-design.md))
    references these tool names as an external caller — this is the one
    consumer most likely to break silently if the rename isn't coordinated
    with that team/PR.
- **~15 test files assert on the literal tool-name strings** and must be
  updated in the same change, not after:
  `tests/dq/test_mcp_gloomberb_tools.py`, `test_mcp_server_scope.py`,
  `test_mcp_sdca_platform.py`, `test_mcp_tearsheet_tool.py`,
  `test_mcp_sdca_risk_index.py`, `research/test_build_grounding_digifetch.py`,
  `test_orchestrator_invoke_digifetch.py`, `research/test_phase_tool_flags.py`,
  `portfolio/test_digifetch_grounding.py`,
  `data/test_gloomberb_agent_tools.py`, plus digigraph's
  `tests/dg/test_usage.py`, `test_tool_result_attribution.py`,
  `test_web_search_opt_in.py`, `test_llm_client.py` (digigraph's own
  `digifetch_web_search` tool is unrelated and out of scope — verify no test
  there confuses the two namespaces).
- **Docs**: `digiquant/AGENTS.md` (the canonical 34-tool table + entitlement
  tiers + per-tool upstream-caveat notes), `digiquant/ARCHITECTURE.md`, and
  the full `docs/superpowers/{plans,specs}/2026-09-16-*gloomberb*`,
  `2026-09-12-digifetch-scoping-design.md`,
  `2026-09-16-digifetch-{coverage-expansion,scoping-closeout}*.md` set.
- **No Cloudflare deploy manifest hardcodes individual tool names** (checked
  `apps/*/wrangler.toml`) — the rename does not touch deploy config, only
  requires a coordinated redeploy so the running MCP surface matches the new
  names atomically with the code merge. A caller hitting the old name
  mid-rollout gets a clean "unknown tool" rather than silently wrong data, so
  a brief window of 404s during redeploy is the acceptable failure mode —
  **not** a dual-registration compatibility shim (this repo's stated
  preference, per CLAUDE.md, is to avoid backwards-compatibility hacks/aliases
  for internal renames rather than carry a shim indefinitely).
- **Any external system or saved prompt that calls these tools by name**
  outside this repo (a deployed digichat instance, a saved Claude
  conversation/workflow) breaks silently until updated — sweep for these
  before cutting over, not just the in-repo call sites listed above.

**Recommended execution shape** (not started — this ADR is the naming
decision, not the migration plan): one dedicated branch/PR, not folded into
unrelated work. Rename in `mcp_server.py` first, keep tests red until every
call site above is updated in the same PR, then redeploy. Do not touch
`settings.json` or `RESEARCH_STATE.md`'s SDCA research-state content as part
of this — those follow SDCA's own standing accept gate, independent of this
rename.

## Links

- Related: [`docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md`](../superpowers/specs/2026-09-12-digifetch-scoping-design.md)
  (original `digifetch_*` naming decision, §"Placement", being revised here)
- Related: [ADR 0022](0022-supabase-env-naming-standard.md) (prior precedent
  for a coordinated platform-wide renaming ADR with a read-new-fall-back-to-old
  transition — considered and rejected here in favor of a clean cutover, since
  MCP tool names are called by exact string match with no fallback-chain
  mechanism analogous to env-var resolution)
- Supersedes: the naming clause of the digifetch-scoping design doc above
  (its capability/entitlement/pacing decisions are unaffected)
