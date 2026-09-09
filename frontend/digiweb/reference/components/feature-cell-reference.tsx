/**
 * Feature cell — a feature block pairing an eyebrow / outcome / mechanism copy
 * column with a scaled product frame. Consumes the shared <FeatureCell/> +
 * <ProductFrame/> primitives from @digithings/web. Static layout template.
 */
import { FeatureCell, ProductFrame } from "@digithings/web";
import { MockTearsheet, type MockTearsheetProps } from "@/components/product-frame-reference";

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
    mechanism: "research pulls free macro and market data, proposes directions, and hands each to a backtest before you ever see it.",
    tag: "research · research",
    accent: "research",
  },
  {
    eyebrow: "execution",
    outcome: "From signal to order, timed",
    mechanism: "portfolio routes a validated signal to the sizer and execution holds it until the moment the rules actually fire.",
    tag: "portfolio · risk",
    accent: "portfolio",
  },
];

// Distinct MockTearsheet stats per cell (see product-frame-reference.tsx) —
// same demo-data values already used elsewhere on the reference site
// (sortable-table-reference.tsx's trend_xsec and carry strategies), so this
// isn't a fresh invented number, just reused for cross-page consistency.
// Typed against MockTearsheet's own (all-optional) prop type rather than a
// locally-required one: cell.eyebrow is a plain string with no shared literal
// union tying it to these keys, so a future eyebrow that doesn't match a key
// here must fall through to MockTearsheet's defaults, not crash the render.
const MOCKS: Record<string, MockTearsheetProps> = {
  research: {
    title: "trend_xsec · ETH-USD",
    cagr: "+44.9%",
    maxDd: "-18.4%",
    profitFactor: "2.31",
    points: "0,150 60,140 120,146 180,110 240,120 300,84 360,92 420,54 480,64 560,24",
  },
  execution: {
    title: "carry · BTC-USD",
    cagr: "+31.2%",
    maxDd: "-12.1%",
    profitFactor: "3.02",
    points: "0,120 60,115 120,118 180,100 240,105 300,90 360,95 420,78 480,82 560,60",
  },
};

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
        {CELLS.map((cell) => {
          // Falls back to {} (not a crash) if a future cell's eyebrow has no
          // matching entry above — every MockTearsheet prop is optional, so
          // an empty object just renders its built-in defaults.
          const mock = MOCKS[cell.eyebrow] ?? {};
          return (
            <FeatureCell
              key={cell.tag}
              eyebrow={cell.eyebrow}
              outcome={cell.outcome}
              mechanism={cell.mechanism}
              href="#feature-cell"
              // Both cells otherwise share identical link text AND an
              // identical, self-referencing href — two adjacent "Learn
              // more" links a screen reader announces with no way to tell
              // them apart. A real instance should give each its own
              // destination; this demo has none, so an aria-label at least
              // disambiguates the accessible name.
              linkAriaLabel={`Learn more about ${cell.eyebrow}`}
              livery={cell.accent}
            >
              <ProductFrame tag={cell.tag}>
                <MockTearsheet
                  title={mock.title}
                  cagr={mock.cagr}
                  maxDd={mock.maxDd}
                  profitFactor={mock.profitFactor}
                  points={mock.points}
                />
              </ProductFrame>
            </FeatureCell>
          );
        })}
      </div>
    </section>
  );
}
