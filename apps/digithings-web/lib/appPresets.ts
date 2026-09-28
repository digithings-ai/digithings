/**
 * App-first presets for the single variant (Refs #4429).
 *
 * Three apps, each with its own provider topology, workload, defaults, one
 * recommended digithings stack, dimmed boxes, top-box labels and provider
 * caption. Step ids (yours/door/locked/metered or gated/taller) are stable
 * across apps; box ids are stable within an app across picks, but differ
 * across apps (finance draws feeds/filings, support draws review/email).
 */

import type { TourStep } from "@digithings/ui";
import type { RagWorkload } from "@/lib/ragCost";
import type { LayerId, StackPick } from "@/lib/stackCatalog";

/** A morph beat: one swap on the right-hand diagram. `layers` are the
    invoice rows this beat cuts on the digi column; `boxes` are the box ids
    whose labels flip this beat (finer than layers — finance flips the
    runner and the archive on separate beats sharing the hosting row).
    The send beat carries no priced row (delivery is diagram-only until
    it becomes a layer). */
export interface MorphStep extends TourStep {
  layers: LayerId[];
  boxes: string[];
  email?: boolean;
}

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
  /** Top-right box on the provider drawing; defaults to "your data sources".
      Ignored by the finance topology (twin feeds/filings boxes). */
  providerSources?: string;
  /** One-line caption under the provider drawing; per-app meter language. */
  providerCaption: string;
  /** Provider topology: rag is the full traditional stack; support swaps in
      the review lane, email service and runner with no vector boxes; finance
      swaps in the runner and research archive with no embedding boxes. */
  topology: "rag" | "support" | "finance";
  /** Layers forced for pricing where the drawing has no box (support and
      finance run no vector indexing: embeddings local, vectors self). */
  fixedLayers: Partial<StackPick>;
  /** One-line caption under the morph drawing. */
  morphCaption: string;
  leftSteps: TourStep[];
  /** Right-hand walk: same topology, one swap per beat. Four beats each. */
  morphSteps: MorphStep[];
}

const FULL_RAG = ["app", "sources", "api", "model", "embed", "memory", "record", "telemetry", "machines", "terms", "platform"];
const FULL_SUPPORT = ["app", "sources", "api", "model", "email", "launcher", "telemetry", "terms", "platform", "review"];
const FULL_FINANCE = ["app", "feeds", "filings", "api", "model", "launcher", "record", "telemetry", "terms", "platform"];

const ragLeft: TourStep[] = [
  {
    id: "yours",
    label: "Your product, your corpus — their everything else.",
    line: "The top row is the only part you hold: your product and the corpus it answers from, and the only way the corpus gets in is through their connectors on their terms.",
    ids: ["app", "sources"],
  },
  {
    id: "door",
    label: "One gateway serves every question twice.",
    line: "Each question passes the gateway twice over — once to embed it for lookup, once to answer with what the lookup returned — so one SDK version, one limit change, one price move touches both halves of every answer.",
    ids: ["app", "sources", "api", "embed", "memory"],
  },
  {
    id: "locked",
    label: "The lock-in is the embedding format.",
    line: "The index only speaks the embedder that wrote it, so swapping either means re-embedding the whole corpus and reworking the lake pipeline that feeds it — the vectors port, the fit doesn't.",
    ids: ["record", "embed", "memory", "model"],
  },
  {
    id: "metered",
    label: "Every answer is traced, housed and billed.",
    line: "Each answer lands in their trace dashboard while the index rents their GPUs and the lake meters by the gigabyte — three meters behind one boundary, none of them swappable alone.",
    ids: ["record", "telemetry", "machines"],
  },
  {
    id: "taller",
    label: "And the wall gets taller, not shorter.",
    line: "Model companies keep buying the layers above and below their models — apps at the top, chips at the bottom. The industry trend is toward more lock-in per stack, not less. That is the shape digithings is drawn against.",
    ids: FULL_RAG,
  },
];

