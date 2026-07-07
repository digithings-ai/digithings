type Stage = { num: string; module: string; livery: string; title: string; mech: string };

// Linear's numbered feature progression, mapped to the real DigiThings pipeline.
const STAGES: Stage[] = [
  {
    num: "1.0",
    module: "atlas",
    livery: "atlas",
    title: "Research",
    mech: "Ask in plain language. The research loop pulls free macro and market data and proposes directions worth testing.",
  },
  {
    num: "2.0",
    module: "digiquant",
    livery: "digiquant",
    title: "Backtest",
    mech: "NautilusTrader runs the idea across years of bars. The tearsheet is the receipt — re-runnable, not a rumor.",
  },
  {
    num: "3.0",
    module: "hermes",
    livery: "hermes",
    title: "Execute",
    mech: "A validated signal routes to the sizer; Kairos holds it until the moment the rules actually fire.",
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

      <ol className="ns-spine">
        {STAGES.map((s) => (
          <li key={s.num} className={`ns-stage accent-${s.livery}`}>
            <span className="ns-node" aria-hidden="true">
              {s.num}
            </span>
            <div className="ns-body">
              <p className="ns-tag">{s.module}</p>
              <h3 className="ns-title">{s.title}</h3>
              <p className="ns-mech">{s.mech}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
