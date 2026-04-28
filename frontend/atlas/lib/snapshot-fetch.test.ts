import { describe, expect, it, vi } from 'vitest';
import type { SupabaseClient } from '@supabase/supabase-js';
import { envelopeFromRow, fetchLatestSnapshot } from './snapshot-fetch';
import { fixtureDigest, fixtureSnapshotRow } from './__fixtures__/snapshot-fixture';
import type { Database } from './database.types';

const NOW = new Date('2026-04-27T12:00:00Z');

/** Build a fake Supabase client whose `from()...maybeSingle()` returns a fixed shape. */
function fakeClient<T>(payload: { data: T | null; error: { message: string } | null }) {
  const builder = {
    select: vi.fn().mockReturnThis(),
    order: vi.fn().mockReturnThis(),
    limit: vi.fn().mockReturnThis(),
    maybeSingle: vi.fn().mockResolvedValue(payload),
  };
  const from = vi.fn().mockReturnValue(builder);
  // Cast through unknown — the test only exercises the chain we use in
  // snapshot-fetch.ts, not the full SupabaseClient surface.
  return { from } as unknown as SupabaseClient<Database>;
}

describe('envelopeFromRow', () => {
  it('builds an envelope from a row with a valid digest payload', () => {
    const env = envelopeFromRow(fixtureSnapshotRow(), NOW);
    expect(env).not.toBeNull();
    expect(env?.run_date).toBe('2026-04-27');
    expect(env?.run_type).toBe('delta');
    expect(env?.baseline_date).toBe('2026-04-26');
    expect(env?.digest.headline).toBe(fixtureDigest().headline);
  });

  it('returns null when run_type is not baseline/delta', () => {
    const row = fixtureSnapshotRow();
    row.run_type = 'invalid';
    expect(envelopeFromRow(row, NOW)).toBeNull();
  });

  it('returns null when the snapshot payload is missing required fields', () => {
    const row = fixtureSnapshotRow();
    row.snapshot = { headline: 'only this one' };
    expect(envelopeFromRow(row, NOW)).toBeNull();
  });

  it('falls back to "now" when created_at is missing', () => {
    const row = fixtureSnapshotRow();
    row.created_at = null;
    const env = envelopeFromRow(row, NOW);
    expect(env?.published_at).toBe(NOW.toISOString());
  });
});

describe('fetchLatestSnapshot', () => {
  it('returns kind=present when the latest row is for today', async () => {
    const today = NOW.toISOString().slice(0, 10);
    const row = fixtureSnapshotRow();
    row.date = today;
    const client = fakeClient({ data: row, error: null });

    const result = await fetchLatestSnapshot({ now: NOW, client });
    expect(result.kind).toBe('present');
    if (result.kind === 'present') {
      expect(result.envelope.run_date).toBe(today);
    }
  });

  it('returns kind=present when the latest row is for yesterday', async () => {
    const row = fixtureSnapshotRow();
    row.date = '2026-04-26'; // yesterday vs NOW
    const client = fakeClient({ data: row, error: null });

    const result = await fetchLatestSnapshot({ now: NOW, client });
    expect(result.kind).toBe('present');
  });

  it('returns kind=empty/no_recent_row when the latest row is older than yesterday', async () => {
    const row = fixtureSnapshotRow();
    row.date = '2026-04-20'; // 7 days old
    const client = fakeClient({ data: row, error: null });

    const result = await fetchLatestSnapshot({ now: NOW, client });
    expect(result.kind).toBe('empty');
    if (result.kind === 'empty') {
      expect(result.reason).toBe('no_recent_row');
    }
  });

  it('returns kind=empty/no_recent_row when no row exists', async () => {
    const client = fakeClient({ data: null, error: null });
    const result = await fetchLatestSnapshot({ now: NOW, client });
    expect(result.kind).toBe('empty');
    if (result.kind === 'empty') {
      expect(result.reason).toBe('no_recent_row');
    }
  });

  it('returns kind=empty/unconfigured when no Supabase client is available', async () => {
    const result = await fetchLatestSnapshot({ now: NOW, client: null });
    expect(result.kind).toBe('empty');
    if (result.kind === 'empty') {
      expect(result.reason).toBe('unconfigured');
    }
  });

  it('returns kind=error when Supabase returns an error', async () => {
    const client = fakeClient({ data: null, error: { message: 'RLS denied' } });
    const result = await fetchLatestSnapshot({ now: NOW, client });
    expect(result.kind).toBe('error');
    if (result.kind === 'error') {
      expect(result.message).toContain('RLS denied');
    }
  });

  it('returns kind=error when the payload fails validation', async () => {
    const today = NOW.toISOString().slice(0, 10);
    const row = fixtureSnapshotRow();
    row.date = today;
    row.snapshot = { headline: 'incomplete' };
    const client = fakeClient({ data: row, error: null });

    const result = await fetchLatestSnapshot({ now: NOW, client });
    expect(result.kind).toBe('error');
  });
});
