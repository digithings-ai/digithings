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
 * The rented stack, at the container level and kept deliberately generic: no
 * vendor is named, because the point is the SHAPE — a product that calls one
 * interface, and every layer behind that interface rented back to it.
 *
 * Round 12 (owner): "The diagrams should be a little more comprehensive and high
 * level. You don't have to reference specifically all the different Digi modules.
 * It's just a philosophical representation of what digithings is versus what the
 * current industry options are." So the boxes are categories a client grasps —
 * their interface, their models, their index, their data, their monitoring,
 * their machines, their terms — never brands, never digi module names.
 *
 * Eight nodes here and eight on the owned side, same ids, same topology, so the
 * two drawings read as one diagram whose box wording flipped.
 */
export const CONVENTIONAL_ARCH: ArchSpec = {
  title: "A conventional off-the-shelf AI stack",
  description:
    "Container diagram: a product calls one vendor interface, behind which sit the model, the index, the data store, the monitoring and the machines — every one of them a rented layer inside a single boundary governed by one account and one release schedule.",
  groups: [
    {
      id: "platform",
      label: "one vendor · one account · one release schedule",
      icon: "cloud",
      col: 0,
      row: 1,
      cols: 3,
      rows: 3,
    },
  ],
  services: [
    { id: "app", label: "your product", icon: "internet", col: 0, row: 0 },
    { id: "api", label: "their interface", icon: "server", group: "platform", col: 1, row: 1 },
    { id: "model", label: "their models", icon: "server", group: "platform", col: 0, row: 2 },
    { id: "memory", label: "their index", icon: "database", group: "platform", col: 1, row: 2 },
    { id: "record", label: "their data", icon: "database", group: "platform", col: 2, row: 2 },
    { id: "oversight", label: "their monitoring", icon: "server", group: "platform", col: 0, row: 3 },
    { id: "metal", label: "their machines", icon: "cloud", group: "platform", col: 1, row: 3 },
    { id: "terms", label: "their terms", icon: "disk", group: "platform", col: 2, row: 3 },
  ],
  edges: [
    { from: "app", to: "api", fromSide: "B", toSide: "T", label: "requests" },
    { from: "api", to: "model", fromSide: "R", toSide: "L", label: "inference" },
    { from: "api", to: "memory", fromSide: "L", toSide: "R", label: "retrieval" },
    { from: "api", to: "record", fromSide: "B", toSide: "T", label: "storage" },
    { from: "model", to: "oversight", fromSide: "B", toSide: "T", label: "traces" },
    { from: "memory", to: "metal", fromSide: "B", toSide: "T", label: "index" },
    { from: "record", to: "metal", fromSide: "B", toSide: "L", label: "data" },
    { from: "metal", to: "terms", fromSide: "R", toSide: "L", label: "metered" },
  ],
};

/* ══════════════════════ B. the same system on digithings ══════════════════════ */

/**
 * The same container diagram — same node ids, same positions, same wiring — with
 * every box flipped from "theirs" to "yours". The comparison is the point: the
 * calls do not change, only who owns the layer and whether the boundary has
 * seams in it. No digi module is named here either; the modules belong in the
 * capability ledger below, not in a diagram a client has to decode.
 */
export const DIGITHINGS_ARCH: ArchSpec = {
  title: "The same stack, owned",
  description:
    "Container diagram: the same product over the same calls, but every layer behind it is a piece you run — the interface, the model, the index, the data, the monitoring, the machines and the keys are all yours, inside your own boundary.",
  groups: [
    {
      id: "hosts",
      label: "your hosts · your regions · your accounts",
      icon: "server",
      col: 0,
      row: 1,
      cols: 3,
      rows: 3,
    },
  ],
  services: [
    { id: "app", label: "your product", icon: "internet", col: 0, row: 0 },
    { id: "api", label: "your interface", icon: "server", group: "hosts", col: 1, row: 1 },
    { id: "model", label: "any model", icon: "server", group: "hosts", col: 0, row: 2 },
    { id: "memory", label: "your index", icon: "database", group: "hosts", col: 1, row: 2 },
    { id: "record", label: "your data", icon: "database", group: "hosts", col: 2, row: 2 },
    { id: "oversight", label: "your log", icon: "server", group: "hosts", col: 0, row: 3 },
    { id: "metal", label: "your machines", icon: "cloud", group: "hosts", col: 1, row: 3 },
    { id: "terms", label: "your keys", icon: "disk", group: "hosts", col: 2, row: 3 },
  ],
  edges: [
    { from: "app", to: "api", fromSide: "B", toSide: "T", label: "requests" },
    { from: "api", to: "model", fromSide: "R", toSide: "L", label: "inference" },
    { from: "api", to: "memory", fromSide: "L", toSide: "R", label: "retrieval" },
    { from: "api", to: "record", fromSide: "B", toSide: "T", label: "storage" },
    { from: "model", to: "oversight", fromSide: "B", toSide: "T", label: "traces" },
    { from: "memory", to: "metal", fromSide: "B", toSide: "T", label: "index" },
    { from: "record", to: "metal", fromSide: "B", toSide: "L", label: "data" },
    { from: "metal", to: "terms", fromSide: "R", toSide: "L", label: "yours" },
  ],
};

