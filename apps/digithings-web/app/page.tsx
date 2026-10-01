import type { Metadata } from "next";

import { DtFooter } from "@/components/DtFooter";
import { DtNav } from "@/components/DtNav";
import { FooterWordmark } from "@/components/landing/PixelWordmark";
import { LandingPage } from "@/components/landing/LandingPage";
import { embedOriginForChat } from "@/lib/security-headers.mjs";

// The landing page (v15, D1, #4429).
//
// The body of the page is `LandingPage` — the lean seven-section composition
// the owner picked from the v14 review, refined in v15. This file keeps only
// the shell: the nav, the metadata, and the footer. The vertical rails live
// in the root layout so every route shares them.
//
// The closing wordmark is the hero's pixel lockup (`PixelWordmark`) at page
// width, so the footer mark and the header mark are the same family.

export const metadata: Metadata = {
  title: "digithings — AI infrastructure in a glass box",
  description:
    "AI infrastructure you run yourself: nine modules that plug into the stack you already "
    + "run, rather than replacing it. Self-host on your own hosts, with your own keys and providers, "
    + "and a traced request path.",
  openGraph: {
    description:
      "AI infrastructure you self-host: nine modules that drop into the stack you already run. "
      + "Your own keys and providers, every step traceable.",
  },
};

export default function Home() {
  return (
    <>
      <DtNav />

      <main id="main" tabIndex={-1} className="landing relative z-10 pt-[var(--dq-nav-h)]">
        <LandingPage embedOrigin={embedOriginForChat()} />
      </main>

      <FooterWordmark />
      <DtFooter />
    </>
  );
}
