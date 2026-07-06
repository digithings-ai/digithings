import "./layout.css";
import { FeatureCellReference } from "@/components/feature-cell-reference";
import { MockTearsheet, ProductFrame } from "@/components/product-frame-reference";

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
    </main>
  );
}
