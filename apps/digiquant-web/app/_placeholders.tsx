import { Placeholder, Wire } from "./_chrome/Placeholder";

/** Layout placeholders for the showcase. Structure first: each one fixes a slot on
 *  the grid and says in its design note what will fill it. Nothing here is wired
 *  to data, brokers or iframes, and nothing implies trading. */

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
