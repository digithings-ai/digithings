"use client";

import { useDqPath } from "@/lib/hooks/use-dq-path";
import { fmtPct, fmtPrice, type BookData, type BookRow } from "@/lib/dq-paths/registry";
import { DataTable, type DataColumn } from "./data-table";
import { PathPane } from "./path-pane";

const COLUMNS: DataColumn<BookRow>[] = [
  { key: "ticker", label: "Ticker", render: (r) => r.ticker },
  { key: "w", label: "Weight", numeric: true, render: (r) => fmtPct(r.scaled_weight_pct) },
  { key: "entry", label: "Entry", numeric: true, render: (r) => fmtPrice(r.entry_price) },
  { key: "mark", label: "Mark", numeric: true, render: (r) => fmtPrice(r.current_price) },
  { key: "unr", label: "Unreal.", numeric: true, render: (r) => fmtPct(r.unrealized_pct) },
];

/** /book → GET /allocations (CONTRACT §6.2). */
export function BookTable() {
  const { data, loading, error, uiPath } = useDqPath<BookData>("book");
  return (
    <PathPane path={uiPath} as_of={data?.data.book_as_of ?? data?.as_of}>
      <DataTable
        rows={data?.data.rows ?? []}
        columns={COLUMNS}
        rowKey={(r) => r.ticker}
        loading={loading}
        error={error}
      />
    </PathPane>
  );
}
