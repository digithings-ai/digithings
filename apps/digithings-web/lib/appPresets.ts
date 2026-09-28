/**
 * App-first presets for the single variant (Refs #4429).
 *
 * Three apps, each with its own workload, provider defaults, digithings
 * defaults, one recommended digithings stack, dimmed boxes and top-box
 * labels. The guided walk keeps stable box ids across apps, so the tour
 * mechanics never change — only the left steps carry per-app wording where
 * the numbers or the story differ (RAG reuses the Study D walk verbatim).
 */

import type { TourStep } from "@digithings/ui";
import { TRADITIONAL_STEPS } from "@/lib/whyLeftStudy";
import type { RagWorkload } from "@/lib/ragCost";
import type { StackPick } from "@/lib/stackCatalog";

export interface AppPreset {
  id: string;
  tab: string;
  subhead: string;
  workload: RagWorkload;
  providerDefaults: StackPick;
  digiDefaults: StackPick;
  recommended: StackPick;
  recommendedNote: string;
  dimmedProvider: string[];
  dimmedDigi: string[];
  providerApp: string;
  digiApp: string;
  leftSteps: TourStep[];
}

const FULL = ["app", "sources", "api", "model", "embed", "memory", "record", "telemetry", "machines", "terms", "platform"];

const supportLeft: TourStep[] = [
  {
    id: "yours",
    label: "Your tickets, your docs — their everything else.",
    line: "The top row is the only part you hold: the ticket queue and the product docs. But drafts can only be written through their connectors, on their terms.",
    ids: ["app", "sources"],
  },
  {
    id: "door",
    label: "One door in: the OpenAI API.",
    line: "A single gateway fronts triage, drafting and audit alike. Its SDK version, limits and prices move on a schedule you don't set — and every layer below is reachable only through it.",
    ids: ["app", "sources", "api"],
  },
  {
    id: "locked",
    label: "Locked in at the embedding layer.",
    line: "Ticket history lives in Pinecone, but the pipeline only speaks embed-3-large — switching models means re-embedding years of tickets. That is the lock-in that actually bites, long before the contract does.",
    ids: ["api", "model", "embed", "memory"],
  },
  {
    id: "metered",
    label: "LangSmith watches at $39 a seat; Azure bills the rest.",
    line: "Every draft is a trace at $2.50 per thousand past the allowance, Pinecone holds its $50 floor, and Azure meters the GPUs by the hour. Nothing here is modular: no layer can be swapped without leaving the wall.",
    ids: ["record", "telemetry", "machines"],
  },
  {
    id: "taller",
    label: "And the wall gets taller, not shorter.",
    line: "Model companies keep buying the layers above and below their models — apps at the top, chips at the bottom. The industry trend is toward more lock-in per stack, not less. That is the shape digithings is drawn against.",
    ids: FULL,
  },
];

const financeLeft: TourStep[] = [
  {
    id: "yours",
    label: "Your thesis, your universe — their everything else.",
    line: "The top row is the only part you hold: the research question and the watchlist. But every quote, filing and price arrives through scattered third-party endpoints you stitch yourself.",
    ids: ["app", "sources"],
  },
  {
    id: "door",
    label: "Reasoning at flagship prices, data from everywhere.",
    line: "Deep synthesis needs a reasoning model at $2 in and $8 out — while market data trickles in from half a dozen meters with half a dozen formats. Two bills, neither of which you set.",
    ids: ["app", "sources", "api"],
  },
  {
    id: "locked",
    label: "Locked in at the reasoning layer.",
    line: "The workflow only speaks one vendor's reasoning dialect, and the embeddings on your filings only fit their index. Switching either means rebuilding the pipeline and re-embedding the archive.",
    ids: ["api", "model", "embed", "memory"],
  },
  {
    id: "metered",
    label: "Traces, GPUs and lake — all inside the wall.",
    line: "Each deep run burns a hundred thousand input tokens before it writes a word; telemetry, compute and storage meter separately behind the same boundary. Nothing here is modular.",
    ids: ["record", "telemetry", "machines"],
  },
  {
    id: "taller",
    label: "And the wall gets taller, not shorter.",
    line: "Model companies keep buying the layers above and below their models — apps at the top, chips at the bottom. The industry trend is toward more lock-in per stack, not less. That is the shape digithings is drawn against.",
    ids: FULL,
  },
];

export const APP_PRESETS: AppPreset[] = [
  {
    id: "rag",
    tab: "RAG chatbot loop",
    subhead: "The industry-standard agent: chat over your corpus, answered daily.",
    workload: { corpusGB: 1, chunkTokens: 500, queriesPerDay: 1000, queryEmbedTokens: 2000, chatInTokensPerQuery: 8000, chatOutTokensPerQuery: 1500 },
    providerDefaults: { models: "sol", embeddings: "large", vector: "pinecone", telemetry: "langsmith", hosting: "azure" },
    digiDefaults: { models: "local", embeddings: "local", vector: "self", telemetry: "digismith", hosting: "own" },
    recommended: { models: "luna", embeddings: "small", vector: "qdrant", telemetry: "digismith", hosting: "own" },
    recommendedNote: "Cheap-managed: Luna routes, small embeddings, Qdrant, own traces.",
    dimmedProvider: [],
    dimmedDigi: [],
    providerApp: "your product",
    digiApp: "your product",
    leftSteps: TRADITIONAL_STEPS,
  },
  {
    id: "support",
    tab: "Support email agent",
    subhead: "LangGraph triage over ticket history, drafts reviewed by humans.",
    workload: { corpusGB: 3, chunkTokens: 500, queriesPerDay: 500, queryEmbedTokens: 2000, chatInTokensPerQuery: 12000, chatOutTokensPerQuery: 1500 },
    providerDefaults: { models: "sol", embeddings: "large", vector: "pinecone", telemetry: "langsmith", hosting: "azure" },
    digiDefaults: { models: "local", embeddings: "local", vector: "self", telemetry: "digismith", hosting: "own" },
    recommended: { models: "luna", embeddings: "small", vector: "self", telemetry: "digismith", hosting: "own" },
    recommendedNote: "Mid-tier drafting, small embeddings, self-hosted ticket index, audit-grade traces.",
    dimmedProvider: [],
    dimmedDigi: ["vault"],
    providerApp: "support agent",
    digiApp: "support agent · digichat",
    leftSteps: supportLeft,
  },
  {
    id: "finance",
    tab: "Finance research workflow",
    subhead: "Deep synthesis over market data, run through the digiquant pipeline.",
    workload: { corpusGB: 0.2, chunkTokens: 500, queriesPerDay: 50, queryEmbedTokens: 2000, chatInTokensPerQuery: 100000, chatOutTokensPerQuery: 20000 },
    providerDefaults: { models: "o3", embeddings: "large", vector: "pinecone", telemetry: "langsmith", hosting: "azure" },
    digiDefaults: { models: "local", embeddings: "local", vector: "self", telemetry: "digismith", hosting: "own" },
    recommended: { models: "deepseek", embeddings: "small", vector: "self", telemetry: "digismith", hosting: "own" },
    recommendedNote: "DeepSeek synthesis over free feeds — flagship-class reasoning near 3% of o3.",
    dimmedProvider: [],
    dimmedDigi: [],
    providerApp: "research agent",
    digiApp: "digiquant pipeline",
    leftSteps: financeLeft,
  },
];
