/**
 * Homepage `#pipeline` — the research → portfolio pipeline as a keycap-chip
 * function gallery (#4430). Every phase folder that actually ships is one
 * chip-labelled card, grouped by engine. This replaces the previous two
 * competing sections (a 7-step linear rail and a 480vh scroll-pinned track):
 * one honest surface, no scroll animation, and the count derives from
 * `app/_pipeline.ts` — the same file the metrics band reads.
 *
 * Server component: no state, no effects. Flat by design; each card earns its
 * place by naming a real phase.
 */
import { Card } from "@digithings/ui/ui";
import { Kbd } from "@digithings/ui/ui";
import { PIPELINE_ENGINES, PIPELINE_PHASES } from "@/app/_pipeline";

export function PipelineGallery() {
  return (
    <section className="section" id="pipeline">
      <div className="wrap">
        <div className="dq-sechead">
          <span className="kicker">{"// the pipeline"}</span>
          <h2 className="dq-title">Research in, a tested strategy out.</h2>
          <p className="dq-sub">
            {PIPELINE_PHASES.length} phase folders ship today across research and portfolio.
            Execution is the stage after the book is committed — it has no phase folders yet
            because nothing is sent to a live venue. Every chip below is a real phase, not a
            mock-up.
          </p>
        </div>

        <div className="flex flex-col gap-[clamp(1.8rem,4vw,2.6rem)]">
          {PIPELINE_ENGINES.map((engine) => (
            <div key={engine.id}>
              <div className="flex flex-wrap items-baseline gap-x-[0.8rem] gap-y-[0.2rem]">
                <h3 className="font-display text-[clamp(1.05rem,2.2vw,1.3rem)] font-normal tracking-[-0.01em] text-ink">
                  {engine.label}
                </h3>
                <span className="font-mono text-[0.68rem] uppercase tracking-[0.1em] text-ink-mute">
                  {engine.phases.length > 0
                    ? `${engine.phases.length} phases`
                    : "in development"}
                </span>
              </div>
              <p className="mt-[0.4rem] max-w-[62ch] text-[0.92rem] leading-[1.55] text-ink-soft">
                {engine.summary}
              </p>

              {engine.phases.length > 0 ? (
                <ol
                  className="m-0 mt-[1rem] grid list-none grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-[0.7rem] p-0"
                  aria-label={`${engine.label} phases`}
                >
                  {engine.phases.map((phase) => (
                    <li key={`${engine.id}-${phase.id}`}>
                      <Card className="h-full gap-[0.35rem] px-[0.9rem] py-[0.8rem]">
                        <Kbd className="self-start text-accent">{phase.id}</Kbd>
                        <span className="text-[0.9rem] font-medium tracking-[-0.01em] text-ink">
                          {phase.name}
                        </span>
                        <span className="text-[0.74rem] leading-[1.4] text-ink-mute">
                          {phase.detail}
                        </span>
                      </Card>
                    </li>
                  ))}
                </ol>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
