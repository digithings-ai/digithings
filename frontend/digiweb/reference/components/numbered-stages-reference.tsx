/**
 * Numbered stages — a Linear-style numbered progression mapped to the digithings
 * pipeline, each stage carrying its module livery, title, and mechanism.
 * Consumes the shared <NumberedStages/> primitive from @digithings/web.
 * Static display template.
 */
import { NumberedStages, type NumberedStage } from "@digithings/web";

// Linear's numbered feature progression, mapped to the real digithings pipeline.
const STAGES: NumberedStage[] = [
  {
    num: "1.0",
    tag: "atlas",
    livery: "atlas",
    title: "Research",
    mech: "Ask in plain language. The research loop pulls free macro and market data and proposes directions worth testing.",
  },
  {
    num: "2.0",
    tag: "digiquant",
    livery: "digiquant",
    title: "Backtest",
    mech: "NautilusTrader runs the idea across years of bars. The tearsheet is the receipt — re-runnable, not a rumor.",
  },
  {
    num: "3.0",
    tag: "hermes",
    livery: "hermes",
    title: "Execute",
    mech: "A validated signal routes to the sizer; kairos holds it until the moment the rules actually fire.",
  },
];

export function NumberedStagesReference() {
  return (
    <section className="section-block numbered-stages">
      <p className="kicker">{"// numbered stages"}</p>
      <h2 className="title">The pipeline, numbered.</h2>
      <p className="section-copy">
        The sequential-stage grammar: a numbered spine where each step is one move in the flow —
        big mono index, a serif title, one sentence of mechanism. Here it carries the real
        research → backtest → execute pipeline, each stage wearing its module&apos;s livery.
      </p>

      <NumberedStages stages={STAGES} className="mt-[1.2rem]" />
    </section>
  );
}
