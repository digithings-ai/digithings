import Link from "next/link";
import { Footer, Reveal } from "@digithings/web";
import { DQ_FOOTER, DQ_FOOTER_META } from "./_nav";
import { PRICING_TIERS, PRICING_FAQ } from "./_pricing";
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
          <div className="dqhero-cta">
            <Link className="btn btn-primary" href="/#olympus">
              Open Olympus <span aria-hidden="true">→</span>
            </Link>
            <Link className="btn btn-ghost" href="/strategies">
              Browse strategies
            </Link>
          </div>
          <div className="trust-strip" style={{ marginTop: "1.7rem" }}>
            <span className="trust-strip__item">NautilusTrader</span>
            <span className="trust-strip__item">open core</span>
            <span className="trust-strip__item">Atlas · Hermes · Kairos</span>
          </div>
          {/* Real values (no placeholders): 3 reference strategies (BTC/ETH/SOL,
              public/strategies/index.json) and the 3 specialist agents named in
              the lede. Static render — the count-up is the vanilla stat-counter.js
              path (dead in React); a React count-up is a follow-up, not wired here. */}
          <div className="stat-counter-row" style={{ marginTop: "2.1rem" }}>
            <div className="stat-counter">
              <span className="stat-counter__value">3</span>
              <span className="stat-counter__label">reference strategies</span>
            </div>
            <div className="stat-counter">
              <span className="stat-counter__value">3</span>
              <span className="stat-counter__label">specialist agents</span>
            </div>
          </div>
        </HeroMesh>

        <section className="section" id="features">
          <div className="wrap">
            <Reveal className="section-head center">
              <span className="kicker">{"// what's inside"}</span>
              <h2>Research, execution, and the terms to run it.</h2>
            </Reveal>
            <Reveal className="bento">
              <Link className="bento__cell" href="#olympus">
                <div className="bento__kicker">{"// pipeline"}</div>
                <div className="bento__title">Research → execution</div>
                <p className="bento__body">
                  Atlas researches, Hermes sizes the risk, Kairos executes — one live pipeline you can
                  watch end to end.
                </p>
                <span className="bento__cta">
                  See the pipeline <span aria-hidden="true">→</span>
                </span>
              </Link>
              <Link className="bento__cell" href="/strategies">
                <div className="bento__kicker">{"// strategies"}</div>
                <div className="bento__title">Reference strategies</div>
                <p className="bento__body">
                  BTC, ETH, and SOL reference strategies with full backtest tearsheets — clone and run
                  them yourself.
                </p>
                <span className="bento__cta">
                  Browse strategies <span aria-hidden="true">→</span>
                </span>
              </Link>
              <Link className="bento__cell bento__cell--span-2" href="#pricing">
                <div className="bento__kicker">{"// pricing"}</div>
                <div className="bento__title">Own it, or have it hosted</div>
                <p className="bento__body">
                  Open core and free to self-host, or a managed Olympus runner with an SLA — the same
                  engine either way.
                </p>
                <span className="bento__cta">
                  See pricing <span aria-hidden="true">→</span>
                </span>
              </Link>
            </Reveal>
          </div>
        </section>

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
            <div style={{ marginTop: "2.2rem" }}>
              <Reveal className="pricing">
                {PRICING_TIERS.map((tier) => (
                  <div
                    key={tier.id}
                    className={`pricing__tier${tier.featured ? " pricing__tier--featured" : ""}`}
                  >
                    <div className="pricing__name">{tier.name}</div>
                    <div className="pricing__price">
                      {tier.price}
                      {tier.cadence ? <small> {tier.cadence}</small> : null}
                    </div>
                    <p className="pricing__desc">{tier.desc}</p>
                    <ul className="pricing__features">
                      {tier.features.map((feature) => (
                        <li key={feature}>{feature}</li>
                      ))}
                    </ul>
                    <div className="pricing__cta">
                      {tier.id === "self" ? (
                        <CloneRepoButton />
                      ) : tier.cta ? (
                        <a className="btn btn-primary" href={tier.cta.href}>
                          {tier.cta.label} <span aria-hidden="true">→</span>
                        </a>
                      ) : null}
                    </div>
                  </div>
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

        <section aria-label="Get started">
          <Reveal className="closing-cta">
            <div className="closing-cta__inner">
              <h2 className="closing-cta__title">One graph, research to execution.</h2>
              <p className="closing-cta__sub">
                Backtest, optimize, and route strategies on NautilusTrader with Atlas and Hermes.
              </p>
              <div className="closing-cta__actions">
                <Link className="btn btn-primary" href="/#olympus">
                  Open Olympus
                </Link>
                <Link className="closing-cta__secondary" href="/strategies">
                  Browse strategies <span aria-hidden="true">→</span>
                </Link>
              </div>
            </div>
          </Reveal>
        </section>
      </main>
      <Footer links={DQ_FOOTER} meta={DQ_FOOTER_META} />
    </>
  );
}
