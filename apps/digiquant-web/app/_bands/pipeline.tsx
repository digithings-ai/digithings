import { Badge } from "@digithings/ui/ui";
import { ExecutionCard, StageCard } from "@/components/pipeline/StageCard";
import { StageRunway } from "@/components/pipeline/StageRunway";
import { getLatestRun } from "@/lib/run-snapshot";
import { Band } from "../_chrome/Band";
import { ResearchRunsPlaceholder } from "../_placeholders";
import { EXECUTION_STAGE, PIPELINE_STAGES } from "../_stages";

/** The pipeline band, straight after the dashboard. Stages sit side by side on desktop (a snap row
 *  on narrow screens) and slide in one by one as you scroll through the pinned band. The strip above
 *  the cards says what the data is: a recorded run (date, run type) or that none was captured. */
export function PipelineBand() {
  const latest = getLatestRun();
  const snap = latest.snapshot;
  const total = PIPELINE_STAGES.length + 1;
  const badge = snap ? `recorded · ${snap.runDate} · ${snap.runType ?? "run type unknown"}` : "no recorded run";

  return (
    <Band
      id="pipeline"
      status={snap ? "recorded" : "no recorded run"}
      title="Six stages, one record per run"
      takeaway="A run moves from inputs to learning, and each stage writes down what it did. What you see is a recorded run, not a live one."
    >
      <StageRunway
        label="Pipeline stages"
        intro={
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border border-hair px-3 py-2 font-mono text-[0.68rem] text-ink-mute">
            <span>run</span>
            <Badge variant="neutral">{badge}</Badge>
            <span className="text-ink-soft">
              {snap ? "a recorded run, not live" : "no run was captured for this build; the cards show the pipeline's structure"}
            </span>
            <span className="ms-auto hidden sm:inline">metadata only · captured {latest.capturedAt.slice(0, 10)}</span>
          </div>
        }
        outro={<ResearchRunsPlaceholder />}
      >
        {PIPELINE_STAGES.map((name, i) => (
          <li key={name} className="flex min-w-0 snap-start">
            <StageCard
              index={i}
              total={total}
              name={name}
              hasRun={snap !== null}
              recorded={snap?.stages.find((s) => s.name === name)}
            />
          </li>
        ))}
        <li className="flex min-w-0 snap-start">
          <ExecutionCard index={PIPELINE_STAGES.length} total={total} status={EXECUTION_STAGE.status} />
        </li>
      </StageRunway>
    </Band>
  );
}
