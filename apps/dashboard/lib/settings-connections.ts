/**
 * Unified Connections model: brokers and LLM provider keys share one table.
 * CONNECTION_KINDS is the registry seam — a new integration (LuxAlgo SDK, MCP
 * data connection, ...) is an entry here, not a new tab. Only real kinds ship.
 *
 * Secret hygiene: rows pass through a SAFE_KEYS whitelist before they reach
 * state, so a stray `secret` / `key` field on a response is never rendered.
 */
import type {
  BrokerConnectionView,
  LlmProviderName,
  ProviderCredentialView,
} from '@/lib/settings-api';
import type { SettingsTabId } from '@/lib/entitlements';

export type ConnectionKindId = 'broker' | 'llm';

/** Display-safe broker fields only — never render secret material. */
export const BROKER_SAFE_KEYS: ReadonlySet<string> = new Set([
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

export const KEY_SAFE_KEYS: ReadonlySet<string> = new Set([
  'id',
  'provider',
  'auth_kind',
  'fingerprint',
  'status',
  'last_used_at',
  'created_at',
  'revoked_at',
]);

function pick<T>(row: T, allow: ReadonlySet<string>): T {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(row as Record<string, unknown>)) {
    if (allow.has(k)) out[k] = v;
  }
  return out as T;
}

export function sanitizeConnection(row: BrokerConnectionView): BrokerConnectionView {
  return pick(row, BROKER_SAFE_KEYS);
}

export function sanitizeKeyRow(row: ProviderCredentialView): ProviderCredentialView {
  return pick(row, KEY_SAFE_KEYS);
}

export const LLM_PROVIDERS: readonly { id: LlmProviderName; label: string }[] = [
  { id: 'openai', label: 'OpenAI' },
  { id: 'anthropic', label: 'Anthropic' },
  { id: 'groq', label: 'Groq' },
  { id: 'openrouter', label: 'OpenRouter' },
  { id: 'xai', label: 'xAI' },
  { id: 'gemini', label: 'Gemini' },
];

export type ConnectionTone = 'ok' | 'warn' | 'off';

export type ConnectionRow = {
  /** Unique across kinds. */
  key: string;
  kind: ConnectionKindId;
  kindLabel: string;
  /** Kind-local id used for revoke. */
  id: string;
  name: string;
  env: string | null;
  authKind: string | null;
  fingerprint: string;
  status: string;
  tone: ConnectionTone;
  active: boolean;
  lastUsedAt: string | null;
  createdAt: string | null;
};

export type ConnectionKind = {
  id: ConnectionKindId;
  label: string;
  /** Legacy settings tab that gates this kind (omitted, never greyed). */
  requiredTab: SettingsTabId;
};

export const CONNECTION_KINDS: readonly ConnectionKind[] = [
  { id: 'broker', label: 'Broker', requiredTab: 'brokers' },
  { id: 'llm', label: 'Model key', requiredTab: 'keys' },
];

export function connectionKindsVisible(
  visibleTabIds: readonly SettingsTabId[],
): readonly ConnectionKind[] {
  return CONNECTION_KINDS.filter((k) => visibleTabIds.includes(k.requiredTab));
}

/** active = ok, revoked/error/expired = off, anything in between = warn. */
export function connectionTone(status: string): ConnectionTone {
  const s = status.toLowerCase();
  if (s === 'active') return 'ok';
  if (s === 'revoked' || s === 'error' || s === 'expired' || s === 'failed') return 'off';
  return 'warn';
}

export function brokerToRow(raw: BrokerConnectionView): ConnectionRow {
  const row = sanitizeConnection(raw);
  return {
    key: `broker:${row.id}`,
    kind: 'broker',
    kindLabel: 'Broker',
    id: row.id,
    name: row.broker,
    env: row.env ?? null,
    authKind: row.auth_kind ?? null,
    fingerprint: row.fingerprint,
    status: row.status,
    tone: connectionTone(row.status),
    active: row.status === 'active',
    lastUsedAt: row.last_used_at ?? null,
    createdAt: row.created_at ?? null,
  };
}

export function keyToRow(raw: ProviderCredentialView): ConnectionRow {
  const row = sanitizeKeyRow(raw);
  return {
    key: `llm:${row.id}`,
    kind: 'llm',
    kindLabel: 'Model key',
    id: row.id,
    name: LLM_PROVIDERS.find((p) => p.id === row.provider)?.label ?? row.provider,
    env: null,
    authKind: row.auth_kind ?? null,
    fingerprint: row.fingerprint,
    status: row.status,
    tone: connectionTone(row.status),
    active: row.status === 'active',
    lastUsedAt: row.last_used_at ?? null,
    createdAt: row.created_at ?? null,
  };
}

const TONE_ORDER: Record<ConnectionTone, number> = { ok: 0, warn: 1, off: 2 };

function ts(iso: string | null): number {
  if (!iso) return 0;
  const t = Date.parse(iso);
  return Number.isFinite(t) ? t : 0;
}

/** Live rows first, then most recently used/created. Stable across kinds. */
export function mergeConnections(
  ...groups: ReadonlyArray<readonly ConnectionRow[]>
): ConnectionRow[] {
  return groups
    .flat()
    .slice()
    .sort(
      (a, b) =>
        TONE_ORDER[a.tone] - TONE_ORDER[b.tone] ||
        Math.max(ts(b.lastUsedAt), ts(b.createdAt)) -
          Math.max(ts(a.lastUsedAt), ts(a.createdAt)) ||
        a.key.localeCompare(b.key),
    );
}

/** "2h", "3d", "just now"; null/invalid -> "never". */
export function ageLabel(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return 'never';
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return 'never';
  const s = Math.max(0, Math.floor((now - t) / 1000));
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86_400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86_400)}d`;
}

/** Screen-reader summary: "3 connections, 2 active, 1 inactive". */
export function connectionsSummary(rows: readonly ConnectionRow[]): string {
  if (rows.length === 0) return 'No connections';
  const active = rows.filter((r) => r.active).length;
  const rest = rows.length - active;
  return `${rows.length} connection${rows.length === 1 ? '' : 's'}, ${active} active${
    rest ? `, ${rest} inactive` : ''
  }`;
}
