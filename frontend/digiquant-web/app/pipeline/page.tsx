import type { Metadata } from "next";
import { Nav, Footer, Reveal, type NavLink } from "@digithings/web";

export const metadata: Metadata = {
  title: "Pipeline — DigiQuant",
  description: "Atlas researches, Hermes deliberates, Kairos executes on NautilusTrader. Human-gated, audited, reproducible.",
};
const NAV: NavLink[] = [
  { label: "Pipeline", href: "/pipeline" }, { label: "Atlas", href: "/subsystems/atlas" }, { label: "Pricing", href: "/#pricing" },
  { label: "digithings.ai", href: "https://digithings.ai", external: true }, { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
  { label: "Open Olympus", href: "/olympus/", cta: true },
];
const Brand = () => (<><span className="dq-glyph" aria-hidden="true" /><span className="brand-word">digiquant</span></>);

const NODES: [string, number, number, number, boolean, string | null][] = [
  ["Atlas", 180, 130, 30, true, "atlas"], ["Hermes", 460, 130, 30, true, "hermes"], ["Kairos", 740, 130, 30, true, "kairos"],
  ["Nautilus", 740, 300, 22, false, null], ["DigiStore", 180, 300, 22, false, null],
];
const EDGES: [number, number, number, number][] = [
  [180, 130, 460, 130], [460, 130, 740, 130], [740, 130, 740, 300], [180, 130, 180, 300], [740, 130, 180, 300],
];

export default function PipelinePage() {
  return (
    <>
      <Nav brand={<Brand />} links={NAV} />
      <main>
        <section className="section">
          <div className="wrap">
            <Reveal className="section-head"><span className="kicker">// the pipeline</span><h2 className="hero-title" style={{ fontSize: "clamp(2.2rem,5vw,3.4rem)", margin: ".4rem 0 .8rem" }}>Research → signals → execution.</h2><p>Three specialists, one deterministic flow — Atlas persists research, Hermes turns it into attributed signals, Kairos executes on a NautilusTrader core. Click a node for the subsystem reference.</p></Reveal>
            <Reveal>
              <figure className="graph" style={{ maxWidth: 920, margin: "0 auto" }}>
                <svg viewBox="0 0 920 400" role="img" aria-label="DigiQuant pipeline" preserveAspectRatio="xMidYMid meet" style={{ width: "100%", height: "auto" }}>
                  <g>{EDGES.map(([x1, y1, x2, y2], i) => <line key={i} className="dg-edge" x1={x1} y1={y1} x2={x2} y2={y2} />)}</g>
                  <g>
                    {NODES.map(([label, x, y, r, hub, id]) => {
                      const node = (
                        <g className={`dg-node${hub ? " hub" : ""}`} transform={`translate(${x} ${y})`}>
                          <circle className="halo" r={r + 12} /><circle className="node" r={r} /><text className="label" y={r + 18}>{label}</text>
                        </g>
                      );
                      return id ? <a key={label} href={`/subsystems/${id}`}>{node}</a> : <g key={label}>{node}</g>;
                    })}
                  </g>
                </svg>
              </figure>
            </Reveal>
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <Reveal className="section-head center"><span className="kicker">// execution, gated</span><h2>Strategies climb a ladder.</h2><p>Backtest → paper → loopback → live. Each rung is a human gate; loopback-only by default.</p></Reveal>
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
              <p className="ladder-cap">// loopback-only by default · human-gated transitions</p>
            </Reveal>
          </div>
        </section>
      </main>
      <Footer links={[{ label: "Home", href: "/" }, { label: "Olympus", href: "/olympus/" }, { label: "GitHub", href: "https://github.com/digithings-ai", external: true }]} meta="© 2026 digithings AI · open core" />
    </>
  );
}
