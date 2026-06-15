import type { Metadata } from "next";
import { Nav, Footer, Terminal, Reveal, type TermLine, type NavLink } from "@digithings/web";

export const metadata: Metadata = {
  title: "DigiChat — digithings",
  description: "Talk to your stack. DigiChat streams DigiGraph — BYOK, self-hosted, audited.",
};

const NAV: NavLink[] = [
  { label: "Architecture", href: "/architecture" },
  { label: "Modules", href: "/#modules" },
  { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
  { label: "Try Chat", href: "/chat", cta: true },
];
const Brand = () => (<><img src="/favicon-qr.svg" alt="" className="brand-mark" width={26} height={26} aria-hidden="true" /><span className="brand-word">digithings</span></>);

const SESSION: TermLine[] = [
  { kind: "cmd", text: "Build me a mean-reversion stat-arb on tech" },
  { kind: "out", text: "→ routing to DigiQuant + DigiSearch" },
  { kind: "out", text: "Atlas: researching candidates (NASDAQ tech, 90d)" },
  { kind: "out", text: "→ scaffold: pairs-mean-reversion · sector=tech" },
  { kind: "arrow", text: "→ backtest queued · tear sheet on completion" },
  { kind: "gap" },
  { kind: "cmd", text: "Show me the Sharpe by year" },
  { kind: "out", text: "→ 2021: 1.12   2022: 0.87   2023: 1.44   2024: 1.31" },
];

const FEATURES = [
  ["byok", "Your keys, your models", "Paste any Anthropic / OpenAI / LiteLLM key — forwarded per-request, never stored."],
  ["streams digigraph", "Full orchestration surface", "Every message routes through the LangGraph supervisor; tools and sub-graphs on every turn."],
  ["audit on", "Immutable logs, zero raw PII", "DigiSmith correlation IDs on every span; PII redacted before logs hit disk."],
  ["self-hosted", "One compose file", "Runs on your laptop, a VM, or Kubernetes — the same Docker profile."],
];

export default function ChatPage() {
  return (
    <>
      <Nav brand={<Brand />} links={NAV} />
      <main>
        <section className="hero">
          <div className="wrap" style={{ textAlign: "center" }}>
            <Reveal as="p" className="eyebrow"><span className="prompt">$</span> digichat · streams digigraph</Reveal>
            <Reveal as="h1" className="hero-title" delay={0.05} >Talk to your <em>stack.</em></Reveal>
            <Reveal as="p" className="hero-lede" delay={0.1}>Ask questions, run research, explore your data — with your keys, your models, and full audit on every response.</Reveal>
            <Reveal className="hero-actions" delay={0.15}>
              <a className="btn btn-primary" href="https://github.com/digithings-ai/digithings" target="_blank" rel="noopener noreferrer">Self-host on GitHub <span aria-hidden="true">→</span></a>
              <a className="btn btn-ghost" href="/">Back to the stack</a>
            </Reveal>
          </div>
        </section>

        <section className="section">
          <div className="wrap">
            <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))" }}>
              {FEATURES.map(([tag, h, p]) => (
                <Reveal key={h} className="card">
                  <div className="card-top"><span className="tier core">{tag}</span></div>
                  <h3>{h}</h3><p className="card-body">{p}</p>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <Reveal className="section-head center"><span className="kicker">// example session</span><h2>What a turn looks like.</h2><p>Illustrative only — numbers are not real data.</p></Reveal>
            <div style={{ maxWidth: 760, margin: "0 auto" }}>
              <Terminal title="chat.digithings.ai" lines={SESSION} />
            </div>
          </div>
        </section>
      </main>
      <Footer links={[{ label: "Architecture", href: "/architecture" }, { label: "GitHub", href: "https://github.com/digithings-ai", external: true }]} meta="© 2026 DigiThings · open core" />
    </>
  );
}
