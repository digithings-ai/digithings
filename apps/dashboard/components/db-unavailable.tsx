'use client';

import type { ReactNode } from 'react';
import { Button, EmptyState } from '@digithings/ui/ui';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import type { DbStatus } from '@/lib/dashboard-context';

/**
 * Standardized "database unavailable" gate card.
 *
 * Rendered in the shell's children slot (in place of the page) when the live
 * data backend is unconfigured or unreachable and the current route is not
 * allowlisted. It must say WHY (plan §6): a misconfigured deploy and a backend
 * outage are different operator problems and the previous single message
 * ("can't reach its data") conflated them. Visually matches the Today
 * error-state card via the promoted `@digithings/ui` EmptyState
 * (variant="error", dress="glass-display").
 *
 * #1548: the card is the promoted @digithings/ui EmptyState — variant="error"
 * (semantic; the glass dresses carry no glyph disc, so no down tint shows) in
 * the dress="glass-display" cut (API name; the surface is a tonal slab, not
 * glass). Title uses font-display (mono voice). The promoted EmptyState
 * carries its own tonal-slab box, so the retired `.dq-slab` layer was
 * redundant; the reveal hook is now the `data-reveal` attribute.
 *
 * Copy fix (full-UI-suite critique, P2): this used to say "It'll reconnect
 * automatically", but dbStatus (lib/dashboard-context.tsx) is set once from a
 * single fetch on mount and never polled or retried in the background — the
 * claim was false, and it contradicted the only visible recovery affordance
 * (a manual Retry). Softened to describe what actually happens: reload, or
 * check back.
 */

const COPY: Record<Exclude<DbStatus, 'ok'>, { title: string; body: ReactNode }> = {
  unconfigured: {
    title: 'Live data is not connected in this build',
    body: (
      <>
        This deployment has no live data backend configured, so live figures cannot load. Static
        surfaces — Pipeline and Settings — stay available.
      </>
    ),
  },
  unreachable: {
    title: 'Live data is temporarily unavailable',
    body: (
      <>
        The dashboard is configured but cannot reach its data right now. Try reloading, or check
        back shortly. Static surfaces — Pipeline and Settings — stay available.
      </>
    ),
  },
};

export default function DbUnavailable({ status }: { status: DbStatus }) {
  const { title, body } = COPY[status === 'ok' ? 'unreachable' : status];
  return (
    <div className={`${SUBPAGE_MAX} py-12`} data-testid="db-unavailable" data-db-status={status}>
      <EmptyState
        variant="error"
        dress="glass-display"
        className="mx-auto max-w-md"
        data-reveal
        title={title}
        body={body}
        action={
          <Button
            type="button"
            variant="outline"
            onClick={() => window.location.reload()}
            className="mt-5 h-auto border-hair px-4 py-2 text-sm text-accent"
          >
            Retry
          </Button>
        }
      />
    </div>
  );
}
