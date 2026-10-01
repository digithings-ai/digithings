import type { ReactNode } from "react";

export type DataColumn<Row> = {
  key: string;
  label: string;
  numeric?: boolean;
  render: (row: Row) => ReactNode;
};

/** DataTable atom — dense, sticky header; loading/error/empty fail closed. */
export function DataTable<Row>({
  rows,
  columns,
  rowKey,
  loading,
  error,
}: {
  rows: Row[];
  columns: DataColumn<Row>[];
  rowKey: (row: Row) => string;
  loading?: boolean;
  error?: string | null;
}) {
  if (error) return <p role="alert" className="p-3 text-sm">{error}</p>;
  if (loading) return <p className="p-3 text-sm opacity-60">Loading…</p>;
  if (rows.length === 0) return <p className="p-3 text-sm opacity-60">No rows.</p>;
  return (
    <table className="w-full border-collapse text-xs tabular-nums">
      <thead className="sticky top-0 bg-background">
        <tr>
          {columns.map((c) => (
            <th
              key={c.key}
              scope="col"
              className={`px-3 py-1 font-mono font-normal uppercase opacity-70 ${c.numeric ? "text-right" : "text-left"}`}
            >
              {c.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={rowKey(r)} className="border-t border-white/10">
            {columns.map((c) => (
              <td key={c.key} className={`px-3 py-1 ${c.numeric ? "text-right" : ""}`}>
                {c.render(r)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
