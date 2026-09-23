/**
 * The data behind `/variants/why` (round 10, #4429).
 *
 * The owner's round-10 direction, after rejecting the simple node graph:
 *
 *   "i want a visual like a graph like a design document or a design graph an
 *    architecture graph this is a visual graph with nodes and lines connecting
 *    the different services from a database to a cloud infrastructure the
 *    specific graph that you typically build when you're designing a system or
 *    an architecture"
 *
 *   "i can't say that i wouldn't have done a simple graph like that ... there's a
 *    convention for this that's standard practice amongst software companies ...
 *    we need to accurately describe the design of ... an architecture diagram of
 *    an AI stack for a company with all the services that we have in digithings
 *    and kind of estimate the costs ..."
 *
 * THE CONVENTION IS THE C4 MODEL (Simon Brown): Context -> Container ->
 * Component -> Code. What he described is specifically the CONTAINER diagram —
 * one box per deployable/runtime unit, a labelled connector per call, external
 * systems outside the boundary. Both specs below are written in that grammar,
 * and both are handed to the same renderer, so the two drawings share a
 * silhouette and diff only in what the boxes are and how they are wired.
 *
 * HONESTY RULES THIS MODULE OBEYS
 *  - The conventional side names NO vendor. Round 9b taught that lesson twice.
 *    Every box is a CATEGORY an engineer would draw ("managed vector store"),
 *    never a brand.
 *  - Nothing is asserted about any platform's unpublished pricing or contract
 *    terms.
 *  - No figure in `COST_LINES` is ours. Each is a published third-party list
 *    rate, labelled with what it is and when it was read, and the framing says
 *    outright that it is a model and not a quote.
 *  - No performance, backtest or trading figure appears anywhere.
 *
 * Plain data, therefore server-safe: the variants page is a server component and
 * cannot reach a client module's exports.
 */

import type { ArchSpec, TourStep } from "@digithings/ui";

/* ══════════════════════ A. the conventional stack ══════════════════════ */

/**
 * The rented stack, drawn at the container level for an organisation of a few
 * hundred seats: your application calling one vendor API, the managed services
 * fanned out behind it, and one boundary that governs all of it.
 */
export const CONVENTIONAL_ARCH: ArchSpec = {
  title: "A conventional managed AI stack",
  description:
    "Container diagram: an application calls one vendor API, behind which sit a managed models API, a vector store, a managed database, a managed queue and managed traces, running on the vendor's infrastructure — all inside a single vendor boundary governed by one account.",
  groups: [
    {
      id: "platform",
      label: "one vendor · one account · one release schedule",
      icon: "cloud",
    },
  ],
  services: [
    { id: "app", label: "your application", icon: "internet" },
    { id: "gateway", label: "api gateway", icon: "server", group: "platform" },
    { id: "model", label: "managed models", icon: "server", group: "platform" },
    { id: "vector", label: "vector store", icon: "database", group: "platform" },
    { id: "rdbms", label: "managed database", icon: "database", group: "platform" },
    { id: "queue", label: "managed queue", icon: "disk", group: "platform" },
    { id: "obs", label: "managed traces", icon: "server", group: "platform" },
    { id: "cloud", label: "their compute", icon: "cloud", group: "platform" },
  ],
  edges: [
    { from: "app", to: "gateway", fromSide: "B", toSide: "T", label: "https" },
    { from: "gateway", to: "model", fromSide: "R", toSide: "L", label: "inference" },
    { from: "gateway", to: "vector", fromSide: "L", toSide: "R", label: "retrieval" },
    { from: "gateway", to: "rdbms", fromSide: "B", toSide: "T", label: "sql" },
    { from: "model", to: "obs", fromSide: "R", toSide: "L", label: "traces" },
    { from: "vector", to: "queue", fromSide: "B", toSide: "T", label: "ingest" },
    { from: "rdbms", to: "cloud", fromSide: "R", toSide: "L", label: "storage" },
    { from: "queue", to: "cloud", fromSide: "B", toSide: "T", label: "events" },
  ],
};

/* ══════════════════════ B. the same system on digithings ══════════════════════ */

/**
 * The same container diagram, same silhouette, every box swapped for the module
 * that does that job and the boundary relabelled. The comparison is the point:
 * the calls are the same, the difference is who owns the boxes and whether the
 * boundary has seams in it.
 */
