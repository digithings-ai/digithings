/**
 * After login/signup, redeem a stashed FX Hub invite via the existing
 * hashed path (FX_HUB_INVITE_HASH / product_invite_codes). Requires a
 * session JWT and an email — never grants anonymously.
 */

import { redeemInvite, SettingsHttpError } from './settings-api';
import {
  clearStashedInvite,
  peekStashedInvite,
  type InviteStorage,
} from './invite-stash';

export type RedeemStashOutcome = 'granted' | 'skipped' | 'invalid' | 'failed';

export type RedeemInviteFn = typeof redeemInvite;

const inFlight = new WeakMap<object, Promise<RedeemStashOutcome>>();

function hasEmail(email: string | null | undefined): boolean {
  const value = (email ?? '').trim();
  return value.includes('@');
}

function isInvalidInvite(err: unknown): boolean {
  return err instanceof SettingsHttpError && (err.status === 403 || err.code === 'INVITE_INVALID');
}

function flightKey(storage?: InviteStorage): object | null {
  if (storage) return storage;
  try {
    if (typeof sessionStorage === 'undefined') return null;
    return sessionStorage;
  } catch {
    return null;
  }
}

export async function redeemStashedInvite(args: {
  accessToken: string | null | undefined;
  email: string | null | undefined;
  redeem?: RedeemInviteFn;
  refresh?: () => void;
  storage?: InviteStorage;
}): Promise<RedeemStashOutcome> {
  const code = peekStashedInvite(args.storage);
  if (!code) return 'skipped';
  const accessToken = (args.accessToken ?? '').trim();
  if (!accessToken || !hasEmail(args.email)) return 'skipped';

  const key = flightKey(args.storage);
  if (key) {
    const existing = inFlight.get(key);
    if (existing) return existing;
  }

  const redeem = args.redeem ?? redeemInvite;
  const run = (async (): Promise<RedeemStashOutcome> => {
    try {
      await redeem({ accessToken }, { code, product_key: 'fx_hub' });
      clearStashedInvite(args.storage);
      args.refresh?.();
      return 'granted';
    } catch (err) {
      if (isInvalidInvite(err)) {
        clearStashedInvite(args.storage);
        return 'invalid';
      }
      return 'failed';
    } finally {
      if (key) inFlight.delete(key);
    }
  })();

  if (key) inFlight.set(key, run);
  return run;
}
