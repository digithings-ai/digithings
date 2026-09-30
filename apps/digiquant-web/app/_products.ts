import type { TerminalManifestRow } from "@digithings/ui";

/** Data for the products band. Every line is a repo fact, re-verify before publishing.
 *
 *  Sources:
 *  - rows / phases: docs/superpowers/specs/2026-09-30-digiquant-web-rebuild-inventory.md
 *    (research phases 00-09, portfolio phases h1-h9, decision log per run id).
 *  - Gloomberb: digiquant/src/digiquant/data/gloomberb/attribution.py defines
 *    GLOOMBERB_ATTRIBUTION = "Sourced from Gloomberb" and, for the free tier,
 *    GLOOMBERB_DELAY_NOTICE = "Data delayed up to 15 minutes". The 15 minutes is
 *    stated only with that "free tier" qualifier, exactly as the source does.
 *  - Coinbase: app/_chrome/MarketBarShell.tsx (keyless public websocket, top bar).
 *  - NautilusTrader: LGPL-3.0-or-later per the package METADATA of nautilus_trader
 *    1.231.0 (digiquant/pyproject.toml pins >=1.190,<2). The app FAQ in _pricing.ts
 *    says "see the NautilusTrader repository for its current license terms".
 *  - MCP: digiquant/src/digiquant/mcp_server.py --stdio; no hosted endpoint exists.
 *  - LuxAlgo: #4779 is present on this branch. The local gateway exposes Library
 *    research concepts and indicator metadata only, never signals or source code.
 *    Charting and journaling stay in LuxAlgo rather than being rebuilt here. */
export const PRODUCT_ROWS: TerminalManifestRow[] = [
  {
    id: "research",
    name: "research",
    status: "online",
    blurb: "daily runs, a decision log for each",
    detail:
      "Research runs daily through ten phases (00-09), from preflight and triage to synthesis and publish. Every run writes a decision log under its own run id, redacted on the way out.",
  },
  {
    id: "portfolio",
    name: "portfolio",
    status: "online",
    blurb: "risk sizing, backtests, tearsheets",
    detail:
      "Portfolio phases (h1-h9) turn the research into a thesis, a vehicle map and risk sizing, then commit the run. Backtests run on NautilusTrader and publish as tearsheets marked backtest, illustrative, in-sample.",
  },
  {
    id: "strategy",
    name: "strategy",
    status: "roadmap",
    blurb: "chat-driven building, in development",
    detail:
      "Building a strategy from chat through MCP tools is in development. Backtest, optimize and export run today through the local MCP server; export writes JSON only. Nothing trades live.",
  },
];

export type IntegrationStatus = "live" | "integrated" | "built on" | "local only" | "in development";

export type IntegrationRow = {
  id: string;
  name: string;
  status: IntegrationStatus;
  /** One line: what it does and where it shows up. */
  what: string;
};

export const INTEGRATIONS: IntegrationRow[] = [
  {
    id: "gloomberb",
    name: "Gloomberb",
    status: "integrated",
    what: "Research data through digifetch tools. Sourced from Gloomberb. Free-tier data delayed up to 15 minutes.",
  },
  {
    id: "coinbase",
    name: "Coinbase",
    status: "live",
    what: "Public keyless price feed for the top bar.",
  },
  {
    id: "nautilus",
    name: "NautilusTrader",
    status: "built on",
    what: "The backtest engine behind every tearsheet. LGPL-3.0-or-later, see its repository for terms.",
  },
  {
    id: "mcp",
    name: "MCP",
    status: "local only",
    what: "Runs locally over stdio. There is no public hosted server.",
  },
  {
    id: "luxalgo",
    name: "LuxAlgo",
    status: "integrated",
    what: "Chart and journal workspace. The local gateway adds Library concepts and indicator metadata only. No signals, no source code.",
  },
];
