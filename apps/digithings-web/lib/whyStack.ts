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
 * RULE THIS MODULE OBEYS, per side: the conventional side names NO vendor.
 * Round 9b taught that lesson twice — every rented box is a CATEGORY an
 * engineer would draw ("their models"), never a brand. The digithings side
 * is the deliberate exception (round 16, owner direction): every box there
 * names the module that runs it, so the diagram reads as a parts list you
 * compose — interface with digichat, models with digillm — instead of a
 * second set of abstractions.
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
  title: "The fixed AI stack",
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
 * The digithings side: the same product on top, but every layer behind it is
 * a NAMED module you compose — nine boxes, one per shipped service, inside a
 * boundary that says digithings instead of describing your hosts. Deliberately
 * NOT the rented topology: the asymmetry is the argument (one fixed shape vs
 * pieces you compose). digibase is the shared library inside every box rather
 * than a box of its own; digistore and digilink are roadmap and stay out of
 * the drawing (the mosaic above already labels them roadmap).
 */
export const DIGITHINGS_ARCH: ArchSpec = {
  title: "The digithings stack you compose",
  description:
    "Container diagram: the same product over the same calls, but every layer behind it is a named digithings module — chat, router, models, index, vault, strategies, scheduler, traces, keys — composed on your hosts, inside your boundary.",
  groups: [
    {
      id: "digithings",
      label: "digithings · take one module or run them all",
      icon: "server",
      col: 0,
      row: 1,
      cols: 3,
      rows: 3,
    },
  ],
  services: [
    { id: "app", label: "your product", icon: "internet", col: 1, row: 0 },
    { id: "chat", label: "digichat · chat interface", icon: "server", group: "digithings", col: 0, row: 1 },
    { id: "graph", label: "digigraph · request router", icon: "server", group: "digithings", col: 1, row: 1 },
    { id: "models", label: "digillm · model gateway", icon: "server", group: "digithings", col: 2, row: 1 },
    { id: "memory", label: "digisearch · vector index", icon: "database", group: "digithings", col: 0, row: 2 },
    { id: "vault", label: "digivault · notes vault", icon: "database", group: "digithings", col: 1, row: 2 },
    { id: "quant", label: "digiquant · strategy lab", icon: "cloud", group: "digithings", col: 2, row: 2 },
    { id: "traces", label: "digismith · run traces", icon: "server", group: "digithings", col: 0, row: 3 },
    { id: "claw", label: "digiclaw · scheduler", icon: "server", group: "digithings", col: 1, row: 3 },
    { id: "keys", label: "digikey · your keys", icon: "disk", group: "digithings", col: 2, row: 3 },
  ],
  edges: [
    { from: "app", to: "chat", fromSide: "B", toSide: "T", label: "every request" },
    { from: "chat", to: "graph", fromSide: "R", toSide: "L", label: "routes" },
    { from: "graph", to: "models", fromSide: "R", toSide: "L", label: "you choose" },
    { from: "graph", to: "memory", fromSide: "L", toSide: "R", label: "you choose" },
    { from: "graph", to: "quant", fromSide: "B", toSide: "T", label: "your strategies" },
    { from: "models", to: "keys", fromSide: "B", toSide: "T", label: "your rates" },
    { from: "models", to: "traces", fromSide: "B", toSide: "T", label: "you see it" },
    { from: "claw", to: "graph", fromSide: "T", toSide: "B", label: "on a schedule" },
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
 * The walk over the digithings diagram, step by step. The frame is custom
 * builds, not ownership: compose vs fixed shape, one layer or all, swap
 * without migrating, your keys your rates — with owning the stack as one
 * thread among them, never the headline. Every id here must exist in
 * `DIGITHINGS_ARCH`. Six steps, comparable to the rented four.
 */
export const OWNED_TOUR_STEPS: TourStep[] = [
  {
    id: "overview",
    label: "One fixed shape, or pieces you compose.",
    line: "The calls don't change — your product still calls an interface. What changes is that every layer behind it is a named module you can take alone or run together, on hosts you already pay for.",
    ids: [],
  },
  {
    id: "front",
    label: "Your front door, your router.",
    line: "digichat is the interface your product talks to; digigraph routes each request — chat, retrieval, or research — to the right module. Swap either without touching your product.",
    ids: ["chat", "graph"],
  },
  {
    id: "models",
    label: "Any model. Your keys, your rates.",
    line: "digillm routes to whichever provider wins today — model string, your key, your bill. When a cheaper model drops, you change a string, not a vendor.",
    ids: ["models"],
  },
  {
    id: "knowledge",
    label: "Your index, your vault.",
    line: "digisearch queries whatever backend you run; digivault keeps your notes addressable. Move stores without rewriting — the calls stay yours.",
    ids: ["memory", "vault"],
  },
  {
    id: "work",
    label: "Your strategies, on your schedule.",
    line: "digiquant researches against a real backtest engine; digiclaw keeps the loop running on an interval. Your book, and an audit trail you can read.",
    ids: ["quant", "claw"],
  },
  {
    id: "trust",
    label: "Your keys, your traces.",
    line: "digikey issues and revokes access; digismith traces every hop. Owning the stack is part of it — never being locked in is the point.",
    ids: ["keys", "traces"],
  },
];
