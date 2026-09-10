'use client';

import { EmptyState } from '@digithings/web';
import { SUBPAGE_MAX } from '@/components/layout-constants';

/**
 * Standardized "database unavailable" gate card.
 *
 * Rendered in the shell's children slot (in place of the page) when the live
 * data backend is unconfigured or unreachable and the current route is not
 * allowlisted. Visually matches the Today error-state card. Deliberately says
 * nothing about env vars / anon keys — the owner sees a calm, reassuring state,
 * not an operator config message.
 *
 * #1548: the card is the promoted @digithings/web EmptyState — variant="error"
 * (semantic; the glass dresses carry no glyph disc, so no down tint shows) in
 * the dress="glass-display" cut (API name; the surface is a tonal slab, not
 * glass). Title uses font-display (mono voice). The `.oly-slab` surface is
 * the call-site class so MotionLayer's reveal hook keeps firing.
 *
 * Copy fix (full-UI-suite critique, P2): this used to say "It'll reconnect
 * automatically", but dbStatus (lib/dashboard-context.tsx) is set once from a
 * single fetch on mount and never polled or retried in the background — the
 * claim was false, and it contradicted the only visible recovery affordance
 * (a manual Retry). Softened to describe what actually happens: reload, or
 * check back.
 */
export default function DbUnavailable() {
  return (
    <div className={`${SUBPAGE_MAX} py-12`}>
      <EmptyState
        variant="error"
        dress="glass-display"
        className="oly-slab mx-auto max-w-md"
        title="Live data is temporarily unavailable"
        body={
          <>
            The dashboard can&rsquo;t reach its data right now. Try reloading, or check back
            shortly.
          </>
        }
        action={
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-5 inline-flex items-center border border-hair px-4 py-2 text-sm font-medium text-accent transition-colors hover:bg-ink/[0.06]"
          >
            Retry
          </button>
        }
      />
    </div>
  );
}
