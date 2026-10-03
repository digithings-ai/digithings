import { DASH, EMPTY_READ, type ReadResult } from "../read";
import { shapeLines, type PaneBlock, type PaneBody } from "./shape";

/**
 * Strategies desk panes.
 * Index: a summary stat, the catalog table, and the deployments table.
 * Detail: overview, parameters, the track record, and runs.
 * The tearsheet pane stays on its own sheet. Deploy stays the line read.
 */

const BARS = "▁▂▃▄▅▆▇█";
const CHART_WIDTH = 24;

const NO_DEPLOYMENTS = "No deployments yet.";

const SUMMARY_FIELDS: { key: string; label: string }[] = [
  { key: "catalog", label: "catalog" },
  { key: "deployable", label: "deployable" },
  { key: "deployments", label: "deployments" },
  { key: "paper_accounts", label: "paper accounts" },
  { key: "portfolios", label: "portfolios" },
  { key: "brokers", label: "brokers" },
  { key: "plan", label: "plan" },
  { key: "last_run", label: "last run" },
];

const CATALOG_COLUMNS = ["id", "strategy", "family", "universe", "cadence", "targets", "status", "deploy"];
const DEPLOYMENT_COLUMNS = ["deployment", "strategy", "target", "status", "last run"];

const NO_PARAMETERS = "No parameters.";
const NO_RUNS = "No runs.";
const NOT_AVAILABLE = "Not available.";

const STRATEGY_IDS = ["st-kpis", "st-catalog", "st-deployments"] as const;
const DETAIL_IDS = ["st-overview", "st-parameters", "st-track-record", "st-runs"] as const;

type StrategyId = (typeof STRATEGY_IDS)[number];
type DetailId = (typeof DETAIL_IDS)[number];

const OVERVIEW_FIELDS: { key: string; label: string }[] = [
  { key: "id", label: "id" },
  { key: "name", label: "name" },
  { key: "lede", label: "lede" },
  { key: "family", label: "family" },
  { key: "universe", label: "universe" },
  { key: "cadence", label: "cadence" },
  { key: "targets", label: "targets" },
  { key: "related_thesis", label: "related thesis" },
  { key: "execution", label: "execution" },
];

const CARD_FIELDS: { key: string; label: string }[] = [
  { key: "name", label: "name" },
  { key: "symbol", label: "symbol" },
  { key: "kind", label: "kind" },
  { key: "net_profit_pct", label: "net profit %" },
  { key: "max_drawdown_pct", label: "max drawdown %" },
  { key: "profit_factor", label: "profit factor" },
  { key: "win_rate_pct", label: "win rate %" },
  { key: "total_trades", label: "trades" },
  { key: "period_start", label: "period start" },
  { key: "period_end", label: "period end" },
  { key: "vs_lump_pct", label: "vs lump %" },
  { key: "allocated_pct", label: "allocated %" },
];

function isStrategyId(id: string): id is StrategyId {
  return (STRATEGY_IDS as readonly string[]).includes(id);
}

function isDetailId(id: string): id is DetailId {
  return (DETAIL_IDS as readonly string[]).includes(id);
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
  return typeof value === "string" && value.length > 0 ? value : null;
}

function noticeLine(value: unknown): string | null {
  const note = rec(value);
  if (!note) return null;
  const tag = named(note.tag);
  const text = named(note.text);
  if (!tag && !text) return null;
  return [tag, text].filter((part): part is string => part != null).join("  ");
}

function targets(value: unknown): string {
  if (!Array.isArray(value)) return cell(value);
  const names = value.flatMap((item) => {
    const text = named(item);
    return text ? [text] : [];
  });
  return names.length > 0 ? names.join(", ") : DASH;
}

function paintSummary(data: Record<string, unknown>): PaneBody {
  const pairs: [string, string][] = [];
  for (const field of SUMMARY_FIELDS) {
    if (!(field.key in data)) continue;
    const value = cell(data[field.key]);
    if (value === DASH) continue;
    pairs.push([field.label, value]);
  }
  const head = stat(pairs);
  if (!head) return sentence(EMPTY_READ);
  const blocks: PaneBlock[] = [head];
  const note = noticeLine(data.notice);
  if (note) blocks.push({ kind: "sentence", text: note });
  return { blocks };
}

