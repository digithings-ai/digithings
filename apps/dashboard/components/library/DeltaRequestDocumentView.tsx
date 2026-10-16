'use client';

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@digithings/ui/ui';

type Op = { op?: string; path?: string; value?: unknown; reason?: string };

function previewValue(v: unknown): string {
  if (v === undefined) return '—';
  try {
    const s = JSON.stringify(v);
    return s.length > 120 ? `${s.slice(0, 117)}…` : s;
  } catch {
    return String(v);
  }
}

export default function DeltaRequestDocumentView({ payload }: { payload: Record<string, unknown> | null }) {
  if (!payload) {
    return <p className="text-ink-mute text-sm">No delta payload.</p>;
  }

  const date = String(payload.date || '');
  const baseline = String(payload.baseline_date || '—');
  const changed = Array.isArray(payload.changed_paths)
    ? (payload.changed_paths as string[]).filter((x) => typeof x === 'string')
    : [];
  const opsRaw = payload.ops;
  const ops: Op[] = Array.isArray(opsRaw) ? (opsRaw as Op[]) : [];

  return (
    <div className="space-y-6 text-sm">
      <div className="border border-hair bg-term-bg/50 p-4 space-y-1">
        <p>
          <span className="text-ink-mute">Target date:</span>{' '}
          <span className="font-mono text-ink">{date || '—'}</span>
        </p>
        <p>
          <span className="text-ink-mute">Baseline:</span>{' '}
          <span className="font-mono text-accent">{baseline}</span>
        </p>
        <p className="text-ink-mute text-xs">
          This file drives the digest compiler; structured view replaces raw JSON in the library.
        </p>
      </div>

      {changed.length > 0 ? (
        <div>
          <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-2">Changed paths</h3>
          <div className="flex flex-wrap gap-2">
            {changed.map((p) => (
              <span
                key={p}
                className="font-mono text-[11px] px-2 py-1 bg-accent/15 text-accent border border-accent/25"
              >
                {p}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {ops.length > 0 ? (
        <div>
          <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-2">Operations</h3>
          <Table className="min-w-[640px]">
            <TableHeader>
              <TableRow className="border-hair hover:bg-transparent">
                <TableHead className="text-ink-mute">Op</TableHead>
                <TableHead className="text-ink-mute">Path</TableHead>
                <TableHead className="text-ink-mute">Value (preview)</TableHead>
                <TableHead className="text-ink-mute">Reason</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ops.map((o, i) => (
                <TableRow key={i} className="border-hair/60 align-top hover:bg-transparent">
                  <TableCell className="font-mono text-accent whitespace-nowrap">{o.op ?? '—'}</TableCell>
                  <TableCell className="font-mono text-[11px] text-ink-soft break-all whitespace-normal">
                    {o.path ?? '—'}
                  </TableCell>
                  <TableCell className="font-mono text-[10px] text-ink-mute break-all whitespace-normal max-w-[240px]">
                    {previewValue(o.value)}
                  </TableCell>
                  <TableCell className="text-ink-soft whitespace-pre-wrap">{o.reason ?? '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <p className="text-ink-mute text-xs">No operations in this delta request.</p>
      )}
    </div>
  );
}
