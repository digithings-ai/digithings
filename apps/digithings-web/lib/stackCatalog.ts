/**
 * Stack configurator catalog (review-only price thread, Refs #4429).
 *
 * Both sides of the comparison are built from the same five layers
 * (models, embeddings, vector store, telemetry, hosting), each a dropdown
 * of researched options. The diagrams and the invoice both render from the
 * pick, so the graph and the bill can never disagree.
 *
 * Rate honesty: researched Sep-2026 list prices come from `RAG_PRICING`;
 * the two entries marked `estimate: true` (Azure hosting, Qdrant entry)
 * are single-source planning figures and render with a ~ prefix. Anything
 * without a defensible number is not an option (no OpenRouter row until its
 * pass-through rate is sourced).
 */

import type { ArchSpec } from "@digithings/ui";
import {
  DEFAULT_WORKLOAD,
  RAG_PRICING,
  TOKENS_PER_GB,
  type RagWorkload,
} from "@/lib/ragCost";

export type LayerId = "models" | "embeddings" | "vector" | "telemetry" | "hosting";

export interface LayerOption {
  id: string;
  label: string;
  vendor: string;
  /** Kit logo slug; absent renders the generic plate. */
  logo?: string;
  estimate?: boolean;
}

export interface Layer {
  id: LayerId;
  label: string;
  options: LayerOption[];
}

export const PROVIDER_LAYERS: Layer[] = [
  {
    id: "models",
    label: "Model provider",
    options: [
      { id: "sol", label: "GPT-5.6 Sol · $5/$30", vendor: "OpenAI", logo: "openai" },
      { id: "luna", label: "GPT-5.6 Luna · $0.20/$1.20", vendor: "OpenAI", logo: "openai" },
      { id: "o3", label: "o3 reasoning · $2/$8", vendor: "OpenAI", logo: "openai" },
      { id: "deepseek", label: "DeepSeek V4 · $0.14/$0.28", vendor: "DeepSeek" },
      { id: "commandr", label: "Command R · $0.15/$0.60", vendor: "Cohere" },
      { id: "local", label: "Self-hosted · $0", vendor: "you" },
    ],
  },
  {
    id: "embeddings",
    label: "Embeddings",
    options: [
      { id: "large", label: "embed-3-large · $0.13/M", vendor: "OpenAI", logo: "openai" },
      { id: "small", label: "embed-3-small · $0.02/M", vendor: "OpenAI", logo: "openai" },
      { id: "cohere", label: "Cohere v4 · $0.12/M", vendor: "Cohere" },
      { id: "local", label: "Self-hosted · $0", vendor: "you" },
    ],
  },
  {
    id: "vector",
    label: "Vector store",
    options: [
      { id: "pinecone", label: "Pinecone · $50 floor", vendor: "Pinecone" },
      { id: "qdrant", label: "Qdrant Cloud · ~$25", vendor: "Qdrant", estimate: true },
      { id: "self", label: "Self-hosted pgvector · $0", vendor: "you" },
    ],
  },
  {
    id: "telemetry",
    label: "Telemetry",
    options: [
      { id: "langsmith", label: "LangSmith · $39 + traces", vendor: "LangSmith" },
      { id: "self", label: "Self-hosted traces · $0", vendor: "you" },
    ],
  },
  {
    id: "hosting",
    label: "Hosting",
    options: [
      { id: "azure", label: "Azure · ~$75 est.", vendor: "Azure", estimate: true },
      { id: "own", label: "Own hardware · $0", vendor: "you" },
    ],
  },
];