const supportLeft: TourStep[] = [
  {
    id: "yours",
    label: "Your tickets and docs — nothing else.",
    line: "The top row is the only part you hold: the ticket queue and the product docs. Everything below it runs somewhere else.",
    ids: ["app", "sources"],
  },
  {
    id: "door",
    label: "One gateway in, on their terms.",
    line: "Tickets and docs enter through a single vendor gateway, so triage, drafting, and audit all move on a schedule and a price list you do not set.",
    ids: ["app", "sources", "api"],
  },
  {
    id: "locked",
    label: "The loop is the lock-in.",
    line: "A scheduled runner wakes the draft model again and again; triage rules and draft history accumulate inside their automation, so leaving means rebuilding the workflow, not exporting a file.",
    ids: ["launcher", "api", "model"],
  },
  {
    id: "gated",
    label: "Eyes before send — then it leaves.",
    line: "Every draft queues for human review before anything sends, and the approved reply leaves through their delivery service. Reviewer habits are workflow state you cannot take with you.",
    ids: ["model", "review", "email"],
  },
  {
    id: "taller",
    label: "And the wall gets taller, not shorter.",
    line: "Each draft is audited on their telemetry and each send runs on their terms. Model companies keep buying the layers above and below their models — that is the shape digithings is drawn against.",
    ids: FULL_SUPPORT,
  },
];

const financeLeft: TourStep[] = [
  {
    id: "yours",
    label: "Your question, their universe of data.",
    line: "The only boxes you hold are the research question and the watchlist — every price and filing arrives through scattered third-party endpoints you stitch yourself.",
    ids: ["app", "feeds", "filings"],
  },
  {
    id: "door",
    label: "One gateway funnels a dozen formats.",
    line: "A single vendor API fronts every feed at once, but quotes, filings and prices arrive in half a dozen formats across half a dozen meters — two bills, neither of which you set.",
    ids: ["feeds", "filings", "api"],
  },
  {
    id: "locked",
    label: "The pipeline only speaks one reasoning dialect.",
    line: "Deep synthesis runs on one vendor's reasoning model, fired by their nightly runner on their schedule — switching vendors means rebuilding the pipeline, not swapping a key.",
    ids: ["api", "model", "launcher"],
  },
  {
    id: "metered",
    label: "Every run burns six figures of tokens, then files.",
    line: "Each nightly run reads on the order of a hundred thousand input tokens before it writes a word, and the runner, the archive and the run-audit telemetry meter separately behind the same boundary.",
    ids: ["model", "launcher", "record", "telemetry"],
  },
  {
    id: "taller",
    label: "And the wall gets taller, not shorter.",
    line: "Model companies keep buying the layers above and below their models — apps at the top, chips at the bottom. The industry trend is toward more lock-in per stack, not less. That is the shape digithings is drawn against.",
    ids: FULL_FINANCE,
  },
];

const ragMorph: MorphStep[] = [
  {
    id: "m-models",
    label: "Models move behind your digillm gateway.",
    line: "Your questions stop going to their API on their key and go through your digillm gateway on keys you hold — Sol chat becomes a local model behind digillm that you choose. The answers read the same; the control point is yours.",
    ids: ["api", "model", "terms"],
    layers: ["models"],
    boxes: ["api", "model", "terms"],
  },
  {
    id: "m-recall",
    label: "Recall moves to digisearch in your format.",
    line: "Your embedder becomes a local embed and the Pinecone index becomes a self-hosted index you own, so lookups run as local recall in an open format. You keep the chunks; the bundled meter and the per-query lookup fall away, and recall runs at zero marginal cost on your hardware.",
    ids: ["embed", "memory"],
    layers: ["embeddings", "vector"],
    boxes: ["embed", "memory"],
  },
  {
    id: "m-telemetry",
    label: "Traces move to digismith on your store.",
    line: "Every answer is still traced, but LangSmith traces become digismith traces on a store you control — you see each lookup and answer yourself. Your audit trail stays queryable at zero marginal cost on your hardware.",
    ids: ["telemetry"],
    layers: ["telemetry"],
    boxes: ["telemetry"],
  },
  {
    id: "m-hosting",
    label: "Hosting moves to your disk and your GPUs.",
    line: "Your Azure Blob lake becomes a digivault lake on your disk and the Azure GPU pool becomes your GPU pool — same chunks, same roof, yours. Both run at zero marginal cost on your hardware once it exists.",
    ids: ["record", "machines"],
    layers: ["hosting"],
    boxes: ["record", "machines"],
  },
];

