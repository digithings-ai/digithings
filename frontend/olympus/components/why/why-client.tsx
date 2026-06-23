'use client';

import { useCallback } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { SubpageStickyTabBar, subpageTabButtonClass, SUBPAGE_MAX } from '@/components/subpage-tab-bar';
import { WHY_TABS, resolveWhyTab, type WhyTabId } from '@/lib/why-tabs';
import ResearchClient from '@/app/research/ResearchClient';
import { TheRead } from '@/components/why/the-read';
import { DeliberationsTab } from '@/components/why/deliberations-tab';

/**
 * Why — the reasoning, ordered synthesized → argued → sourced:
 *  • The read       — the structured digest
 *  • Deliberations  — bull/bear, risk debate, rebalance memo, PM-memo history
 *  • Documents      — the full research library (the existing browser, intact)
 *
 * The Why tab uses its own `why` URL param so it never collides with the
 * Documents browser's `tab`/`date`/`docKey` params; legacy research/library
 * deep links (which carry those) resolve to Documents.
 */
export default function WhyClient() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const active = resolveWhyTab({
    why: searchParams.get('why'),
    tab: searchParams.get('tab'),
    date: searchParams.get('date'),
    docKey: searchParams.get('docKey'),
  });

  const setTab = useCallback(
    (next: WhyTabId) => {
      const p = new URLSearchParams(searchParams.toString());
      p.set('why', next);
      // Leaving Documents drops its browser-scoped params so the URL stays clean.
      if (next !== 'documents') {
        p.delete('tab');
        p.delete('date');
        p.delete('docKey');
      }
      const s = p.toString();
      router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams]
  );

  return (
    <div className="flex min-h-full flex-col">
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

      {active === 'documents' ? (
        <ResearchClient />
      ) : (
        <div className={`${SUBPAGE_MAX} flex-1 py-4 md:py-6`}>
          {active === 'read' ? <TheRead /> : <DeliberationsTab />}
        </div>
      )}
    </div>
  );
}
