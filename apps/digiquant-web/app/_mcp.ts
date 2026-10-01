import type { TerminalManifestRow } from "@digithings/ui";

/** Data for the MCP band. Every line is a repo fact; re-verify before publishing.
 *
 *  Sources:
 *  - Tool names and scopes: digiquant/src/digiquant/mcp_server.py. `--stdio` runs it
 *    locally; `--scope read` registers only READ_SCOPE_TOOLS (the dashboard chat's
 *    list), `--scope full` (default) registers every tool. No hosted endpoint exists.
 *  - Backtests run on NautilusTrader; optimize results are in-sample; export writes
 *    a JSON config or a local nautilus_bundle zip (ema_cross only). Nothing trades. */
export const MCP_ROWS: TerminalManifestRow[] = [
  {
    id: "strategies",
    name: "strategies",
    status: "online",
    blurb: "list, backtest, optimize, export",
    detail:
      "digiquant_list_strategies, digiquant_run_backtest, digiquant_run_optimize and digiquant_export. Backtests run on NautilusTrader, optimized results are in-sample, and export writes a local file. digiquant_run_pipeline chains them.",
  },
  {
    id: "research",
    name: "research",
    status: "online",
    blurb: "query past runs, price and macro context",
    detail:
      "digiquant_query_research reads the decision log of past runs. digiquant_get_price_technicals, digiquant_get_macro_series and digiquant_get_trade_levels add context for a symbol. All read scope.",
  },
  {
    id: "market-data",
    name: "market data",
    status: "online",
    blurb: "quotes, history, filings, news",
    detail:
      "The digifetch tools: quotes, price history, financials, filings, news and economic series. All read scope, so the dashboard chat can call them.",
  },
  {
    id: "builder",
    name: "strategy builder",
    status: "roadmap",
    blurb: "the chat flow, inside the dashboard",
    detail:
      "The dashboard's strategy builder drives the strategy tools from a chat. It is in development; today the same tools run through the local MCP server.",
  },
];

/** What the server does and does not expose. */
export const MCP_LEDGER: { key: string; value: string }[] = [
  { key: "transport", value: "stdio, run locally. There is no hosted server, no public URL and no connect button." },
  { key: "read scope", value: "Lists and queries only. This is the scope the dashboard chat gets." },
  { key: "full scope", value: "Adds backtest, optimize, export and the pipeline run." },
  { key: "output", value: "Results are in-sample and illustrative. Nothing is deployed and nothing trades." },
];
