"use client";

import { DASH, cell } from "digiquant-tui/format";
import type { ReadResult } from "digiquant-tui/read";
import {
  BlockBoundary,
  DataTable,
  KpiGrid,
  Sparkline,
  StateBlock,
  type DataTableColumn,
  type DataTableTone,
  type KpiCell,
} from "@digithings/ui";

const ROUTE = "/nav-series";

/** One figure the payload did not carry, plus the reason it is missing. */
const ABSENT = "not in payload";
const NO_SERIES = "the payload's points list is empty";

export type NavSeriesBlockProps = {
  /** The desk read for `/nav-series`. `undefined` while the first fetch is in flight. */
  read?: ReadResult;
  /** The envelope's `data`, when the read is ok and carried one. */
  data?: unknown;
};

type NavRow = {
  date: string;
  index: string;
  day: string;
  contract: string;
  /** The raw index level, for the sparkline and the tone. */
  level: number | null;
  /** The raw day return, for the tone. */
  move: number | null;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function tone(value: number | null): DataTableTone | undefined {
  if (value === null || value === 0) return undefined;
  return value > 0 ? "pos" : "neg";
}

/** One row per point the payload returned. A null or absent level stays `—`, never a zero. */
function navRows(points: unknown[]): NavRow[] {
  const rows: NavRow[] = [];
  for (const raw of points) {
    if (!isRecord(raw)) continue;
    const level = finite(raw.index);
    const move = finite(raw.day_return_pct);
    rows.push({
      date: text(raw.date) ?? DASH,
      index: level === null ? DASH : cell(level, "index"),
      day: cell(raw.day_return_pct, "day_return_pct"),
      contract: text(raw.contract) ?? DASH,
      level,
      move,
    });
  }
  return rows;
}

const COLS: DataTableColumn<NavRow>[] = [
  { key: "date", label: "date", role: "key", cell: (row) => row.date },
  { key: "index", label: "index", num: true, cell: (row) => row.index },
  { key: "day", label: "day", num: true, cell: (row) => row.day, tone: (row) => tone(row.move) },
  { key: "contract", label: "contract", cell: (row) => row.contract },
];

/** The continuity index is the only series a chart may plot; the accounting NAV is labelled, not drawn. */
function accountingKpi(plot: Record<string, unknown> | null): KpiCell {
  const nav = plot && isRecord(plot.accounting_nav) ? plot.accounting_nav : null;
  const contract = text(nav?.contract);
  const plottable = typeof nav?.plottable === "boolean" ? nav.plottable : null;
  const why = text(nav?.reason);
  const note =
    contract === null
      ? ABSENT
      : plottable === null
        ? "plottable state not in payload"
        : plottable
          ? "plottable"
          : `not plottable${why ? ` · ${why}` : ""}`;
  return { label: "Accounting NAV", value: contract, note };
}

/**
 * The `/nav-series` payload as a real block: the tip summary on hairlines, the
 * index as a sparkline when the read carries two or more levels, and the points
 * as a table.
 *
 * The contract draws the continuity `index` and never `points[].nav` (§6.6), so
 * this block plots and tabulates the index alone and states the accounting NAV's
 * contract beside it. A point the payload did not carry is `—`, never a zero.
 */
function NavSeriesBody({ read, data }: NavSeriesBlockProps) {
  if (!read) {
    return <StateBlock kind="loading" title="NAV series" reason={`reading ${ROUTE}`} />;
  }
  if (read.status === "error") {
    return (
      <StateBlock
        kind="error"
        title="NAV series could not be read."
        reason={read.lines.join(" ") || `${ROUTE} failed without a message.`}
      />
    );
  }
  if (read.status === "stub") {
    return <StateBlock kind="withheld" title="NAV series withheld." reason={read.lines.join(" ")} />;
  }
  if (read.status === "empty") {
    return <StateBlock kind="empty" title="No NAV series in this read." reason={read.lines.join(" ")} />;
  }
  if (!isRecord(data)) {
    return (
      <StateBlock
        kind="withheld"
        title="NAV series withheld."
        reason={`${ROUTE} returned ${data === null ? "no data object" : `a ${Array.isArray(data) ? "list" : typeof data}, not an object`}.`}
      />
    );
  }

  const points = Array.isArray(data.points) ? data.points : null;
  if (!points || points.length === 0) {
    return (
      <StateBlock
        kind="empty"
        title="No NAV series in this read."
        reason={points === null ? `points ${ABSENT}.` : NO_SERIES}
      />
    );
  }

  const rows = navRows(points);
  if (rows.length === 0) {
    return (
      <StateBlock
        kind="withheld"
        title="NAV series withheld."
        reason={`${ROUTE} returned ${points.length} points, none of them a date and a level.`}
      />
    );
  }

  const tip = isRecord(data.tip) ? data.tip : null;
  const plot = isRecord(data.plot) ? data.plot : null;
  const levels = rows.map((row) => row.level).filter((level): level is number => level !== null);
  const last = rows.reduce<NavRow | null>((seen, row) => (row.level !== null ? row : seen), null);
  const tipDate = text(tip?.date);
  const gaps = rows.filter((row) => row.level === null).length;
  const lastMove = last ? last.move : null;

  const items: KpiCell[] = [
    { label: "Tip", value: tipDate ?? last?.date ?? null, note: tipDate || last ? undefined : ABSENT },
    {
      label: "Points",
      value: rows.length,
      note: `${levels.length} ${levels.length === 1 ? "level" : "levels"}`,
    },
    { label: "Index", value: last?.index ?? null, note: last ? "base 100" : ABSENT },
    {
      label: "Day",
      value: lastMove === null ? null : last?.day,
      note: lastMove === null ? "no day return for the last level" : undefined,
      tone: tone(lastMove),
    },
    accountingKpi(plot),
  ];

  return (
    <div className="flex flex-col gap-2">
      <KpiGrid items={items} missing="—" />
      {levels.length >= 2 ? (
        <div className="border-x border-b border-hair px-3 py-2">
          <Sparkline
            values={levels}
            height={56}
            label={`NAV index over ${levels.length} points`}
          />
        </div>
      ) : null}
      <DataTable
        rows={rows}
        cols={COLS}
        rowKey={(row, index) => `${row.date}-${index}`}
        label="NAV series"
        empty="no points"
      />
      {gaps > 0 ? (
        <p className="m-0 font-mono text-[0.72rem] text-ink-mute">{`${DASH} · index ${ABSENT} on ${gaps} ${gaps === 1 ? "point" : "points"}`}</p>
      ) : null}
    </div>
  );
}

/** One block throwing on an odd payload must not take the desk down. */
export function NavSeriesBlock({ read, data }: NavSeriesBlockProps) {
  return (
    <BlockBoundary label={ROUTE}>
      <NavSeriesBody read={read} data={data} />
    </BlockBoundary>
  );
}
