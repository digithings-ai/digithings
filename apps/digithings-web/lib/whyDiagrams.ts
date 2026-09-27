/**
 * Per-version diagram pairs for the why-copy variants page (Refs #4429).
 *
 * Each version is a different LENS on the same comparison, drawn as a
 * genuinely different diagram — not a relabel:
 *
 *   A-right "open hub" — the composed module map with protocol edges
 *     (HTTPS/SSE/OpenAI API/MCP/OTLP) and a "swap any box" hot-path group
 *     around the request path.
 *   C-left "bill flow" — the fixed stack plus a vendor-invoice box
 *     collecting a meter off every layer.
 *   C-right "two lanes" — modules on your hosts in one lane, your keys
 *     paying providers directly in the other, no vendor between them.
 *
 * Box IDS ARE STABLE (right: app/chat/graph/models/memory/vault/traces/
 * claw/keys + boundary; C-left extends the fixed stack with a `bill` box).
 * The v2 step text addresses boxes by id, so it works unchanged against
 * every layout here.
 *
 * No new glyphs: developer-accuracy comes from topology, labels and edges.
 * (Extending `ArchIcon` would also widen the mermaid doc-export grammar,
 * which only knows the five plates — not worth it for decoration.)
 */

import type { ArchSpec } from "@digithings/ui";

/* ══════════════ C-left: their stack, metered (bill collector) ══════════════ */

export const RENTED_METERED: ArchSpec = {
  title: "Their stack, metered",
  description:
    "Layered diagram: the same fixed stack, plus the vendor invoice at the bottom collecting a meter off every layer.",
  groups: [
    {
      id: "platform",
      label: "one account · every layer on it",
      icon: "cloud",
      col: 0,
      row: 1,
      cols: 3,
      rows: 4,
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
    { id: "bill", label: "vendor invoice", icon: "disk", group: "platform", col: 1, row: 4 },
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
    { from: "model", to: "bill", fromSide: "B", toSide: "L", label: "per-token" },
    { from: "memory", to: "bill", fromSide: "B", toSide: "T", label: "per-query" },
    { from: "record", to: "bill", fromSide: "B", toSide: "L", label: "per-GB" },
  ],
};

/* ══════════════ B-right: open hub (hot-path group) ══════════════ */

export const COMPOSE_OPEN: ArchSpec = {
  title: "The digithings stack, seam by seam",
  description:
    "Hub diagram: digigraph routes every request, and the hot path around it is a group you can swap box by box over open protocols.",
  groups: [
    {
      id: "digithings",
      label: "digithings · every seam moves",
      icon: "server",
      col: 0,
      row: 1,
      cols: 4,
      rows: 2,
    },
    {
      id: "hotpath",
      label: "hot path · swap any box",
      parent: "digithings",
    },
  ],
  services: [
    { id: "app", label: "your product", icon: "internet", col: 1, row: 0 },
    { id: "chat", label: "digichat · chat interface", icon: "server", group: "digithings", col: 0, row: 1 },
    { id: "graph", label: "digigraph · request router", icon: "server", group: "hotpath", col: 1, row: 1 },
    { id: "models", label: "digillm · model gateway", icon: "server", group: "hotpath", col: 2, row: 1 },
    { id: "memory", label: "digisearch · vector index", icon: "database", group: "digithings", col: 3, row: 1 },
    { id: "vault", label: "digivault · notes vault", icon: "database", group: "digithings", col: 0, row: 2 },
    { id: "traces", label: "digismith · run traces", icon: "server", group: "digithings", col: 1, row: 2 },
    { id: "claw", label: "digiclaw · scheduler", icon: "server", group: "digithings", col: 2, row: 2 },
    { id: "keys", label: "digikey · your keys", icon: "disk", group: "digithings", col: 3, row: 2 },
  ],
  edges: [
    { from: "app", to: "chat", fromSide: "B", toSide: "T", label: "HTTPS" },
    { from: "chat", to: "graph", fromSide: "R", toSide: "L", label: "SSE" },
    { from: "graph", to: "models", fromSide: "R", toSide: "L", label: "OpenAI API" },
    { from: "graph", to: "memory", fromSide: "R", toSide: "L", label: "HTTP" },
    { from: "graph", to: "vault", fromSide: "B", toSide: "T", label: "MCP" },
    { from: "models", to: "keys", fromSide: "B", toSide: "T", label: "your key" },
    { from: "models", to: "traces", fromSide: "B", toSide: "T", label: "OTLP" },
    { from: "claw", to: "graph", fromSide: "T", toSide: "B", label: "interval" },
  ],
};

/* ══════════════ C-right: two lanes (hosts vs providers) ══════════════ */

export const COMPOSE_ACCOUNTS: ArchSpec = {
  title: "The digithings stack, billed direct",
  description:
    "Two-lane diagram: your modules run on your hosts in one lane while your keys pay your providers directly in the other — no vendor between them.",
  groups: [
    {
      id: "digithings",
      label: "digithings · your hosts",
      icon: "server",
      col: 0,
      row: 1,
      cols: 2,
      rows: 3,
    },
    {
      id: "providers",
      label: "your providers · billed to you",
      icon: "cloud",
      col: 2,
      row: 1,
      cols: 1,
      rows: 2,
    },
  ],
  services: [
    { id: "app", label: "your product", icon: "internet", col: 0, row: 0 },
    { id: "chat", label: "digichat · chat interface", icon: "server", group: "digithings", col: 0, row: 1 },
    { id: "graph", label: "digigraph · request router", icon: "server", group: "digithings", col: 1, row: 1 },
    { id: "models", label: "digillm · model gateway", icon: "server", group: "providers", col: 2, row: 1 },
    { id: "memory", label: "digisearch · vector index", icon: "database", group: "digithings", col: 0, row: 2 },
    { id: "vault", label: "digivault · notes vault", icon: "database", group: "digithings", col: 1, row: 2 },
    { id: "keys", label: "digikey · your keys", icon: "disk", group: "providers", col: 2, row: 2 },
    { id: "traces", label: "digismith · run traces", icon: "server", group: "digithings", col: 0, row: 3 },
    { id: "claw", label: "digiclaw · scheduler", icon: "server", group: "digithings", col: 1, row: 3 },
  ],
  edges: [
    { from: "app", to: "chat", fromSide: "B", toSide: "T", label: "every request" },
    { from: "chat", to: "graph", fromSide: "R", toSide: "L", label: "routes" },
    { from: "graph", to: "models", fromSide: "R", toSide: "L", label: "your rates" },
    { from: "models", to: "keys", fromSide: "B", toSide: "T", label: "your key" },
    { from: "graph", to: "memory", fromSide: "L", toSide: "R", label: "you choose" },
    { from: "graph", to: "vault", fromSide: "B", toSide: "T", label: "you keep" },
    { from: "models", to: "traces", fromSide: "L", toSide: "R", label: "you see it" },
    { from: "claw", to: "graph", fromSide: "T", toSide: "B", label: "on a schedule" },
  ],
};
