'use client';

import { useEffect, useMemo, useState } from 'react';
import { EYEBROW, H1, LEDE, PAGE, PAGE_HEADER } from '@/components/layout-constants';
import { SettingsContent } from '@/components/settings-content';
import { ProfileTab } from '@/components/settings/profile-tab';
import { PipelineTab } from '@/components/settings/pipeline-tab';
import { KeysTab } from '@/components/settings/keys-tab';
import { BrokersTab } from '@/components/settings/brokers-tab';
import { NotifyTab } from '@/components/settings/notify-tab';
import { BillingTab } from '@/components/settings/billing-tab';
import { RemainingHopStatus } from '@/components/settings/remaining-hop-status';
import { subpageTabButtonClass, SubpageStickyTabBar } from '@/components/subpage-tab-bar';
import { FxHubAccount } from '@/components/settings/fx-hub-account';
import { useFxHubOnlyInvitee } from '@/lib/fx-hub-only';
import { useDashboard } from '@/lib/dashboard-context';
import { useAppShell } from '@/components/app-shell-context';
import { dataSourceHost } from '@/lib/data-source-host';
import { useAuth } from '@/lib/auth-context';
import { usePlanTier } from '@/lib/use-entitlement';
import {
  defaultSettingsTab,
  resolveSettingsTab,
  settingsTabsVisible,
  type SettingsTabId,
} from '@/lib/entitlements';
import type { SettingsApiOptions } from '@/lib/settings-api';

export default function SettingsPage() {
  const { data } = useDashboard();
  const { openCommandPalette } = useAppShell();
  const { session } = useAuth();
  const tier = usePlanTier();
  const { canFxHub, fxHubOnlyInvitee } = useFxHubOnlyInvitee();
  const tabs = useMemo(() => settingsTabsVisible(tier), [tier]);
  const visibleIds = useMemo(() => tabs.map((item) => item.id), [tabs]);
  const meta = data?.portfolio?.meta ?? null;
  // Start where the prerender started; the effect below adopts the URL on the
  // first post-hydration commit. Reading location here instead would hydrate a
  // tab strip whose highlight React never writes out — see TwelveXClient.
  const [tab, setTab] = useState<SettingsTabId>(() => defaultSettingsTab(tier));
  const [lastVersionId, setLastVersionId] = useState<string | null>(null);
  const activeTab = visibleIds.includes(tab) ? tab : defaultSettingsTab(tier);

  useEffect(() => {
    const applyLocation = () => {
      const next = resolveSettingsTab(
        window.location.search,
        window.location.hash,
        visibleIds,
        defaultSettingsTab(tier),
      );
      setTab(next);
    };
    applyLocation();
    window.addEventListener('hashchange', applyLocation);
    window.addEventListener('popstate', applyLocation);
    return () => {
      window.removeEventListener('hashchange', applyLocation);
      window.removeEventListener('popstate', applyLocation);
    };
  }, [tier, visibleIds]);

  const selectTab = (id: SettingsTabId) => {
    setTab(id);
    if (typeof window === 'undefined') return;
    const next = `#${id}`;
    if (window.location.hash !== next) {
      window.history.replaceState(null, '', next);
    }
  };

  const api: SettingsApiOptions | null = useMemo(() => {
    const token = session?.access_token;
    if (!token) return null;
    return { accessToken: token };
  }, [session?.access_token]);

  if (fxHubOnlyInvitee) {
    return (
      <div className={`${PAGE} space-y-6 py-6 md:py-8`}>
        <header className={PAGE_HEADER}>
          <p className={EYEBROW}>
            fx hub <span className="text-ink-mute">· account</span>
          </p>
          <h1 className={H1}>Your account.</h1>
          <p className={LEDE}>
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

  return (
    <div className={`${PAGE} space-y-6 py-6 md:py-8`}>
      <header className={PAGE_HEADER}>
        <p className={EYEBROW}>
          dashboard <span className="text-ink-mute">· settings</span>
        </p>
        <h1 className={H1}>The desk, not the product.</h1>
        <p className={LEDE}>
          Notifications and billing on every plan. Pipeline, keys, and brokers only appear when this
          workspace can use them.
        </p>
      </header>

      <SubpageStickyTabBar aria-label="Settings sections">
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            className={subpageTabButtonClass(activeTab === item.id)}
            onClick={() => selectTab(item.id)}
            data-testid={`settings-tab-${item.id}`}
          >
            {item.label}
          </button>
        ))}
      </SubpageStickyTabBar>

      <div className="max-w-2xl border border-hair bg-surface p-[1.1rem_1.2rem]" id={activeTab}>
        {activeTab === 'profile' ? (
          <ProfileTab
            api={api}
            lastVersionId={lastVersionId}
            onVersionSaved={setLastVersionId}
          />
        ) : null}
        {activeTab === 'pipeline' ? (
          <PipelineTab
            api={api}
            lastVersionId={lastVersionId}
            onVersionSaved={setLastVersionId}
          />
        ) : null}
        {activeTab === 'keys' ? <KeysTab api={api} /> : null}
        {activeTab === 'brokers' ? <BrokersTab api={api} /> : null}
        {activeTab === 'notifications' ? <NotifyTab api={api} /> : null}
        {activeTab === 'billing' ? <BillingTab api={api} /> : null}
        {activeTab === 'about' ? (
          <div className="space-y-5" data-testid="settings-about">
            <RemainingHopStatus api={api} />
            <SettingsContent
              variant="popover"
              lastRunDate={meta?.last_updated ?? null}
              lastRunAt={meta?.last_run_at ?? null}
              runType={meta?.latest_snapshot_run_type ?? null}
              version={process.env.NEXT_PUBLIC_DASHBOARD_VERSION ?? 'v0.1 · dev'}
              dataSourceHost={dataSourceHost()}
              onOpenPalette={openCommandPalette}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}
