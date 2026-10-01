'use client';

import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent as RKeyEvent, type PointerEvent as RPointerEvent } from 'react';
import { COLS, ROWS, clampSize, parse, place, slot, swap, type Layout, type Placement } from '@/lib/grid';
import { BLOCKS } from './blocks';
import { useAccess } from './Access';
import { StateBlock } from './ui';
import { Window } from './Window';

const key = (pageId: string) => `dq-layout:${pageId}`;
const byId = new Map(BLOCKS.map((b) => [b.id, b]));
const KNOWN = new Set(byId.keys());

type Drag = { id: string; mode: 'move' | 'size'; sx: number; sy: number; start: Layout; from: Placement };

/**
 * Places registry blocks on a COLS×ROWS grid that fills its container.
 * `e` toggles layout editing: drag a block to move, its corner to resize,
 * arrows move and shift+arrows resize the focused block. Saved per page.
 */
export function BlockGrid({ pageId, initial }: { pageId: string; initial: Layout }) {
  const { block } = useAccess();
  const [layout, setLayout] = useState<Layout>(initial);
  const [edit, setEdit] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const drag = useRef<Drag | null>(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(key(pageId));
      if (raw) setLayout(parse(JSON.parse(raw), KNOWN, initial));
    } catch { /* storage unavailable or corrupt: keep defaults */ }
  }, [pageId, initial]);

  const save = useCallback((l: Layout) => {
    try { localStorage.setItem(key(pageId), JSON.stringify(l)); } catch { /* storage unavailable */ }
  }, [pageId]);

  const commit = useCallback((l: Layout) => { setLayout(l); save(l); }, [save]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement) return;
      if (t instanceof HTMLSelectElement || t?.isContentEditable || document.querySelector('[role="dialog"]')) return;
      if (e.key === 'e' && !e.metaKey && !e.ctrlKey && !e.altKey) {
        drag.current = null;
        setEdit((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const begin = (e: RPointerEvent<HTMLElement>, p: Placement, mode: Drag['mode']) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { id: p.id, mode, sx: e.clientX, sy: e.clientY, start: layout, from: p };
  };
  const move = (e: RPointerEvent<HTMLElement>) => {
    const d = drag.current, box = ref.current?.getBoundingClientRect();
    if (!d || !box) return;
    if (e.buttons === 0) { end(); return; }
    const dx = Math.round((e.clientX - d.sx) / (box.width / COLS));
    const dy = Math.round((e.clientY - d.sy) / (box.height / ROWS));
    const next = d.mode === 'move'
      ? { ...d.from, x: d.from.x + dx, y: d.from.y + dy }
      : clampSize({ ...d.from, w: d.from.w + dx, h: d.from.h + dy });
    const l = place(d.start, next) ?? (d.mode === 'move' ? swap(d.start, next) : null);
    if (l) setLayout(l);
  };
  const end = () => {
    if (!drag.current) return;
    drag.current = null;
    setLayout((l) => { save(l); return l; });
  };

  const onKeyCell = (e: RKeyEvent<HTMLElement>, p: Placement) => {
    const step: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); commit(layout.filter((q) => q.id !== p.id)); return; }
    const s = step[e.key];
    if (!s) return;
    e.preventDefault();
    const n = e.shiftKey ? clampSize({ ...p, w: p.w + s[0], h: p.h + s[1] }) : { ...p, x: p.x + s[0], y: p.y + s[1] };
    const l = place(layout, n) ?? (e.shiftKey ? null : swap(layout, n));
    if (l) commit(l);
  };

  const unplaced = useMemo(() => BLOCKS.filter((b) => !layout.some((p) => p.id === b.id)), [layout]);

  return (
    <div className="bg">
      <div className="bg-bar">
        {edit ? (
          <>
            <span className="mute">layout · drag to move, corner to resize, arrows / shift+arrows, Del removes</span>
            <span className="bg-acts">
              {unplaced.map((b) => {
                const free = slot(layout, b.id);
                return (
                  <button key={b.id} type="button" className="btn" disabled={!free} title={free ? undefined : 'no free space — remove or shrink a block'} onClick={() => { if (free) commit([...layout, free]); }}>+ {b.id}</button>
                );
              })}
              <button type="button" className="btn" onClick={() => commit(initial)}>reset</button>
              <button type="button" className="btn" onClick={() => setEdit(false)}>done</button>
            </span>
          </>
        ) : (
          <button type="button" className="btn bg-edit" onClick={() => setEdit(true)}>edit layout</button>
        )}
      </div>
      <div className="grid" ref={ref}>
        {layout.map((p) => {
          const def = byId.get(p.id);
          if (!def) return null;
          const { Component } = def;
          const acc = block(p.id);
          const lock = acc?.access === 'locked' ? acc.reason ?? 'Locked' : null;
          return (
            <div key={p.id} className="cell" style={{ gridColumn: `${p.x} / span ${p.w}`, gridRow: `${p.y} / span ${p.h}` }}>
              {lock ? <Window no="--" label={def.title} right="locked"><StateBlock kind="empty" title="Locked." why={`${lock}.`} /></Window> : <Component />}
              {edit ? (
                <div
                  className="edit"
                  tabIndex={0}
                  role="group"
                  aria-label={`${def.title} — arrows move, shift+arrows resize, Delete removes`}
                  onPointerDown={(e) => begin(e, p, 'move')}
                  onPointerMove={move}
                  onPointerUp={end}
                  onPointerCancel={end}
                  onLostPointerCapture={end}
                  onKeyDown={(e) => onKeyCell(e, p)}
                >
                  <span className="edit-t">{def.id} · {p.w}×{p.h}</span>
                  <button type="button" className="btn edit-x" aria-label={`Remove ${def.title}`} onPointerDown={(e) => e.stopPropagation()} onClick={() => commit(layout.filter((q) => q.id !== p.id))}>remove</button>
                  <span className="edit-r" aria-hidden="true" onPointerDown={(e) => begin(e, p, 'size')} onPointerMove={move} onPointerUp={end} onPointerCancel={end} onLostPointerCapture={end} />
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
