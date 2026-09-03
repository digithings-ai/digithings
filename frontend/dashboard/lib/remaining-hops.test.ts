import { describe, expect, it } from 'vitest';
import {
  provenRemainingHops,
  remainingHopBlockers,
  remainingHopsUnproven,
  REMAINING_LIVE_HOPS,
} from './remaining-hops';

describe('provenRemainingHops', () => {
  it('does not treat ops-studio none as Stripe', () => {
    const proven = provenRemainingHops({ subscription_status: 'none' });
    expect(proven.browser_stripe_checkout).toBe(false);
    expect(remainingHopsUnproven(proven)).toEqual([...REMAINING_LIVE_HOPS]);
    expect(
      provenRemainingHops({
        plan_tier: 'studio',
        subscription_status: 'none',
        has_stripe_subscription: false,
      }).browser_stripe_checkout,
    ).toBe(false);
  });

  it('does not treat house active without Stripe subscription boolean', () => {
    const proven = provenRemainingHops({
      subscription_status: 'active',
      has_stripe_subscription: false,
      plan_tier: 'enterprise',
    });
    expect(proven.browser_stripe_checkout).toBe(false);
  });

  it('does not treat Brief or Desk Stripe as the overlay checkout hop', () => {
    expect(
      provenRemainingHops({
        subscription_status: 'active',
        has_stripe_subscription: true,
        plan_tier: 'brief',
      }).browser_stripe_checkout,
    ).toBe(false);
    expect(
      provenRemainingHops({
        subscription_status: 'active',
        has_stripe_subscription: true,
        plan_tier: 'desk',
      }).browser_stripe_checkout,
    ).toBe(false);
    expect(
      provenRemainingHops({
        subscription_status: 'active',
        has_stripe_subscription: true,
        plan_tier: 'studio',
      }).browser_stripe_checkout,
    ).toBe(true);
  });

  it('does not treat digest log without inbox confirmation as received', () => {
    const proven = provenRemainingHops({
      digest_event_keys: ['digest:2026-08-31'],
      daily_digest_enabled: true,
    });
    expect(proven.digest_email_received).toBe(false);
  });

  it('does not treat digest log with inbox confirm when prefs are off', () => {
    const proven = provenRemainingHops({
      digest_event_keys: ['digest:2026-08-31'],
      digest_inbox_confirmed: true,
      daily_digest_enabled: false,
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

  it('does not treat api_key fills as the paper fill hop', () => {
    const apiKeyFill = provenRemainingHops({
      connections: [['alpaca', 'paper', 'active', 'api_key']],
      fill_count: 1,
    });
    expect(apiKeyFill.paper_fill_mirrored).toBe(false);
    expect(apiKeyFill.alpaca_paper_oauth_connect).toBe(false);
    expect(provenRemainingHops({ fill_count: 1 }).paper_fill_mirrored).toBe(false);
    const oauthFill = provenRemainingHops({
      connections: [['alpaca', 'paper', 'active', 'oauth']],
      fill_count: 1,
    });
    expect(oauthFill.paper_fill_mirrored).toBe(true);
    expect(oauthFill.alpaca_paper_oauth_connect).toBe(true);
  });

  it('proves all five from product state including inbox flag', () => {
    const proven = provenRemainingHops({
      subscription_status: 'active',
      has_stripe_subscription: true,
      plan_tier: 'studio',
      connections: [['alpaca', 'paper', 'active', 'oauth']],
      jobs: [['overlay_daily', 'succeeded']],
      fill_count: 1,
      digest_event_keys: ['digest:2026-08-31'],
      digest_inbox_confirmed: true,
      daily_digest_enabled: true,
    });
    expect(remainingHopsUnproven(proven)).toEqual([]);
    for (const name of REMAINING_LIVE_HOPS) {
      expect(proven[name]).toBe(true);
    }
    expect(remainingHopBlockers({
      subscription_status: 'active',
      has_stripe_subscription: true,
      plan_tier: 'studio',
      connections: [['alpaca', 'paper', 'active', 'oauth']],
      jobs: [['overlay_daily', 'succeeded']],
      fill_count: 1,
      digest_event_keys: ['digest:2026-08-31'],
      digest_inbox_confirmed: true,
      daily_digest_enabled: true,
    })).toEqual({});
  });

  it('surfaces closed-vocabulary blockers for Observer product state', () => {
    const blockers = remainingHopBlockers({
      plan_tier: 'free',
      subscription_status: 'none',
      connections: [['alpaca', 'paper', 'active', 'api_key']],
      fill_count: 1,
      digest_event_keys: ['digest:2026-08-31'],
      daily_digest_enabled: true,
    });
    expect(blockers.browser_stripe_checkout).toBe('plan_tier_not_studio');
    expect(blockers.alpaca_paper_oauth_connect).toBe('alpaca_api_key_not_oauth');
    expect(blockers.overlay_daily_claimed).toBe('overlay_not_succeeded');
    expect(blockers.paper_fill_mirrored).toBe('fill_without_oauth');
    expect(blockers.digest_email_received).toBe('digest_inbox_unconfirmed');
  });

  it('names house missing Stripe ids and persist_disabled overlay', () => {
    expect(
      remainingHopBlockers({
        plan_tier: 'enterprise',
        subscription_status: 'active',
        has_stripe_subscription: false,
      }).browser_stripe_checkout,
    ).toBe('missing_stripe_ids');
    expect(
      remainingHopBlockers({ jobs: [['overlay_daily', 'persist_disabled']] })
        .overlay_daily_claimed,
    ).toBe('overlay_persist_disabled');
    expect(
      remainingHopBlockers({
        jobs: [['overlay_daily', 'persist_disabled']],
        overlay_job_errors: ['legacy_book_unique'],
      }).overlay_daily_claimed,
    ).toBe('overlay_persist_disabled');
    expect(
      remainingHopBlockers({
        jobs: [['overlay_daily', 'failed']],
        overlay_job_errors: ['legacy_book_unique'],
      }).overlay_daily_claimed,
    ).toBe('overlay_legacy_book_unique');
    expect(
      remainingHopBlockers({
        jobs: [['overlay_daily', 'failed']],
        overlay_job_errors: ['BudgetExhausted'],
      }).overlay_daily_claimed,
    ).toBe('overlay_not_succeeded');
    expect(
      remainingHopBlockers({
        digest_event_keys: ['digest:2026-08-31'],
        digest_inbox_confirmed: true,
        daily_digest_enabled: false,
      }).digest_email_received,
    ).toBe('digest_pref_off');
  });
});
