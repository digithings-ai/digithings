'use client';

import Link from 'next/link';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { Button } from '@digithings/ui/ui';
import { useAppShell } from '@/components/app-shell-context';
import { AsOfBadge } from '@/components/shared/as-of-badge';
import { useDashboard } from '@/lib/dashboard-context';
import { dataSourceHost } from '@/lib/data-source-host';
import { useFxHubOnlyInvitee } from '@/lib/fx-hub-only';

const BUILD = process.env.NEXT_PUBLIC_DASHBOARD_VERSION ?? 'v0.1 · dev';

/**
 * Pinned status block: last pipeline run, DB reachability, data source, build.
 * Carries the old settings popover's Status/About rows so they're always in view.
 * The dot uses accent (ok) or warn (DB down) — never up/down, which are P&L colours.
 */
export default function SidebarStatus() {
  const { statusOpen, toggleStatus } = useAppShell();
  const { data, dbStatus } = useDashboard();
  const { fxHubOnlyInvitee } = useFxHubOnlyInvitee();
  const meta = data?.portfolio?.meta ?? null;
  const dbOk = dbStatus === 'ok';
  const dot = dbOk ? 'bg-accent' : 'bg-warn';

  const runType = meta?.latest_snapshot_run_type;
  const lastRun = meta?.last_run_at ?? meta?.last_updated ?? null;
  const host = dataSourceHost();

  return (
    <>
      <div
        role="img"
        title={dbOk ? 'Backend ok' : 'Backend unavailable'}
        aria-label={dbOk ? 'Data backend ok' : 'Data backend unavailable'}
        className="hidden justify-center border-t border-hair py-2 group-data-[collapsible=icon]:flex"
      >
        <span className={`size-2 ${dot}`} />
      </div>
    <section
      aria-label="Status"
      data-testid="sidebar-status"
      className="shrink-0 border-t border-hair px-2 py-1.5 font-mono text-[0.68rem] text-ink-mute group-data-[collapsible=icon]:hidden"
    >
      <div className="flex items-center justify-between">
        <span className="inline-flex items-center gap-2">
          <span className={`size-2 ${dot}`} aria-hidden />
          <span className="uppercase tracking-[0.12em]">Status</span>
        </span>
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          aria-expanded={statusOpen}
          aria-label={statusOpen ? 'Hide status details' : 'Show status details'}
          onClick={toggleStatus}
        >
          {statusOpen ? <ChevronDown /> : <ChevronUp />}
        </Button>
      </div>
      {statusOpen ? (
        <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 pb-1">
          {fxHubOnlyInvitee ? null : (
            <>
              <dt>Run</dt>
              <dd className="m-0 truncate text-ink-soft">
                {lastRun ? (
                  <>
                    {runType ? `${runType} · ` : ''}
                    <AsOfBadge date={meta?.last_updated ?? lastRun.slice(0, 10)} createdAt={meta?.last_run_at ?? null} />
                  </>
                ) : (
                  'No pipeline runs yet'
                )}
              </dd>
            </>
          )}
          <dt>DB</dt>
          <dd className="m-0 truncate text-ink-soft">
            {dbOk ? (
              'ok'
            ) : (
              <Link href="/pipeline" className="text-warn underline">
                unavailable
              </Link>
            )}
          </dd>
          {fxHubOnlyInvitee ? null : (
            <>
              <dt>Source</dt>
              <dd className="m-0 truncate text-ink-soft" title={host ?? undefined}>
                {host ?? 'not configured'}
              </dd>
            </>
          )}
          <dt>Build</dt>
          <dd className="m-0 truncate text-ink-soft">{BUILD}</dd>
        </dl>
      ) : null}
    </section>
    </>
  );
}
