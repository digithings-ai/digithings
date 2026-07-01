'use client';

import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';

/**
 * Standardized "database unavailable" gate card.
 *
 * Rendered in the shell's children slot (in place of the page) when the live
 * data backend is unconfigured or unreachable and the current route is not
 * allowlisted. Visually matches the Today error-state card. Deliberately says
 * nothing about env vars / anon keys — the owner sees a calm, reassuring state,
 * not an operator config message.
 */
export default function DbUnavailable() {
  return (
    <div className={`${SUBPAGE_MAX} py-12`}>
      <div className="glass-card mx-auto max-w-md px-6 py-8 text-center">
        <h2 className="font-display text-2xl tracking-tight text-text-primary">
          Live data is temporarily unavailable
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-text-muted">
          The dashboard can&rsquo;t reach its data right now. It&rsquo;ll reconnect automatically.
        </p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="mt-5 inline-flex items-center rounded-lg border border-border-subtle px-4 py-2 text-sm font-medium text-accent transition-colors hover:bg-white/[0.06]"
        >
          Retry
        </button>
      </div>
    </div>
  );
}
