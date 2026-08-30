import { describe, expect, it } from 'vitest';
import {
  provenRemainingHops,
  remainingHopsUnproven,
  REMAINING_LIVE_HOPS,
} from './remaining-hops';

describe('provenRemainingHops', () => {
  it('does not treat ops-custom none as Stripe', () => {
    const proven = provenRemainingHops({ subscription_status: 'none' });
    expect(proven.browser_stripe_checkout).toBe(false);
    expect(remainingHopsUnproven(proven)).toEqual([...REMAINING_LIVE_HOPS]);
  });

  it('does not treat house active without Stripe subscription boolean', () => {
    const proven = provenRemainingHops({
      subscription_status: 'active',
      has_stripe_subscription: false,
    });
    expect(proven.browser_stripe_checkout).toBe(false);
  });

  it('does not treat digest log without inbox confirmation as received', () => {
    const proven = provenRemainingHops({
      digest_event_keys: ['digest:2026-08-31'],
    });
    expect(proven.digest_email_received).toBe(false);
  });

  it('does not treat skipped/running/persist_disabled overlay as claimed', () => {
    expect(
      provenRemainingHops({ jobs: [['overlay_daily', 'skipped']] }).overlay_daily_claimed,
    ).toBe(false);
    expect(
      provenRemainingHops({ jobs: [['overlay_daily', 'not_entitled']] }).overlay_daily_claimed,
    ).toBe(false);
    expect(
      provenRemainingHops({ jobs: [['overlay_daily', 'running']] }).overlay_daily_claimed,
    ).toBe(false);
    expect(
      provenRemainingHops({ jobs: [['overlay_daily', 'persist_disabled']] })
        .overlay_daily_claimed,
    ).toBe(false);
    expect(
      provenRemainingHops({ jobs: [['overlay_daily', 'succeeded']] }).overlay_daily_claimed,
    ).toBe(true);
  });

  it('does not treat Alpaca live or api_key paper as OAuth hop', () => {
    expect(
      provenRemainingHops({
        connections: [['alpaca', 'live', 'active', 'oauth']],
      }).alpaca_paper_oauth_connect,
    ).toBe(false);
    expect(
      provenRemainingHops({
        connections: [['alpaca', 'paper', 'active', 'api_key']],
      }).alpaca_paper_oauth_connect,
    ).toBe(false);
  });

  it('proves all five from product state including inbox flag', () => {
    const proven = provenRemainingHops({
      subscription_status: 'active',
      has_stripe_subscription: true,
      connections: [['alpaca', 'paper', 'active', 'oauth']],
      jobs: [['overlay_daily', 'succeeded']],
      fill_count: 1,
      digest_event_keys: ['digest:2026-08-31'],
      digest_inbox_confirmed: true,
    });
    expect(remainingHopsUnproven(proven)).toEqual([]);
    for (const name of REMAINING_LIVE_HOPS) {
      expect(proven[name]).toBe(true);
    }
  });
});
