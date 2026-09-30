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
 * Round 7 kept the shape and filled it in: "I like how simple it is. I would
 * just center it on the screen and add more detail so it's professional." So the
 * table is centred (`mx-auto`) and four rows joined — what each tier covers, how
 * the work starts, what we need from you, and who owns the result — bringing it
 * to eleven rows without going back to the sixteen-row sprawl he cut.
 *
 * The only figure on the table is the true one: $0 for the self-host path.
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
      <CtaLink href={REPO_URL} external className="text-[0.84rem]">
        Clone the repo
      </CtaLink>
    ),
  },
  {
    name: "service",
    price: "on contact",
    // Featured column (#4429 ship list): the table carries the section, so
    // the custom-build middle tier gets the gradient band. No `popularLabel`
    // — tinting is emphasis, not a recommendation of one tier over the others.
    popular: true,
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
        cells: ["$0 — no account", "scoped to the deployment", "scoped to the work"],
      },
      {
        label: "what it covers",
        cells: ["everything, no ceiling", "the deployment itself", "the engagement, end to end"],
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
        label: "how it starts",
        cells: [
          "clone it and read the docs",
          "a short call, then a written plan",
          "a scoping call and a proposal",
        ],
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
      {
        label: "what we need from you",
        cells: ["nothing", "hosts, keys and access", "hosts, keys and a named owner"],
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
        label: "who owns the result",
        cells: [
          "you — it stays yours",
          "you — the deployment stays yours",
          "you, and the custom work is handed over",
        ],
      },
      {
        label: "support",
        cells: [
          "docs, OpenAPI, issue tracker",
          "deployment, documentation, handover",
          "ongoing maintenance and upgrades",
        ],
      },
    ],
  },
];

export function Pricing() {
  return (
    <div className="w-full">
      <PricingMatrix
        tiers={TIERS}
        groups={GROUPS}
        featureColumnLabel="the detail"
        className="min-w-0 [&_table]:text-[0.94rem] [&_th]:text-[1rem] [&_td]:text-[0.86rem]"
      />
    </div>
  );
}
