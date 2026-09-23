/**
 * The data behind `/variants/why` (round 9, #4429).
 *
 * One architecture grammar, drawn twice. The owner's round-9 direction:
 *
 *   "I would focus on the two visuals, one for the rented stack and the other
 *    for the DigiThings stack should be somewhat similar, just changing the
 *    components and the wiring to a certain degree … it could be an actual
 *    architecture visualization of how true designers and software developers
 *    would architect the platform … the proper symbolism used, the proper words
 *    … show the visual representation of what the rented, hosted stack would
 *    look like using … OpenAI and Anthropic logos in Gemini and Azure, which is
 *    the conventional tools out there that aren't open source … And most
 *    importantly, the cost, everything cost, cost, cost, cost, cost, and then
 *    you end up with a massive bill."
 *
 * So both sides are drawn from the SAME five slots, in the same order, with the
 * same connector grammar — only the components and the wiring differ. The rented
 * side names the conventional closed tools (the ones the owner listed); the
 * owned side names what you put in the same slot when you run it yourself.
 *
 * HONESTY — what is named, and what is not.
 *
 * Naming a vendor as "a conventional tool you would rent" is a factual statement
 * about a category, and the owner asked for the logos explicitly. What is NOT
 * said anywhere: any price, any percentage, any "Nx cheaper", any claim about a
 * vendor's contract terms or unpublished pricing, and any performance or trading
 * figure. Each component therefore carries the CADENCE it bills on — "per token",
 * "per GB · per read", "per host · per seat" — which is how these products
 * publicly bill, and no amount. The bill lands by COUNT, not by a number we
 * cannot source: every rented component is its own invoice, which is the whole
 * point of the shape.
 *
 * This module is plain data and therefore server-safe: the variants page is a
 * server component and cannot reach a client module's exports.
 */

/** The five slots both architectures are drawn from, top to bottom. */
export interface StackSlot {
  id: string;
  /** The layer name, as an engineer would write it on the diagram. */
  layer: string;
}

export const SLOTS: StackSlot[] = [
  { id: "inference", layer: "inference" },
  { id: "retrieval", layer: "retrieval" },
  { id: "observability", layer: "observability" },
  { id: "runtime", layer: "runtime" },
  { id: "product", layer: "product" },
];

/** One box on the diagram: a named thing, a mark, and how it bills. */
export interface StackComponent {
  slot: string;
  name: string;
  /** A key into the kit's `ICONS` registry, or null for a monogram chip. */
  icon: string | null;
  /** How the thing bills — a cadence, never an amount. */
  cadence: string;
  /** False on the owned side, where the point is that it is not a new bill. */
  billed?: boolean;
}

/**
 * The rented stack: the conventional, closed tools. Each one is a separate
 * account with its own meter — which is the argument the bill column makes.
 */
export const RENTED_COMPONENTS: StackComponent[] = [
  { slot: "inference", name: "OpenAI", icon: "openai", cadence: "per token · per call" },
  { slot: "inference", name: "Anthropic", icon: "anthropic", cadence: "per token · per call" },
  { slot: "inference", name: "Gemini", icon: "googlegemini", cadence: "per token · per call" },
  { slot: "retrieval", name: "Snowflake", icon: "snowflake", cadence: "per GB stored · per read" },
  { slot: "retrieval", name: "MongoDB Atlas", icon: "mongodb", cadence: "per GB stored · per read" },
  { slot: "observability", name: "Datadog", icon: "datadog", cadence: "per host · per seat" },
  { slot: "observability", name: "Grafana Cloud", icon: "grafana", cadence: "per series · per seat" },
  { slot: "runtime", name: "Azure", icon: null, cadence: "per instance · per seat" },
  { slot: "runtime", name: "Google Cloud", icon: "googlecloud", cadence: "per instance · per seat" },
  { slot: "product", name: "a licensed app", icon: null, cadence: "per seat · you take what ships" },
];

/**
 * The owned stack: the same five slots, filled by things you run. Nothing here
 * is a new vendor — that is the claim, and the wiring says so.
 */
export const OWNED_COMPONENTS: StackComponent[] = [
  { slot: "inference", name: "open weights", icon: null, cadence: "your provider account" },
  { slot: "retrieval", name: "your vector store", icon: "postgresql", cadence: "your store · your documents" },
  { slot: "observability", name: "your log", icon: "opentelemetry", cadence: "your disk · your retention" },
  { slot: "runtime", name: "your hosts", icon: "docker", cadence: "your metal · your region" },
  { slot: "product", name: "your app", icon: null, cadence: "REST · MCP · CLI · container" },
];

/** How many separate invoices the rented shape ends up with. */
export const RENTED_BILLS = RENTED_COMPONENTS.length;

export interface WhyStep {
  id: string;
  /** The stepper's line. */
  label: string;
  /** One sentence of mechanism — what is true, not what is promised. */
  line: string;
  /** Components of the diagram this step lights up. */
  marks: string[];
}

