import { SortableTable, type SortableColumn } from "@digithings/ui";

/**
 * The pricing band (v15, stage 7, #4429 — point 12).
 *
 * The owner asked for this as a *digiweb table*, not two prose cards: the rows
 * are the two integration TYPES — self-host the MIT stack yourself, or take the
 * scoped integration service — and the columns answer the question a buyer
 * actually asks: what it costs, what you run, who holds the keys, who supports
 * it. Sorting is the point of the primitive, so the frame stays out of its way.
 *
 * That replaces the v13 two-up, which double-stated the same two types under
 * two headings. The CTAs stay (they were the useful half of the cards), one row
 * per type, so nothing about the offer is lost — only the prose volume.
 *
 * Round 2: the CTA block the cards carried is gone too. The owner's instruction
 * was "remove the buttons, I just want that comparison table here", and it was
 * the same "read the docs buttons all over the place" complaint he raised for
 * the argument band. The table plus its footnote is the whole section now.
 *
 * Two honesty positions from the cards survive verbatim in the footnote, because
 * neither is a formatting choice: there are still no public prices (that is the
 * same position /services states, and inventing a number would contradict it),
 * and the hosted docs MCP is still roadmap, not shipped — today the MCP surfaces
 * are the ones the stack runs itself, on your host.
 *
 * No `tone` on any column: the up/down money colours are reserved for figures,
 * and there are no figures here to colour.
 */

type IntegrationRow = {
  type: string;
  cost: string;
  youRun: string;
  keys: string;
  support: string;
};

const ROWS: IntegrationRow[] = [
  {
    type: "01 self-host",
    cost: "$0 · MIT, no account",
    youRun: "the monorepo, on your hosts",
    keys: "yours, end to end",
    support: "docs, OpenAPI, issue tracker",
  },
  {
    type: "02 integration service",
    cost: "scoped · quoted in writing",
    youRun: "the modules you need, fitted in",
    keys: "yours — we wire them up",
    support: "deploy, docs, handover",
  },
];

const COLUMNS: SortableColumn<IntegrationRow>[] = [
  { key: "type", label: "integration type", emphasis: true },
  { key: "cost", label: "cost basis" },
  { key: "youRun", label: "what you run" },
  { key: "keys", label: "who holds the keys" },
  { key: "support", label: "support" },
];

export function Pricing() {
  return (
    <div className="flex flex-col gap-[1.4rem]">
      <SortableTable
        rows={ROWS}
        columns={COLUMNS}
        rowKey={(r) => r.type}
        defaultSort={{ key: "type", dir: "asc" }}
      />

      <p className="m-0 max-w-[var(--measure-prose)] text-[0.78rem] leading-[1.7] text-ink-mute">
        There are no public package prices: the work is scoped for each environment, so a number
        before the scope would be a guess dressed as a rate. A hosted docs MCP — one public
        endpoint an agent can point at — is roadmap, not shipped; today the MCP surfaces are the
        ones you run yourself.
      </p>
    </div>
  );
}
