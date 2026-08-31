import { describe, expect, it } from 'vitest';
import { lastRunAt } from './queries';

describe('lastRunAt', () => {
  it('lifts created_at off the snapshot row', () => {
    expect(lastRunAt({ created_at: '2026-06-23T16:13:04Z' })).toBe('2026-06-23T16:13:04Z');
  });
  it('returns null when the run has no created_at', () => {
    expect(lastRunAt({ created_at: null })).toBeNull();
  });
});
