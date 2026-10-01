'use client';

import { usePathname } from 'next/navigation';
import { useCallback, useEffect, useRef, useState, type PointerEvent as RPointerEvent, type ReactNode } from 'react';
import { SHORTCUTS } from '@/lib/shortcuts';
import { CommandLine, type CommandLineHandle } from './CommandLine';
import { Logo } from './Logo';
import { NavTree } from './NavTree';

const PIN_KEY = 'dq-nav-pinned';
const W_KEY = 'dq-nav-width';
const W_DEFAULT = 200;
const W_MIN = 140;
const W_MAX = 360;
/** Dragging narrower than this hides the sidebar entirely (same as unpinned). */
const W_COLLAPSE = 110;

/**
 * Terminal shell. The sidebar starts pinned and is resizable. Dragged past its
 * minimum it collapses off the page; the menu link then drops it over the page.
 */
export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname() || '/';
  const [pinned, setPinned] = useState(true);
  const [drop, setDrop] = useState(false);
  const [width, setWidth] = useState(W_DEFAULT);
  const [dragging, setDragging] = useState(false);
  const [help, setHelp] = useState(false);
  const cmd = useRef<CommandLineHandle>(null);

  useEffect(() => {
    try {
      if (localStorage.getItem(PIN_KEY) === '0') setPinned(false);
      const w = Number(localStorage.getItem(W_KEY));
      if (w >= W_MIN && w <= W_MAX) setWidth(w);
    } catch { /* storage unavailable */ }
  }, []);

  const setPin = useCallback((next: boolean) => {
    setPinned(next);
    setDrop(false);
    try { localStorage.setItem(PIN_KEY, next ? '1' : '0'); } catch { /* storage unavailable */ }
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement;
      if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing)) {
        e.preventDefault();
        cmd.current?.focus();
      } else if (e.key === 'Escape') { setDrop(false); setHelp(false); }
      else if (!typing && e.key === '[') setPin(!pinned);
      else if (!typing && e.key === '?') setHelp((h) => !h);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [pinned, setPin]);

  const startResize = (e: RPointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const el = e.currentTarget;
    el.setPointerCapture(e.pointerId);
    setDragging(true);
    let last = width;
    const move = (ev: PointerEvent) => { last = Math.max(60, Math.min(W_MAX, ev.clientX)); setWidth(last); };
    const up = () => {
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up);
      setDragging(false);
      if (last < W_COLLAPSE) { setWidth(W_DEFAULT); setPin(false); return; }
      const final = Math.max(W_MIN, last);
      setWidth(final);
      try { localStorage.setItem(W_KEY, String(final)); } catch { /* storage unavailable */ }
    };
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
  };

  const rail = (
    <>
      <div className="rail-head">
        <span>~/pages</span>
        <button type="button" className="btn" onClick={() => setPin(!pinned)} aria-pressed={pinned}>
          {pinned ? 'unpin' : 'pin'}
        </button>
      </div>
      <NavTree pathname={pathname} onNavigate={() => setDrop(false)} />
    </>
  );

  return (
    <div className={`shell${pinned ? ' has-rail' : ''}${dragging ? ' dragging' : ''}`} style={{ ['--rail' as string]: `${width}px` }}>
      <header className="top">
        <div className="brand">
          {pinned ? null : (
            <button type="button" className="btn" aria-expanded={drop} aria-controls="nav-drop" onClick={() => setDrop((d) => !d)}>
              menu
            </button>
          )}
          <Logo />
        </div>
        <CommandLine ref={cmd} pathname={pathname} />
        <button type="button" className="btn help-btn" onClick={() => setHelp((h) => !h)} aria-label="Keyboard shortcuts">?</button>
      </header>

      {pinned ? (
        <>
          <aside className="rail">{rail}</aside>
          <div className="grip" style={{ left: width - 3 }} role="separator" aria-orientation="vertical" aria-label="Resize sidebar" onPointerDown={startResize} />
        </>
      ) : null}

      {!pinned && drop ? (
        <>
          <div className="scrim" onClick={() => setDrop(false)} />
          <aside id="nav-drop" className="rail drop">{rail}</aside>
        </>
      ) : null}

      <main className="main">{children}</main>

      {help ? (
        <div className="help" role="dialog" aria-label="Keyboard shortcuts">
          <div className="help-head"><span>shortcuts</span><button type="button" className="btn" onClick={() => setHelp(false)}>close</button></div>
          <dl className="kv">
            {SHORTCUTS.map((s) => (
              <div key={s.keys} className="kv-row"><dt className="mono">{s.keys}</dt><dd>{s.does}</dd></div>
            ))}
          </dl>
        </div>
      ) : null}
    </div>
  );
}
