import { DeckCard, DeckStack } from "@digithings/ui";
import { Badge } from "@digithings/ui/ui";
import { PipelineFlow, type FlowStep } from "@/components/pipeline/pipeline-flow";
import { Band } from "../_chrome/Band";

type Workflow = {
  name: string;
  /** Only the unfinished workflows carry a badge. */
  status?: "in development";
  body: string;
  later?: string;
  graph: readonly FlowStep[];
  loop: string;
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
  },
];

/** Homepage `#pipeline`. The digiweb card deck: each card slides up and stacks.
 *  Not the old runway that grew by extra viewports. `/app/pipeline` is untouched. */
export function PipelineBand() {
  return (
    <Band
      id="pipeline"
      plain
      pin
      title="Agent orchestration"
      takeaway="Workflows, graphs, and orchestrations. Research and the investment portfolio run. Each card is a picture of that graph, not a live run. None of them places an order."
    >
      {/* The head is pinned under the nav (globals.css .band-pin), so the deck
          stops at the pinned rule instead of riding up under it: nav clearance
          + the head's own height, which that stylesheet authors once. Below
          901px the deck drops sticky and the var is 0. */}
      <DeckStack
        className="[--deck-top:calc(var(--nav-shell-h,62px)+var(--band-pin-h,0px))]"
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
            <PipelineFlow
              label={`${workflow.name} orchestration`}
              steps={workflow.graph}
              loop={workflow.loop}
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