export const DIGITHINGS_ARCH: ArchSpec = {
  title: "The same stack on digithings",
  description:
    "Container diagram: the same application, but every service behind it is a digithings module — digigraph routing to digiquant, digisearch, digivault and digichat, with digikey, digismith, digiclaw and digibase beneath — all inside your own boundary.",
  groups: [
    {
      id: "hosts",
      label: "your hosts · your regions · your accounts",
      icon: "server",
    },
  ],
  services: [
    { id: "app", label: "your application", icon: "internet" },
    { id: "graph", label: "digigraph", icon: "server", group: "hosts" },
    { id: "quant", label: "digiquant", icon: "server", group: "hosts" },
    { id: "search", label: "digisearch", icon: "database", group: "hosts" },
    { id: "vault", label: "digivault", icon: "disk", group: "hosts" },
    { id: "chat", label: "digichat", icon: "internet", group: "hosts" },
    { id: "smith", label: "digismith", icon: "server", group: "hosts" },
    { id: "key", label: "digikey", icon: "server", group: "hosts" },
    { id: "claw", label: "digiclaw", icon: "server", group: "hosts" },
    { id: "base", label: "digibase", icon: "disk", group: "hosts" },
  ],
  edges: [
    { from: "app", to: "graph", fromSide: "B", toSide: "T", label: "https" },
    { from: "graph", to: "quant", fromSide: "R", toSide: "L", label: "research" },
    { from: "graph", to: "search", fromSide: "L", toSide: "R", label: "retrieval" },
    { from: "graph", to: "vault", fromSide: "B", toSide: "T", label: "notes" },
    { from: "quant", to: "smith", fromSide: "R", toSide: "L", label: "traces" },
    { from: "search", to: "chat", fromSide: "B", toSide: "T", label: "context" },
    { from: "vault", to: "key", fromSide: "R", toSide: "L", label: "scope" },
    { from: "chat", to: "base", fromSide: "B", toSide: "T", label: "shared" },
    { from: "key", to: "claw", fromSide: "B", toSide: "T", label: "heartbeat" },
  ],
};

/* ══════════════════════ A2. the guided walk ══════════════════════ */

/**
 * The walk, step by step, over `DIGITHINGS_ARCH`. The first step names no boxes
 * on purpose: the tour opens on the whole diagram and then comes in, which is
 * the owner's "at the beginning we show the full diagram and as we go through
 * every step we kind of have this guided view".
 *
 * Every id here must exist in `DIGITHINGS_ARCH` — the tour resolves them against
 * the ids mermaid puts on the rendered groups.
 */
export const TOUR_STEPS: TourStep[] = [
  {
    id: "overview",
    label: "The whole system",
    line: "One application, nine modules and a shared library under them. Every box is a process you run, inside a boundary that is yours.",
    ids: [],
  },
  {
    id: "route",
    label: "A request arrives",
    line: "Your application calls digigraph. That is the only entry point, and what happens next is a graph you can read and edit rather than a route you are given.",
    ids: ["app", "graph"],
  },
  {
    id: "research",
    label: "Research and backtests",
    line: "digiquant proposes ideas against public data, backtests them before anyone sees a number, and sizes the survivor into weights.",
    ids: ["quant"],
  },
  {
    id: "retrieval",
    label: "Answers with sources",
    line: "digisearch indexes whatever you point it at — documents, your own stores, the open web — and digichat is the surface that asks the question.",
    ids: ["search", "chat"],
  },
  {
    id: "notes",
    label: "Your own documents",
    line: "digivault keeps a markdown vault with wikilinks and backlinks, so the knowledge stays in files you can open in any editor.",
    ids: ["vault"],
  },
  {
    id: "trust",
    label: "Keys, traces, heartbeat",
    line: "digikey issues the keys and scopes them on every call, digismith records what ran, and digiclaw keeps the whole thing alive.",
    ids: ["key", "smith", "claw"],
  },
  {
    id: "foundation",
    label: "One shared library",
    line: "digibase sits under all of it. A change to HTTP, audit or settings lands once instead of nine times, which is what keeps nine modules one product.",
    ids: ["base"],
  },
];

/** The foot line under each diagram. */
export const ARCH_CAPTIONS = {
  conventional: {
    caption:
      "container view · every box below your application is a rented product with its own meter",
    foot: "You own the application. Everything under it is a contract you did not write, wired in an order you cannot change, released on someone else's schedule.",
  },
  digithings: {
    caption: "container view · every box is a process you run, on infrastructure you already pay for",
    foot: "Same shape, same calls. The difference is that each box is a module you can replace on its own — which is what makes the rest of this page true.",
  },
} as const;

/* ══════════════════════ C. the capability comparison ══════════════════════ */

/**
 * The same nine questions asked of both stacks. Written as structural
 * consequences, not adjectives — "you ship against their API" rather than
 * "less flexible".
 */
export interface CapabilityRow {
  capability: string;
  rented: string;
  owned: string;
}

export const CAPABILITIES: CapabilityRow[] = [
  {
    capability: "the source",
    rented: "closed — you get the product, never the code",
    owned: "an MIT monorepo; every module, test and CI definition is readable",
  },
  {
    capability: "what you can change",
    rented: "the surface only; everything below the API is theirs",
    owned: "any layer — swap a store or a model without a migration",
  },
  {
    capability: "how you reach it",
    rented: "their API and their SDK, inside their limits",
    owned: "a REST endpoint, an MCP tool, a CLI command and a container, per capability",
  },
  {
    capability: "who holds the keys",
    rented: "one account; scopes and rate limits are set for you",
    owned: "keys you issue and revoke, JWT-signed and scoped on every call",
  },
  {
    capability: "where it runs",
    rented: "their regions, on their capacity",
    owned: "your hosts, in your regions, next to your data",
  },
  {
    capability: "the record of what ran",
    rented: "their logs, inside their retention window",
    owned: "an append-only log on your disk, kept as long as you keep it",
  },
  {
    capability: "scaling a layer",
    rented: "their ceiling — you queue behind every other tenant",
    owned: "each layer scales where it already runs; no shared ceiling",
  },
  {
    capability: "building on top",
    rented: "you ship against their API and take each release",
    owned: "you ship your own app on the same primitives the product uses",
  },
  {
    capability: "the cost shape",
    rented: "a platform margin on every layer, on top of the provider price",
    owned: "the provider's list price, plus your own metal and your own time",
  },
];

