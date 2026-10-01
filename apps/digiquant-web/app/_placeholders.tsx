import { IntegrationMark } from "@/components/integrations/marks";
import { Placeholder, Wire } from "./_chrome/Placeholder";

/** Layout placeholders for the showcase. Structure first: each one fixes a slot on
 *  the grid and says in its design note what will fill it. Nothing here is wired
 *  to data, brokers or iframes, and nothing implies trading. */

const BROKERS = [
  { id: "alpaca", name: "Alpaca" },
  { id: "ibkr", name: "Interactive Brokers" },
] as const;
const TABS = ["Profile", "Chart", "Financials", "News", "Filings"] as const;
const RANGES = ["1D", "1W", "1M", "1Y"] as const;
const STAGES = ["Inputs", "Research", "Synthesis", "Selection", "Decision", "Learning"] as const;
type Cell = "done" | "active" | "idle";
const SAMPLE_RUNS: { name: string; cells: Cell[] }[] = [
  { name: "sample run A", cells: ["done", "done", "done", "done", "done", "done"] },
  { name: "sample run B", cells: ["done", "done", "done", "done", "done", "idle"] },
  { name: "sample run C", cells: ["done", "done", "active", "idle", "idle", "idle"] },
];
const CELL_STYLE: Record<Cell, string> = {
  done: "border-ink-mute bg-ink/10",
  active: "border-accent",
  idle: "border-dashed border-hair",
};

/** DESIGN NOTE: a framed screenshot or embed of the digiquant dashboard, the
 *  product this page showcases. A recording replaces it once one exists. */
export function DashboardViewPlaceholder() {
  return (
    <Placeholder
      title="Dashboard · product view"
      note="A framed screenshot or embed of the digiquant dashboard: strategy builder, strategies and journal. This page shows the product; it does not rebuild it."
      bodyClassName="min-h-[16rem]"
    >
      <div className="grid h-full min-h-[14rem] grid-cols-[7rem_minmax(0,1fr)] gap-3 max-sm:grid-cols-[4rem_minmax(0,1fr)]">
        <div className="flex flex-col gap-2">
          {[0, 1, 2, 3, 4].map((i) => (
            <Wire key={i} className="h-5" />
          ))}
        </div>
        <div className="grid grid-rows-[auto_minmax(0,1fr)] gap-3">
          <Wire className="h-7" />
          <div className="grid grid-cols-2 gap-3">
            <Wire className="min-h-[6rem]" />
            <Wire className="min-h-[6rem]" />
            <Wire className="col-span-2 min-h-[6rem]" />
          </div>
        </div>
      </div>
    </Placeholder>
  );
}

/** DESIGN NOTE: the strategy path as the dashboard shows it. */
export function DashboardFlowPlaceholder() {
  const nodes = [
    { name: "digichat", sub: "describe the idea" },
    { name: "backtest + optimize", sub: "the quant engine" },
    { name: "inspect + hand off", sub: "review, then export" },
  ];
  return (
    <Placeholder
      title="Dashboard pipeline · strategy path"
      note="The strategy path as the dashboard shows it: digichat, then the backtester and optimizer, then inspect and hand off. Final art comes from the dashboard."
      bodyClassName="min-h-0"
    >
      <ol className="m-0 grid list-none items-stretch gap-3 p-0 font-mono md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_auto_minmax(0,1fr)]">
        {nodes.flatMap((node, i) => [
          <li key={node.name} className="flex flex-wrap items-baseline gap-x-2 border border-dashed border-hair px-3 py-2">
            <span className="text-[0.62rem] text-ink-mute">[{String(i + 1).padStart(2, "0")}]</span>
            <span className="text-[0.82rem] text-ink">{node.name}</span>
            <span className="text-[0.68rem] text-ink-mute">{node.sub}</span>
          </li>,
          i < nodes.length - 1 ? (
            <li key={`${node.name}-arrow`} className="grid place-items-center text-ink-mute max-md:hidden">
              →
            </li>
          ) : null,
        ])}
      </ol>
    </Placeholder>
  );
}

