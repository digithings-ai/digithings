import { Footer, Reveal } from "@digithings/web";
import { DQ_FOOTER, DQ_FOOTER_META } from "./_nav";
import { DqNav } from "@/components/landing/DqNav";
import { HeroMesh } from "@/components/landing/HeroMesh";
import { ResearchPipeline } from "@/components/landing/ResearchPipeline";
import { OlympusScene } from "@/components/landing/OlympusScene";
import { StrategySuite } from "@/components/landing/StrategySuite";

// v7 scroll-driven landing: mesh hero → linear pipeline → Olympus scrolly →
// strategy suite → pricing. Client islands; page stays a server component.
export default function Home() {
  return (
    <>
      <DqNav />
      <main>
        <HeroMesh>
          <h1 className="dqhero-h1">
            <span className="ln">
              <span>A quant hedge fund.</span>
            </span>
            <span className="ln">
              <span>
                <em>In a box you own.</em>
              </span>
            </span>
          </h1>
          <p className="dqhero-lede">
            The research-to-execution stack an institutional desk would build — <b>Atlas</b>{" "}
            researches, <b>Hermes</b> sizes the risk, <b>Kairos</b> executes. Open-source and
            self-hosted, so a fund that once needed a team now runs for one.
          </p>
          <div className="dqhero-cta dqhero-scrollcue">
            <span className="dqhero-scroll-label">Scroll to explore</span>
            <div className="dqhero-scroll" aria-hidden="true" />
          </div>
        </HeroMesh>

        <ResearchPipeline />

        <OlympusScene />

        <StrategySuite />

        <section className="section" id="pricing">
          <div className="wrap">
            <Reveal>
              <div style={{ textAlign: "center" }}>
                <div className="dq-eyebrow">Pricing</div>
                <h2 className="dq-title">Open core. Managed tier for Atlas.</h2>
                <p className="dq-sub" style={{ marginInline: "auto" }}>
                  Self-host the full stack at no cost. The managed Atlas tier adds SLAs, onboarding,
                  and operational support.
                </p>
              </div>
            </Reveal>
            <div className="grid dq-pricing" style={{ marginInline: "auto", marginTop: "2.2rem" }}>
              <Reveal className="price-card">
                <h3>Open core</h3>
                <p className="price">
                  self-host · <span className="dq-up">free</span>
                </p>
                <ul>
                  <li>Full stack, MIT / Apache-licensed</li>
                  <li>NautilusTrader execution engine</li>
                  <li>Research → backtest → execution pipeline</li>
                  <li>Community support on GitHub</li>
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
                <h3>Managed Atlas</h3>
                <p className="price">contact</p>
                <ul>
                  <li>Managed Atlas runner with SLA</li>
                  <li>Custom strategy onboarding</li>
                  <li>Priority fixes + roadmap input</li>
                  <li>Optional on-prem deployment</li>
                </ul>
                <a className="btn btn-primary" href="mailto:hello@digithings.ai">
                  Get in touch <span aria-hidden="true">→</span>
                </a>
              </Reveal>
            </div>
            <Reveal>
              <p className="dq-built" style={{ textAlign: "center", marginTop: "2.2rem" }}>
                digiquant is the quant module of{" "}
                <a href="https://digithings.ai" target="_blank" rel="noopener noreferrer">
                  the digithings platform
                </a>{" "}
                — the same open-core, self-hosted, audit-on stack.
              </p>
            </Reveal>
          </div>
        </section>
      </main>
      <Footer links={DQ_FOOTER} meta={DQ_FOOTER_META} />
    </>
  );
}
