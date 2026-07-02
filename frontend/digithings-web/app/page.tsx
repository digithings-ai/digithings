import { Footer, Reveal } from "@digithings/web";
import { DT_CONTACT_EMAIL, DT_FOOTER, DT_FOOTER_META } from "./_nav";
import { DigiNav } from "@/components/landing/DigiNav";
import { HeroMesh } from "@/components/landing/HeroMesh";
import { ModuleManifest } from "@/components/landing/ModuleManifest";

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
            <div className="trust-strip" style={{ marginBottom: "0.4rem" }}>
              <span className="trust-strip__item">open core · self-hosted</span>
              <span className="trust-strip__item">BYOK · keys never stored</span>
              <span className="trust-strip__item">audit-on by default</span>
            </div>
            <p className="dqhero-scroll-label">Scroll to explore</p>
            <div className="dqhero-scroll" aria-hidden="true" />
          </div>
        </HeroMesh>

        <section className="section" id="product">
          <div className="wrap">
            <Reveal className="product-frame">
              <div className="product-frame__surface">
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.6em",
                    paddingBottom: "0.75em",
                    borderBottom: "1px solid var(--hair)",
                    marginBottom: "0.9em",
                  }}
                >
                  <span
                    style={{
                      width: "0.7em",
                      height: "0.7em",
                      borderRadius: "50%",
                      background: "var(--up)",
                      display: "inline-block",
                    }}
                  />
                  <strong>digithings · supervisor</strong>
                  <span
                    style={{
                      marginLeft: "auto",
                      color: "var(--ink-mute)",
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.8em",
                    }}
                  >
                    audit-on
                  </span>
                </div>
                <pre
                  style={{
                    fontFamily: "var(--font-mono)",
                    margin: 0,
                    color: "var(--ink-soft)",
                    lineHeight: 1.75,
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {`$ export ANTHROPIC_API_KEY=sk-…   # BYOK — forwarded, never stored
$ digithings chat "summarize the latest filings"
supervisor → routes across research · retrieval · chat
✓ answered · correlation id logged · PII redacted before disk`}
                </pre>
              </div>
            </Reveal>
            <p className="product-frame__caption">One supervisor routes every request — your keys, audited by default.</p>
          </div>
        </section>

        <section className="section section-architecture" id="architecture">
          <div className="wrap">
            <Reveal className="section-head center">
              <span className="kicker">{"// the architecture"}</span>
              <h2>Ten modules, wired into one.</h2>
              <p>A supervisor at the centre routes every request to the right module — chat, quant research, or retrieval. Each one self-hosted, audited, and swappable.</p>
            </Reveal>
            <div style={{ margin: "2.75rem 0 3.25rem" }}>
              <Reveal className="bento">
                <a
                  className="bento__cell accent-digigraph"
                  href="https://github.com/digithings-ai"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <div className="bento__kicker">{"// orchestration"}</div>
                  <div className="bento__title">digigraph</div>
                  <p className="bento__body">One supervisor decides which specialist runs. Every time.</p>
                  <span className="bento__cta">Source <span aria-hidden="true">→</span></span>
                </a>
                <a
                  className="bento__cell accent-digiquant"
                  href="https://digiquant.io"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <div className="bento__kicker">{"// quant engine"}</div>
                  <div className="bento__title">digiquant</div>
                  <p className="bento__body">Strategy research that ends in an order, not a markdown file.</p>
                  <span className="bento__cta">digiquant.io <span aria-hidden="true">→</span></span>
                </a>
                <a className="bento__cell accent-digisearch" href="https://github.com/digithings-ai" target="_blank" rel="noopener noreferrer">
                  <div className="bento__kicker">{"// retrieval"}</div>
                  <div className="bento__title">digisearch</div>
                  <p className="bento__body">Production RAG without a stack rewrite when you switch vector DB.</p>
                  <span className="bento__cta">Source <span aria-hidden="true">→</span></span>
                </a>
                <a className="bento__cell accent-digichat" href="/chat">
                  <div className="bento__kicker">{"// chat"}</div>
                  <div className="bento__title">digichat</div>
                  <p className="bento__body">Talk to your stack with your keys, your models, your audit log.</p>
                  <span className="bento__cta">Ask digichat <span aria-hidden="true">→</span></span>
                </a>
              </Reveal>
            </div>
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

      <Footer links={DT_FOOTER} meta={DT_FOOTER_META} />
    </>
  );
}