export const DIGI_LAYERS: Layer[] = [
  {
    id: "models",
    label: "Models via digillm",
    options: [
      { id: "local", label: "Local · $0", vendor: "you" },
      { id: "luna", label: "Luna · $0.20/$1.20", vendor: "OpenAI", logo: "openai" },
      { id: "deepseek", label: "DeepSeek V4 · $0.14/$0.28", vendor: "DeepSeek" },
      { id: "o3", label: "o3 · $2/$8", vendor: "OpenAI", logo: "openai" },
      { id: "sol", label: "Sol · $5/$30", vendor: "OpenAI", logo: "openai" },
    ],
  },
  {
    id: "embeddings",
    label: "Embeddings",
    options: [
      { id: "local", label: "Local · $0", vendor: "you" },
      { id: "small", label: "small · $0.02/M", vendor: "OpenAI", logo: "openai" },
      { id: "cohere", label: "Cohere v4 · $0.12/M", vendor: "Cohere" },
      { id: "large", label: "large · $0.13/M", vendor: "OpenAI", logo: "openai" },
    ],
  },
  {
    id: "vector",
    label: "Vector store",
    options: [
      { id: "self", label: "Self-hosted · $0", vendor: "you" },
      { id: "qdrant", label: "Qdrant Cloud · ~$25", vendor: "Qdrant", estimate: true },
      { id: "pinecone", label: "Pinecone · metered", vendor: "Pinecone" },
    ],
  },
  {
    id: "telemetry",
    label: "Telemetry",
    options: [
      { id: "digismith", label: "digismith · $0", vendor: "digithings" },
      { id: "langsmith", label: "LangSmith · metered", vendor: "LangSmith" },
    ],
  },
  {
    id: "hosting",
    label: "Hosting",
    options: [
      { id: "own", label: "Own hardware · $0", vendor: "you" },
      { id: "azure", label: "Azure · ~$75 est.", vendor: "Azure", estimate: true },
    ],
  },
];

export type StackPick = Record<LayerId, string>;

/** The most common off-the-shelf stack; the page default. */
export const DEFAULT_PROVIDER_PICK: StackPick = {
  models: "sol",
  embeddings: "large",
  vector: "pinecone",
  telemetry: "langsmith",
  hosting: "azure",
};

/** digithings for everything, self-hosted to zero; the page default. */
export const DEFAULT_DIGI_PICK: StackPick = {
  models: "local",
  embeddings: "local",
  vector: "self",
  telemetry: "digismith",
  hosting: "own",
};

const MODEL_RATES: Record<string, { inPerM: number; outPerM: number }> = {
  sol: { inPerM: RAG_PRICING.chatFlagshipInPerM, outPerM: RAG_PRICING.chatFlagshipOutPerM },
  luna: { inPerM: RAG_PRICING.chatMidInPerM, outPerM: RAG_PRICING.chatMidOutPerM },
  o3: { inPerM: RAG_PRICING.reasoningInPerM, outPerM: RAG_PRICING.reasoningOutPerM },
  deepseek: { inPerM: RAG_PRICING.deepseekInPerM, outPerM: RAG_PRICING.deepseekOutPerM },
  commandr: { inPerM: 0.15, outPerM: 0.6 },
  local: { inPerM: 0, outPerM: 0 },
};

const EMBED_RATES: Record<string, { perM: number; dims: number }> = {
  large: { perM: RAG_PRICING.embedLargePerM, dims: 3072 },
  small: { perM: RAG_PRICING.embedSmallPerM, dims: 1536 },
  cohere: { perM: RAG_PRICING.embedCoherePerM, dims: 1024 },
  local: { perM: 0, dims: 1536 },
};

const AZURE_HOSTING_ESTIMATE = 75;

export interface PricedLine {
  label: string;
  amount: number;
  estimate?: boolean;
}

export interface StackPrice {
  setup: number;
  monthly: number;
  lines: PricedLine[];
  vendors: string[];
}

function lookup(layers: Layer[], pick: StackPick, layer: LayerId): LayerOption {
  const found = layers.find((l) => l.id === layer)?.options.find((o) => o.id === pick[layer]);
  if (!found) throw new Error(`unknown pick ${layer}:${pick[layer]}`);
  return found;
}

/**
 * Setup + monthly for a full five-layer pick. Formulas mirror `ragCost`
 * (same workload, same snapshot); the cross-check test pins the default
 * provider pick to the invoice panel's provider number plus hosting.
 */
