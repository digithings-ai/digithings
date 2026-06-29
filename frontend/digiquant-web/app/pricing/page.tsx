import type { Metadata } from "next";
import { Footer, Reveal } from "@digithings/web";
import { DQ_CONTACT_EMAIL, DQ_FOOTER, DQ_FOOTER_META } from "../_nav";
import { DqNav } from "@/components/landing/DqNav";
import { AmbientMesh } from "@/components/landing/AmbientMesh";

export const metadata: Metadata = {
  title: "Pricing — digiquant",
  description:
    "Self-manage the full open-core stack for free, or have Olympus managed for you. What's included in each.",
};

// Detailed two-tier pricing: self-managed (open core) vs. managed. The home page
// keeps a short pricing teaser; this is the full breakdown linked from the nav.
const SELF = [
  "The complete stack — research, portfolio management, and execution",
  "MIT / Apache-licensed; clone, fork, and run it on hardware you own",
  "Atlas research, Hermes deliberation, and the backtest pipeline",
  "Your data, your machines, your keys — nothing leaves your infra",
  "Community support on GitHub",
];

const MANAGED = [
  "A hosted Olympus runner, operated for you with an SLA",
  "Onboarding and custom strategy setup",
  "Priority fixes and a say in the roadmap",
  "Optional on-prem / VPC deployment",
  "Everything in self-managed, kept running",
];

export default function PricingPage() {
  return (
    <>
      <DqNav />
      <main className="dq-subpage">
        <AmbientMesh />
        <section className="section">
          <div className="wrap">
            <Reveal>
              <div style={{ textAlign: "center" }}>
                <div className="dq-eyebrow">Pricing</div>
                <h2 className="dq-title" style={{ marginInline: "auto" }}>
                  Own it, or have it run for you.
                </h2>
                <p className="dq-sub" style={{ marginInline: "auto" }}>
                  digiquant is open core. Self-manage the whole stack at no cost, or let us
                  manage Olympus for you. Same engine either way — the difference is who keeps
                  it running.
                </p>
              </div>
            </Reveal>

            <div className="grid dq-pricing" style={{ marginInline: "auto", marginTop: "2.4rem" }}>
              <Reveal className="price-card">
                <h3>Self-managed</h3>
                <p className="price">
                  open core · <span className="dq-up">free</span>
                </p>
                <ul>
                  {SELF.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>
                <a
                  className="btn btn-ghost"
                  href="https://github.com/digithings-ai"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  View on GitHub <span aria-hidden="true">→</span>
                </a>
              </Reveal>

              <Reveal className="price-card accent">
                <span className="price-flag">managed</span>
                <h3>Managed</h3>
                <p className="price">contact us</p>
                <ul>
                  {MANAGED.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>
                <a className="btn btn-primary" href={`mailto:${DQ_CONTACT_EMAIL}?subject=Managed%20Olympus`}>
                  Get in touch <span aria-hidden="true">→</span>
                </a>
              </Reveal>
            </div>

            <Reveal>
              <p className="dq-built" style={{ textAlign: "center", marginTop: "2.4rem" }}>
                Not sure which fits? Start self-managed — it&rsquo;s the full product — and{" "}
                <a href={`mailto:${DQ_CONTACT_EMAIL}?subject=Managed%20Olympus`}>get in touch</a> if you
                later want it managed.
              </p>
            </Reveal>
          </div>
        </section>
      </main>
      <Footer links={DQ_FOOTER} meta={DQ_FOOTER_META} />
    </>
  );
}
