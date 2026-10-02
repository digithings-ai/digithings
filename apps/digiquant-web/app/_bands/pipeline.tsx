import { Badge } from "@digithings/ui/ui";
import { Band } from "../_chrome/Band";

type PipelineStatus = "done" | "in development";

/** Four product workflows. Research and the investment portfolio are the
 *  digiquant baselines. Strategy building and trade setups are not finished. */
const PIPELINES: readonly {
  name: string;
  status: PipelineStatus;
  body: string;
  later?: string;
}[] = [
  {
    name: "Research",
    status: "done",
    body: "digiquant baseline research. Theme-delegated sub-agents search the web and read a custom knowledge base, including the 12x terminal. It runs on digithings, on digigraph and the digithings infrastructure.",
  },
  {
    name: "Investment portfolio",
    status: "done",
    body: "digiquant baseline portfolio. Thesis generation, then stock analysis, then deliberation with portfolio management and the investment preferences.",
  },
  {
    name: "Strategy building",
    status: "in development",
    body: "Workflows that help an agent turn an idea into an algorithmic strategy, backtest it, and ship a strategy that has been backtested.",
  },
  {
    name: "Trade setups",
    status: "in development",
    body: "From research, prices, and charts, long or short ideas on asset pairs — the 12x work.",
    later:
      "Reliable setups with an entry, a stop, and a target, then monitoring. The system builds trade levels from different criteria, and an agent selects the one it judges most viable. Technical judgment on the chart.",
  },
];

/** Homepage `#pipeline`. One static banner: no sliding panes, no scroll runway,
 *  no per-stage accordion. The desk at `/app/pipeline` is a different surface. */
export function PipelineBand() {
  return (
    <Band
      id="pipeline"
      status="two done"
      title="Four pipelines"
      takeaway="Research and the investment portfolio are the digiquant baselines, and they run. Strategy building and trade setups are in development. None of them places an order."
    >
      <ol
        aria-label="digiquant pipelines"
        className="m-0 grid list-none grid-cols-1 gap-px overflow-hidden border border-hair bg-hair p-0 md:grid-cols-2 xl:grid-cols-4"
      >
        {PIPELINES.map((pipeline, index) => (
          <li key={pipeline.name} className="flex min-w-0 flex-col gap-3 bg-surface p-5">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
              <span className="font-mono text-[0.72rem] tracking-[0.08em] text-ink-mute">
                {String(index + 1).padStart(2, "0")}
              </span>
              <Badge variant={pipeline.status === "done" ? "accent" : "neutral"}>{pipeline.status}</Badge>
            </div>
            <h3 className="m-0 font-display text-[1.25rem] font-medium leading-tight tracking-[-0.02em] text-ink">
              {pipeline.name}
            </h3>
            <p className="m-0 text-[0.8125rem] leading-[1.55] text-ink-soft">{pipeline.body}</p>
            {pipeline.later ? (
              <p className="m-0 border-t border-hair pt-3 text-[0.8125rem] leading-[1.55] text-ink-soft">
                <span className="mb-1 block font-mono text-[0.68rem] text-ink-mute">Still to come</span>
                {pipeline.later}
              </p>
            ) : null}
          </li>
        ))}
      </ol>
    </Band>
  );
}