export function pricePick(
  layers: Layer[],
  pick: StackPick,
  workload: RagWorkload = DEFAULT_WORKLOAD,
): StackPrice {
  const p = RAG_PRICING;
  const model = lookup(layers, pick, "models");
  const embed = lookup(layers, pick, "embeddings");
  const vector = lookup(layers, pick, "vector");
  const telemetry = lookup(layers, pick, "telemetry");
  const hosting = lookup(layers, pick, "hosting");
  const lines: PricedLine[] = [];
  let setup = 0;
  let monthly = 0;
  const add = (label: string, amount: number, recurring: boolean, estimate?: boolean) => {
    lines.push({ label, amount, estimate });
    if (recurring) monthly += amount;
    else setup += amount;
  };

  const corpusTokens = workload.corpusGB * TOKENS_PER_GB;
  const vectors = corpusTokens / workload.chunkTokens;
  const queriesPerMonth = workload.queriesPerDay * 30;

  const embedRate = EMBED_RATES[embed.id];
  add(`Embed corpus · ${embed.label}`, (corpusTokens * embedRate.perM) / 1e6, false, embed.estimate);

  if (vector.id === "pinecone") {
    const gb = (vectors * embedRate.dims * 4) / 1e9;
    add("Pinecone writes", ((vectors * p.pineconeWritePerM) / 1e6), false);
    const ruPerQuery = Math.max(0.25, gb);
    const usage = gb * p.pineconeStoragePerGB + ((queriesPerMonth * ruPerQuery * p.pineconeReadPerM) / 1e6);
    add("Pinecone store + reads", Math.max(p.pineconeMinMonthly, usage), true);
  } else if (vector.id === "qdrant") {
    add("Qdrant Cloud", p.qdrantEntryMonthly, true, true);
  } else {
    add("Self-hosted vectors", 0, true);
  }

  const queryEmbedTokens = queriesPerMonth * workload.queryEmbedTokens;
  add(`Query embeddings · ${embed.label}`, (queryEmbedTokens * embedRate.perM) / 1e6, true, embed.estimate);

  const chatIn = queriesPerMonth * workload.chatInTokensPerQuery;
  const chatOut = queriesPerMonth * workload.chatOutTokensPerQuery;
  const rates = MODEL_RATES[model.id];
  add(`Model answers · ${model.label}`, (chatIn * rates.inPerM + chatOut * rates.outPerM) / 1e6, true, model.estimate);

  if (telemetry.id === "langsmith") {
    const over = Math.max(0, queriesPerMonth - p.langsmithIncludedTraces);
    add("LangSmith", p.langsmithSeatMonthly + (over * p.langsmithTraceOveragePerK) / 1000, true);
  } else {
    add(telemetry.vendor === "digithings" ? "digismith traces" : "Self-hosted traces", 0, true);
  }

  if (hosting.id === "azure") {
    add("Azure hosting", AZURE_HOSTING_ESTIMATE, true, true);
  } else {
    add("Own hardware", 0, true);
  }

  const vendors = [...new Set([model, embed, vector, telemetry, hosting].map((o) => o.vendor))].filter(
    (v) => v !== "you" && v !== "digithings",
  );
  return { setup, monthly, lines, vendors };
}

/* ── diagrams: fixed topologies, labels from the pick ─────────────────── */

const MODEL_GATEWAY: Record<string, string> = {
  sol: "OpenAI API",
  luna: "OpenAI API",
  o3: "OpenAI API",
  deepseek: "DeepSeek API",
  commandr: "Cohere API",
  local: "your API",
};

const MODEL_BOX: Record<string, string> = {
  sol: `Sol · $${RAG_PRICING.chatFlagshipInPerM}/$${RAG_PRICING.chatFlagshipOutPerM}`,
  luna: `Luna · $${RAG_PRICING.chatMidInPerM}/$${RAG_PRICING.chatMidOutPerM}`,
  o3: `o3 · $${RAG_PRICING.reasoningInPerM}/$${RAG_PRICING.reasoningOutPerM}`,
  deepseek: `DeepSeek · $${RAG_PRICING.deepseekInPerM}/$${RAG_PRICING.deepseekOutPerM}`,
  commandr: "Command R · $0.15/$0.60",
  local: "local model · $0",
};

const EMBED_BOX: Record<string, string> = {
  large: `embed-3-large · $${RAG_PRICING.embedLargePerM}/M`,
  small: `embed-3-small · $${RAG_PRICING.embedSmallPerM}/M`,
  cohere: `Cohere v4 · $${RAG_PRICING.embedCoherePerM}/M`,
  local: "local embed · $0",
};

const VECTOR_BOX: Record<string, string> = {
  pinecone: `Pinecone · $${RAG_PRICING.pineconeMinMonthly} floor`,
  qdrant: "Qdrant · ~$25",
  self: "pgvector · $0",
};

