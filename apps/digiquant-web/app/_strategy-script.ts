import type { ChatPlaybackStep } from "@digithings/ui";

/** Workflow story script: digichat to Nautilus to inspect and hand off. Data, not a component.
 *
 *  Tool names and argument names are the real ones registered in
 *  digiquant/src/digiquant/mcp_server.py (the `*_json` arguments are JSON strings).
 *  Every result is masked: the simulation shows that something came back, never
 *  what. No metrics, no timings, no file paths. `AAPL` is the example symbol from
 *  the tool's own docstring; `ema_cross` is a registered strategy. */

export const STRATEGY_BADGE = "Story · scripted · not connected to any MCP server";
export const STRATEGY_HEADER = "digichat · local full-scope MCP";

/** Scope of each tool: `read` is in the dashboard chat's read-scope list,
 *  `full` needs the local full-scope server (READ_SCOPE_TOOLS in mcp_server.py). */
export type ToolScope = "read" | "full";

export const STRATEGY_SCRIPT: ChatPlaybackStep[] = [
  { role: "user", text: "Build me a simple trend-following strategy. What can I start from?" },
  {
    role: "tool",
    tool: { name: "digiquant_list_strategies", result: "▒▒▒▒▒▒▒▒▒ ▒▒▒▒▒▒▒▒▒▒▒", masked: true },
  },
  { role: "assistant", text: "There is an EMA crossover in the registry. Backtest it first." },
  {
    role: "tool",
    tool: {
      name: "digiquant_run_backtest",
      args: 'strategy_name="ema_cross", symbols_json=\'["AAPL"]\'',
      result: "▒▒▒▒▒▒▒▒▒▒▒▒ ▒▒▒▒▒▒▒▒▒▒",
      masked: true,
    },
  },
  { role: "assistant", text: "Now search its parameters over the same data." },
  {
    role: "tool",
    tool: {
      name: "digiquant_run_optimize",
      args: 'strategy_name="ema_cross", symbols_json=\'["AAPL"]\', method="grid"',
      result: "▒▒▒▒▒▒▒▒▒▒▒▒ ▒▒▒▒▒▒▒▒▒▒▒▒▒",
      masked: true,
    },
  },
  {
    role: "assistant",
    text: "Optimized results are in-sample. Exporting writes a file, so I need your go-ahead.",
  },
  { role: "user", text: "Go ahead and export it." },
  {
    role: "tool",
    tool: {
      name: "digiquant_export",
      args: 'strategy_name="ema_cross", target="nautilus_bundle"',
      result: "▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒",
      masked: true,
    },
  },
  { role: "assistant", text: "A file was written for you to review. Nothing is deployed and nothing trades." },
];

/** One ledger step per tool call, in script order. */
export const STRATEGY_STEPS: { tool: string; label: string; scope: ToolScope }[] = [
  { tool: "digiquant_list_strategies", label: "list", scope: "read" },
  { tool: "digiquant_run_backtest", label: "backtest", scope: "full" },
  { tool: "digiquant_run_optimize", label: "optimize", scope: "full" },
  { tool: "digiquant_export", label: "hand off", scope: "full" },
];

/** Honest status ledger shown under the story. */
export const STRATEGY_LEDGER: { key: string; value: string }[] = [
  { key: "where it is built", value: "the dashboard is the builder; this page tells the story and builds nothing" },
  { key: "strategy development", value: "in development, not live" },
  { key: "backtest · optimize · export", value: "run locally over stdio, full-scope MCP" },
  { key: "hosted MCP", value: "none: no public server, no connect button, no URL" },
  { key: "hand-off", value: "export writes a local JSON config only: no Pine or TradingView output, no broker or QuantConnect deployment" },
  { key: "nautilus_bundle", value: "a local zip, and for ema_cross only" },
  { key: "dashboard chat", value: "read scope: list_strategies only, from these four" },
];
