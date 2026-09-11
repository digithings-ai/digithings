/**
 * Member-visible remaining-hop predicates.
 *
 * Mirrors ``digiquant.execution.remaining_hops.proven_remaining_hops``
 * and ``remaining_hop_blockers``. The Settings About panel never claims
 * digest inbox confirmation — that flag is operator-only
 * (`DIGIQUANT_STAGING_DIGEST_INBOX_CONFIRMED`). Digest also requires
 * ``daily_digest`` on; dispatch skips prefs that are off. Paper fills do not
 * prove the hop unless an Alpaca paper OAuth connection is also present.
 * Brief or Desk Stripe does not prove checkout — overlay stays Studio-gated.
 * Persist-disabled overlay names ``overlay_persist_disabled``; a failed overlay
 * with ``error=legacy_book_unique`` names ``overlay_legacy_book_unique``
 * (cutover 113 not applied). Unproven hops show a closed-vocabulary blocker
 * code, never Stripe ids.
 */

export const REMAINING_LIVE_HOPS = [
  'browser_stripe_checkout',
  'alpaca_paper_oauth_connect',
  'overlay_daily_claimed',
  'paper_fill_mirrored',
  'digest_email_received',
] as const;

export type RemainingLiveHop = (typeof REMAINING_LIVE_HOPS)[number];

export const OVERLAY_RUN_STATUSES = new Set(['succeeded']);
export const STRIPE_CHECKOUT_TIERS = new Set(['studio', 'enterprise']);

export const REMAINING_HOP_BLOCKER_CODES = [
  'plan_tier_not_studio',
  'missing_stripe_ids',
  'subscription_not_active',
  'alpaca_api_key_not_oauth',
  'no_alpaca_paper_oauth',
  'overlay_persist_disabled',
  'overlay_legacy_book_unique',
  'overlay_not_succeeded',
  'fill_without_oauth',
  'no_paper_fill',
  'digest_pref_off',
  'no_digest_log',
  'digest_inbox_unconfirmed',
] as const;

export type RemainingHopBlockerCode = (typeof REMAINING_HOP_BLOCKER_CODES)[number];

export type RemainingHopEvidence = {
  subscription_status?: string | null;
  has_stripe_subscription?: boolean;
  plan_tier?: string | null;
  connections?: readonly (readonly [string, string, string, string])[];
  jobs?: readonly (readonly [string, string])[];
  overlay_job_errors?: readonly string[];
  fill_count?: number;
  digest_event_keys?: readonly string[];
  digest_inbox_confirmed?: boolean;
  daily_digest_enabled?: boolean;
};

export type RemainingHopProven = Record<RemainingLiveHop, boolean>;
export type RemainingHopBlockers = Partial<Record<RemainingLiveHop, RemainingHopBlockerCode>>;

export function remainingHopsUnproven(
  proven: Partial<Record<RemainingLiveHop, boolean>> | RemainingHopProven = {},
): RemainingLiveHop[] {
  return REMAINING_LIVE_HOPS.filter((name) => !proven[name]);
}

function alpacaPaperOauth(evidence: RemainingHopEvidence): boolean {
  return (evidence.connections ?? []).some(
    ([broker, env, status, authKind]) =>
      broker === 'alpaca' && env === 'paper' && status === 'active' && authKind === 'oauth',
  );
}

function alpacaPaperApiKey(evidence: RemainingHopEvidence): boolean {
  return (evidence.connections ?? []).some(
    ([broker, env, status, authKind]) =>
      broker === 'alpaca' && env === 'paper' && status === 'active' && authKind === 'api_key',
  );
}

function digestLogPresent(evidence: RemainingHopEvidence): boolean {
  return (evidence.digest_event_keys ?? []).some((key) => key.startsWith('digest:'));
}

