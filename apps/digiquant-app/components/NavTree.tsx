'use client';

import Link from 'next/link';
import { useState } from 'react';
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

  return (
    <nav className="navtree" aria-label="Pages">
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
                  <Link href={n.path} onClick={onNavigate} className={`nav-link${here ? ' on' : ''}`} aria-current={here ? 'page' : undefined} title={n.path}>
                    <span className="nav-path">{n.path}</span>
                    <Tag n={n} />
                  </Link>
                </div>
                {kids.length && isOpen(n.path)
                  ? kids.map((c) => (
                      <div className="nav-row kid" key={c.path}>
                        <span className="nav-tri leaf" aria-hidden="true">▸</span>
                        <Link href={c.path} onClick={onNavigate} className={`nav-link${pathname === c.path ? ' on' : ''}`} aria-current={pathname === c.path ? 'page' : undefined} title={c.path}>
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
