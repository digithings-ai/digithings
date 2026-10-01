import type { ReactNode } from 'react';

export type Col<R> = {
  key: string;
  label: string;
  num?: boolean;
  /** Long text: wraps within the column and clamps to 3 lines instead of widening the table. */
  wrap?: boolean;
  /** Inline weight bar under the figure, 0–100. */
  bar?: (r: R) => number | null;
  cell: (r: R) => ReactNode;
  tone?: (r: R) => 'pos' | 'neg' | undefined;
};

/** Table atom — hairline rows, mono right-aligned figures, sticky header. Row variants: grp, total. */
export function DataTable<R>({ rows, cols, rowKey, variant, empty = 'no rows' }: {
  rows: R[];
  cols: Col<R>[];
  rowKey: (r: R) => string;
  variant?: (r: R) => 'grp' | 'total' | 'sel' | undefined;
  empty?: string;
}) {
  if (!rows.length) return <p className="note mute">{empty}</p>;
  return (
    <table className="tbl">
      <thead>
        <tr>{cols.map((c) => <th key={c.key} className={c.num ? 'num' : undefined}>{c.label}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={rowKey(r)} className={variant?.(r)}>
            {cols.map((c) => {
              const w = c.bar?.(r);
              const cls = [c.num ? 'num' : '', c.wrap ? 'wrap' : '', c.tone?.(r) ?? ''].join(' ').trim() || undefined;
              return (
                <td key={c.key} className={cls}>
                  {c.wrap ? <span className="clamp">{c.cell(r)}</span> : c.cell(r)}
                  {w != null && Number.isFinite(w) ? <span className="bar"><i style={{ width: `${Math.max(0, Math.min(100, w))}%` }} /></span> : null}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
