import { Colophon, Footer, Reveal } from "@digithings/web";
import { DT_CONTACT_EMAIL, DT_FOOTER, DT_FOOTER_META } from "./_nav";
import { DtNav } from "@/components/DtNav";
import { HeroMesh } from "@/components/landing/HeroMesh";
import { ModuleManifest } from "@/components/landing/ModuleManifest";

// v7 landing for the DigiThings platform: a mouse-following mesh-gradient hero
// (HeroMesh + reveal-field HeroGraph), then the existing module-graph + principles
// content kept verbatim below. The mesh / graph are client islands; the page
// itself stays a server component and exports statically.
export default function Home() {
  return (
    <>
      <DtNav />

      <main>
        <HeroMesh>
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
            An open-core agentic stack — research, retrieval, and chat behind one supervisor.
            Self-hosted, BYOK, audit-on by default. No vendor lock-in, no opaque pipelines.
          </p>
          <div className="dqhero-cta">
            <p className="dqhero-scroll-label">Scroll to explore</p>
            <div className="dqhero-scroll" aria-hidden="true" />
          </div>
        </HeroMesh>

        <section className="section section-architecture" id="architecture">
          <div className="wrap">
            <Reveal className="section-head center">
              <span className="kicker">{"// the architecture"}</span>
              <h2>Ten modules, wired into one.</h2>
              <p>A supervisor at the centre routes every request to the right module — chat, quant research, or retrieval. Each one self-hosted, audited, and swappable.</p>
            </Reveal>
            <ModuleManifest />
          </div>
        </section>

        <section className="section section-alt" id="principles">
          <div className="wrap">
            <Reveal className="section-head"><span className="kicker">{"// why digithings"}</span><h2>Four properties of every module.</h2></Reveal>
            <div className="principles">
              <Reveal className="principle"><span className="principle-num">01</span><h3>Self-hosted by default</h3><p>One docker-compose file runs the whole stack on a laptop, a VM, or a cluster.</p></Reveal>
              <Reveal className="principle"><span className="principle-num">02</span><h3>BYOK, every request</h3><p>Anthropic, OpenAI, or any LiteLLM-compatible key — forwarded per-request, never stored.</p></Reveal>
              <Reveal className="principle"><span className="principle-num">03</span><h3>Audit-on by default</h3><p>Immutable JSONL audit, correlation IDs across every span, PII redacted before logs hit disk.</p></Reveal>
              <Reveal className="principle"><span className="principle-num">04</span><h3>Backend-swappable</h3><p>Swap vector DB or storage backend without touching business code.</p></Reveal>
            </div>
          </div>
        </section>

        <section className="section dqcta" id="contact">
          <Reveal className="wrap">
            <div className="dq-eyebrow">Contact</div>
            <h2 className="dq-title">Questions, enterprise, or partnership.</h2>
            <p className="dq-sub">
              The stack is open core — reach out for managed deployments, on-prem setups, or
              anything else about the platform.
            </p>
            <div className="dqcta-actions">
              <a
                className="btn btn-primary"
                href={`mailto:${DT_CONTACT_EMAIL}?subject=DigiThings%20inquiry`}
              >
                Email us <span aria-hidden="true">→</span>
              </a>
              <a
                className="btn btn-ghost"
                href={`mailto:${DT_CONTACT_EMAIL}?subject=DigiThings%20enterprise`}
              >
                Enterprise
              </a>
            </div>
            <p className="dt-contact-email">
              <a href={`mailto:${DT_CONTACT_EMAIL}`}>{DT_CONTACT_EMAIL}</a>
            </p>
          </Reveal>
        </section>
      </main>

      <Colophon name="digi" suffix="things" />
      <Footer links={DT_FOOTER} meta={DT_FOOTER_META} />
    </>
  );
}
