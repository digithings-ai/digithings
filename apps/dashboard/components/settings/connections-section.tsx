'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ALPACA_OAUTH_STATE_KEY,
  alpacaOAuthRedirectUri,
  buildAlpacaAuthorizeUrl,
  resolveAlpacaOauthClientId,
} from '@/lib/settings/alpaca-oauth';
import {
  connectBrokerApiKey,
  connectProviderKey,
  getAppUrls,
  getFills,
  listBrokers,
  listKeys,
  revokeBroker,
  revokeProviderKey,
  type FillView,
  type LlmProviderName,
  type SettingsApiOptions,
} from '@/lib/settings-api';
import type { SettingsTabId } from '@/lib/entitlements';
import {
  ageLabel,
  brokerToRow,
  connectionKindsVisible,
  connectionsSummary,
  keyToRow,
  LLM_PROVIDERS,
  mergeConnections,
  type ConnectionRow,
} from '@/lib/settings-connections';
import { SETTINGS_LOAD_ERROR_MESSAGE, SettingsLoadError } from './settings-load-error';
import {
  Alert,
  AlertDescription,
  Button,
  EmptyState,
  Input,
  SegmentedControl,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  StatusDot,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@digithings/ui/ui';

export type ConnectionsSectionProps = {
  api: SettingsApiOptions | null;
  /** Legacy tab ids the viewer may use; gates each kind (omitted, never greyed). */
  visibleTabs: readonly SettingsTabId[];
  listBrokersFn?: typeof listBrokers;
  connectBrokerFn?: typeof connectBrokerApiKey;
  revokeBrokerFn?: typeof revokeBroker;
  listKeysFn?: typeof listKeys;
  connectKeyFn?: typeof connectProviderKey;
  revokeKeyFn?: typeof revokeProviderKey;
  fillsFn?: typeof getFills;
  /** Test seam: GET /app-urls (public Alpaca client id). */
  appUrlsFn?: typeof getAppUrls;
  /** Test seam: capture authorize URL instead of navigating. */
  onAuthorizeNavigate?: (url: string) => void;
};

type AddMode = 'alpaca' | 'api-key' | 'llm';

/**
 * One table for every credentialed connection (brokers and model keys), driven
 * by the CONNECTION_KINDS registry. Credential entry keeps the old behaviour:
 * secrets are cleared from state the moment a save returns and only
 * whitelisted display fields ever reach a row.
 */
export function ConnectionsSection({
  api,
  visibleTabs,
  listBrokersFn = listBrokers,
  connectBrokerFn = connectBrokerApiKey,
  revokeBrokerFn = revokeBroker,
  listKeysFn = listKeys,
  connectKeyFn = connectProviderKey,
  revokeKeyFn = revokeProviderKey,
  fillsFn = getFills,
  appUrlsFn = getAppUrls,
  onAuthorizeNavigate,
}: ConnectionsSectionProps) {
  const kinds = useMemo(() => connectionKindsVisible(visibleTabs), [visibleTabs]);
  const hasBroker = kinds.some((k) => k.id === 'broker');
  const hasLlm = kinds.some((k) => k.id === 'llm');

  const [brokerRows, setBrokerRows] = useState<ConnectionRow[]>([]);
  const [keyRows, setKeyRows] = useState<ConnectionRow[]>([]);
  const [fills, setFills] = useState<FillView[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [mode, setMode] = useState<AddMode>(hasBroker ? 'alpaca' : 'llm');
  const [broker, setBroker] = useState<'alpaca' | 'ibkr'>('alpaca');
  const [keyId, setKeyId] = useState('');
  const [secret, setSecret] = useState('');
  const [provider, setProvider] = useState<LlmProviderName>('openai');
  const [oauthClientId, setOauthClientId] = useState('');
  const [now, setNow] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    if (!api) return;
    try {
      if (hasBroker) {
        const list = await listBrokersFn(api);
        setBrokerRows(list.map(brokerToRow));
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
      }
      if (hasLlm) {
        const list = await listKeysFn(api);
        setKeyRows(list.map(keyToRow));
      }
      setError(null);
      setLoadError(null);
      setLoaded(true);
    } catch {
      setLoadError(SETTINGS_LOAD_ERROR_MESSAGE);
    }
  }, [api, hasBroker, hasLlm, listBrokersFn, listKeysFn, fillsFn, appUrlsFn]);

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect -- load connections after mount; clock set post-hydration */
    setNow(Date.now());
    void refresh();
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [refresh]);

  const rows = useMemo(() => mergeConnections(brokerRows, keyRows), [brokerRows, keyRows]);

  async function onConnectApiKey() {
    if (!api) {
      setError('Sign in to connect a broker.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const row = await connectBrokerFn(api, { broker, key_id: keyId, secret });
      // Clear plaintext immediately — never retain in component state after save.
      setKeyId('');
      setSecret('');
      setBrokerRows((prev) => [brokerToRow(row), ...prev]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Connect failed');
    } finally {
      setBusy(false);
    }
  }

  async function onConnectLlm() {
    if (!api) {
      setError('Sign in to save a provider key.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const row = await connectKeyFn(api, { provider, secret });
      setSecret('');
      setKeyRows((prev) => [
        keyToRow(row),
        ...prev.filter((r) => r.name !== keyToRow(row).name),
      ]);
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

  async function onRevoke(row: ConnectionRow) {
    if (!api || !row.active) return;
    setBusy(true);
    try {
      if (row.kind === 'broker') {
        const next = await revokeBrokerFn(api, { connection_id: row.id });
        setBrokerRows((prev) => prev.map((r) => (r.id === row.id ? brokerToRow(next) : r)));
      } else {
        const next = await revokeKeyFn(api, { credential_id: row.id });
        setKeyRows((prev) => prev.map((r) => (r.id === row.id ? keyToRow(next) : r)));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Revoke failed');
    } finally {
      setBusy(false);
    }
  }

  const modes: { value: AddMode; label: string }[] = [
    ...(hasBroker
      ? [
          { value: 'alpaca' as const, label: 'Alpaca OAuth' },
          { value: 'api-key' as const, label: 'Broker API key' },
        ]
      : []),
    ...(hasLlm ? [{ value: 'llm' as const, label: 'Model key' }] : []),
  ];
  const activeMode = modes.some((m) => m.value === mode) ? mode : (modes[0]?.value ?? 'llm');

  return (
    <div className="space-y-4" data-testid="settings-connections">
      {hasBroker ? <span id="brokers" className="block scroll-mt-20" aria-hidden /> : null}
      {hasLlm ? <span id="keys" className="block scroll-mt-20" aria-hidden /> : null}

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p
          className="font-mono text-xs text-ink-mute"
          data-testid="connections-summary"
          role="status"
        >
          {loaded ? connectionsSummary(rows) : 'Loading connections'}
        </p>
        <Button
          type="button"
          variant={adding ? 'outline' : 'default'}
          className="h-auto px-3 py-1.5 text-sm"
          aria-expanded={adding}
          onClick={() => setAdding((v) => !v)}
          data-testid="connections-add"
        >
          {adding ? 'Close' : 'Add connection'}
        </Button>
      </div>

      {adding ? (
        <div className="space-y-3 border border-hair bg-surface p-3" data-testid="connections-add-panel">
          <SegmentedControl
            aria-label="Connection type"
            value={activeMode}
            onChange={(v) => {
              setMode(v);
              setSecret('');
              setKeyId('');
            }}
            options={modes}
          />

          {activeMode === 'alpaca' ? (
            <div className="space-y-2">
              <p className="text-xs text-ink-mute">
                Paper connections only. After save we show fingerprint, venue, and status — never
                the credential itself.
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
          ) : null}

          {activeMode === 'api-key' ? (
            <div className="space-y-2">
              <Select
                value={broker}
                onValueChange={(next) => {
                  if (next === 'alpaca' || next === 'ibkr') setBroker(next);
                }}
              >
                <SelectTrigger className="w-full text-ink" data-testid="broker-select">
                  <SelectValue>
                    {(value) => (value === 'ibkr' ? 'IBKR (beta)' : 'Alpaca')}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="alpaca">Alpaca</SelectItem>
                  <SelectItem value="ibkr">IBKR (beta)</SelectItem>
                </SelectContent>
              </Select>
              {broker === 'ibkr' ? (
                <p className="text-xs text-warn" data-testid="ibkr-beta-note">
                  IBKR connect is beta / self-service for paper and development. Product OAuth
                  1.0a waits on vendor onboarding — prefer a dedicated API username so sync never
                  competes with your interactive session.
                </p>
              ) : null}
              <Input
                className="font-mono"
                placeholder="Key id"
                value={keyId}
                onChange={(e) => setKeyId(e.target.value)}
                autoComplete="off"
                data-testid="broker-key-id"
              />
              <Input
                type="password"
                className="font-mono"
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
          ) : null}

          {activeMode === 'llm' ? (
            <div className="space-y-2">
              <p className="text-xs text-ink-mute">
                Bring your own LLM key for overlay research. After save we show provider and
                fingerprint only — never the secret. House baseline never spends your key.
              </p>
              <Select
                value={provider}
                onValueChange={(next) => {
                  if (typeof next === 'string') setProvider(next as LlmProviderName);
                }}
              >
                <SelectTrigger className="w-full text-ink" data-testid="keys-provider-select">
                  <SelectValue>
                    {(value) => LLM_PROVIDERS.find((p) => p.id === value)?.label ?? ''}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {LLM_PROVIDERS.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Input
                type="password"
                className="font-mono"
                placeholder="API key"
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                autoComplete="off"
                data-testid="keys-secret"
              />
              <Button
                type="button"
                variant="outline"
                disabled={busy || !secret}
                onClick={() => void onConnectLlm()}
                className="h-auto px-3 py-1.5 text-sm text-ink-soft"
                data-testid="keys-connect"
              >
                Save key
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}

      {loadError ? (
        <SettingsLoadError message={loadError} onRetry={() => void refresh()} />
      ) : null}
      {error ? (
        <Alert variant="destructive" data-testid="brokers-error">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <div data-testid="connections-list">
        {loaded && rows.length === 0 ? (
          <EmptyState
            variant="first-run"
            title="No connections yet"
            body="Add a broker or a model key to get started."
          />
        ) : rows.length > 0 ? (
          <Table aria-label="Connections">
            <TableHeader>
              <TableRow>
                <TableHead>Status</TableHead>
                <TableHead>Connection</TableHead>
                <TableHead>Kind</TableHead>
                <TableHead>Fingerprint</TableHead>
                <TableHead className="text-right">Last used</TableHead>
                <TableHead className="text-right">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow
                  key={row.key}
                  data-testid={row.kind === 'broker' ? 'broker-row' : 'keys-row'}
                  data-status={row.status}
                >
                  <TableCell>
                    <span className="inline-flex items-center gap-2 font-mono text-xs">
                      <StatusDot tone={row.tone} label={row.status} />
                      <span className="text-ink-mute">{row.status}</span>
                    </span>
                  </TableCell>
                  <TableCell className="font-mono text-ink">
                    {row.name}
                    {row.env ? <span className="text-ink-mute"> · {row.env}</span> : null}
                    {row.authKind ? <span className="text-ink-mute"> · {row.authKind}</span> : null}
                  </TableCell>
                  <TableCell className="text-ink-mute">{row.kindLabel}</TableCell>
                  <TableCell className="font-mono text-ink-soft">{row.fingerprint}</TableCell>
                  <TableCell className="text-right font-mono text-ink-mute">
                    {now === null ? '' : ageLabel(row.lastUsedAt, now)}
                  </TableCell>
                  <TableCell className="text-right">
                    {row.active ? (
                      <Button
                        type="button"
                        variant="link"
                        disabled={busy}
                        className="h-auto p-0 text-xs text-ink-soft underline-offset-2"
                        onClick={() => void onRevoke(row)}
                        data-testid={row.kind === 'broker' ? 'broker-revoke' : 'keys-revoke'}
                      >
                        Revoke
                      </Button>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
      </div>

      {hasBroker ? (
        <div className="space-y-2" data-testid="brokers-fills">
          <p className="font-mono text-[0.65rem] uppercase tracking-wider text-ink-mute">
            Paper fills
          </p>
          <p className="text-xs text-ink-mute">
            Mirrored Alpaca paper executions for this workspace. The remaining hop requires a
            fingerprint with a non-empty symbol and an Alpaca paper OAuth connection — API-key
            paper rows do not prove it.
          </p>
          {fills.length === 0 ? (
            <p className="text-sm text-ink-mute">No paper fills mirrored yet.</p>
          ) : (
            <Table aria-label="Paper fills">
              <TableHeader>
                <TableRow>
                  <TableHead>Symbol</TableHead>
                  <TableHead className="text-right">Qty</TableHead>
                  <TableHead className="text-right">Executed</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {fills.map((fill) => (
                  <TableRow key={fill.id} data-testid="broker-fill-row">
                    <TableCell className="font-mono text-ink">{fill.symbol}</TableCell>
                    <TableCell className="text-right font-mono tabular-nums text-ink">
                      {fill.quantity}
                    </TableCell>
                    <TableCell className="text-right font-mono text-ink-mute">
                      {fill.executed_at ?? fill.recorded_at ?? ''}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      ) : null}
    </div>
  );
}
