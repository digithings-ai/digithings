import type { ReactNode } from 'react';

export type Col<R> = { key: string; label: string; num?: boolean; cell: (r: R) => ReactNode; tone?: (r: R) => 'pos' | 'neg' | undefined };

/** Table atom — hairline rows, mono right-aligned figures, sticky header. */
export function DataTable<R>({ rows, cols, rowKey }: { rows: R[]; cols: Col<R>[]; rowKey: (r: R) => string }) {
  return (
    <table className="tbl">
      <thead>
        <tr>{cols.map((c) => <th key={c.key} className={c.num ? 'num' : undefined}>{c.label}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={rowKey(r)}>
            {cols.map((c) => <td key={c.key} className={[c.num ? 'num' : '', c.tone?.(r) ?? ''].join(' ').trim() || undefined}>{c.cell(r)}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
