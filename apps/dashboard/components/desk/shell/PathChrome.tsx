'use client';

import Link from 'next/link';
import { Button } from '@digithings/ui/ui';
import type { ChromeSegment } from '@/lib/desk/spine';

export function PathChrome({
  segments,
  railCollapsed,
  onToggleRail,
  onSearch,
}: {
  segments: readonly ChromeSegment[];
  railCollapsed: boolean;
  onToggleRail: () => void;
  onSearch: () => void;
}) {
  return (
    <header
      data-path-chrome=""
      className="col-span-full flex h-11 min-w-0 items-center gap-3 border-b border-hair bg-surface px-3"
    >
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        onClick={onToggleRail}
        aria-label={railCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {railCollapsed ? '›' : '‹'}
      </Button>
      <nav aria-label="Path" className="flex min-w-0 flex-1 items-center gap-0 font-mono text-xs text-ink">
        {segments.map((segment, index) => (
          <span key={`${segment.href}-${segment.label}`} className="flex min-w-0 items-center">
            {index > 0 ? (
              <span aria-hidden className="px-1 text-ink-mute">
                {' / '}
              </span>
            ) : null}
            <Link href={segment.href} className="truncate text-ink hover:text-accent">
              {segment.label}
            </Link>
          </span>
        ))}
      </nav>
      <p data-posture="" className="hidden font-mono text-[0.68rem] tracking-[0.06em] text-ink-mute uppercase sm:block">
        paper / research
      </p>
      <Button type="button" variant="outline" size="sm" onClick={onSearch} aria-label="Search">
        Search
      </Button>
    </header>
  );
}
