/**
 * Strategies, detail, and deploy.
 * Each catalog block is one official read. An empty deployment, run, or
 * target store stays empty. Deploy renders the plan and the draft; it does
 * not send an order.
 */
import { useEffect, useState } from "react";
import { BLOCKS, layoutFor, type BlockKind } from "../catalog";
import { COLS, ROWS } from "../grid";
import { DASH, EMPTY_READ, STUB_READ, presentResponse, type ReadResult } from "../read";
import { DANGER, INK, MUTE } from "../theme";
import { PaneFrame, useFocusedPane } from "./pane";
import { strategiesBody } from "./strategies-format";
import { shapeLines, strategyBlocks, type PaneBody } from "./shape";
import { strategySheetBody } from "./strategy-sheet";

const API = (process.env.DQ_API_URL ?? "http://127.0.0.1:8788").replace(/\/+$/, "");
const INDEX_PATH = "/strategies";
const STUB_MARKS = ["99.909", "204.04", "legacy_estimate"];

const STRATEGY_PATHS = new Set(["/strategies", "/strategies/detail", "/strategies/deploy"]);

type BlockId =
  | "st-kpis"
  | "st-catalog"
  | "st-deployments"
  | "st-overview"
  | "st-tearsheet"
  | "st-parameters"
  | "st-track-record"
  | "st-runs"
  | "st-targets"
  | "st-deploy-flow"
  | "st-deploy-draft";

const BLOCK_IDS: readonly BlockId[] = [
  "st-kpis",
  "st-catalog",
  "st-deployments",
  "st-overview",
  "st-tearsheet",
  "st-parameters",
  "st-track-record",
  "st-runs",
  "st-targets",
  "st-deploy-flow",
  "st-deploy-draft",
];

export type StrategyBlockBody =
  | { type: "text"; lines: string[] }
  | { type: "empty"; title: string; why: string | null }
  | { type: "kpis"; notice: string | null; items: { label: string; value: string }[] }
  | { type: "table"; head: string[]; rows: string[][] }
  | { type: "fields"; notice: string | null; lead: string | null; lede: string | null; rows: { label: string; value: string }[] }
  | { type: "steps"; steps: { label: string; meta: string; detail: string | null }[] }
  | { type: "track"; headline: string | null; why: string | null; rows: { label: string; value: string }[]; points: { date: string; value: string }[] }
  | { type: "sheet"; rows: { label: string; value: string }[]; chart: string | null; trades: string[][] };

type Loaded = { result: ReadResult; data: unknown };

const share = (cells: number, total: number): `${number}%` => `${(cells / total) * 100}%` as `${number}%`;

function isBlockId(id: string): id is BlockId {
  return (BLOCK_IDS as readonly string[]).includes(id);
}

