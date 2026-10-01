'use client';

import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { CommandLine, type CommandLineHandle } from './CommandLine';
import { NavTree } from './NavTree';

const PIN_KEY = 'dq-nav-pinned';

/**
 * Terminal shell. The sidebar starts pinned. Unpinned, it is hidden and a
 * menu button drops the same sidebar over the page; it closes after use.
 */
export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname() || '/';
  const [pinned, setPinned] = useState(true);
  const [drop, setDrop] = useState(false);
  const cmd = useRef<CommandLineHandle>(null);

  useEffect(() => {
    try { if (localStorage.getItem(PIN_KEY) === '0') setPinned(false); } catch { /* storage unavailable */ }
  }, []);

  const setPin = (next: boolean) => {
    setPinned(next);
    setDrop(false);
    try { localStorage.setItem(PIN_KEY, next ? '1' : '0'); } catch { /* storage unavailable */ }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement;
      if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing)) {
        e.preventDefault();
        cmd.current?.focus();
      } else if (e.key === 'Escape') setDrop(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const rail = (
    <>
      <div className="rail-head">
        <span>nav</span>
        <button type="button" className="btn" onClick={() => setPin(!pinned)} aria-pressed={pinned}>
          {pinned ? 'unpin' : 'pin'}
        </button>
      </div>
      <NavTree pathname={pathname} onNavigate={() => setDrop(false)} />
    </>
  );

  return (
    <div className={`shell${pinned ? ' has-rail' : ''}`}>
      <header className="top">
        <div className="brand">
          {pinned ? null : (
            <button type="button" className="btn" aria-expanded={drop} aria-controls="nav-drop" onClick={() => setDrop((d) => !d)}>
              menu
            </button>
          )}
          <span className="wm">DIGIQUANT</span>
        </div>
        <CommandLine ref={cmd} pathname={pathname} />
      </header>

      {pinned ? <aside className="rail">{rail}</aside> : null}

      {!pinned && drop ? (
        <>
          <div className="scrim" onClick={() => setDrop(false)} />
          <aside id="nav-drop" className="rail drop">{rail}</aside>
        </>
      ) : null}

      <main className="main">{children}</main>
    </div>
  );
}
