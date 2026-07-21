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

      <div className={`${SUBPAGE_MAX} flex-1 py-4 md:py-6`}>
        {active === 'read' ? <TheRead /> : <DeliberationsTab />}
      </div>
    </div>
  );
}
