import { Nav, Footer, Emblem, StackRow, Reveal, subsystems } from "@digithings/web";
import { Brand, DQ_NAV, DQ_FOOTER, DQ_FOOTER_META } from "./_nav";
import { StrategyCard } from "@/components/tearsheet/strategy-card";
import { type StrategyIndexEntry } from "@/components/tearsheet/types";
import index from "@/public/strategies/index.json";

const strategies = index as StrategyIndexEntry[];

const TICKER = [
  ["ATLAS", "184.22", "+0.42%"], ["HERMES", "96.10", "-0.18%"], ["KAIROS", "212.74", "+1.04%"],
  ["BTC-USD", "68,940", "+2.11%"], ["ETH-USD", "3,612", "-0.63%"], ["SOL-USD", "184.9", "+3.27%"], ["DGQ-COMP", "1.184", "+0.84%"],
];

const PIPE_STEPS = ["Research", "Indicators", "Strategy", "Signals", "Optimize", "Backtest", "Execution"];

export default function Home() {
  const ticker = [...TICKER, ...TICKER];
  return (
    <>
      <Nav brand={<Brand />} links={DQ_NAV} />
      <main>
        <section className="hero">
          <div className="wrap hero-grid">
            <div className="hero-copy">
              <Reveal as="p" className="eyebrow"><span className="prompt">$</span> open core · nautilustrader · human-gated live</Reveal>
              <Reveal as="h1" className="hero-title" delay={0.05}>Backtest, optimize, and deploy — <em>on infrastructure you own.</em></Reveal>
              <Reveal as="p" className="hero-lede" delay={0.1}>A research-first quant pipeline that ends in an order, not a markdown file. Chat to research, compose indicators, optimize and backtest on a NautilusTrader core, then promote to execution — every run deterministic, reproducible, and audited.</Reveal>
              <Reveal className="hero-actions" delay={0.15}>
                <a className="btn btn-primary" href="/pipeline">Walk the pipeline <span aria-hidden="true">→</span></a>
                <a className="btn btn-ghost" href="/strategies">See the strategies</a>
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
            <Reveal className="section-head center"><span className="kicker">// the pipeline</span><h2>Research → signals → execution, in a straight line.</h2><p>No hub-and-spoke. You start in a chat and each stage hands its output to the next, ending in a human-gated execution layer.</p></Reveal>
            <Reveal>
              <div className="dq-mini-flow" aria-hidden="true">
                {PIPE_STEPS.map((s, i) => (
                  <span className="dq-mini-step" key={s}>{s}{i < PIPE_STEPS.length - 1 && <i className="dq-mini-arrow">→</i>}</span>
                ))}
              </div>
            </Reveal>
            <Reveal><p style={{ textAlign: "center", marginTop: "0.6rem" }}><a className="btn btn-ghost" href="/pipeline">Walk the full pipeline <span aria-hidden="true">→</span></a></p></Reveal>
          </div>
        </section>

        <section className="section section-alt" id="strategies">
          <div className="wrap">
            <Reveal className="section-head center"><span className="kicker">// strategy library</span><h2>Three base strategies, validated.</h2><p>Reference crypto strategies — one per major asset — you can fork, re-optimize, and extend. Each ships with a full Pine-faithful validation tearsheet.</p></Reveal>
            <div className="ts-lib-grid">
              {strategies.map((e) => (
                <Reveal key={e.strategy}><StrategyCard e={e} /></Reveal>
              ))}
            </div>
            <Reveal><p style={{ textAlign: "center", marginTop: "1.8rem" }}><a className="btn btn-ghost" href="/strategies">Open the library <span aria-hidden="true">→</span></a></p></Reveal>
          </div>
        </section>

        <section className="section" id="olympus">
          <div className="wrap">
            <Reveal className="section-head"><span className="kicker">// side project · autonomous</span><h2>Olympus — a hedge fund in a box.</h2><p>A separate, autonomous research desk built on the same stack. Where the pipeline above is hands-on, Olympus runs the whole loop itself: Atlas researches the market, Hermes deliberates and attributes signals, Kairos executes — full AI portfolio management, end to end.</p></Reveal>
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
            <Reveal><p style={{ textAlign: "center", marginTop: "1.8rem" }}><a className="btn btn-primary" href="/olympus/">Open Olympus <span aria-hidden="true">→</span></a></p></Reveal>
          </div>
        </section>

        <section className="section section-alt" id="pricing">
          <div className="wrap">
            <Reveal className="section-head"><span className="kicker">// pricing</span><h2>Open core. Managed tier for Atlas.</h2><p>Self-host the full stack at no cost. The managed Atlas tier adds SLAs, onboarding, and operational support.</p></Reveal>
            <div className="grid dq-pricing">
              <Reveal className="price-card">
                <h3>Open core</h3><p className="price">self-host · <span className="dq-up">free</span></p>
                <ul><li>Full stack, MIT / Apache-licensed</li><li>NautilusTrader execution engine</li><li>Research → backtest → execution pipeline</li><li>Community support on GitHub</li></ul>
                <a className="btn btn-ghost" href="https://github.com/digithings-ai" target="_blank" rel="noopener noreferrer">View on GitHub <span aria-hidden="true">→</span></a>
              </Reveal>
              <Reveal className="price-card accent">
                <span className="price-flag">managed</span><h3>Managed Atlas</h3><p className="price">contact</p>
                <ul><li>Managed Atlas runner with SLA</li><li>Custom strategy onboarding</li><li>Priority fixes + roadmap input</li><li>Optional on-prem deployment</li></ul>
                <a className="btn btn-primary" href="mailto:hello@digithings.ai">Get in touch <span aria-hidden="true">→</span></a>
              </Reveal>
            </div>
            <Reveal><p className="dq-built" style={{ textAlign: "center", marginTop: "2.2rem" }}>DigiQuant is the quant module of <a href="https://digithings.ai" target="_blank" rel="noopener noreferrer">the DigiThings platform</a> — the same open-core, self-hosted, audit-on stack.</p></Reveal>
          </div>
        </section>
      </main>
      <Footer links={DQ_FOOTER} meta={DQ_FOOTER_META} />
    </>
  );
}
