"use client";

import { useMemo } from "react";
import { SegToggle } from "./charts";
import { fmtNum, fmtPct, toneClass } from "./format";
import { fmtRatio } from "./stats";
import {
  PIVOT_LABELS,
  buildStatSlices,
  computeSliceMetrics,
  type SliceMetrics,
  type StatsPivot,
} from "./pivot-stats";
import type { TearsheetData } from "./types";

function Toned({ v, children }: { v: number | null | undefined; children: React.ReactNode }) {
  const c = toneClass(v);
  return c ? <span className={c}>{children}</span> : <>{children}</>;
}

function pctCell(v: number | null): React.ReactNode {
  if (v === null) return "—";
  return <Toned v={v}>{fmtPct(v)}</Toned>;
}

type MetricDef = {
  key: string;
  label: string;
  cell: (m: SliceMetrics) => React.ReactNode;
};

const METRIC_ROWS: MetricDef[] = [
  { key: "return", label: "Total return", cell: (m) => pctCell(m.returnPct) },
  { key: "cagr", label: "Avg annual return", cell: (m) => pctCell(m.cagrPct) },
  {
    key: "maxdd",
    label: "Max drawdown",
    cell: (m) =>
      m.maxDrawdownPct !== null ? (
        <span className="is-neg">{fmtPct(m.maxDrawdownPct)}</span>
      ) : (
        "—"
      ),
  },
  { key: "sharpe", label: "Sharpe ratio", cell: (m) => fmtRatio(m.sharpe) },
  { key: "sortino", label: "Sortino ratio", cell: (m) => fmtRatio(m.sortino) },
  { key: "calmar", label: "Calmar ratio", cell: (m) => fmtRatio(m.calmar) },
  { key: "omega", label: "Omega ratio", cell: (m) => fmtRatio(m.omega) },
  {
    key: "vol",
    label: "Annualized volatility",
    cell: (m) => (m.volatilityPct !== null ? fmtPct(m.volatilityPct) : "—"),
  },
  { key: "recovery", label: "Recovery factor", cell: (m) => fmtRatio(m.recovery) },
  { key: "alpha", label: "Alpha vs buy-and-hold", cell: (m) => pctCell(m.alphaPct) },
  { key: "trades", label: "Trades", cell: (m) => fmtNum(m.trades) },
  { key: "winrate", label: "Win rate", cell: (m) => (m.winRatePct !== null ? fmtPct(m.winRatePct) : "—") },
  {
    key: "pf",
    label: "Profit factor",
    cell: (m) => (m.profitFactor !== null ? fmtNum(m.profitFactor, 2) : "—"),
  },
  { key: "avgtrade", label: "Avg trade %", cell: (m) => pctCell(m.avgTradePct) },
  { key: "avgwin", label: "Avg winner %", cell: (m) => pctCell(m.avgWinPct) },
  { key: "avgloss", label: "Avg loser %", cell: (m) => pctCell(m.avgLossPct) },
  { key: "best", label: "Best trade %", cell: (m) => pctCell(m.bestPct) },
  { key: "worst", label: "Worst trade %", cell: (m) => pctCell(m.worstPct) },
];

const PREVIEW_METRIC_KEYS = new Set([
  "return",
  "maxdd",
  "sharpe",
  "winrate",
  "pf",
  "trades",
]);

const PIVOT_OPTIONS: { value: StatsPivot; label: string }[] = [
  { value: "direction", label: PIVOT_LABELS.direction },
  { value: "year", label: PIVOT_LABELS.year },
];

const PRINT_PIVOTS: StatsPivot[] = ["direction", "year"];

export function PivotStatsPivotToggle({
  value,
  onChange,
}: {
  value: StatsPivot;
  onChange: (pivot: StatsPivot) => void;
}) {
  return (
    <SegToggle
      className="ts-pivot-seg"
      label="Pivot by"
      value={value}
      onChange={onChange}
      options={PIVOT_OPTIONS}
    />
  );
}

export function PivotStatsTable({
  data,
  printing = false,
  pivot = "direction",
  compact = false,
}: {
  data: TearsheetData;
  printing?: boolean;
  pivot?: StatsPivot;
  /** Homepage preview card — fewer rows, no scroll. */
  compact?: boolean;
}) {
  if (printing) {
    return (
      <div className="ts-pivot-stats ts-pivot-stats-print">
        {PRINT_PIVOTS.map((p) => (
          <section key={p} className="ts-pivot-print-block">
            <h3 className="ts-pivot-print-title">By {PIVOT_LABELS[p].toLowerCase()}</h3>
            <PivotStatsGrid data={data} pivot={p} />
          </section>
        ))}
      </div>
    );
  }

  return (
    <div className={"ts-pivot-stats" + (compact ? " ts-pivot-stats-compact" : "")}>
      <PivotStatsGrid data={data} pivot={pivot} compact={compact} />
    </div>
  );
}

function PivotStatsGrid({
  data,
  pivot,
  compact = false,
}: {
  data: TearsheetData;
  pivot: StatsPivot;
  compact?: boolean;
}) {
  const slices = useMemo(() => buildStatSlices(data, pivot), [data, pivot]);
  const columns = useMemo(
    () =>
      slices
        .filter((slice) => !compact || slice.id !== "all")
        .map((slice) => ({
          slice,
          metrics: computeSliceMetrics(slice, data),
        })),
    [compact, slices, data],
  );

  const metricRows = compact
    ? METRIC_ROWS.filter((row) => PREVIEW_METRIC_KEYS.has(row.key))
    : METRIC_ROWS;

  if (columns.length === 0) {
    return <p className="ts-status">No statistics available.</p>;
  }

  return (
    <div
      className={
        "ts-table-wrap ts-pivot-wrap" + (compact ? " ts-pivot-wrap-compact" : " ts-table-scroll")
      }
    >
      <table className={"ts-table ts-pivot-table" + (compact ? " ts-pivot-table-compact" : "")}>
        <thead>
          <tr>
            <th scope="col" className="ts-pivot-metric-col">
              Metric
            </th>
            {columns.map(({ slice }) => (
              <th
                key={slice.id}
                scope="col"
                className="ts-num ts-pivot-col"
                aria-label={slice.id === "full" ? "Full period" : undefined}
              >
                {slice.id === "full" ? "" : slice.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metricRows.map((row) => (
            <tr key={row.key}>
              <th scope="row" className="ts-pivot-metric-col">
                {row.label}
              </th>
              {columns.map(({ slice, metrics }) => (
                <td key={slice.id} className="ts-num ts-pivot-col">
                  {row.cell(metrics)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
