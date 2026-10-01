/** Data for the MCP band. Every line is a repo fact; re-verify before publishing.
 *
 *  Sources:
 *  - Tool names and scopes: digiquant/src/digiquant/mcp_server.py. `--stdio` runs it
 *    locally; `--scope read` registers only READ_SCOPE_TOOLS (the dashboard chat's
 *    list), `--scope full` (default) registers every tool. No hosted endpoint exists.
 *  - Optimize results are in-sample; export writes a config or a local bundle file.
 *    Nothing trades. */

export const MCP_COMMAND = "python -m digiquant.mcp_server --stdio --scope full";

export const MCP_HELP_COMMAND = "python -m digiquant.mcp_server --help";

export type McpScope = "read" | "full" | "roadmap";

export interface McpCommand {
  id: string;
  name: string;
  /** The tools behind the command, as the server registers them (prefix dropped). */
  tools: string;
  scope: McpScope;
  detail: string;
}

export const MCP_COMMANDS: McpCommand[] = [
  {
    id: "strategies",
    name: "strategies",
    tools: "list_strategies · run_backtest · run_optimize · export · run_pipeline",
    scope: "full",
    detail:
      "Registered as digiquant_list_strategies, digiquant_run_backtest, digiquant_run_optimize and digiquant_export; digiquant_run_pipeline chains them. Optimized results are in-sample, and export writes a local file.",
  },
  {
    id: "research",
    name: "research",
    tools: "query_research · get_price_technicals · get_macro_series · get_trade_levels",
    scope: "read",
    detail:
      "digiquant_query_research reads the decision log of past runs. The price, macro and trade-level tools add context for a symbol. All read scope.",
  },
  {
    id: "market-data",
    name: "market-data",
    tools: "digifetch · quotes · history · financials · filings · news",
    scope: "read",
    detail:
      "The digifetch tools: quotes, price history, financials, filings, news and economic series. All read scope, so the dashboard chat can call them.",
  },
  {
    id: "builder",
    name: "builder",
    tools: "the chat flow, inside the dashboard",
    scope: "roadmap",
    detail:
      "The dashboard's strategy builder drives the strategy tools from a chat. It is in development; today the same tools run through the local MCP server.",
  },
];

/** What the server does and does not expose, printed as the command's options. */
export const MCP_OPTIONS: { flag: string; text: string }[] = [
  { flag: "--stdio", text: "runs locally. no hosted server, no public URL, no connect button" },
  { flag: "--scope read", text: "lists and queries only. this is the scope the dashboard chat gets" },
  { flag: "--scope full", text: "adds backtest, optimize, export and the pipeline run" },
  { flag: "output", text: "in-sample and illustrative. nothing is deployed and nothing trades" },
];
