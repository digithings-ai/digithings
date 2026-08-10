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
 * the dress="glass-display" cut, which reproduces the shipped look exactly
 * (font-display 2xl title, relaxed body, accent Retry). The `.glass-card`
 * surface stays a call-site class so the app's motion-reveal hook keeps firing.
 */
export default function DbUnavailable() {
  return (
    <div className={`${SUBPAGE_MAX} py-12`}>
      <EmptyState
        variant="error"
        dress="glass-display"
        className="glass-card mx-auto max-w-md"
        title="Live data is temporarily unavailable"
        body={
          <>
            The dashboard can&rsquo;t reach its data right now. It&rsquo;ll reconnect
            automatically.
          </>
        }
        action={
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-5 inline-flex items-center rounded-lg border border-hair px-4 py-2 text-sm font-medium text-accent transition-colors hover:bg-ink/[0.06]"
          >
            Retry
          </button>
        }
      />
    </div>
  );
}
