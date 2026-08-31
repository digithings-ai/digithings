/** digiquant subsystems — research → portfolio → execution.
 *  Same shape conventions as modules; drives the pipeline graph + detail pages.
 *
 *  Display names are job words (ADR-0026). URL ids (`atlas` / `hermes` / `kairos`)
 *  and Python import snippets still match package paths until the path/package waves.
 */
import { type StackItem } from "./modules";

export interface Subsystem {
  id: string;
  name: string;
  tier: "research" | "signals" | "execution";
  step: string;
  emblem: string;
  role: string;
  tagline: string;
  summary: string[];
  stack: StackItem[];
  dockerCmd: string | null;
  initSnippet: { lang: string; code: string };
  related: string[];
}

export const subsystems: Subsystem[] = [
  {
    id: "atlas",
    name: "Research",
    tier: "research",
    step: "01 · research",
    emblem: "atlas",
    role: "Scheduled macro & market research",
    tagline: "Research, persisted — structured views, not prose.",
    summary: [
      "Scheduled LangGraph research cycles across a configurable universe, pulling from open data sources (FRED, Treasury, CoinGecko, SEC/EDGAR) on one daily graph, with per-artifact skip, edit, or full refresh.",
      "Every cycle writes structured, versioned views to Supabase — re-used downstream, and fully auditable.",
    ],
    stack: [
      { name: "LangGraph", icon: "langchain" },
      { name: "Polars", icon: "polars" },
      { name: "Supabase", icon: "supabase" },
      { name: "FRED", icon: null, mono: "FRED" },
      { name: "CoinGecko", icon: null, mono: "CG" },
    ],
    dockerCmd: "docker compose up -d digiquant",
    initSnippet: { lang: "python", code: "from digiquant.olympus.atlas.graph import build_atlas_graph\natlas = build_atlas_graph()" },
    related: ["hermes", "kairos"],
  },
  {
    id: "hermes",
    name: "Portfolio",
    tier: "signals",
    step: "02 · signals",
    emblem: "hermes",
    role: "Deliberation & signal delivery",
    tagline: "Delivery, not deliberation theatre.",
    summary: [
      "Translates daily research into allocations via a LangGraph deliberation pipeline. Each signal is timestamped, attributed to the views that produced it, and fully replayable.",
      "Signals carry their provenance, so any decision can be reconstructed from the research that drove it.",
    ],
    stack: [
      { name: "LangGraph", icon: "langchain" },
      { name: "Polars", icon: "polars" },
      { name: "Supabase", icon: "supabase" },
    ],
    dockerCmd: "docker compose up -d digiquant",
    initSnippet: { lang: "python", code: "from digiquant.olympus.hermes.graph import build_hermes_graph\nhermes = build_hermes_graph()" },
    related: ["atlas", "kairos"],
  },
  {
    id: "kairos",
    name: "Execution",
    tier: "execution",
    step: "03 · execution",
    emblem: "kairos",
    role: "Backtest, optimize, and paper-route — live venues refused",
    tagline: "Paper adapters ship. Live tokens never leave the router.",
    summary: [
      "The execution stage runs the sized book through a real NautilusTrader engine — backtest and Optuna-driven optimization over your own OHLCV data, with a tearsheet and an append-only audit trail per run.",
      "Paper adapters for Alpaca and IBKR ship; routing stays off until you opt in. Live venue tokens are refused on the public path. Connecting a live venue is your own integration, not a flag we flip.",
    ],
    stack: [
      { name: "NautilusTrader", icon: null, mono: "NT" },
      { name: "Optuna", icon: "optuna" },
      { name: "Polars", icon: "polars" },
    ],
    dockerCmd: "docker compose up -d digiquant",
    initSnippet: { lang: "python", code: "from digiquant.backtest import run_backtest\nresult = run_backtest(...)  # paper adapters exist; live tokens are refused" },
    related: ["hermes", "atlas"],
  },
];

export const subsystemById = (id: string) => subsystems.find((s) => s.id === id);