export function provenRemainingHops(evidence: RemainingHopEvidence): RemainingHopProven {
  const alpaca = alpacaPaperOauth(evidence);
  const overlay = (evidence.jobs ?? []).some(
    ([jobType, status]) => jobType === 'overlay_daily' && OVERLAY_RUN_STATUSES.has(status),
  );
  const digestLog = digestLogPresent(evidence);
  return {
    browser_stripe_checkout:
      evidence.subscription_status === 'active' &&
      evidence.has_stripe_subscription === true &&
      STRIPE_CHECKOUT_TIERS.has(evidence.plan_tier ?? ''),
    alpaca_paper_oauth_connect: alpaca,
    overlay_daily_claimed: overlay,
    paper_fill_mirrored: (evidence.fill_count ?? 0) > 0 && alpaca,
    digest_email_received:
      evidence.digest_inbox_confirmed === true &&
      digestLog &&
      evidence.daily_digest_enabled === true,
  };
}

export function remainingHopBlockers(evidence: RemainingHopEvidence): RemainingHopBlockers {
  const proven = provenRemainingHops(evidence);
  const blockers: RemainingHopBlockers = {};
  if (!proven.browser_stripe_checkout) {
    if (!STRIPE_CHECKOUT_TIERS.has(evidence.plan_tier ?? '')) {
      blockers.browser_stripe_checkout = 'plan_tier_not_studio';
    } else if (evidence.has_stripe_subscription !== true) {
      blockers.browser_stripe_checkout = 'missing_stripe_ids';
    } else {
      blockers.browser_stripe_checkout = 'subscription_not_active';
    }
  }
  if (!proven.alpaca_paper_oauth_connect) {
    blockers.alpaca_paper_oauth_connect = alpacaPaperApiKey(evidence)
      ? 'alpaca_api_key_not_oauth'
      : 'no_alpaca_paper_oauth';
  }
  if (!proven.overlay_daily_claimed) {
    const overlayStatuses = new Set(
      (evidence.jobs ?? [])
        .filter(([jobType]) => jobType === 'overlay_daily')
        .map(([, status]) => status),
    );
    if (overlayStatuses.has('persist_disabled')) {
      blockers.overlay_daily_claimed = 'overlay_persist_disabled';
    } else if ((evidence.overlay_job_errors ?? []).includes('legacy_book_unique')) {
      blockers.overlay_daily_claimed = 'overlay_legacy_book_unique';
    } else {
      blockers.overlay_daily_claimed = 'overlay_not_succeeded';
    }
  }
  if (!proven.paper_fill_mirrored) {
    blockers.paper_fill_mirrored = (evidence.fill_count ?? 0) > 0 ? 'fill_without_oauth' : 'no_paper_fill';
  }
  if (!proven.digest_email_received) {
    if (evidence.daily_digest_enabled !== true) {
      blockers.digest_email_received = 'digest_pref_off';
    } else if (!digestLogPresent(evidence)) {
      blockers.digest_email_received = 'no_digest_log';
    } else {
      blockers.digest_email_received = 'digest_inbox_unconfirmed';
    }
  }
  return blockers;
}

export const REMAINING_HOP_LABELS: Record<RemainingLiveHop, string> = {
  browser_stripe_checkout: 'Stripe checkout',
  alpaca_paper_oauth_connect: 'Alpaca paper OAuth',
  overlay_daily_claimed: 'Overlay daily succeeded',
  paper_fill_mirrored: 'Paper fill mirrored',
  digest_email_received: 'Digest email received',
};

export const REMAINING_HOP_BLOCKER_LABELS: Record<RemainingHopBlockerCode, string> = {
  plan_tier_not_studio: 'Studio Stripe checkout required',
  missing_stripe_ids: 'no Stripe subscription ids',
  subscription_not_active: 'subscription not active',
  alpaca_api_key_not_oauth: 'api_key paper does not prove OAuth',
  no_alpaca_paper_oauth: 'no Alpaca paper OAuth',
  overlay_persist_disabled: 'overlay persist disabled',
  overlay_legacy_book_unique: 'legacy UNIQUE(date) still blocks overlay',
  overlay_not_succeeded: 'no succeeded overlay_daily job',
  fill_without_oauth: 'fill without Alpaca paper OAuth',
  no_paper_fill: 'no paper fill',
  digest_pref_off: 'daily_digest pref off',
  no_digest_log: 'no digest: log key',
  digest_inbox_unconfirmed: 'inbox confirmation missing',
};
