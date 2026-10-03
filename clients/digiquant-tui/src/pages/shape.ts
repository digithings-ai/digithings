import { EMPTY_READ, STUB_READ } from "../read";

/** One painted block inside a pane body. Sentences stay verbatim. A chart is one row of block characters. */
export type PaneBlock =
  | { kind: "sentence"; text: string }
  | { kind: "stat"; text: string }
  | { kind: "chart"; text: string }
  | { kind: "table"; columns: string[]; rows: string[][] };

export type PaneBody = { blocks: PaneBlock[] };

const EXACT = new Set([STUB_READ, EMPTY_READ, "loading…", "—"]);

type Classified =
  | { kind: "sentence"; text: string }
  | { kind: "pair"; key: string; value: string }
  | { kind: "keyed"; keys: string[]; values: string[] }
  | { kind: "cells"; cells: string[] };

function isSentence(text: string): boolean {
  if (EXACT.has(text)) return true;
  if (/ failed \(\d+\)/.test(text)) return true;
  if (/returned no data|could not be reached/.test(text)) return true;
  if (/^(no|No) /.test(text)) return true;
  if (/not provisioned|not configured/i.test(text)) return true;
  if (text.startsWith("…")) return true;
  return !text.includes("  ") && /[.!?]$/.test(text);
}

const KEY = /^[A-Za-z][\w .%+/-]*$/;

function asKeyed(parts: string[]): { keys: string[]; values: string[] } | null {
  if (parts.length < 2 || parts.length % 2 !== 0) return null;
  const keys: string[] = [];
  const values: string[] = [];
  for (let i = 0; i < parts.length; i += 2) {
    const key = parts[i] ?? "";
    if (!KEY.test(key)) return null;
    keys.push(key);
    values.push(parts[i + 1] ?? "");
  }
  return { keys, values };
}

/** `label value  label value` — one space inside a cell, two spaces between cells. */
function asLabeled(parts: string[]): { keys: string[]; values: string[] } | null {
  if (parts.length < 2) return null;
  const keys: string[] = [];
  const values: string[] = [];
  for (const part of parts) {
    const space = part.indexOf(" ");
    if (space <= 0) return null;
    const key = part.slice(0, space);
    const value = part.slice(space + 1);
    if (!KEY.test(key) || value.length === 0) return null;
    keys.push(key);
    values.push(value);
  }
  return { keys, values };
}

function classifyRaw(line: string): Classified {
  if (isSentence(line)) return { kind: "sentence", text: line };
  const parts = line
    .split("  ")
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
  if (parts.length <= 1) return { kind: "cells", cells: parts.length ? parts : [line] };
  const keyed = asKeyed(parts) ?? asLabeled(parts);
  if (!keyed) return { kind: "cells", cells: parts };
  if (keyed.keys.length === 1) return { kind: "pair", key: keyed.keys[0] ?? "", value: keyed.values[0] ?? "" };
  return { kind: "keyed", keys: keyed.keys, values: keyed.values };
}

function classify(line: string): Classified {
  const numbered = /^\d+\.\s+(.*)$/.exec(line);
  if (!numbered) return classifyRaw(line);
  const inner = classifyRaw(numbered[1] ?? "");
  if (inner.kind === "pair" || inner.kind === "keyed") return inner;
  return classifyRaw(line);
}

/** A read's lines. A sentence stays that sentence. A list or table becomes rows. */
export function shapeLines(lines: string[]): PaneBody {
  const items = lines.filter((line) => line.length > 0).map(classify);
  if (items.length === 0) return { blocks: [{ kind: "sentence", text: EMPTY_READ }] };
  if (items.every((item) => item.kind === "sentence")) {
    return { blocks: [{ kind: "sentence", text: items.map((item) => (item.kind === "sentence" ? item.text : "")).join("\n") }] };
  }

  const hasWide = items.some((item) => item.kind === "keyed" || (item.kind === "cells" && item.cells.length >= 2));
  const blocks: PaneBlock[] = [];
  let i = 0;
  while (i < items.length) {
    const item = items[i];
    if (!item) break;
    if (item.kind === "sentence") {
      const group: string[] = [];
      while (i < items.length && items[i]?.kind === "sentence") {
        const cur = items[i];
        if (cur?.kind === "sentence") group.push(cur.text);
        i += 1;
      }
      blocks.push({ kind: "sentence", text: group.join("\n") });
      continue;
    }
    if (item.kind === "pair" && hasWide) {
      const pairs: string[] = [];
      while (i < items.length && items[i]?.kind === "pair") {
        const cur = items[i];
        if (cur?.kind === "pair") pairs.push(`${cur.key}  ${cur.value}`);
        i += 1;
      }
      blocks.push({ kind: "stat", text: pairs.join("   ") });
      continue;
    }
    if (item.kind === "pair" || (item.kind === "cells" && item.cells.length === 1)) {
      const rows: string[][] = [];
      while (i < items.length) {
        const cur = items[i];
        if (cur?.kind === "pair") rows.push([cur.key, cur.value]);
        else if (cur?.kind === "cells" && cur.cells.length === 1) rows.push(cur.cells);
        else break;
        i += 1;
      }
      blocks.push({ kind: "table", columns: [], rows });
      continue;
    }
    if (item.kind === "keyed") {
      const keys = item.keys;
      const mark = keys.join("\0");
      const rows: string[][] = [];
      while (i < items.length && items[i]?.kind === "keyed") {
        const cur = items[i];
        if (cur?.kind !== "keyed" || cur.keys.join("\0") !== mark) break;
        rows.push(cur.values);
        i += 1;
      }
      blocks.push({ kind: "table", columns: keys, rows });
      continue;
    }
    const rows: string[][] = [];
    while (i < items.length && items[i]?.kind === "cells") {
      const cur = items[i];
      if (cur?.kind !== "cells" || cur.cells.length < 2) break;
      rows.push(cur.cells);
      i += 1;
    }
    if (rows.length === 0) {
      i += 1;
      continue;
    }
    blocks.push({ kind: "table", columns: [], rows });
  }
  return { blocks: blocks.length ? blocks : [{ kind: "sentence", text: EMPTY_READ }] };
}

