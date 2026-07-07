/**
 * Numbered stages — a Linear-style numbered progression mapped to the digithings
 * pipeline, each stage carrying its module livery, title, and mechanism.
 * Static display template.
 */
type Stage = { num: string; module: string; livery: string; title: string; mech: string };

// Linear's numbered feature progression, mapped to the real digithings pipeline.
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

      {/* Token-backed Tailwind utilities via the @theme bridge. ns-stage keeps its
          class for the ::before spine line + :last-child rules; ns-node keeps its
          class for its two-colour color-mix border/background. */}
      <ol className="mt-[1.2rem] grid list-none gap-0 p-0">
        {STAGES.map((s) => (
          <li key={s.num} className={`ns-stage relative grid grid-cols-[3.4rem_1fr] gap-[1.1rem] pb-[1.8rem] accent-${s.livery}`}>
            <span className="ns-node" aria-hidden="true">
              {s.num}
            </span>
            <div className="pt-[0.1rem]">
              <p className="font-mono text-[0.6rem] uppercase tracking-[0.12em] text-accent">{s.module}</p>
              <h3 className="mt-[0.2rem] font-display font-normal text-[clamp(1.2rem,2.4vw,1.5rem)] tracking-[-0.013em] text-ink">
                {s.title}
              </h3>
              <p className="mt-[0.35rem] max-w-[52ch] text-[0.9rem] text-ink-soft">{s.mech}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
