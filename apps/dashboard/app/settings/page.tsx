'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { Alert, AlertDescription, SearchBar } from '@digithings/ui/ui';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import { usePageHeader } from '@/components/shell/page-header';
import { AccountIdentity } from '@/components/settings/account-section';
import { AppearanceSection } from '@/components/settings/appearance-section';
import { ConnectionsSection } from '@/components/settings/connections-section';
import { FxHubAccount } from '@/components/settings/fx-hub-account';
import { NotifyTab } from '@/components/settings/notify-tab';
import { PipelineTab } from '@/components/settings/pipeline-tab';
import { PlanSection } from '@/components/settings/plan-section';
import { ProfileTab } from '@/components/settings/profile-tab';
import { SystemSection } from '@/components/settings/system-section';
import { useDashboard } from '@/lib/dashboard-context';
import { dataSourceHost } from '@/lib/data-source-host';
import { useAuth } from '@/lib/auth-context';
import { useFxHubOnlyInvitee } from '@/lib/fx-hub-only';
import { usePlanTier } from '@/lib/use-entitlement';
import { settingsTabsVisible } from '@/lib/entitlements';
import type { SettingsApiOptions } from '@/lib/settings-api';
import { filterSettingsIndex } from '@/lib/settings-index';
import {
  defaultSection,
  resolveSettingsTarget,
  visibleSections,
  type SettingsSectionId,
} from '@/lib/settings-sections';

const SECTION_BLURB: Record<SettingsSectionId, string> = {
  account: 'Who you are signed in as, and your investment profile.',
  pipeline: 'Overlay research knobs, the weekly schedule, and recent runs.',
  connections: 'Brokers and model keys in one place. Secrets are never shown after save.',
  plan: 'Where you are on the ladder, and what the next rung unlocks.',
  notifications: 'Digests and alerts, and when they last went out.',
  appearance: 'Device-local display preferences. Applied immediately.',
  system: 'Last run, build, data source, and the remaining-hop proof.',
};

function scrollToAnchor(anchor: string) {
  if (typeof document === 'undefined') return;
  const el = document.getElementById(anchor);
  if (el && typeof el.scrollIntoView === 'function') {
    el.scrollIntoView({ block: 'start' });
  }
}

