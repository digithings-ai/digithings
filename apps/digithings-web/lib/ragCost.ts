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
}

export const RAG_PRICING: RagPricing = {
  researchedAt: "2026-09-28",
  sources: [
    "developers.openai.com (embed $0.13/M large, $0.02/M small)",
    "usagepricing.com (GPT-5.6 Sol $5 in / $30 out; Luna $0.20 / $1.20)",
    "pinecone.io/pricing (Standard $50 min, $0.33/GB, $4/M writes, $16/M reads)",
    "spendark.com (Qdrant Cloud ~$25/mo entry)",
    "langchain.com/pricing (Plus $39/seat, 10k traces, $2.50/1k overage)",
    "cohere.com via Azure Foundry (Embed v4 $0.12/M)",
  ],
  embedLargePerM: 0.13,
  embedSmallPerM: 0.02,
  embedCoherePerM: 0.12,
  chatFlagshipInPerM: 5,
  chatFlagshipOutPerM: 30,
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
