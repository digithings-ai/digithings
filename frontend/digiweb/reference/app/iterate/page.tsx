import "./iterate.css";
import { UtilBlendComposite } from "@/components/iterate/util-blend-composite";
import { UtilIterateGallery } from "@/components/iterate/util-iterate-gallery";

export default function IteratePage() {
  return (
    <main className="reference-page">
      <header className="hero">
        <p className="kicker">{"// iterate · utilitarian terminal"}</p>
        <h1>
          Pick the boring <em>sharp</em> parts.
        </h1>
        <p>
          Round 1 picks are recorded in <code>design/BLEND.md</code> with a consistency pass. The
          composite below is the cohesive candidate; the gallery under it stays for revisiting
          individual axes. Gallery CSS is prefixed <code>uv-</code> and never ships to product apps.
        </p>
      </header>

      <UtilBlendComposite />
      <UtilIterateGallery />
    </main>
  );
}
