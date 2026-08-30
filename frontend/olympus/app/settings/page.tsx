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
import { RemainingHopStatus } from '@/components/settings/remaining-hop-status';
import {
  BrokerStatusSurface,
  OverlayProfileSurface,
} from '@/components/tier/custom-workspace-surfaces';
import { subpageTabButtonClass, SubpageStickyTabBar } from '@/components/subpage-tab-bar';
import { useDashboard } from '@/lib/dashboard-context';
import { useAppShell } from '@/components/app-shell-context';
import { dataSourceHost } from '@/lib/data-source-host';
import { useAuth } from '@/lib/auth-context';
import type { SettingsApiOptions } from '@/lib/settings-api';

type SettingsTab =
  | 'profile'
  | 'pipeline'
  | 'keys'
  | 'brokers'
  | 'notifications'
  | 'billing'
  | 'about';

const TABS: { id: SettingsTab; label: string }[] = [
  { id: 'profile', label: 'Profile' },
  { id: 'pipeline', label: 'Pipeline' },
  { id: 'keys', label: 'Keys' },
  { id: 'brokers', label: 'Brokers' },
  { id: 'notifications', label: 'Notifications' },
  { id: 'billing', label: 'Billing' },
  { id: 'about', label: 'About' },
];

export default function SettingsPage() {
  const { data } = useDashboard();
  const { openCommandPalette } = useAppShell();
  const { session } = useAuth();
  const meta = data?.portfolio?.meta ?? null;
  const [tab, setTab] = useState<SettingsTab>('profile');
  const [lastVersionId, setLastVersionId] = useState<string | null>(null);

  const api: SettingsApiOptions | null = useMemo(() => {
    const token = session?.access_token;
    if (!token) return null;
    return { accessToken: token };
  }, [session?.access_token]);

  return (
    <div className={`${SUBPAGE_MAX} py-6 md:py-8 space-y-6`}>
      <h1 className="font-display text-3xl tracking-tight text-ink">Settings</h1>

      <SubpageStickyTabBar aria-label="Settings sections">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={subpageTabButtonClass(tab === t.id)}
            onClick={() => setTab(t.id)}
            data-testid={`settings-tab-${t.id}`}
          >
            {t.label}
          </button>
        ))}
      </SubpageStickyTabBar>

      <div className="max-w-2xl">
        {tab === 'profile' ? (
          <OverlayProfileSurface>
            <ProfileTab
              api={api}
              lastVersionId={lastVersionId}
              onVersionSaved={setLastVersionId}
            />
          </OverlayProfileSurface>
        ) : null}
        {tab === 'pipeline' ? (
          <OverlayProfileSurface>
            <PipelineTab
              api={api}
              lastVersionId={lastVersionId}
              onVersionSaved={setLastVersionId}
            />
          </OverlayProfileSurface>
        ) : null}
        {tab === 'keys' ? (
          <OverlayProfileSurface>
            <KeysTab api={api} />
          </OverlayProfileSurface>
        ) : null}
        {tab === 'brokers' ? (
          <BrokerStatusSurface>
            <BrokersTab api={api} />
          </BrokerStatusSurface>
        ) : null}
        {tab === 'notifications' ? <NotifyTab api={api} /> : null}
        {tab === 'billing' ? (
          <div id="billing">
            <BillingTab api={api} />
          </div>
        ) : null}
        {tab === 'about' ? (
          <div className="oly-slab p-6 max-w-lg space-y-5" data-testid="settings-about">
            <RemainingHopStatus api={api} />
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
