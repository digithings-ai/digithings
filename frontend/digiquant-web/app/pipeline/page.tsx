import type { Metadata } from "next";
import { Footer, Reveal } from "@digithings/web";
import { DQ_FOOTER, DQ_FOOTER_META } from "../_nav";
import { DqNav } from "@/components/landing/DqNav";
import { AmbientMesh } from "@/components/landing/AmbientMesh";

export const metadata: Metadata = {
  title: "Pipeline — digiquant",
  description:
    "A linear, research-first quant workflow: chat with an LLM, build indicators, assemble a strategy, generate signals, optimize, backtest on NautilusTrader, then promote to execution — human-gated, audited, reproducible.",
};

// The seven-stage research → execution flow. Unlike the digithings module graph
// (a hub-and-spoke topology), this is deliberately linear — each stage hands its
// output to the next, ending in a gated execution layer.
const FLOW: { n: string; title: string; body: string; tool: string }[] = [
  { n: "01", title: "Research", body: "Ask in plain language. An LLM research loop pulls free macro and market data and proposes directions to test.", tool: "chat · LLM" },
  { n: "02", title: "Indicators", body: "Compose validated indicators — moving averages, RSI, ADF, DPSD — from the shared, unit-tested library.", tool: "indicators lib" },
  { n: "03", title: "Strategy", body: "Wire indicators into a rules-based strategy with explicit entries, exits, sizing, and risk.", tool: "strategy spec" },
  { n: "04", title: "Signals", body: "Generate entry and exit signals across historical bars — deterministic and reproducible.", tool: "signal gen" },
  { n: "05", title: "Optimize", body: "Search the parameter space with Optuna; walk-forward windows guard against overfitting.", tool: "Optuna" },
  { n: "06", title: "Backtest", body: "Replay on a NautilusTrader core — Pine-faithful fills, full trade ledger, and a tearsheet.", tool: "NautilusTrader" },
  { n: "07", title: "Execution", body: "Promote up the ladder: backtest → paper → loopback → live. Every rung is a human gate.", tool: "Kairos · gated" },
];

export default function PipelinePage() {
  return (
    <>
      <DqNav />
      <main className="dq-subpage">
        <AmbientMesh />
        <section className="section">
          <div className="wrap">
            <Reveal className="dq-sechead">
              <div className="dq-eyebrow">{"// the pipeline"}</div>
              <h2 className="dq-title">Research in, orders out — in a straight line.</h2>
              <p className="dq-sub">digiquant is not a hub of services routing messages around; it&rsquo;s a linear research workflow. You start in a chat, and each stage hands its output to the next until a strategy is ready to run. Built on the open <a href="https://digiquant.io" style={{ color: "var(--accent)" }}>digiquant</a> stack — itself a module of <a href="https://digithings.ai" target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent)" }}>the digithings platform</a>.</p>
            </Reveal>

            <Reveal>
              <ol className="dq-flow" aria-label="digiquant research-to-execution pipeline">
                {FLOW.map((s, i) => (
                  <li key={s.n} className={`dq-flow-step${i === FLOW.length - 1 ? " is-exec" : ""}`}>
                    <span className="dq-flow-n">{s.n}</span>
                    <h3>{s.title}</h3>
                    <p>{s.body}</p>
                    <span className="dq-flow-tool">{s.tool}</span>
                    {i < FLOW.length - 1 && <span className="dq-flow-arrow" aria-hidden="true">→</span>}
                  </li>
                ))}
              </ol>
            </Reveal>
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <Reveal className="dq-sechead center">
              <div className="dq-eyebrow">{"// execution, gated"}</div>
              <h2 className="dq-title">The execution layer climbs a ladder.</h2>
              <p className="dq-sub">Stage 07 in detail: a strategy earns its way to live. Backtest → paper → loopback → live, each rung a human gate. Loopback-only by default.</p>
            </Reveal>
            <Reveal className="ladder">
              <svg viewBox="0 0 520 280" preserveAspectRatio="xMidYMid meet">
                <g stroke="var(--hair)" strokeWidth="1"><line x1="0" y1="250" x2="520" y2="250" /></g>
                <g fill="none" strokeWidth="1.6">
                  <rect x="20" y="200" width="100" height="50" className="rung" />
                  <rect x="140" y="150" width="100" height="100" className="rung" />
                  <rect x="260" y="100" width="100" height="150" className="rung active" />
                  <rect x="380" y="50" width="100" height="200" className="rung future" strokeDasharray="4 6" />
                </g>
                <g fontFamily="var(--font-mono)" fontSize="11" fill="var(--ink-mute)" textAnchor="middle">
                  <text x="70" y="270">BACKTEST</text><text x="190" y="270">PAPER</text><text x="310" y="270">LOOPBACK</text><text x="430" y="270">LIVE · GATED</text>
                </g>
                <g transform="translate(421 24)" fill="none" stroke="var(--accent)" strokeWidth="1.4"><rect x="0" y="7" width="18" height="13" rx="1.5" /><path d="M4 7 v-2 a5 5 0 0 1 10 0 v2" /></g>
              </svg>
              <p className="ladder-cap">{"// loopback-only by default · human-gated transitions"}</p>
            </Reveal>
          </div>
        </section>
      </main>
      <Footer links={DQ_FOOTER} meta={DQ_FOOTER_META} />
    </>
  );
}
