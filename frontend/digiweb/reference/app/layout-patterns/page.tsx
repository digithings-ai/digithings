import "./layout.css";
import { BentoGridReference } from "@/components/bento-grid-reference";
import { FeatureCellReference } from "@/components/feature-cell-reference";
import { NumberedStagesReference } from "@/components/numbered-stages-reference";
import { PhoneOlympus } from "@/components/phone-olympus";
import { MockTearsheet, ProductFrame } from "@/components/product-frame-reference";
import { TestimonialWallReference } from "@/components/testimonial-wall-reference";

export default function LayoutPage() {
  return (
    <main className="reference-page">
      <header className="hero">
        <p className="kicker">{"// layout"}</p>
        <h1>
          Composed <em>content bands.</em>
        </h1>
        <p>
          The building blocks above the atom: the universal feature cell, and the product frame
          that keeps a real surface pixel-faithful while it scales. Copy leads, the product proves
          it, the crop wears a tag.
        </p>
      </header>

      <FeatureCellReference />
      <NumberedStagesReference />
      <BentoGridReference />
      <TestimonialWallReference />

      <section className="section-block" id="product-frame">
        <p className="kicker">{"// product frame"}</p>
        <h2 className="title">Real surfaces, cropped.</h2>
        <p className="section-copy">
          A screenshot is authored once on a fixed 800px artboard, then scaled proportionally to
          its container — <code>min(1, (100cqw − 2rem) / 800)</code> — so it never reflows and
          stays pixel-faithful at any width. The mono overlay tag names the crop without a caption.
        </p>
        <div className="pf-solo">
          <ProductFrame tag="atlas · research">
            <MockTearsheet />
          </ProductFrame>
        </div>
      </section>

      <section className="section-block" id="phone">
        <p className="kicker">{"// phone · olympus app"}</p>
        <h2 className="title">The app, on the device.</h2>
        <p className="section-copy">
          The companion to the cropped desktop surface: a phone frame — matte bezel, dynamic island,
          side buttons — showcasing the olympus mobile dashboard. Same product grammar as the frame
          above (an inline SVG sparkline, no charting engine); P&amp;L wears the money colors, the
          accent dresses the chrome and re-themes with the livery. It floats gently; reduced motion
          holds it still.
        </p>
        <div className="phone-stage">
          <PhoneOlympus />
        </div>
      </section>
    </main>
  );
}
