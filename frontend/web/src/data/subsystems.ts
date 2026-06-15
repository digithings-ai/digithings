/** DigiQuant subsystems — Atlas (research) → Hermes (signals) → Kairos (execution).
 *  Same shape conventions as modules; drives the pipeline graph + detail pages. */
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
    name: "Atlas",
    tier: "research",
    step: "01 · research",
    emblem: "atlas",
    role: "Scheduled macro & market research",
    tagline: "Research, persisted — structured views, not prose.",
    summary: [
      "Atlas runs scheduled LangGraph research cycles across a configurable universe, pulling from open data sources (FRED, Treasury, CoinGecko, SEC/EDGAR) on daily-delta, weekly-baseline, and monthly-rollup cadences.",
      "Every cycle writes structured, versioned views to Supabase — re-used by Hermes and Kairos, and fully auditable.",
    ],
    stack: [
      { name: "LangGraph", icon: "langchain" },
      { name: "Polars", icon: "polars" },
      { name: "Supabase", icon: "supabase" },
      { name: "FRED", icon: null, mono: "FRED" },
      { name: "CoinGecko", icon: "coingecko" },
    ],
    dockerCmd: "docker compose up -d digiquant",
    initSnippet: { lang: "python", code: "from digiquant.atlas.graph import build_atlas_graph\natlas = build_atlas_graph()" },
    related: ["hermes", "kairos"],
  },
  {
    id: "hermes",
    name: "Hermes",
    tier: "signals",
    step: "02 · signals",
    emblem: "hermes",
    role: "Deliberation & signal delivery",
    tagline: "Delivery, not deliberation theatre.",
    summary: [
      "Hermes translates Atlas research into allocations via a LangGraph deliberation pipeline. Each signal is timestamped, attributed to the views that produced it, and fully replayable.",
      "Signals carry their provenance, so any decision can be reconstructed from the research that drove it.",
    ],
    stack: [
      { name: "LangGraph", icon: "langchain" },
      { name: "Polars", icon: "polars" },
      { name: "Supabase", icon: "supabase" },
    ],
    dockerCmd: "docker compose up -d digiquant",
    initSnippet: { lang: "python", code: "from digiquant.hermes.graph import build_hermes_graph\nhermes = build_hermes_graph()" },
    related: ["atlas", "kairos"],
  },
  {
    id: "kairos",
    name: "Kairos",
    tier: "execution",
    step: "03 · execution",
    emblem: "kairos",
    role: "Execution on NautilusTrader · human-gated",
    tagline: "Execution, gated. Strategies climb a ladder.",
    summary: [
      "Kairos executes Hermes signals on a NautilusTrader core. Strategies climb a ladder — backtest → paper → loopback → live — and each rung is a human gate.",
      "Loopback-only by default: nothing reaches a live venue until someone flips the gate, and every transition is audited.",
    ],
    stack: [
      { name: "NautilusTrader", icon: null, mono: "NT" },
      { name: "Optuna", icon: null, mono: "Op" },
      { name: "Polars", icon: "polars" },
    ],
    dockerCmd: "docker compose up -d digiquant",
    initSnippet: { lang: "python", code: 'kairos.execute(signals, gate="human")  # loopback-only by default' },
    related: ["hermes", "atlas"],
  },
];

export const subsystemById = (id: string) => subsystems.find((s) => s.id === id);
