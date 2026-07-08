/**
 * Pricing — the open-core two-path shape (self-hosted vs. managed) with a
 * single filled CTA, plus a per-unit model price table. The two paths sit
 * side by side, the featured one tinted; the precision table rides the same
 * hairline-row, mono-numeral voice as our tearsheets. Static display template
 * consuming Pricing + PrecisionTable from @digithings/web.
 */
import { PrecisionTable, Pricing } from "@digithings/web";

const MODELS = [
  { model: "grok-parity-4.3", context: "256k", price: "$3.00" },
  { model: "grok-build-0.1", context: "128k", price: "$0.85" },
  { model: "grok-fast-0.2", context: "64k", price: "$0.20" },
];

export function PricingReference() {
  return (
    <section className="section-block pricing-ref">
      <p className="kicker">{"// pricing"}</p>
      <h2 className="title">Precision over persuasion.</h2>
      <p className="section-copy">
        x.ai runs exactly two paths — self-serve vs. talk to sales — with one filled CTA total.
        That is the open-core shape: self-hosted vs. managed. The per-unit table below rides the
        same hairline-row, mono-numeral voice as our tearsheets.
      </p>

      <Pricing
        className="mt-[1.2rem]"
        tiers={[
          {
            name: "Self-hosted",
            description:
              "Open core · BYOK · audit-on by default. All modules, usage-based inference.",
            cta: (
              <button type="button" className="btn-ghost">
                Read the docs
              </button>
            ),
          },
          {
            name: "Managed",
            accent: true,
            description: "Onboarding, custom limits, SSO, audit log, SLA-backed uptime.",
            cta: (
              <button type="button" className="btn-primary">
                Contact sales
              </button>
            ),
          },
        ]}
        footnote="Free for your first 30 days. No credit card required. Synced with your GitHub account."
      />

      <PrecisionTable
        className="mt-[1.2rem]"
        columns={["Model", "Context", "$/M tokens"]}
        rows={MODELS.map((row) => [row.model, row.context, row.price])}
      />
    </section>
  );
}
