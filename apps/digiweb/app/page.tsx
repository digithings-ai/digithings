import "./baseline.css";
import Link from "next/link";
import type { ReactNode } from "react";
import { Badge, Button } from "@digithings/ui/ui";
import { ContentsOverview } from "@/components/contents-overview";
import { HomeBanner } from "@/components/home-banner";
import { LiverySwitcher } from "@/components/livery-switcher";

/**
 * The baseline — the rules the live surfaces already follow.
 *
 * Every rule here has a live witness in `digithings-web`, `digiquant-web`, the
 * dashboard or digichat; the specimens below rebuild that grammar from tokens
 * rather than restating a screenshot. `docs/design/CURRENT_UI_LANGUAGE.md` is
 * the long-form reconstruction this page renders.
 */
export default function BaselinePage() {
  return (
    <main className="reference-page baseline-page">
      <header className="hero">
        <p className="kicker">{"// baseline"}</p>
        <h1>
          The rules the live surfaces <em>already follow</em>.
        </h1>
        <p>
          digiweb is the baseline design document, not a gallery of proposals. Every rule below is
          taken from a shipped surface — digithings.ai, digiquant.io, the dashboard, digichat — and
          rendered live from the same tokens. When a surface disagrees, the disagreement is named
          rather than smoothed over.
        </p>

        <div className="dw-banner" aria-label="digithings wordmark banner">
          <HomeBanner />
        </div>

        <p className="dw-links">
          <Link href="/foundations">Tokens and type →</Link>
          <Link href="/components">The kit →</Link>
          <Link href="/rtl">Direction proof →</Link>
        </p>
      </header>

      <section className="section-block">
        <h2 className="title">The four surfaces</h2>
        <p className="section-copy">
          One language, four densities. The tile does not change between them; only its padding,
          gap and ground do.
        </p>
        <dl className="bl-surfaces">
          <div>
            <dt>digithings.ai</dt>
            <dd>Marketing, landing v15. Sections on a hairline, one step between them.</dd>
            <code>apps/digithings-web</code>
          </div>
          <div>
            <dt>digiquant.io</dt>
            <dd>Marketing bands and the desk. Sparse bands, instrument density.</dd>
            <code>apps/digiquant-web</code>
          </div>
          <div>
            <dt>dashboard</dt>
            <dd>Operator glass. Panes are the header; no section head at all.</dd>
            <code>apps/dashboard</code>
          </div>
          <div>
            <dt>digichat</dt>
            <dd>The row is the unit. No box tile; the tool card is a rail.</dd>
            <code>apps/digichat</code>
          </div>
        </dl>
      </section>

      <section className="section-block">
        <h2 className="title">The tile</h2>
        <p className="section-copy">
          <code>background: var(--surface); border: 1px solid var(--hair); border-radius: 0</code>.
          The demo below is the desk mosaic: a 12-column grid with <code>gap-px</code> over a{" "}
          <code>--hair</code> ground, split 7/5 and 4/4/4.
        </p>

        <div className="bl-mosaic">
          <article className="bl-tile bl-span-7">
            <header className="bl-tile-head">
              <span className="bl-eyebrow">desk / research</span>
              <span className="bl-tile-title">Coverage</span>
              <span className="bl-chrome">7 / 12</span>
            </header>
            <div className="bl-tile-body">
              <div className="bl-metric">
                <span className="bl-metric-value">1.42</span>
                <span className="bl-metric-label">sharpe</span>
              </div>
              <div className="bl-metric">
                <span className="bl-metric-value bl-up">+12.4%</span>
                <span className="bl-metric-label">ytd</span>
              </div>
              <div className="bl-metric">
                <span className="bl-metric-value">-8.1%</span>
                <span className="bl-metric-label">max dd</span>
              </div>
            </div>
          </article>

          <article className="bl-tile bl-span-5">
            <header className="bl-tile-head">
              <span className="bl-eyebrow">desk / live</span>
              <span className="bl-tile-title">Positions</span>
            </header>
            <ul className="bl-list">
              <li>
                <span>BTC-PERP</span>
                <span className="bl-num">1.20</span>
                <span className="bl-up">+1.8%</span>
              </li>
              <li>
                <span>ETH-PERP</span>
                <span className="bl-num">15.00</span>
                <span className="bl-down">-0.4%</span>
              </li>
              <li>
                <span>SOL-PERP</span>
                <span className="bl-num">200</span>
                <span className="bl-up">+0.9%</span>
              </li>
            </ul>
          </article>

          {["Orders", "Risk", "Fills"].map((label) => (
            <article className="bl-tile bl-span-4" key={label}>
              <header className="bl-tile-head">
                <span className="bl-eyebrow">desk / book</span>
                <span className="bl-tile-title">{label}</span>
              </header>
              <div className="bl-tile-body">
                <span className="bl-empty">No open rows.</span>
              </div>
            </article>
          ))}
        </div>
        <p className="bl-evidence">
          <code>apps/dashboard/components/desk/panes/brief/BriefDesk.tsx:70</code> ·{" "}
          <code>apps/digiquant-web/components/desk/pages/pane.tsx:19-22</code>
        </p>
      </section>

      <section className="section-block">
        <h2 className="title">Eight rules</h2>

        <Rule
          n="01"
          title="One hairline is the only depth cue."
          evidence="tokens.css has no shadow token; the desk reserves --shadow-overlay for floating chrome only."
        >
          <p className="bl-rule-copy">
            A tile is separated from the page by a 1px line, never by a shadow. Hairlines escalate:
            <code> --hair</code> between cells, <code>--hair-2</code> for rails,{" "}
            <code>--hair-strong</code> for chrome edges.
          </p>
          <div className="bl-demo bl-demo-grid">
            <div className="bl-demo-cell">
              <span className="bl-eyebrow">--hair</span>
              <span>cell border</span>
            </div>
            <div className="bl-demo-cell bl-demo-rail">
              <span className="bl-eyebrow">--hair-2</span>
              <span>rail</span>
            </div>
            <div className="bl-demo-cell bl-demo-strong">
              <span className="bl-eyebrow">--hair-strong</span>
              <span>chrome</span>
            </div>
          </div>
        </Rule>

        <Rule
          n="02"
          title="Zero radius, enforced."
          evidence="tokens.css sets --r-sm / --r-md / --radius-md to 0; the desk force-squares a third-party widget with border-radius: 0 !important."
        >
          <p className="bl-rule-copy">
            Corners are square unless a kit part says otherwise. Radius is not a taste knob here; it
            is removed from the system.
          </p>
          <div className="bl-demo bl-row">
            <Button>Primary</Button>
            <Button variant="outline">Outline</Button>
            <Button variant="ghost">Ghost</Button>
            <Badge>badge</Badge>
            <Badge variant="accent">accent</Badge>
          </div>
        </Rule>

        <Rule
          n="03"
          title="The gap is the rule."
          evidence="BriefDesk.tsx:70 and pane.tsx:22 both use grid gap-px over a bg-hair ground; lists use divide-y divide-hair."
        >
          <p className="bl-rule-copy">
            A hairline grid is one pixel of ground showing through, not a frame plus a gutter. Lists
            repeat the same idea vertically with <code>divide-y</code>.
          </p>
          <div className="bl-mosaic bl-mosaic-flat">
            {["A", "B", "C", "D", "E", "F"].map((cell) => (
              <article className="bl-tile bl-span-4" key={cell}>
                <div className="bl-tile-body">
                  <span className="bl-eyebrow">cell {cell}</span>
                </div>
              </article>
            ))}
          </div>
        </Rule>

        <Rule
          n="04"
          title="Three grounds, no band fills."
          evidence="bg -> surface -> surface-2 is the whole ladder; desk chrome swaps to the term set."
        >
          <p className="bl-rule-copy">
            The page is <code>--bg</code>, a tile is <code>--surface</code>, a nested block is{" "}
            <code>--surface-2</code>. Instrument chrome may swap the whole set to{" "}
            <code>--term-*</code>; marketing bands do not get their own fill.
          </p>
          <div className="bl-grounds">
            {[
              ["--bg", "var(--bg)"],
              ["--surface", "var(--surface)"],
              ["--surface-2", "var(--surface-2)"],
              ["--term-bg", "var(--term-bg)"],
            ].map(([label, tone]) => (
              <div className="bl-ground" key={label} style={{ background: tone }}>
                <span>{label}</span>
              </div>
            ))}
          </div>
        </Rule>

        <Rule
          n="05"
          title="Mono for chrome. Meta is a micro-caps label."
          evidence="tokens.css:197 makes --font-sans the mono stack; DeskPaneChrome.tsx:16 is a 10px mono eyebrow in --ink-mute."
        >
          <p className="bl-rule-copy">
            Labels, commands and numbers are mono. A meta label is upper-case mono at 10–11.5px with
            tracking between .04em and .14em, in <code>--ink-mute</code>.
          </p>
          <div className="bl-demo">
            <header className="bl-tile-head">
              <span className="bl-eyebrow">desk / live</span>
              <span className="bl-tile-title">Book</span>
              <span className="bl-chrome">updated 14:32</span>
            </header>
            <p className="bl-rule-copy bl-mono">mono carries the command line, not the argument.</p>
          </div>
        </Rule>

        <Rule
          n="06"
          title="Numbers are tabular; colour is reserved for money."
          evidence="Every figure uses tabular-nums; --up / --down only on reads with money meaning (PerfMetrics.tsx:6-8)."
        >
          <p className="bl-rule-copy">
            Align digits, not just columns. Green and red mean a signed result, never decoration.
          </p>
          <table className="bl-table">
            <thead>
              <tr>
                <th scope="col">strategy</th>
                <th scope="col">sharpe</th>
                <th scope="col">max dd</th>
                <th scope="col">cagr</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["momentum-v3", "1.42", "-12.4%", "18.1%"],
                ["carry-basis", "0.98", "-8.1%", "11.6%"],
                ["mean-revert", "1.11", "-15.9%", "14.2%"],
              ].map(([name, sharpe, dd, cagr]) => (
                <tr key={name}>
                  <th scope="row">{name}</th>
                  <td>{sharpe}</td>
                  <td className="bl-down">{dd}</td>
                  <td className="bl-up">{cagr}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Rule>

        <Rule
          n="07"
          title="A section is a hairline and a step. The kicker is optional."
          evidence="digithings SectionHead has no kicker; digiquant's Band uses a numbered mono label, never an eyebrow phrase."
        >
          <p className="bl-rule-copy">
            <code>--page-step</code> sets the rhythm, <code>line-b</code> closes the band. Whether a
            band opens with <code>03 / label</code> is a surface decision, not a law.
          </p>
          <div className="bl-bands">
            <div className="bl-band">
              <span className="bl-eyebrow">03 / with a numbered kicker</span>
              <span className="bl-band-title">digiquant band</span>
            </div>
            <div className="bl-band">
              <span className="bl-band-title">digithings section</span>
              <span className="bl-meta">no kicker, the lede does the work</span>
            </div>
          </div>
        </Rule>

        <Rule
          n="08"
          title="Density is a ladder, not a skin."
          evidence="Tile padding runs 1.6rem -> 1.4 -> 1.25 -> 1.1 -> 0.85 -> 0; digichat is the one surface with an explicit compact/default/airy switch."
        >
          <p className="bl-rule-copy">
            The same tile gets tighter as the surface gets more instrumental. The chrome row is the
            floor: <code>px-3 py-2</code> with no body padding.
          </p>
          <ul className="bl-ladder">
            {[
              ["1.6rem", "FeatureCell", "marketing feature"],
              ["1.4rem", "mod-card", "marketing card"],
              ["1.25rem", "ts-panel", "tearsheet"],
              ["1.1rem", "ts-kpi", "metric"],
              ["0.85rem", "dg-cell", "landing cell"],
              ["1px", "desk mosaic", "instrument"],
            ].map(([pad, name, use]) => (
              <li key={name}>
                <code>{pad}</code>
                <span>{name}</span>
                <span className="bl-meta">{use}</span>
              </li>
            ))}
          </ul>
        </Rule>
      </section>

      <section className="section-block">
        <h2 className="title">Known deltas</h2>
        <p className="section-copy">
          A baseline that hides its disagreements is a brochure. These three are live in the code
          today:
        </p>
        <ol className="bl-deltas">
          <li>
            The marketing hero <code>h1</code> is hardcoded at 1.5/1.7rem;{" "}
            <code>--type-page-title</code> exists but no surface consumes it.
          </li>
          <li>
            “Sans” means mono in <code>tokens.css</code>, but digiquant re-declares prose as sans
            and treats mono as opt-in.
          </li>
          <li>
            Legacy marketing cards lift on hover; live desk tiles do not. Lift is not part of the
            tile grammar.
          </li>
        </ol>
      </section>

      <ContentsOverview />
      <LiverySwitcher />
    </main>
  );
}

function Rule({
  n,
  title,
  evidence,
  children,
}: {
  n: string;
  title: string;
  evidence: string;
  children: ReactNode;
}) {
  return (
    <section className="bl-rule">
      <header className="bl-rule-head">
        <span className="bl-num">{n}</span>
        <h3>{title}</h3>
      </header>
      <p className="bl-evidence">{evidence}</p>
      {children}
    </section>
  );
}
