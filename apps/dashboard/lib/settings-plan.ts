/**
 * Plan ladder derivation. Capabilities per rung come from the same `can()` map
 * that gates the app, so the copy cannot drift from real entitlements.
 * No usage/spend meters: no backend endpoint exists (see report).
 */
import { ARTIFACT_CLASSES, can, type ArtifactClass, type PlanTier } from '@/lib/entitlements';
import { PAID_PLAN_CATALOG, planPriceLines, type BillingInterval } from '@/lib/pricing-catalog';
import { planRungId } from '@/lib/settings-runs';

export const CAPABILITY_LABELS: Record<ArtifactClass, string> = {
  research: 'research',
  narrative: 'narrative',
  digest_summary: 'digest',
  portfolio_teaser: 'portfolio teaser',
  house_weights_nav: 'house portfolio',
  glassbox_economics: 'glass-box pipeline',
  private_book: 'private book',
  broker_status: 'paper brokers',
  overlay_profile: 'overlay and BYOK',
};

/** Classes unlocked at `tier` that the previous paid rung (or free) lacks. */
export function unlocksAt(tier: 'brief' | 'desk' | 'studio'): ArtifactClass[] {
  const prev: PlanTier = tier === 'brief' ? 'free' : tier === 'desk' ? 'brief' : 'desk';
  return ARTIFACT_CLASSES.filter((c) => can(tier, c) && !can(prev, c));
}

export type PlanRungView = {
  id: 'brief' | 'desk' | 'studio';
  name: string;
  blurb: string;
  price: string;
  unlocks: string;
  /** True when this rung is above the viewer, i.e. an upgrade target. */
  upgrade: boolean;
  current: boolean;
};

export function planRungs(tier: PlanTier, interval: BillingInterval): PlanRungView[] {
  const cur = planRungId(tier);
  const order = PAID_PLAN_CATALOG.map((p) => p.id);
  const curIdx = cur ? order.indexOf(cur) : -1;
  return PAID_PLAN_CATALOG.map((p, i) => ({
    id: p.id,
    name: p.name,
    blurb: p.blurb,
    price: planPriceLines(p, interval).hero,
    unlocks: unlocksAt(p.id)
      .map((c) => CAPABILITY_LABELS[c])
      .join(', '),
    upgrade: i > curIdx,
    current: i === curIdx,
  }));
}

/** Screen-reader sentence for the ladder. */
export function planSummary(tier: PlanTier, status?: string | null): string {
  const cur = planRungId(tier);
  const name = cur ? (PAID_PLAN_CATALOG.find((p) => p.id === cur)?.name ?? cur) : 'Observer';
  return `Current plan ${name}${status ? `, subscription ${status}` : ''}`;
}
