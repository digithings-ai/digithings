'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  connectProviderKey,
  listKeys,
  revokeProviderKey,
  type LlmProviderName,
  type ProviderCredentialView,
  type SettingsApiOptions,
} from '@/lib/settings-api';

export type KeysTabProps = {
  api: SettingsApiOptions | null;
  listFn?: typeof listKeys;
  connectFn?: typeof connectProviderKey;
  revokeFn?: typeof revokeProviderKey;
};

const PROVIDERS: { id: LlmProviderName; label: string }[] = [
  { id: 'openai', label: 'OpenAI' },
  { id: 'anthropic', label: 'Anthropic' },
  { id: 'groq', label: 'Groq' },
  { id: 'openrouter', label: 'OpenRouter' },
  { id: 'xai', label: 'xAI' },
  { id: 'gemini', label: 'Gemini' },
];

const SAFE_KEYS = new Set([
  'id',
  'provider',
  'auth_kind',
  'fingerprint',
  'status',
  'last_used_at',
  'created_at',
  'revoked_at',
]);

export function sanitizeKeyRow(row: ProviderCredentialView): ProviderCredentialView {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(row)) {
    if (SAFE_KEYS.has(k)) out[k] = v;
  }
  return out as ProviderCredentialView;
}

export function KeysTab({
  api,
  listFn = listKeys,
  connectFn = connectProviderKey,
  revokeFn = revokeProviderKey,
}: KeysTabProps) {
  const [rows, setRows] = useState<ProviderCredentialView[]>([]);
  const [provider, setProvider] = useState<LlmProviderName>('openai');
  const [secret, setSecret] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!api) return;
    try {
      const list = await listFn(api);
      setRows(list.map(sanitizeKeyRow));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load keys');
    }
  }, [api, listFn]);

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect -- load keys after mount */
    void refresh();
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [refresh]);

  async function onConnect() {
    if (!api) {
      setError('Sign in to save a provider key.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const row = await connectFn(api, { provider, secret });
      setSecret('');
      setRows((prev) => [sanitizeKeyRow(row), ...prev.filter((r) => r.provider !== row.provider)]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Connect failed');
    } finally {
      setBusy(false);
    }
  }

  async function onRevoke(id: string) {
    if (!api) return;
    setBusy(true);
    try {
      const row = await revokeFn(api, { credential_id: id });
      setRows((prev) =>
        prev.map((r) => (r.id === id ? sanitizeKeyRow(row) : r)),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Revoke failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5" data-testid="settings-keys-tab">
      <div>
        <h2 className="font-display text-xl text-ink tracking-tight">Models &amp; keys</h2>
        <p className="mt-1 text-sm text-ink-soft">
          Bring your own LLM key for overlay research. After save we show provider and fingerprint
          only — never the secret. House baseline never spends your key.
        </p>
      </div>

      <div className="space-y-3 border border-hair bg-term-bg/40 px-4 py-3">
        <p className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
          Provider API key
        </p>
        <select
          className="border border-hair bg-term-bg/50 px-3 py-2 text-sm text-ink"
          value={provider}
          onChange={(e) => setProvider(e.target.value as LlmProviderName)}
          data-testid="keys-provider-select"
        >
          {PROVIDERS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
        <input
          type="password"
          className="w-full border border-hair bg-term-bg/50 px-3 py-2 text-sm font-mono text-ink"
          placeholder="API key"
          value={secret}
          onChange={(e) => setSecret(e.target.value)}
          autoComplete="off"
          data-testid="keys-secret"
        />
        <button
          type="button"
          disabled={busy || !secret}
          onClick={() => void onConnect()}
          className="border border-hair px-3 py-1.5 text-sm font-medium text-ink-soft hover:bg-ink/[0.04] disabled:opacity-50"
          data-testid="keys-connect"
        >
          Save key
        </button>
        <p className="text-xs text-ink-mute">
          Model routing follows the sealed provider via digillm. A free-form model picker lands
          after a ProfileConfig contract bump — see SETTINGS-IA.
        </p>
      </div>

      {error ? (
        <p className="text-sm text-down" role="alert" data-testid="keys-error">
          {error}
        </p>
      ) : null}

      <div className="space-y-2" data-testid="keys-list">
        <p className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
          Sealed keys
        </p>
        {rows.length === 0 ? (
          <p className="text-sm text-ink-mute">No provider keys yet.</p>
        ) : (
          <ul className="divide-y divide-hair border border-hair">
            {rows.map((row) => (
              <li
                key={row.id}
                className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm"
                data-testid="keys-row"
              >
                <div className="space-y-0.5">
                  <p className="font-mono text-ink">
                    {row.provider} · {row.fingerprint}
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
                    data-testid="keys-revoke"
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
