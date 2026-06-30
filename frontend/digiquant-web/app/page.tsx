import { Footer, Reveal } from "@digithings/web";
import { DQ_FOOTER, DQ_FOOTER_META } from "./_nav";
import {
  CONTACT_MANAGED_FEATURES,
  CONTACT_SELF_FEATURES,
  MANAGED_CONTACT_MAILTO,
} from "./_contact";
import { DqNav } from "@/components/landing/DqNav";
import { HeroMesh } from "@/components/landing/HeroMesh";
import { ResearchPipeline } from "@/components/landing/ResearchPipeline";
import { OlympusScene } from "@/components/landing/OlympusScene";
import { StrategySuite } from "@/components/landing/StrategySuite";
import { CloneRepoButton } from "@/components/landing/CloneRepoButton";

// v7 scroll-driven landing: mesh hero → linear pipeline → Olympus scrolly →
// strategy suite → contact. Client islands; page stays a server component.
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

        <section className="section" id="contact">
          <div className="wrap">
            <Reveal>
              <div style={{ textAlign: "center" }}>
                <span className="kicker">{"// contact"}</span>
                <h2 className="dq-title">Own it, or have it run for you.</h2>
                <p className="dq-sub" style={{ marginInline: "auto" }}>
                  digiquant is open core. Self-manage the whole stack at no cost, or let us manage
                  Olympus for you. Same engine either way — the difference is who keeps it running.
                </p>
              </div>
            </Reveal>
            <div className="grid dq-contact" style={{ marginInline: "auto", marginTop: "2.2rem" }}>
              <Reveal className="price-card">
                <h3>Self hosted</h3>
                <p className="price">
                  open core · <span className="dq-up">free</span>
                </p>
                <ul>
                  {CONTACT_SELF_FEATURES.map((feature) => (
                    <li key={feature}>{feature}</li>
                  ))}
                </ul>
                <CloneRepoButton />
              </Reveal>
              <Reveal className="price-card accent">
                <h3>Managed</h3>
                <p className="price">contact us</p>
                <ul>
                  {CONTACT_MANAGED_FEATURES.map((feature) => (
                    <li key={feature}>{feature}</li>
                  ))}
                </ul>
                <a className="btn btn-primary" href={MANAGED_CONTACT_MAILTO}>
                  Email us <span aria-hidden="true">→</span>
                </a>
              </Reveal>
            </div>
            <Reveal>
              <p className="dq-built" style={{ textAlign: "center", marginTop: "2.2rem" }}>
                Not sure which fits? Start self-managed — it&rsquo;s the full product — and{" "}
                <a href={MANAGED_CONTACT_MAILTO}>get in touch</a> if you later want it managed.
              </p>
            </Reveal>
          </div>
        </section>
      </main>
      <Footer links={DQ_FOOTER} meta={DQ_FOOTER_META} />
    </>
  );
}
