import { DASH, EMPTY_READ, type ReadResult } from "../read";
import { shapeLines, type PaneBlock, type PaneBody } from "./shape";

/** Strategies index. A summary stat, the catalog table, and the deployments table. */

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

const STRATEGY_IDS = ["st-kpis", "st-catalog", "st-deployments"] as const;

type StrategyId = (typeof STRATEGY_IDS)[number];

function isStrategyId(id: string): id is StrategyId {
  return (STRATEGY_IDS as readonly string[]).includes(id);
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

/** One strategies-index pane. A stub or a missed API stays the sentence read already returned. */
export function strategiesBody(id: string, data: unknown, result: ReadResult): PaneBody {
  if (result.status === "error" || result.status === "stub") return textBody(result);
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
