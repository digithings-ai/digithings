/**
 * RAG cost model (review-only price thread, Refs #4429).
 *
 * Compares one workload — a 1GB-text RAG agent at 1k queries/day — across
 * the provider stack and three digithings states. Pure arithmetic over a
 * dated price snapshot, so every figure on the variants page traces to
 * these rates and the tests pin the math.
 *
 * Honesty rules for this file: rates are Sep-2026 list prices
 * (`researchedAt` + sources below), the workload math shows its assumptions
 * (1GB ≈ 250M tokens, 500-token chunks), results are planning estimates not
 * quotes, and self-hosted is "$0 marginal on hardware you already pay for" —
 * never "free".
 */

export interface RagPricing {
  researchedAt: string;
  sources: string[];
  /** $/M tokens. */
  embedLargePerM: number;
  embedSmallPerM: number;
  embedCoherePerM: number;
  chatFlagshipInPerM: number;
  chatFlagshipOutPerM: number;
  chatMidInPerM: number;
  chatMidOutPerM: number;
  pineconeMinMonthly: number;
  pineconeStoragePerGB: number;
  pineconeWritePerM: number;
  pineconeReadPerM: number;
  /** Qdrant Cloud entry footprint (single-source estimate, see sources). */
  qdrantEntryMonthly: number;
  langsmithSeatMonthly: number;
  langsmithIncludedTraces: number;
  langsmithTraceOveragePerK: number;
  deepseekInPerM: number;
  deepseekOutPerM: number;
  reasoningInPerM: number;
  reasoningOutPerM: number;
  /** $/GB-mo object storage. */
  s3StoragePerGB: number;
  /** Azure Blob Hot $/GB-mo (secondary-source estimate). */
  azureBlobPerGB: number;
  /** Serverless runner planning figure (covers the free grant). */
  runnerMonthly: number;
}

/**
 * One flagship row per model provider (Refs #4429).
 *
 * `source: "list"` = vendor list price; `source: "catalog"` = OpenRouter
 * live-catalog pass-through (renders with ~). Recognizable names clients
 * already buy — the point is replacement, not exhaustiveness. Refine after
 * the design lands.
 */
export interface ModelProvider {
  id: string;
  provider: string;
  model: string;
  inPerM: number;
  outPerM: number;
  source: "list" | "catalog";
  note: string;
}

export const MODEL_PROVIDERS: ModelProvider[] = [
  { id: "sol", provider: "OpenAI", model: "GPT-5.6 Sol", inPerM: 4, outPerM: 20, source: "list", note: "short-ctx list; long-ctx $8/$30; promo thru 2026-11-21" },
  { id: "opus", provider: "Anthropic", model: "Opus 5.5", inPerM: 4.5, outPerM: 20, source: "list", note: "vendor $4-5/$20-25 range midpoint" },
  { id: "gemini", provider: "Google", model: "Gemini 3.1 Pro", inPerM: 2, outPerM: 12, source: "list", note: "Vertex list; >200K ctx doubles input" },
  { id: "grok", provider: "Grok", model: "Grok 4.7", inPerM: 1.6, outPerM: 4.8, source: "catalog", note: "OpenRouter pass-through" },
  { id: "mistral", provider: "Mistral", model: "Mistral Large", inPerM: 0.5, outPerM: 1.5, source: "list", note: "vendor FAQ" },
  { id: "deepseek", provider: "DeepSeek", model: "DeepSeek V4 Pro", inPerM: 0.78, outPerM: 1.57, source: "catalog", note: "OpenRouter pass-through" },
  { id: "glm", provider: "Z.ai", model: "GLM 5.3 Prime", inPerM: 2.8, outPerM: 8.8, source: "catalog", note: "OpenRouter pass-through (z-ai prefix)" },
  { id: "minimax", provider: "MiniMax", model: "MiniMax M1", inPerM: 0.4, outPerM: 2.2, source: "catalog", note: "OpenRouter pass-through" },
  { id: "luna", provider: "OpenAI", model: "GPT-5.6 Luna", inPerM: 0.2, outPerM: 1.2, source: "list", note: "short-ctx list; cheap-managed default" },
  { id: "o3", provider: "OpenAI", model: "o3 reasoning", inPerM: 2, outPerM: 8, source: "list", note: "reasoning slot; o3-pro is 10x" },
  { id: "local", provider: "you", model: "local model", inPerM: 0, outPerM: 0, source: "list", note: "$0 marginal on your hardware" },
];

