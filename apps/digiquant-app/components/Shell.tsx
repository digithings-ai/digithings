'use client';

import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { CommandLine, type CommandLineHandle } from './CommandLine';
import { NavTree } from './NavTree';

const PIN_KEY = 'dq-nav-pinned';

/**
 * Terminal shell. The whole page is the workspace; the nav is a drop-down
 * from the top bar that goes away after use, unless pinned into a left rail.
 */
export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname() || '/';
  const [menu, setMenu] = useState(false);
  const [pinned, setPinned] = useState(false);
  const cmd = useRef<CommandLineHandle>(null);

  useEffect(() => {
    try { setPinned(localStorage.getItem(PIN_KEY) === '1'); } catch { /* storage unavailable */ }
  }, []);

  const togglePin = () => {
    setPinned((p) => {
      try { localStorage.setItem(PIN_KEY, p ? '0' : '1'); } catch { /* storage unavailable */ }
      return !p;
    });
    setMenu(false);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement;
      if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing)) {
        e.preventDefault();
        cmd.current?.focus();
      } else if (e.key === 'Escape') setMenu(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <div className={`shell${pinned ? ' has-rail' : ''}`}>
      <header className="top">
        {pinned ? null : (
          <button type="button" className="top-btn" aria-expanded={menu} aria-controls="nav-menu" onClick={() => setMenu((m) => !m)}>
            menu <span aria-hidden>{menu ? '▴' : '▾'}</span>
          </button>
        )}
        <span className="brand">DIGIQUANT</span>
        <CommandLine ref={cmd} pathname={pathname} />
        <span className="top-spacer" />
        <button type="button" className={`top-btn${pinned ? ' on' : ''}`} aria-pressed={pinned} onClick={togglePin} title="Keep the navigation on the page">
          {pinned ? 'unpin nav' : 'pin nav'}
        </button>
      </header>

      {menu && !pinned ? (
        <>
          <div className="scrim" onClick={() => setMenu(false)} />
          <div id="nav-menu" className="drop">
            <NavTree pathname={pathname} variant="menu" onNavigate={() => setMenu(false)} />
            <div className="drop-foot mute">
              <span>/ or ⌘K — go to any page by path</span>
              <button type="button" className="top-btn" onClick={togglePin}>pin as sidebar</button>
            </div>
          </div>
        </>
      ) : null}

      {pinned ? (
        <aside className="rail">
          <NavTree pathname={pathname} variant="rail" />
        </aside>
      ) : null}

      <main className="main">{children}</main>
    </div>
  );
}
