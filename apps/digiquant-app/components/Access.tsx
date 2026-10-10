'use client';

import { usePathname, useRouter } from 'next/navigation';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { blockAccess, findEntry, flatNav, lockTag, navFromDesk, type BlockEntry, type DeskEntry, type Manifest } from '@/lib/access';
import { dqGet } from '@/lib/dq-api';
import type { NavGroup, NavNode } from '@/lib/nav';
import { StateBlock } from './ui';

const DESK_KEY = 'dq-desk';

type Ctx = {
  manifest: Manifest | null;
  err: string | null;
  desk: DeskEntry | null;
  setDesk: (id: string) => void;
  nav: NavGroup[];
  pages: NavNode[];
  block: (id: string) => BlockEntry | null;
};

const AccessCtx = createContext<Ctx>({ manifest: null, err: null, desk: null, setDesk: () => {}, nav: [], pages: [], block: () => null });
export const useAccess = () => useContext(AccessCtx);

/**
 * Loads the caller's access manifest once and owns the active desk. Fails closed:
 * if the manifest cannot be read, nothing is offered. Identity comes from the
 * worker (edge headers, or the dev caller). The app does not impersonate a tier.
 */
export function AccessProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname() || '/';
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [deskId, setDeskId] = useState<string | null>(null);

  useEffect(() => {
    try { setDeskId(localStorage.getItem(DESK_KEY)); } catch { /* storage unavailable */ }
    dqGet<Manifest>('/access/manifest')
      .then((env) => setManifest(env.data))
      .catch((e: unknown) => setErr(e instanceof Error ? e.message : 'failed'));
  }, []);

  const setDesk = useCallback((id: string) => {
    setDeskId(id);
    try { localStorage.setItem(DESK_KEY, id); } catch { /* storage unavailable */ }
  }, []);

  // The desk that owns the current path wins, so deep links and the command line switch desks themselves.
  const owner = manifest ? findEntry(manifest, pathname, deskId ?? undefined)?.desk.id ?? null : null;
  useEffect(() => { if (owner && owner !== deskId) setDesk(owner); }, [owner, deskId, setDesk]);

  const desk = useMemo(() => {
    if (!manifest) return null;
    const granted = manifest.desks.find((d) => d.access === 'granted');
    return manifest.desks.find((d) => d.id === (owner ?? deskId) && d.access === 'granted') ?? granted ?? manifest.desks[0] ?? null;
  }, [manifest, deskId, owner]);

  const value = useMemo<Ctx>(() => {
    const nav = desk ? navFromDesk(desk) : [];
    return { manifest, err, desk, setDesk, nav, pages: flatNav(nav), block: (id) => (manifest ? blockAccess(manifest, id) : null) };
  }, [manifest, err, desk, setDesk]);

  return <AccessCtx.Provider value={value}>{children}</AccessCtx.Provider>;
}

/** Guards a page: dev galleries pass; everything else must be in the manifest and granted. */
export function PageGate({ children }: { children: ReactNode }) {
  const pathname = usePathname() || '/';
  const { manifest, err, desk } = useAccess();
  if (pathname.startsWith('/blocks')) return <>{children}</>;
  if (err) return <StateBlock kind="error" title="Access unavailable." why={err} />;
  if (!manifest) return <p className="note mute">loading…</p>;
  const hit = findEntry(manifest, pathname, desk?.id);
  if (!hit) return <StateBlock kind="empty" title="Not available." why={`${pathname} is not part of any desk you can see.`} next={[{ label: 'Brief', href: '/brief' }]} />;
  const why = hit.desk.access === 'locked' ? hit.desk.reason : hit.page.access === 'locked' ? hit.page.reason : null;
  if (why) return <StateBlock kind="empty" title="Locked." why={`${hit.page.label} (${pathname}): ${why}.`} next={[{ label: 'Brief', href: '/brief' }]} />;
  if (hit.page.status === 'soon' && hit.page.blocks.length === 0) {
    return <StateBlock kind="empty" title="Coming soon." why={`${hit.page.label} is not built yet. It is listed so you can see what is on the way.`} next={[{ label: 'Brief', href: '/brief' }]} />;
  }
  return <>{children}</>;
}

/** Top-bar desk selector: `d` opens it, ↑/↓ choose, Enter switches, Esc closes. Locked desks show why and cannot be opened. */
export function DeskPicker() {
  const { manifest, desk, setDesk } = useAccess();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const list = useRef<HTMLUListElement>(null);
  const btn = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement || t instanceof HTMLSelectElement || !!t?.isContentEditable;
      if (e.key === 'd' && !typing && !e.metaKey && !e.ctrlKey && !e.altKey) { e.preventDefault(); setOpen(true); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    if (open) list.current?.querySelector<HTMLElement>('button:not([disabled])[aria-current="true"], button:not([disabled])')?.focus();
  }, [open]);

  if (!manifest || !desk) return <span className="desk-pick mute">desk: —</span>;

  const close = () => { setOpen(false); btn.current?.focus(); };
  const onKeyDown = (e: KeyboardEvent<HTMLUListElement>) => {
    const items = [...e.currentTarget.querySelectorAll<HTMLButtonElement>('button:not([disabled])')];
    const i = items.indexOf(document.activeElement as HTMLButtonElement);
    if (e.key === 'ArrowDown') items[Math.min(i + 1, items.length - 1)]?.focus();
    else if (e.key === 'ArrowUp') items[Math.max(i - 1, 0)]?.focus();
    else if (e.key === 'Escape') close();
    else return;
    e.preventDefault();
    e.stopPropagation();
  };

  return (
    <div className="desk-pick">
      <button ref={btn} type="button" className="btn" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen((o) => !o)} title="Switch desk (d)">
        desk: {desk.label} ▾
      </button>
      {open ? (
        <>
          <div className="scrim" onClick={() => setOpen(false)} />
          <ul ref={list} className="desk-list" role="listbox" aria-label="Desks" onKeyDown={onKeyDown}>
            {manifest.desks.map((d) => (
              <li key={d.id} role="option" aria-selected={d.id === desk.id}>
                <button type="button" disabled={d.access === 'locked'} aria-current={d.id === desk.id ? 'true' : undefined} onClick={() => { setDesk(d.id); setOpen(false); const home = d.pages.find((p) => p.access === 'granted'); if (home) router.push(home.path); }}>
                  <span className="desk-name">{d.label}{d.access === 'locked' ? <span className="nav-tag">[{lockTag(d.reason)}]</span> : null}</span>
                  <span className="desk-blurb">{d.access === 'locked' ? d.reason : d.blurb}</span>
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}