/* ══════════════════════ A2. the guided walk ══════════════════════ */

/**
 * The walk over `CONVENTIONAL_ARCH` — the rented side of the walk-through.
 *
 * The owner: "we start with the diagram for the off-the-shelf solution and then
 * we swipe over to the digi things solution the guided camera". So the tour
 * spends its four steps on the rented stack (glow only — no camera, since a walk
 * that both zooms in and later has to pull back out is the thing that read as
 * broken), then pushes across to the owned diagram and hands the camera to
 * `OWNED_TOUR_STEPS`.
 *
 * The sets grow a layer at a time and the last one includes the `platform`
 * boundary group, so the walk ends on the closed wall rather than on a box.
 */
export const RENTED_TOUR_STEPS: TourStep[] = [
  {
    id: "surface",
    label: "You own the surface",
    line: "One box is yours: the product. Everything it calls belongs to somebody else.",
    ids: ["app"],
  },
  {
    id: "interface",
    label: "Their interface, their rules",
    line: "A single interface is the only way in. Its shape, its limits and its version are decided above you.",
    ids: ["app", "api"],
  },
  {
    id: "services",
    label: "Every layer below is rented",
    line: "The model, the index and the data are three separate contracts, three meters and three things you cannot change.",
    ids: ["app", "api", "model", "memory", "record"],
  },
  {
    id: "closed",
    label: "One closed boundary",
    line: "Monitoring, machines and the terms all sit behind the same wall. The diagram is not smaller than digithings — it is the same diagram with nothing movable in it.",
    ids: ["app", "api", "model", "memory", "record", "oversight", "metal", "terms", "platform"],
  },
];

/**
 * The walk, step by step, over `DIGITHINGS_ARCH`. The first step names no boxes
 * on purpose: the tour opens on the whole diagram and then comes in, which is
 * the owner's "at the beginning we show the full diagram and as we go through
 * every step we kind of have this guided view".
 *
 * Every id here must exist in `DIGITHINGS_ARCH` — the tour resolves them against
 * the ids mermaid puts on the rendered groups. Kept to six steps so the phase
 * count stays comparable to the rented four.
 */
export const OWNED_TOUR_STEPS: TourStep[] = [
  {
    id: "overview",
    label: "The same stack, owned",
    line: "One product over the same calls — except every box behind it is a process you run, inside a boundary that is yours.",
    ids: [],
  },
  {
    id: "surface",
    label: "The same surface",
    line: "Your product is still the top box. It calls an interface, exactly as before; the difference is who publishes that interface.",
    ids: ["app"],
  },
  {
    id: "intelligence",
    label: "Swap the model, no migration",
    line: "The interface and the model are separate layers. Move to a different model behind the same call whenever a better or cheaper one lands.",
    ids: ["api", "model"],
  },
  {
    id: "memory",
    label: "Your index, your data",
    line: "The retrieval layer and the store are yours to point anywhere. The vectors and the records stay where you put them.",
    ids: ["memory", "record"],
  },
  {
    id: "operations",
    label: "Your log, your machines",
    line: "The record of what ran and the metal it ran on are both inside your boundary — your regions, your accounts, your audit trail.",
    ids: ["oversight", "metal"],
  },
  {
    id: "keys",
    label: "The keys stay yours",
    line: "Access is issued and revoked by you, carried on every call, so the boundary is a set of seams you can move rather than a wall you rent.",
    ids: ["terms"],
  },
];

