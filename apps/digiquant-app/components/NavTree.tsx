'use client';

import Link from 'next/link';
import { useState } from 'react';
import { NAV, sectionOf, type NavNode } from '@/lib/nav';

function Tag({ n }: { n: NavNode }) {
  return n.status ? <span className="nav-tag">[{n.status}]</span> : null;
}

/**
 * One nav tree, two presentations.
 * - menu: every section open, laid out in columns (drop-down from the top bar)
 * - rail: accordion — the active section is open, others reveal on click (pinned sidebar)
 */
export function NavTree({ pathname, variant, onNavigate }: { pathname: string; variant: 'menu' | 'rail'; onNavigate?: () => void }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const active = sectionOf(pathname);
  const isOpen = (p: string) => variant === 'menu' || (open[p] ?? p === active);
  let no = 0;

  return (
    <nav className={`navtree ${variant}`} aria-label="Pages">
      {NAV.map((g, gi) => (
        <div className="nav-group" key={gi}>
          {g.title ? <div className="nav-title">{g.title}</div> : null}
          {g.items.map((n) => {
            no += 1;
            const num = String(no).padStart(2, '0');
            const here = pathname === n.path;
            const hasKids = !!n.children?.length;
            return (
              <div key={n.path}>
                <div className="nav-row">
                  <Link href={n.path} onClick={onNavigate} className={`nav-link${here ? ' on' : ''}`} aria-current={here ? 'page' : undefined}>
                    <span className="nav-no">{num}</span>
                    <span>{n.label}</span>
                    <Tag n={n} />
                  </Link>
                  {hasKids && variant === 'rail' ? (
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
                {hasKids && isOpen(n.path) ? (
                  <div className="nav-kids">
                    {n.children!.map((c) => (
                      <Link key={c.path} href={c.path} onClick={onNavigate} className={`nav-link kid${pathname === c.path ? ' on' : ''}`} aria-current={pathname === c.path ? 'page' : undefined}>
                        <span>{c.label}</span>
                        <Tag n={c} />
                      </Link>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
