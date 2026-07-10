import {
  Colophon,
  Footer,
  Marquee,
  OdometerStrip,
  PricingTierCard,
  Reveal,
  WordReveal,
  subsystems,
  type MarqueeItem,
  type OdometerStat,
} from "@digithings/web";
import { DQ_FOOTER, DQ_FOOTER_META } from "./_nav";
import { PRICING_TIERS, PRICING_FAQ } from "./_pricing";
import { SiteNav } from "@/components/landing/SiteNav";
import { HeroMesh } from "@/components/landing/HeroMesh";
import { ResearchPipeline } from "@/components/landing/ResearchPipeline";
import { OlympusScene } from "@/components/landing/OlympusScene";
import { StrategySuite } from "@/components/landing/StrategySuite";
import { CloneRepoButton } from "@/components/landing/CloneRepoButton";
import strategyIndex from "@/public/strategies/index.json";
import type { StrategyIndexEntry } from "@/components/tearsheet/types";

// The stack the site copy actually claims (flagship grammar, #1450): the
// pipeline runs Optuna + NautilusTrader (ResearchPipeline steps 05/06, pricing
// FAQ), Atlas/Hermes are LangGraph graphs persisting views to Supabase over
// Polars frames (shared subsystems data), keys ride LiteLLM (pricing FAQ), and
// the whole box ships as a docker compose command (subsystem pages). Glyphs
// come from the shared Simple Icons registry where a mark exists;
// NautilusTrader, Optuna, and LiteLLM have none and read text-only.
const STACK: MarqueeItem[] = [
  { name: "NautilusTrader" },
  { name: "Polars", icon: "polars" },
  { name: "LangGraph", icon: "langgraph" },
  { name: "Optuna" },
  { name: "LiteLLM" },
  { name: "Supabase", icon: "supabase" },
  { name: "Docker", icon: "docker" },
];

// Real figures only — each one is mined from shipped data, never invented:
// subsystem count from the shared subsystems registry (Atlas · Hermes ·
// Kairos), trade count summed from the published tearsheets' strategies
// index at build time, the 7 pipeline stages from ResearchPipeline's FLOW
// (01 research → 07 execution), and the zero is Kairos's loopback-only
// default — nothing reaches a live venue until a human flips the gate.
const TOTAL_TRADES = (strategyIndex as StrategyIndexEntry[]).reduce(
  (n, s) => n + s.total_trades,
  0,
);
const METRICS: OdometerStat[] = [
  { value: String(subsystems.length), label: "subsystems" },
  { value: "7", label: "pipeline stages" },
  { value: String(TOTAL_TRADES), label: "backtested trades" },
  { value: "0", label: "ungated live orders" },
];

// v7 scroll-driven landing, now wearing the flagship expressive grammar
// (#1450): mesh hero → drifting stack Marquee → digit-roll OdometerStrip →
// linear pipeline → Olympus scrolly → strategy suite → the one WordReveal
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

        <section className="border-y border-hair" aria-label="Built on">
          <Marquee
            items={STACK}
            tone="mute"
            speed={42}
            aria-label="Built on NautilusTrader, Polars, LangGraph, Optuna, LiteLLM, Supabase, and Docker"
            className="py-[0.95rem]"
          />
        </section>

        <section className="section" id="metrics">
          <div className="wrap">
            <Reveal>
              <div style={{ textAlign: "center" }}>
                <span className="kicker">{"// by the numbers"}</span>
                <h2 className="dq-title">The desk, in four numbers.</h2>
                <p className="dq-sub" style={{ marginInline: "auto" }}>
                  No projections — every figure is a property of the shipped stack: the
                  subsystems, the pipeline, and the published tearsheets. Live stays zero until a
                  human flips the gate.
                </p>
              </div>
            </Reveal>
            <Reveal>
              <OdometerStrip stats={METRICS} className="mx-auto mt-[2.2rem] max-w-[880px]" />
            </Reveal>
          </div>
        </section>

        <ResearchPipeline />

        <OlympusScene />

        <StrategySuite />

        {/* No .section padding here: the WordReveal track is its own breathing
            room (the line rides in, pins at mid-viewport for a beat, and the
            page flows on) — section padding on top of it reads as a dead gap.
            The claim reuses the hero's own words ("In a box you own") — one
            voice, no re-voicing. */}
        <section id="claim" aria-label="Research to execution, in a box you own">
          <div className="wrap">
            <WordReveal id="claim-reveal" text="Research to execution. In a box you own." />
          </div>
        </section>

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
      {/* sweep: the homepage opts into the reference footer's glow sweep
          (flagship grammar, #1450) — subpage consumers keep the
          outline-only default. */}
      <Colophon name="digi" suffix="quant" sweep />
      <Footer links={DQ_FOOTER} meta={DQ_FOOTER_META} />
    </>
  );
}
