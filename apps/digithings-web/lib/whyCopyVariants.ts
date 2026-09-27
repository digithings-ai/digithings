/**
 * The why-band v2 takes: three DIFFERENT arguments with three DIFFERENT
 * drawings. Review-only — `/variants/why-copy` renders one full band per
 * version so the owner can scroll each and pick. The live band stays
 * untouched until a version freezes and migrates over.
 *
 * - A "One wall, or eight seams": a brand-new monolith diagram (3 boxes)
 *   walked against the exploded 8-module build. Lock-in argument.
 * - B "Start with the layer that hurts": four cumulative stage diagrams,
 *   no scroll-walk. Modularity / land-and-expand argument.
 * - C "The invoice duel": no diagrams — two ledgers, their invoice vs your
 *   rates. Price argument. No figures anywhere: meters are qualitative.
 */

import type { ArchSpec, TourStep } from "@digithings/ui";

/* ═══════════ A. the monolith (fresh left diagram) ═══════════ */

export const MONOLITH_ARCH: ArchSpec = {
  title: "One vendor. One wall.",
  description:
    "Your product calls one platform. Everything behind it — models, index, data, log, machines, keys — is one box, one bill, one roadmap.",
  groups: [
    {
      id: "platform",
      label: "one bill · one roadmap · no seams",
      icon: "cloud",
      col: 0,
      row: 1,
      cols: 2,
      rows: 1,
    },
  ],
  services: [
    { id: "app", label: "your product", icon: "internet", col: 0, row: 0 },
    { id: "api", label: "their interface", icon: "server", group: "platform", col: 0, row: 1 },
    { id: "all", label: "models · index · data · log · machines · keys", icon: "server", group: "platform", col: 1, row: 1 },
  ],
  edges: [
    { from: "app", to: "api", fromSide: "B", toSide: "T", label: "every request" },
    { from: "api", to: "all", fromSide: "R", toSide: "L", label: "trust us" },
  ],
};

export const MONOLITH_STEPS: TourStep[] = [
  {
    id: "door",
    label: "One door, and they hold the key.",
    line: "Your product calls one interface. Its limits, its version and its price are decided above you.",
    ids: ["app", "api"],
  },
  {
    id: "wall",
    label: "One wall behind it.",
    line: "Models, index, data, log, machines, keys — a single box you cannot open, swap, or see into.",
    ids: ["all", "platform"],
  },
  {
    id: "bill",
    label: "One bill, and you don't set it.",
    line: "Every layer is priced by someone else, on a roadmap you don't vote on. The only direction is their next version.",
    ids: ["app", "api", "all", "platform"],
  },
];

/* ═══════════ B. the adoption ladder (four cumulative stages) ═══════════ */

export interface LadderStage {
  id: string;
  label: string;
  line: string;
  spec: ArchSpec;
}

const LADDER_APP = { id: "app", label: "your product", icon: "internet", col: 1, row: 0 } as const;