export default function SettingsPage() {
  usePageHeader({ title: 'Settings' });
  const { data } = useDashboard();
  const { session } = useAuth();
  const tier = usePlanTier();
  const { canFxHub, fxHubOnlyInvitee } = useFxHubOnlyInvitee();
  const tabs = useMemo(() => settingsTabsVisible(tier), [tier]);
  const visibleTabIds = useMemo(() => tabs.map((t) => t.id), [tabs]);
  const sections = useMemo(() => visibleSections(visibleTabIds), [visibleTabIds]);
  const sectionIds = useMemo(() => sections.map((s) => s.id), [sections]);
  const meta = data?.portfolio?.meta ?? null;

  // Start where the prerender started; the effect below adopts the URL on the
  // first post-hydration commit. Reading location here instead would hydrate a
  // rail whose highlight React never writes out — see TwelveXClient.
  const [active, setActive] = useState<SettingsSectionId>(() => defaultSection(visibleTabIds));
  const [lastVersionId, setLastVersionId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [checkout, setCheckout] = useState<'success' | 'cancel' | null>(null);
  const pending = useRef<string | null>(null);

  const activeSection = sectionIds.includes(active) ? active : defaultSection(visibleTabIds);

  // URL -> section (deep links, Stripe return, OAuth return, sidebar children).
  useEffect(() => {
    const apply = (scroll: boolean) => {
      const target = resolveSettingsTarget(
        window.location.search,
        window.location.hash,
        visibleTabIds,
      );
      const params = new URLSearchParams(window.location.search);
      const c = params.get('checkout');
      setCheckout(c === 'success' || c === 'cancel' ? c : null);
      if (!target) return;
      setActive(target.section);
      if (scroll) pending.current = target.anchor;
    };
    apply(true);
    const onHash = () => apply(true);
    window.addEventListener('hashchange', onHash);
    window.addEventListener('popstate', onHash);
    return () => {
      window.removeEventListener('hashchange', onHash);
      window.removeEventListener('popstate', onHash);
    };
  }, [visibleTabIds]);

  // Scroll once the section DOM exists (after the state commit above).
  useEffect(() => {
    if (!pending.current) return;
    const anchor = pending.current;
    pending.current = null;
    scrollToAnchor(anchor);
  });

  // Scrollspy: highlight the rail item for the section nearest the top.
  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return;
    const seen = new Set<string>();
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) seen.add(e.target.id);
          else seen.delete(e.target.id);
        }
        const first = sectionIds.find((id) => seen.has(id));
        if (first) setActive(first);
      },
      { rootMargin: '-15% 0px -70% 0px' },
    );
    for (const id of sectionIds) {
      const el = document.getElementById(id);
      if (el) io.observe(el);
    }
    return () => io.disconnect();
  }, [sectionIds]);

  const jump = useCallback((id: string, section: SettingsSectionId) => {
    setActive(section);
    if (typeof window !== 'undefined') {
      const next = `#${id}`;
      if (window.location.hash !== next) window.history.replaceState(null, '', next);
    }
    scrollToAnchor(id);
  }, []);

  const hits = useMemo(() => filterSettingsIndex(query, sectionIds), [query, sectionIds]);

  const api: SettingsApiOptions | null = useMemo(() => {
    const token = session?.access_token;
    if (!token) return null;
    return { accessToken: token };
  }, [session?.access_token]);

  if (fxHubOnlyInvitee) {
    return (
      <div className={`${SUBPAGE_MAX} py-6 md:py-8 space-y-6`}>
        <header className="space-y-2">
          <p className="font-mono text-[0.72rem] tracking-[0.02em] text-ink">
            fx hub <span className="text-ink-mute">· account</span>
          </p>
          <h1 className="font-display text-3xl tracking-tight text-ink">Your account.</h1>
          <p className="max-w-[46ch] text-[0.88rem] leading-[1.45] text-ink-soft">
            Your FX Hub profile: invite status and sign-out only. Desk settings do not apply to
            this product.
          </p>
        </header>
        <div
          className="max-w-2xl border border-hair bg-surface p-[1.1rem_1.2rem]"
          data-testid="settings-fx-hub-account"
        >
          <FxHubAccount fxHubGranted={canFxHub} />
        </div>
      </div>
    );
  }

  const has = (id: (typeof visibleTabIds)[number]) => visibleTabIds.includes(id);

  function body(id: SettingsSectionId) {
    switch (id) {
      case 'account':
        return (
          <div className="space-y-5">
            <AccountIdentity tier={tier} />
            {has('profile') ? (
              <div id="profile" className="scroll-mt-20">
                <ProfileTab
                  api={api}
                  lastVersionId={lastVersionId}
                  onVersionSaved={setLastVersionId}
                />
              </div>
            ) : null}
          </div>
        );
      case 'pipeline':
        return (
          <div className="space-y-5">
            <Link
              href="/pipeline"
              className="inline-block font-mono text-xs text-accent underline-offset-2 hover:underline"
              data-testid="settings-open-pipeline"
            >
              Open pipeline view
            </Link>
            <PipelineTab
              api={api}
              lastVersionId={lastVersionId}
              onVersionSaved={setLastVersionId}
            />
          </div>
        );
      case 'connections':
        return <ConnectionsSection api={api} visibleTabs={visibleTabIds} />;
      case 'plan':
        return (
          <div className="space-y-4">
            <span id="billing" className="block scroll-mt-20" aria-hidden />
            {checkout ? (
              <Alert data-testid="settings-checkout-notice">
                <AlertDescription>
                  {checkout === 'success'
                    ? 'Checkout complete. Your plan updates once Stripe confirms.'
                    : 'Checkout cancelled. Nothing was charged.'}
                </AlertDescription>
              </Alert>
            ) : null}
            <PlanSection api={api} tier={tier} />
          </div>
        );
      case 'notifications':
        return <NotifyTab api={api} />;
      case 'appearance':
        return <AppearanceSection />;
      case 'system':
        return (
          <div id="about" className="scroll-mt-20">
            <SystemSection
              api={api}
              lastRunDate={meta?.last_updated ?? null}
              lastRunAt={meta?.last_run_at ?? null}
              runType={meta?.latest_snapshot_run_type ?? null}
              version={process.env.NEXT_PUBLIC_DASHBOARD_VERSION ?? 'v0.1 · dev'}
              dataSourceHost={dataSourceHost()}
            />
          </div>
        );
    }
  }

  return (
    <div className={`${SUBPAGE_MAX} py-6 md:py-8 space-y-5`} data-testid="settings-page">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <p className="font-mono text-[0.72rem] tracking-[0.02em] text-ink">
          dashboard <span className="text-ink-mute">· settings</span>
        </p>
        <div className="relative w-full sm:w-72">
          <SearchBar
            value={query}
            onChange={setQuery}
            placeholder="Search settings"
            aria-label="Search settings"
            data-testid="settings-search"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && hits[0]) {
                jump(hits[0].anchor, hits[0].section);
                setQuery('');
              }
              if (e.key === 'Escape') setQuery('');
            }}
          />
          {query.trim() ? (
            <ul
              className="absolute inset-x-0 top-full z-10 mt-1 border border-hair bg-surface"
              data-testid="settings-search-results"
              aria-label="Matching settings"
            >
              {hits.length === 0 ? (
                <li className="px-3 py-2 text-xs text-ink-mute">No matching settings</li>
              ) : (
                hits.map((hit) => (
                  <li key={hit.id}>
                    <button
                      type="button"
                      className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm text-ink-soft hover:bg-accent-weak hover:text-ink"
                      onClick={() => {
                        jump(hit.anchor, hit.section);
                        setQuery('');
                      }}
                      data-testid="settings-search-hit"
                    >
                      <span>{hit.label}</span>
                      <span className="font-mono text-[0.65rem] uppercase tracking-wider text-ink-mute">
                        {sections.find((s) => s.id === hit.section)?.label}
                      </span>
                    </button>
                  </li>
                ))
              )}
            </ul>
          ) : null}
        </div>
      </header>

      <div className="grid gap-5 md:grid-cols-[11rem_minmax(0,1fr)]">
        <nav
          aria-label="Settings sections"
          className="sticky top-0 z-10 -mx-1 flex gap-1 overflow-x-auto bg-bg px-1 py-1 md:top-4 md:mx-0 md:flex-col md:self-start md:overflow-visible md:p-0"
          data-testid="settings-rail"
        >
          {sections.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => jump(s.id, s.id)}
              aria-current={activeSection === s.id ? 'true' : undefined}
              data-testid={`settings-section-${s.id}`}
              className={`shrink-0 border-s-2 px-3 py-1.5 text-left font-mono text-xs transition-colors ${
                activeSection === s.id
                  ? 'border-s-accent bg-accent-weak text-ink'
                  : 'border-s-transparent text-ink-mute hover:text-ink-soft'
              }`}
            >
              {s.label}
            </button>
          ))}
        </nav>

        <div className="min-w-0 space-y-6">
          {sections.map((s) => (
            <section
              key={s.id}
              id={s.id}
              aria-labelledby={`settings-h-${s.id}`}
              data-testid={`settings-panel-${s.id}`}
              className="scroll-mt-16 space-y-3 border border-hair bg-surface p-[1.1rem_1.2rem]"
            >
              <div>
                <h2
                  id={`settings-h-${s.id}`}
                  className="font-mono text-xs uppercase tracking-wider text-ink"
                >
                  {s.label}
                </h2>
                <p className="mt-1 text-xs text-ink-mute">{SECTION_BLURB[s.id]}</p>
              </div>
              {body(s.id)}
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