export const RAG_PRICING: RagPricing = {
  researchedAt: "2026-09-28",
  sources: [
    "platform.openai.com/docs/pricing (GPT-5.6 Sol $4/$20 short-ctx, $8/$30 long-ctx, promo thru 2026-11-21; Luna $0.20/$1.20; o3 $2/$8; embed $0.13/M large, $0.02/M small)",
    "platform.claude.com/docs (Opus 5.5 $4-5/$20-25; Sonnet 5 $2/$10)",
    "cloud.google.com Vertex pricing (Gemini 3.1 Pro $2/$12)",
    "mistral.ai/pricing FAQ (Mistral Large $0.50/$1.50)",
    "OpenRouter live catalog 2026-09-28 — Grok 4.7 $1.6/$4.8, DeepSeek V4 Pro $0.78/$1.57, GLM 5.3 Prime $2.8/$8.8, MiniMax M1 $0.4/$2.2 (pass-through, ~)",
    "pinecone.io/pricing (Standard $50 min, $0.33/GB, $4/M writes, $16/M reads)",
    "spendark.com (Qdrant Cloud ~$25/mo entry)",
    "langchain.com/pricing (Plus $39/seat, 10k traces, $2.50/1k overage)",
    "cohere.com via Azure Foundry (Embed v4 $0.12/M)",
    "aws.amazon.com/s3/pricing (S3 Standard $0.023/GB)",
    "azure.microsoft.com/pricing (Blob Hot ~$0.018/GB estimate; runner ~$75/mo planning figure)",
  ],
  embedLargePerM: 0.13,
  embedSmallPerM: 0.02,
  embedCoherePerM: 0.12,
  chatFlagshipInPerM: 4,
  chatFlagshipOutPerM: 20,
  chatMidInPerM: 0.2,
  chatMidOutPerM: 1.2,
  pineconeMinMonthly: 50,
  pineconeStoragePerGB: 0.33,
  pineconeWritePerM: 4,
  pineconeReadPerM: 16,
  qdrantEntryMonthly: 25,
  langsmithSeatMonthly: 39,
  langsmithIncludedTraces: 10000,
  langsmithTraceOveragePerK: 2.5,
  deepseekInPerM: 0.78,
  deepseekOutPerM: 1.57,
  reasoningInPerM: 2,
  reasoningOutPerM: 8,
  s3StoragePerGB: 0.023,
  azureBlobPerGB: 0.018,
  runnerMonthly: 75,
};

export interface RagWorkload {
  /** Text corpus, GB. */
  corpusGB: number;
  chunkTokens: number;
  queriesPerDay: number;
  queryEmbedTokens: number;
  chatInTokensPerQuery: number;
  chatOutTokensPerQuery: number;
}

export const DEFAULT_WORKLOAD: RagWorkload = {
  corpusGB: 1,
  chunkTokens: 500,
  queriesPerDay: 1000,
  queryEmbedTokens: 2000,
  chatInTokensPerQuery: 8000,
  chatOutTokensPerQuery: 1500,
};

/** 1 token ≈ 4 chars of English text. */
export const TOKENS_PER_GB = 250_000_000;
const BYTES_PER_DIM = 4;
const DAYS_PER_MONTH = 30;

export type RagState = "provider" | "dg-self" | "dg-cheap" | "dg-flagship";

export const RAG_STATES: { id: RagState; label: string; note: string }[] = [
  { id: "provider", label: "Provider stack", note: "OpenAI large + Pinecone + Sol + LangSmith" },
  { id: "dg-self", label: "digithings · self-hosted", note: "Local models + vectors + traces, your hardware" },
  { id: "dg-cheap", label: "digithings · cheap managed", note: "Small embeddings + Qdrant + mid-tier routing" },
  { id: "dg-flagship", label: "digithings · flagship routed", note: "Same Sol + Pinecone, own traces" },
];