export const LADDER_STAGES: LadderStage[] = [
  {
    id: "s1",
    label: "Step 1 — Talk to your own knowledge.",
    line: "digichat over digisearch: ask your docs with your key. One module pair, running this week.",
    spec: {
      title: "digithings · step 1 of 4",
      description: "Chat over your index.",
      groups: [{ id: "digithings", label: "digithings · month one", icon: "server", col: 0, row: 1, cols: 4, rows: 1 }],
      services: [
        { ...LADDER_APP },
        { id: "chat", label: "digichat · chat interface", icon: "server", group: "digithings", col: 0, row: 1 },
        { id: "memory", label: "digisearch · vector index", icon: "database", group: "digithings", col: 3, row: 1 },
      ],
      edges: [{ from: "app", to: "chat", fromSide: "B", toSide: "T", label: "every request" }],
    },
  },
  {
    id: "s2",
    label: "Step 2 — Choose your models.",
    line: "digigraph routes, digillm shops providers. A cheaper model is a string change, not a migration.",
    spec: {
      title: "digithings · step 2 of 4",
      description: "Router plus model gateway.",
      groups: [{ id: "digithings", label: "digithings · quarter two", icon: "server", col: 0, row: 1, cols: 4, rows: 1 }],
      services: [
        { ...LADDER_APP },
        { id: "chat", label: "digichat · chat interface", icon: "server", group: "digithings", col: 0, row: 1 },
        { id: "graph", label: "digigraph · request router", icon: "server", group: "digithings", col: 1, row: 1 },
        { id: "models", label: "digillm · model gateway", icon: "server", group: "digithings", col: 2, row: 1 },
        { id: "memory", label: "digisearch · vector index", icon: "database", group: "digithings", col: 3, row: 1 },
      ],
      edges: [
        { from: "app", to: "chat", fromSide: "B", toSide: "T", label: "every request" },
        { from: "chat", to: "graph", fromSide: "R", toSide: "L", label: "routes" },
        { from: "graph", to: "models", fromSide: "R", toSide: "L", label: "you choose" },
        { from: "graph", to: "memory", fromSide: "L", toSide: "R", label: "you choose" },
      ],
    },
  },
  {
    id: "s3",
    label: "Step 3 — Keep your data.",
    line: "digivault holds your notes, digikey holds your keys. Nothing you adopt locks the rest.",
    spec: {
      title: "digithings · step 3 of 4",
      description: "Vault plus keys.",
      groups: [{ id: "digithings", label: "digithings · half built", icon: "server", col: 0, row: 1, cols: 4, rows: 2 }],
      services: [
        { ...LADDER_APP },
        { id: "chat", label: "digichat · chat interface", icon: "server", group: "digithings", col: 0, row: 1 },
        { id: "graph", label: "digigraph · request router", icon: "server", group: "digithings", col: 1, row: 1 },
        { id: "models", label: "digillm · model gateway", icon: "server", group: "digithings", col: 2, row: 1 },
        { id: "memory", label: "digisearch · vector index", icon: "database", group: "digithings", col: 3, row: 1 },
        { id: "vault", label: "digivault · notes vault", icon: "database", group: "digithings", col: 0, row: 2 },
        { id: "keys", label: "digikey · your keys", icon: "disk", group: "digithings", col: 3, row: 2 },
      ],
      edges: [
        { from: "app", to: "chat", fromSide: "B", toSide: "T", label: "every request" },
        { from: "chat", to: "graph", fromSide: "R", toSide: "L", label: "routes" },
        { from: "graph", to: "models", fromSide: "R", toSide: "L", label: "you choose" },
        { from: "graph", to: "memory", fromSide: "L", toSide: "R", label: "you choose" },
        { from: "graph", to: "vault", fromSide: "B", toSide: "T", label: "you keep" },
        { from: "models", to: "keys", fromSide: "B", toSide: "T", label: "your rates" },
      ],
    },
  },
  {
    id: "s4",
    label: "Step 4 — Run it like yours.",
    line: "digiclaw keeps the loop on schedule, digismith traces every hop. The whole build, still swappable.",
    spec: {
      title: "digithings · the whole build",
      description: "Scheduler plus traces complete it.",
      groups: [{ id: "digithings", label: "digithings · take one or run them all", icon: "server", col: 0, row: 1, cols: 4, rows: 2 }],
      services: [
        { ...LADDER_APP },
        { id: "chat", label: "digichat · chat interface", icon: "server", group: "digithings", col: 0, row: 1 },
        { id: "graph", label: "digigraph · request router", icon: "server", group: "digithings", col: 1, row: 1 },
        { id: "models", label: "digillm · model gateway", icon: "server", group: "digithings", col: 2, row: 1 },
        { id: "memory", label: "digisearch · vector index", icon: "database", group: "digithings", col: 3, row: 1 },
        { id: "vault", label: "digivault · notes vault", icon: "database", group: "digithings", col: 0, row: 2 },
        { id: "traces", label: "digismith · run traces", icon: "server", group: "digithings", col: 1, row: 2 },
        { id: "claw", label: "digiclaw · scheduler", icon: "server", group: "digithings", col: 2, row: 2 },
        { id: "keys", label: "digikey · your keys", icon: "disk", group: "digithings", col: 3, row: 2 },
      ],
      edges: [
        { from: "app", to: "chat", fromSide: "B", toSide: "T", label: "every request" },
        { from: "chat", to: "graph", fromSide: "R", toSide: "L", label: "routes" },
        { from: "graph", to: "models", fromSide: "R", toSide: "L", label: "you choose" },
        { from: "graph", to: "memory", fromSide: "L", toSide: "R", label: "you choose" },
        { from: "graph", to: "vault", fromSide: "B", toSide: "T", label: "you keep" },
        { from: "models", to: "keys", fromSide: "B", toSide: "T", label: "your rates" },
        { from: "models", to: "traces", fromSide: "B", toSide: "T", label: "you see it" },
        { from: "claw", to: "graph", fromSide: "T", toSide: "B", label: "on a schedule" },
      ],
    },
  },
];

/* ═══════════ C. the invoice duel (ledger rows, no figures) ═══════════ */

export interface LedgerRow {
  layer: string;
  theirs: string;
  yours: string;
}

export const LEDGER_ROWS: LedgerRow[] = [
  { layer: "Models", theirs: "Per-token meter, priced by them", yours: "Your key at the provider rate — a cheaper model is a string change" },
  { layer: "Index", theirs: "Per-query meter on their backend", yours: "Your backend, no toll per call" },
  { layer: "Data", theirs: "Per-gigabyte rent", yours: "Your disk, your vault" },
  { layer: "Interface", theirs: "Versioned on their schedule", yours: "Your interface, your schedule" },
  { layer: "The bill", theirs: "One invoice you don't set", yours: "Bills you already pay — minus one margin" },
];
