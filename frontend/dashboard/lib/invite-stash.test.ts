import { describe, expect, it } from 'vitest';
import {
  FX_HUB_INVITE_STORAGE_KEY,
  clearStashedInvite,
  parseInviteQuery,
  pathWithoutInviteParam,
  peekStashedInvite,
  stashInviteFromSearch,
  type InviteStorage,
} from './invite-stash';

function memoryStorage(seed: Record<string, string> = {}): InviteStorage {
  const map = new Map(Object.entries(seed));
  return {
    getItem: (key) => map.get(key) ?? null,
    setItem: (key, value) => {
      map.set(key, value);
    },
    removeItem: (key) => {
      map.delete(key);
    },
  };
}

describe('parseInviteQuery', () => {
  it('reads invite from a dashboard query string', () => {
    expect(parseInviteQuery('?invite=fx-hub-desk-token')).toBe('fx-hub-desk-token');
    expect(parseInviteQuery('invite=fx-hub-desk-token')).toBe('fx-hub-desk-token');
  });

  it('trims whitespace and keeps other params intact for the parser', () => {
    expect(parseInviteQuery('?tab=brief&invite=%20fx-hub-desk-token%20')).toBe(
      'fx-hub-desk-token',
    );
  });

  it('returns null when the token is missing or too short to redeem', () => {
    expect(parseInviteQuery('')).toBeNull();
    expect(parseInviteQuery('?tab=brief')).toBeNull();
    expect(parseInviteQuery('?invite=')).toBeNull();
    expect(parseInviteQuery('?invite=short')).toBeNull();
  });
});

describe('stashInviteFromSearch', () => {
  it('persists a valid invite token in the provided storage', () => {
    const storage = memoryStorage();
    expect(stashInviteFromSearch('?invite=fx-hub-desk-token', storage)).toBe(
      'fx-hub-desk-token',
    );
    expect(peekStashedInvite(storage)).toBe('fx-hub-desk-token');
    expect(storage.getItem(FX_HUB_INVITE_STORAGE_KEY)).toBe('fx-hub-desk-token');
  });

  it('does not stash a missing or invalid token', () => {
    const storage = memoryStorage();
    expect(stashInviteFromSearch('?tab=brief', storage)).toBeNull();
    expect(stashInviteFromSearch('?invite=nope', storage)).toBeNull();
    expect(peekStashedInvite(storage)).toBeNull();
  });

  it('clears a previously stashed token', () => {
    const storage = memoryStorage();
    stashInviteFromSearch('?invite=fx-hub-desk-token', storage);
    clearStashedInvite(storage);
    expect(peekStashedInvite(storage)).toBeNull();
  });
});

describe('pathWithoutInviteParam', () => {
  it('strips invite and preserves the rest of the path', () => {
    expect(pathWithoutInviteParam('/dashboard?invite=fx-hub-desk-token')).toBe('/dashboard');
    expect(pathWithoutInviteParam('/dashboard/?invite=fx-hub-desk-token&tab=brief')).toBe(
      '/dashboard/?tab=brief',
    );
    expect(pathWithoutInviteParam('/dashboard/twelve-x?invite=fx-hub-desk-token')).toBe(
      '/dashboard/twelve-x',
    );
  });

  it('leaves URLs without invite unchanged', () => {
    expect(pathWithoutInviteParam('/dashboard?tab=brief')).toBe('/dashboard?tab=brief');
  });
});
