/**
 * The data behind `/variants/why` (round 9c, #4429).
 *
 * One architecture grammar, drawn twice. The owner's round-9c direction, after
 * rejecting the vendor-marked slabs and the invoice column:
 *
 *   "i don't like that we're naming openai anthropic gemini specifically i don't
 *    want to name the stack elements i don't like that there's the invoice i want
 *    a visual like a graph like a design document or a design graph an
 *    architecture graph this is a visual graph with nodes and lines connecting
 *    the different services from a database to a cloud infrastructure the
 *    specific graph that you typically build when you're designing a system or an
 *    architecture that's what i want to show and we basically compare what that
 *    looks like for the conventional off-the-shelf solution versus what that
 *    would look like for digi things if you were to use all the digi things
 *    modules"
 *
 * So: two node-and-edge diagrams, both drawn from the same box/line vocabulary
 * and the same viewBox, differing only in what the boxes are called and how they
 * are wired. The conventional side names NO vendor — it names the generic parts
 * an engineer would draw (an application, an API, a managed model, an index, a
 * database, a queue, telemetry, a cache, a cloud, an account). The digithings
 * side names the actual modules, because the owner asked for exactly that
 * ("if you were to use all the digi things modules") and the module names are
 * the product, not a third party.
 *
 * The only edge between the two diagrams is the shape: same boundary rectangle,
 * same rows, same connectors. On the rented side the boundary is dashed and
 * everything behind the surface belongs to one vendor; on the owned side the
 * boundary is solid and every node is a process you run.
 *
 * HONESTY: no amount, percentage, "Nx cheaper", contract-terms claim or
 * performance figure appears anywhere in this module. The cost argument is made
 * by the SHAPE — one closed boundary with no seams you can move — not by a
 * number the repository cannot source.
 *
 * Plain data, therefore server-safe: the variants page is a server component and
 * cannot reach a client module's exports.
 */

/** What a box is, so the diagram can style the few that are not plain services. */
export type ArchKind = "app" | "service" | "infra" | "account";

/** One box on the diagram. `x`/`y` are the box centre in the shared viewBox. */
export interface ArchNode {
  id: string;
  label: string;
  kind: ArchKind;
  x: number;
  y: number;
}

/** One connector. Drawn only when both ends are lit. */
export interface ArchEdge {
  a: string;
  b: string;
}

/** The rectangle every box sits inside — the boundary, drawn on both sides. */
export interface ArchBoundary {
  x: number;
  y: number;
  w: number;
  h: number;
  /** Uppercase mono caption on the boundary's top edge. */
  label: string;
}

export interface ArchGraph {
  nodes: ArchNode[];
  edges: ArchEdge[];
  boundary: ArchBoundary;
  aria: string;
}

/** Box geometry, shared by both diagrams so they diff at a glance. */
export const NODE_W = 168;
export const NODE_H = 42;
/** The shared drawing frame. */
export const VIEW = { w: 960, h: 600 };

/**
 * The conventional off-the-shelf stack: the generic parts, no vendors named.
 *
 * The layout is what an engineer sketches for a managed platform — your app on
 * top of one vendor API, the managed services fanned out behind it, the cloud
 * underneath, and one account that governs all of it.
 */
export const RENTED_GRAPH: ArchGraph = {
  aria: "Architecture diagram: an application calling one vendor API, behind which sit a managed model, a managed index, a managed database, a managed queue, managed telemetry, a managed cache and the vendor's cloud, all inside one vendor boundary governed by one account.",
  boundary: { x: 48, y: 104, w: 864, h: 456, label: "the managed platform · one account · one release schedule" },
  nodes: [
    { id: "app", label: "your app", kind: "app", x: 480, y: 46 },
    { id: "api", label: "vendor api", kind: "service", x: 480, y: 140 },
    { id: "llm", label: "managed model", kind: "service", x: 150, y: 258 },
    { id: "index", label: "managed index", kind: "service", x: 350, y: 258 },
    { id: "db", label: "managed database", kind: "service", x: 560, y: 258 },
    { id: "queue", label: "managed queue", kind: "service", x: 770, y: 258 },
    { id: "obs", label: "managed telemetry", kind: "service", x: 250, y: 388 },
    { id: "cache", label: "managed cache", kind: "service", x: 480, y: 388 },
    { id: "cloud", label: "their cloud", kind: "infra", x: 720, y: 388 },
    { id: "account", label: "their accounts", kind: "account", x: 480, y: 512 },
  ],
  edges: [
    { a: "app", b: "api" },
    { a: "api", b: "llm" },
    { a: "api", b: "index" },
    { a: "api", b: "db" },
    { a: "api", b: "queue" },
    { a: "llm", b: "obs" },
    { a: "index", b: "cache" },
    { a: "db", b: "cache" },
    { a: "queue", b: "cloud" },
    { a: "obs", b: "cloud" },
    { a: "cache", b: "cloud" },
    { a: "api", b: "account" },
  ],
};

/**
 * The same system built from the digithings modules.
 *
 * Same frame, same rows, same connector vocabulary — the boxes are the modules
 * and the dashed vendored services have become processes you run. The edges are
 * the real module topology (the same pairs `packages/ui/src/data/modules.ts`
 * declares), so the diagram is the product's actual architecture and not a
 * drawing of one.
 */