function catalogRows(value: unknown): string[][] {
  if (!Array.isArray(value)) return [];
  const rows: string[][] = [];
  for (const item of value) {
    const row = rec(item);
    const id = named(row?.id);
    if (!row || !id) continue;
    rows.push([
      id,
      cell(row.name),
      cell(row.family),
      cell(row.universe),
      cell(row.cadence),
      targets(row.targets),
      cell(row.status),
      cell(row.deploy),
    ]);
  }
  return rows;
}

function paintCatalog(data: Record<string, unknown>): PaneBody {
  const list = table(CATALOG_COLUMNS, catalogRows(data.strategies));
  return list ? { blocks: [list] } : sentence(EMPTY_READ);
}

function deploymentRows(value: unknown): string[][] {
  if (!Array.isArray(value)) return [];
  const rows: string[][] = [];
  for (const item of value) {
    const row = rec(item);
    const id = named(row?.id);
    if (!row || !id) continue;
    rows.push([id, cell(row.strategy_id), cell(row.target), cell(row.status), cell(row.last_run)]);
  }
  return rows;
}

/** The deployment store already names this empty state. */
function deploymentEmptySentence(data: unknown): string {
  const reason = named(rec(data)?.empty_reason);
  return reason ? `${NO_DEPLOYMENTS}\n${reason}` : NO_DEPLOYMENTS;
}

function paintDeployments(data: Record<string, unknown>): PaneBody {
  const list = table(DEPLOYMENT_COLUMNS, deploymentRows(data.deployments));
  return list ? { blocks: [list] } : sentence(deploymentEmptySentence(data));
}

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** Evenly spaced points from the series. Each bar is a value the payload returned. */
function sample(values: number[], width: number): number[] {
  if (values.length <= width) return values;
  const last = values.length - 1;
  const out: number[] = [];
  for (let i = 0; i < width; i += 1) {
    const value = values[Math.round((i * last) / (width - 1))];
    if (value != null) out.push(value);
  }
  return out;
}

function chart(values: number[]): PaneBlock | null {
  if (values.length < 2) return null;
  const sampled = sample(values, CHART_WIDTH);
  const lo = Math.min(...sampled);
  const hi = Math.max(...sampled);
  const span = hi - lo;
  const text = sampled
    .map((n) => {
      if (span === 0) return BARS[3] ?? BARS[0];
      const index = Math.round(((n - lo) / span) * (BARS.length - 1));
      return BARS[Math.min(BARS.length - 1, Math.max(0, index))] ?? BARS[0];
    })
    .join("");
  return text.length > 0 ? { kind: "chart", text } : null;
}

function presentPairs(
  fields: { key: string; label: string }[],
  data: Record<string, unknown>,
  read: (key: string, value: unknown) => string,
): [string, string][] {
  const pairs: [string, string][] = [];
  for (const field of fields) {
    if (!(field.key in data)) continue;
    const value = read(field.key, data[field.key]);
    if (value === DASH) continue;
    pairs.push([field.label, value]);
  }
  return pairs;
}

function overviewValue(key: string, value: unknown): string {
  return key === "targets" ? targets(value) : cell(value);
}

function paintOverview(data: Record<string, unknown>): PaneBody | null {
  if (!OVERVIEW_FIELDS.some((field) => field.key in data)) return null;
  const pairs = presentPairs(OVERVIEW_FIELDS, data, overviewValue);
  if (pairs.length === 0) return sentence(EMPTY_READ);
  if (pairs.length <= 4) {
    const head = stat(pairs);
    return head ? { blocks: [head] } : sentence(EMPTY_READ);
  }
  const list = table(["field", "value"], pairs);
  return list ? { blocks: [list] } : sentence(EMPTY_READ);
}

function objectRows(value: unknown, pick: (row: Record<string, unknown>) => string[] | null): string[][] {
  if (!Array.isArray(value)) return [];
  const rows: string[][] = [];
  for (const item of value) {
    const row = rec(item);
    if (!row) continue;
    const picked = pick(row);
    if (picked) rows.push(picked);
  }
  return rows;
}

function storeSentence(title: string, data: Record<string, unknown>): string {
  const reason = named(data.empty_reason);
  return reason ? `${title}\n${reason}` : title;
}