/* ══════════════════════ D. the cost model ══════════════════════ */

/**
 * Assumptions every figure below is conditioned on. Deliberately changeable —
 * a reader who disagrees with one of these has the lever in their hand, which is
 * the difference between a model and a claim.
 */
export const COST_ASSUMPTIONS: string[] = [
  "≈200 people using the system, a mix of chat users and agent runs",
  "a chat turn is one inference call; an agentic task averages 10–20 calls, so the same headcount can be 5–30× the token volume",
  "embedding and index maintenance run continuously over the document set",
  "the system is on the provider's published list price, with no negotiated discount",
  "self-hosting adds engineering time — this model does not pretend it is free",
];

export interface CostLine {
  layer: string;
  /** What the rented stack is billed for. */
  rented: string;
  /** What the same layer costs when you run it. */
  owned: string;
  /** Where the figure comes from. Every one of these is third-party. */
  source: string;
}

/**
 * Per-layer market rates, as published. Each `source` names what kind of figure
 * it is and when it was read; none of these is a quote, and none is our own
 * measurement.
 */
export const COST_LINES: CostLine[] = [
  {
    layer: "inference",
    rented: "the same list price either way — the model provider bills you directly or through the platform",
    owned: "unchanged, or lower: hosted open-weight models list at roughly 1/10th of frontier rates, and self-hosted changes the unit to your own metal",
    source: "frontier list rates per 1M tokens, in / out: $2.50 / $15.00, $3.00 / $15.00, $1.25 / $10.00; budget tier $0.10–$1.00 in",
  },
  {
    layer: "embeddings",
    rented: "a metered line you do not see itemised on a platform invoice",
    owned: "the same embedding API, billed to your own account, or an open model you host",
    source: "text-embedding class list rates around $0.02 per 1M tokens, read Sep 2026",
  },
  {
    layer: "vector store",
    rented: "per GB stored, per read, per query, plus a plan minimum",
    owned: "your own index on your own disk — the compute you already pay for",
    source: "managed vector tiers list from ~$0 to ~$5,000/mo; hosted units around $2.64 per unit",
  },
  {
    layer: "database and queue",
    rented: "per instance, per GB, per operation, per seat",
    owned: "one process on the machine you already bought",
    source: "published managed-instance tiers, read Sep 2026",
  },
  {
    layer: "observability",
    rented: "per host, per seat, per custom metric, per retained event",
    owned: "Prometheus, OpenTelemetry and a log file — the cost is the disk",
    source: "platform monitoring commonly lands at $2,200–$11,000/mo; self-hosted equivalents $500–$2,000/mo",
  },
  {
    layer: "compute",
    rented: "an instance rate with a margin over the underlying resource",
    owned: "whatever you already run, or a specialist GPU rate",
    source: "H100 $1.99–$2.50/hr from specialists vs $4.59–$8.90/hr on the hyperscalers, read Sep 2026",
  },
  {
    layer: "engineering time",
    rented: "near zero to start, and you cannot spend it on the parts you want to change",
    owned: "$1,500–$4,000/mo of operations for a small deployment, and more as it grows — the honest other side of the ledger",
    source: "published ops-rate estimates at $150–$200/hr, read Sep 2026",
  },
];

/**
 * The framing that makes the table honest. Without this paragraph the numbers
 * above read as a promise; with it they read as arithmetic.
 */
export const COST_FRAMING = {
  headline: "You pay the same provider price either way. The difference is the layer on top.",
  body: "Both stacks rent the same frontier models from the same providers at the same list rates — that part of the bill is identical and no diagram changes it. What differs is everything wrapped around them. A managed platform charges a margin on each layer it resells, and every layer is metered separately: storage, reads, seats, hosts, custom metrics, retained events. Running the same layers yourself removes that margin and replaces it with two costs that no vendor invoice shows — your own infrastructure, and the engineering time to operate it. Whether that trade wins depends entirely on volume: the crossover generally sits in the millions of tokens per day, so a small deployment is usually cheaper rented and a large one is usually cheaper owned. Every figure in the table above is a published list rate, not a quote, and this model assumes no negotiated discount — the two things that would move it most.",
} as const;

/**
 * What the model deliberately does not do, said out loud so nobody reads more
 * into the table than is there.
 */
export const COST_CAVEATS: string[] = [
  "no single monthly total: it would be an invented number, because the same stack costs wildly different amounts at a chatbot's volume and at an agent fleet's",
  "no negotiated discount, no committed-use pricing, no reserved capacity",
  "no claim about any named vendor's contract terms or unpublished pricing",
  "self-hosted model quality is not priced here — that is a capability question, answered above",
];
