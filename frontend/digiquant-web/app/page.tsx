import { Nav, Footer, Emblem, StackRow, Reveal, subsystems, type NavLink } from "@digithings/web";

const NAV: NavLink[] = [
  { label: "Pipeline", href: "/pipeline" },
  { label: "Strategies", href: "/strategies" },
  { label: "Atlas", href: "/subsystems/atlas" },
  { label: "Pricing", href: "#pricing" },
  { label: "digithings.ai", href: "https://digithings.ai", external: true },
  { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
  { label: "Open Olympus", href: "/olympus/", cta: true },
];
const FOOTER: NavLink[] = [
  { label: "Pipeline", href: "/pipeline" },
  { label: "Olympus", href: "/olympus/" },
  { label: "digithings.ai", href: "https://digithings.ai", external: true },
  { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
];
const Brand = () => (<><span className="dq-glyph" aria-hidden="true" /><span className="brand-word">digiquant</span></>);

const TICKER = [
  ["ATLAS", "184.22", "+0.42%"], ["HERMES", "96.10", "-0.18%"], ["KAIROS", "212.74", "+1.04%"],
  ["BTC-USD", "68,940", "+2.11%"], ["ETH-USD", "3,612", "-0.63%"], ["SOL-USD", "184.9", "+3.27%"], ["DGQ-COMP", "1.184", "+0.84%"],
];

export default function Home() {
  const ticker = [...TICKER, ...TICKER];
  return (
    <>
      <Nav brand={<Brand />} links={NAV} />
      <main>
        <section className="hero">
          <div className="wrap hero-grid">
            <div className="hero-copy">
              <Reveal as="p" className="eyebrow"><span className="prompt">$</span> open core · nautilustrader · human-gated live</Reveal>
              <Reveal as="h1" className="hero-title" delay={0.05}>Backtest, optimize, and deploy — <em>on infrastructure you own.</em></Reveal>
              <Reveal as="p" className="hero-lede" delay={0.1}>A quant-native pipeline that ends in an order, not a markdown file. Atlas researches, Hermes deliberates, Kairos executes — every run deterministic, reproducible, and audited.</Reveal>
              <Reveal className="hero-actions" delay={0.15}>
                <a className="btn btn-primary" href="/olympus/">Open Olympus <span aria-hidden="true">→</span></a>
                <a className="btn btn-ghost" href="https://github.com/digithings-ai" target="_blank" rel="noopener noreferrer">View on GitHub</a>
              </Reveal>
            </div>
            <Reveal className="hero-visual" delay={0.1}>
              <div className="panel">
                <div className="panel-head"><span>equity · example run</span><span className="dq-up">▲ +18.4%</span></div>
                <svg className="dq-curve" viewBox="0 0 480 150" preserveAspectRatio="none" aria-hidden="true">
                  <defs><linearGradient id="eq" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--accent)" stopOpacity="0.28" /><stop offset="100%" stopColor="var(--accent)" stopOpacity="0" /></linearGradient></defs>
                  <path d="M0,120 L40,116 L80,108 L120,112 L160,98 L200,90 L240,80 L280,84 L320,66 L360,58 L400,48 L440,38 L480,30 L480,150 L0,150 Z" fill="url(#eq)" />
                  <path className="dq-curve-line" d="M0,120 L40,116 L80,108 L120,112 L160,98 L200,90 L240,80 L280,84 L320,66 L360,58 L400,48 L440,38 L480,30" fill="none" stroke="var(--accent)" strokeWidth="1.6" />
                </svg>
                <div className="panel-metrics">
                  <div><span className="ml">Sharpe</span><span className="mv dq-up">1.42</span></div>
                  <div><span className="ml">Max DD</span><span className="mv dq-down">8.6%</span></div>
                  <div><span className="ml">Exposure</span><span className="mv">74%</span></div>
                </div>
              </div>
            </Reveal>
          </div>
        </section>

        <div className="dq-tickerbar"><div className="dq-ticker"><div className="dq-ticker-track">
          {ticker.map(([s, p, d], i) => (
            <span className="dq-ti" key={i}><span className="s">{s}</span><span className="p">{p}</span><span className={d.startsWith("-") ? "dq-down" : "dq-up"}>{d}</span></span>
          ))}
        </div></div></div>

        <section className="section" id="pipeline">
          <div className="wrap">
            <Reveal className="section-head center"><span className="kicker">// the pipeline</span><h2>One pipeline. Three specialists.</h2><p>Atlas researches. Hermes deliberates. Kairos executes. Every run lands in NautilusTrader — yours to inspect and replay.</p></Reveal>
            <div className="grid dq-stages">
              {subsystems.map((s) => (
                <Reveal key={s.id}>
                  <a className="mod-card t-core" href={`/subsystems/${s.id}`}>
                    <div className="mod-card-top"><Emblem id={s.emblem} size={26} /><span className="dg-tier t-core">{s.step}</span></div>
                    <h3>{s.name}</h3><p className="role">{s.tagline}</p>
                    <StackRow items={s.stack.slice(0, 4)} className="stack-row compact" />
                  </a>
                </Reveal>
              ))}
            </div>
            <Reveal><p style={{ textAlign: "center", marginTop: "1.8rem" }}><a className="btn btn-ghost" href="/pipeline">Open the pipeline <span aria-hidden="true">→</span></a></p></Reveal>
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <Reveal className="section-head"><span className="kicker">// illustrative output</span><h2>What a run reports.</h2><p>Example tear-sheet figures — your numbers come from your data, your strategies, your run.</p></Reveal>
            <div className="grid dq-metrics">
              <Reveal className="dq-metric"><span className="ml">Sharpe</span><span className="mv dq-up">1.42</span></Reveal>
              <Reveal className="dq-metric"><span className="ml">Max drawdown</span><span className="mv dq-down">8.6%</span></Reveal>
              <Reveal className="dq-metric"><span className="ml">Gross exposure</span><span className="mv">74%</span></Reveal>
              <Reveal className="dq-metric"><span className="ml">Backtest speed</span><span className="mv">12<span className="mu">ms/candle</span></span></Reveal>
            </div>
          </div>
        </section>

        <section className="section" id="pricing">
          <div className="wrap">
            <Reveal className="section-head"><span className="kicker">// pricing</span><h2>Open core. Managed tier for Atlas.</h2><p>Self-host the full stack at no cost. The managed Atlas tier adds SLAs, onboarding, and operational support.</p></Reveal>
            <div className="grid dq-pricing">
              <Reveal className="price-card">
                <h3>Open core</h3><p className="price">self-host · <span className="dq-up">free</span></p>
                <ul><li>Full stack, MIT / Apache-licensed</li><li>NautilusTrader execution engine</li><li>Atlas, Hermes, Kairos pipelines</li><li>Community support on GitHub</li></ul>
                <a className="btn btn-ghost" href="https://github.com/digithings-ai" target="_blank" rel="noopener noreferrer">View on GitHub <span aria-hidden="true">→</span></a>
              </Reveal>
              <Reveal className="price-card accent">
                <span className="price-flag">managed</span><h3>Managed Atlas</h3><p className="price">contact</p>
                <ul><li>Managed Atlas runner with SLA</li><li>Custom strategy onboarding</li><li>Priority fixes + roadmap input</li><li>Optional on-prem deployment</li></ul>
                <a className="btn btn-primary" href="mailto:hello@digithings.ai">Get in touch <span aria-hidden="true">→</span></a>
              </Reveal>
            </div>
          </div>
        </section>
      </main>
      <Footer links={FOOTER} meta="© 2026 digithings AI · open core" />
    </>
  );
}