function paintParameters(data: Record<string, unknown>): PaneBody | null {
  if (!("parameters" in data)) return null;
  const rows = objectRows(data.parameters, (row) => {
    const name = named(row.name);
    if (!name) return null;
    return [name, cell(row.value), cell(row.state)];
  });
  const list = table(["name", "value", "state"], rows);
  return list ? { blocks: [list] } : sentence(storeSentence(NO_PARAMETERS, data));
}

function pointRows(points: unknown[]): string[][] {
  return objectRows(points, (row) => [cell(row.date), cell(row.value)]);
}

/** Numeric `value` fields, or a bare number. A null value is not replaced. */
function pointNumbers(points: unknown[]): number[] {
  const values: number[] = [];
  for (const item of points) {
    if (typeof item === "number" && Number.isFinite(item)) {
      values.push(item);
      continue;
    }
    const value = finite(rec(item)?.value);
    if (value != null) values.push(value);
  }
  return values;
}

function paintTrack(data: Record<string, unknown>): PaneBody | null {
  const hasShape = typeof data.available === "boolean" || "points" in data || "card" in data;
  if (!hasShape) return null;
  const blocks: PaneBlock[] = [];
  const card = rec(data.card);
  if (card) {
    const head = stat(presentPairs(CARD_FIELDS, card, (key, value) => (key.length > 0 ? cell(value) : DASH)));
    if (head) blocks.push(head);
  }
  const points = Array.isArray(data.points) ? data.points : [];
  const series = chart(pointNumbers(points));
  if (series) blocks.push(series);
  const list = table(["date", "value"], pointRows(points));
  if (list) blocks.push(list);
  if (!list) {
    const why = named(data.reason);
    blocks.push({ kind: "sentence", text: why ? `${NOT_AVAILABLE}\n${why}` : NOT_AVAILABLE });
  }
  return { blocks };
}

function paintRuns(data: Record<string, unknown>): PaneBody | null {
  if (!("runs" in data)) return null;
  const rows = objectRows(data.runs, (row) => {
    const run = named(row.run_date);
    if (!run) return null;
    return [run, cell(row.deployment_id), cell(row.status)];
  });
  const list = table(["run", "deployment", "status"], rows);
  return list ? { blocks: [list] } : sentence(storeSentence(NO_RUNS, data));
}

function paintDetail(id: DetailId, data: Record<string, unknown>): PaneBody | null {
  switch (id) {
    case "st-overview":
      return paintOverview(data);
    case "st-parameters":
      return paintParameters(data);
    case "st-track-record":
      return paintTrack(data);
    case "st-runs":
      return paintRuns(data);
    default: {
      const exhaustive: never = id;
      return sentence(String(exhaustive));
    }
  }
}

function detailBody(id: DetailId, data: unknown, result: ReadResult): PaneBody {
  if (data == null) return sentence(EMPTY_READ);
  const row = rec(data);
  if (!row) return textBody(result);
  const painted = paintDetail(id, row);
  if (!painted) return textBody(result);
  return withProvenance(result, painted);
}

function paint(id: StrategyId, data: Record<string, unknown>): PaneBody {
  switch (id) {
    case "st-kpis":
      return paintSummary(data);
    case "st-catalog":
      return paintCatalog(data);
    case "st-deployments":
      return paintDeployments(data);
    default: {
      const exhaustive: never = id;
      return sentence(String(exhaustive));
    }
  }
}

/** One strategies pane. A stub or a missed API stays the sentence read already returned. */
export function strategiesBody(id: string, data: unknown, result: ReadResult): PaneBody {
  if (result.status === "error" || result.status === "stub") return textBody(result);
  if (isDetailId(id)) return detailBody(id, data, result);
  if (!isStrategyId(id)) return textBody(result);
  if (id === "st-deployments") {
    const row = rec(data);
    const painted = row ? paintDeployments(row) : sentence(deploymentEmptySentence(data));
    const only = painted.blocks.length === 1 ? painted.blocks[0] : null;
    if (only?.kind === "sentence") return painted;
    return withProvenance(result, painted);
  }
  if (result.status === "empty" || data == null) return sentence(EMPTY_READ);
  const row = rec(data);
  if (!row) return textBody(result);
  return withProvenance(result, paint(id, row));
}
