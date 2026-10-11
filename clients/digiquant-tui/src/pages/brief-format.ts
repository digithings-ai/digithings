import { DASH, EMPTY_READ, type ReadResult } from "../read";
import { shapeLines, type PaneBlock, type PaneBody } from "./shape";

/** Brief panes. Stat, then table. A chart needs a series this page does not return. */
const BRIEF_IDS = ["brief", "live", "decision", "signals", "risks", "movers", "pl-run-health"] as const;

type BriefId = (typeof BRIEF_IDS)[number];

function isBriefId(id: string): id is BriefId {
  return (BRIEF_IDS as readonly string[]).includes(id);
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

function bodyOf(blocks: PaneBlock[]): PaneBody {
  return { blocks: blocks.length > 0 ? blocks : [{ kind: "sentence", text: EMPTY_READ }] };
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

function paintBrief(data: Record<string, unknown>): PaneBody {
  const tip = rec(data.nav_tip);
  const overlay = rec(data.overlay);
  const blocks: PaneBlock[] = [];
  const head = stat([
    ["NAV", cell(tip?.nav)],
    ["date", cell(tip?.date)],
    ["contract", cell(tip?.contract)],
    ["day", cell(data.day_return_pct)],
    ["since", cell(data.since_inception_pct)],
    ["invested", cell(data.invested_pct)],
    ["overlay", cell(overlay?.badge)],
    ["vs mark", cell(overlay?.live_vs_mark_pct)],
  ]);
  if (head) blocks.push(head);
  const events = Array.isArray(data.session_events) ? data.session_events : [];
  const rows: string[][] = [];
  for (const item of events) {
    const row = rec(item);
    if (!row) continue;
    const ticker = typeof row.ticker === "string" ? row.ticker : "";
    const event = typeof row.event === "string" ? row.event : "";
    if (!ticker && !event) continue;
    rows.push([cell(row.date), ticker || DASH, event || DASH, cell(row.weight_pct)]);
  }
  const list = table(["date", "ticker", "event", "weight"], rows);
  if (list) blocks.push(list);
  return bodyOf(blocks);
}

function paintLive(data: Record<string, unknown>): PaneBody {
  const blocks: PaneBlock[] = [];
  const head = stat([
    ["quote", cell(data.quote_date)],
    ["vs mark", cell(data.live_vs_mark_pct)],
    ["day", cell(data.day_return_live_pct)],
    ["since", cell(data.since_inception_live_pct)],
    ["excess", cell(data.excess_live_pct)],
    ["overlay", cell(data.overlay_eligible)],
  ]);
  if (head) blocks.push(head);
  const universe = Array.isArray(data.universe) ? data.universe : [];
  const rows: string[][] = [];
  for (const item of universe) {
    if (typeof item === "string" && item.trim()) rows.push([item]);
  }
  const list = table(["symbol"], rows);
  if (list) blocks.push(list);
  return bodyOf(blocks);
}

function paintDecision(data: Record<string, unknown>): PaneBody {
  const decision = data.decision === null ? null : rec(data.decision);
  if (!("decision" in data) || decision === null) return sentence(EMPTY_READ);
  const lead = typeof decision.lead === "string" ? decision.lead.trim() : "";
  const note = typeof decision.body === "string" ? decision.body.trim() : "";
  const blocks: PaneBlock[] = [];
  const when = stat([["run", cell(decision.run_date)]]);
  if (when) blocks.push(when);
  const text = [lead, note].filter((part) => part.length > 0).join("\n");
  if (text) blocks.push({ kind: "sentence", text });
  return bodyOf(blocks);
}

function paintSignals(data: Record<string, unknown>): PaneBody {
  if (!Array.isArray(data.theses) || data.theses.length === 0) return sentence(EMPTY_READ);
  const rows: string[][] = [];
  for (const item of data.theses) {
    const row = rec(item);
    if (!row || typeof row.name !== "string" || row.name.length === 0) continue;
    const vehicles = Array.isArray(row.vehicles)
      ? row.vehicles.filter((name): name is string => typeof name === "string" && name.length > 0).join(", ")
      : "";
    rows.push([row.name, cell(row.state), vehicles || DASH]);
  }
  const blocks: PaneBlock[] = [];
  const counts = rec(data.counts);
  const head = counts
    ? stat([
        ["active", cell(counts.active)],
        ["watch", cell(counts.watch)],
        ["exited", cell(counts.exited)],
      ])
    : null;
  if (head) blocks.push(head);
  const list = table(["name", "state", "vehicles"], rows);
  if (list) blocks.push(list);
  return bodyOf(blocks);
}

function paintRisks(data: Record<string, unknown>): PaneBody {
  if (!Array.isArray(data.risks)) return sentence(EMPTY_READ);
  const rows = data.risks
    .filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    .map((item) => [item]);
  const list = table([], rows);
  return list ? { blocks: [list] } : sentence(EMPTY_READ);
}

function paintMovers(data: Record<string, unknown>): PaneBody {
  if (!Array.isArray(data.rows)) return sentence(EMPTY_READ);
  const rows: string[][] = [];
  for (const item of data.rows) {
    const row = rec(item);
    if (!row || typeof row.ticker !== "string" || row.ticker.length === 0) continue;
    rows.push([
      row.ticker,
      cell(row.sleeve),
      cell(row.scaled_weight_pct),
      cell(row.current_price),
      cell(row.day_return_pct),
      cell(row.unrealized_pct),
    ]);
  }
  const list = table(["ticker", "sleeve", "weight", "price", "day", "unrealized"], rows);
  return list ? { blocks: [list] } : sentence(EMPTY_READ);
}

function paintHealth(data: Record<string, unknown>): PaneBody {
  const nodes = rec(data.nodes);
  const head = stat([
    ["run", cell(data.run_date)],
    ["type", cell(data.run_type)],
    ["status", cell(data.status)],
    ["config", cell(data.config)],
    ["ok", cell(nodes?.ok)],
    ["carried", cell(nodes?.carried)],
    ["failed", cell(nodes?.failed)],
  ]);
  return head ? { blocks: [head] } : sentence(EMPTY_READ);
}

function paint(id: BriefId, data: Record<string, unknown>): PaneBody {
  switch (id) {
    case "brief":
      return paintBrief(data);
    case "live":
      return paintLive(data);
    case "decision":
      return paintDecision(data);
    case "signals":
      return paintSignals(data);
    case "risks":
      return paintRisks(data);
    case "movers":
      return paintMovers(data);
    case "pl-run-health":
      return paintHealth(data);
    default: {
      const exhaustive: never = id;
      return sentence(String(exhaustive));
    }
  }
}

/** One brief pane. Errors, stubs, and empty payloads stay the official sentence. */
export function briefBlocks(id: string, data: unknown, result: ReadResult): PaneBody {
  if (result.status === "error" || result.status === "stub" || result.status === "empty" || data == null) {
    return textBody(result);
  }
  const row = rec(data);
  if (!row || !isBriefId(id)) return textBody(result);
  return withProvenance(result, paint(id, row));
}
