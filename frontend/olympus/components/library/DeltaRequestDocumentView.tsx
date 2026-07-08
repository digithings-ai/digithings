'use client';

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
      <div className="rounded-lg border border-hair bg-term-bg/50 p-4 space-y-1">
        <p>
          <span className="text-ink-mute">Target date:</span>{' '}
          <span className="font-mono text-white">{date || '—'}</span>
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
                className="font-mono text-[11px] px-2 py-1 rounded-md bg-accent/15 text-accent border border-accent/25"
              >
                {p}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {ops.length > 0 ? (
        <div className="overflow-x-auto">
          <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-2">Operations</h3>
          <table className="w-full text-left text-xs border-collapse min-w-[640px]">
            <thead>
              <tr className="border-b border-hair text-ink-mute">
                <th className="py-2 pr-2 font-medium">Op</th>
                <th className="py-2 pr-2 font-medium">Path</th>
                <th className="py-2 pr-2 font-medium">Value (preview)</th>
                <th className="py-2 font-medium">Reason</th>
              </tr>
            </thead>
            <tbody>
              {ops.map((o, i) => (
                <tr key={i} className="border-b border-hair/60 align-top">
                  <td className="py-2 pr-2 font-mono text-accent whitespace-nowrap">{o.op ?? '—'}</td>
                  <td className="py-2 pr-2 font-mono text-[11px] text-ink-soft break-all">{o.path ?? '—'}</td>
                  <td className="py-2 pr-2 font-mono text-[10px] text-ink-mute break-all max-w-[240px]">
                    {previewValue(o.value)}
                  </td>
                  <td className="py-2 text-ink-soft whitespace-pre-wrap">{o.reason ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-ink-mute text-xs">No operations in this delta request.</p>
      )}
    </div>
  );
}
