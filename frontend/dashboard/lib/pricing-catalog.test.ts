import { describe, expect, it } from 'vitest';
import {
  annualDiscount,
  annualToggleLabel,
  formatUsdFromCents,
  PAID_PLAN_CATALOG,
  planPriceLines,
} from './pricing-catalog';

describe('pricing catalog', () => {
  it('pins live Stripe list prices (cents)', () => {
    expect(PAID_PLAN_CATALOG.map((p) => [p.id, p.monthlyCents, p.annualCents])).toEqual([
      ['brief', 1_000, 10_000],
      ['desk', 3_000, 30_000],
      ['studio', 10_000, 100_000],
    ]);
  });

  it('treats annual as two months free versus twelve months of monthly', () => {
    for (const plan of PAID_PLAN_CATALOG) {
      const offer = annualDiscount(plan.monthlyCents, plan.annualCents);
      expect(plan.annualCents).toBe(plan.monthlyCents * 10);
      expect(offer.monthsFree).toBe(2);
      expect(offer.savedCents).toBe(plan.monthlyCents * 2);
      expect(offer.discountPercent).toBe(17);
      expect(offer.equivalentMonthlyCents).toBeLessThan(plan.monthlyCents);
    }
  });

  it('formats whole dollars without cents and fractional as two places', () => {
    expect(formatUsdFromCents(1_000)).toBe('$10');
    expect(formatUsdFromCents(833)).toBe('$8.33');
    expect(formatUsdFromCents(2_500)).toBe('$25');
  });

  it('shows monthly as the list and annual as a discount over that list', () => {
    const brief = PAID_PLAN_CATALOG[0]!;
    expect(planPriceLines(brief, 'monthly')).toEqual({
      hero: '$10/mo',
      listStruck: null,
      discount: null,
      caption: null,
    });
    expect(planPriceLines(brief, 'annual')).toEqual({
      hero: '$8.33/mo',
      listStruck: '$10/mo',
      discount: '17% off',
      caption: 'billed $100/yr',
    });
    expect(planPriceLines(PAID_PLAN_CATALOG[1]!, 'annual')).toEqual({
      hero: '$25/mo',
      listStruck: '$30/mo',
      discount: '17% off',
      caption: 'billed $300/yr',
    });
    expect(planPriceLines(PAID_PLAN_CATALOG[2]!, 'annual')).toEqual({
      hero: '$83.33/mo',
      listStruck: '$100/mo',
      discount: '17% off',
      caption: 'billed $1000/yr',
    });
  });

  it('names the annual toggle as a percent off monthly', () => {
    expect(annualToggleLabel()).toBe('Annual · 17% off');
  });
});
