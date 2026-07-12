/**
 * TradeLogTable + DirectionPill (#1463) — the tearsheet table grammar
 * promoted from the inline TradeLogTable in
 * frontend/digiquant-web/components/tearsheet/tearsheet-view.tsx, generalized
 * to ReactNode cells so consumers keep their own cell wiring (unrealized-mark
 * cells, toned figures, conviction badges …). The dress is the shared
 * `.ts-table` grammar: sticky mono thead inside a scroll clamp on screen; in
 * print the clamp opens (`max-height: none`), the head goes static, and rows
 * carry `break-inside: avoid` (styles/finance-tearsheet.css). An `open` row
 * wears `.ts-trade-open` — the accent-washed live-position state. Server
 * component — no state, no effects.
 */
import type { ReactNode } from "react";

export interface TradeLogColumn {
  label: ReactNode;
  /** Right-aligned numeric column (`.ts-num`). */
  numeric?: boolean;
}

export interface TradeLogRow {
  key: string | number;
  /** Live open position — row wears the `.ts-trade-open` state. */
  open?: boolean;
  /** One ReactNode per column, in column order. */
  cells: ReactNode[];
}

export interface TradeLogTableProps {
  columns: TradeLogColumn[];
  rows: TradeLogRow[];
  /** Extra classes on the scroll wrapper. */
  className?: string;
}

export function TradeLogTable({ columns, rows, className }: TradeLogTableProps) {
  return (
    <div className={"ts-table-wrap ts-table-scroll" + (className ? ` ${className}` : "")}>
      <table className="ts-table ts-trades">
        <thead>
          <tr>
            {columns.map((c, i) => (
              <th key={i} className={c.numeric ? "ts-num" : undefined}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className={r.open ? "ts-trade-open" : undefined}>
              {r.cells.map((cell, i) => (
                <td key={i} className={columns[i]?.numeric ? "ts-num" : undefined}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Long/short direction pill (`.ts-dir`) — long wears --up, short --down.
 *  Copy is always lowercase (long / short, not LONG). */
export function DirectionPill({ direction }: { direction: "long" | "short" }) {
  return <span className={`ts-dir ts-dir-${direction}`}>{direction}</span>;
}
