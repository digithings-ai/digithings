import { DASH, EMPTY_READ, type ReadResult } from "../read";
import { shapeLines, type PaneBlock, type PaneBody } from "./shape";

/** Pipeline panes. The graph is a node table. There is no canvas. */

const NO_NODES = "No nodes in this read.";
const NO_DOCUMENT = "no document for this node";

const PIPELINE_IDS = [
  "pl-run-health",
  "pl-narrative",
  "pl-artifacts",
  "pl-canvas",
  "pl-node-document",
  "pl-call-trace",
] as const;

type PipelineId = (typeof PIPELINE_IDS)[number];

function isPipelineId(id: string): id is PipelineId {
  return (PIPELINE_IDS as readonly string[]).includes(id);
}

function rec(value: unknown): Record<string, unknown> | null {
  return value != null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function cell(value: unknown): string {
  if (value == null || value === "") return DASH;
  if (typeof value === "number") return Number.isFinite(value) ? JSON.stringify(value) : DASH;
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string") return value;
  return DASH;
}

function stat(pairs: [string, string][]): PaneBlock | null {
  const shown = pairs.filter(([, value]) => value !== DASH);
  if (shown.length === 0) return null;
  return { kind: "stat", text: shown.map(([label, value]) => `${label}  ${value}`).join("   ") };
}

function table(columns: string[], rows: string[][]): PaneBlock | null {
  if (rows.length === 0) return null;
  return { kind: "table", columns, rows };
}

function sentence(text: string): PaneBody {
  return { blocks: [{ kind: "sentence", text }] };
}

function textBody(result: ReadResult): PaneBody {
  const lines = result.lines.filter((line) => line.length > 0);
  return shapeLines(lines.length > 0 ? lines : [EMPTY_READ]);
}

function withProvenance(result: ReadResult, painted: PaneBody): PaneBody {
  const only = painted.blocks.length === 1 ? painted.blocks[0] : null;
  if (only?.kind === "sentence") return painted;
  const bits = result.lines.filter((line) => line.startsWith("source  ") || line.startsWith("marks  "));
  if (bits.length === 0) return painted;
  return { blocks: [{ kind: "stat", text: bits.join("   ") }, ...painted.blocks] };
}

function named(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
}

function paragraphs(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const text = named(item);
    return text ? [text] : [];
  });
}

function joinText(parts: (string | null)[]): string {
  return parts.filter((part): part is string => part != null && part.length > 0).join("\n");
}

function persisted(value: unknown): string {
  const row = rec(value);
  if (!row || typeof row.persisted !== "boolean") return DASH;
  return row.persisted ? "true" : "false";
}

function paintHealth(data: Record<string, unknown>): PaneBody {
  const nodes = rec(data.nodes);
  const head = stat([
    ["run", cell(data.run_date)],
    ["type", cell(data.run_type)],
    ["status", cell(data.status)],
    ["config", cell(data.config)],
    ["posture", cell(data.posture)],
    ["ok", cell(nodes?.ok)],
    ["carried", cell(nodes?.carried)],
    ["failed", cell(nodes?.failed)],
    ["calls", cell(data.calls)],
    ["persisted", persisted(data.inputs_calls)],
    ["tokens in", cell(data.tokens_in)],
    ["tokens out", cell(data.tokens_out)],
    ["cost", cell(data.cost_usd)],
  ]);
  return head ? { blocks: [head] } : sentence(EMPTY_READ);
}

function paintNarrative(data: Record<string, unknown>): PaneBody {
  const text = joinText([named(data.heading), ...paragraphs(data.paragraphs)]);
  return text ? sentence(text) : sentence(EMPTY_READ);
}

function paintDocument(data: Record<string, unknown>): PaneBody {
  const note = named(data.note);
  const text = joinText([named(data.title), ...paragraphs(data.paragraphs), note === NO_DOCUMENT ? null : note]);
  return text ? sentence(text) : sentence(EMPTY_READ);
}

function artifactRows(value: unknown): string[][] {
  if (!Array.isArray(value)) return [];
  const rows: string[][] = [];
  for (const item of value) {
    const row = rec(item);
    const node = named(row?.node);
    if (!row || !node) continue;
    rows.push([cell(row.stage), node, cell(row.document), cell(row.date)]);
  }
  return rows;
}

function paintArtifacts(data: Record<string, unknown>): PaneBody {
  const list = table(["stage", "node", "document", "date"], artifactRows(data.rows));
  return list ? { blocks: [list] } : sentence(EMPTY_READ);
}

function targets(value: unknown): string {
  if (!Array.isArray(value)) return DASH;
  const names = value.flatMap((item) => {
    const text = named(item);
    return text ? [text] : [];
  });
  return names.length > 0 ? names.join(", ") : DASH;
}

function nodeRows(value: unknown): string[][] {
  if (!Array.isArray(value)) return [];
  const rows: string[][] = [];
  for (const item of value) {
    const row = rec(item);
    const node = named(row?.label) ?? named(row?.id);
    if (!row || !node) continue;
    rows.push([node, cell(row.stage), cell(row.state), targets(row.to)]);
  }
  return rows;
}

function paintGraph(data: Record<string, unknown>): PaneBody {
  const list = table(["node", "stage", "state", "to"], nodeRows(data.nodes));
  if (!list) return sentence(NO_NODES);
  const blocks: PaneBlock[] = [];
  const head = stat([
    ["run", cell(data.run_date)],
    ["selected", cell(data.selected_node)],
  ]);
  if (head) blocks.push(head);
  blocks.push(list);
  return { blocks };
}

function traceRows(value: unknown): string[][] {
  if (!Array.isArray(value)) return [];
  const rows: string[][] = [];
  for (const item of value) {
    const row = rec(item);
    const node = named(row?.node);
    if (!row || !node) continue;
    rows.push([node, cell(row.calls), cell(row.duration_s), cell(row.state)]);
  }
  return rows;
}

function paintTrace(data: Record<string, unknown>): PaneBody {
  const list = table(["node", "calls", "duration", "state"], traceRows(data.rows));
  return list ? { blocks: [list] } : sentence(EMPTY_READ);
}

function paint(id: PipelineId, data: Record<string, unknown>): PaneBody {
  switch (id) {
    case "pl-run-health":
      return paintHealth(data);
    case "pl-narrative":
      return paintNarrative(data);
    case "pl-artifacts":
      return paintArtifacts(data);
    case "pl-canvas":
      return paintGraph(data);
    case "pl-node-document":
      return paintDocument(data);
    case "pl-call-trace":
      return paintTrace(data);
    default: {
      const exhaustive: never = id;
      return sentence(String(exhaustive));
    }
  }
}

/** One pipeline pane. Errors, stubs, and an empty read stay the official sentence. */
export function pipelineBody(id: string, data: unknown, result: ReadResult): PaneBody {
  if (result.status === "error" || result.status === "stub") return textBody(result);
  if (result.status === "empty" || data == null) {
    return sentence(id === "pl-canvas" ? NO_NODES : EMPTY_READ);
  }
  const row = rec(data);
  if (!row || !isPipelineId(id)) return textBody(result);
  return withProvenance(result, paint(id, row));
}
