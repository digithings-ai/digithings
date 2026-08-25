'use client';

import Link from 'next/link';
import { periodInspectabilityState } from '@/lib/house-identity';

/**
 * Period inspectability surface (#2643).
 *
 * Raw `olympus_accounting_*` rows are service_role-only (Track A privacy).
 * This panel states that typed gap and points at public tearsheet metrics —
 * never fabricates period equity / contribution rows.
 */
export default function PeriodInspectPanel() {
  const state = periodInspectabilityState();

  return (
    <section data-testid="period-inspect-panel" className="space-y-4">
      <div>
        <h1 className="font-display text-xl font-normal tracking-tight text-ink">Period</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-soft">
          Reconciled EOD accounting periods are product — when the browser can read them. Today the
          anon olympus client cannot SELECT <code className="font-mono text-[11px]">olympus_accounting_*</code>{' '}
          (service_role only).
        </p>
      </div>

      <div
        role="status"
        className="rounded-lg border border-hair bg-term-bg/50 px-4 py-3 text-sm text-ink-soft"
        data-period-state={state}
      >
        <p className="font-medium text-ink">Typed gap — private accounting</p>
        <p className="mt-1">
          Period finalizer rows stay behind the Track A privacy boundary. This chrome does not invent
          opening/closing equity, contributions, or EOD holdings from private tables.
        </p>
        <p className="mt-2 text-xs text-ink-mute">
          Public substitute: persisted portfolio metrics on the Tearsheet (NAV / returns as-of), not
          a period ledger dump.
        </p>
      </div>

      <ul className="space-y-2 text-sm">
        <li>
          <Link href="/portfolio/performance" className="text-accent hover:underline">
            Open Tearsheet (public metrics) →
          </Link>
        </li>
        <li>
          <Link href="/portfolio/ledger" className="text-accent hover:underline">
            Open Ledger (position events) →
          </Link>
        </li>
      </ul>
    </section>
  );
}