/**
 * The rented half: the stack, then each layer, then the bill.
 *
 * The stair is deliberate — each step adds the next meter, and the marks stay
 * lit so the bill column only ever grows.
 */
export const RENTED_STEPS: WhyStep[] = [
  {
    id: "stack",
    label: "The stack you rent",
    line: "Five layers, ten products, one account and one invoice for each of them.",
    /* Nothing is lit yet: the step shows the shape, and the meters come on one
       layer at a time so the bill below visibly grows. */
    marks: [],
  },
  {
    id: "inference",
    label: "Inference",
    line: "You rent the weights. The release schedule and the price tier come with them, and it meters per token and per call.",
    marks: ["OpenAI", "Anthropic", "Gemini"],
  },
  {
    id: "retrieval",
    label: "Retrieval",
    line: "Your documents sit in their store, in their embedding family — billed by the gigabyte and by the read.",
    marks: ["Snowflake", "MongoDB Atlas"],
  },
  {
    id: "observability",
    label: "Observability",
    line: "The traces are theirs and the retention window is theirs. Per host, per series, per seat.",
    marks: ["Datadog", "Grafana Cloud"],
  },
  {
    id: "runtime",
    label: "Runtime and product",
    line: "You pay to run it, and the app on top is one everybody shares — so nothing above the surface line is yours to change.",
    marks: ["Azure", "Google Cloud", "a licensed app"],
  },
  {
    id: "bill",
    label: "A bill per layer",
    line: "Ten meters, ten invoices, and adding a capability means adding a meter. Nothing here consolidates, because nothing here is yours.",
    marks: RENTED_COMPONENTS.map((c) => c.name),
  },
];

/** The owned half's arc. */
export const OWNED_ARC = ["rented", "modular", "yours"] as const;
export type OwnedArc = (typeof OWNED_ARC)[number];

export interface OwnedStep extends WhyStep {
  arc: OwnedArc;
}

/**
 * The owned half: the same slots, detached, then yours to build on.
 *
 * Note the marks: each step adds its slot and keeps the previous ones, so the
 * diagram fills up rather than flashing one box at a time.
 */
export const OWNED_STEPS: OwnedStep[] = [
  {
    id: "modular",
    label: "Modular",
    line: "The same five slots — but each one is a seam you can move, and no module assumes you run any other.",
    marks: ["open weights", "your vector store", "your log"],
    arc: "modular",
  },
  {
    id: "accounts",
    label: "Your accounts",
    line: "Your provider keys, your store, your documents. Nothing in the middle of a bill you already pay.",
    marks: ["open weights", "your vector store"],
    arc: "modular",
  },
  {
    id: "hosts",
    label: "Your hosts",
    line: "The graph runs where you already run things, the log is on your disk, and the keys are yours — signed and scoped on the call.",
    marks: ["your hosts", "your log", "open weights"],
    arc: "yours",
  },
  {
    id: "build",
    label: "Yours to build on",
    line: "Every capability is a REST endpoint, an MCP tool, a CLI command and a container. You ship the app, and the app is yours.",
    marks: OWNED_COMPONENTS.map((c) => c.name),
    arc: "yours",
  },
];

/** The seam each slot becomes, said as what you get back. */
export const SEAM_LABELS: { id: string; seam: string }[] = [
  { id: "inference", seam: "swap the model" },
  { id: "retrieval", seam: "own the index" },
  { id: "observability", seam: "keep the log" },
  { id: "runtime", seam: "choose the metal" },
  { id: "product", seam: "ship your own app" },
];

/** Everything a diagram can draw as lit — what a reduced-motion reader sees. */
export function allMarks(...groups: string[][]): string[] {
  const seen = new Set<string>();
  groups.forEach((group) => group.forEach((mark) => seen.add(mark)));
  return [...seen];
}

/** The rented side's full mark set, in draw order. */
export const RENTED_MARKS = RENTED_COMPONENTS.map((c) => c.name);
/** The owned side's full mark set, in draw order. */
export const OWNED_MARKS = OWNED_COMPONENTS.map((c) => c.name);

/**
 * The benefit ledger, as structural consequences rather than figures.
 *
 * Each of these is what changes about the structure — the claim the four
 * benefit words ("cheaper, more efficient, easier to scale, yours to build on")
 * actually cash out to.
 */
export const LEDGER: { claim: string; because: string }[] = [
  {
    claim: "you pay providers, not a platform",
    because:
      "one invoice per layer becomes your own provider accounts — nothing in the middle marking up a layer you already pay for",
  },
  {
    claim: "a layer swaps without a migration",
    because:
      "no module assumes you are running any other one, so replacing a store or a model is a local change",
  },
  {
    claim: "each layer scales where it already runs",
    because: "your metal, your region — there is no vendor capacity ceiling to queue behind",
  },
  {
    claim: "you ship your own app on top",
    because: "every capability is a REST endpoint, an MCP tool, a CLI command and a container",
  },
];
