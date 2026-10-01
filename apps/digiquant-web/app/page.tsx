import {
  Colophon,
  ContactMailto,
  CtaLink,
  Footer,
  NumberedStages,
  OdometerStrip,
  Reveal,
  SocialRow,
  WordReveal,
} from "@digithings/ui";
import { DQ_CONTACT_EMAIL, DQ_FOOTER, DQ_FOOTER_META } from "./_nav";
import { SiteNav } from "@/components/landing/SiteNav";
import { HeroMesh } from "@/components/landing/HeroMesh";
import { DeskTour } from "@/components/showcase/DeskTour";
import { VideoSlots } from "@/components/showcase/VideoSlots";
import { PartnerStory } from "@/components/showcase/PartnerStory";
import {
  METHOD_STAGES,
  SHOWCASE_METRICS,
  STORY_STAGES,
} from "@/lib/showcase";

export default function Home() {
  return (
    <>
      <SiteNav />
      <main id="main" tabIndex={-1}>
        <HeroMesh>
          <h1 className="dqhero-h1">
            <span className="ln">
              <span>The research desk.</span>
            </span>
            <span className="ln">
              <span>
                On <em>display</em>.
              </span>
            </span>
          </h1>
          <p className="dqhero-lede">
            Showcase of the digiquant dashboard — tour, method, and the path from
            digichat to a Nautilus backtest. The tools live in the product.
          </p>
          <div className="dqhero-cta">
            <p className="cmdline">
              <span className="prompt">$</span>
              git clone https://github.com/digithings-ai/digithings.git
            </p>
            <CtaLink href="/#desk" variant="default" size="default">
              Tour the desk
            </CtaLink>
            <a className="dqhero-scroll-label" href="#watch">
              Watch
            </a>
            <div className="dqhero-scroll" aria-hidden="true" />
          </div>
        </HeroMesh>

        <section className="section" id="metrics">
          <div className="wrap">
            <Reveal className="section-head center">
              <span className="kicker">{"// by the numbers"}</span>
              <h2>Paper marks. Zero venues.</h2>
              <p>Every figure is a property of the shipped stack. Nothing is sent to a venue.</p>
            </Reveal>
            <Reveal>
              <OdometerStrip stats={SHOWCASE_METRICS} columns={2} className="mx-auto max-w-[560px]" />
            </Reveal>
          </div>
        </section>

        <section className="section section-alt" id="desk">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// the desk"}</span>
              <h2>Research and the book, at a glance.</h2>
              <p>
                Guided display of the dashboard: compose, the paper book, the journal.
                The live surface ships in-app.
              </p>
            </Reveal>
            <Reveal>
              <DeskTour />
            </Reveal>
          </div>
        </section>

        <section className="section" id="watch">
          <div className="wrap">
            <Reveal className="section-head center">
              <span className="kicker">{"// watch"}</span>
              <h2>Method, on film.</h2>
              <p>Short films of the method and the chat-to-backtest arc. Slots first; pictures later.</p>
            </Reveal>
            <Reveal>
              <VideoSlots />
            </Reveal>
          </div>
        </section>

        <section className="section section-alt" id="method">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// method"}</span>
              <h2>How the desk thinks.</h2>
              <p>Tooling, workflow, and capabilities — explained here, operated in the dashboard.</p>
            </Reveal>
            <NumberedStages stages={METHOD_STAGES} className="max-w-[760px]" />
          </div>
        </section>

        <section className="section" id="partners">
          <div className="wrap">
            <Reveal className="section-head center">
              <span className="kicker">{"// partners"}</span>
              <h2>Chart tape. Desk language.</h2>
              <p>LuxAlgo and Gloomberg belong in the story. Embeds land in these frames.</p>
            </Reveal>
            <Reveal>
              <PartnerStory />
            </Reveal>
          </div>
        </section>

        <section className="section section-alt" id="story">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// the arc"}</span>
              <h2>digichat to Nautilus.</h2>
              <p>
                A demo narrative of compose, backtest, inspect, hand off. The builder is the
                dashboard.
              </p>
            </Reveal>
            <NumberedStages stages={STORY_STAGES} className="max-w-[760px]" />
          </div>
        </section>

        <section id="claim" aria-label="The desk, on display">
          <div className="wrap">
            <WordReveal id="claim-reveal" text="The desk. On display. In a box you own." />
          </div>
        </section>

        <section className="section text-center" id="contact">
          <Reveal className="wrap">
            <div className="section-head center">
              <span className="kicker">{"// contact"}</span>
              <h2>Open core. Self-host, or talk.</h2>
              <p>
                The stack is MIT-licensed. Take it. What we sell is fitting it to the desk you
                already run.
              </p>
            </div>
            <div className="mt-[2rem] flex flex-wrap justify-center gap-[0.8rem]">
              <CtaLink href="/contact" variant="default" size="default">
                Self-host or managed <span aria-hidden="true">→</span>
              </CtaLink>
              <ContactMailto
                email={DQ_CONTACT_EMAIL}
                className="font-mono text-[0.88rem] text-ink-mute"
                subject="digiquant%20inquiry"
                showAddress
              >
                Or email us
              </ContactMailto>
            </div>
            <div className="mt-[1.6rem] flex justify-center">
              <SocialRow />
            </div>
          </Reveal>
        </section>
      </main>
      <Colophon name="digi" suffix="quant" sweep />
      <Footer links={DQ_FOOTER} meta={DQ_FOOTER_META} />
    </>
  );
}
