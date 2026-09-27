/**
 * The why-band v2 takes: three DIFFERENT arguments with three DIFFERENT
 * drawings, stacked for review.
 *
 * - A "One wall, or eight seams": monolith diagram vs exploded module build,
 *   full guided walk. Lock-in argument.
 * - B "Start with the layer that hurts": four cumulative stage diagrams, no
 *   scroll-walk. Modularity / land-and-expand argument.
 * - C "The invoice duel": no diagrams — two ledgers, their invoice vs your
 *   rates. Price argument.
 *
 * Server component: `ArchitectureTour` is the only client piece.
 */

import { ArchitectureDiagram, ArchitectureTour, Reveal } from "@digithings/ui";

import { DIGITHINGS_ARCH, OWNED_TOUR_STEPS } from "@/lib/whyStack";
import { LADDER_STAGES, LEDGER_ROWS, MONOLITH_ARCH, MONOLITH_STEPS } from "@/lib/whyCopyVariants";

const HEADLINE = "m-0 font-mono text-[clamp(1.3rem,2.4vw,1.85rem)] font-medium leading-[1.2] tracking-[-0.02em] text-ink";
const LEDE = "m-0 max-w-[var(--measure-prose)] text-[0.9rem] leading-[1.7] text-ink-soft";
const VERSION_LABEL = "font-mono text-[0.68rem] uppercase tracking-[0.08em] text-ink-mute";

function VersionHead({ id, name, blurb }: { id: string; name: string; blurb: string }) {
  return (
    <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[0.5rem] px-[var(--page-pad)] pt-[2.5rem]">
      <span className={VERSION_LABEL}>
        version {id} · {name}
      </span>
      <p className={LEDE}>{blurb}</p>
    </div>
  );
}

function VersionA() {
  return (
    <section aria-label="Version A — one wall, or eight seams" className="line-b">
      <VersionHead
        id="A"
        name="one wall, or eight seams"
        blurb="Lock-in argument. A brand-new 3-box monolith walked against the exploded 8-module build."
      />
      <div className="whyx">
        <div className="whyx__block">
          <div className="whyx__tours">
            <div className="whyx__tour">
              <ArchitectureTour
                header={
                  <>
                    <h2 className={HEADLINE}>
                      <span className="why-rent">One wall around everything,</span>{" "}
                      <span className="why-own">or seams everywhere you need them.</span>
                    </h2>
                    <p className={LEDE}>
                      Their platform is one box you cannot open: every layer behind a single
                      interface, on a roadmap you don&apos;t vote on. digithings is the same
                      AI infrastructure cut along its seams — eight named modules you can
                      take alone or run together. The difference isn&apos;t who owns the
                      machines. It&apos;s whether anything in the drawing can move.
                    </p>
                  </>
                }
                sides={[
                  {
                    spec: MONOLITH_ARCH,
                    steps: MONOLITH_STEPS,
                    tag: "one wall",
                    rail: "end",
                    caption: "One box, one bill, one roadmap",
                  },
                  {
                    spec: DIGITHINGS_ARCH,
                    steps: OWNED_TOUR_STEPS,
                    tag: "digithings stack",
                    caption:
                      "Every box a module — take one or run them all · digibase under all of them",
                  },
                ]}
                variant="camera"
              />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function VersionB() {
  return (
    <section aria-label="Version B — start with the layer that hurts" className="line-b">
      <VersionHead
        id="B"
        name="start with the layer that hurts"
        blurb="Modularity argument. Four cumulative stage diagrams, no scroll-walk — the build grows in place."
      />
      <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[2.5rem] px-[var(--page-pad)] py-[2.5rem]">
        <div className="flex max-w-[var(--measure-prose)] flex-col gap-[0.5rem]">
          <h2 className={HEADLINE}>
            <span className="why-rent">Start with the layer that hurts,</span>{" "}
            <span className="why-own">end with a stack that&apos;s yours.</span>
          </h2>
          <p className={LEDE}>
            Nobody rips out eight layers at once. digithings adopts the way pain
            arrives: chat over your index this month, your own models next, your
            data after that — each step running on your hosts, each step leaving
            the rest exactly where it was.
          </p>
        </div>
        {LADDER_STAGES.map((stage, i) => (
          <Reveal key={stage.id} delay={Math.min(i * 0.05, 0.15)}>
            <div className="flex flex-col gap-[0.8rem] border border-hair bg-surface p-[1.4rem]">
              <span className={VERSION_LABEL}>stage {i + 1} of 4</span>
              <h3 className="m-0 font-mono text-[1.05rem] font-medium text-ink">{stage.label}</h3>
              <p className="m-0 max-w-[var(--measure-prose)] text-[0.88rem] leading-[1.7] text-ink-soft">
                {stage.line}
              </p>
              <ArchitectureDiagram spec={stage.spec} />
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

function VersionC() {
  return (
    <section aria-label="Version C — the invoice duel" className="line-b">
      <VersionHead
        id="C"
        name="the invoice duel"
        blurb="Price argument. No diagrams — two ledgers, their invoice against your rates. No figures, only meters."
      />
      <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[1.5rem] px-[var(--page-pad)] py-[2.5rem]">
        <div className="flex max-w-[var(--measure-prose)] flex-col gap-[0.5rem]">
          <h2 className={HEADLINE}>
            <span className="why-rent">Metered by them,</span>{" "}
            <span className="why-own">or priced by your own providers.</span>
          </h2>
          <p className={LEDE}>
            The managed AI bill is a margin on top of the same models, indexes
            and machines you could call directly. digithings removes the
            middleman&apos;s meter: your keys call the providers, your hosts run
            the rest. Start with one module — each layer you take back is one
            less margin you pay.
          </p>
        </div>
        <Reveal>
          <div className="whyx-cap" role="table" aria-label="Their invoice versus your rates">
            <div className="whyx-cap__row whyx-cap__row--head" role="row">
              <span className="whyx-cap__key" role="columnheader">layer</span>
              <span className="whyx-cap__cell" role="columnheader">their invoice</span>
              <span className="whyx-cap__cell" role="columnheader">your rates</span>
            </div>
            {LEDGER_ROWS.map((row) => (
              <div className="whyx-cap__row" role="row" key={row.layer}>
                <span className="whyx-cap__key" role="rowheader">{row.layer}</span>
                <span className="whyx-cap__cell" role="cell">{row.theirs}</span>
                <span className="whyx-cap__cell whyx-cap__cell--owned" role="cell">{row.yours}</span>
              </div>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

export function WhyCopyVariants() {
  return (
    <>
      <VersionA />
      <VersionB />
      <VersionC />
    </>
  );
}
