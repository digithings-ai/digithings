'use client';

import { usePathname } from 'next/navigation';
import { useCallback, useEffect, useRef, useState, type KeyboardEvent as RKeyEvent, type PointerEvent as RPointerEvent, type ReactNode } from 'react';
import { SHORTCUTS } from '@/lib/shortcuts';
import { CommandLine, type CommandLineHandle } from './CommandLine';
import { DeskPicker, PageGate } from './Access';
import { ChatRail } from './ChatRail';
import { Logo } from './Logo';
import { NavTree } from './NavTree';

const PIN_KEY = 'dq-nav-pinned';
const CHAT_KEY = 'dq-chat-rail';
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
  const [chat, setChat] = useState(false);
  const [narrow, setNarrow] = useState(false);
  const cmd = useRef<CommandLineHandle>(null);
  const helpRef = useRef<HTMLDivElement>(null);
  const dropRef = useRef<HTMLElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  // Below this width a pinned rail would crush the page (small screens, high zoom): treat as unpinned.
  const showRail = pinned && !narrow;

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 720px)');
    const on = () => setNarrow(mq.matches);
    on();
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);

  // Dialog / drop-over focus: move focus in on open, hand it back on close.
  useEffect(() => {
    if (!help) return;
    opener.current = document.activeElement as HTMLElement | null;
    helpRef.current?.focus();
    return () => { opener.current?.focus?.(); };
  }, [help]);
  useEffect(() => {
    if (!drop) return;
    const from = document.activeElement as HTMLElement | null;
    dropRef.current?.querySelector<HTMLElement>('a,button')?.focus();
    return () => { from?.focus?.(); };
  }, [drop]);

  useEffect(() => {
    try {
      if (localStorage.getItem(PIN_KEY) === '0') setPinned(false);
      if (localStorage.getItem(CHAT_KEY) === '1') setChat(true);
      const w = Number(localStorage.getItem(W_KEY));
      if (w >= W_MIN && w <= W_MAX) setWidth(w);
    } catch { /* storage unavailable */ }
  }, []);

  const setPin = useCallback((next: boolean) => {
    setPinned(next);
    setDrop(false);
    try { localStorage.setItem(PIN_KEY, next ? '1' : '0'); } catch { /* storage unavailable */ }
  }, []);

  const focusNav = () => {
    const links = document.querySelectorAll<HTMLElement>('.navtree a.nav-link');
    (document.querySelector<HTMLElement>('.navtree a.nav-link.on') ?? links[0])?.focus();
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement || t instanceof HTMLSelectElement || !!t?.isContentEditable;
      const bare = !e.metaKey && !e.ctrlKey && !e.altKey;
      if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing && bare)) {
        e.preventDefault();
        cmd.current?.focus();
      } else if (e.key === 'Escape') { setDrop(false); setHelp(false); }
      else if (!typing && bare && e.key === '[') setPin(!pinned);
      else if (!typing && bare && e.key === 'n') {
        e.preventDefault();
        if (!showRail) setDrop(true);
        else focusNav();
      }
      else if (!typing && bare && e.key === '?') setHelp((h) => !h);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [pinned, setPin, showRail]);

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
      el.removeEventListener('pointercancel', up);
      setDragging(false);
      if (last < W_COLLAPSE) { setWidth(W_DEFAULT); setPin(false); return; }
      const final = Math.max(W_MIN, last);
      setWidth(final);
      try { localStorage.setItem(W_KEY, String(final)); } catch { /* storage unavailable */ }
    };
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', up);
  };

  const persistWidth = (w: number) => {
    setWidth(w);
    try { localStorage.setItem(W_KEY, String(w)); } catch { /* storage unavailable */ }
  };
  const onGripKey = (e: RKeyEvent<HTMLDivElement>) => {
    const big = e.shiftKey ? 40 : 10;
    if (e.key === 'ArrowLeft') persistWidth(Math.max(W_MIN, width - big));
    else if (e.key === 'ArrowRight') persistWidth(Math.min(W_MAX, width + big));
    else if (e.key === 'Home') persistWidth(W_MIN);
    else if (e.key === 'End') persistWidth(W_MAX);
    else if (e.key === 'Enter') { setWidth(W_DEFAULT); setPin(false); }
    else return;
    e.preventDefault();
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
    <div className={`shell${showRail ? ' has-rail' : ''}${chat ? ' has-chat' : ''}${dragging ? ' dragging' : ''}`} style={{ ['--rail' as string]: `${width}px` }}>
      <a className="skip" href="#main">skip to content</a>
      <header className="top">
        <div className="brand">
          {showRail ? null : (
            <button type="button" className="btn" aria-expanded={drop} aria-controls="nav-drop" onClick={() => setDrop((d) => !d)}>
              menu
            </button>
          )}
          <Logo />
        </div>
        <DeskPicker />
        <CommandLine ref={cmd} pathname={pathname} />
        <button
          type="button"
          className="btn help-btn"
          aria-pressed={chat}
          aria-expanded={chat}
          aria-controls="chat-rail"
          onClick={() => {
            setChat((v) => {
              const next = !v;
              try { localStorage.setItem(CHAT_KEY, next ? '1' : '0'); } catch { /* storage unavailable */ }
              return next;
            });
          }}
        >chat</button>
        <button type="button" className="btn help-btn" onClick={() => setHelp((h) => !h)} aria-label="Keyboard shortcuts" aria-expanded={help} aria-controls="help">?</button>
      </header>

      {showRail ? (
        <>
          <aside className="rail">{rail}</aside>
          <div
            className="grip"
            style={{ left: width - 3 }}
            role="separator"
            tabIndex={0}
            aria-orientation="vertical"
            aria-label="Resize sidebar (arrows; Enter hides)"
            aria-valuenow={width}
            aria-valuemin={W_MIN}
            aria-valuemax={W_MAX}
            onPointerDown={startResize}
            onKeyDown={onGripKey}
          />
        </>
      ) : null}

      {!showRail && drop ? (
        <>
          <div className="scrim" onClick={() => setDrop(false)} />
          <aside id="nav-drop" ref={dropRef} className="rail drop">{rail}</aside>
        </>
      ) : null}

      <main id="main" tabIndex={-1} className="main"><PageGate>{children}</PageGate></main>
      <ChatRail open={chat} />

      {help ? (
        <div id="help" ref={helpRef} tabIndex={-1} className="help" role="dialog" aria-modal="true" aria-label="Keyboard shortcuts">
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
