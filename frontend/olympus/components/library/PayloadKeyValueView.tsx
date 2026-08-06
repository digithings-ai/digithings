'use client';

/**
 * Structured fallback for documents with a payload but no useful markdown (#1679):
 * every pipeline artifact must render readable — never a raw JSON dump. Nested
 * objects become bordered sections, arrays become lists, scalars a key/value
 * grid. Depth-capped; deeper structures render as pretty-printed JSON inside a
 * scrollable block.
 */

const MAX_DEPTH = 3;

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function labelize(key: string): string {
  return key.replace(/[_-]+/g, ' ');
}

function Scalar({ value }: { value: unknown }) {
  if (value == null || value === '') return <span className="text-ink-mute/60">—</span>;
  if (typeof value === 'boolean') return <span className="font-mono">{String(value)}</span>;
  if (typeof value === 'number') return <span className="font-mono">{value}</span>;
  return <span className="whitespace-pre-wrap">{String(value)}</span>;
}

function Node({ value, depth }: { value: unknown; depth: number }) {
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-ink-mute/60">—</span>;
    return (
      <ul className="list-disc space-y-1 pl-4">
        {value.map((item, i) => (
          <li key={i}>
            <Node value={item} depth={depth + 1} />
          </li>
        ))}
      </ul>
    );
  }
  if (isPlainObject(value)) {
    if (depth >= MAX_DEPTH) {
      return (
        <pre className="max-h-64 overflow-auto rounded-lg border border-hair bg-term-bg/40 p-3 font-mono text-[11px] leading-relaxed">
          {JSON.stringify(value, null, 2)}
        </pre>
      );
    }
    const entries = Object.entries(value).filter(([, v]) => v !== null && v !== '');
    if (entries.length === 0) return <span className="text-ink-mute/60">—</span>;
    return (
      <dl className="space-y-2.5">
        {entries.map(([k, v]) => (
          <div key={k} className={depth > 0 ? '' : 'border-b border-hair/60 pb-2.5'}>
            <dt className="font-mono text-[0.6rem] uppercase tracking-[0.08em] text-ink-mute">
              {labelize(k)}
            </dt>
            <dd className="mt-1 text-sm leading-relaxed text-ink-soft">
              <Node value={v} depth={depth + 1} />
            </dd>
          </div>
        ))}
      </dl>
    );
  }
  return <Scalar value={value} />;
}

export default function PayloadKeyValueView({ payload }: { payload: Record<string, unknown> }) {
  return (
    <div className="text-sm">
      <Node value={payload} depth={0} />
    </div>
  );
}
