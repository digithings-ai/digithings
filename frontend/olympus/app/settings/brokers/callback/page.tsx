'use client';

import { useEffect, useState } from 'react';
import {
  ALPACA_OAUTH_STATE_KEY,
  connectBrokerOAuth,
  type SettingsApiOptions,
} from '@/lib/settings-api';
import { useAuth } from '@/lib/auth-context';
import { SUBPAGE_MAX } from '@/components/layout-constants';

/**
 * Alpaca OAuth callback — posts the authorization code to the settings Edge
 * Function. The client secret never enters this page.
 */
export default function AlpacaOAuthCallbackPage() {
  const { session } = useAuth();
  const [status, setStatus] = useState<'working' | 'ok' | 'error'>('working');
  const [detail, setDetail] = useState('Completing Alpaca paper connect…');

  useEffect(() => {
    let cancelled = false;

    async function finish() {
      const params = new URLSearchParams(window.location.search);
      const code = params.get('code');
      const state = params.get('state');
      const stored = sessionStorage.getItem(ALPACA_OAUTH_STATE_KEY);
      sessionStorage.removeItem(ALPACA_OAUTH_STATE_KEY);

      if (!code || !state || !stored || state !== stored) {
        if (!cancelled) {
          setStatus('error');
          setDetail('OAuth state mismatch — return to Brokers and try again.');
        }
        return;
      }
      const token = session?.access_token;
      if (!token) {
        if (!cancelled) {
          setStatus('error');
          setDetail('Sign in required to finish broker connect.');
        }
        return;
      }

      const api: SettingsApiOptions = { accessToken: token };
      const redirectUri = `${window.location.origin}${process.env.NEXT_PUBLIC_BASE_PATH ?? ''}/settings/brokers/callback`;

      try {
        const row = await connectBrokerOAuth(api, {
          broker: 'alpaca',
          code,
          redirect_uri: redirectUri,
        });
        if (cancelled) return;
        setStatus('ok');
        setDetail(
          `Connected ${row.broker} (${row.env}) — fingerprint ${row.fingerprint}. Returning to Brokers…`,
        );
        window.setTimeout(() => {
          window.location.assign(`${process.env.NEXT_PUBLIC_BASE_PATH ?? ''}/settings`);
        }, 1200);
      } catch (err: unknown) {
        if (cancelled) return;
        setStatus('error');
        setDetail(err instanceof Error ? err.message : 'OAuth exchange failed.');
      }
    }

    void finish();

    return () => {
      cancelled = true;
    };
  }, [session?.access_token]);

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