function rec(value: unknown): Record<string, unknown> | null {
  return value != null && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function str(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function cell(value: unknown): string {
  if (value == null || value === "") return DASH;
  if (typeof value === "number") return Number.isFinite(value) ? JSON.stringify(value) : DASH;
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    if (value.length === 0) return "no rows";
    return value.map((item) => cell(item)).join(", ");
  }
  return DASH;
}

function list(data: unknown, key: string): unknown[] | null {
  const row = rec(data);
  if (!row || !(key in row)) return null;
  const value = row[key];
  return Array.isArray(value) ? value : null;
}

function noticeLine(data: unknown): string | null {
  const note = rec(rec(data)?.notice);
  if (!note) return null;
  const tag = typeof note.tag === "string" ? note.tag : "";
  const text = typeof note.text === "string" ? note.text : "";
  if (!tag && !text) return null;
  return [tag, text].filter(Boolean).join("  ");
}

function textBody(result: ReadResult): StrategyBlockBody {
  return { type: "text", lines: result.lines.length ? result.lines : [EMPTY_READ] };
}

const CARD: { key: string; label: string }[] = [
  { key: "name", label: "Name" },
  { key: "symbol", label: "Symbol" },
  { key: "kind", label: "Kind" },
  { key: "net_profit_pct", label: "Net profit %" },
  { key: "max_drawdown_pct", label: "Max drawdown %" },
  { key: "profit_factor", label: "Profit factor" },
  { key: "win_rate_pct", label: "Win rate %" },
  { key: "total_trades", label: "Trades" },
  { key: "period_start", label: "Period start" },
  { key: "period_end", label: "Period end" },
  { key: "vs_lump_pct", label: "Vs lump %" },
  { key: "allocated_pct", label: "Allocated %" },
];

function paintKpis(data: unknown): StrategyBlockBody | null {
  const row = rec(data);
  if (!row || !("catalog" in row)) return null;
  return {
    type: "kpis",
    notice: noticeLine(row),
    items: [
      { label: "Catalog", value: cell(row.catalog) },
      { label: "Deployable", value: cell(row.deployable) },
      { label: "My deployments", value: cell(row.deployments) },
      { label: "Paper accounts", value: cell(row.paper_accounts) },
      { label: "Portfolios", value: cell(row.portfolios) },
      { label: "Brokers", value: cell(row.brokers) },
      { label: "Plan", value: cell(row.plan) },
      { label: "Last run", value: cell(row.last_run) },
    ],
  };
}

function paintCatalog(data: unknown): StrategyBlockBody | null {
  const strategies = list(data, "strategies");
  if (!strategies) return null;
  if (strategies.length === 0) return { type: "empty", title: "No strategies.", why: str(rec(data)?.empty_reason) };
  const rows: string[][] = [];
  for (const item of strategies) {
    const row = rec(item);
    if (!row || typeof row.id !== "string" || row.id === "") continue;
    rows.push([
      row.id,
      cell(row.name),
      cell(row.family),
      cell(row.universe),
      cell(row.cadence),
      cell(row.targets),
      cell(row.status),
      cell(row.deploy),
    ]);
  }
  if (rows.length === 0) return { type: "empty", title: "No strategies.", why: null };
  return {
    type: "table",
    head: ["ID", "Strategy", "Family", "Universe", "Cadence", "Targets", "Status", "Deploy"],
    rows,
  };
}

function paintObjects(
  data: unknown,
  key: string,
  emptyTitle: string,
  head: string[],
  pick: (row: Record<string, unknown>) => string[] | null,
): StrategyBlockBody | null {
  const items = list(data, key);
  if (!items) return null;
  if (items.length === 0) return { type: "empty", title: emptyTitle, why: str(rec(data)?.empty_reason) };
  const rows: string[][] = [];
  for (const item of items) {
    const row = rec(item);
    if (!row) continue;
    const picked = pick(row);
    if (picked) rows.push(picked);
  }
  if (rows.length === 0) return { type: "empty", title: emptyTitle, why: str(rec(data)?.empty_reason) };
  return { type: "table", head, rows };
}

function paintDeployments(data: unknown): StrategyBlockBody | null {
  return paintObjects(
    data,
    "deployments",
    "No deployments yet.",
    ["Deployment", "Strategy", "Target", "Status", "Last run"],
    (row) => [cell(row.id), cell(row.strategy_id), cell(row.target), cell(row.status), cell(row.last_run)],
  );
}

function paintTargets(data: unknown): StrategyBlockBody | null {
  return paintObjects(data, "targets", "No targets.", ["Target", "What it is", "Status"], (row) => {
    if (typeof row.target !== "string" || !row.target) return null;
    return [row.target, cell(row.description), cell(row.status)];
  });
}

function paintRuns(data: unknown): StrategyBlockBody | null {
  return paintObjects(data, "runs", "No runs.", ["Run", "Deployment", "Status"], (row) => {
    if (typeof row.run_date !== "string" || !row.run_date) return null;
    return [row.run_date, cell(row.deployment_id), cell(row.status)];
  });
}

function paintParameters(data: unknown): StrategyBlockBody | null {
  return paintObjects(data, "parameters", "No parameters.", ["Name", "Value", "State"], (row) => {
    if (typeof row.name !== "string" || !row.name) return null;
    return [row.name, cell(row.value), cell(row.state)];
  });
}

function paintOverview(data: unknown): StrategyBlockBody | null {
  const row = rec(data);
  if (!row) return null;
  const known = ["id", "name", "lede", "family", "universe", "cadence", "targets", "related_thesis", "execution"];
  if (!known.some((key) => key in row)) return null;
  const lead = str(row.name);
  const lede = str(row.lede);
  const rows = [
    { label: "ID", value: cell(row.id) },
    { label: "Family", value: cell(row.family) },
    { label: "Universe", value: cell(row.universe) },
    { label: "Cadence", value: cell(row.cadence) },
    { label: "Targets", value: cell(row.targets) },
    { label: "Related thesis", value: cell(row.related_thesis) },
    { label: "Execution", value: cell(row.execution) },
  ];
  if (!lead && !lede && rows.every((item) => item.value === DASH)) {
    return { type: "empty", title: EMPTY_READ, why: null };
  }
  return { type: "fields", notice: null, lead, lede, rows };
}

function paintTrack(data: unknown): StrategyBlockBody | null {
  const row = rec(data);
  if (!row || typeof row.available !== "boolean") return null;
  const points: { date: string; value: string }[] = [];
  if (row.available && Array.isArray(row.points)) {
    for (const item of row.points) {
      const point = rec(item);
      if (!point || typeof point.date !== "string" || !point.date) continue;
      points.push({ date: point.date, value: cell(point.value) });
    }
  }
  const card = rec(row.card);
  const rows = card ? CARD.map((item) => ({ label: item.label, value: cell(card[item.key]) })) : [];
  const why = str(row.reason);
  if (!row.available || points.length === 0) {
    return { type: "track", headline: "Not available.", why, rows, points: [] };
  }
  return { type: "track", headline: null, why: null, rows, points };
}

function paintFlow(data: unknown): StrategyBlockBody | null {
  const steps = list(data, "steps");
  if (!steps) return null;
  const painted: { label: string; meta: string; detail: string | null }[] = [];
  for (const item of steps) {
    const step = rec(item);
    if (!step || typeof step.label !== "string" || !step.label.trim()) continue;
    const state = typeof step.state === "string" && step.state ? step.state : DASH;
    const status = typeof step.status === "string" && step.status ? step.status : null;
    painted.push({
      label: step.label,
      meta: status ? `${state}  ${status}` : state,
      detail: str(step.detail),
    });
  }
  if (painted.length === 0) return { type: "empty", title: "No deploy steps.", why: null };
  return { type: "steps", steps: painted };
}

function paintDraft(data: unknown): StrategyBlockBody | null {
  const row = rec(data);
  if (!row) return null;
  const keys = ["target_kind", "paper_capital", "broker", "portfolio", "schedule", "notice"];
  if (!keys.some((key) => key in row)) return null;
  const notice = noticeLine(row);
  const rows = [
    { label: "Target kind", value: cell(row.target_kind) },
    { label: "Paper capital", value: cell(row.paper_capital) },
    { label: "Broker", value: cell(row.broker) },
    { label: "Portfolio", value: cell(row.portfolio) },
    { label: "Schedule", value: cell(row.schedule) },
  ];
  if (!notice && rows.every((item) => item.value === DASH)) return { type: "empty", title: EMPTY_READ, why: null };
  return { type: "fields", notice, lead: null, lede: null, rows };
}

function paintStrategySheet(data: unknown): StrategyBlockBody {
  return strategySheetBody(data);
}

function paint(id: BlockId, data: unknown): StrategyBlockBody | null {
  switch (id) {
    case "st-kpis":
      return paintKpis(data);
    case "st-catalog":
      return paintCatalog(data);
    case "st-deployments":
      return paintDeployments(data);
    case "st-overview":
      return paintOverview(data);
    case "st-tearsheet":
      return paintStrategySheet(data);
    case "st-parameters":
      return paintParameters(data);
    case "st-track-record":
      return paintTrack(data);
    case "st-runs":
      return paintRuns(data);
    case "st-targets":
      return paintTargets(data);
    case "st-deploy-flow":
      return paintFlow(data);
    case "st-deploy-draft":
      return paintDraft(data);
    default: {
      const exhaustive: never = id;
      return exhaustive;
    }
  }
}

/** One block body. Stub and error envelopes stay the official lines. */
export function strategyBlockBody(id: string, data: unknown, result: ReadResult): StrategyBlockBody {
  if (id === "st-tearsheet") return paintStrategySheet(data);
  if (result.status === "error" || result.status === "stub" || data == null) return textBody(result);
  if (!isBlockId(id)) return textBody(result);
  return paint(id, data) ?? textBody(result);
}

const tone = (status: ReadResult["status"] | "loading") => {
  if (status === "ok") return INK;
  if (status === "empty" || status === "loading") return MUTE;
  return DANGER;
};

/** Same fetch as readBlock, plus the payload so an empty store can be named. */
async function loadStrategy(api: string, route: string, kind: BlockKind, signal?: AbortSignal): Promise<Loaded> {
  let res: Response;
  try {
    res = await fetch(`${api}${route}`, { signal });
  } catch {
    if (signal?.aborted) return { result: { status: "error", lines: [], asOf: null }, data: null };
    return { result: { status: "error", lines: [`${route}: the official API could not be reached.`], asOf: null }, data: null };
  }
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  const result = presentResponse(route, res.status, body, kind);
  if (result.status === "error" || result.status === "stub") return { result, data: null };
  const data = body && typeof body === "object" && "data" in body ? (body as { data: unknown }).data : null;
  return { result, data };
}

export function StrategiesPages({ path, api = API }: { path: string; api?: string }) {
  const [state, setState] = useState<{ path: string; reads: Record<string, Loaded> }>({ path: "", reads: {} });

  useEffect(() => {
    if (!STRATEGY_PATHS.has(path)) return;
    const ac = new AbortController();
    let cancel = false;
    for (const placement of layoutFor(path)) {
      const def = BLOCKS[placement.id];
      if (!def) continue;
      void loadStrategy(api, def.route, def.kind, ac.signal).then((read) => {
        if (cancel) return;
        setState((prev) => {
          const base = prev.path === path ? prev.reads : {};
          return { path, reads: { ...base, [placement.id]: read } };
        });
      });
    }
    return () => {
      cancel = true;
      ac.abort();
    };
  }, [api, path]);

  if (!STRATEGY_PATHS.has(path)) return null;
  const reads = state.path === path ? state.reads : {};
  const layout = layoutFor(path);
  if (path === INDEX_PATH) return <StrategiesIndex reads={reads} layout={layout} />;
  return <StrategiesDesk path={path} reads={reads} layout={layout} />;
}

function paintIndex(id: string, read: Loaded | undefined): { status: ReadResult["status"] | "loading"; blocks: PaneBody; asOf: string | null } {
  if (!read) return { status: "loading", blocks: shapeLines(["loading…"]), asOf: null };
  if (read.result.status === "stub" || read.result.lines.some((line) => STUB_MARKS.some((mark) => line.includes(mark)))) {
    return { status: "stub", blocks: shapeLines([STUB_READ]), asOf: null };
  }
  if (id !== "st-deployments" && read.result.lines.length === 0 && read.result.status !== "ok") {
    return { status: read.result.status, blocks: shapeLines([EMPTY_READ]), asOf: null };
  }
  return { status: read.result.status, blocks: strategiesBody(id, read.data, read.result), asOf: read.result.asOf };
}

/** Terminal strategies index. Summary, catalog, and deployments. Detail and deploy stay on their own pages. */
function StrategiesIndex({ reads, layout }: { reads: Record<string, Loaded>; layout: ReturnType<typeof layoutFor> }) {
  const [focus, setFocus] = useFocusedPane(layout.length, INDEX_PATH);
  return (
    <box width="100%" height="100%" position="relative" overflow="hidden">
      {layout.map((placement, index) => {
        const def = BLOCKS[placement.id];
        if (!def) return null;
        const read = reads[placement.id];
        const view = paintIndex(placement.id, read);
        return (
          <box
            key={`${INDEX_PATH}:${placement.id}`}
            position="absolute"
            left={share(placement.x - 1, COLS)}
            top={share(placement.y - 1, ROWS)}
            width={share(placement.w, COLS)}
            height={share(placement.h, ROWS)}
            onMouseDown={() => setFocus(index)}
          >
            <PaneFrame
              title={def.title}
              status={view.asOf ? `as of ${view.asOf}` : def.route}
              focused={index === focus}
              blocks={view.blocks}
              ink={tone(view.status)}
            />
          </box>
        );
      })}
    </box>
  );
}

function StrategiesDesk({
  path,
  reads,
  layout,
}: {
  path: string;
  reads: Record<string, Loaded>;
  layout: ReturnType<typeof layoutFor>;
}) {
  const [focus, setFocus] = useFocusedPane(layout.length, path);
  return (
    <box width="100%" height="100%" position="relative" overflow="hidden">
      {layout.map((placement, index) => {
        const def = BLOCKS[placement.id];
        if (!def) return null;
        const read = reads[placement.id];
        const status = read?.result.status ?? "loading";
        const structured = read
          ? strategyBlockBody(placement.id, read.data, read.result)
          : ({ type: "text", lines: ["loading…"] } satisfies StrategyBlockBody);
        const provenance =
          structured.type === "text"
            ? []
            : (read?.result.lines.filter((line) => line.startsWith("source  ") || line.startsWith("marks  ")) ?? []);
        return (
          <box
            key={`${path}:${placement.id}`}
            position="absolute"
            left={share(placement.x - 1, COLS)}
            top={share(placement.y - 1, ROWS)}
            width={share(placement.w, COLS)}
            height={share(placement.h, ROWS)}
            onMouseDown={() => setFocus(index)}
          >
            <PaneFrame
              title={def.title}
              status={read?.result.asOf ? `as of ${read.result.asOf}` : def.route}
              focused={index === focus}
              blocks={strategyBlocks(structured, provenance)}
              ink={tone(status)}
            />
          </box>
        );
      })}
    </box>
  );
}

export function StrategiesPage({ api }: { api?: string }) {
  return <StrategiesPages path="/strategies" api={api} />;
}

export function StrategyDetailPage({ api }: { api?: string }) {
  return <StrategiesPages path="/strategies/detail" api={api} />;
}

export function StrategyDeployPage({ api }: { api?: string }) {
  return <StrategiesPages path="/strategies/deploy" api={api} />;
}