const TELEMETRY_BOX: Record<string, string> = {
  langsmith: `LangSmith · $${RAG_PRICING.langsmithSeatMonthly}/seat`,
  self: "own traces · $0",
  digismith: "digismith · $0",
};

function vendorCount(price: StackPrice): string {
  const n = price.vendors.length;
  return n === 0 ? "no vendors · no meters" : `${n} vendor${n === 1 ? "" : "s"} · ${n} meter${n === 1 ? "" : "s"}`;
}

/** Provider-side drawing: fixed traditional topology, labels from the pick. */
export function providerSpec(
  pick: StackPick,
  workload: RagWorkload = DEFAULT_WORKLOAD,
  opts: { appLabel?: string; sourcesLabel?: string; review?: boolean } = {},
): ArchSpec {
  const model = lookup(PROVIDER_LAYERS, pick, "models");
  const embed = lookup(PROVIDER_LAYERS, pick, "embeddings");
  const vector = lookup(PROVIDER_LAYERS, pick, "vector");
  const telemetry = lookup(PROVIDER_LAYERS, pick, "telemetry");
  const hosting = lookup(PROVIDER_LAYERS, pick, "hosting");
  const price = pricePick(PROVIDER_LAYERS, pick, workload);
  /* Support apps run a human review lane across the top: drafts leave the
     model for people, approvals re-enter the product. Extra box, stable ids
     everywhere else, so existing steps keep working. */
  const reviewService = opts.review
    ? [{ id: "review", label: "human review lane", icon: "server" as const, col: 1, row: 0 }]
    : [];
  const reviewEdges = opts.review
    ? [
        { from: "model", to: "review", fromSide: "B" as const, toSide: "L" as const, label: "drafts" },
        { from: "review", to: "app", fromSide: "L" as const, toSide: "T" as const, label: "approved replies" },
      ]
    : [];
  return {
    title: "Your off-the-shelf stack, as picked",
    description: "The traditional stack with the picked providers on every box.",
    groups: [{ id: "platform", label: vendorCount(price), icon: "cloud", col: 0, row: 1, cols: 3, rows: 4 }],
    services: [
      { id: "app", label: opts.appLabel ?? "your product", icon: "internet", col: 0, row: 0 },
      ...reviewService,
      { id: "sources", label: opts.sourcesLabel ?? "your data sources", icon: "database", col: 2, row: 0 },
      { id: "api", label: MODEL_GATEWAY[model.id], icon: "server", logo: model.logo, group: "platform", col: 1, row: 1 },
      { id: "model", label: MODEL_BOX[model.id], icon: "server", logo: model.logo, group: "platform", col: 0, row: 2 },
      { id: "embed", label: EMBED_BOX[embed.id], icon: "server", logo: embed.logo, group: "platform", col: 1, row: 2 },
      { id: "memory", label: VECTOR_BOX[vector.id], icon: "database", group: "platform", col: 2, row: 2 },
      { id: "record", label: hosting.id === "azure" ? "Azure Blob" : "your disk", icon: "database", group: "platform", col: 0, row: 3 },
      { id: "telemetry", label: TELEMETRY_BOX[telemetry.id], icon: "server", group: "platform", col: 1, row: 3 },
      { id: "machines", label: hosting.id === "azure" ? "Azure GPUs" : "your machines", icon: "cloud", group: "platform", col: 2, row: 3 },
      { id: "terms", label: "their terms", icon: "disk", group: "platform", col: 1, row: 4 },
    ],
    edges: [
      { from: "app", to: "api", fromSide: "B", toSide: "T", label: "one SDK" },
      { from: "sources", to: "api", fromSide: "B", toSide: "T", label: "their connectors" },
      { from: "api", to: "model", fromSide: "L", toSide: "R", label: "per-token" },
      { from: "api", to: "memory", fromSide: "R", toSide: "L", label: "per-query" },
      { from: "api", to: "embed", fromSide: "B", toSide: "T", label: "bundled in" },
      { from: "embed", to: "memory", fromSide: "R", toSide: "L", label: "their format" },
      { from: "api", to: "record", fromSide: "L", toSide: "T", label: "per-GB" },
      { from: "model", to: "telemetry", fromSide: "B", toSide: "L", label: "their dashboard" },
      { from: "memory", to: "machines", fromSide: "B", toSide: "T", label: "same roof" },
      { from: "machines", to: "terms", fromSide: "B", toSide: "L", label: "their terms" },
      ...reviewEdges,
    ],
  };
}

