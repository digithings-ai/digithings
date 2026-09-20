import { Colophon, CtaLink, PricingTierCard, Reveal, WordReveal, subsystems } from "@digithings/ui";
import { ContactMailto } from "@digithings/ui";
import { buttonVariants } from "@digithings/ui/ui";
import { PRICING_TIERS, PRICING_FAQ } from "./_pricing";
import { SiteNav } from "@/components/landing/SiteNav";
import { SiteFooter } from "@/components/landing/SiteFooter";
import { HeroArtefact } from "@/components/landing/HeroArtefact";
import { LiveTickerRow } from "@/components/landing/LiveTickerRow";
import { LivePortfolioPanel } from "@/components/landing/DashboardPortfolioPanel";
import { PipelineGallery } from "@/components/landing/PipelineGallery";
import { StrategySuite } from "@/components/landing/StrategySuite";
import { CloneRepoButton } from "@/components/landing/CloneRepoButton";
import { MetricsOdometer } from "@/components/landing/MetricsOdometer";

// Real figures only — each one is mined from shipped data, never invented:
// subsystem count from the shared subsystems registry (research · portfolio ·
// execution), trade count summed live from the Supabase strategy index (inside
// <MetricsOdometer/>), the phase count from the single pipeline data file, and
// the zero is deliberate: routing is off by default, live venue tokens are
// refused, and nothing is sent to a venue yet.
//
// gloom-informed landing (#4430): a one-line mono value proposition over a
// product artefact (not a canvas mesh) → live market ticker → the metrics band
// → the research→portfolio pipeline as a keycap-chip function gallery → the
// live paper book → the strategy suite → the one WordReveal claim → pricing.
// Client islands; the page stays a server component.
export default function Home() {
  return (
    <>
      <SiteNav />
      <main id="main" tabIndex={-1}>
        <section className="section">
          <div className="wrap">
            <div className="mx-auto max-w-[1120px]">
              <h1 className="font-display text-[clamp(1.9rem,3.4vw,2.4rem)] font-normal leading-[1.12] tracking-[-0.02em] text-ink">
                A quant research desk in a glass box you own.
              </h1>
              <p className="mt-[1.1rem] max-w-[62ch] text-[1.05rem] leading-[1.6] text-ink-soft">
                Research runs daily and portfolio sizes the risk, through backtest to a tearsheet.
                Open-source and self-hosted, so work that once needed a team runs for one.
              </p>
              <div className="mt-[1.6rem] flex flex-wrap items-center gap-[0.9rem]">
                <CtaLink href="/dashboard/" aria-label="Open the dashboard">
                  Open dashboard <span aria-hidden="true">→</span>
                </CtaLink>
              </div>
              <div className="mt-[clamp(2rem,4vw,3rem)]">
                <HeroArtefact />
              </div>
            </div>
          </div>
        </section>

        {/* The single market-pulse tape right under the hero: one shared
            StockTicker row carrying crypto (keyless Coinbase WS) then the equity
            majors (seeded from the daily-close view, live intraday from the
            feed). A client island; SSR-safe (renders a muted "connecting" line
            until quotes arrive). */}
        <LiveTickerRow />

        <section className="section" id="metrics">
          <div className="wrap">
            <Reveal>
              <div className="text-center">
                <span className="kicker">{"// by the numbers"}</span>
                <h2 className="dq-title">The desk, in four numbers.</h2>
                <p className="dq-sub mx-auto">
                  No projections — every figure is a property of the shipped stack: the
                  subsystems, the pipeline, and the published tearsheets. Live stays zero
                  because nothing is sent to a venue yet.
                </p>
              </div>
            </Reveal>
            <Reveal>
              <MetricsOdometer
                subsystemCount={subsystems.length}
                className="mx-auto mt-[2.2rem] max-w-[880px]"
              />
            </Reveal>
          </div>
        </section>

        <PipelineGallery />

        {/* The payoff of the research book: positions the pipeline
            maintains, marked live off the same feed. Client island; SSR-safe
            (renders a plain "connects on deploy" card without env vars). */}
        <LivePortfolioPanel />

        <StrategySuite />

        {/* No section padding here: the WordReveal track is its own breathing
            room (the line rides in, pins at mid-viewport for a beat, and the
            page flows on) — section padding on top of it reads as a dead gap.
            The claim reuses the hero's own words — one voice, no re-voicing. */}
        <section id="claim" aria-label="Research to conviction, in a glass box you own">
          <div className="wrap">
            <WordReveal id="claim-reveal" text="Research to conviction. In a glass box you own." />
          </div>
        </section>

        <section className="section" id="pricing">
          <div className="wrap">
            <Reveal>
              <div className="text-center">
                <span className="kicker">{"// pricing"}</span>
                <h2 className="dq-title">Own it, or have it run for you.</h2>
                <p className="dq-sub mx-auto">
                  digiquant is open core, and it is built on the same digithings modules you can
                  deploy yourself. Self-host the whole stack at no cost, join the waitlist for
                  managed hosting, or talk to us about enterprise — the same engine either way.
                </p>
              </div>
            </Reveal>
            {/* Tier cards are the shared PricingTierCard (hero voice, #1417) —
                one grammar with the /contact tiers; the featured tier wears the
                shared flat accent wash. The app owns the grid (three-up from
                768px). */}
            <div className="mt-[2.2rem]">
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
                        <ContactMailto
                          className={buttonVariants({ variant: "default" })}
                          email={tier.cta.email}
                          subject={tier.cta.subject}
                        >
                          {tier.cta.label} <span aria-hidden="true">→</span>
                        </ContactMailto>
                      ) : null
                    }
                  />
                ))}
              </Reveal>
            </div>
            <div className="mt-[3rem] text-center">
              <Reveal>
                <h3 className="dq-title text-[clamp(1.3rem,2.4vw,1.7rem)]">Questions</h3>
              </Reveal>
            </div>
            <div className="mt-[1.2rem]">
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
      <SiteFooter />
    </>
  );
}