const supportMorph: MorphStep[] = [
  {
    id: "m-models",
    label: "Your drafts answer behind your own gateway.",
    line: "You point triage and drafting at a local model behind a digillm gateway you hold, so the vendor gateway and its terms drop out. You keep your keys and your routing, and the draft model changes without the workflow changing.",
    ids: ["api", "model", "terms"],
    layers: ["models"],
    boxes: ["api", "model", "terms"],
  },
  {
    id: "m-email",
    label: "Your approved replies send from inside the workflow.",
    line: "You keep the human review lane exactly where it is — every draft still waits for your eyes before it sends. Once you approve, the reply leaves through a digigraph mail tool, so delivery lives in the same graph that drafted it.",
    ids: ["email"],
    layers: [],
    boxes: ["email"],
    email: true,
  },
  {
    id: "m-telemetry",
    label: "Your draft audit lives in your own trace store.",
    line: "You still trace every draft for review, but the trail lands in digismith on your side instead of their dashboard. You see what the model saw, and the audit stays with the tickets it explains.",
    ids: ["telemetry"],
    layers: ["telemetry"],
    boxes: ["telemetry"],
  },
  {
    id: "m-hosting",
    label: "Your schedule fires from your own runner.",
    line: "You move the loop onto a digiclaw runner on hardware you already own, so the same interval fires under your control. You keep the cadence and the triage history, and the runner answers to you.",
    ids: ["launcher"],
    layers: ["hosting"],
    boxes: ["launcher"],
  },
];

const financeMorph: MorphStep[] = [
  {
    id: "m-models",
    label: "Reasoning moves to digillm.",
    line: "You route the same nightly synthesis through your digillm gateway onto your local model, so each run answers behind your key. Their terms become your keys and the per-token reasoning edge becomes your rates.",
    ids: ["api", "model", "terms"],
    layers: ["models"],
    boxes: ["api", "model", "terms"],
  },
  {
    id: "m-runner",
    label: "Nights move to digiclaw.",
    line: "You fire the same pipeline from your digiclaw runner on your hardware, so nights run on your interval instead of their schedule. The hosting row starts cutting live below, at marginal cost on hardware you own.",
    ids: ["launcher"],
    layers: ["hosting"],
    boxes: ["launcher"],
  },
  {
    id: "m-archive",
    label: "The archive moves to digivault.",
    line: "You file every thesis into your digivault archive, so past research stays yours on your disk either way. This finishes the hosting row the runner already started, at marginal cost on hardware you own.",
    ids: ["record"],
    layers: ["hosting"],
    boxes: ["record"],
  },
  {
    id: "m-telemetry",
    label: "Run audit moves to digismith.",
    line: "You keep an audit on every run, but traces land in your digismith store instead of their dashboard. You still see each run end to end, without the seats following it home.",
    ids: ["telemetry"],
    layers: ["telemetry"],
    boxes: ["telemetry"],
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
    topology: "rag",
    fixedLayers: {},
    leftSteps: ragLeft,
    morphSteps: ragMorph,
    providerCaption: "Every edge metered — per-token · per-query · per-gigabyte",
    morphCaption: "Same loop, rehomed box by box — each swap lands live in the invoice below",
  },
  {
    id: "support",
    tab: "Support email agent",
    subhead: "LangGraph triage over ticket history, drafts reviewed by humans.",
    workload: { corpusGB: 3, chunkTokens: 500, queriesPerDay: 500, queryEmbedTokens: 2000, chatInTokensPerQuery: 12000, chatOutTokensPerQuery: 1500 },
    providerDefaults: { models: "sol", embeddings: "large", vector: "pinecone", telemetry: "langsmith", hosting: "azure" },
    digiDefaults: { models: "local", embeddings: "local", vector: "self", telemetry: "digismith", hosting: "own" },
    recommended: { models: "luna", embeddings: "small", vector: "self", telemetry: "digismith", hosting: "own" },
    recommendedNote: "Mid-tier drafting, small embeddings, own runner, audit-grade traces.",
    dimmedProvider: [],
    dimmedDigi: ["vault", "memory"],
    providerApp: "support agent",
    digiApp: "support agent · digichat",
    providerSources: "tickets + docs",
    topology: "support",
    fixedLayers: { embeddings: "local", vector: "self" },
    leftSteps: supportLeft,
    morphSteps: supportMorph,
    providerCaption: "Scheduled loop — every draft traced, every send metered",
    morphCaption: "Same send pipeline, moved home box by box — you keep the review lane throughout",
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
    dimmedDigi: ["memory"],
    providerApp: "research agent",
    digiApp: "digiquant pipeline",
    providerSources: "scattered market endpoints",
    topology: "finance",
    fixedLayers: { embeddings: "local", vector: "self" },
    leftSteps: financeLeft,
    morphSteps: financeMorph,
    providerCaption: "Nightly runs — per-token reasoning · archive · traces",
    morphCaption: "Same nightly runs — intelligence home first, meters off one by one",
  },
];
