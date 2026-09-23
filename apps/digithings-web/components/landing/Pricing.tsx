import {
  PricingMatrix,
  type PricingMatrixGroup,
  type PricingMatrixTier,
} from "@digithings/ui";

/**
 * The pricing band (v15, stage 7, #4429 — point 12; Round 3, #4429 — point 9).
 *
 * Round 3: the owner asked for the *digiweb comparison table* here — the one the
 * pricing page uses — instead of the sortable row list. So this is the kit's
 * `PricingMatrix`: one column per integration type, one group per axis, and the
 * price stated in the tier header. His instruction for the pricing column was
 * exact: show **zero** for self-hosting, because it is all open source and MIT,
 * and for the service show **on contact**, determined by the project scope.
 *
 * Round 2 context that still holds: the CTA block is gone ("remove the buttons,
 * I just want that comparison table here"). No `popular` tier either — flagging
 * one column would invent a recommendation the offer does not make — and no
 * billing toggle, because there is no billing cycle to toggle.
 *
 * Two honesty positions survive in the footnote, because neither is a formatting
 * choice: there are no public package prices (that is the same position /services
 * states, and inventing a number would contradict it), and the hosted docs MCP is
 * still roadmap, not shipped — today the MCP surfaces are the ones the stack runs
 * itself, on your host.
 *
 * The only figure on this table is the true one: $0 for the MIT self-host path.
 */

const TIERS: PricingMatrixTier[] = [
  { name: "self-host", price: "$0" },
  { name: "integration service", price: "on contact" },
];

const GROUPS: PricingMatrixGroup[] = [
  {
    label: "cost basis",
    rows: [
      {
        label: "what you pay",
        cells: ["$0 · MIT, no account", "on contact, scoped to the project"],
      },
      {
        label: "what is quoted",
        cells: ["nothing to quote", "the scope, in writing, before work starts"],
      },
    ],
  },
  {
    label: "what you take",
    rows: [
      { label: "the code", cells: ["the whole monorepo, MIT", "the modules you need"] },
      {
        label: "the setup",
        cells: ["you run it, on your hosts", "we fit them into your environment"],
      },
      {
        label: "the updates",
        cells: ["pull from main, any time", "brought forward as the work lands"],
      },
    ],
  },
  {
    label: "the terms",
    rows: [
      {
        label: "who holds the keys",
        cells: ["yours, end to end", "yours — we wire them together"],
      },
      {
        label: "support",
        cells: ["docs, OpenAPI, issue tracker", "deploy, documentation, handover"],
      },
      { label: "after handover", cells: ["—", "the stack is yours to run"] },
    ],
  },
];

export function Pricing() {
  return (
    <div className="flex flex-col gap-[1.4rem]">
      <PricingMatrix
        tiers={TIERS}
        groups={GROUPS}
        featureColumnLabel="the detail"
        className="min-w-0"
      />

      <p className="m-0 max-w-[var(--measure-prose)] text-[0.78rem] leading-[1.7] text-ink-mute">
        There are no public package prices: self-hosting is free and MIT-licensed, and the
        integration work is scoped for each environment, so a number before the scope would be a
        guess dressed as a rate. A hosted docs MCP — one public endpoint an agent can point at — is
        roadmap, not shipped; today the MCP surfaces are the ones you run yourself.
      </p>
    </div>
  );
}
