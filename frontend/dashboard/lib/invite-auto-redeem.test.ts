import { describe, expect, it, vi } from 'vitest';
import { SettingsHttpError } from './settings-api';
import { redeemStashedInvite } from './invite-auto-redeem';
import {
  FX_HUB_INVITE_STORAGE_KEY,
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

const SESSION = {
  accessToken: 'sess-tok',
  email: 'analyst@example.com',
};

describe('redeemStashedInvite', () => {
  it('auto-redeems a stashed token after auth and refreshes access', async () => {
    const storage = memoryStorage();
    stashInviteFromSearch('?invite=fx-hub-desk-token', storage);
    const redeem = vi.fn(async () => ({
      ok: true as const,
      already_granted: false,
      product_key: 'fx_hub',
    }));
    const refresh = vi.fn();

    const outcome = await redeemStashedInvite({
      ...SESSION,
      redeem,
      refresh,
      storage,
    });

    expect(outcome).toBe('granted');
    expect(redeem).toHaveBeenCalledWith(
      { accessToken: 'sess-tok' },
      { code: 'fx-hub-desk-token', product_key: 'fx_hub' },
    );
    expect(refresh).toHaveBeenCalledOnce();
    expect(storage.getItem(FX_HUB_INVITE_STORAGE_KEY)).toBeNull();
  });

  it('does not call redeem when no token is stashed', async () => {
    const redeem = vi.fn();
    const refresh = vi.fn();
    const outcome = await redeemStashedInvite({
      ...SESSION,
      redeem,
      refresh,
      storage: memoryStorage(),
    });
    expect(outcome).toBe('skipped');
    expect(redeem).not.toHaveBeenCalled();
    expect(refresh).not.toHaveBeenCalled();
  });

  it('does not redeem without a session token or email (no anonymous grant)', async () => {
    const storage = memoryStorage();
    stashInviteFromSearch('?invite=fx-hub-desk-token', storage);
    const redeem = vi.fn();

    expect(
      await redeemStashedInvite({
        accessToken: null,
        email: 'analyst@example.com',
        redeem,
        storage,
      }),
    ).toBe('skipped');
    expect(
      await redeemStashedInvite({
        accessToken: 'sess-tok',
        email: null,
        redeem,
        storage,
      }),
    ).toBe('skipped');
    expect(
      await redeemStashedInvite({
        accessToken: 'sess-tok',
        email: 'not-an-email',
        redeem,
        storage,
      }),
    ).toBe('skipped');
    expect(redeem).not.toHaveBeenCalled();
    expect(storage.getItem(FX_HUB_INVITE_STORAGE_KEY)).toBe('fx-hub-desk-token');
  });

  it('does not grant when the token is invalid', async () => {
    const storage = memoryStorage();
    stashInviteFromSearch('?invite=totally-wrong-invite', storage);
    const redeem = vi.fn(async () => {
      throw new SettingsHttpError({
        status: 403,
        code: 'INVITE_INVALID',
        message: 'Invite code is not valid.',
      });
    });
    const refresh = vi.fn();

    const outcome = await redeemStashedInvite({
      ...SESSION,
      redeem,
      refresh,
      storage,
    });

    expect(outcome).toBe('invalid');
    expect(redeem).toHaveBeenCalledOnce();
    expect(refresh).not.toHaveBeenCalled();
    expect(storage.getItem(FX_HUB_INVITE_STORAGE_KEY)).toBeNull();
  });

  it('keeps the stash on a transient failure so a later session can retry', async () => {
    const storage = memoryStorage();
    stashInviteFromSearch('?invite=fx-hub-desk-token', storage);
    const redeem = vi.fn(async () => {
      throw new SettingsHttpError({
        status: 429,
        code: 'INVITE_RATE_LIMIT',
        message: 'Too many invite attempts. Try again later.',
      });
    });
    const refresh = vi.fn();

    const outcome = await redeemStashedInvite({
      ...SESSION,
      redeem,
      refresh,
      storage,
    });

    expect(outcome).toBe('failed');
    expect(refresh).not.toHaveBeenCalled();
    expect(storage.getItem(FX_HUB_INVITE_STORAGE_KEY)).toBe('fx-hub-desk-token');
  });
});
