/**
 * The hero artefact — a product surface, not an illustration (#4430).
 *
 * Authored once on a fixed 1200×520 artboard and scaled by the kit's
 * <ProductFrame/>, so it stays pixel-faithful at any width and never reflows
 * (the reference's "real surface, cropped" technique). DOM + SVG only: no
 * binary screenshot, so nothing goes stale the moment the product changes and
 * nothing enters the canon ALLOWLIST.
 *
 * What it shows is process, not P&L — the research → portfolio pipeline, the
 * phase chips, and the honest status line ("paper routing · 0 live orders").
 * There is deliberately no performance figure here: a hero crop is the last
 * place to imply a result, and the tearsheets (with their in-sample wording)
 * are where numbers belong.
 */
import { ProductFrame } from "@digithings/ui";
import { Kbd } from "@digithings/ui/ui";
import { PIPELINE_ENGINES } from "@/app/_pipeline";

const THESES = [
  { tag: "rates", title: "Duration stays short while the curve steepens" },
  { tag: "energy", title: "Supply tightness outlives the headline" },
  { tag: "fx", title: "The dollar’s bid is carry, not conviction" },
];

export function HeroArtefact() {
  return (
    <ProductFrame
      tag="digiquant · research → portfolio"
      artboardWidth={1200}
      artboardHeight={520}
      className="w-full"
    >
      <div className="flex h-full w-full flex-col bg-surface text-ink">
        {/* Mock product chrome */}
        <div className="flex h-[52px] shrink-0 items-center gap-[1.2rem] border-b border-hair px-[1.6rem]">
          <span className="font-mono text-[13px] tracking-[-0.01em] text-ink">digiquant</span>
          <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-mute">
            pipeline
          </span>
          <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-mute">
            tearsheets
          </span>
          <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.14em] text-ink-mute">
            research run · in-sample
          </span>
        </div>

        {/* Phase rails */}
        <div className="flex min-h-0 flex-1 gap-[1.4rem] px-[1.6rem] py-[1.3rem]">
          <div className="flex min-w-0 flex-1 flex-col gap-[1.1rem]">
            {PIPELINE_ENGINES.filter((e) => e.phases.length > 0).map((engine) => (
              <div key={engine.id} className="min-w-0">
                <div className="mb-[0.5rem] flex items-baseline gap-[0.6rem]">
                  <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-accent">
                    {engine.label}
                  </span>
                  <span className="font-mono text-[10px] text-ink-mute">
                    {engine.phases.length} phases
                  </span>
                </div>
                <div className="flex flex-wrap gap-[0.4rem]">
                  {engine.phases.map((p) => (
                    <span
                      key={`${engine.id}-${p.id}`}
                      className="inline-flex items-center gap-[0.4rem] border border-hair bg-bg px-[0.5rem] py-[0.3rem]"
                    >
                      <Kbd>{p.id}</Kbd>
                      <span className="text-[12px] text-ink-soft">{p.name}</span>
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Thesis store */}
          <div className="flex w-[320px] shrink-0 flex-col border border-hair bg-bg">
            <div className="flex items-center justify-between border-b border-hair px-[0.8rem] py-[0.55rem]">
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-mute">
                thesis store
              </span>
              <span className="font-mono text-[10px] text-ink-mute">3 sourced</span>
            </div>
            <ul className="m-0 flex list-none flex-col p-0">
              {THESES.map((t) => (
                <li
                  key={t.tag}
                  className="border-b border-hair px-[0.8rem] py-[0.6rem] last:border-b-0"
                >
                  <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-accent">
                    {t.tag}
                  </span>
                  <p className="m-0 mt-[0.25rem] text-[12px] leading-[1.4] text-ink-soft">
                    {t.title}
                  </p>
                </li>
              ))}
            </ul>
            <div className="mt-auto flex items-center gap-[0.45rem] border-t border-hair px-[0.8rem] py-[0.55rem]">
              <span className="inline-block h-[6px] w-[6px] bg-accent" aria-hidden="true" />
              <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-mute">
                risk gate · human
              </span>
            </div>
          </div>
        </div>

        {/* Honest status footer */}
        <div className="flex h-[38px] shrink-0 items-center gap-[0.8rem] border-t border-hair px-[1.6rem]">
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-mute">
            illustrative surface · not live results
          </span>
          <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.14em] text-ink-mute">
            0 live orders
          </span>
        </div>
      </div>
    </ProductFrame>
  );
}
