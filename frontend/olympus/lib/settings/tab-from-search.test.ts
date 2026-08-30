import { describe, expect, it } from 'vitest';
import { settingsTabFromSearch } from './tab-from-search';

describe('settingsTabFromSearch', () => {
  it('defaults to profile', () => {
    expect(settingsTabFromSearch('')).toBe('profile');
    expect(settingsTabFromSearch('?')).toBe('profile');
  });

  it('honors tab= billing and other known tabs', () => {
    expect(settingsTabFromSearch('?tab=billing')).toBe('billing');
    expect(settingsTabFromSearch('tab=brokers')).toBe('brokers');
  });

  it('opens billing after Stripe checkout return', () => {
    expect(settingsTabFromSearch('?tab=billing&checkout=success')).toBe('billing');
    expect(settingsTabFromSearch('?checkout=cancel')).toBe('billing');
  });

  it('ignores unknown tab values', () => {
    expect(settingsTabFromSearch('?tab=not-a-tab')).toBe('profile');
  });
});
