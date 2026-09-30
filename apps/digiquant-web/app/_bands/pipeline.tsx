import { Band, Slot } from "../_chrome/Band";
import { EXECUTION_STAGE, PIPELINE_STAGES } from "../_stages";

export function PipelineBand() {
  return (
    <Band id="pipeline" tint title="The pipeline, stage by stage" takeaway="A recorded run, not live: six stages from inputs to learning.">
      <Slot height="22rem" label={`${PIPELINE_STAGES.join(" → ")} · ${EXECUTION_STAGE.name}: ${EXECUTION_STAGE.status}`} />
    </Band>
  );
}
