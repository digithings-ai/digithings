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
  loop: string;
  notes: readonly string[];
  receipt: readonly string[];
};

/** Four workflows on one infrastructure. The last two are not finished.
 *  Each graph is a picture of the orchestration, not a recorded run. */
const WORKFLOWS: readonly Workflow[] = [
  {
    name: "Research",
    body: "digiquant baseline research. Theme-delegated sub-agents search the web and read a custom knowledge base. It runs on digithings, on digigraph and the digithings infrastructure.",
    loop: "search again until the theme is covered",
    graph: [
      { nodes: [{ label: "Theme", tone: "main" }] },
      {
        nodes: [
          { label: "Web search", tone: "side" },
          { label: "Custom knowledge base", tone: "side" },
        ],
      },
      { nodes: [{ label: "digigraph", tone: "model" }] },
    ],
    notes: [
      "The theme sets the question",
      "Web search and the knowledge base run together",
      "digigraph orchestrates the pass on digithings",
    ],
    receipt: [
      "theme · question",
      "web search · in parallel",
      "knowledge base · in parallel",
      "digigraph · orchestrate",
    ],
  },
  {
    name: "Investment portfolio",
    body: "digiquant baseline portfolio. Thesis generation, then stock analysis, then deliberation with portfolio management and the investment preferences.",
    loop: "deliberate again until the thesis holds",
    graph: [
      { nodes: [{ label: "Thesis generation", tone: "main" }] },
      { nodes: [{ label: "Stock analysis", tone: "model" }] },
      {
        nodes: [
          { label: "Portfolio management", tone: "side" },
          { label: "Investment preferences", tone: "side" },
        ],
      },
      { nodes: [{ label: "Deliberation", tone: "model" }] },
    ],
    notes: [
      "Thesis generation opens the pass",
      "Stock analysis reads the names",
      "Portfolio management and the investment preferences sit together",
      "Deliberation closes the pass",
    ],
    receipt: [
      "thesis · open",
      "stock analysis · read",
      "portfolio management · in parallel",
      "investment preferences · in parallel",
      "deliberation · close",
    ],
  },
  {
    name: "Strategy building",
    status: "in development",
    body: "Workflows that help an agent turn an idea into an algorithmic strategy, backtest it, and ship a strategy that has been backtested.",
    loop: "backtest again until the idea holds or the run stops",
    graph: [
      { nodes: [{ label: "Idea", tone: "main" }] },
      { nodes: [{ label: "Algorithmic strategy", tone: "model" }] },
      { nodes: [{ label: "Backtest", tone: "side" }] },
      { nodes: [{ label: "Ship the backtested strategy", pending: true }] },
    ],
    notes: [
      "An idea becomes an algorithmic strategy",
      "The backtest is the check",
      "Shipping the backtested strategy is not finished",
    ],
    receipt: [
      "idea · open",
      "algorithmic strategy · draft",
      "backtest · check",
      "ship · pending",
    ],
  },
  {
    name: "Trade setups",
    status: "in development",
    body: "From research, prices, and charts, long or short ideas on asset pairs.",
    later:
      "Reliable setups with an entry, a stop, and a target, then monitoring. The system builds trade levels from different criteria, and an agent selects the one it judges most viable. Technical judgment on the chart.",
    loop: "watch again while a setup is open",
    graph: [
      {
        nodes: [
          { label: "Research", tone: "side" },
          { label: "Prices", tone: "side" },
          { label: "Charts", tone: "side" },
        ],
      },
      { nodes: [{ label: "Long or short on a pair", tone: "main" }] },
      { nodes: [{ label: "Levels from different criteria", pending: true }] },
      { nodes: [{ label: "Agent selects a level", pending: true }] },
      { nodes: [{ label: "Entry, stop, and target", pending: true }] },
      { nodes: [{ label: "Monitoring", pending: true }] },
    ],
    notes: [
      "Research, prices, and charts arrive together",
      "The picture is long or short on a pair",
      "Levels, the selection, and monitoring are not finished",
    ],
    receipt: [
      "research · prices · charts",
      "pair · long or short",
      "levels · pending",
      "selection · pending",
      "monitoring · pending",
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
            <WorkflowGraph
              label={`${workflow.name} orchestration`}
              steps={workflow.graph}
              loop={workflow.loop}
              notes={workflow.notes}
              receipt={workflow.receipt}
            />
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
