'use client';

import Link from 'next/link';
import { useState, type KeyboardEvent } from 'react';
import { NAV, sectionOf, type NavNode } from '@/lib/nav';

function Tag({ n }: { n: NavNode }) {
  return n.status ? <span className="nav-tag">[{n.status}]</span> : null;
}

/**
 * Sidebar as a folder listing: every line is a slash path behind a triangle.
 * ▾ open, ▸ closed or leaf. Folders toggle with the triangle; the path navigates.
 */
export function NavTree({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const active = sectionOf(pathname);
  const isOpen = (p: string) => open[p] ?? p === active;

  /** ↑/↓ walk the visible lines (Home/End jump), → opens a folder then steps into it, ← closes it or goes to its parent. Enter on a link loads the page; focus stays so you can keep going. */
  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    if (e.altKey || e.metaKey || e.ctrlKey) return;
    const links = [...e.currentTarget.querySelectorAll<HTMLAnchorElement>('a.nav-link')];
    const i = links.indexOf(document.activeElement as HTMLAnchorElement);
    if (i < 0) return;
    const cur = links[i];
    const folder = cur.dataset.folder === '1';
    const path = cur.dataset.path ?? '';
    let to: HTMLAnchorElement | undefined;
    if (e.key === 'ArrowDown') to = links[Math.min(i + 1, links.length - 1)];
    else if (e.key === 'ArrowUp') to = links[Math.max(i - 1, 0)];
    else if (e.key === 'Home') to = links[0];
    else if (e.key === 'End') to = links[links.length - 1];
    else if (e.key === 'ArrowRight' && folder) {
      if (!isOpen(path)) setOpen((o) => ({ ...o, [path]: true }));
      else to = links[i + 1];
    } else if (e.key === 'ArrowLeft') {
      if (folder && isOpen(path)) setOpen((o) => ({ ...o, [path]: false }));
      else if (cur.dataset.parent) to = links.find((l) => l.dataset.path === cur.dataset.parent);
    } else return;
    e.preventDefault();
    to?.focus();
  };

  return (
    <nav className="navtree" aria-label="Pages" onKeyDown={onKeyDown}>
      {NAV.map((g, gi) => (
        <div className="nav-group" key={gi}>
          {g.title ? <div className="nav-title">{g.title}</div> : null}
          {g.items.map((n) => {
            const kids = n.children ?? [];
            const here = pathname === n.path;
            return (
              <div key={n.path}>
                <div className="nav-row">
                  {kids.length ? (
                    <button type="button" className="nav-tri" aria-expanded={isOpen(n.path)} aria-label={`${isOpen(n.path) ? 'Collapse' : 'Expand'} ${n.path}`} onClick={() => setOpen((o) => ({ ...o, [n.path]: !isOpen(n.path) }))}>
                      {isOpen(n.path) ? '▾' : '▸'}
                    </button>
                  ) : <span className="nav-tri leaf" aria-hidden="true">▸</span>}
                  <Link href={n.path} data-path={n.path} data-folder={kids.length ? '1' : undefined} onClick={onNavigate} className={`nav-link${here ? ' on' : ''}`} aria-current={here ? 'page' : undefined} title={n.path}>
                    <span className="nav-path">{n.path}</span>
                    <Tag n={n} />
                  </Link>
                </div>
                {kids.length && isOpen(n.path)
                  ? kids.map((c) => (
                      <div className="nav-row kid" key={c.path}>
                        <span className="nav-tri leaf" aria-hidden="true">▸</span>
                        <Link href={c.path} data-path={c.path} data-parent={n.path} onClick={onNavigate} className={`nav-link${pathname === c.path ? ' on' : ''}`} aria-current={pathname === c.path ? 'page' : undefined} title={c.path}>
                          <span className="nav-path">{c.path}</span>
                          <Tag n={c} />
                        </Link>
                      </div>
                    ))
                  : null}
              </div>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
