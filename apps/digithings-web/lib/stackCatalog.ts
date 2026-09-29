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
 * are single-source planning figures and render with a ~ prefix in the
 * price table. Hosts, tracers and mail vendors without a sourced rate are
 * still choosable — the table shows them as unpriced, never as $0.
 * Dropdown labels carry no prices; the table owns that.
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
  /** Menu name. Prices stay in the price table, never here. */
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
      { id: "sol", label: "GPT-5.6 Sol", vendor: "OpenAI", logo: "openai" },
      { id: "opus", label: "Opus 5.5", vendor: "Anthropic" },
      { id: "gemini", label: "Gemini 3.1 Pro", vendor: "Google" },
      { id: "grok", label: "Grok 4.7", vendor: "Grok", estimate: true },
      { id: "mistral", label: "Mistral Large", vendor: "Mistral" },
      { id: "deepseek", label: "DeepSeek V4", vendor: "DeepSeek", estimate: true },
      { id: "glm", label: "GLM 5.3", vendor: "Z.ai", estimate: true },
      { id: "minimax", label: "MiniMax M1", vendor: "MiniMax", estimate: true },
      { id: "luna", label: "GPT-5.6 Luna", vendor: "OpenAI", logo: "openai" },
      { id: "o3", label: "o3 reasoning", vendor: "OpenAI", logo: "openai" },
      { id: "local", label: "Self-hosted", vendor: "you" },
    ],
  },
  {
    id: "embeddings",
    label: "Embeddings",
    options: [
      { id: "large", label: "embed-3-large", vendor: "OpenAI", logo: "openai" },
      { id: "small", label: "embed-3-small", vendor: "OpenAI", logo: "openai" },
      { id: "cohere", label: "Cohere v4", vendor: "Cohere" },
      { id: "local", label: "Self-hosted", vendor: "you" },
    ],
  },
  {
    id: "vector",
    label: "Vector store",
    options: [
      { id: "pinecone", label: "Pinecone", vendor: "Pinecone" },
      { id: "qdrant", label: "Qdrant Cloud", vendor: "Qdrant", estimate: true },
      { id: "self", label: "Self-hosted pgvector", vendor: "you" },
    ],
  },
  {
    id: "telemetry",
    label: "Telemetry",
    options: [
      { id: "langsmith", label: "LangSmith", vendor: "LangSmith" },
      { id: "langfuse", label: "Langfuse", vendor: "Langfuse" },
      { id: "helicone", label: "Helicone", vendor: "Helicone" },
      { id: "braintrust", label: "Braintrust", vendor: "Braintrust" },
      { id: "arize", label: "Arize Phoenix", vendor: "Arize" },
      { id: "datadog", label: "Datadog", vendor: "Datadog" },
      { id: "self", label: "Self-hosted traces", vendor: "you" },
    ],
  },
  {
    id: "hosting",
    label: "Hosting",
    options: [
      { id: "azure", label: "Azure", vendor: "Azure", estimate: true },
      { id: "aws", label: "AWS", vendor: "AWS" },
      { id: "gcp", label: "Google Cloud", vendor: "Google" },
      { id: "cloudflare", label: "Cloudflare", vendor: "Cloudflare" },
      { id: "fly", label: "Fly.io", vendor: "Fly.io" },
      { id: "railway", label: "Railway", vendor: "Railway" },
      { id: "own", label: "Own hardware", vendor: "you" },
    ],
  },
];

/** Delivery vendors on the support graph. Unpriced: no sourced send rate. */
export const EMAIL_OPTIONS: LayerOption[] = [
  { id: "sendgrid", label: "SendGrid", vendor: "Twilio" },
  { id: "postmark", label: "Postmark", vendor: "Postmark" },
  { id: "resend", label: "Resend", vendor: "Resend" },
  { id: "mailgun", label: "Mailgun", vendor: "Mailgun" },
  { id: "ses", label: "Amazon SES", vendor: "Amazon" },
  { id: "smtp", label: "Your SMTP", vendor: "you" },
];

export function emailBoxLabel(id: string): string {
  return EMAIL_OPTIONS.find((option) => option.id === id)?.label ?? "SendGrid";
}

