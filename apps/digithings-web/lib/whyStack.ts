/**
 * The data behind the `#why` guided walk (round 15, #4429).
 *
 * Folded in from the `/variants/why` exploration the owner picked. His round-10
 * direction, after rejecting the simple node graph:
 *
 *   "i want a visual like a graph like a design document or a design graph an
 *    architecture graph this is a visual graph with nodes and lines connecting
 *    the different services from a database to a cloud infrastructure the
 *    specific graph that you typically build when you're designing a system or
 *    an architecture"
 *
 *   "i can't say that i wouldn't have done a simple graph like that ... there's a
 *    convention for this that's standard practice amongst software companies"
 *
 * THE CONVENTION IS THE C4 MODEL (Simon Brown): Context -> Container ->
 * Component -> Code. What he described is specifically the CONTAINER diagram —
 * one box per deployable/runtime unit, a labelled connector per call, external
 * systems outside the boundary. Both specs below are written in that grammar,
 * and both are handed to the same renderer, so the two drawings share a
 * silhouette and diff only in what the boxes are and how they are wired.
 *
 * RULE THIS MODULE OBEYS: the conventional side names NO vendor. Round 9b
 * taught that lesson twice — every box is a CATEGORY an engineer would draw
 * ("their models"), never a brand, and never a digi module name either.
 *
 * Plain data, therefore server-safe: the band renders it from a server
 * component.
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
  title: "The AI stack you rent",
  description:
    "Container diagram: your product calls one vendor interface, and behind it sit the model, the index, the data store, the monitoring and the machines — every layer rented by the meter, inside a single boundary governed by one account and one release schedule.",
  groups: [
    {
      id: "platform",
      label: "one vendor's roadmap · one account · one bill you don't set",
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
    { id: "model", label: "their models, their prices", icon: "server", group: "platform", col: 0, row: 2 },
    { id: "memory", label: "their index", icon: "database", group: "platform", col: 1, row: 2 },
    { id: "record", label: "their data store", icon: "database", group: "platform", col: 2, row: 2 },
    { id: "oversight", label: "their monitoring", icon: "server", group: "platform", col: 0, row: 3 },
    { id: "metal", label: "their machines", icon: "cloud", group: "platform", col: 1, row: 3 },
    { id: "terms", label: "their terms", icon: "disk", group: "platform", col: 2, row: 3 },
  ],
  edges: [
    { from: "app", to: "api", fromSide: "B", toSide: "T", label: "every request" },
    { from: "api", to: "model", fromSide: "R", toSide: "L", label: "per-token" },
    { from: "api", to: "memory", fromSide: "L", toSide: "R", label: "per-query" },
    { from: "api", to: "record", fromSide: "B", toSide: "T", label: "per-gigabyte" },
    { from: "model", to: "oversight", fromSide: "B", toSide: "T", label: "per-span" },
    { from: "memory", to: "metal", fromSide: "B", toSide: "T", label: "metered" },
    { from: "record", to: "metal", fromSide: "B", toSide: "L", label: "metered" },
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
  title: "The digithings stack you run",
  description:
    "Container diagram: the same product over the same calls, but every layer behind it is a piece you run — the interface, the model, the index, the data, the log, the machines and the keys are all yours, inside your own boundary.",
  groups: [
    {
      id: "hosts",
      label: "your hosts · your regions · your keys",
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
    { id: "model", label: "any model you choose", icon: "server", group: "hosts", col: 0, row: 2 },
    { id: "memory", label: "your index", icon: "database", group: "hosts", col: 1, row: 2 },
    { id: "record", label: "your data, on your disk", icon: "database", group: "hosts", col: 2, row: 2 },
    { id: "oversight", label: "your log", icon: "server", group: "hosts", col: 0, row: 3 },
    { id: "metal", label: "your machines", icon: "cloud", group: "hosts", col: 1, row: 3 },
    { id: "terms", label: "your keys", icon: "disk", group: "hosts", col: 2, row: 3 },
  ],
  edges: [
    { from: "app", to: "api", fromSide: "B", toSide: "T", label: "every request" },
    { from: "api", to: "model", fromSide: "R", toSide: "L", label: "swap it" },
    { from: "api", to: "memory", fromSide: "L", toSide: "R", label: "you choose" },
    { from: "api", to: "record", fromSide: "B", toSide: "T", label: "you choose" },
    { from: "model", to: "oversight", fromSide: "B", toSide: "T", label: "you see it" },
    { from: "memory", to: "metal", fromSide: "B", toSide: "T", label: "yours" },
    { from: "record", to: "metal", fromSide: "B", toSide: "L", label: "yours" },
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
    label: "You own one box. They own the rest.",
    line: "Your product sits on top. Everything it calls — the models, the index, the data, the machines — is somebody else's, and you reach it only through the shape they publish.",
    ids: ["app"],
  },
  {
    id: "interface",
    label: "One door in, and they hold the key.",
    line: "A single vendor interface is the only way through. Its limits, its version and its price are decided above you, on a schedule you do not set.",
    ids: ["app", "api"],
  },
  {
    id: "services",
    label: "Every layer below is rented by the meter.",
    line: "The model bills per token, the index per query, the data per gigabyte — three contracts, three meters, and nothing you can reach in to change.",
    ids: ["app", "api", "model", "memory", "record"],
  },
  {
    id: "closed",
    label: "One wall, and it does not open.",
    line: "Monitoring, machines and the terms all sit behind the same closed boundary. This is not a smaller stack than digithings — it is the same stack with nothing in it you can move.",
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
    label: "Same stack. Every box is yours.",
    line: "Nothing about the shape changes. What changes is that every layer behind your product is a piece you run, on infrastructure you already pay for, behind a boundary only you open.",
    ids: [],
  },
  {
    id: "surface",
    label: "Your product, unchanged.",
    line: "The top box is exactly the product you had. It calls an interface the same way it always did — the difference is that you publish that interface now.",
    ids: ["app"],
  },
  {
    id: "intelligence",
    label: "Swap the model, ship nothing.",
    line: "The interface and the model are separate layers, so a better or cheaper model drops in behind the same call. No migration, no rewrite, no vendor's roadmap dictating yours.",
    ids: ["api", "model"],
  },
  {
    id: "memory",
    label: "Your index. Your data. On your disk.",
    line: "Retrieval points at a store you choose and the records never leave your boundary. The knowledge your product depends on is an asset you hold, not one you rent back.",
    ids: ["memory", "record"],
  },
  {
    id: "operations",
    label: "The whole run stays visible to you.",
    line: "The log of what ran and the machines it ran on are both inside your boundary — your regions, your accounts, an audit trail you can read end to end.",
    ids: ["oversight", "metal"],
  },
  {
    id: "keys",
    label: "The keys never leave your hands.",
    line: "Access is issued and revoked by you and carried on every call. The boundary is not a wall you rent — it is a set of seams you can move whenever you want to. Each seam is a piece you can take alone — adopt one layer or run the whole stack.",
    ids: ["terms"],
  },
];
