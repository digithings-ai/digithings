'use client';

import { useMemo, useState } from 'react';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import { SettingsContent } from '@/components/settings-content';
import { ProfileTab } from '@/components/settings/profile-tab';
import { PipelineTab } from '@/components/settings/pipeline-tab';
import { KeysTab } from '@/components/settings/keys-tab';
import { BrokersTab } from '@/components/settings/brokers-tab';
import { NotifyTab } from '@/components/settings/notify-tab';
import { BillingTab } from '@/components/settings/billing-tab';
import { subpageTabButtonClass, SubpageStickyTabBar } from '@/components/subpage-tab-bar';
import { useDashboard } from '@/lib/dashboard-context';
import { useAppShell } from '@/components/app-shell-context';
import { dataSourceHost } from '@/lib/data-source-host';
import { useAuth } from '@/lib/auth-context';
import { usePlanTier } from '@/lib/use-entitlement';
import {
  defaultSettingsTab,
  settingsTabsVisible,
  type SettingsTabId,
} from '@/lib/entitlements';
import type { SettingsApiOptions } from '@/lib/settings-api';

export default function SettingsPage() {
  const { data } = useDashboard();
  const { openCommandPalette } = useAppShell();
  const { session } = useAuth();
  const tier = usePlanTier();
  const tabs = useMemo(() => settingsTabsVisible(tier), [tier]);
  const meta = data?.portfolio?.meta ?? null;
  const [tab, setTab] = useState<SettingsTabId>(() => defaultSettingsTab(tier));
  const [lastVersionId, setLastVersionId] = useState<string | null>(null);
  const activeTab = tabs.some((item) => item.id === tab) ? tab : defaultSettingsTab(tier);

  const api: SettingsApiOptions | null = useMemo(() => {
    const token = session?.access_token;
    if (!token) return null;
    return { accessToken: token };
  }, [session?.access_token]);

  return (
    <div className={`${SUBPAGE_MAX} py-6 md:py-8 space-y-6`}>
      <header className="space-y-2">
        <p className="acct-settings-kicker">
          olympus <span className="text-ink-mute">· settings</span>
        </p>
        <h1 className="font-display text-3xl tracking-tight text-ink">The desk, not the product.</h1>
        <p className="acct-settings-copy">
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
            onClick={() => setTab(item.id)}
            data-testid={`settings-tab-${item.id}`}
          >
            {item.label}
          </button>
        ))}
      </SubpageStickyTabBar>

      <div className="acct-settings-panel max-w-2xl">
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
        {activeTab === 'billing' ? (
          <div id="billing">
            <BillingTab api={api} />
          </div>
        ) : null}
        {activeTab === 'about' ? (
          <div data-testid="settings-about">
            <SettingsContent
              variant="popover"
              lastRunDate={meta?.last_updated ?? null}
              lastRunAt={meta?.last_run_at ?? null}
              runType={meta?.latest_snapshot_run_type ?? null}
              version={process.env.NEXT_PUBLIC_OLYMPUS_VERSION ?? 'v0.1 · dev'}
              dataSourceHost={dataSourceHost()}
              onOpenPalette={openCommandPalette}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}
