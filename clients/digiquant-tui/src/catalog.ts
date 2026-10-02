import type { Layout } from "./grid";

// Parked: a digichat terminal tab is not built. See README.md.
// Web-only, not in this terminal: Bloomberg, LuxAlgo, LuxAlgo charts, chat.

const FX_PAIR = "USDJPY";

export type Page = { path: string; label: string; group: string };
export type BlockKind = "fields" | "graph";
export type BlockDef = { id: string; title: string; route: string; kind: BlockKind };

const L = (rows: [string, number, number, number, number][]): Layout =>
  rows.map(([id, x, y, w, h]) => ({ id, x, y, w, h }));

export const PAGES: Page[] = [
  { path: "/brief", label: "Brief", group: "Desk" },
  { path: "/portfolio", label: "Portfolio", group: "Desk" },
  { path: "/portfolio/holdings", label: "Holdings", group: "Portfolio" },
  { path: "/portfolio/attribution", label: "Attribution", group: "Portfolio" },
  { path: "/portfolio/ledger", label: "Ledger", group: "Portfolio" },
  { path: "/portfolio/theses", label: "Theses", group: "Portfolio" },
  { path: "/portfolio/tearsheet", label: "Tearsheet", group: "Portfolio" },
  { path: "/performance", label: "Performance", group: "Desk" },
  { path: "/pipeline", label: "Pipeline", group: "Desk" },
  { path: "/strategies", label: "Strategies", group: "Desk" },
  { path: "/strategies/detail", label: "Detail", group: "Strategies" },
  { path: "/strategies/deploy", label: "Deploy", group: "Strategies" },
  { path: "/fx", label: "FX Hub", group: "FX Hub" },
  { path: "/fx/ideas", label: "Ideas", group: "FX Hub" },
  { path: "/fx/watch", label: "Watch", group: "FX Hub" },
  { path: "/fx/rates", label: "Rates", group: "FX Hub" },
  { path: "/fx/settings", label: "Settings", group: "FX Hub" },
];

const tearsheet = L([
  ["performance", 1, 1, 6, 6],
  ["navtable", 7, 1, 6, 6],
  ["benchmarks", 1, 7, 6, 6],
  ["drawdown", 7, 7, 6, 6],
]);

/** Default placements, copied from the current desk. `/performance` is that tearsheet. */
export const PAGE_LAYOUTS: Record<string, Layout> = {
  "/brief": L([
    ["brief", 1, 1, 8, 3],
    ["live", 9, 1, 4, 3],
    ["decision", 1, 4, 4, 4],
    ["signals", 5, 4, 4, 4],
    ["risks", 9, 4, 4, 4],
    ["movers", 1, 8, 6, 5],
    ["pl-run-health", 7, 8, 6, 5],
  ]),
  "/portfolio": L([
    ["portfolio", 1, 1, 4, 6],
    ["sleeves", 5, 1, 4, 6],
    ["movers", 9, 1, 4, 6],
    ["book", 1, 7, 6, 6],
    ["nav", 7, 7, 3, 6],
    ["drawdown", 10, 7, 3, 6],
  ]),
  "/portfolio/holdings": L([["holdings", 1, 1, 12, 12]]),
  "/portfolio/attribution": L([["attribution", 1, 1, 12, 12]]),
  "/portfolio/ledger": L([
    ["ledger", 1, 1, 8, 12],
    ["cash", 9, 1, 4, 12],
  ]),
  "/portfolio/tearsheet": tearsheet,
  "/performance": tearsheet.map((p) => ({ ...p })),
  "/portfolio/theses": L([
    ["theses", 1, 1, 8, 12],
    ["signals", 9, 1, 4, 12],
  ]),
  "/fx": L([
    ["fx-summary", 1, 1, 12, 4],
    ["fx-pairs", 1, 5, 7, 4],
    ["fx-levels", 8, 5, 5, 4],
    ["fx-pair-path", 1, 9, 7, 4],
    ["fx-sessions", 8, 9, 5, 4],
  ]),
  "/fx/ideas": L([
    ["fx-ideas", 1, 1, 7, 7],
    ["fx-idea-detail", 8, 1, 5, 7],
    ["fx-flags", 1, 8, 6, 5],
    ["fx-pair-path", 7, 8, 6, 5],
  ]),
  "/fx/watch": L([
    ["fx-pairs", 1, 1, 7, 6],
    ["fx-levels", 8, 1, 5, 6],
    ["fx-paper-exposure", 1, 7, 7, 6],
    ["fx-flags", 8, 7, 5, 6],
  ]),
  "/fx/rates": L([
    ["rt-summary", 1, 1, 12, 3],
    ["rt-curve", 1, 4, 7, 9],
    ["rt-watchlist", 8, 4, 5, 5],
    ["rt-theses", 8, 9, 5, 4],
  ]),
  "/fx/settings": L([
    ["se-fx-feed", 1, 1, 6, 6],
    ["fx-directives", 7, 1, 6, 12],
    ["se-brokers", 1, 7, 6, 6],
  ]),
  "/pipeline": L([
    ["pl-run-health", 1, 1, 4, 4],
    ["pl-narrative", 5, 1, 4, 4],
    ["pl-artifacts", 9, 1, 4, 4],
    ["pl-canvas", 1, 5, 8, 8],
    ["pl-node-document", 9, 5, 4, 4],
    ["pl-call-trace", 9, 9, 4, 4],
  ]),
  "/strategies": L([
    ["st-kpis", 1, 1, 12, 3],
    ["st-catalog", 1, 4, 7, 9],
    ["st-deployments", 8, 4, 5, 9],
  ]),
  "/strategies/detail": L([
    ["st-overview", 1, 1, 6, 6],
    ["st-parameters", 7, 1, 6, 6],
    ["st-track-record", 1, 7, 7, 6],
    ["st-runs", 8, 7, 5, 6],
  ]),
  "/strategies/deploy": L([
    ["st-targets", 1, 1, 5, 12],
    ["st-deploy-flow", 6, 1, 7, 6],
    ["st-deploy-draft", 6, 7, 7, 6],
  ]),
};

