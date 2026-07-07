/**
 * Feature cell — a feature block pairing an eyebrow / outcome / mechanism copy
 * column with a scaled product frame. Static layout template.
 */
import { MockTearsheet, ProductFrame } from "@/components/product-frame-reference";

type Cell = {
  eyebrow: string;
  outcome: string;
  mechanism: string;
  tag: string;
  accent: string;
};

// The universal cell structure across graphite / cursor / x.ai:
// eyebrow → outcome (4–8 words) → one-sentence mechanism → "Learn more →" →
// product visual, with an overlay tag on the crop.
const CELLS: Cell[] = [
  {
    eyebrow: "research",
    outcome: "Ideas that arrive already tested",
    mechanism: "atlas pulls free macro and market data, proposes directions, and hands each to a backtest before you ever see it.",
    tag: "atlas · research",
    accent: "atlas",
  },
  {
    eyebrow: "execution",
    outcome: "From signal to order, timed",
    mechanism: "hermes routes a validated signal to the sizer and kairos holds it until the moment the rules actually fire.",
    tag: "hermes · risk",
    accent: "hermes",
  },
];

export function FeatureCellReference() {
  return (
    <section className="section-block feature-cells" id="feature-cell">
      <p className="kicker">{"// feature cell"}</p>
      <h2 className="title">The universal cell.</h2>
      <p className="section-copy">
        One structure repeats across every reference site and every band we ship: eyebrow → a
        short outcome headline → one sentence of mechanism → a quiet link → the product itself,
        cropped in a frame with a mono overlay tag. Copy leads; the screenshot proves it.
      </p>

      {/* Token-backed Tailwind utilities via the @theme bridge; off-scale rem and
          the clamp() outcome size stay as arbitrary utilities. fc-cell keeps its
          class for the :nth-child(even) .fc-copy order swap; fc-link keeps its
          class for the :hover underline. */}
      <div className="mt-[1.2rem] grid gap-[1.2rem]">
        {CELLS.map((cell) => (
          <article
            key={cell.tag}
            className={`fc-cell grid grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] items-center gap-[1.6rem] rounded-[12px] border border-hair bg-surface p-[1.6rem] max-[760px]:grid-cols-1 accent-${cell.accent}`}
          >
            <div className="fc-copy">
              <p className="font-mono text-[0.62rem] uppercase tracking-[0.12em] text-accent">{cell.eyebrow}</p>
              <h3 className="mt-[0.5rem] font-display font-normal text-[clamp(1.3rem,2.6vw,1.7rem)] tracking-[-0.013em] leading-[1.12] text-ink">
                {cell.outcome}
              </h3>
              <p className="mt-[0.6rem] max-w-[42ch] text-[0.92rem] text-ink-soft">{cell.mechanism}</p>
              <a className="fc-link mt-[0.9rem] inline-block font-mono text-[0.72rem] text-accent no-underline" href="#feature-cell">
                Learn more <span aria-hidden="true">→</span>
              </a>
            </div>
            <ProductFrame tag={cell.tag}>
              <MockTearsheet />
            </ProductFrame>
          </article>
        ))}
      </div>
    </section>
  );
}
