/**
 * Feature cell — a feature block pairing an eyebrow / outcome / mechanism copy
 * column with a scaled product frame. Consumes the shared <FeatureCell/> +
 * <ProductFrame/> primitives from @digithings/web. Static layout template.
 */
import { FeatureCell, ProductFrame } from "@digithings/web";
import { MockTearsheet } from "@/components/product-frame-reference";

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

      <div className="mt-[1.2rem] grid gap-[1.2rem]">
        {CELLS.map((cell) => (
          <FeatureCell
            key={cell.tag}
            eyebrow={cell.eyebrow}
            outcome={cell.outcome}
            mechanism={cell.mechanism}
            href="#feature-cell"
            livery={cell.accent}
          >
            <ProductFrame tag={cell.tag}>
              <MockTearsheet />
            </ProductFrame>
          </FeatureCell>
        ))}
      </div>
    </section>
  );
}
