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
    mechanism: "Atlas pulls free macro and market data, proposes directions, and hands each to a backtest before you ever see it.",
    tag: "atlas · research",
    accent: "atlas",
  },
  {
    eyebrow: "execution",
    outcome: "From signal to order, timed",
    mechanism: "Hermes routes a validated signal to the sizer and Kairos holds it until the moment the rules actually fire.",
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

      <div className="fc-grid">
        {CELLS.map((cell) => (
          <article key={cell.tag} className={`fc-cell accent-${cell.accent}`}>
            <div className="fc-copy">
              <p className="fc-eyebrow">{cell.eyebrow}</p>
              <h3 className="fc-outcome">{cell.outcome}</h3>
              <p className="fc-mechanism">{cell.mechanism}</p>
              <a className="fc-link" href="#feature-cell">
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
