import { describe, expect, it } from 'vitest';
import {
  CORPUS_KEY_PREFIXES,
  HOUSE_BOOK_IDENTITY,
  HOUSE_PROFILE_PINS,
  isSharedCorpusKey,
  mapHouseTabFromUrl,
  periodInspectabilityState,
} from './house-identity';

describe('house-identity', () => {
  it('declares digithings as house owner with lowercase product naming', () => {
    expect(HOUSE_BOOK_IDENTITY.owner).toBe('digithings');
    expect(HOUSE_BOOK_IDENTITY.label.toLowerCase()).toContain('etf');
  });

  it('keeps profile pins read-only until ProfileConfig lands', () => {
    expect(HOUSE_PROFILE_PINS.editable).toBe(false);
    expect(HOUSE_PROFILE_PINS.profileId).toBe('house');
  });

  it('maps house chrome tabs from URL', () => {
    expect(mapHouseTabFromUrl(null)).toBe('corpus');
    expect(mapHouseTabFromUrl('Book')).toBe('book');
    expect(mapHouseTabFromUrl('profile')).toBe('profile');
    expect(mapHouseTabFromUrl('nope')).toBe('corpus');
  });

  it('recognizes tenant-agnostic corpus key prefixes', () => {
    expect(CORPUS_KEY_PREFIXES).toEqual(['theme:', 'asset:', 'segment:']);
    expect(isSharedCorpusKey('theme:macro')).toBe(true);
    expect(isSharedCorpusKey('asset:SPY')).toBe(true);
    expect(isSharedCorpusKey('digest')).toBe(false);
  });

  it('states period accounting as a typed private gap for anon UI', () => {
    expect(periodInspectabilityState()).toBe('typed-gap-private-accounting');
  });
});
