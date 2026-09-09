/**
 * Consumer list prices for Brief / Desk / Studio.
 *
 * Display only — Checkout still charges the Stripe `price_…` ids in Edge
 * Function secrets. Keep these cents in lockstep with the live Stripe
 * products (Brief $10/mo $96/yr, Desk $30/mo $288/yr, Studio $100/mo $960/yr).
 * Annual is 20% off twelve months of the monthly list.
 */

export type PaidCheckoutTier = 'brief' | 'desk' | 'studio';
export type BillingInterval = 'monthly' | 'annual';

/** Annual prepay percent off twelve months of monthly. Toggle copy must match. */
export const ANNUAL_OFF_PERCENT = 20;

export type PaidPlanCatalogEntry = {
  id: PaidCheckoutTier;
  name: string;
  blurb: string;
  monthlyCents: number;
  annualCents: number;
};

export function annualCentsFromMonthly(monthlyCents: number): number {
  return Math.round((monthlyCents * 12 * (100 - ANNUAL_OFF_PERCENT)) / 100);
}

export const PAID_PLAN_CATALOG: readonly PaidPlanCatalogEntry[] = [
  {
    id: 'brief',
    name: 'Brief',
    blurb: 'Full digest and house portfolio.',
    monthlyCents: 1_000,
    annualCents: annualCentsFromMonthly(1_000),
  },
  {
    id: 'desk',
    name: 'Desk',
    blurb: 'House pipeline and paper brokers.',
    monthlyCents: 3_000,
    annualCents: annualCentsFromMonthly(3_000),
  },
  {
    id: 'studio',
    name: 'Studio',
    blurb: 'Overlay, private book, and BYOK.',
    monthlyCents: 10_000,
    annualCents: annualCentsFromMonthly(10_000),
  },
];

export type AnnualDiscount = {
  yearAtMonthlyCents: number;
  savedCents: number;
  /** Rounded whole percent off the monthly-for-a-year list (20 at ANNUAL_OFF_PERCENT). */
  discountPercent: number;
  /** Annual ÷ 12, rounded to the nearest cent. */
  equivalentMonthlyCents: number;
  /** savedCents / monthlyCents — 2.4 when annual is 20% off. */
  monthsFree: number;
};

export function annualDiscount(monthlyCents: number, annualCents: number): AnnualDiscount {
  const yearAtMonthlyCents = monthlyCents * 12;
  const savedCents = Math.max(0, yearAtMonthlyCents - annualCents);
  const discountPercent =
    yearAtMonthlyCents === 0 ? 0 : Math.round((savedCents * 100) / yearAtMonthlyCents);
  const equivalentMonthlyCents = Math.round(annualCents / 12);
  const monthsFree = monthlyCents === 0 ? 0 : savedCents / monthlyCents;
  return {
    yearAtMonthlyCents,
    savedCents,
    discountPercent,
    equivalentMonthlyCents,
    monthsFree,
  };
}

export function formatUsdFromCents(cents: number): string {
  const dollars = cents / 100;
  if (Number.isInteger(dollars)) return `$${dollars}`;
  return `$${dollars.toFixed(2)}`;
}

export type PlanPriceLines = {
  /** Hero figure: "$10/mo" or the annual equivalent "$8/mo". */
  hero: string;
  /** Struck monthly list when showing annual; null on monthly. */
  listStruck: string | null;
  /** Percent off the monthly list ("20% off"); null on monthly. */
  discount: string | null;
  /** Caption under the hero ("billed $96/yr"). */
  caption: string | null;
};

export function planPriceLines(
  plan: PaidPlanCatalogEntry,
  interval: BillingInterval,
): PlanPriceLines {
  if (interval === 'monthly') {
    return {
      hero: `${formatUsdFromCents(plan.monthlyCents)}/mo`,
      listStruck: null,
      discount: null,
      caption: null,
    };
  }
  const offer = annualDiscount(plan.monthlyCents, plan.annualCents);
  return {
    hero: `${formatUsdFromCents(offer.equivalentMonthlyCents)}/mo`,
    listStruck: `${formatUsdFromCents(plan.monthlyCents)}/mo`,
    discount: offer.discountPercent > 0 ? `${offer.discountPercent}% off` : null,
    caption: `billed ${formatUsdFromCents(plan.annualCents)}/yr`,
  };
}

/** Shared toggle label — live catalog is ANNUAL_OFF_PERCENT off monthly. */
export function annualToggleLabel(): string {
  const first = PAID_PLAN_CATALOG[0];
  if (!first) return 'Annual';
  const offer = annualDiscount(first.monthlyCents, first.annualCents);
  if (offer.discountPercent > 0) {
    return `Annual · ${offer.discountPercent}% off`;
  }
  return 'Annual';
}
