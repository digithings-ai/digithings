import {
  Colophon,
  Footer,
  PricingTierCard,
  Reveal,
  WordReveal,
  subsystems,
} from "@digithings/web";
import { DQ_FOOTER, DQ_FOOTER_META } from "./_nav";
import { PRICING_TIERS, PRICING_FAQ } from "./_pricing";
import { ContactMailto } from "@/components/ContactMailto";
import { SiteNav } from "@/components/landing/SiteNav";
import { HeroMesh } from "@/components/landing/HeroMesh";
import { LiveTickerRow } from "@/components/landing/LiveTickerRow";
import { LivePortfolioPanel } from "@/components/landing/OlympusPortfolioPanel";
import { ResearchPipeline } from "@/components/landing/ResearchPipeline";
import { PipelineScene } from "@/components/landing/PipelineScene";
import { StrategySuite } from "@/components/landing/StrategySuite";
import { CloneRepoButton } from "@/components/landing/CloneRepoButton";
import { MetricsOdometer } from "@/components/landing/MetricsOdometer";

// Real figures only — each one is mined from shipped data, never invented:
// subsystem count from the shared subsystems registry (research · portfolio ·
// execution), trade count summed live from the Supabase strategy index (inside
// <MetricsOdometer/>), the 7 pipeline stages from ResearchPipeline's FLOW
// (01 research → 07 export), and the zero is literal: there is no execution
// path at all — every broker adapter under digiquant/src/digiquant/brokers/
// raises NotImplementedError, so no order can be submitted, gated or not.

// v7 scroll-driven landing, now wearing the flagship expressive grammar
// (#1450): mesh hero → live market ticker → digit-roll OdometerStrip →
// linear pipeline → desk scrolly → strategy suite → the one WordReveal
// claim → pricing. Client islands; page stays a server component. Every
// motion moment honors prefers-reduced-motion and reads with no JS.
export default function Home() {
  return (
    <>
      <SiteNav />
      <main>
        <HeroMesh>
          <h1 className="dqhero-h1">
            <span className="ln">
              <span>A quant research desk</span>
            </span>
            <span className="ln">
              <span>in a glass box</span>
            </span>
            <span className="ln">
              <span>
                <em>you own</em>
              </span>
            </span>
          </h1>
          <p className="dqhero-lede">
            The research stack an institutional desk would build — research runs daily and{" "}
            portfolio sizes the risk, through backtest to a tearsheet. Open-source and
            self-hosted, so work that once needed a team runs for one.
          </p>
          <div className="dqhero-cta dqhero-scrollcue">
            {/* Claim + install: shared .cmdline (site.css) is the diegetic
                proof; the loud control is ink/paper, never a teal pill. */}
            <p className="cmdline">
              <span className="prompt">$</span>
              git clone https://github.com/digithings-ai/digithings.git
            </p>
            <a className="btn btn-primary" href="/olympus/">
              Open digiquant
            </a>
            <span className="dqhero-scroll-label">Scroll to explore</span>
            <div className="dqhero-scroll" aria-hidden="true" />
          </div>
        </HeroMesh>

        {/* The single market-pulse tape right under the hero: one shared
            StockTicker row carrying crypto (keyless Coinbase WS) then the equity
            majors (seeded from the daily-close view, live intraday from the
            feed). A client island; SSR-safe (renders a muted "connecting" line
            until quotes arrive). */}
        <LiveTickerRow />

        <section className="section" id="metrics">
          <div className="wrap">
            <Reveal>
              <div style={{ textAlign: "center" }}>
                <span className="kicker">{"// by the numbers"}</span>
                <h2 className="dq-title">The desk, in four numbers.</h2>
                <p className="dq-sub" style={{ marginInline: "auto" }}>
                  No projections — every figure is a property of the shipped stack: the
                  subsystems, the pipeline, and the published tearsheets. Live stays zero because
                  there is no execution path: every broker adapter is a stub.
                </p>
              </div>
            </Reveal>
            <Reveal>
              <MetricsOdometer subsystemCount={subsystems.length} className="mx-auto mt-[2.2rem] max-w-[880px]" />
            </Reveal>
          </div>
        </section>

        <ResearchPipeline />

        <PipelineScene />

        {/* The payoff of the research book: positions the pipeline
            maintains, marked live off the same feed. Client island; SSR-safe
            (renders a plain "connects on deploy" card without env vars). */}
        <LivePortfolioPanel />

        <StrategySuite />

        {/* No .section padding here: the WordReveal track is its own breathing
            room (the line rides in, pins at mid-viewport for a beat, and the
            page flows on) — section padding on top of it reads as a dead gap.
            The claim reuses the hero's own words ("In a box you own") — one
            voice, no re-voicing. */}
        <section id="claim" aria-label="Research to conviction, in a glass box you own">
          <div className="wrap">
            <WordReveal id="claim-reveal" text="Research to conviction. In a glass box you own." />
          </div>
        </section>

        <section className="section" id="pricing">
          <div className="wrap">
            <Reveal>
              <div style={{ textAlign: "center" }}>
                <span className="kicker">{"// pricing"}</span>
                <h2 className="dq-title">Own it, or have it run for you.</h2>
                <p className="dq-sub" style={{ marginInline: "auto" }}>
                  digiquant is open core, and it is built on the same digithings modules you can
                  deploy yourself. Self-host the whole stack at no cost, join the waitlist for
                  managed hosting, or talk to us about enterprise — the same engine either way.
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
                        <ContactMailto className="btn btn-primary" href={tier.cta.href}>
                          {tier.cta.label} <span aria-hidden="true">→</span>
                        </ContactMailto>
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
      {/* sweep: the homepage opts into the reference footer's glow sweep
          (flagship grammar, #1450) — subpage consumers keep the
          outline-only default. */}
      <Colophon name="digi" suffix="quant" sweep />
      <Footer links={DQ_FOOTER} meta={DQ_FOOTER_META} />
    </>
  );
}
