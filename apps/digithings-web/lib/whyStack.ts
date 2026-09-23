/**
 * The data behind `/variants/why` (round 9, #4429).
 *
 * The owner's direction for this composition: show "the conventional stack or
 * the off-the-shelf stack … what it would look like and how much it would cost
 * for each component", then "swipe that around", "and then DigiThings comes in".
 * "That's basically laying out the trap, and then you throw DigiThings [at] them
 * and explain how it's going to improve that stack."
 *
 * HONESTY — the reason there is no money on this page.
 *
 * The owner asked for cost per component. Nothing in this repo sources a
 * comparison, `docs/vision/README.md` makes no cost claim against anyone (it
 * says digithings "competes with the engineering time and cost of building
 * production AI systems from scratch" — a claim about building from scratch, not
 * about a rival's invoice), and inventing figures for a category of vendor is
 * what the live band's docblock forbids outright. So each component carries the
 * CADENCE it bills on — `per token · per call`, `per GB stored · per read` — and
 * no amounts. Every word of it is checkable, and "five layers, five bills" lands
 * anyway.
 *
 * No vendor is named. The left half is the shape of a rented stack, not an
 * accusation against one.
 */

/** A component of the conventional stack, as drawn. */
export interface StackPart {
  id: string;
  /** The label on the slab. */
  label: string;
  /** How it bills — cadence, never an amount. */
  cadence: string;
}

export const CONVENTIONAL_PARTS: StackPart[] = [
  { id: "models", label: "model APIs", cadence: "per token · per call" },
  { id: "data", label: "data + vectors", cadence: "per GB stored · per read" },
  { id: "telemetry", label: "telemetry", cadence: "per event · per seat" },
  { id: "hosting", label: "app hosting", cadence: "per instance · per seat" },
  { id: "app", label: "the app itself", cadence: "shared · nobody's edge" },
];

export interface WhyStep {
  id: string;
  /** The stepper's line. */
  label: string;
  /** One sentence of mechanism — what is true, not what is promised. */
  line: string;
  /** Parts of the diagram this step lights up. */
  parts: string[];
}

/** The rented half: the stack, then each bill, then what the shape costs you. */
export const RENTED_STEPS: WhyStep[] = [
  {
    id: "stack",
    label: "The stack you rent",
    line: "Five layers, five vendors, five bills — and a contract for each one of them.",
    parts: ["models", "data", "telemetry", "hosting", "app"],
  },
  {
    id: "models",
    label: "Model APIs",
    line: "You rent the weights, and the release schedule comes with them. Billed per token, per call.",
    parts: ["models"],
  },
  {
    id: "data",
    label: "Data and vectors",
    line: "Your documents sit in their store, billed by the gigabyte and by the read.",
    parts: ["data"],
  },
  {
    id: "telemetry",
    label: "Telemetry",
    line: "The traces are theirs, the retention window is theirs, and it bills per event and per seat.",
    parts: ["telemetry"],
  },
  {
    id: "apps",
    label: "Hosting, and the app itself",
    line: "You pay to run it — and the app is one everybody shares, so nothing about it is your edge.",
    parts: ["hosting", "app"],
  },
  {
    id: "bill",
    label: "The bill does not scale down",
    line: "The efficiency the field reaches and the invoice you receive run on different schedules. Reaching for more capability means paying for more capability.",
    parts: ["models", "data", "telemetry", "hosting", "app"],
  },
];

/** The borrowed half's own arc — the one thing worth keeping from variant 4. */
export const OWNED_ARC = ["rented", "modular", "yours"] as const;
export type OwnedArc = (typeof OWNED_ARC)[number];

export interface OwnedStep extends WhyStep {
  /** Which word of `rented → modular → yours` this step stands on. */
  arc: OwnedArc;
}

/** The owned half: the same seven layers, detached, then yours to build on. */
export const OWNED_STEPS: OwnedStep[] = [
  {
    id: "modular",
    label: "Modular",
    line: "The same seven layers — but each one is a seam you can move, and no module assumes you run any other.",
    parts: ["models", "data", "telemetry"],
    arc: "modular",
  },
  {
    id: "accounts",
    label: "Your accounts",
    line: "Your provider keys, your vector store, your documents. Nobody stands in the middle of a bill you already pay.",
    parts: ["data", "models"],
    arc: "modular",
  },
  {
    id: "hosts",
    label: "Your hosts and keys",
    line: "The graph runs where you already run things, the log is on your disk, and the keys are yours — signed and scoped on the call.",
    parts: ["hosting", "telemetry", "models"],
    arc: "yours",
  },
  {
    id: "build",
    label: "Yours to build on",
    line: "Every capability is a REST endpoint, an MCP tool, a CLI command and a container. You ship the app, and the app is yours.",
    parts: ["app", "models", "data", "telemetry", "hosting"],
    arc: "yours",
  },
];

/**
 * The seven seams, named as what you get back — reused verbatim from
 * `Argument.tsx`'s `LAYERS` so this page cannot drift from the live band. The
 * module names stay out: the layer is the seam, not the package that fills it.
 */
export const SEAM_LABELS: { id: string; seam: string }[] = [
  { id: "models", seam: "swap the model" },
  { id: "data", seam: "own the index" },
  { id: "telemetry", seam: "keep the log" },
  { id: "hosting", seam: "choose the metal" },
  { id: "app", seam: "ship your own app" },
];

/** Union of every step's marks — what a reduced-motion reader sees. */
export function allParts(steps: readonly WhyStep[]): string[] {
  const seen = new Set<string>();
  steps.forEach((step) => step.parts.forEach((part) => seen.add(part)));
  return [...seen];
}

/**
 * The benefit ledger, as structural consequences rather than figures.
 *
 * Each of these is what changes about the structure — the claim the four
 * benefit words ("cheaper, more efficient, easier to scale, yours to build on")
 * actually cash out to. It lives here, in the plain-data module, and not beside
 * the component, because the page is a server component and a client module's
 * data export is not reachable from it.
 */
export const LEDGER: { claim: string; because: string }[] = [
  {
    claim: "you pay providers, not a platform",
    because:
      "one bill becomes your own provider accounts — nothing in the middle marking up a layer you already pay for",
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
