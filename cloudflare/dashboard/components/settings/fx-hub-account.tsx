'use client';

import { LogOut } from 'lucide-react';
import { useAuth } from '@/lib/auth-context';

/**
 * The whole account surface a 12x FX Hub invitee gets: their email, the
 * invite-redeemed fact, and sign-out. No DigiQuant settings (notifications,
 * billing, pipeline, keys, brokers) apply to a product-grant-only account
 * (#4142).
 */
export function FxHubAccount({ fxHubGranted }: { fxHubGranted: boolean }) {
  const { user, signOut } = useAuth();
  const email = user?.email ?? null;
  return (
    <div
      className="border border-hair bg-term-bg/50 divide-y divide-hair"
      data-testid="fx-hub-account"
    >
      <div className="flex items-center justify-between gap-2 px-3 py-2.5">
        <span className="text-xs text-ink-soft">Email</span>
        <span
          className="font-mono text-[11px] text-ink-mute truncate max-w-[60%]"
          title={email ?? undefined}
        >
          {email ?? 'not signed in'}
        </span>
      </div>
      <div className="flex items-center justify-between gap-2 px-3 py-2.5">
        <span className="text-xs text-ink-soft">FX Hub access</span>
        <span className="text-xs text-ink-mute">
          {fxHubGranted ? 'Invite redeemed — active' : 'No FX Hub grant on this account'}
        </span>
      </div>
      <button
        type="button"
        onClick={() => {
          void signOut();
        }}
        className="flex w-full items-center gap-2 px-3 py-2.5 text-xs font-medium text-ink-soft hover:bg-ink/[0.04] hover:text-ink transition-colors"
        data-testid="fx-hub-sign-out"
      >
        <LogOut size={14} className="shrink-0 text-ink-mute" aria-hidden />
        <span>Sign out</span>
      </button>
    </div>
  );
}
