import { HorizontalScrollTrack, HorizontalTrackStepper } from "@digithings/ui";
import { Badge } from "@digithings/ui/ui";
import { ExecutionCard, StageCard } from "@/components/pipeline/StageCard";
import { getLatestRun } from "@/lib/run-snapshot";
import { Band } from "../_chrome/Band";
import { ResearchRunsPlaceholder } from "../_placeholders";
import { EXECUTION_STAGE, PIPELINE_STAGES } from "../_stages";

/** The method band; the page's only pin. The frame chrome above the cards says what the data is:
 *  a recorded run (date, run type) or, when none was captured, that there is none. */
export function PipelineBand() {
  const latest = getLatestRun();
  const snap = latest.snapshot;
  const total = PIPELINE_STAGES.length + 1;
  const badge = snap ? `recorded · ${snap.runDate} · ${snap.runType ?? "run type unknown"}` : "no recorded run";
  const labels = [...PIPELINE_STAGES, EXECUTION_STAGE.name];

  const frame = (
    <div className="mx-6 flex flex-wrap items-center gap-x-3 gap-y-1 border border-hair px-3 py-2 font-mono text-[0.68rem] text-ink-mute">
      <span>run</span>
      <Badge variant="neutral">{badge}</Badge>
      <span className="text-ink-soft">
        {snap ? "a recorded run, not live" : "no run was captured for this build; the cards show the pipeline's structure"}
      </span>
      <span className="ms-auto hidden sm:inline">metadata only · captured {latest.capturedAt.slice(0, 10)}</span>
    </div>
  );

  return (
    <Band
      id="pipeline"
      tint
      status={snap ? "recorded" : "no recorded run"}
      title="The method, stage by stage"
      takeaway="Every run goes through six stages, from inputs to learning, and each one leaves a record. This is a recorded run, not a live one."
    >
      <HorizontalScrollTrack
        ariaLabel="Pipeline stages"
        className="-mx-6"
        pinTop={62}
        header={frame}
        footer={<HorizontalTrackStepper labels={labels} />}
        itemClassName="flex w-[min(82vw,21rem)]"
      >
        {PIPELINE_STAGES.map((name, i) => (
          <StageCard
            key={name}
            index={i}
            total={total}
            name={name}
            hasRun={snap !== null}
            recorded={snap?.stages.find((s) => s.name === name)}
          />
        ))}
        <ExecutionCard index={PIPELINE_STAGES.length} total={total} status={EXECUTION_STAGE.status} />
      </HorizontalScrollTrack>
      <div className="mt-8">
        <ResearchRunsPlaceholder />
      </div>
    </Band>
  );
}
