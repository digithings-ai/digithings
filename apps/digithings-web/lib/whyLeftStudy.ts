/**
 * Study D — the traditional AI stack, drawn accurately (review-only).
 *
 * Renders on `/variants/why-copy` as a single-side guided walk. The live
 * band is untouched; this migrates over only when the drawing freezes.
 *
 * What's accurate here, box by box: the client's own data sources sit
 * OUTSIDE the wall (they're yours — the hook is that the only way in is
 * their connectors); models, embeddings, vectors, lake, telemetry, GPUs
 * and terms sit inside one provider boundary labeled app-to-silicon (the
 * vertical-integration trend: model companies buying the layers above and
 * below their models). Vectors live with the provider and only their
 * embedding models fit — switching models means re-embedding everything,
 * which is the working lock-in, not an abstraction.
 *
 * The walk runs the three beats in order — locked in, not modular, more
 * expensive — then lands the trend: the wall gets taller, not shorter.
 * No vendor is named anywhere (repo rule); no figures, only meters.
 */

import type { ArchSpec, TourStep } from "@digithings/ui";

export const TRADITIONAL_ARCH: ArchSpec = {
  title: "The traditional AI stack",
  description:
    "Layered diagram: your product and data sources on top, everything else — gateway, models, embeddings, vectors, lake, telemetry, GPUs, terms — inside one provider boundary.",
  groups: [
    {
      id: "platform",
      label: "one provider · app to silicon",
      icon: "cloud",
      col: 0,
      row: 1,
      cols: 3,
      rows: 4,
    },
  ],
  services: [
    { id: "app", label: "your product", icon: "internet", col: 0, row: 0 },
    { id: "sources", label: "your data sources", icon: "database", col: 2, row: 0 },
    { id: "api", label: "their API gateway", icon: "server", group: "platform", col: 1, row: 1 },
    { id: "model", label: "their models", icon: "server", group: "platform", col: 0, row: 2 },
    { id: "embed", label: "their embeddings", icon: "server", group: "platform", col: 1, row: 2 },
    { id: "memory", label: "their vector DB", icon: "database", group: "platform", col: 2, row: 2 },
    { id: "record", label: "their data lake", icon: "database", group: "platform", col: 0, row: 3 },
    { id: "telemetry", label: "their telemetry", icon: "server", group: "platform", col: 1, row: 3 },
    { id: "machines", label: "their GPUs", icon: "cloud", group: "platform", col: 2, row: 3 },
    { id: "terms", label: "their terms", icon: "disk", group: "platform", col: 1, row: 4 },
  ],
  edges: [
    { from: "app", to: "api", fromSide: "B", toSide: "T", label: "one SDK" },
    { from: "sources", to: "api", fromSide: "B", toSide: "T", label: "their connectors" },
    { from: "api", to: "model", fromSide: "L", toSide: "R", label: "per-token" },
    { from: "api", to: "memory", fromSide: "R", toSide: "L", label: "per-query" },
    { from: "api", to: "embed", fromSide: "B", toSide: "T", label: "bundled in" },
    { from: "embed", to: "memory", fromSide: "R", toSide: "L", label: "their format" },
    { from: "api", to: "record", fromSide: "L", toSide: "T", label: "per-GB" },
    { from: "model", to: "telemetry", fromSide: "B", toSide: "L", label: "their dashboard" },
    { from: "memory", to: "machines", fromSide: "B", toSide: "T", label: "same roof" },
    { from: "machines", to: "terms", fromSide: "B", toSide: "L", label: "their terms" },
  ],
};

export const TRADITIONAL_STEPS: TourStep[] = [
  {
    id: "yours",
    label: "Your product, your data — their everything else.",
    line: "The top row is the only part you hold: your product and your data sources. But the only way data gets in is through their connectors, on their terms.",
    ids: ["app", "sources"],
  },
  {
    id: "door",
    label: "One door in, and they hold the key.",
    line: "A single gateway fronts the whole stack. Its SDK version, its limits and its prices move on a schedule you don't set — and every layer below is reachable only through it.",
    ids: ["app", "sources", "api"],
  },
  {
    id: "locked",
    label: "Locked in at the embedding layer.",
    line: "Vectors live with the provider, and only their embedding models fit the index. Switching models means re-embedding everything you own — that is the lock-in that actually bites, long before the contract does.",
    ids: ["api", "model", "embed", "memory"],
  },
  {
    id: "metered",
    label: "Watched, metered, and minted below.",
    line: "The lake, the telemetry and the GPUs all bill inside the same wall — per token, per query, per gigabyte. Nothing here is modular: no layer can be swapped without leaving the wall.",
    ids: ["record", "telemetry", "machines"],
  },
  {
    id: "taller",
    label: "And the wall gets taller, not shorter.",
    line: "Model companies keep buying the layers above and below their models — apps at the top, chips at the bottom. The industry trend is toward more lock-in per stack, not less. That is the shape digithings is drawn against.",
    ids: ["app", "sources", "api", "model", "embed", "memory", "record", "telemetry", "machines", "terms", "platform"],
  },
];
