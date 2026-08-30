'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  ALPACA_OAUTH_STATE_KEY,
  buildAlpacaAuthorizeUrl,
  connectBrokerApiKey,
  listBrokers,
  publicAlpacaClientId,
  revokeBroker,
  type BrokerConnectionView,
  type SettingsApiOptions,
} from '@/lib/settings-api';

export type BrokersTabProps = {
  api: SettingsApiOptions | null;
  listFn?: typeof listBrokers;
  connectFn?: typeof connectBrokerApiKey;
  revokeFn?: typeof revokeBroker;
  /** Test seam: capture authorize URL instead of navigating. */
  onAuthorizeNavigate?: (url: string) => void;
};

/** Display-safe fields only — never render secret material. */
const SAFE_KEYS = new Set([
  'id',
  'broker',
  'env',
  'auth_kind',
  'fingerprint',
  'status',
  'last_used_at',
  'created_at',
  'revoked_at',
]);

export function sanitizeConnection(row: BrokerConnectionView): BrokerConnectionView {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(row)) {
    if (SAFE_KEYS.has(k)) out[k] = v;
  }
  return out as BrokerConnectionView;
}

export function BrokersTab({
  api,
  listFn = listBrokers,
  connectFn = connectBrokerApiKey,
  revokeFn = revokeBroker,
  onAuthorizeNavigate,
}: BrokersTabProps) {
  const [rows, setRows] = useState<BrokerConnectionView[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [broker, setBroker] = useState<'alpaca' | 'ibkr'>('alpaca');
  const [keyId, setKeyId] = useState('');
  const [secret, setSecret] = useState('');
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!api) return;
    try {
      const list = await listFn(api);
      setRows(list.map(sanitizeConnection));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load connections');
    }
  }, [api, listFn]);

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect -- load connections after mount */
    void refresh();
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [refresh]);

  async function onConnectApiKey() {
    if (!api) {
      setError('Sign in to connect a broker.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const row = await connectFn(api, {
        broker,
        key_id: keyId,
        secret,
      });
      // Clear plaintext immediately — never retain in component state after save.
      setKeyId('');
      setSecret('');
      setRows((prev) => [sanitizeConnection(row), ...prev]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Connect failed');
    } finally {
      setBusy(false);
    }
  }

  function onAlpacaOAuth() {
    const clientId = publicAlpacaClientId();
    if (!clientId) {
      setError('Alpaca OAuth client id is not configured.');
      return;
    }
    const state =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `st_${Date.now()}`;
    try {
      sessionStorage.setItem(ALPACA_OAUTH_STATE_KEY, state);
    } catch {
      setError('Unable to store OAuth state (sessionStorage).');
      return;
    }
    const redirectUri = `${window.location.origin}${process.env.NEXT_PUBLIC_BASE_PATH ?? ''}/settings/brokers/callback`;
    const url = buildAlpacaAuthorizeUrl({ clientId, redirectUri, state });
    if (onAuthorizeNavigate) {
      onAuthorizeNavigate(url);
      return;
    }
    window.location.assign(url);
  }

  async function onRevoke(id: string) {
    if (!api) return;
    setBusy(true);
    try {
      const row = await revokeFn(api, { connection_id: id });
      setRows((prev) =>
        prev.map((r) => (r.id === id ? sanitizeConnection(row) : r)),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Revoke failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5" data-testid="settings-brokers-tab">
      <div>
        <h2 className="font-display text-xl text-ink tracking-tight">Brokers</h2>
        <p className="mt-1 text-sm text-ink-soft">
          Paper connections only. After save we show fingerprint, venue, and status — never the
          credential itself.
        </p>
      </div>

      <div className="space-y-3 rounded-lg border border-hair bg-term-bg/40 px-4 py-3">
        <p className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
          Alpaca paper — Connect with Alpaca
        </p>
        <button
          type="button"
          onClick={onAlpacaOAuth}
          className="rounded-lg border border-accent/40 bg-accent/15 px-3 py-1.5 text-sm font-medium text-accent"
          data-testid="alpaca-oauth-connect"
        >
          Connect Alpaca (paper)
        </button>
      </div>

      <div className="space-y-3 rounded-lg border border-hair bg-term-bg/40 px-4 py-3">
        <p className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
          API key entry
        </p>
        <div className="flex flex-wrap gap-2">
          <select
            className="rounded-lg border border-hair bg-term-bg/50 px-3 py-2 text-sm text-ink"
            value={broker}
            onChange={(e) => setBroker(e.target.value as 'alpaca' | 'ibkr')}
            data-testid="broker-select"
          >
            <option value="alpaca">Alpaca</option>
            <option value="ibkr">IBKR (beta)</option>
          </select>
        </div>
        {broker === 'ibkr' ? (
          <p className="text-xs text-warn" data-testid="ibkr-beta-note">
            IBKR connect is beta / self-service for paper and development. Product OAuth 1.0a
            waits on vendor onboarding — prefer a dedicated API username so sync never competes
            with your interactive session.
          </p>
        ) : null}
        <input
          className="w-full rounded-lg border border-hair bg-term-bg/50 px-3 py-2 text-sm font-mono text-ink"
          placeholder="Key id"
          value={keyId}
          onChange={(e) => setKeyId(e.target.value)}
          autoComplete="off"
          data-testid="broker-key-id"
        />
        <input
          type="password"
          className="w-full rounded-lg border border-hair bg-term-bg/50 px-3 py-2 text-sm font-mono text-ink"
          placeholder="Secret"
          value={secret}
          onChange={(e) => setSecret(e.target.value)}
          autoComplete="off"
          data-testid="broker-secret"
        />
        <button
          type="button"
          disabled={busy || !keyId || !secret}
          onClick={() => void onConnectApiKey()}
          className="rounded-lg border border-hair px-3 py-1.5 text-sm font-medium text-ink-soft hover:bg-ink/[0.04] disabled:opacity-50"
          data-testid="broker-api-key-connect"
        >
          Save API key (paper)
        </button>
      </div>

      {error ? (
        <p className="text-sm text-down" role="alert" data-testid="brokers-error">
          {error}
        </p>
      ) : null}

      <div className="space-y-2" data-testid="brokers-list">
        <p className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
          Connections
        </p>
        {rows.length === 0 ? (
          <p className="text-sm text-ink-mute">No broker connections yet.</p>
        ) : (
          <ul className="divide-y divide-hair rounded-lg border border-hair">
            {rows.map((row) => (
              <li
                key={row.id}
                className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm"
                data-testid="broker-row"
              >
                <div className="space-y-0.5">
                  <p className="font-mono text-ink">
                    {row.broker} · {row.env} · {row.fingerprint}
                  </p>
                  <p className="text-xs text-ink-mute">
                    {row.status}
                    {row.last_used_at ? ` · last used ${row.last_used_at}` : ''}
                  </p>
                </div>
                {row.status === 'active' ? (
                  <button
                    type="button"
                    className="text-xs text-ink-soft underline-offset-2 hover:underline"
                    onClick={() => void onRevoke(row.id)}
                    data-testid="broker-revoke"
                  >
                    Revoke
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