export const OWNED_GRAPH: ArchGraph = {
  aria: "Architecture diagram: your app on top of digigraph, with digiquant, digisearch, digivault and digichat alongside it, digikey, digismith and digiclaw beneath, and digibase under all of it — every node a module you run inside your own boundary.",
  boundary: { x: 48, y: 104, w: 864, h: 456, label: "your hosts · your regions · your accounts" },
  nodes: [
    { id: "app", label: "your app", kind: "app", x: 480, y: 46 },
    { id: "graph", label: "digigraph", kind: "service", x: 480, y: 140 },
    { id: "quant", label: "digiquant", kind: "service", x: 150, y: 258 },
    { id: "search", label: "digisearch", kind: "service", x: 350, y: 258 },
    { id: "vault", label: "digivault", kind: "service", x: 560, y: 258 },
    { id: "chat", label: "digichat", kind: "service", x: 770, y: 258 },
    { id: "key", label: "digikey", kind: "service", x: 250, y: 388 },
    { id: "smith", label: "digismith", kind: "service", x: 480, y: 388 },
    { id: "claw", label: "digiclaw", kind: "service", x: 720, y: 388 },
    { id: "base", label: "digibase", kind: "infra", x: 480, y: 512 },
  ],
  edges: [
    { a: "app", b: "graph" },
    { a: "graph", b: "quant" },
    { a: "graph", b: "search" },
    { a: "graph", b: "vault" },
    { a: "graph", b: "chat" },
    { a: "graph", b: "key" },
    { a: "graph", b: "smith" },
    { a: "graph", b: "claw" },
    { a: "chat", b: "key" },
    { a: "chat", b: "search" },
    { a: "claw", b: "quant" },
    { a: "smith", b: "chat" },
    { a: "search", b: "base" },
  ],
};

export interface WhyStep {
  id: string;
  /** The stepper's line. */
  label: string;
  /** One sentence of mechanism — what is true, not what is promised. */
  line: string;
  /** Node ids this step lights up. Marks accumulate in the walker. */
  marks: string[];
}

/**
 * The rented half: the diagram assembles the way a managed platform is sold —
 * surface first, then the services behind it, then the boundary that closes.
 */
export const RENTED_STEPS: WhyStep[] = [
  {
    id: "app",
    label: "The surface",
    line: "You get an application and one endpoint. The application is the surface — it is the only part you actually touch.",
    marks: ["app"],
  },
  {
    id: "api",
    label: "One vendor api",
    line: "Behind it a single API decides what you can reach. You do not choose the services behind the API, and you cannot replace one of them.",
    marks: ["app", "api"],
  },
  {
    id: "services",
    label: "Managed services",
    line: "The model, the index, the database and the queue are four separate products, each rented and each metered. None of them is yours to swap.",
    marks: ["app", "api", "llm", "index", "db", "queue"],
  },
  {
    id: "plumbing",
    label: "The plumbing",
    line: "Telemetry, cache and the cloud underneath are rented too. The traces expire on the vendor's schedule and the capacity is theirs to allocate.",
    marks: ["app", "api", "llm", "index", "db", "queue", "obs", "cache", "cloud"],
  },
  {
    id: "boundary",
    label: "One closed boundary",
    line: "One account governs all of it, and the release schedule is the vendor's. Inside the boundary there is no seam you can move — that is the whole shape.",
    marks: RENTED_GRAPH.nodes.map((node) => node.id),
  },
];

/** The owned half's arc, shown above its steps. */
export const OWNED_ARC = ["rented", "modular", "yours"] as const;
export type OwnedArc = (typeof OWNED_ARC)[number];

export interface OwnedStep extends WhyStep {
  arc: OwnedArc;
}

/**
 * The owned half: the SAME frame, rebuilt node by node. Each step adds modules
 * and keeps the previous ones, so the diagram fills up rather than flashing one
 * box at a time.
 */
export const OWNED_STEPS: OwnedStep[] = [
  {
    id: "graph",
    label: "One graph on your hosts",
    line: "digigraph routes every request. It is a process you run, not an endpoint you call, so the path a request takes is visible and editable.",
    marks: ["app", "graph"],
    arc: "modular",
  },
  {
    id: "modules",
    label: "The capabilities",
    line: "Quant, retrieval, the vault and chat are separate modules with separate state. Swap one and the others keep running — no module assumes another.",
    marks: ["app", "graph", "quant", "search", "vault", "chat"],
    arc: "modular",
  },
  {
    id: "guards",
    label: "Keys, traces, heartbeat",
    line: "Auth issues the keys and scopes them on every call, tracing records what ran, and the heartbeat keeps it alive — all three run where the rest runs.",
    marks: ["app", "graph", "quant", "search", "vault", "chat", "key", "smith", "claw"],
    arc: "yours",
  },
  {
    id: "library",
    label: "Yours to build on",
    line: "One shared library under all of it, and every capability is also a REST endpoint, an MCP tool, a CLI command and a container. You ship the app.",
    marks: OWNED_GRAPH.nodes.map((node) => node.id),
    arc: "yours",
  },
];

/** Everything in a set of mark lists — what a reduced-motion reader sees. */
export function allMarks(...groups: string[][]): string[] {
  const seen = new Set<string>();
  groups.forEach((group) => group.forEach((mark) => seen.add(mark)));
  return [...seen];
}

/** One node id per node, in draw order — the "everything lit" state. */
export const RENTED_MARKS = RENTED_GRAPH.nodes.map((node) => node.id);
export const OWNED_MARKS = OWNED_GRAPH.nodes.map((node) => node.id);

/**
 * The benefit ledger, as structural consequences rather than figures.
 *
 * Each of these is what changes about the structure — the claim the four
 * benefit words ("cheaper, more efficient, easier to scale, yours to build on")
 * actually cash out to. No number appears in any of them.
 */
export const LEDGER: { claim: string; because: string }[] = [
  {
    claim: "you pay providers, not a platform",
    because:
      "the middle of your bill becomes your own provider accounts — nothing sits between you and a layer you already pay for",
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
