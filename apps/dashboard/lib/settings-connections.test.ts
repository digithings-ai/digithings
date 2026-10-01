import { describe, expect, it } from 'vitest';
import type { BrokerConnectionView, ProviderCredentialView } from '@/lib/settings-api';
import {
  ageLabel,
  brokerToRow,
  CONNECTION_KINDS,
  connectionKindsVisible,
  connectionsSummary,
  connectionTone,
  keyToRow,
  mergeConnections,
  sanitizeConnection,
  sanitizeKeyRow,
} from '@/lib/settings-connections';

const broker = (over: Partial<BrokerConnectionView> = {}): BrokerConnectionView => ({
  id: 'b1',
  broker: 'alpaca',
  env: 'paper',
  auth_kind: 'oauth',
  fingerprint: '...a91f',
  status: 'active',
  last_used_at: '2026-09-29T10:00:00Z',
  created_at: '2026-09-01T00:00:00Z',
  ...over,
});
const key = (over: Partial<ProviderCredentialView> = {}): ProviderCredentialView => ({
  id: 'k1',
  provider: 'openai',
  fingerprint: '...c3d2',
  status: 'active',
  last_used_at: null,
  created_at: '2026-09-02T00:00:00Z',
  ...over,
});

describe('SAFE_KEYS whitelist', () => {
  it('drops secret material from broker rows', () => {
    const dirty = { ...broker(), secret: 'sk-live', key_id: 'AKIA', access_token: 't' };
    const out = sanitizeConnection(dirty as unknown as BrokerConnectionView);
    expect(JSON.stringify(out)).not.toMatch(/sk-live|AKIA|access_token/);
    expect(out.fingerprint).toBe('...a91f');
  });

  it('drops secret material from key rows and from the merged view model', () => {
    const dirty = { ...key(), secret: 'sk-live', api_key: 'xyz' };
    expect(JSON.stringify(sanitizeKeyRow(dirty as unknown as ProviderCredentialView))).not.toMatch(
      /sk-live|xyz/,
    );
    expect(JSON.stringify(keyToRow(dirty as unknown as ProviderCredentialView))).not.toMatch(
      /sk-live|xyz/,
    );
  });
});

describe('merge + tone', () => {
  it('maps status to health tone, never up/down', () => {
    expect(connectionTone('active')).toBe('ok');
    expect(connectionTone('pending')).toBe('warn');
    expect(connectionTone('revoked')).toBe('off');
  });

  it('puts active rows first then most recent, across kinds', () => {
    const rows = mergeConnections(
      [
        brokerToRow(broker({ id: 'old', status: 'revoked' })),
        brokerToRow(broker({ id: 'b2', last_used_at: '2026-09-30T00:00:00Z' })),
      ],
      [keyToRow(key())],
    );
    expect(rows.map((r) => r.key)).toEqual(['broker:b2', 'llm:k1', 'broker:old']);
  });

  it('only active rows are revocable', () => {
    expect(brokerToRow(broker()).active).toBe(true);
    expect(brokerToRow(broker({ status: 'revoked' })).active).toBe(false);
  });

  it('summarises for screen readers', () => {
    expect(connectionsSummary([])).toBe('No connections');
    expect(
      connectionsSummary([brokerToRow(broker()), keyToRow(key({ status: 'revoked' }))]),
    ).toBe('2 connections, 1 active, 1 inactive');
  });
});

describe('registry seam', () => {
  it('ships exactly the real kinds and gates each by its tab', () => {
    expect(CONNECTION_KINDS.map((k) => k.id)).toEqual(['broker', 'llm']);
    expect(connectionKindsVisible(['brokers']).map((k) => k.id)).toEqual(['broker']);
    expect(connectionKindsVisible(['notifications']).map((k) => k.id)).toEqual([]);
  });
});

describe('ageLabel', () => {
  const now = Date.parse('2026-09-30T12:00:00Z');
  it('formats recency', () => {
    expect(ageLabel(null, now)).toBe('never');
    expect(ageLabel('garbage', now)).toBe('never');
    expect(ageLabel('2026-09-30T11:59:40Z', now)).toBe('just now');
    expect(ageLabel('2026-09-30T10:00:00Z', now)).toBe('2h');
    expect(ageLabel('2026-09-27T12:00:00Z', now)).toBe('3d');
  });
});
