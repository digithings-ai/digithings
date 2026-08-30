import "./iterate.css";
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
          Side-by-side treatments for every foundational digiweb axis — corners, type, CTAs, nav,
          heroes, density — inspired by herdr, agentmail, omarchy, and our Instrument Panel. Click
          the ones you like. The ledger sticks in this browser; paste it into{" "}
          <code>design/BLEND.md</code> when a round lands. Gallery CSS is prefixed{" "}
          <code>uv-</code> and never ships to product apps.
        </p>
      </header>

      <UtilIterateGallery />
    </main>
  );
}
