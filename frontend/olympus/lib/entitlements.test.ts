import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Session } from '@supabase/supabase-js';
import {
  ALL_PLAN_TIERS,
  ARTIFACT_CLASSES,
  can,
  requiredTierFor,
  tierFromSession,
  type ArtifactClass,
  type PlanTier,
} from './entitlements';

/**
 * Spec §5-T5 matrix (verbatim semantics):
 *
 * | Artifact class                         | Observer (free) | Baseline | Custom |
 * | Atlas research / theses / corpus       | ✓               | ✓        | ✓      |
 * | Hermes narrative                       | ✓               | ✓        | ✓      |
 * | House weights / NAV / tearsheet / …    | —               | ✓        | ✓      |
 * | Pipeline glass-box economics           | —               | ✓        | ✓      |
 * | Private book / broker / overlay        | —               | —        | ✓      |
 *
 * Enterprise ≡ Custom for content entitlements.
 */
const MATRIX: Record<PlanTier, Record<ArtifactClass, boolean>> = {
  free: {
    research: true,
    narrative: true,
    house_weights_nav: false,
    glassbox_economics: false,
    private_book: false,
    broker_status: false,
    overlay_profile: false,
  },
  baseline: {
    research: true,
    narrative: true,
    house_weights_nav: true,
    glassbox_economics: true,
    private_book: false,
    broker_status: false,
    overlay_profile: false,
  },
  custom: {
    research: true,
    narrative: true,
    house_weights_nav: true,
    glassbox_economics: true,
    private_book: true,
    broker_status: true,
    overlay_profile: true,
  },
  enterprise: {
    research: true,
    narrative: true,
    house_weights_nav: true,
    glassbox_economics: true,
    private_book: true,
    broker_status: true,
    overlay_profile: true,
  },
};

describe('entitlements §5-T5 matrix', () => {
  it.each(
    ALL_PLAN_TIERS.flatMap((tier) =>
      ARTIFACT_CLASSES.map((cls) => ({ tier, cls, allowed: MATRIX[tier][cls] })),
    ),
  )('$tier × $cls → $allowed', ({ tier, cls, allowed }) => {
    expect(can(tier, cls)).toBe(allowed);
  });

  it('covers every tier × class cell (no gaps in the table-driven suite)', () => {
    expect(ALL_PLAN_TIERS).toHaveLength(4);
    expect(ARTIFACT_CLASSES).toHaveLength(7);
    expect(ALL_PLAN_TIERS.length * ARTIFACT_CLASSES.length).toBe(28);
  });
});

describe('requiredTierFor', () => {
  it('maps classes to the minimum unlock tier', () => {
    expect(requiredTierFor('research')).toBe('free');
    expect(requiredTierFor('narrative')).toBe('free');
    expect(requiredTierFor('house_weights_nav')).toBe('baseline');
    expect(requiredTierFor('glassbox_economics')).toBe('baseline');
    expect(requiredTierFor('private_book')).toBe('custom');
    expect(requiredTierFor('broker_status')).toBe('custom');
    expect(requiredTierFor('overlay_profile')).toBe('custom');
  });
});

function sessionWithTier(planTier: unknown): Session {
  return {
    access_token: 'test',
    refresh_token: 'test',
    expires_in: 3600,
    token_type: 'bearer',
    user: {
      id: 'u1',
      app_metadata: { plan_tier: planTier },
      user_metadata: {},
      aud: 'authenticated',
      created_at: '2026-01-01T00:00:00Z',
    },
  } as Session;
}

describe('tierFromSession', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it('returns enterprise when NEXT_PUBLIC_OLYMPUS_AUTH is off (prod pre-cutover)', async () => {
    vi.resetModules();
    vi.stubEnv('NEXT_PUBLIC_OLYMPUS_AUTH', '');
    const { tierFromSession: tier } = await import('./entitlements');
    expect(tier(null)).toBe('enterprise');
    expect(tier(sessionWithTier('free'))).toBe('enterprise');
  });

  it('reads app_metadata.plan_tier when auth is on', async () => {
    vi.resetModules();
    vi.stubEnv('NEXT_PUBLIC_OLYMPUS_AUTH', '1');
    const { tierFromSession: tier } = await import('./entitlements');
    expect(tier(sessionWithTier('baseline'))).toBe('baseline');
    expect(tier(sessionWithTier('custom'))).toBe('custom');
    expect(tier(sessionWithTier('enterprise'))).toBe('enterprise');
    expect(tier(sessionWithTier('free'))).toBe('free');
  });

  it('falls back to free when auth is on and claim is missing or unknown', async () => {
    vi.resetModules();
    vi.stubEnv('NEXT_PUBLIC_OLYMPUS_AUTH', '1');
    const { tierFromSession: tier } = await import('./entitlements');
    expect(tier(null)).toBe('free');
    expect(tier(sessionWithTier(undefined))).toBe('free');
    expect(tier(sessionWithTier('gold'))).toBe('free');
  });
});