export const DIGI_LAYERS: Layer[] = [
  {
    id: "models",
    label: "Models via digillm",
    options: [
      { id: "local", label: "Local", vendor: "you" },
      { id: "luna", label: "Luna", vendor: "OpenAI", logo: "openai" },
      { id: "mistral", label: "Mistral Large", vendor: "Mistral" },
      { id: "deepseek", label: "DeepSeek V4", vendor: "DeepSeek", estimate: true },
      { id: "minimax", label: "MiniMax M1", vendor: "MiniMax", estimate: true },
      { id: "grok", label: "Grok 4.7", vendor: "Grok", estimate: true },
      { id: "o3", label: "o3", vendor: "OpenAI", logo: "openai" },
      { id: "gemini", label: "Gemini 3.1 Pro", vendor: "Google" },
      { id: "glm", label: "GLM 5.3", vendor: "Z.ai", estimate: true },
      { id: "opus", label: "Opus 5.5", vendor: "Anthropic" },
      { id: "sol", label: "Sol", vendor: "OpenAI", logo: "openai" },
    ],
  },
  {
    id: "embeddings",
    label: "Embeddings",
    options: [
      { id: "local", label: "Local", vendor: "you" },
      { id: "small", label: "small", vendor: "OpenAI", logo: "openai" },
      { id: "cohere", label: "Cohere v4", vendor: "Cohere" },
      { id: "large", label: "large", vendor: "OpenAI", logo: "openai" },
    ],
  },
  {
    id: "vector",
    label: "Vector store",
    options: [
      { id: "self", label: "Self-hosted", vendor: "you" },
      { id: "qdrant", label: "Qdrant Cloud", vendor: "Qdrant", estimate: true },
      { id: "pinecone", label: "Pinecone", vendor: "Pinecone" },
    ],
  },
  {
    id: "telemetry",
    label: "Telemetry",
    options: [
      { id: "digismith", label: "digismith", vendor: "digithings" },
      { id: "langsmith", label: "LangSmith", vendor: "LangSmith" },
      { id: "langfuse", label: "Langfuse", vendor: "Langfuse" },
      { id: "helicone", label: "Helicone", vendor: "Helicone" },
      { id: "braintrust", label: "Braintrust", vendor: "Braintrust" },
      { id: "arize", label: "Arize Phoenix", vendor: "Arize" },
      { id: "datadog", label: "Datadog", vendor: "Datadog" },
    ],
  },
  {
    id: "hosting",
    label: "Hosting",
    options: [
      { id: "own", label: "Own hardware", vendor: "you" },
      { id: "azure", label: "Azure", vendor: "Azure", estimate: true },
      { id: "aws", label: "AWS", vendor: "AWS" },
      { id: "gcp", label: "Google Cloud", vendor: "Google" },
      { id: "cloudflare", label: "Cloudflare", vendor: "Cloudflare" },
      { id: "fly", label: "Fly.io", vendor: "Fly.io" },
      { id: "railway", label: "Railway", vendor: "Railway" },
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
  opus: { inPerM: 4.5, outPerM: 20 },
  gemini: { inPerM: 2, outPerM: 12 },
  grok: { inPerM: 1.6, outPerM: 4.8 },
  mistral: { inPerM: 0.5, outPerM: 1.5 },
  glm: { inPerM: 2.8, outPerM: 8.8 },
  minimax: { inPerM: 0.4, outPerM: 2.2 },
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
  layer: LayerId;
  /** False for one-time lines (corpus embedding); true for monthly meters. */
  recurring: boolean;
  /** No sourced rate. Excluded from totals; the table renders an em dash. */
  unpriced?: boolean;
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
 * Setup + monthly for a five-layer pick. Formulas mirror `ragCost`
 * (same workload, same snapshot); the cross-check test pins the default
 * provider pick to the invoice panel's provider number plus hosting.
 * Topologies without vector indexing (support, finance) omit the
 * embeddings + vector lines entirely — no zero-priced filler.
 */
export function pricePick(
  layers: Layer[],
  pick: StackPick,
  workload: RagWorkload = DEFAULT_WORKLOAD,
  topology?: "rag" | "support" | "finance",
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
  const add = (
    label: string,
    amount: number,
    recurring: boolean,
    layer: LayerId,
    estimate?: boolean,
    unpriced?: boolean,
  ) => {
    lines.push({ label, amount: unpriced ? 0 : amount, estimate, layer, recurring, unpriced });
    if (unpriced) return;
    if (recurring) monthly += amount;
    else setup += amount;
  };

  const corpusTokens = workload.corpusGB * TOKENS_PER_GB;
  const vectors = corpusTokens / workload.chunkTokens;
  const queriesPerMonth = workload.queriesPerDay * 30;
  const noVectors = topology === "support" || topology === "finance";

  if (!noVectors) {
    const embedRate = EMBED_RATES[embed.id];
    add(`Embed corpus · ${embed.label}`, (corpusTokens * embedRate.perM) / 1e6, false, "embeddings", embed.estimate);

    if (vector.id === "pinecone") {
      const gb = (vectors * embedRate.dims * 4) / 1e9;
      add("Pinecone writes", ((vectors * p.pineconeWritePerM) / 1e6), false, "vector");
      const ruPerQuery = Math.max(0.25, gb);
      const usage = gb * p.pineconeStoragePerGB + ((queriesPerMonth * ruPerQuery * p.pineconeReadPerM) / 1e6);
      add("Pinecone store + reads", Math.max(p.pineconeMinMonthly, usage), true, "vector");
    } else if (vector.id === "qdrant") {
      add("Qdrant Cloud", p.qdrantEntryMonthly, true, "vector", true);
    } else {
      add("Self-hosted vectors", 0, true, "vector");
    }

    const queryEmbedTokens = queriesPerMonth * workload.queryEmbedTokens;
    add(`Query embeddings · ${embed.label}`, (queryEmbedTokens * embedRate.perM) / 1e6, true, "embeddings", embed.estimate);
  }

  const chatIn = queriesPerMonth * workload.chatInTokensPerQuery;
  const chatOut = queriesPerMonth * workload.chatOutTokensPerQuery;
  const rates = MODEL_RATES[model.id];
  add(`Model answers · ${model.label}`, (chatIn * rates.inPerM + chatOut * rates.outPerM) / 1e6, true, "models", model.estimate);

  if (telemetry.id === "langsmith") {
    const over = Math.max(0, queriesPerMonth - p.langsmithIncludedTraces);
    add("LangSmith", p.langsmithSeatMonthly + (over * p.langsmithTraceOveragePerK) / 1000, true, "telemetry");
  } else if (telemetry.id === "self" || telemetry.id === "digismith") {
    add(telemetry.vendor === "digithings" ? "digismith traces" : "Self-hosted traces", 0, true, "telemetry");
  } else {
    add(telemetry.label, 0, true, "telemetry", false, true);
  }

  if (hosting.id === "azure") {
    add("Azure hosting", AZURE_HOSTING_ESTIMATE, true, "hosting", true);
  } else if (hosting.id === "own") {
    add("Own hardware", 0, true, "hosting");
  } else {
    add(hosting.label, 0, true, "hosting", false, true);
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
  opus: "Anthropic API",
  gemini: "Google API",
  grok: "Grok API",
  mistral: "Mistral API",
  glm: "Z.ai API",
  minimax: "MiniMax API",
  local: "your API",
};

const MODEL_BOX: Record<string, string> = {
  sol: "Sol",
  luna: "Luna",
  o3: "o3 reasoning",
  deepseek: "DeepSeek V4",
  opus: "Opus 5.5",
  gemini: "Gemini 3.1 Pro",
  grok: "Grok 4.7",
  mistral: "Mistral Large",
  glm: "GLM 5.3",
  minimax: "MiniMax M1",
  local: "local model",
};

const EMBED_BOX: Record<string, string> = {
  large: "embed-3-large",
  small: "embed-3-small",
  cohere: "Cohere v4",
  local: "local embed",
};

const VECTOR_BOX: Record<string, string> = {
  pinecone: "Pinecone",
  qdrant: "Qdrant",
  self: "pgvector",
};

const TELEMETRY_BOX: Record<string, string> = {
  langsmith: "LangSmith",
  langfuse: "Langfuse",
  helicone: "Helicone",
  braintrust: "Braintrust",
  arize: "Arize",
  datadog: "Datadog",
  self: "own traces",
  digismith: "digismith",
};

/** Short box names. Menu labels can be longer; a box has about 14 characters. */
const HOST_LAKE: Record<string, string> = {
  azure: "Azure lake",
  aws: "S3 lake",
  gcp: "GCS lake",
  cloudflare: "R2 lake",
  fly: "Fly volume",
  railway: "Railway disk",
  own: "your lake",
};
const HOST_GPU: Record<string, string> = {
  azure: "Azure GPUs",
  aws: "AWS GPUs",
  gcp: "GCP GPUs",
  cloudflare: "CF Workers",
  fly: "Fly machines",
  railway: "Railway",
  own: "your GPUs",
};
const HOST_RUNNER: Record<string, string> = {
  azure: "Azure runner",
  aws: "AWS runner",
  gcp: "GCP runner",
  cloudflare: "CF Workers",
  fly: "Fly runner",
  railway: "Railway",
  own: "your runner",
};
const HOST_ARCHIVE: Record<string, string> = {
  azure: "Azure archive",
  aws: "S3 archive",
  gcp: "GCS archive",
  cloudflare: "R2 archive",
  fly: "Fly archive",
  railway: "Railway",
  own: "your archive",
};

function hostBox(map: Record<string, string>, id: string): string {
  return map[id] ?? id;
}

/** A box fits about 14 monospace characters before the label wraps onto the glyph. */
function fitBox(preferred: string, fallback: string): string {
  return preferred.length <= 14 ? preferred : fallback;
}

function vendorCount(price: StackPrice): string {
  const n = price.vendors.length;
  return n === 0 ? "no vendors · no meters" : `${n} vendor${n === 1 ? "" : "s"} · ${n} meter${n === 1 ? "" : "s"}`;
}

/** Provider-side drawing: one topology per app, labels from the pick. */
export function providerSpec(
  pick: StackPick,
  workload: RagWorkload = DEFAULT_WORKLOAD,
  opts: {
    appLabel?: string;
    sourcesLabel?: string;
    topology?: "rag" | "support" | "finance";
    /** Support delivery box. Defaults to SendGrid. */
    emailId?: string;
  } = {},
): ArchSpec {
  const model = lookup(PROVIDER_LAYERS, pick, "models");
  const embed = lookup(PROVIDER_LAYERS, pick, "embeddings");
  const vector = lookup(PROVIDER_LAYERS, pick, "vector");
  const telemetry = lookup(PROVIDER_LAYERS, pick, "telemetry");
  const hosting = lookup(PROVIDER_LAYERS, pick, "hosting");
  const topology = opts.topology ?? "rag";
  const price = pricePick(PROVIDER_LAYERS, pick, workload, topology);
  const head =
    topology === "finance"
      ? [
          { id: "app", label: opts.appLabel ?? "research agent", icon: "internet" as const, col: 0, row: 0 },
          /* Twin scattered endpoints, one empty column between agent and
             feeds so the scatter is drawn. opts.sourcesLabel is ignored
             here: the fan-in signature needs two static boxes. */
          { id: "feeds", label: "price feeds", icon: "database" as const, col: 2, row: 0 },
          { id: "filings", label: "filings + news", icon: "database" as const, col: 3, row: 0 },
          { id: "api", label: MODEL_GATEWAY[model.id], icon: "server" as const, logo: model.logo, group: "platform", col: 1, row: 1 },
        ]
      : [
          { id: "app", label: opts.appLabel ?? "your product", icon: "internet" as const, col: 0, row: 0 },
          { id: "sources", label: opts.sourcesLabel ?? "your sources", icon: "database" as const, col: 2, row: 0 },
          { id: "api", label: MODEL_GATEWAY[model.id], icon: "server" as const, logo: model.logo, group: "platform", col: 1, row: 1 },
        ];
  const tail =
    topology === "support"
      ? {
          /* Send pipeline: model -> review gate -> delivery, all on row 2.
             The review box sits ON the send path (eyes before send), not
             parked in the top row. No vector boxes by design. */
          rows: 3 as const,
          services: [
            { id: "model", label: MODEL_BOX[model.id], icon: "server" as const, logo: model.logo, group: "platform", col: 0, row: 2 },
            { id: "review", label: "human review", icon: "server" as const, group: "platform", col: 1, row: 2 },
            { id: "email", label: emailBoxLabel(opts.emailId ?? "sendgrid"), icon: "server" as const, group: "platform", col: 2, row: 2 },
            { id: "launcher", label: hostBox(HOST_RUNNER, hosting.id), icon: "cloud" as const, group: "platform", col: 0, row: 3 },
            { id: "telemetry", label: TELEMETRY_BOX[telemetry.id] ?? telemetry.label, icon: "server" as const, group: "platform", col: 1, row: 3 },
            { id: "terms", label: "their terms", icon: "disk" as const, group: "platform", col: 2, row: 3 },
          ],
          edges: [
            { from: "app", to: "api", fromSide: "B" as const, toSide: "T" as const, label: "one SDK" },
            { from: "sources", to: "api", fromSide: "B" as const, toSide: "T" as const, label: "their connectors" },
            { from: "api", to: "model", fromSide: "L" as const, toSide: "R" as const, label: "per-token" },
            { from: "launcher", to: "model", fromSide: "T" as const, toSide: "B" as const, label: "scheduled" },
            { from: "model", to: "review", fromSide: "R" as const, toSide: "L" as const, label: "needs eyes" },
            { from: "review", to: "email", fromSide: "R" as const, toSide: "L" as const, label: "approved send" },
            { from: "model", to: "telemetry", fromSide: "B" as const, toSide: "T" as const, label: "every draft" },
            { from: "email", to: "terms", fromSide: "B" as const, toSide: "T" as const, label: "their terms" },
          ],
        }
      : topology === "finance"
        ? {
            /* Batch pipeline, 4 wide: the clock fires left-to-right
               (launcher -> model -> dead-end archive) while twin sources
               fan into one gateway. No embedding boxes by design; the
               empty centre lane is the contrast with RAG. */
            rows: 3 as const,
            services: [
              { id: "launcher", label: hostBox(HOST_RUNNER, hosting.id), icon: "cloud" as const, group: "platform", col: 0, row: 2 },
              { id: "model", label: MODEL_BOX[model.id], icon: "server" as const, logo: model.logo, group: "platform", col: 1, row: 2 },
              { id: "record", label: hostBox(HOST_ARCHIVE, hosting.id), icon: "database" as const, group: "platform", col: 3, row: 2 },
              { id: "telemetry", label: TELEMETRY_BOX[telemetry.id] ?? telemetry.label, icon: "server" as const, group: "platform", col: 1, row: 3 },
              { id: "terms", label: "their terms", icon: "disk" as const, group: "platform", col: 3, row: 3 },
            ],
            edges: [
              { from: "app", to: "api", fromSide: "B" as const, toSide: "T" as const, label: "one SDK" },
              { from: "feeds", to: "api", fromSide: "B" as const, toSide: "T" as const, label: "many formats" },
              { from: "filings", to: "api", fromSide: "B" as const, toSide: "T" as const, label: "many meters" },
              { from: "api", to: "model", fromSide: "B" as const, toSide: "T" as const, label: "per-token reasoning" },
              { from: "launcher", to: "model", fromSide: "R" as const, toSide: "L" as const, label: "nightly runs" },
              { from: "model", to: "record", fromSide: "R" as const, toSide: "L" as const, label: "archive write" },
              { from: "model", to: "telemetry", fromSide: "B" as const, toSide: "T" as const, label: "every run" },
              { from: "api", to: "terms", fromSide: "R" as const, toSide: "L" as const, label: "their terms" },
            ],
          }
        : {
            /* Two-phase fork/join: embed -> memory -> model read left to
               right on row 2 (ingest, retrieve, generate) while the lake,
               GPU pool and traces each take a straight vertical drop on
               row 3. Role suffixes stay inline in this branch so the
               shared maps (and parallel topologies) are untouched. */
            rows: 4 as const,
            services: [
              { id: "embed", label: EMBED_BOX[embed.id], icon: "server" as const, logo: embed.logo, group: "platform", col: 0, row: 2 },
              { id: "memory", label: `${VECTOR_BOX[vector.id]} index`, icon: "database" as const, group: "platform", col: 1, row: 2 },
              { id: "model", label: fitBox(`${MODEL_BOX[model.id]} chat`, MODEL_BOX[model.id]), icon: "server" as const, logo: model.logo, group: "platform", col: 2, row: 2 },
              { id: "record", label: hostBox(HOST_LAKE, hosting.id), icon: "database" as const, group: "platform", col: 0, row: 3 },
              { id: "machines", label: hostBox(HOST_GPU, hosting.id), icon: "cloud" as const, group: "platform", col: 1, row: 3 },
              { id: "telemetry", label: TELEMETRY_BOX[telemetry.id] ?? telemetry.label, icon: "server" as const, group: "platform", col: 2, row: 3 },
              { id: "terms", label: "their terms", icon: "disk" as const, group: "platform", col: 1, row: 4 },
            ],
            edges: [
              { from: "app", to: "api", fromSide: "B" as const, toSide: "T" as const, label: "one SDK" },
              { from: "sources", to: "api", fromSide: "B" as const, toSide: "T" as const, label: "their connectors" },
              { from: "api", to: "embed", fromSide: "L" as const, toSide: "T" as const, label: "embed query" },
              { from: "api", to: "memory", fromSide: "B" as const, toSide: "T" as const, label: "top-k lookup" },
              { from: "embed", to: "memory", fromSide: "R" as const, toSide: "L" as const, label: "their format" },
              { from: "memory", to: "model", fromSide: "R" as const, toSide: "L" as const, label: "chunks" },
              { from: "record", to: "embed", fromSide: "T" as const, toSide: "B" as const, label: "raw chunks" },
              { from: "model", to: "telemetry", fromSide: "B" as const, toSide: "T" as const, label: "every answer" },
              { from: "memory", to: "machines", fromSide: "B" as const, toSide: "T" as const, label: "same roof" },
              { from: "machines", to: "terms", fromSide: "B" as const, toSide: "T" as const, label: "their terms" },
            ],
          };
  return {
    title: "Your off-the-shelf stack, as picked",
    description: "The traditional stack with the picked providers on every box.",
    groups: [{ id: "platform", label: vendorCount(price), icon: "cloud", col: 0, row: 1, cols: topology === "finance" ? 4 : 3, rows: tail.rows }],
    services: [...head, ...tail.services],
    edges: tail.edges,
  };
}

/* ── morph: the same provider topology, swapped service by service ──── */

export interface MorphState {
  /** Layers whose edge rewrites have fired (invoice rows cut on the same beat). */
  replaced: LayerId[];
  /** Box ids whose labels have flipped. Finer than layers: finance flips the
      runner and the archive on separate beats sharing the hosting row. */
  boxes: string[];
  /** Support send box flips to the in-graph mail tool (unpriced, diagram-only). */
  email?: boolean;
}

/** Edge-label rewrites applied when their layer has been swapped. Old meter
    verbs become owned verbs; untouched edges (sources, review, SDK) stay. */
const MORPH_EDGE_OVERRIDES: Record<LayerId, Record<string, string>> = {
  models: {
    "per-token": "your rates",
    "per-token reasoning": "your rates",
    "their terms": "your keys",
  },
  embeddings: { "embed query": "your query" },
  vector: { "top-k lookup": "local recall", "their format": "open format" },
  telemetry: { "every answer": "you see it", "every draft": "you see it", "every run": "you see it" },
  hosting: {
    "raw chunks": "your chunks",
    "same roof": "your roof",
    scheduled: "interval",
    "nightly runs": "interval",
  },
};

/* The send beat flips only the delivery box: review→email keeps its
   approved-send edge, because approval still happens. */

/**
 * The morph drawing: provider topology with swapped labels for the flipped
 * boxes. Box ids never move, so the walk, spotlight and camera keep working;
 * the group boundary keeps the provider vendor count (it names the stack
 * being left). Unflipped boxes render exactly their provider labels; edge
 * rewrites still follow replaced layers.
 */
export function morphSpec(
  providerPick: StackPick,
  digiPick: StackPick,
  workload: RagWorkload = DEFAULT_WORKLOAD,
  opts: {
    appLabel?: string;
    sourcesLabel?: string;
    topology?: "rag" | "support" | "finance";
    replaced?: LayerId[];
    boxes?: string[];
    email?: boolean;
    emailId?: string;
    /** The finished drawing: the group names the digithings picks and the
        sources edge is yours, not the boundary being left. */
    owned?: boolean;
  } = {},
): ArchSpec {
  const topology = opts.topology ?? "rag";
  const replaced = new Set(opts.replaced ?? []);
  const swapped = new Set(opts.boxes ?? []);
  const base = providerSpec(providerPick, workload, {
    appLabel: opts.appLabel,
    sourcesLabel: opts.sourcesLabel,
    topology,
    emailId: opts.emailId,
  });
  const dModel = lookup(DIGI_LAYERS, digiPick, "models");
  const dEmbed = lookup(DIGI_LAYERS, digiPick, "embeddings");
  const dVector = lookup(DIGI_LAYERS, digiPick, "vector");
  const dTelemetry = lookup(DIGI_LAYERS, digiPick, "telemetry");
  const dHosting = lookup(DIGI_LAYERS, digiPick, "hosting");

  const labelFor = (id: string): { label: string; logo?: string } | null => {
    switch (id) {
      case "api":
        return swapped.has("api") ? { label: "digillm gateway" } : null;
      case "model":
        return swapped.has("model")
          ? { label: DIGI_MODEL_BOX[dModel.id], logo: dModel.logo }
          : null;
      case "embed":
        return swapped.has("embed")
          ? { label: `${DIGI_EMBED_SHORT[dEmbed.id]} embed`, logo: dEmbed.logo }
          : null;
      case "memory":
        return swapped.has("memory") ? { label: `${DIGI_VECTOR_BOX[dVector.id]} index` } : null;
      case "record":
        if (!swapped.has("record")) return null;
        if (dHosting.id === "own") {
          return { label: topology === "finance" ? "digivault archive" : "digivault lake" };
        }
        return { label: topology === "finance" ? hostBox(HOST_ARCHIVE, dHosting.id) : hostBox(HOST_LAKE, dHosting.id) };
      case "machines":
        if (!swapped.has("machines")) return null;
        return { label: dHosting.id === "own" ? "your GPUs" : hostBox(HOST_GPU, dHosting.id) };
      case "launcher":
        if (!swapped.has("launcher")) return null;
        return { label: dHosting.id === "own" ? "digiclaw runner" : hostBox(HOST_RUNNER, dHosting.id) };
      case "telemetry":
        return swapped.has("telemetry")
          ? { label: TELEMETRY_BOX[dTelemetry.id] ?? dTelemetry.label }
          : null;
      case "email":
        return opts.email ? { label: "digigraph mail" } : null;
      case "terms":
        return swapped.has("terms") ? { label: "your keys" } : null;
      default:
        return null;
    }
  };

  const services = base.services.map((s) => {
    const swap = labelFor(s.id);
    if (!swap) return s;
    const next = { ...s, label: swap.label };
    if (swap.logo) next.logo = swap.logo;
    else delete next.logo;
    return next;
  });

  const tables = [...replaced].map((l) => MORPH_EDGE_OVERRIDES[l]);
  if (opts.owned) tables.push({ "their connectors": "your connectors" });
  const edges = base.edges.map((e) => {
    if (!("label" in e) || typeof e.label !== "string") return e;
    for (const table of tables) {
      const next = table[e.label];
      if (next) return { ...e, label: next };
    }
    return e;
  });

  return {
    ...base,
    title: "The same stack, swapped service by service",
    description: "Each replacement moves a box — and its invoice row — to digithings.",
    ...(opts.owned
      ? {
          groups: base.groups?.map((g) => ({
            ...g,
            label: `digithings · ${vendorCount(pricePick(DIGI_LAYERS, digiPick, workload, topology))}`,
          })),
        }
      : {}),
    services,
    edges,
  };
};

const DIGI_MODEL_BOX: Record<string, string> = {
  local: "digillm · local",
  luna: "digillm · Luna",
  mistral: "digillm · Mistral Large",
  deepseek: "digillm · DeepSeek",
  minimax: "digillm · MiniMax",
  grok: "digillm · Grok",
  o3: "digillm · o3",
  gemini: "digillm · Gemini",
  glm: "digillm · GLM",
  opus: "digillm · Opus",
  sol: "digillm · Sol",
};

const DIGI_EMBED_SHORT: Record<string, string> = {
  local: "local",
  small: "small",
  cohere: "cohere",
  large: "large",
};

const DIGI_VECTOR_BOX: Record<string, string> = {
  self: "self-hosted",
  qdrant: "Qdrant",
  pinecone: "Pinecone",
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
      { id: "traces", label: TELEMETRY_BOX[telemetry.id] ?? telemetry.label, icon: "server", group: "digithings", col: 1, row: 2 },
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
