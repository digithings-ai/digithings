'use client';

import { useEffect, useRef, useState } from 'react';
import {
  ALPACA_OAUTH_STATE_KEY,
  alpacaOAuthRedirectUri,
  resolveAlpacaOAuthCallback,
  settingsHomeHref,
} from '@/lib/settings/alpaca-oauth';
import {
  connectBrokerOAuth,
  type SettingsApiOptions,
} from '@/lib/settings-api';
import { useAuth } from '@/lib/auth-context';
import { SUBPAGE_MAX } from '@/components/layout-constants';

/**
 * Alpaca OAuth callback — posts the authorization code to the settings Edge
 * Function. The client secret never enters this page.
 *
 * Auth hydration: wait until `loading === false` before reading/removing the
 * sessionStorage nonce. Consume the nonce ONLY after a successful exchange.
 */
export default function AlpacaOAuthCallbackPage() {
  const { session, loading } = useAuth();
  const [status, setStatus] = useState<'working' | 'ok' | 'error'>('working');
  const [detail, setDetail] = useState('Completing Alpaca paper connect…');
  const started = useRef(false);

  useEffect(() => {
    if (loading) return;
    if (started.current) return;

    let cancelled = false;

    async function finish() {
      const stored = sessionStorage.getItem(ALPACA_OAUTH_STATE_KEY);
      const phase = resolveAlpacaOAuthCallback({
        loading: false,
        accessToken: session?.access_token,
        search: window.location.search,
        storedState: stored,
        origin: window.location.origin,
      });

      if (phase.kind === 'wait_auth') return;

      if (phase.kind === 'error') {
        // Do not remove the nonce on mismatch/sign-in failure so a later
        // hydration with a session can still succeed if this was a false start.
        // (State mismatch leaves the nonce for a fresh Brokers connect.)
        if (!cancelled) {
          setStatus('error');
          setDetail(phase.message);
        }
        return;
      }

      started.current = true;
      const api: SettingsApiOptions = { accessToken: session!.access_token! };
      const redirectUri = alpacaOAuthRedirectUri(window.location.origin);

      try {
        const row = await connectBrokerOAuth(api, {
          broker: 'alpaca',
          code: phase.code,
          redirect_uri: redirectUri,
        });
        // Consume nonce only after successful exchange.
        sessionStorage.removeItem(ALPACA_OAUTH_STATE_KEY);
        if (cancelled) return;
        setStatus('ok');
        setDetail(
          `Connected ${row.broker} (${row.env}) — fingerprint ${row.fingerprint}. Returning to Brokers…`,
        );
        window.setTimeout(() => {
          window.location.assign(settingsHomeHref());
        }, 1200);
      } catch (err: unknown) {
        // Leave nonce in place so the user can retry from Brokers (fresh state).
        if (cancelled) return;
        setStatus('error');
        setDetail(err instanceof Error ? err.message : 'OAuth exchange failed.');
      }
    }

    void finish();

    return () => {
      cancelled = true;
    };
  }, [loading, session]);

  return (
    <div className={`${SUBPAGE_MAX} py-10`} data-testid="alpaca-oauth-callback">
      <h1 className="font-display text-2xl text-ink tracking-tight">Broker connect</h1>
      <p
        className={`mt-3 text-sm ${status === 'error' ? 'text-down' : 'text-ink-soft'}`}
        role="status"
      >
        {detail}
      </p>
    </div>
  );
}