const DIGI_MODEL_BOX: Record<string, string> = {
  local: "digillm · local · $0",
  luna: `digillm · Luna $${RAG_PRICING.chatMidInPerM}/$${RAG_PRICING.chatMidOutPerM}`,
  deepseek: `digillm · DeepSeek $${RAG_PRICING.deepseekInPerM}/$${RAG_PRICING.deepseekOutPerM}`,
  o3: `digillm · o3 $${RAG_PRICING.reasoningInPerM}/$${RAG_PRICING.reasoningOutPerM}`,
  sol: `digillm · Sol $${RAG_PRICING.chatFlagshipInPerM}/$${RAG_PRICING.chatFlagshipOutPerM}`,
};

const DIGI_EMBED_SHORT: Record<string, string> = {
  local: "local $0",
  small: `small $${RAG_PRICING.embedSmallPerM}`,
  cohere: `cohere $${RAG_PRICING.embedCoherePerM}`,
  large: `large $${RAG_PRICING.embedLargePerM}`,
};

const DIGI_VECTOR_BOX: Record<string, string> = {
  self: "self-hosted",
  qdrant: "Qdrant ~$25",
  pinecone: "Pinecone metered",
};

const DIGI_TELEMETRY_BOX: Record<string, string> = {
  digismith: "digismith · $0",
  langsmith: "LangSmith · metered",
};

/** digithings-side drawing: module boxes, per-layer subtitles from the pick. */
export function digiSpec(
  pick: StackPick,
  workload: RagWorkload = DEFAULT_WORKLOAD,
  opts: { appLabel?: string } = {},
): ArchSpec {
  const model = lookup(DIGI_LAYERS, pick, "models");
  const embed = lookup(DIGI_LAYERS, pick, "embeddings");
  const vector = lookup(DIGI_LAYERS, pick, "vector");
  const telemetry = lookup(DIGI_LAYERS, pick, "telemetry");
  const price = pricePick(DIGI_LAYERS, pick, workload);
  return {
    title: "Your digithings build, as picked",
    description: "The same workload on digithings modules with the picked options.",
    groups: [{ id: "digithings", label: `digithings · ${vendorCount(price)}`, icon: "server", col: 0, row: 1, cols: 4, rows: 2 }],
    services: [
      { id: "app", label: opts.appLabel ?? "your product", icon: "internet", col: 1, row: 0 },
      { id: "chat", label: "digichat · chat UI", icon: "server", group: "digithings", col: 0, row: 1 },
      { id: "graph", label: "digigraph · router", icon: "server", group: "digithings", col: 1, row: 1 },
      { id: "models", label: DIGI_MODEL_BOX[model.id], icon: "server", logo: model.logo, group: "digithings", col: 2, row: 1 },
      { id: "memory", label: `digisearch · ${DIGI_VECTOR_BOX[vector.id]} · ${DIGI_EMBED_SHORT[embed.id]}`, icon: "database", group: "digithings", col: 3, row: 1 },
      { id: "vault", label: "digivault · notes vault", icon: "database", group: "digithings", col: 0, row: 2 },
      { id: "traces", label: DIGI_TELEMETRY_BOX[telemetry.id], icon: "server", group: "digithings", col: 1, row: 2 },
      { id: "claw", label: "digiclaw · scheduler", icon: "server", group: "digithings", col: 2, row: 2 },
      { id: "keys", label: "digikey · your keys", icon: "disk", group: "digithings", col: 3, row: 2 },
    ],
    edges: [
      { from: "app", to: "chat", fromSide: "B", toSide: "T", label: "HTTPS" },
      { from: "chat", to: "graph", fromSide: "R", toSide: "L", label: "SSE" },
      { from: "graph", to: "models", fromSide: "R", toSide: "L", label: "your key" },
      { from: "graph", to: "memory", fromSide: "R", toSide: "L", label: "HTTP" },
      { from: "graph", to: "vault", fromSide: "B", toSide: "T", label: "MCP" },
      { from: "models", to: "keys", fromSide: "B", toSide: "T", label: "your rates" },
      { from: "models", to: "traces", fromSide: "B", toSide: "T", label: "you see it" },
      { from: "claw", to: "graph", fromSide: "T", toSide: "B", label: "interval" },
    ],
  };
}
