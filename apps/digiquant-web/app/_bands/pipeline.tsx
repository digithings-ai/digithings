import { DeckCard, DeckStack } from "@digithings/ui";
import { Badge } from "@digithings/ui/ui";
import { WorkflowGraph, type GraphStep } from "@/components/pipeline/workflow-graph";
import { Band } from "../_chrome/Band";

type Workflow = {
  name: string;
  /** Only the unfinished workflows carry a badge. */
  status?: "in development";
  body: string;
  later?: string;
  graph: readonly GraphStep[];
};

/** Four workflows on one infrastructure. The last two are not finished.
 *  Each graph is a picture of the orchestration, not a recorded run. */
const WORKFLOWS: readonly Workflow[] = [
  {
    name: "Research",
    body: "digiquant baseline research. Theme-delegated sub-agents search the web and read a custom knowledge base, including the 12x terminal. It runs on digithings, on digigraph and the digithings infrastructure.",
    graph: [
      { nodes: [{ label: "Theme" }] },
      {
        nodes: [{ label: "Web search" }, { label: "Custom knowledge base" }, { label: "12x terminal" }],
      },
      { nodes: [{ label: "digigraph" }] },
    ],
  },
  {
    name: "Investment portfolio",
    body: "digiquant baseline portfolio. Thesis generation, then stock analysis, then deliberation with portfolio management and the investment preferences.",
    graph: [
      { nodes: [{ label: "Thesis generation" }] },
      { nodes: [{ label: "Stock analysis" }] },
      {
        nodes: [{ label: "Portfolio management" }, { label: "Investment preferences" }],
      },
      { nodes: [{ label: "Deliberation" }] },
    ],
  },
  {
    name: "Strategy building",
    status: "in development",
    body: "Workflows that help an agent turn an idea into an algorithmic strategy, backtest it, and ship a strategy that has been backtested.",
    graph: [
      { nodes: [{ label: "Idea" }] },
      { nodes: [{ label: "Algorithmic strategy" }] },
      { nodes: [{ label: "Backtest" }] },
      { nodes: [{ label: "Ship the backtested strategy" }] },
    ],
  },
  {
    name: "Trade setups",
    status: "in development",
    body: "From research, prices, and charts, long or short ideas on asset pairs — the 12x work.",
    later:
      "Reliable setups with an entry, a stop, and a target, then monitoring. The system builds trade levels from different criteria, and an agent selects the one it judges most viable. Technical judgment on the chart.",
    graph: [
      {
        nodes: [{ label: "Research" }, { label: "Prices" }, { label: "Charts" }],
      },
      { nodes: [{ label: "Long or short on a pair" }] },
      { nodes: [{ label: "Levels from different criteria", pending: true }] },
      { nodes: [{ label: "Agent selects a level", pending: true }] },
      { nodes: [{ label: "Entry, stop, and target", pending: true }] },
      { nodes: [{ label: "Monitoring", pending: true }] },
    ],
  },
];

/** Homepage `#pipeline`. The digiweb card deck: each card slides up and stacks.
 *  Not the old runway that grew by extra viewports. `/app/pipeline` is untouched. */
export function PipelineBand() {
  return (
    <Band
      id="pipeline"
      plain
      title="Agent orchestration"
      takeaway="Workflows, graphs, and orchestrations. Research and the investment portfolio run. Each card is a picture of that graph, not a live run. None of them places an order."
    >
      <DeckStack
        className="[--deck-top:calc(var(--nav-shell-h,62px)+0.75rem)]"
        ariaLabel="digiquant workflows"
        rail={WORKFLOWS.map((workflow) => workflow.name)}
        railAriaLabel="Workflows"
      >
        {WORKFLOWS.map((workflow, index) => (
          <DeckCard key={workflow.name} className="flex flex-col gap-4 px-6 py-6 md:px-8 md:py-7">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
              <span className="font-mono text-[0.72rem] tracking-[0.08em] text-ink-mute">
                {String(index + 1).padStart(2, "0")}
              </span>
              <h3 className="m-0 font-display text-[1.65rem] font-medium leading-tight tracking-[-0.02em] text-ink">
                {workflow.name}
              </h3>
              {workflow.status ? <Badge variant="neutral">{workflow.status}</Badge> : null}
            </div>
            <p className="m-0 max-w-[62ch] text-[0.9375rem] leading-[1.6] text-ink-soft">{workflow.body}</p>
            <WorkflowGraph label={`${workflow.name} orchestration`} steps={workflow.graph} />
            {workflow.later ? (
              <p className="m-0 max-w-[62ch] border-t border-hair pt-3 text-[0.9375rem] leading-[1.6] text-ink-soft">
                {workflow.later}
              </p>
            ) : null}
          </DeckCard>
        ))}
      </DeckStack>
    </Band>
  );
}
