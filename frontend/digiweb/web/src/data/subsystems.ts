/** digiquant subsystems — research → portfolio → execution.
 *  Same shape conventions as modules; drives the pipeline graph + detail pages.
 *
 *  Display names and URL ids are job words (ADR-0026). Emblem keys stay on the
 *  existing mark set (research/portfolio/execution alias the same SVGs).
 *  Init snippets do not print retired package paths.
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
    id: "research",
    name: "Research",
    tier: "research",
    step: "01 · research",
    emblem: "research",
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
    initSnippet: {
      lang: "python",
      code: "# daily research cycle — structured views, not prose\n# universe + open data → versioned artifacts (A0–A4)",
    },
    related: ["portfolio", "execution"],
  },
  {
    id: "portfolio",
    name: "Portfolio",
    tier: "signals",
    step: "02 · signals",
    emblem: "portfolio",
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
    initSnippet: {
      lang: "python",
      code: "# deliberation → a sized book (H1–H9)\n# every signal timestamped to the views that produced it",
    },
    related: ["research", "execution"],
  },
  {
    id: "execution",
    name: "Execution",
    tier: "execution",
    step: "03 · execution",
    emblem: "execution",
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
    initSnippet: {
      lang: "python",
      code: "from digiquant.backtest import run_backtest\nresult = run_backtest(...)  # paper adapters exist; live tokens are refused",
    },
    related: ["portfolio", "research"],
  },
];

export const subsystemById = (id: string) => subsystems.find((s) => s.id === id);
