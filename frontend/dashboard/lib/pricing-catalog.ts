/**
 * Consumer list prices for Brief / Desk / Studio.
 *
 * Display only — Checkout still charges the Stripe `price_…` ids in Edge
 * Function secrets. Keep these cents in lockstep with the live Stripe
 * products (Brief $10/mo $100/yr, Desk $30/mo $300/yr, Studio $100/mo $1000/yr).
 * Annual is ten months of the monthly list (17% off monthly).
 */

export type PaidCheckoutTier = 'brief' | 'desk' | 'studio';
export type BillingInterval = 'monthly' | 'annual';

export type PaidPlanCatalogEntry = {
  id: PaidCheckoutTier;
  name: string;
  blurb: string;
  monthlyCents: number;
  annualCents: number;
};

export const PAID_PLAN_CATALOG: readonly PaidPlanCatalogEntry[] = [
  {
    id: 'brief',
    name: 'Brief',
    blurb: 'Full digest and house portfolio.',
    monthlyCents: 1_000,
    annualCents: 10_000,
  },
  {
    id: 'desk',
    name: 'Desk',
    blurb: 'House pipeline and paper brokers.',
    monthlyCents: 3_000,
    annualCents: 30_000,
  },
  {
    id: 'studio',
    name: 'Studio',
    blurb: 'Overlay, private book, and BYOK.',
    monthlyCents: 10_000,
    annualCents: 100_000,
  },
] as const;

export type AnnualDiscount = {
  yearAtMonthlyCents: number;
  savedCents: number;
  /** Rounded whole percent off the monthly-for-a-year list (17 for 2/12). */
  discountPercent: number;
  /** Annual ÷ 12, rounded to the nearest cent. */
  equivalentMonthlyCents: number;
  /** savedCents / monthlyCents — 2 when annual is ten months of monthly. */
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
  /** Hero figure: "$10/mo" or the annual equivalent "$8.33/mo". */
  hero: string;
  /** Struck monthly list when showing annual; null on monthly. */
  listStruck: string | null;
  /** Percent off the monthly list ("17% off"); null on monthly. */
  discount: string | null;
  /** Caption under the hero ("billed $100/yr"). */
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

/** Shared toggle label — live catalog is 17% off monthly (ten months of twelve). */
export function annualToggleLabel(): string {
  const first = PAID_PLAN_CATALOG[0];
  if (!first) return 'Annual';
  const offer = annualDiscount(first.monthlyCents, first.annualCents);
  if (offer.discountPercent > 0) {
    return `Annual · ${offer.discountPercent}% off`;
  }
  return 'Annual';
}
