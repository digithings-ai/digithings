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
 * Round 5: "the free self-host versus integration service comparison table is
 * good well formatted i would just add more detail give it more information
 * detail of what we do". So the table gained a fourth group — "the work", which
 * describes the engagement itself (how it starts, who does it, what lands, how
 * long, what we need) — and three rows on the existing axes (how a price is
 * reached, the interface you build against, the audit trail). Every new cell is
 * still a description of a real practice, not a restatement of the tier name,
 * and no new figure is introduced.
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
      {
        label: "how the number is reached",
        cells: [
          "you read the docs and decide; there is no quote to request",
          "one working session against your environment, then a written scope",
        ],
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
        label: "the interface you build against",
        cells: [
          "the OpenAPI specs and the MCP tools, as documented",
          "the same surface, fitted to the clients you already have",
        ],
      },
      {
        label: "the updates",
        cells: ["pull from main whenever you want", "brought forward as each release lands, until handover"],
      },
    ],
  },
  {
    label: "the work",
    rows: [
      {
        label: "how it starts",
        cells: [
          "you clone it; no call is required",
          "a short call, then read access to what you are running today",
        ],
      },
      {
        label: "who does it",
        cells: ["you and whoever you have", "the maintainers of the modules you are wiring"],
      },
      {
        label: "what lands at the end",
        cells: [
          "a running stack, and the docs it ships with",
          "the deployment, a runbook, and a walkthrough of the seams we moved",
        ],
      },
      {
        label: "how long it takes",
        cells: ["however long you give it", "quoted with the scope, in working days"],
      },
      {
        label: "what we need from you",
        cells: ["—", "a point of contact, your providers, and access to a staging environment"],
      },
    ],
  },
  {
    label: "the terms",
    rows: [
      { label: "who holds the keys", cells: ["you do, on your host", "you do — we wire them together"] },
      { label: "support", cells: ["docs, OpenAPI, issue tracker", "the same, plus a runbook for your deployment"] },
      {
        label: "the audit trail",
        cells: [
          "every call, tool and result in a log on your disk",
          "the same log, plus a deployment checklist you can hand to security",
        ],
      },
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
