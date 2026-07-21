'use client';

import { useCallback } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import { SubpageStickyTabBar, subpageTabButtonClass } from '@/components/subpage-tab-bar';
import { WHY_TABS, resolveWhyTab, type WhyTabId } from '@/lib/why-tabs';
import { TheRead } from '@/components/why/the-read';
import { DeliberationsTab } from '@/components/why/deliberations-tab';

/**
 * Why — the reasoning, ordered synthesized → argued:
 *  • The read       — the structured digest
 *  • Deliberations  — bull/bear, risk debate, rebalance memo, PM-memo history
 *
 * The standalone Documents archive (per-day reader + carry-forward browser) was
 * retired (deferred behind distinct-dates>1). Per-day reading now lives in
 * Pipeline node-detail; cross-day discovery lives in the command palette.
 */
export default function WhyClient() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const active = resolveWhyTab({ why: searchParams.get('why') });
  const activeLabel = WHY_TABS.find((tab) => tab.id === active)?.label ?? 'The read';

  const setTab = useCallback(
    (next: WhyTabId) => {
      const p = new URLSearchParams(searchParams.toString());
      p.set('why', next);
      const s = p.toString();
      router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams]
  );

  return (
    <div data-testid="why-workspace" className="flex min-h-full flex-col">
      <div className={`${SUBPAGE_MAX} pt-4 md:pt-6`}>
        <header
          data-testid="why-command-band"
          className="grid gap-4 border border-hair bg-surface px-4 py-4 md:px-6 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end"
        >
          <div className="min-w-0">
            <p className="font-mono text-xs font-semibold uppercase text-ink-mute">
              Reasoning workspace
            </p>
            <h1 className="mt-1 font-display text-3xl text-ink">
              Why the book looks this way
            </h1>
            <p className="mt-1 text-sm text-ink-mute">
              synthesized read → challenged decisions → PM record
            </p>
          </div>
          <dl className="grid grid-cols-2 gap-px border border-hair bg-hair text-sm lg:min-w-64">
            <div className="bg-surface px-3 py-2">
              <dt className="font-mono text-xs uppercase text-ink-mute">View</dt>
              <dd className="mt-1 font-medium text-ink">{activeLabel}</dd>
            </div>
            <div className="bg-surface px-3 py-2">
              <dt className="font-mono text-xs uppercase text-ink-mute">Record</dt>
              <dd className="mt-1 font-medium text-ink">Latest run</dd>
            </div>
          </dl>
        </header>
      </div>

      <SubpageStickyTabBar aria-label="Why sections">
        {WHY_TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={subpageTabButtonClass(active === id)}
          >
            <Icon size={16} aria-hidden />
            {label}
          </button>
        ))}
      </SubpageStickyTabBar>

      <main className={`${SUBPAGE_MAX} flex-1 pb-6 pt-4 md:pb-8 md:pt-6`}>
        {active === 'read' ? <TheRead /> : <DeliberationsTab />}
      </main>
    </div>
  );
}
