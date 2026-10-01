'use client';

import Link from 'next/link';
import { useState } from 'react';
import { NAV, sectionOf, type NavNode } from '@/lib/nav';

function Tag({ n }: { n: NavNode }) {
  return n.status ? <span className="nav-tag">[{n.status}]</span> : null;
}

/** Sidebar tree. The active section is open; others reveal on click. */
export function NavTree({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const active = sectionOf(pathname);
  const isOpen = (p: string) => open[p] ?? p === active;
  let no = 0;

  return (
    <nav className="navtree" aria-label="Pages">
      {NAV.map((g, gi) => (
        <div className="nav-group" key={gi}>
          {g.title ? <div className="nav-title">{g.title}</div> : null}
          {g.items.map((n) => {
            no += 1;
            const here = pathname === n.path;
            const hasKids = !!n.children?.length;
            return (
              <div key={n.path}>
                <div className="nav-row">
                  <Link href={n.path} onClick={onNavigate} className={`nav-link${here ? ' on' : ''}`} aria-current={here ? 'page' : undefined}>
                    <span className="nav-no">{String(no).padStart(2, '0')}</span>
                    <span>{n.label}</span>
                    <Tag n={n} />
                  </Link>
                  {hasKids ? (
                    <button
                      type="button"
                      className="nav-twist"
                      aria-expanded={isOpen(n.path)}
                      aria-label={`${isOpen(n.path) ? 'Collapse' : 'Expand'} ${n.label}`}
                      onClick={() => setOpen((o) => ({ ...o, [n.path]: !isOpen(n.path) }))}
                    >
                      {isOpen(n.path) ? '–' : '+'}
                    </button>
                  ) : null}
                </div>
                {hasKids && isOpen(n.path)
                  ? n.children!.map((c) => (
                      <Link key={c.path} href={c.path} onClick={onNavigate} className={`nav-link kid${pathname === c.path ? ' on' : ''}`} aria-current={pathname === c.path ? 'page' : undefined}>
                        <span>{c.label}</span>
                        <Tag n={c} />
                      </Link>
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
