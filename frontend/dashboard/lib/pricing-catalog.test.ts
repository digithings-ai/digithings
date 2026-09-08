import { describe, expect, it } from 'vitest';
import {
  ANNUAL_OFF_PERCENT,
  annualCentsFromMonthly,
  annualDiscount,
  annualToggleLabel,
  formatUsdFromCents,
  PAID_PLAN_CATALOG,
  planPriceLines,
} from './pricing-catalog';

describe('pricing catalog', () => {
  it('pins live Stripe list prices (cents) at 20% off annual', () => {
    expect(ANNUAL_OFF_PERCENT).toBe(20);
    expect(PAID_PLAN_CATALOG.map((p) => [p.id, p.monthlyCents, p.annualCents])).toEqual([
      ['brief', 1_000, 9_600],
      ['desk', 3_000, 28_800],
      ['studio', 10_000, 96_000],
    ]);
  });

  it('treats annual as 20% off twelve months of monthly', () => {
    for (const plan of PAID_PLAN_CATALOG) {
      const offer = annualDiscount(plan.monthlyCents, plan.annualCents);
      expect(plan.annualCents).toBe(annualCentsFromMonthly(plan.monthlyCents));
      expect(offer.discountPercent).toBe(20);
      expect(offer.savedCents).toBe(plan.monthlyCents * 12 - plan.annualCents);
      expect(offer.equivalentMonthlyCents).toBeLessThan(plan.monthlyCents);
    }
  });

  it('formats whole dollars without cents and fractional as two places', () => {
    expect(formatUsdFromCents(1_000)).toBe('$10');
    expect(formatUsdFromCents(800)).toBe('$8');
    expect(formatUsdFromCents(833)).toBe('$8.33');
    expect(formatUsdFromCents(2_400)).toBe('$24');
  });

  it('shows monthly as the list and annual as a percent off that list', () => {
    const brief = PAID_PLAN_CATALOG[0]!;
    expect(planPriceLines(brief, 'monthly')).toEqual({
      hero: '$10/mo',
      listStruck: null,
      discount: null,
      caption: null,
    });
    expect(planPriceLines(brief, 'annual')).toEqual({
      hero: '$8/mo',
      listStruck: '$10/mo',
      discount: '20% off',
      caption: 'billed $96/yr',
    });
    expect(planPriceLines(PAID_PLAN_CATALOG[1]!, 'annual')).toEqual({
      hero: '$24/mo',
      listStruck: '$30/mo',
      discount: '20% off',
      caption: 'billed $288/yr',
    });
    expect(planPriceLines(PAID_PLAN_CATALOG[2]!, 'annual')).toEqual({
      hero: '$80/mo',
      listStruck: '$100/mo',
      discount: '20% off',
      caption: 'billed $960/yr',
    });
  });

  it('names the annual toggle as a percent off monthly', () => {
    expect(annualToggleLabel()).toBe('Annual · 20% off');
  });
});
