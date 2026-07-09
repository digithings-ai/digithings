import { Colophon, Footer, PricingTierCard, Reveal } from "@digithings/web";
import { DQ_FOOTER, DQ_FOOTER_META } from "./_nav";
import { PRICING_TIERS, PRICING_FAQ } from "./_pricing";
import { SiteNav } from "@/components/landing/SiteNav";
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
      <SiteNav />
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
                <span className="kicker">{"// pricing"}</span>
                <h2 className="dq-title">Own it, or have it run for you.</h2>
                <p className="dq-sub" style={{ marginInline: "auto" }}>
                  digiquant is open core. Self-host the whole stack at no cost, join the waitlist for
                  managed Olympus, or talk to us about enterprise — the same engine either way.
                </p>
              </div>
            </Reveal>
            {/* Tier cards are the shared PricingTierCard (hero voice, #1417) —
                one grammar with the /contact tiers; the featured tier wears the
                shared flat accent wash. The app owns the grid (three-up from
                768px, the old site.css .pricing breakpoint). */}
            <div style={{ marginTop: "2.2rem" }}>
              <Reveal className="grid grid-cols-1 gap-[1.25rem] min-[768px]:grid-cols-3">
                {PRICING_TIERS.map((tier) => (
                  <PricingTierCard
                    key={tier.id}
                    variant="hero"
                    nameAs="h3"
                    className="h-full"
                    accent={tier.featured}
                    name={tier.name}
                    priceLine={
                      <>
                        {tier.price}
                        {tier.cadence ? <span className="text-ink-mute"> {tier.cadence}</span> : null}
                      </>
                    }
                    description={tier.desc}
                    features={[...tier.features]}
                    cta={
                      tier.id === "self" ? (
                        <CloneRepoButton />
                      ) : tier.cta ? (
                        <a className="btn btn-primary" href={tier.cta.href}>
                          {tier.cta.label} <span aria-hidden="true">→</span>
                        </a>
                      ) : null
                    }
                  />
                ))}
              </Reveal>
            </div>
            <div style={{ marginTop: "3rem", textAlign: "center" }}>
              <Reveal>
                <h3 className="dq-title" style={{ fontSize: "clamp(1.3rem, 2.4vw, 1.7rem)" }}>
                  Questions
                </h3>
              </Reveal>
            </div>
            <div style={{ marginTop: "1.2rem" }}>
              <Reveal className="faq">
                {PRICING_FAQ.map((item, i) => (
                  <details className="faq__item" name="dq-pricing-faq" key={item.q} open={i === 0}>
                    <summary className="faq__q">{item.q}</summary>
                    <p className="faq__a">{item.a}</p>
                  </details>
                ))}
              </Reveal>
            </div>
          </div>
        </section>
      </main>
      <Colophon name="digi" suffix="quant" />
      <Footer links={DQ_FOOTER} meta={DQ_FOOTER_META} />
    </>
  );
}
