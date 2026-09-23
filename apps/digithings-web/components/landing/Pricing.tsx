import { CtaLink, PricingMatrix, type PricingMatrixGroup, type PricingMatrixTier } from "@digithings/ui";
import { REPO_URL } from "@/lib/repoActivity";

/**
 * The pricing band (v15, stage 7, #4429 — point 12; Round 3, point 9; Round 4).
 *
 * The owner asked for the *digiweb comparison table* here — the one the pricing
 * page uses — so this is the kit's `PricingMatrix`: one column per integration
 * type, one group per axis, and the price stated in the tier header. His
 * instruction for the pricing column was exact: show **zero** for self-hosting,
 * because it is all open source and MIT, and for the service show **on contact**,
 * determined by the project scope.
 *
 * Round 4 changes, all from the walkthrough:
 *   - "make the integration service background different so it stands out a bit,
 *     because that's what we're trying to sell" — so the service tier is the
 *     `popular` column, which the component paints with an accent top rule and a
 *     tinted body. It is the honest reading: the offer really does point at it.
 *   - "when where it says on contact that should be a button that they could
 *     press and it should route them to the bottom where the contact form is" —
 *     the tier's CTA slot now holds a link to `/#contact`, which is the stable
 *     anchor the nav and the footer already use (`scroll-margin-top` is set for
 *     it in globals.css).
 *   - "add more detail on every line" — every row says who does what and what
 *     happens at the edges, rather than restating the tier name.
 *   - "remove the description of there is no public package prices... keep it
 *     simple with the table" — the footnote is gone.
 *
 * The only figure on this table is the true one: $0 for the MIT self-host path.
 * No `popularLabel`: with one offer, "most popular" would be a claim the page
 * cannot support.
 */

const TIERS: PricingMatrixTier[] = [
  {
    name: "self-host",
    price: "$0",
    cta: (
      <CtaLink href={REPO_URL} external className="text-[0.78rem]">
        Clone the repo
      </CtaLink>
    ),
  },
  {
    name: "integration service",
    price: "on contact",
    popular: true,
    cta: <CtaLink href="/#contact">Talk to us</CtaLink>,
  },
];

const GROUPS: PricingMatrixGroup[] = [
  {
    label: "cost",
    rows: [
      {
        label: "what you pay",
        cells: ["$0 — MIT, no account, no trial", "quoted per project, in writing, before work starts"],
      },
      {
        label: "what you are billed for",
        cells: ["nothing", "the integration work: scoping, wiring, handover"],
      },
      {
        label: "what recurs",
        cells: ["nothing", "nothing — further work is a new scope"],
      },
    ],
  },
  {
    label: "what you run",
    rows: [
      { label: "the code", cells: ["the whole monorepo, every module", "the modules you need, fitted in"] },
      { label: "the hosts", cells: ["your machines, your regions", "your machines — we deploy into them"] },
      {
        label: "the keys and providers",
        cells: ["yours, BYOK throughout", "yours — we wire the provider config"],
      },
      {
        label: "the updates",
        cells: ["pull from main whenever you want", "brought forward as each release lands, until handover"],
      },
    ],
  },
  {
    label: "the terms",
    rows: [
      { label: "who holds the keys", cells: ["you do, on your host", "you do — we wire them together"] },
      { label: "support", cells: ["docs, OpenAPI, issue tracker", "the same, plus a runbook for your deployment"] },
      {
        label: "when a module breaks upstream",
        cells: ["pin a version, or send a patch", "we take it upstream and bring the fix back"],
      },
      { label: "after handover", cells: ["—", "the stack is yours to run"] },
    ],
  },
];

export function Pricing() {
  return (
    <PricingMatrix
      tiers={TIERS}
      groups={GROUPS}
      featureColumnLabel="the detail"
      className="min-w-0"
    />
  );
}
