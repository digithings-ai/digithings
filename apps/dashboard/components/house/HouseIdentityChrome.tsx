'use client';

import Link from 'next/link';
import { StatusDot } from '@digithings/ui/ui';
import { SubpageStickyTabBar, subpageTabButtonClass } from '@/components/subpage-tab-bar';
import { HOUSE_BOOK_IDENTITY, HOUSE_CHROME_TABS, type HouseChromeTabId } from '@/lib/house-identity';
import type { RunFreshness } from '@/lib/house-view';

/**
 * Compact status bar for the always-on house run: identity, freshness dot and
 * run type, then the Corpus | Book | Profile tabs. Health tones only.
 */
export default function HouseIdentityChrome({
  active,
  freshness,
  runType,
}: {
  active: HouseChromeTabId;
  freshness?: RunFreshness;
  runType?: 'baseline' | 'delta' | null;
}) {
  return (
    <div data-testid="house-identity-chrome">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-hair bg-surface/80 px-5 py-2 font-mono text-[10px] uppercase tracking-widest text-ink-mute sm:px-7">
        <span>
          {HOUSE_BOOK_IDENTITY.owner} · {HOUSE_BOOK_IDENTITY.label}
        </span>
        {freshness ? (
          <span className="inline-flex items-center gap-1.5 text-ink-soft" data-testid="house-freshness">
            <StatusDot tone={freshness.tone} label={freshness.label} />
            {freshness.label}
          </span>
        ) : null}
        {runType ? <span className="text-ink-soft">{runType}</span> : null}
        <span className="normal-case tracking-normal">{HOUSE_BOOK_IDENTITY.cadence}</span>
      </div>
      <SubpageStickyTabBar aria-label="Corpus Book Profile">
        {HOUSE_CHROME_TABS.map(({ id, label, href }) => (
          <Link key={id} href={href} scroll={false} className={subpageTabButtonClass(active === id)}>
            {label}
          </Link>
        ))}
      </SubpageStickyTabBar>
    </div>
  );
}
