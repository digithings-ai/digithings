/**
 * Terminal pictures of the three example apps (the #why band).
 *
 * Each drawing is the digithings flow for that app. Counters and the receipt
 * are presentational motion, not a recorded run.
 */

import type { SchematicLegend, TerminalSchematicProps } from "@digithings/ui";

const LEGEND: SchematicLegend[] = [
  { tone: "main", label: "main step" },
  { tone: "model", label: "model step" },
  { tone: "side", label: "side step" },
  { tone: "ok", label: "ok" },
];

export const APP_FLOWS: Record<string, TerminalSchematicProps> = {
  rag: {
    title: "digichat · rag loop",
    label: "digichat rag loop. not a live run",
    legend: LEGEND,
    loop: "ask again until the answer is enough",
    rows: [
      { nodes: [{ label: "digichat", tone: "main" }] },
      { nodes: [{ label: "digigraph", tone: "model" }] },
      { nodes: [{ label: "digisearch", tone: "side" }] },
      { nodes: [{ label: "digillm", tone: "model" }] },
      { nodes: [{ label: "digitrace", tone: "side" }] },
    ],
    notes: [
      "digichat asks over the corpus",
      "digigraph runs the loop",
      "digisearch recalls in an open format",
      "digillm answers behind your gateway",
      "digitrace keeps the trace",
    ],
    receipt: [
      "digichat · question",
      "digigraph · orchestrate",
      "digisearch · recall",
      "digillm · answer",
      "digitrace · trace",
    ],
  },
  support: {
    title: "digichat · support",
    label: "support email flow on digithings. not a live run",
    legend: LEGEND,
    loop: "draft again until a reply is approved",
    rows: [
      { nodes: [{ label: "digichat", tone: "main" }] },
      { nodes: [{ label: "digigraph", tone: "model" }] },
      { nodes: [{ label: "human review", tone: "main" }] },
      { nodes: [{ label: "digigraph mail", tone: "side" }] },
      { nodes: [{ label: "digitrace", tone: "side" }] },
      { nodes: [{ label: "digiclaw", tone: "side" }] },
    ],
    notes: [
      "tickets and docs stay in digichat",
      "digigraph drafts behind digillm",
      "every draft waits for human review",
      "an approved reply leaves through digigraph mail",
      "digitrace audits the draft and digiclaw keeps the schedule",
    ],
    receipt: [
      "digichat · tickets",
      "digigraph · draft",
      "review · waiting",
      "digigraph mail · approved send",
      "digitrace · audit",
      "digiclaw · schedule",
    ],
  },
  finance: {
    title: "digiquant · research",
    label: "digiquant research flow. not a live run",
    legend: LEGEND,
    loop: "run again on the digiclaw interval",
    rows: [
      { nodes: [{ label: "digiquant", tone: "main" }] },
      {
        nodes: [
          { label: "feeds", tone: "side" },
          { label: "filings", tone: "side" },
        ],
      },
      { nodes: [{ label: "digillm", tone: "model" }] },
      { nodes: [{ label: "digiclaw", tone: "side" }] },
      { nodes: [{ label: "digivault", tone: "side" }] },
      { nodes: [{ label: "digitrace", tone: "side" }] },
    ],
    notes: [
      "digiquant holds the research question",
      "feeds and filings arrive together",
      "digillm does the synthesis",
      "digiclaw fires the run on your interval",
      "digivault files the archive and digitrace audits the run",
    ],
    receipt: [
      "digiquant · question",
      "feeds · filings",
      "digillm · synthesis",
      "digiclaw · interval",
      "digivault · archive",
      "digitrace · audit",
    ],
  },
};
