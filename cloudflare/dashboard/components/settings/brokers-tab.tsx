'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  ALPACA_OAUTH_STATE_KEY,
  alpacaOAuthRedirectUri,
  buildAlpacaAuthorizeUrl,
  resolveAlpacaOauthClientId,
} from '@/lib/settings/alpaca-oauth';
import {
  connectBrokerApiKey,
  getAppUrls,
  getFills,
  listBrokers,
  revokeBroker,
  type BrokerConnectionView,
  type FillView,
  type SettingsApiOptions,
} from '@/lib/settings-api';
import {
  SETTINGS_LOAD_ERROR_MESSAGE,
  SettingsLoadError,
} from './settings-load-error';
import {
  Alert,
  AlertDescription,
  Button,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@digithings/web/ui';

export type BrokersTabProps = {
  api: SettingsApiOptions | null;
  listFn?: typeof listBrokers;
  connectFn?: typeof connectBrokerApiKey;
  revokeFn?: typeof revokeBroker;
  fillsFn?: typeof getFills;
  /** Test seam: GET /app-urls (public Alpaca client id). */
  appUrlsFn?: typeof getAppUrls;
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
  fillsFn = getFills,
  appUrlsFn = getAppUrls,
  onAuthorizeNavigate,
}: BrokersTabProps) {
  const [rows, setRows] = useState<BrokerConnectionView[]>([]);
  const [fills, setFills] = useState<FillView[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [broker, setBroker] = useState<'alpaca' | 'ibkr'>('alpaca');
  const [keyId, setKeyId] = useState('');
  const [secret, setSecret] = useState('');
  const [busy, setBusy] = useState(false);
  const [oauthClientId, setOauthClientId] = useState('');

  const refresh = useCallback(async () => {
    if (!api) return;
    try {
      const list = await listFn(api);
      setRows(list.map(sanitizeConnection));
      try {
        setFills(await fillsFn(api));
      } catch {
        setFills([]);
      }
      try {
        const urls = await appUrlsFn(api);
        setOauthClientId(urls.alpaca_oauth_client_id ?? '');
      } catch {
        setOauthClientId('');
      }
      setError(null);
      setLoadError(null);
    } catch {
      setLoadError(SETTINGS_LOAD_ERROR_MESSAGE);
    }
  }, [api, listFn, fillsFn, appUrlsFn]);

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
    const clientId = resolveAlpacaOauthClientId(oauthClientId);
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
    const redirectUri = alpacaOAuthRedirectUri(window.location.origin);
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

      <div className="space-y-3 border border-hair bg-term-bg/40 px-4 py-3">
        <p className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
          Alpaca paper — Connect with Alpaca
        </p>
        <Button
          type="button"
          onClick={onAlpacaOAuth}
          className="h-auto px-3 py-1.5 text-sm"
          data-testid="alpaca-oauth-connect"
        >
          Connect Alpaca (paper)
        </Button>
      </div>

      <div className="space-y-3 border border-hair bg-term-bg/40 px-4 py-3">
        <p className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
          API key entry
        </p>
        <div className="flex flex-wrap gap-2">
          <Select
            value={broker}
            onValueChange={(next) => {
              if (next === 'alpaca' || next === 'ibkr') setBroker(next);
            }}
          >
            <SelectTrigger
              className="h-auto border-hair bg-term-bg/50 px-3 py-2 text-sm text-ink"
              data-testid="broker-select"
            >
              <SelectValue>
                {(value) => (value === 'ibkr' ? 'IBKR (beta)' : 'Alpaca')}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="alpaca">Alpaca</SelectItem>
              <SelectItem value="ibkr">IBKR (beta)</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {broker === 'ibkr' ? (
          <p className="text-xs text-warn" data-testid="ibkr-beta-note">
            IBKR connect is beta / self-service for paper and development. Product OAuth 1.0a
            waits on vendor onboarding — prefer a dedicated API username so sync never competes
            with your interactive session.
          </p>
        ) : null}
        <Input
          className="h-auto w-full border-hair bg-term-bg/50 px-3 py-2 text-sm font-mono text-ink"
          placeholder="Key id"
          value={keyId}
          onChange={(e) => setKeyId(e.target.value)}
          autoComplete="off"
          data-testid="broker-key-id"
        />
        <Input
          type="password"
          className="h-auto w-full border-hair bg-term-bg/50 px-3 py-2 text-sm font-mono text-ink"
          placeholder="Secret"
          value={secret}
          onChange={(e) => setSecret(e.target.value)}
          autoComplete="off"
          data-testid="broker-secret"
        />
        <Button
          type="button"
          variant="outline"
          disabled={busy || !keyId || !secret}
          onClick={() => void onConnectApiKey()}
          className="h-auto px-3 py-1.5 text-sm text-ink-soft"
          data-testid="broker-api-key-connect"
        >
          Save API key (paper)
        </Button>
      </div>

      {loadError ? (
        <SettingsLoadError message={loadError} onRetry={() => void refresh()} />
      ) : null}
      {error ? (
        <Alert variant="destructive" data-testid="brokers-error">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <div className="space-y-2" data-testid="brokers-list">
        <p className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
          Connections
        </p>
        {rows.length === 0 ? (
          <p className="text-sm text-ink-mute">No broker connections yet.</p>
        ) : (
          <ul className="divide-y divide-hair border border-hair">
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
                  <Button
                    type="button"
                    variant="link"
                    className="h-auto p-0 text-xs text-ink-soft underline-offset-2"
                    onClick={() => void onRevoke(row.id)}
                    data-testid="broker-revoke"
                  >
                    Revoke
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="space-y-2" data-testid="brokers-fills">
        <p className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
          Paper fills
        </p>
        <p className="text-xs text-ink-mute">
          Mirrored Alpaca paper executions for this workspace. The remaining hop
          requires a fingerprint with a non-empty symbol **and** an Alpaca paper
          OAuth connection — API-key paper rows do not prove it.
        </p>
        {fills.length === 0 ? (
          <p className="text-sm text-ink-mute">No paper fills mirrored yet.</p>
        ) : (
          <ul className="divide-y divide-hair border border-hair">
            {fills.map((fill) => (
              <li
                key={fill.id}
                className="px-3 py-2 text-sm"
                data-testid="broker-fill-row"
              >
                <p className="font-mono text-ink">
                  {fill.symbol} · {fill.quantity}
                </p>
                <p className="text-xs text-ink-mute">
                  {fill.executed_at ?? fill.recorded_at ?? ''}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
