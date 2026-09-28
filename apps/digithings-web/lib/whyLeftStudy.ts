/**
 * Study D — the traditional AI stack, drawn accurately (review-only).
 *
 * Renders on `/variants/why-copy` as a single-side guided walk. The live
 * band is untouched; this migrates over only when the drawing freezes.
 *
 * Familiar, not generic: every box names the product a team would actually
 * buy — OpenAI for the gateway, flagship and embeddings (real marks: the
 * kit ships the OpenAI glyph), Pinecone for vectors, Azure for blob and
 * GPUs, LangSmith for traces (names with generic plates: those vendors
 * publish no monochrome mark, and a fake logo would be worse than none).
 * Prices on the boxes come out of `RAG_PRICING`, so the drawing and the
 * invoice panel below it can never disagree.
 *
 * What's accurate: the client's own data sources sit OUTSIDE the wall; the
 * boundary counts its vendors ("four vendors · four meters"); vectors live
 * in Pinecone while only OpenAI's embeddings fit the workflow — switching
 * models means re-embedding ~250M tokens, which is the working lock-in.
 *
 * The walk runs the three beats — locked in, not modular, more expensive —
 * then lands the vertical-integration trend. No figures beyond researched
 * list prices; vendor names appear here because the owner directed this
 * study at familiarity (repo-wide no-vendor rule still holds everywhere
 * else, including the live band).
 */

import type { ArchSpec, TourStep } from "@digithings/ui";
import { RAG_PRICING } from "@/lib/ragCost";

const P = RAG_PRICING;

export const TRADITIONAL_ARCH: ArchSpec = {
  title: "The traditional AI stack",
  description:
    "Layered diagram: your product and data sources on top; OpenAI gateway, flagship and embeddings, Pinecone vectors, Azure blob and GPUs, and LangSmith traces inside a four-vendor wall.",
  groups: [
    {
      id: "platform",
      label: "four vendors · four meters",
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
    { id: "api", label: "OpenAI API", icon: "server", logo: "openai", group: "platform", col: 1, row: 1 },
    {
      id: "model",
      label: `GPT-5.6 Sol · $${P.chatFlagshipInPerM}/$${P.chatFlagshipOutPerM}`,
      icon: "server",
      logo: "openai",
      group: "platform",
      col: 0,
      row: 2,
    },
    {
      id: "embed",
      label: `embed-3-large · $${P.embedLargePerM}/M`,
      icon: "server",
      logo: "openai",
      group: "platform",
      col: 1,
      row: 2,
    },
    {
      id: "memory",
      label: `Pinecone · $${P.pineconeMinMonthly} floor`,
      icon: "database",
      group: "platform",
      col: 2,
      row: 2,
    },
    { id: "record", label: "Azure Blob", icon: "database", group: "platform", col: 0, row: 3 },
    {
      id: "telemetry",
      label: `LangSmith · $${P.langsmithSeatMonthly}/seat`,
      icon: "server",
      group: "platform",
      col: 1,
      row: 3,
    },
    { id: "machines", label: "Azure GPUs", icon: "cloud", group: "platform", col: 2, row: 3 },
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
    label: "One door in: the OpenAI API.",
    line: "A single gateway fronts the whole stack. Its SDK version, its limits and its prices move on a schedule you don't set — and every layer below is reachable only through it.",
    ids: ["app", "sources", "api"],
  },
  {
    id: "locked",
    label: "Locked in at the embedding layer.",
    line: "Pinecone holds your vectors, but the pipeline only speaks embed-3-large — switching models means re-embedding some 250M tokens. That is the lock-in that actually bites, long before the contract does.",
    ids: ["api", "model", "embed", "memory"],
  },
  {
    id: "metered",
    label: "LangSmith watches at $39 a seat; Azure bills the rest.",
    line: "Traces run $2.50 per thousand past the included allowance, Pinecone holds its $50 floor, and Azure meters the GPUs by the hour and the Blob by the gigabyte. Nothing here is modular: no layer can be swapped without leaving the wall.",
    ids: ["record", "telemetry", "machines"],
  },
  {
    id: "taller",
    label: "And the wall gets taller, not shorter.",
    line: "Model companies keep buying the layers above and below their models — apps at the top, chips at the bottom. The industry trend is toward more lock-in per stack, not less. That is the shape digithings is drawn against.",
    ids: ["app", "sources", "api", "model", "embed", "memory", "record", "telemetry", "machines", "terms", "platform"],
  },
];