/** The foot line under each diagram. */
export const ARCH_CAPTIONS = {
  conventional: {
    caption:
      "container view · every box below your application is a rented product with its own meter",
    foot: "One shape, sold to everyone — custom nowhere. You own the application, and everything under it is a contract you did not write, wired in an order you cannot change, released on someone else's schedule.",
  },
  digithings: {
    caption: "container view · every box is a process you run, on infrastructure you already pay for",
    foot: "Same shape, same calls — but every box is a module you can replace on its own. Modular and custom by construction; your hosts and your keys make it private and secure; one margin lighter makes it cost-effective.",
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
    capability: "what you are buying",
    rented: "a product built for everyone — one-size-fits-all, so it fits nobody exactly",
    owned: "an architecture you compose: take the modules you need, leave the rest",
  },
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
    owned: "your hosts, in your regions, next to your data — private by construction",
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
    rented: "a plan minimum and a platform margin on every layer, whatever you use",
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
  "a chat turn is one inference call; an agentic task averages 10–20 calls, so the same headcount can be 5–30× the token volume (Gartner, Aug 2026)",
  "at enterprise scale the average LLM bill is real money: a16z's Jan-2026 survey of Global-2000 CIOs puts average enterprise LLM spend near $7m a year and rising",
  "embedding and index maintenance run continuously over the document set",
  "the system is on the provider's published list price, with no negotiated discount and no reserved capacity",
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
    rented: "the provider's list rate, plus the platform's markup on the way through — and an agentic task can cost 5–30× a chat turn",
    owned: "the same provider list rate if you call them directly, or an open model on your own metal",
    source: "frontier list rates per 1M tokens in/out: Claude Opus 4.6 $5/$25, Sonnet 4.6 $3/$15, GPT-5.4 ~$2.50/$15, nano floor $0.05 in [V, read 2026-09-24]; Gartner: agentic AI uses 5–30× the tokens of a chatbot and a $0.01 chat task can reach $1.50 [A, 2026-08-19]",
  },
  {
    layer: "embeddings",
    rented: "a metered line you rarely see itemised on a platform invoice",
    owned: "the same embedding API billed to your own account, or an open model you host",
    source: "text-embedding class list rates around $0.02 per 1M tokens [V, read Sep 2026]",
  },
  {
    layer: "vector store",
    rented: "a plan minimum, then per GB stored, per read unit and per GB egress",
    owned: "your own index on your own disk — the compute you already pay for",
    source: "Pinecone: Builder $20/mo, Standard $50/mo minimum, $0.33/GB-mo stored, $16–18 per M read units, $0.10/GB egress; Weaviate Flex from $45/mo [V, pinecone.io/pricing, read 2026-09]",
  },
  {
    layer: "database and queue",
    rented: "per instance, per GB, per operation, per seat",
    owned: "one process on the machine you already bought",
    source: "published managed-instance tiers, read Sep 2026 [V]",
  },
  {
    layer: "observability",
    rented: "per host, per seat, per custom metric, per retained event — traced spans are metered too",
    owned: "OpenTelemetry and a log file — the cost is the disk and part of an engineer's month",
    source: "Datadog infra $15/host/mo and APM $31/host/mo list; Langfuse Core $29/mo, Pro $199/mo, Enterprise $2,499/mo; self-hosted Grafana/LGTM is 10–40 engineer-hours a month [V, read 2026-09]",
  },
  {
    layer: "compute",
    rented: "an instance rate with a hyperscaler premium over the same silicon",
    owned: "whatever you already run, or a specialist GPU rate",
    source: "H100 per GPU-hour: $1.38–$2.89 from specialists and marketplaces vs $6.88 AWS, $6.98–$15.98 Azure, $11.06 GCP [V/3P, read Sep 2026]",
  },
  {
    layer: "data transfer",
    rented: "egress is billed on every layer, and it is easy to miss",
    owned: "charged at cost, or free on object storage that does not meter it",
    source: "internet egress $0.09/GB on AWS, $0.087 Azure, $0.12 GCP vs $0.00 on Cloudflare R2; data transfer is 10–30% of a typical AWS bill [V, read 2026-09]",
  },
  {
    layer: "engineering time",
    rented: "near zero to start, and you cannot spend it on the parts you want to change — but licence and re-migration costs are real",
    owned: "the honest other side: operations and maintenance, roughly 0.5–2 engineers' worth at a loaded $400–600k each a year",
    source: "Gartner: a 'simple' enterprise RAG build is $750k–$1m lifetime with only 10–20% in the initial build, plus 0.5–2 FTE; a modelled ground-up RAG build is $3.34m in year one with 70% of it payroll [A/3P, 2026]",
  },
];

/**
 * The framing that makes the table honest. Without this paragraph the numbers
 * above read as a promise; with it they read as arithmetic.
 */
export const COST_FRAMING = {
  headline: "A managed stack is priced for everyone. You pay for that average.",
  body: "A managed platform is one-size-fits-all by construction: it is built to serve every customer at once, so it charges for the whole menu — a plan minimum here, a per-seat line there, a markup on every layer it resells — whether or not you use that layer. You pay for the average, and you get the average. digithings is the opposite bet: you take the modules you need, run them where you already run things, and pay the provider's own list price on the parts you do use. That is the custom-architecture advantage, and it shows up in three places at once. Cost: the middle margin disappears and the bill tracks your actual usage instead of a plan tier. Fit: a layer that does not suit you is swapped, not negotiated — swap the model or the store without a migration, because no module assumes the others are the same vendor's. Control: your hosts, your keys, your log, so privacy and security are properties you hold rather than promises you are given. None of that is free: self-hosting moves spend from a vendor invoice to your own metal and your own engineering time, and whether that trade wins depends on volume. But the direction of the trade is not in question — a one-size-fits-all bill grows with your headcount, while a custom architecture grows with the work you actually do.",
} as const;

/**
 * What the model deliberately does not do, said out loud so nobody reads more
 * into the table than is there.
 */
export const COST_CAVEATS: string[] = [
  "every figure is labelled by its source: [V] a vendor's published list price, [A] an analyst estimate, [3P] a third-party model or tracker — never presented as what any one company pays",
  "no single monthly total: it would be an invented number, because the same stack costs wildly different amounts at a chatbot's volume and at an agent fleet's",
  "no negotiated discount, no committed-use pricing, no reserved capacity",
  "no claim about any named vendor's contract terms or unpublished pricing",
  "self-hosted model quality is not priced here — that is a capability question, answered above",
];
