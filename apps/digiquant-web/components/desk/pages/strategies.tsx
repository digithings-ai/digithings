"use client";

/**
 * Strategies, detail, and deploy.
 * Each catalog block is one official read. An empty deployment, run, or
 * target store stays empty. Deploy renders the plan and the draft; it does
 * not send an order.
 */
import { useEffect, useState } from "react";
import { BLOCKS, layoutFor } from "../../../../../clients/digiquant-tui/src/catalog";
import { DASH, EMPTY_READ, STUB_READ, type ReadResult } from "../../../../../clients/digiquant-tui/src/read";
import { strategiesBody } from "../../../../../clients/digiquant-tui/src/pages/strategies-format";
import { shapeLines, strategyBlocks, type PaneBody } from "../../../../../clients/digiquant-tui/src/pages/shape";
import { readOfficial, type OfficialRead } from "../read-block";
import { DeskPane, PANE_GRID, usePaneFocus } from "./pane";

const STRATEGY_PATHS = new Set(["/strategies", "/strategies/detail", "/strategies/deploy"]);
const INDEX_PATH = "/strategies";
const STUB_MARKS = ["99.909", "204.04", "legacy_estimate"];

type BlockId =
  | "st-kpis"
  | "st-catalog"
  | "st-deployments"
  | "st-overview"
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
  | { type: "track"; headline: string | null; why: string | null; rows: { label: string; value: string }[]; points: { date: string; value: string }[] };

const tone: Record<ReadResult["status"] | "loading", string> = {
  ok: "text-ink",
  empty: "text-ink-mute",
  loading: "text-ink-mute",
  stub: "text-ink-soft",
  error: "text-ink-soft",
};

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
  if (result.status === "error" || result.status === "stub" || data == null) return textBody(result);
  if (!isBlockId(id)) return textBody(result);
  return paint(id, data) ?? textBody(result);
}


export function StrategiesPages({ path }: { path: string }) {
  const [state, setState] = useState<{ path: string; reads: Record<string, OfficialRead> }>({ path: "", reads: {} });

  useEffect(() => {
    if (!STRATEGY_PATHS.has(path)) return;
    const ac = new AbortController();
    let cancel = false;
    for (const placement of layoutFor(path)) {
      const def = BLOCKS[placement.id];
      if (!def) continue;
      void readOfficial(def.route, def.kind, ac.signal).then((read) => {
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
  }, [path]);

  if (!STRATEGY_PATHS.has(path)) return null;
  const reads = state.path === path ? state.reads : {};
  const layout = layoutFor(path);
  if (path === INDEX_PATH) return <StrategiesIndex reads={reads} layout={layout} />;
  return <StrategiesDesk path={path} reads={reads} layout={layout} />;
}

function paintIndex(id: string, read: OfficialRead | undefined): { status: ReadResult["status"] | "loading"; blocks: PaneBody; asOf: string | null } {
  if (!read) return { status: "loading", blocks: shapeLines(["loading…"]), asOf: null };
  if (read.result.status === "stub" || read.result.lines.some((line) => STUB_MARKS.some((mark) => line.includes(mark)))) {
    return { status: "stub", blocks: shapeLines([STUB_READ]), asOf: null };
  }
  if (id !== "st-deployments" && read.result.lines.length === 0 && read.result.status !== "ok") {
    return { status: read.result.status, blocks: shapeLines([EMPTY_READ]), asOf: null };
  }
  return { status: read.result.status, blocks: strategiesBody(id, read.data, read.result), asOf: read.result.asOf };
}

/** Desk strategies index. Same blocks as the terminal. Detail and deploy stay on their own pages. */
function StrategiesIndex({ reads, layout }: { reads: Record<string, OfficialRead>; layout: ReturnType<typeof layoutFor> }) {
  const panes = usePaneFocus(layout.map((placement) => placement.id));
  return (
    <div className={PANE_GRID}>
      {layout.map((placement) => {
        const def = BLOCKS[placement.id];
        if (!def) return null;
        const read = reads[placement.id];
        const view = paintIndex(placement.id, read);
        return (
          <div
            key={`${INDEX_PATH}:${placement.id}`}
            className="min-h-0 min-w-0"
            style={{ gridColumn: `${placement.x} / span ${placement.w}`, gridRow: `${placement.y} / span ${placement.h}` }}
          >
            <DeskPane
              title={def.title}
              route={def.route}
              asOf={view.asOf}
              blocks={view.blocks}
              tone={tone[view.status]}
              focused={panes.focus === placement.id}
              onFocus={() => panes.focusAt(placement.id)}
              onNext={panes.next}
            />
          </div>
        );
      })}
    </div>
  );
}

function StrategiesDesk({
  path,
  reads,
  layout,
}: {
  path: string;
  reads: Record<string, OfficialRead>;
  layout: ReturnType<typeof layoutFor>;
}) {
  const panes = usePaneFocus(layout.map((placement) => placement.id));
  return (
    <div className={PANE_GRID}>
      {layout.map((placement) => {
        const def = BLOCKS[placement.id];
        if (!def) return null;
        const read = reads[placement.id];
        const status = read?.result.status ?? "loading";
        const body = read
          ? strategyBlockBody(placement.id, read.data, read.result)
          : ({ type: "text", lines: ["loading…"] } satisfies StrategyBlockBody);
        const provenance =
          body.type === "text"
            ? []
            : (read?.result.lines.filter((line) => line.startsWith("source  ") || line.startsWith("marks  ")) ?? []);
        return (
          <div
            key={`${path}:${placement.id}`}
            className="min-h-0 min-w-0"
            style={{ gridColumn: `${placement.x} / span ${placement.w}`, gridRow: `${placement.y} / span ${placement.h}` }}
          >
            <DeskPane
              title={def.title}
              route={def.route}
              asOf={read?.result.asOf ?? null}
              blocks={strategyBlocks(body, provenance)}
              tone={tone[status]}
              focused={panes.focus === placement.id}
              onFocus={() => panes.focusAt(placement.id)}
              onNext={panes.next}
            />
          </div>
        );
      })}
    </div>
  );
}

export function StrategiesPage() {
  return <StrategiesPages path="/strategies" />;
}

export function StrategyDetailPage() {
  return <StrategiesPages path="/strategies/detail" />;
}

export function StrategyDeployPage() {
  return <StrategiesPages path="/strategies/deploy" />;
}