type StrategyView =
  | { type: "text"; lines: string[] }
  | { type: "empty"; title: string; why: string | null }
  | { type: "kpis"; notice: string | null; items: { label: string; value: string }[] }
  | { type: "table"; head: string[]; rows: string[][] }
  | { type: "fields"; notice: string | null; lead: string | null; lede: string | null; rows: { label: string; value: string }[] }
  | { type: "steps"; steps: { label: string; meta: string; detail: string | null }[] }
  | { type: "track"; headline: string | null; why: string | null; rows: { label: string; value: string }[]; points: { date: string; value: string }[] }
  | { type: "sheet"; rows: { label: string; value: string }[]; chart: string | null; trades: string[][] };

/** Strategy blocks already name their rows. Text envelopes still go through the line shaper. */
export function strategyBlocks(body: StrategyView, provenance: string[] = []): PaneBody {
  if (body.type === "text") return shapeLines(body.lines);
  const blocks: PaneBlock[] = [];
  const prov = provenance.filter((line) => line.length > 0);
  if (prov.length) blocks.push({ kind: "stat", text: prov.join("   ") });
  switch (body.type) {
    case "empty":
      blocks.push({ kind: "sentence", text: body.why ? `${body.title}\n${body.why}` : body.title });
      break;
    case "kpis": {
      if (body.notice) blocks.push({ kind: "sentence", text: body.notice });
      const stat = body.items.map((item) => `${item.label}  ${item.value}`).join("   ");
      if (stat) blocks.push({ kind: "stat", text: stat });
      break;
    }
    case "table":
      blocks.push({ kind: "table", columns: body.head, rows: body.rows });
      break;
    case "fields": {
      if (body.notice) blocks.push({ kind: "sentence", text: body.notice });
      if (body.lead) blocks.push({ kind: "sentence", text: body.lead });
      if (body.lede) blocks.push({ kind: "sentence", text: body.lede });
      if (body.rows.length) {
        const short = body.rows.length <= 4 && !body.lead && !body.lede;
        if (short) blocks.push({ kind: "stat", text: body.rows.map((item) => `${item.label}  ${item.value}`).join("   ") });
        else blocks.push({ kind: "table", columns: [], rows: body.rows.map((item) => [item.label, item.value]) });
      }
      break;
    }
    case "steps":
      blocks.push({
        kind: "table",
        columns: [],
        rows: body.steps.map((step, index) =>
          step.detail ? [`${index + 1}. ${step.label}`, step.meta, step.detail] : [`${index + 1}. ${step.label}`, step.meta],
        ),
      });
      break;
    case "track": {
      if (body.headline) blocks.push({ kind: "sentence", text: body.headline });
      if (body.why) blocks.push({ kind: "sentence", text: body.why });
      if (body.rows.length) blocks.push({ kind: "table", columns: [], rows: body.rows.map((item) => [item.label, item.value]) });
      if (body.points.length) {
        blocks.push({
          kind: "table",
          columns: ["date", "value"],
          rows: body.points.map((point) => [point.date, point.value]),
        });
      }
      break;
    }
    case "sheet": {
      if (body.rows.length) {
        blocks.push({ kind: "table", columns: [], rows: body.rows.map((item) => [item.label, item.value]) });
      }
      if (body.chart) blocks.push({ kind: "chart", text: body.chart });
      if (body.trades.length) {
        blocks.push({
          kind: "table",
          columns: ["Direction", "Entry date", "Entry", "Exit date", "Exit", "Return"],
          rows: body.trades,
        });
      }
      break;
    }
    default: {
      const exhaustive: never = body;
      return { blocks: [{ kind: "sentence", text: String(exhaustive) }] };
    }
  }
  return { blocks: blocks.length ? blocks : [{ kind: "sentence", text: EMPTY_READ }] };
}
