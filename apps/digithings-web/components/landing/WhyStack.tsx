/**
 * The `/variants/why` comparison (round 10, #4429).
 *
 * The owner asked for the industry convention rather than a simple node graph:
 * "there's a convention for this that's standard practice amongst software
 * companies ... the specific graph that you typically build when you're
 * designing a system or an architecture". That convention is the C4 model, and
 * the drawing below is its CONTAINER view — one box per runtime unit, one
 * connector per call, external systems outside the boundary.
 *
 * Three blocks, in the order he asked for them (research, then the plan per
 * diagram, then the costs):
 *
 *   1. the two container diagrams, same silhouette, boxes swapped
 *   2. the capability comparison — the same questions asked of both stacks
 *   3. the cost model — per-layer market rates, the assumptions they ride on,
 *      and the framing that stops a rate from reading as a quote
 *
 * Server component: the diagrams are the only client pieces, and they are client
 * components in their own right (`<ArchitectureDiagram>` lazily imports mermaid),
 * so nothing here ships a bundle.
 */

import { ArchitectureDiagram, ArchitectureTour } from "@digithings/ui";

import {
  ARCH_CAPTIONS,
  CAPABILITIES,
  CONVENTIONAL_ARCH,
  COST_ASSUMPTIONS,
  COST_CAVEATS,
  COST_FRAMING,
  COST_LINES,
  DIGITHINGS_ARCH,
  OWNED_TOUR_STEPS,
  RENTED_TOUR_STEPS,
} from "@/lib/whyStack";

const HEADLINE = "m-0 font-mono text-[clamp(1.3rem,2.4vw,1.85rem)] font-medium leading-[1.2] tracking-[-0.02em] text-ink";
const LEDE = "m-0 max-w-[var(--measure-prose)] text-[0.9rem] leading-[1.7] text-ink-soft";

function Diagrams() {
  return (
    <section className="whyx__diagrams" aria-labelledby="whyx-diagrams">
      <h2 className={HEADLINE} id="whyx-diagrams">
        The same system, drawn twice
      </h2>
      <p className={LEDE}>
        One container diagram per stack: each box is something that runs, each line is a call between
        two of them, and the rectangle is the boundary you own. The boxes and the wiring are
        deliberately the same shape on both sides, because the difference that matters is not the
        architecture — it is who holds each box.
      </p>

      <div className="whyx__pair">
        <div className="whyx__side">
          <span className="whyx__tag">01 · full view — rented</span>
          <ArchitectureDiagram
            spec={CONVENTIONAL_ARCH}
            caption={ARCH_CAPTIONS.conventional.caption}
          />
          <p className="whyx__foot">{ARCH_CAPTIONS.conventional.foot}</p>
        </div>

        <div className="whyx__side whyx__side--owned">
          <span className="whyx__tag">01 · full view — owned</span>
          <ArchitectureDiagram spec={DIGITHINGS_ARCH} caption={ARCH_CAPTIONS.digithings.caption} />
          <p className="whyx__foot">{ARCH_CAPTIONS.digithings.foot}</p>
        </div>
      </div>
    </section>
  );
}

function Tour() {
  return (
    <section className="whyx__block" aria-labelledby="whyx-tour">
      <h2 className={HEADLINE} id="whyx-tour">
        The same diagram, walked
      </h2>
      <p className={LEDE}>
        Scroll. The walk starts on the rented stack and lights each box it is talking about; when it
        has finished that side the page pushes the second diagram in behind it, and the camera takes
        over and moves with the walk.
      </p>

      <div className="whyx__tours">
        <div className="whyx__tour">
          <span className="whyx__tag">02 · guided, rented then owned</span>
          <ArchitectureTour
            sides={[
              { spec: CONVENTIONAL_ARCH, steps: RENTED_TOUR_STEPS, tag: "rented" },
              { spec: DIGITHINGS_ARCH, steps: OWNED_TOUR_STEPS, tag: "owned" },
            ]}
            variant="camera"
          />
        </div>
      </div>
    </section>
  );
}

function Capabilities() {
  return (
    <section className="whyx__block" aria-labelledby="whyx-capabilities">
      <h2 className={HEADLINE} id="whyx-capabilities">
        What changes, question by question
      </h2>
      <p className={LEDE}>
        The same nine questions asked of both stacks. Each answer is what is structurally true, not
        what is advertised — which is why none of them needs an adjective.
      </p>

      <div className="whyx-cap" role="table" aria-label="Capability comparison">
        <div className="whyx-cap__row whyx-cap__row--head" role="row">
          <span className="whyx-cap__key" role="columnheader">
            the question
          </span>
          <span className="whyx-cap__cell" role="columnheader">
            rented
          </span>
          <span className="whyx-cap__cell whyx-cap__cell--owned" role="columnheader">
            on digithings
          </span>
        </div>

        {CAPABILITIES.map((row) => (
          <div className="whyx-cap__row" key={row.capability} role="row">
            <span className="whyx-cap__key" role="rowheader">
              {row.capability}
            </span>
            <span className="whyx-cap__cell" role="cell">
              {row.rented}
            </span>
            <span className="whyx-cap__cell whyx-cap__cell--owned" role="cell">
              {row.owned}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function Costs() {
  return (
    <section className="whyx__block" aria-labelledby="whyx-costs">
      <h2 className={HEADLINE} id="whyx-costs">
        What it costs
      </h2>
      <p className={LEDE}>{COST_FRAMING.headline}</p>

      <ul className="whyx-assume">
        {COST_ASSUMPTIONS.map((assumption) => (
          <li className="whyx-assume__item" key={assumption}>
            {assumption}
          </li>
        ))}
      </ul>

      <div className="whyx-cost" role="table" aria-label="Per-layer market rates">
        <div className="whyx-cost__row whyx-cost__row--head" role="row">
          <span role="columnheader">layer</span>
          <span role="columnheader">what the rented stack bills for</span>
          <span role="columnheader">what running it costs</span>
          <span role="columnheader">the figure, dated and labelled</span>
        </div>
        {COST_LINES.map((line) => (
          <div className="whyx-cost__row" key={line.layer} role="row">
            <span className="whyx-cost__layer" role="rowheader">
              {line.layer}
            </span>
            <span role="cell">{line.rented}</span>
            <span role="cell">{line.owned}</span>
            <span className="whyx-cost__source" role="cell">
              {line.source}
            </span>
          </div>
        ))}
      </div>

      <p className={`${LEDE} whyx-cost__body`}>{COST_FRAMING.body}</p>

      <ul className="whyx-caveat">
        {COST_CAVEATS.map((caveat) => (
          <li className="whyx-caveat__item" key={caveat}>
            {caveat}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function WhyStack() {
  return (
    <div className="whyx">
      <Diagrams />
      <Tour />
      <Capabilities />
      <Costs />
    </div>
  );
}
