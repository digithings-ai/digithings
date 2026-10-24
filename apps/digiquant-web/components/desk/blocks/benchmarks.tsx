"use client";

import { DASH, cell } from "digiquant-tui/format";
import type { ReadResult } from "digiquant-tui/read";
import { isRecord } from "@digithings/ui/lib/record";
import {
  BlockBoundary,
  DataTable,
  KpiGrid,
  StateBlock,
  type DataTableColumn,
  type KpiCell,
} from "@digithings/ui";

const ROUTE = "/benchmarks";

const ABSENT = "not in payload";
/** `reason: null` is the API saying the overlap is healthy, not a missing field. */
const HEALTHY = "healthy";

export type BenchmarksBlockProps = {
  /** The desk read for `/benchmarks`. `undefined` while the first fetch is in flight. */
  read?: ReadResult;
  /** The envelope's `data`, when the read is ok and carried one. */
  data?: unknown;
};

type BenchRow = { ticker: string; date: string; close: string; gap: boolean };

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/** One row per close the payload carried, in the order it returned them. */
function benchRows(series: unknown): BenchRow[] {
  if (!isRecord(series)) return [];
  const rows: BenchRow[] = [];
  for (const [ticker, value] of Object.entries(series)) {
    if (!ticker || !Array.isArray(value)) continue;
    for (const raw of value) {
      if (!isRecord(raw)) continue;
      const date = text(raw.date);
      if (!date) continue;
      const gap = !(typeof raw.close === "number" && Number.isFinite(raw.close));
      rows.push({ ticker, date, close: cell(raw.close, "close"), gap });
    }
  }
  return rows;
}

const COLS: DataTableColumn<BenchRow>[] = [
  { key: "ticker", label: "ticker", role: "key", cell: (row) => row.ticker },
  { key: "date", label: "date", num: true, cell: (row) => row.date },
  { key: "close", label: "close", num: true, cell: (row) => row.close },
];

function tickersOf(universe: unknown, rows: BenchRow[]): string[] {
  if (Array.isArray(universe)) {
    const named = universe.filter((name): name is string => typeof name === "string" && name.trim().length > 0);
    if (named.length > 0) return named;
  }
  return [...new Set(rows.map((row) => row.ticker))];
}

/** Four names fit a cell; the rest stay in the table. */
function namesNote(names: string[]): string | undefined {
  if (names.length === 0) return ABSENT;
  const head = names.slice(0, 4).join(" ");
  return names.length > 4 ? `${head} …` : head;
}

/**
 * The `/benchmarks` payload as a real block: the overlap summary on hairlines and
 * the aligned closes as a table, one row per ticker and date the API returned.
 *
 * A null close is `—`, never a zero. An empty series carries the API's own
 * `reason` token rather than a relabelled cause (§6.7).
 */
function BenchmarksBody({ read, data }: BenchmarksBlockProps) {
  if (!read) {
    return <StateBlock kind="loading" title="Benchmarks" reason={`reading ${ROUTE}`} />;
  }
  if (read.status === "error") {
    return (
      <StateBlock
        kind="error"
        title="Benchmarks could not be read."
        reason={read.lines.join(" ") || `${ROUTE} failed without a message.`}
      />
    );
  }
  if (read.status === "stub") {
    return <StateBlock kind="withheld" title="Benchmarks withheld." reason={read.lines.join(" ")} />;
  }
  if (read.status === "empty") {
    return <StateBlock kind="empty" title="No benchmarks in this read." reason={read.lines.join(" ")} />;
  }
  if (!isRecord(data)) {
    return (
      <StateBlock
        kind="withheld"
        title="Benchmarks withheld."
        reason={`${ROUTE} returned ${data === null ? "no data object" : `a ${Array.isArray(data) ? "list" : typeof data}, not an object`}.`}
      />
    );
  }

  const reason = text(data.reason);
  const alignedStart = text(data.aligned_start);
  const rows = benchRows(data.series);

  if (rows.length === 0) {
    const why = "reason" in data
      ? reason ?? HEALTHY
      : `series ${ABSENT}`;
    return (
      <StateBlock
        kind="empty"
        title="No aligned benchmark closes in this read."
        reason={`${ROUTE} · ${why}`}
      />
    );
  }

  const names = tickersOf(data.universe, rows);
  const gaps = rows.filter((row) => row.gap).length;
  const overlap = cell(data.overlap_days, "overlap_days");
  const items: KpiCell[] = [
    { label: "Tickers", value: names.length, note: namesNote(names) },
    { label: "Rows", value: rows.length, note: `${new Set(rows.map((row) => row.ticker)).size} with closes` },
    { label: "Overlap", value: data.overlap_days == null ? null : overlap, note: data.overlap_days == null ? ABSENT : "days" },
    { label: "Aligned from", value: alignedStart, note: alignedStart ? undefined : ABSENT },
    {
      label: "Reason",
      value: "reason" in data ? reason ?? HEALTHY : null,
      note: "reason" in data ? (reason ? "series withheld by the API" : undefined) : ABSENT,
    },
  ];

  return (
    <div className="flex flex-col gap-2">
      <KpiGrid items={items} missing="—" />
      <DataTable
        rows={rows}
        cols={COLS}
        rowKey={(row, index) => `${row.ticker}-${row.date}-${index}`}
        label="Benchmarks"
        empty="no closes"
      />
      {gaps > 0 ? (
        <p className="m-0 font-mono text-[0.72rem] text-ink-mute">{`${DASH} · close ${ABSENT} on ${gaps} ${gaps === 1 ? "row" : "rows"}`}</p>
      ) : null}
    </div>
  );
}

/** One block throwing on an odd payload must not take the desk down. */
export function BenchmarksBlock({ read, data }: BenchmarksBlockProps) {
  return (
    <BlockBoundary label={ROUTE}>
      <BenchmarksBody read={read} data={data} />
    </BlockBoundary>
  );
}
