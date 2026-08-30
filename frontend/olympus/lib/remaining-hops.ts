/**
 * Member-visible remaining-hop predicates.
 *
 * Mirrors ``digiquant.olympus.kairos.remaining_hops.proven_remaining_hops``.
 * The Settings About panel never claims digest inbox confirmation — that flag
 * is operator-only (`KAIROS_STAGING_DIGEST_INBOX_CONFIRMED`). Digest also
 * requires ``daily_digest`` on; dispatch skips prefs that are off. Paper fills
 * do not prove the hop unless an Alpaca paper OAuth connection is also present.
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

export type RemainingHopEvidence = {
  subscription_status?: string | null;
  has_stripe_subscription?: boolean;
  connections?: readonly (readonly [string, string, string, string])[];
  jobs?: readonly (readonly [string, string])[];
  fill_count?: number;
  digest_event_keys?: readonly string[];
  digest_inbox_confirmed?: boolean;
  daily_digest_enabled?: boolean;
};

export type RemainingHopProven = Record<RemainingLiveHop, boolean>;

export function remainingHopsUnproven(
  proven: Partial<Record<RemainingLiveHop, boolean>> | RemainingHopProven = {},
): RemainingLiveHop[] {
  return REMAINING_LIVE_HOPS.filter((name) => !proven[name]);
}

export function provenRemainingHops(evidence: RemainingHopEvidence): RemainingHopProven {
  const alpaca = (evidence.connections ?? []).some(
    ([broker, env, status, authKind]) =>
      broker === 'alpaca' && env === 'paper' && status === 'active' && authKind === 'oauth',
  );
  const overlay = (evidence.jobs ?? []).some(
    ([jobType, status]) => jobType === 'overlay_daily' && OVERLAY_RUN_STATUSES.has(status),
  );
  const digestLog = (evidence.digest_event_keys ?? []).some((key) => key.startsWith('digest:'));
  return {
    browser_stripe_checkout:
      evidence.subscription_status === 'active' && evidence.has_stripe_subscription === true,
    alpaca_paper_oauth_connect: alpaca,
    overlay_daily_claimed: overlay,
    paper_fill_mirrored: (evidence.fill_count ?? 0) > 0 && alpaca,
    digest_email_received:
      evidence.digest_inbox_confirmed === true &&
      digestLog &&
      evidence.daily_digest_enabled === true,
  };
}

export const REMAINING_HOP_LABELS: Record<RemainingLiveHop, string> = {
  browser_stripe_checkout: 'Stripe checkout',
  alpaca_paper_oauth_connect: 'Alpaca paper OAuth',
  overlay_daily_claimed: 'Overlay daily succeeded',
  paper_fill_mirrored: 'Paper fill mirrored',
  digest_email_received: 'Digest email received',
};
