'use client';

import Link from 'next/link';
import { Stat } from '@digithings/ui/ui';
import { AsOfBadge } from '@/components/shared/as-of-badge';
import { formatRunStamp } from '@/lib/settings-runs';
import type { SettingsApiOptions } from '@/lib/settings-api';
import { RemainingHopStatus } from './remaining-hop-status';

export type SystemSectionProps = {
  api: SettingsApiOptions | null;
  lastRunDate: string | null;
  lastRunAt: string | null;
  runType: 'baseline' | 'delta' | null;
  version: string;
  dataSourceHost: string | null;
};

/** Last run, build, data source and the remaining-hop proof checklist. */
export function SystemSection({
  api,
  lastRunDate,
  lastRunAt,
  runType,
  version,
  dataSourceHost,
}: SystemSectionProps) {
  return (
    <div className="space-y-5" data-testid="settings-about">
      <div className="grid gap-2 sm:grid-cols-3">
        <Stat
          label="Last run"
          value={lastRunDate ? formatRunStamp(lastRunDate, lastRunAt) : null}
          hint={
            lastRunDate ? (
              <span className="inline-flex items-center gap-2">
                <AsOfBadge date={lastRunDate} createdAt={lastRunAt} />
                {runType ? <span>{runType}</span> : null}
              </span>
            ) : (
              'No pipeline runs yet'
            )
          }
          data-testid="system-last-run"
        />
        <Stat label="Build" value={version} data-testid="system-build" />
        <Stat
          label="Data source"
          value={dataSourceHost ?? 'not configured'}
          data-testid="system-data-source"
        />
      </div>
      <Link
        href="/pipeline"
        className="inline-block font-mono text-xs text-accent underline-offset-2 hover:underline"
        data-testid="system-pipeline-link"
      >
        Open pipeline view
      </Link>
      <RemainingHopStatus api={api} />
    </div>
  );
}
