'use client';

import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';
import { SettingsContent } from '@/components/settings-content';
import { useDashboard } from '@/lib/dashboard-context';
import { useAppShell } from '@/components/app-shell-context';
import { dataSourceHost } from '@/lib/data-source-host';

export default function SettingsPage() {
  const { data } = useDashboard();
  const { openCommandPalette } = useAppShell();
  const meta = data?.portfolio?.meta ?? null;
  return (
    <div className={`${SUBPAGE_MAX} py-6 md:py-8`}>
      <h1 className="font-display text-3xl tracking-tight text-ink mb-6">Settings</h1>
      <div className="glass-card p-6 max-w-lg">
        <SettingsContent
          variant="page"
          lastRunDate={meta?.last_updated ?? null}
          lastRunAt={meta?.last_run_at ?? null}
          runType={meta?.latest_snapshot_run_type ?? null}
          version={process.env.NEXT_PUBLIC_OLYMPUS_VERSION ?? 'v0.1 · dev'}
          dataSourceHost={dataSourceHost()}
          onOpenPalette={openCommandPalette}
        />
      </div>
    </div>
  );
}
