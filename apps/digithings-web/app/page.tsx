import type { Metadata } from "next";

import { DtFooter } from "@/components/DtFooter";
import { DtNav } from "@/components/DtNav";
import { FooterWordmark } from "@/components/landing/FooterWordmark";
import { LandingPage } from "@/components/landing/LandingPage";
import { embedOriginForChat } from "@/lib/security-headers.mjs";
import { SHARE_IMAGE } from "@/lib/share";

// The landing page (v15, D1, #4429).
//
// The body of the page is `LandingPage` — the lean seven-section composition
// the owner picked from the v14 review, refined in v15. This file keeps only
// the shell: the nav, the metadata, and the footer. The vertical rails live
// in the root layout so every route shares them.
//
// The closing wordmark is the studio mark (`BrandWordmark`) at page width,
// the same component as the hero and the top bar.

export const metadata: Metadata = {
  title: "digithings — AI infrastructure in a glass box",
  description:
    "AI infrastructure you run yourself: nine modules that plug into the stack you already " +
    "run, rather than replacing it. Self-host on your own hosts, with your own keys and providers, " +
    "and a traced request path.",
  openGraph: {
    description:
      "AI infrastructure you self-host: nine modules that drop into the stack you already run. " +
      "Your own keys and providers, every step traceable.",
    images: [SHARE_IMAGE],
  },
};

export default function Home() {
  return (
    <>
      <DtNav startHidden />

      {/* The hero's pixel field runs to the very top of the page, behind the nav
          band: the first child is the hero section (`.pixel-hero`, in
          LandingPage), so it is pulled up by one nav height and given the same
          height back as padding — net zero for the flow, but its canvas box
          (`inset: 0`) now starts at y=0. The nav keeps its own background,
          backdrop blur and z-index, so the field sits behind it, never over
          the links. Negative *top margin only*: width is untouched, so no
          horizontal overflow. */}
      <main
        id="main"
        tabIndex={-1}
        className="landing relative z-10 pt-[var(--dq-nav-h)] [&>.pixel-hero]:-mt-[var(--dq-nav-h)] [&>.pixel-hero]:pt-[var(--dq-nav-h)]"
      >
        <LandingPage embedOrigin={embedOriginForChat()} />
      </main>

      <FooterWordmark />
      <DtFooter />
    </>
  );
}
