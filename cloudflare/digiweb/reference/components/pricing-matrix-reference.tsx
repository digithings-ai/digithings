/** Graphite's pricing system: grouped comparison rows, ✓/Limited/Advanced
 *  cells, an annual toggle (20% off), per-tier CTA verbs that escalate with
 *  commitment — and enterprise never shows a price. Display template consuming
 *  PricingMatrix from @digithings/web (the primitive owns the toggle state;
 *  both billing price lines are precomputed here). */
import { PricingMatrix, type PricingMatrixGroup, type PricingMatrixTier } from "@digithings/web";

const ANNUAL_OFF = 0.2; // the toggle is worth exactly what it says

const tier = (
  name: string,
  monthly: number | null,
  cta: string,
  kind: "quiet" | "primary" | "ghost",
  popular?: boolean,
): PricingMatrixTier => ({
  name,
  ...(monthly === null
    ? { price: "Let's talk" }
    : monthly === 0
      ? { price: "Free" }
      : {
          priceMonthly: `$${monthly}/mo`,
          priceAnnual: `$${Math.round(monthly * (1 - ANNUAL_OFF))}/mo`,
        }),
  cta: (
    <button
      type="button"
      className={kind === "primary" ? "btn-primary" : kind === "ghost" ? "btn-ghost" : "btn-quiet"}
    >
      {cta}
    </button>
  ),
  popular,
});

const TIERS: PricingMatrixTier[] = [
  tier("Hobby", 0, "Sign up", "quiet"),
  tier("Team", 40, "Start free trial", "primary", true),
  tier("Enterprise", null, "Request a demo", "ghost"),
];

const GROUPS: PricingMatrixGroup[] = [
  {
    label: "Backtesting",
    rows: [
      { label: "Strategies", cells: ["3", "Unlimited", "Unlimited"] },
      { label: "Bar history", cells: ["Limited", "Full", "Full"] },
      { label: "Walk-forward optimize", cells: ["—", "✓", "✓"] },
    ],
  },
  {
    label: "Live",
    rows: [
      { label: "Paper trading", cells: ["✓", "✓", "✓"] },
      { label: "Live adapters", cells: ["—", "Basic", "Advanced"] },
      { label: "Kill-switch SLA", cells: ["—", "—", "✓"] },
    ],
  },
  {
    label: "Support",
    rows: [
      { label: "Audit log", cells: ["—", "✓", "✓"] },
      { label: "SSO", cells: ["—", "—", "✓"] },
    ],
  },
];

export function PricingMatrixReference() {
  return (
    <section className="section-block" id="pricing-matrix">
      <p className="kicker">{"// comparison matrix"}</p>
      <h2 className="title">CTA verbs escalate with commitment.</h2>
      <p className="section-copy">
        Grouped rows, plain-word cells (✓ · Limited · Basic · Advanced), an annual toggle worth
        exactly what it says, and a different verb per tier: sign up, start, request. Enterprise
        never shows a price.
      </p>

      <PricingMatrix
        tiers={TIERS}
        groups={GROUPS}
        toggleLabel="Annual billing (20% off)"
        toggleClassName="mt-[1.2rem]"
        popularLabel="Most popular"
        className="mt-4"
      />
    </section>
  );
}
