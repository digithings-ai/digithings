import type { Metadata } from "next";

import { Colophon, LayoutLines } from "@digithings/ui";
import { DtFooter } from "@/components/DtFooter";
import { DtNav } from "@/components/DtNav";
import { LandingPage } from "@/components/landing/LandingPage";

// The landing page (v15, D1, #4429).
//
// The body of the page is `LandingPage` — the lean seven-section composition
// the owner picked from the v14 review, refined in v15. This file keeps only
// the shell: the persistent layout lines, the nav, the metadata, and the
// footer.
//
// The closing wordmark (v15 point 15) is `<Colophon … sweep />`: the giant
// outlined `digithings` lockup with a bright band passing through it once as
// you scroll into it — the "bright fade through it" the owner remembered.
// Two alternatives were weighed and rejected:
//   • `WordReveal` (packages/ui, .word-reveal) is a pinned 150vh track whose
//     words fill from blur on the ride up — a strong effect, but it renders a
//     display-font *sentence* at clamp(1.55rem,4.2vw,2.6rem), not the giant
//     mono lockup, and its pinned track would add 150vh of dead scroll between
//     the contact band and the footer on the one page that ends here.
//   • `word-reveal-muted` / `word-reveal-outline` are reference-gallery-only
//     siblings (apps/reference) and are not exported from @digithings/ui.
// The Colophon already carries both halves: a zero-JS CSS scroll-driven rise
// (`@supports (animation-timeline: view())` in packages/design/site/site.css)
// and the opt-in `sweep` glow, a Motion-scrubbed background-position on a
// duplicated span. Both fall back to the static outlined lockup under
// prefers-reduced-motion and with scripts off, so the mark is never hidden.

export const metadata: Metadata = {
  title: "digithings — AI infrastructure in a glass box",
  description:
    "Open-source, MIT-licensed AI infrastructure: nine modules that plug into the stack you already "
    + "run — not a replacement for it. Self-hosted anywhere, your own keys and providers, every step "
    + "traceable.",
};

export default function Home() {
  return (
    <>
      <LayoutLines />
      <DtNav />

      <main id="main" tabIndex={-1} className="landing relative z-10 pt-[var(--dq-nav-h)]">
        <LandingPage />
      </main>

      <Colophon name="digi" suffix="things" sweep />
      <DtFooter />
    </>
  );
}