/** DESIGN NOTE: static mock of a run timeline. Real runs replace the rows. */
export function ResearchRunsPlaceholder() {
  return (
    <Placeholder
      title="Research runs · sample timeline"
      note="Stage status from a real desk session goes here. Static mock for layout, not a real run."
      bodyClassName="min-h-0"
    >
      <div className="grid gap-1.5 font-mono text-[0.66rem] text-ink-mute">
        {SAMPLE_RUNS.map((run) => (
          <div key={run.name} className="grid grid-cols-[7.5rem_minmax(0,1fr)] items-center gap-3">
            <span>{run.name}</span>
            <div className="grid grid-cols-6 gap-1">
              {run.cells.map((cell, i) => (
                <span key={STAGES[i]} className={`h-3 border ${CELL_STYLE[cell]}`} />
              ))}
            </div>
          </div>
        ))}
        <div className="grid grid-cols-[7.5rem_minmax(0,1fr)] gap-3">
          <span aria-hidden="true" />
          <div className="grid grid-cols-6 gap-1 text-center text-[0.6rem]">
            {STAGES.map((s) => (
              <span key={s} className="truncate">
                {s}
              </span>
            ))}
          </div>
        </div>
      </div>
    </Placeholder>
  );
}

/** DESIGN NOTE: LuxAlgo / Vela-style chart frame; live ticker after an asset is picked. */
export function ChartFramePlaceholder() {
  return (
    <Placeholder
      title="Chart frame"
      mark={<IntegrationMark id="luxalgo" size={16} />}
      status="story embed"
      note="A LuxAlgo or Vela-style chart: a live ticker chart for the asset picked above it. This frame only hosts it."
      bodyClassName="min-h-[8rem]"
      className="h-full"
    >
      <div className="flex h-full min-h-[6rem] flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Wire className="h-7 w-48 max-w-full border-dashed" />
          <div className="ms-auto flex gap-1 font-mono text-[0.65rem] text-ink-mute">
            {RANGES.map((r) => (
              <span key={r} className="border border-hair px-2 py-1">
                {r}
              </span>
            ))}
          </div>
        </div>
        <div className="relative flex-1 border border-hair">
          {[25, 50, 75].map((top) => (
            <span key={top} className="absolute inset-x-0 border-t border-dashed border-hair" style={{ top: `${top}%` }} />
          ))}
          <span className="absolute inset-0 grid place-items-center font-mono text-[0.68rem] text-ink-mute">chart area</span>
        </div>
      </div>
    </Placeholder>
  );
}

/** DESIGN NOTE: Gloomberb terminal teaser. Profile and tearsheet tabs, rich data via MCP later. */
export function GloombergTerminalPlaceholder() {
  return (
    <Placeholder
      title="Gloomberb terminal"
      mark={<IntegrationMark id="gloomberb" size={16} />}
      status="integrated"
      note="Bloomberg-style profile and tearsheet tabs. Richer data routes through MCP tools later. Sourced from Gloomberb; free-tier data is delayed up to 15 minutes. No affiliation implied."
      bodyClassName="min-h-[8rem]"
      className="h-full"
    >
      <div className="flex h-full min-h-[6rem] flex-col gap-3 font-mono text-[0.68rem] text-ink-mute">
        <div className="flex flex-wrap gap-1">
          {TABS.map((tab, i) => (
            <span key={tab} className={`border px-2 py-1 ${i === 0 ? "border-ink-mute text-ink" : "border-hair"}`}>
              {tab}
            </span>
          ))}
        </div>
        <div className="grid flex-1 grid-cols-2 gap-x-4 gap-y-2">
          {["Sector", "Market cap", "Exchange", "Range", "Float", "Next report"].map((k) => (
            <div key={k} className="flex items-baseline justify-between border-b border-dashed border-hair pb-1">
              <span>{k}</span>
              <span>—</span>
            </div>
          ))}
        </div>
      </div>
    </Placeholder>
  );
}

/** DESIGN NOTE: connected-broker cards with status chips. Showcase only: no orders. */
export function BrokerCardsPlaceholder() {
  return (
    <Placeholder
      title="Brokers"
      status="in development"
      note="Connected brokers with status chips, as the dashboard shows them. Showcase only: no orders, no live trading."
      bodyClassName="min-h-[8rem]"
      className="h-full"
    >
      <div className="grid gap-2">
        {BROKERS.map((b) => (
          <div key={b.name} className="flex items-center justify-between gap-3 border border-dashed border-hair px-3 py-3 font-mono">
            <span className="flex items-center gap-3 text-ink-soft">
              <IntegrationMark id={b.id} size={24} />
              <span className="text-[0.78rem]">{b.name}</span>
            </span>
            <span className="border border-dashed border-hair px-2 py-0.5 text-[0.62rem] text-ink-mute">adapter declared</span>
          </div>
        ))}
      </div>
    </Placeholder>
  );
}
