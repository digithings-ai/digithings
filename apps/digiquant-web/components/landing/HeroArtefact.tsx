/**
 * The hero artefact — a product surface, not an illustration (#4430).
 *
 * Authored once on the kit <ProductFrame/>'s fixed 800×300 artboard and scaled
 * proportionally, so it stays pixel-faithful at any width and never reflows
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
import { LIVE_ORDERS, PIPELINE_ENGINES } from "@/app/_pipeline";

export function HeroArtefact() {
  return (
    <ProductFrame tag="digiquant · research → portfolio" className="w-full">
      <div className="flex h-full w-full flex-col bg-surface text-ink">
        {/* Mock product chrome */}
        <div className="flex h-[40px] shrink-0 items-center gap-[0.9rem] border-b border-hair px-[1.1rem]">
          <span className="font-mono text-[11px] tracking-[-0.01em] text-ink">digiquant</span>
          <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-ink-mute">
            pipeline
          </span>
          <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-ink-mute">
            tearsheets
          </span>
        </div>

        {/* Phase rails — every shipped phase, grouped by engine */}
        <div className="flex min-h-0 flex-1 flex-col gap-[0.7rem] px-[1.1rem] py-[0.8rem]">
          {PIPELINE_ENGINES.filter((e) => e.phases.length > 0).map((engine) => (
            <div key={engine.id} className="min-w-0">
              <div className="mb-[0.35rem] flex items-baseline gap-[0.5rem]">
                <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-accent">
                  {engine.label}
                </span>
                <span className="font-mono text-[9px] text-ink-mute">
                  {engine.phases.length} phases
                </span>
              </div>
              <div className="flex flex-wrap gap-[0.3rem]">
                {engine.phases.map((p) => (
                  <span
                    key={`${engine.id}-${p.id}`}
                    className="inline-flex items-center gap-[0.3rem] border border-hair bg-bg px-[0.4rem] py-[0.2rem]"
                  >
                    <Kbd>{p.id}</Kbd>
                    <span className="text-[10px] text-ink-soft">{p.name}</span>
                  </span>
                ))}
              </div>
            </div>
          ))}
          <div className="mt-auto flex items-center gap-[0.45rem]">
            <span className="inline-block h-[6px] w-[6px] bg-accent" aria-hidden="true" />
            <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-ink-mute">
              execution · in development
            </span>
          </div>
        </div>

        {/* Honest status footer */}
        <div className="flex h-[30px] shrink-0 items-center gap-[0.8rem] border-t border-hair px-[1.1rem]">
          <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-ink-mute">
            illustrative surface · not live results
          </span>
            <span className="ml-auto font-mono text-[9px] uppercase tracking-[0.14em] text-ink-mute">
              {LIVE_ORDERS} live orders
            </span>
        </div>
      </div>
    </ProductFrame>
  );
}
