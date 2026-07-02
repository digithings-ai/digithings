import type { Metadata } from "next";
import Link from "next/link";
import { WelcomeHero } from "./welcome-hero";
import { CodeSampleBand } from "./code-sample-band";
import "./welcome.css";

/**
 * Public "product-as-hero" marketing route for DigiChat (#1218). No auth gate —
 * a signed-in or signed-out visitor can view it; the authenticated chat stays at
 * `/` (server-gated → /login), untouched. The frozen chat screenshot (WelcomeHero)
 * is the visual hero; the CodeSampleBand pitches BYOK/API usage.
 */
export const metadata: Metadata = {
  title: "DigiChat — your stack, your keys, your audit log",
  description:
    "A self-hosted chat surface for the DigiThings stack. Bring your own key — forwarded per request, never stored — with the audit log on by default.",
};

export default function WelcomePage() {
  return (
    <div className="welcome-page">
      <section className="welcome-lead">
        <h1>Talk to your stack. Your keys, your audit log.</h1>
        <p>
          DigiChat is the self-hosted chat surface for the DigiThings stack — research,
          retrieval, and quant behind one supervisor. Bring your own key, forwarded per request
          and never stored.
        </p>
        <div className="welcome-actions">
          <Link className="welcome-cta welcome-cta-primary" href="/">
            Open DigiChat <span aria-hidden="true">→</span>
          </Link>
          <Link className="welcome-cta welcome-cta-ghost" href="/login">
            Sign in
          </Link>
        </div>
      </section>

      <WelcomeHero />

      <section>
        <p className="welcome-section-label">{"// bring your own key"}</p>
        <CodeSampleBand />
      </section>
    </div>
  );
}
