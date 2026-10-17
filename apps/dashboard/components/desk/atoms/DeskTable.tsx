'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { visibleHoldingsColumns } from '@/lib/desk/column-priority';
import type { PaneState } from '@/lib/desk/types';
import { DeskState } from './DeskState';

export type DeskTableColumn = {
  id: string;
  label: string;
  kind?: 'text' | 'number' | 'weight';
};

export type DeskTableCell = string | number | null;

export type DeskTableRow = {
  id: string;
  cells: Record<string, DeskTableCell>;
};

export type DeskTableGroup = {
  id: string;
  label: string;
  rows: DeskTableRow[];
};

export interface DeskTableProps {
  columns: readonly DeskTableColumn[];
  rows?: readonly DeskTableRow[];
  groups?: readonly DeskTableGroup[];
  /** Pane width in px. When omitted, the table measures itself. */
  width?: number;
  state?: PaneState;
  errorMessage?: string;
  emptyMessage?: string;
}

function cellText(value: DeskTableCell): string {
  if (value === null || value === '') return '—';
  return String(value);
}

function WeightCell({ value }: { value: DeskTableCell }) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return <>—</>;
  }
  const width = Math.max(0, Math.min(100, value));
  return (
    <span className="inline-flex min-w-[4.5rem] items-center gap-2">
      <span className="h-1 flex-1 bg-hair">
        <span className="block h-1 bg-accent" style={{ width: `${width}%` }} />
      </span>
      <span>{value}</span>
    </span>
  );
}

function renderCell(column: DeskTableColumn, value: DeskTableCell): ReactNode {
  if (column.kind === 'weight') return <WeightCell value={value} />;
  return cellText(value);
}

export function DeskTable({
  columns,
  rows = [],
  groups = [],
  width,
  state = 'ready',
  errorMessage,
  emptyMessage = 'No rows',
}: DeskTableProps) {
  const frameRef = useRef<HTMLDivElement>(null);
  const [measured, setMeasured] = useState<number | null>(null);

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame || width !== undefined || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver((entries) => {
      const next = entries[0]?.contentRect.width;
      if (next !== undefined) setMeasured(next);
    });
    observer.observe(frame);
    return () => observer.disconnect();
  }, [width]);

  const appliedWidth = width ?? measured ?? Number.POSITIVE_INFINITY;
  const visibleIds = visibleHoldingsColumns(
    appliedWidth,
    columns.map((column) => column.id),
  );
  const visible = columns.filter((column) => visibleIds.includes(column.id));
  const flatCount = rows.length + groups.reduce((sum, group) => sum + group.rows.length, 0);
  const viewState: PaneState = state !== 'ready' ? state : flatCount === 0 ? 'empty' : 'ready';

  return (
    <div ref={frameRef} data-testid="desk-table" data-width={appliedWidth}>
      <DeskState state={viewState} errorMessage={errorMessage} emptyMessage={emptyMessage}>
        <table className="w-full border-collapse font-mono text-[11px]">
          <thead>
            <tr className="border-b border-hair text-left text-[10px] uppercase tracking-[0.12em] text-ink-mute">
              {visible.map((column) => (
                <th key={column.id} className="px-2 py-1.5 font-normal" data-column={column.id}>
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {groups.map((group) => (
              <GroupRows key={group.id} group={group} columns={visible} />
            ))}
            {rows.map((row) => (
              <DataRow key={row.id} row={row} columns={visible} />
            ))}
          </tbody>
        </table>
      </DeskState>
    </div>
  );
}

function GroupRows({
  group,
  columns,
}: {
  group: DeskTableGroup;
  columns: readonly DeskTableColumn[];
}) {
  return (
    <>
      <tr data-testid="desk-table-group">
        <th className="bg-surface px-2 py-1 text-left text-[10px] uppercase tracking-[0.12em] text-ink-soft" colSpan={columns.length} scope="colgroup">
          {group.label}
        </th>
      </tr>
      {group.rows.map((row) => (
        <DataRow key={row.id} row={row} columns={columns} />
      ))}
    </>
  );
}

function DataRow({ row, columns }: { row: DeskTableRow; columns: readonly DeskTableColumn[] }) {
  return (
    <tr className="border-b border-hair text-ink" data-testid="desk-table-row">
      {columns.map((column) => (
        <td key={column.id} className="px-2 py-1.5" data-column={column.id}>
          {renderCell(column, row.cells[column.id] ?? null)}
        </td>
      ))}
    </tr>
  );
}
