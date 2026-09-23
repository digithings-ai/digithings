import { CtaLink, PricingMatrix, type PricingMatrixGroup, type PricingMatrixTier } from "@digithings/ui";
import { REPO_URL } from "@/lib/repoActivity";

/**
 * The pricing band (v15 stage 7 → round 6, #4429).
 *
 * The owner asked for the *digiweb comparison table* here, and in round 6 he
 * asked for it simpler and with a third tier:
 *
 *   "the self host versus integration service section i think it just needs to
 *    be a bit narrower it just feels a little spread out at the moment and the
 *    text isn't inviting to read it's too small there's too many rows i just
 *    keep it simple... it's self-host you take the repo you clone it and you
 *    integrate it yourself there's the service tier which is i build out an
 *    application or integrate or deploy an application in their stack and then
 *    i think we should add a third tier which is more of an enterprise which is
 *    with maintenance and upgrades and custom implementations we should keep it
 *    at three tiers and the third is custom the second is just deploying digi
 *    chat in their environment and just doing the deployment services the setup
 *    of the existing service with no customization beyond what is already
 *    customizable no additional features or custom integrations"
 *
 * So: three tiers, seven rows (down from sixteen), a narrower column, and the
 * body type stepped up one notch. The three offers are exactly his three:
 * self-host (clone and integrate it yourself), the service (we deploy the
 * existing product into your environment, no custom work), and enterprise
 * (maintenance, upgrades, custom implementations).
 *
 * The only figure on the table is the true one: $0 for the MIT self-host path.
 * No `popular` column — flagging one of three would invent a recommendation —
 * and no billing toggle, because there is no billing cycle.
 *
 * The type step and the width live on the wrapper as arbitrary utilities rather
 * than as a kit prop: `PricingMatrix` is shared with the reference and the
 * digiquant pricing page, and one page wanting a roomier table is not a reason
 * to change its public API.
 */

const TIERS: PricingMatrixTier[] = [
  {
    name: "self-host",
    price: "$0",
    cta: (
      <CtaLink href={REPO_URL} external className="text-[0.82rem]">
        Clone the repo
      </CtaLink>
    ),
  },
  {
    name: "service",
    price: "on contact",
    cta: <CtaLink href="/#contact">Talk to us</CtaLink>,
  },
  {
    name: "enterprise",
    price: "custom",
    cta: <CtaLink href="/#contact">Talk to us</CtaLink>,
  },
];

const GROUPS: PricingMatrixGroup[] = [
  {
    label: "price",
    rows: [
      {
        label: "what you pay",
        cells: ["$0 — MIT, no account", "scoped to the deployment", "scoped to the work"],
      },
      {
        label: "what is quoted",
        cells: ["nothing to quote", "the deployment, in writing", "the scope and the timeline"],
      },
    ],
  },
  {
    label: "the work",
    rows: [
      {
        label: "who does it",
        cells: ["you", "we deploy it", "we build it"],
      },
      {
        label: "what lands",
        cells: [
          "the monorepo, every module",
          "the existing product, running in your environment",
          "custom integrations, maintenance and upgrades",
        ],
      },
      {
        label: "what you can change",
        cells: ["anything", "what the stack already exposes", "whatever the engagement needs"],
      },
    ],
  },
  {
    label: "the terms",
    rows: [
      {
        label: "who holds the keys",
        cells: ["you do", "you do — we wire them up", "you do — we build around them"],
      },
      {
        label: "support",
        cells: ["docs, OpenAPI, issue tracker", "deployment, documentation, handover", "ongoing maintenance and upgrades"],
      },
    ],
  },
];

export function Pricing() {
  return (
    <div className="max-w-[52rem]">
      <PricingMatrix
        tiers={TIERS}
        groups={GROUPS}
        featureColumnLabel="the detail"
        className="min-w-0 [&_table]:text-[0.92rem] [&_th]:text-[0.98rem] [&_td]:text-[0.84rem]"
      />
    </div>
  );
}
