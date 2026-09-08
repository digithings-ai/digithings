'use client';

import { useState } from 'react';

/**
 * Structured fallback for documents with a payload but no useful markdown (#1679):
 * every pipeline artifact must render readable — never a raw JSON dump. Nested
 * objects become bordered sections, arrays become lists, and scalars become a
 * key/value grid. Nested records stay structured at every depth.
 */

const INITIAL_COLLECTION_ITEMS = 20;
const COLLECTION_PAGE_SIZE = 50;
const INITIAL_DEPTH_LIMIT = 4;

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
  return <span className="whitespace-pre-wrap break-words">{String(value)}</span>;
}

function Node({ value, depth }: { value: unknown; depth: number }) {
  const [visibleCount, setVisibleCount] = useState(INITIAL_COLLECTION_ITEMS);
  const [deepBranchOpen, setDeepBranchOpen] = useState(depth < INITIAL_DEPTH_LIMIT);
  const isCollection = Array.isArray(value) || isPlainObject(value);

  if (isCollection && !deepBranchOpen) {
    const itemCount = Array.isArray(value) ? value.length : Object.keys(value).length;
    return (
      <button
        type="button"
        onClick={() => setDeepBranchOpen(true)}
        className="border border-hair px-2.5 py-1.5 font-mono text-xs text-accent transition-colors hover:border-accent/50"
      >
        Show nested details · {itemCount} {itemCount === 1 ? 'item' : 'items'}
      </button>
    );
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-ink-mute/60">—</span>;
    const visible = value.slice(0, visibleCount);
    const remaining = value.length - visible.length;
    return (
      <div>
        <ul className="list-disc space-y-1 pl-4">
          {visible.map((item, i) => (
            <li key={i}>
              <Node value={item} depth={depth + 1} />
            </li>
          ))}
        </ul>
        {remaining > 0 ? (
          <button
            type="button"
            onClick={() => setVisibleCount((count) => count + COLLECTION_PAGE_SIZE)}
            className="mt-2 border border-hair px-2.5 py-1.5 font-mono text-xs text-accent transition-colors hover:border-accent/50"
          >
            Show {Math.min(COLLECTION_PAGE_SIZE, remaining)} more · {remaining} remaining
          </button>
        ) : null}
      </div>
    );
  }
  if (isPlainObject(value)) {
    const entries = Object.entries(value).filter(([, v]) => v !== null && v !== '');
    if (entries.length === 0) return <span className="text-ink-mute/60">—</span>;
    const visible = entries.slice(0, visibleCount);
    const remaining = entries.length - visible.length;
    return (
      <div>
        <dl className="space-y-2.5">
          {visible.map(([k, v]) => (
            <div key={k} className={depth > 0 ? '' : 'border-b border-hair/60 pb-2.5'}>
              <dt className="font-mono text-[0.6rem] uppercase tracking-[0.08em] text-ink-mute">
                {labelize(k)}
              </dt>
              <dd className="mt-1 min-w-0 text-sm leading-relaxed text-ink-soft">
                <Node value={v} depth={depth + 1} />
              </dd>
            </div>
          ))}
        </dl>
        {remaining > 0 ? (
          <button
            type="button"
            onClick={() => setVisibleCount((count) => count + COLLECTION_PAGE_SIZE)}
            className="mt-3 border border-hair px-2.5 py-1.5 font-mono text-xs text-accent transition-colors hover:border-accent/50"
          >
            Show {Math.min(COLLECTION_PAGE_SIZE, remaining)} more · {remaining} remaining
          </button>
        ) : null}
      </div>
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