const block = (id: string, title: string, route: string, kind: BlockKind = "fields"): BlockDef => ({
  id,
  title,
  route,
  kind,
});

export const BLOCKS: Record<string, BlockDef> = {
  brief: block("brief", "Brief · scoreboard", "/brief"),
  live: block("live", "Live marks · snapshot", "/kpis/live"),
  decision: block("decision", "Decision", "/brief/decision"),
  signals: block("signals", "Signals to resolve", "/theses/signals"),
  risks: block("risks", "What could break the view", "/brief/risks"),
  movers: block("movers", "Book · movers", "/allocations/enriched"),
  portfolio: block("portfolio", "Portfolio · envelope", "/portfolio"),
  sleeves: block("sleeves", "Exposure · sleeve", "/allocations/enriched"),
  book: block("book", "Book · allocation", "/allocations"),
  nav: block("nav", "NAV · series", "/nav-series"),
  drawdown: block("drawdown", "Drawdown", "/performance/drawdown"),
  holdings: block("holdings", "Holdings · by sleeve", "/allocations/enriched"),
  attribution: block("attribution", "Attribution", "/attribution"),
  ledger: block("ledger", "Ledger · position events", "/ledger?limit=50"),
  cash: block("cash", "Cash ledger", "/ledger/cash"),
  performance: block("performance", "Performance · tearsheet", "/performance"),
  navtable: block("navtable", "NAV · by date", "/nav-series"),
  benchmarks: block("benchmarks", "Benchmarks · aligned", "/benchmarks"),
  theses: block("theses", "Theses", "/theses"),
  "pl-run-health": block("pl-run-health", "Run health", "/pipeline/runs/latest/health"),
  "pl-narrative": block("pl-narrative", "Run narrative", "/pipeline/runs/latest/narrative"),
  "pl-artifacts": block("pl-artifacts", "Artifact ledger", "/pipeline/runs/latest/artifacts"),
  "pl-canvas": block("pl-canvas", "Graph · nodes", "/pipeline/runs/latest/graph", "graph"),
  "pl-node-document": block("pl-node-document", "Node document", "/pipeline/runs/latest/nodes/selected/document"),
  "pl-call-trace": block("pl-call-trace", "Call trace", "/pipeline/runs/latest/trace"),
  "st-kpis": block("st-kpis", "Strategies · summary", "/strategies/summary"),
  "st-catalog": block("st-catalog", "Catalog", "/strategies"),
  "st-deployments": block("st-deployments", "My deployments", "/strategies/deployments"),
  "st-targets": block("st-targets", "Deployment targets", "/strategies/targets"),
  "st-overview": block("st-overview", "Overview", "/strategies/default"),
  "st-parameters": block("st-parameters", "Parameters", "/strategies/default/parameters"),
  "st-track-record": block("st-track-record", "Paper track record", "/strategies/default/performance"),
  "st-runs": block("st-runs", "Runs", "/strategies/default/runs"),
  "st-deploy-flow": block("st-deploy-flow", "Deploy · plan", "/strategies/deploy-flow"),
  "st-deploy-draft": block("st-deploy-draft", "Target · paper", "/strategies/default/deploy-draft"),
  "fx-summary": block("fx-summary", "FX hub · summary", "/fx/summary"),
  "fx-pairs": block("fx-pairs", "FX · pairs", "/fx/pairs"),
  "fx-pair-path": block("fx-pair-path", "Session path", `/fx/pairs/${FX_PAIR}/path`),
  "fx-ideas": block("fx-ideas", "FX · ideas", "/fx/ideas"),
  "fx-idea-detail": block("fx-idea-detail", "Idea detail", `/fx/ideas/${FX_PAIR}`),
  "fx-levels": block("fx-levels", "FX · levels", "/fx/levels"),
  "fx-flags": block("fx-flags", "Research flag", `/fx/flags/${FX_PAIR}`),
  "fx-paper-exposure": block("fx-paper-exposure", "Open risk · paper", "/fx/paper-exposure"),
  "fx-sessions": block("fx-sessions", "FX · sessions", "/fx/sessions"),
  "fx-directives": block("fx-directives", "Generation directives", "/fx/directives"),
  "rt-summary": block("rt-summary", "Rates · digest", "/rates/summary"),
  "rt-watchlist": block("rt-watchlist", "Rates · watchlist", "/rates/watchlist"),
  "rt-curve": block("rt-curve", "Rates · curve", "/rates/curve"),
  "rt-theses": block("rt-theses", "Rates · theses", "/rates/theses"),
  "se-fx-feed": block("se-fx-feed", "Settings · FX feed", "/settings/fx-feed"),
  "se-brokers": block("se-brokers", "Settings · brokers", "/settings/brokers"),
};

export function pageByPath(path: string): Page | undefined {
  return PAGES.find((p) => p.path === path);
}

export function layoutFor(path: string): Layout {
  return (PAGE_LAYOUTS[path] ?? []).map((p) => ({ ...p }));
}