export interface RagLine {
  label: string;
  amount: number;
}

export interface RagCost {
  setup: number;
  monthly: number;
  lines: RagLine[];
}

const DAYS = DAYS_PER_MONTH;

function pineconeBill(
  vectors: number,
  dims: number,
  queriesPerMonth: number,
  p: RagPricing,
): { storage: number; reads: number; total: number } {
  const gb = (vectors * dims * BYTES_PER_DIM) / 1e9;
  const storage = gb * p.pineconeStoragePerGB;
  const ruPerQuery = Math.max(0.25, gb);
  const reads = ((queriesPerMonth * ruPerQuery * p.pineconeReadPerM) / 1e6);
  return { storage, reads, total: Math.max(p.pineconeMinMonthly, storage + reads) };
}

function langsmithBill(tracesPerMonth: number, p: RagPricing): number {
  const over = Math.max(0, tracesPerMonth - p.langsmithIncludedTraces);
  return p.langsmithSeatMonthly + (over * p.langsmithTraceOveragePerK) / 1000;
}

/**
 * Setup (one-time index build) + monthly run cost for a state. Every line is
 * derived from `workload` and `pricing` — no hidden constants.
 */
export function ragCost(
  state: RagState,
  workload: RagWorkload = DEFAULT_WORKLOAD,
  pricing: RagPricing = RAG_PRICING,
): RagCost {
  const corpusTokens = workload.corpusGB * TOKENS_PER_GB;
  const vectors = corpusTokens / workload.chunkTokens;
  const queriesPerMonth = workload.queriesPerDay * DAYS;
  const lines: RagLine[] = [];
  let setup = 0;
  let monthly = 0;
  const add = (label: string, amount: number, recurring: boolean) => {
    lines.push({ label, amount });
    if (recurring) monthly += amount;
    else setup += amount;
  };

  if (state === "dg-self") {
    add("Embed corpus locally", 0, false);
    add("Vectors on your Postgres", 0, true);
    add("Local model answers", 0, true);
    add("digismith traces", 0, true);
    return { setup, monthly, lines };
  }

  const embedPerM =
    state === "provider" || state === "dg-flagship" ? pricing.embedLargePerM : pricing.embedSmallPerM;
  const dims = state === "dg-cheap" ? 1536 : 3072;
  add("Embed corpus", (corpusTokens * embedPerM) / 1e6, false);

  if (state === "dg-cheap") {
    add("Qdrant Cloud entry", pricing.qdrantEntryMonthly, true);
  } else {
    const pinecone = pineconeBill(vectors, dims, queriesPerMonth, pricing);
    add("Pinecone writes (one-time)", ((vectors * pricing.pineconeWritePerM) / 1e6), false);
    add(`Pinecone store + reads (min $${pricing.pineconeMinMonthly})`, pinecone.total, true);
  }

  const queryEmbedTokens = queriesPerMonth * workload.queryEmbedTokens;
  add("Query embeddings", (queryEmbedTokens * embedPerM) / 1e6, true);

  const chatIn = queriesPerMonth * workload.chatInTokensPerQuery;
  const chatOut = queriesPerMonth * workload.chatOutTokensPerQuery;
  const inPerM = state === "dg-cheap" ? pricing.chatMidInPerM : pricing.chatFlagshipInPerM;
  const outPerM = state === "dg-cheap" ? pricing.chatMidOutPerM : pricing.chatFlagshipOutPerM;
  add("Model answers", (chatIn * inPerM + chatOut * outPerM) / 1e6, true);

  add(
    state === "provider" ? "LangSmith (1 seat + traces)" : "digismith traces",
    state === "provider" ? langsmithBill(queriesPerMonth, pricing) : 0,
    true,
  );
  return { setup, monthly, lines };
}

/** Scale corpus and usage together by `factor` (the explode knob). */
export function scaleWorkload(workload: RagWorkload, factor: number): RagWorkload {
  return {
    ...workload,
    corpusGB: workload.corpusGB * factor,
    queriesPerDay: workload.queriesPerDay * factor,
  };
}
