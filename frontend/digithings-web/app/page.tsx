import { Footer, ScrollyGraph, Reveal } from "@digithings/web";
import { DT_FOOTER, DT_FOOTER_META } from "./_nav";
import { DigiNav } from "@/components/landing/DigiNav";
import { HeroMesh } from "@/components/landing/HeroMesh";

// v7 landing for the DigiThings platform: a mouse-following mesh-gradient hero
// (HeroMesh + reveal-field HeroGraph), then the existing module-graph + principles
// content kept verbatim below. The mesh / graph are client islands; the page
// itself stays a server component and exports statically.
export default function Home() {
  return (
    <>
      <DigiNav />

      <main>
        <HeroMesh>
          <p className="dq-eyebrow">open core · ten modules online</p>
          <h1 className="dqhero-h1">
            <span className="ln">
              <span>Build agents on infrastructure</span>
            </span>
            <span className="ln">
              <span>
                <em>you own.</em>
              </span>
            </span>
          </h1>
          <p className="dqhero-lede">
            A modular, open-core agentic stack — composable services wired into one platform.
            Self-hosted, BYOK, audit-on by default. No vendor lock-in, no opaque pipelines.
          </p>
          <div className="dqhero-cta">
            <a className="btn btn-primary" href="/architecture">
              Explore the platform <span aria-hidden="true">→</span>
            </a>
            <a
              className="btn btn-ghost"
              href="https://github.com/digithings-ai"
              target="_blank"
              rel="noopener noreferrer"
            >
              View on GitHub
            </a>
          </div>
          <div className="dqhero-scroll" aria-hidden="true" />
        </HeroMesh>

        <section className="section" id="platform">
          <div className="wrap">
            <Reveal className="section-head center">
              <span className="kicker">// the platform</span>
              <h2>Ten modules, wired into one.</h2>
              <p>A supervisor at the centre routes every request to the right specialist. Scroll to walk the stack — or hover a node.</p>
            </Reveal>
          </div>
          <ScrollyGraph />
        </section>

        <section className="section section-alt" id="principles">
          <div className="wrap">
            <Reveal className="section-head"><span className="kicker">// why digithings</span><h2>Four properties of every module.</h2></Reveal>
            <div className="principles">
              <Reveal className="principle"><span className="principle-num">01</span><h3>Self-hosted by default</h3><p>One docker-compose file runs the whole stack on a laptop, a VM, or a cluster.</p></Reveal>
              <Reveal className="principle"><span className="principle-num">02</span><h3>BYOK, every request</h3><p>Anthropic, OpenAI, or any LiteLLM-compatible key — forwarded per-request, never stored.</p></Reveal>
              <Reveal className="principle"><span className="principle-num">03</span><h3>Audit-on by default</h3><p>Immutable JSONL audit, correlation IDs across every span, PII redacted before logs hit disk.</p></Reveal>
              <Reveal className="principle"><span className="principle-num">04</span><h3>Backend-swappable</h3><p>Swap vector DB or storage backend without touching business code.</p></Reveal>
            </div>
          </div>
        </section>
      </main>

      <Footer links={DT_FOOTER} meta={DT_FOOTER_META} />
    </>
  );
}
