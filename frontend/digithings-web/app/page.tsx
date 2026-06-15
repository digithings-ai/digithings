import { Nav, Footer, ModuleCard, ScrollyGraph, Terminal, Reveal, modules, type TermLine, type NavLink } from "@digithings/web";

const NAV_LINKS: NavLink[] = [
  { label: "Architecture", href: "/architecture" },
  { label: "Modules", href: "#modules" },
  { label: "Principles", href: "#principles" },
  { label: "digiquant.io", href: "https://digiquant.io", external: true },
  { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
  { label: "Try Chat", href: "/chat", cta: true },
];

const FOOTER_LINKS: NavLink[] = [
  { label: "Architecture", href: "/architecture" },
  { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
  { label: "digiquant.io", href: "https://digiquant.io", external: true },
  { label: "DigiChat", href: "/chat" },
];

const BOOT: TermLine[] = [
  { kind: "cmd", text: "digithings --about" },
  { kind: "out", text: "open-core agentic stack · self-hosted" },
  { kind: "gap" },
  { kind: "cmd", text: "docker compose up -d" },
  { kind: "ok", name: "digigraph", text: "orchestration   :8000" },
  { kind: "ok", name: "digiquant", text: "quant engine    :8001" },
  { kind: "ok", name: "digisearch", text: "retrieval       :8002" },
  { kind: "ok", name: "digichat", text: "chat surface    :3005" },
  { kind: "arrow", text: "→ stack online · audit on · byok" },
];

const Brand = () => (
  <>
    <img src="/favicon-qr.svg" alt="" className="brand-mark" width={26} height={26} aria-hidden="true" />
    <span className="brand-word">digithings</span>
  </>
);

export default function Home() {
  return (
    <>
      <Nav brand={<Brand />} links={NAV_LINKS} />

      <main>
        <section className="hero">
          <div className="wrap hero-grid">
            <div className="hero-copy">
              <Reveal as="p" className="eyebrow"><span className="prompt">$</span> open core · ten modules online</Reveal>
              <Reveal as="h1" className="hero-title" delay={0.05}>
                Build agents on infrastructure <em>you own.</em>
              </Reveal>
              <Reveal as="p" className="hero-lede" delay={0.1}>
                A modular, open-core agentic stack — composable services wired into one platform.
                Self-hosted, BYOK, audit-on by default. No vendor lock-in, no opaque pipelines.
              </Reveal>
              <Reveal className="hero-actions" delay={0.15}>
                <a className="btn btn-primary" href="/architecture">Explore the platform <span aria-hidden="true">→</span></a>
                <a className="btn btn-ghost" href="https://github.com/digithings-ai" target="_blank" rel="noopener noreferrer">View on GitHub</a>
              </Reveal>
            </div>
            <Reveal className="hero-term" delay={0.1}>
              <Terminal title="~/digithings — zsh" lines={BOOT} />
            </Reveal>
          </div>
        </section>

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

        <section className="section section-alt" id="modules">
          <div className="wrap">
            <Reveal className="section-head center">
              <span className="kicker">// the full stack</span>
              <h2>Real services. Real stack.</h2>
              <p>Eight services plus a shared library — each runnable with one Docker command. Two more on the roadmap.</p>
            </Reveal>
            <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))" }}>
              {modules.map((m) => (
                <Reveal key={m.id}><ModuleCard m={m} /></Reveal>
              ))}
            </div>
          </div>
        </section>

        <section className="section" id="principles">
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

      <Footer links={FOOTER_LINKS} meta="© 2026 DigiThings · open core" />
    </>
  );
}
