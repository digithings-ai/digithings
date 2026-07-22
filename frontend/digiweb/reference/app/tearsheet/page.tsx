import "./tearsheet.css";
import { TearsheetCardReference } from "@/components/tearsheet-card-reference";
import { TearsheetChartsReference } from "@/components/tearsheet-charts-reference";
import { TearsheetTradeLogReference } from "@/components/tearsheet-trade-log-reference";

const FAMILY_RULES = [
  "Print-first pure SVG is the hard constraint: Download PDF flushSync-re-renders the SAME chart instances at full span and calls window.print() — screen and print share one render tree, so canvas engines are disqualified here. Dashboards without a print path use the canvas finance-charts / finance-composites families instead (frontend/digiweb/CHARTS.md).",
  "Every series pane shares one normalized ViewWindow (fractions over the backtest span): wheel-zoom, drag-pan and double-click reset stay synced across charts, and lookback presets match back when a zoom lands on one.",
  "Scales are linear / log / symlog — symlog carries series that cross zero (cumulative P&L).",
  "Money colors: positive wears --up, negative --down, and they NEVER follow a livery. The module accent is identity/chrome (equity line, markers' buy side, live badge).",
  "The print grammar is part of the family sheet: panes open ([hidden] included), scroll clamps release, rows and cards avoid page breaks, and the light tokens are pinned for paper. Import the sheet PLAINLY — it manages its own layering.",
  "Data derivation (series clipping, stat pivots, trade sorting) stays app-owned — every component takes render-ready props.",
];

export default function TearsheetPage() {
  return (
    <main className="reference-page accent-digiquant">
      <header className="hero">
        <p className="kicker">{"// tearsheet"}</p>
        <h1>
          Backtests, <em>print-grade.</em>
        </h1>
        <p>
          The finance-tearsheet family: the strategy tearsheet grammar reverse-promoted from
          digiquant.io — dependency-free SVG charts with synced zoom and trade markers, the KPI
          strip, signed contribution with exact portfolio return, the returns matrix, the trade
          log, and the library card. Everything on this page survives <code>window.print()</code>:
          hit Download PDF below and the same components re-render at full span into a
          paper-white export.
        </p>
      </header>

      <section className="section-block" id="tearsheet-core">
        <p className="kicker">{"// synced charts + KPI strip"}</p>
        <h2 className="title">One window, every pane.</h2>
        <p className="section-copy">
          The tearsheet core: headline KPIs over the tabbed chart deck. Candles carry
          TradingView-style entry/exit markers with hover cards (long entries buy-arrow from
          below, shorts sell-arrow from above, exits flip); the contribution composite keeps
          additive weighted drivers beside the exact portfolio-return line; equity toggles
          linear-% / log-$; drawdown hangs under a zero baseline in <code>--down</code>;
          per-trade P&amp;L distinguishes realized bars from the accent-ringed unrealized open
          leg. Zoom any pane — the others follow.
        </p>
        <div className="mt-[1.2rem]">
          <TearsheetChartsReference />
        </div>
      </section>

      <section className="section-block" id="tearsheet-trade-log">
        <p className="kicker">{"// trade log"}</p>
        <h2 className="title">Every round trip, on the record.</h2>
        <p className="section-copy">
          ReactNode cells over the shared table grammar: direction pills, toned returns, and the
          open position sorted first wearing the accent wash with its unrealized tag. Sticky mono
          head inside a scroll clamp on screen; opened flat with break-safe rows in print.
        </p>
        <div className="mt-[1.2rem]">
          <TearsheetTradeLogReference />
        </div>
      </section>

      <section className="section-block" id="tearsheet-cards">
        <p className="kicker">{"// library cards"}</p>
        <h2 className="title">Strategies, filed as cards.</h2>
        <p className="section-copy">
          The library index card — a whole-card anchor with hover-lift and accent border over the
          gradient surface, the pulsing LiveBadge on nightly-refreshed entries, and a KPI grid in
          the money tones. The anchor/render composition the controls Card could not express.
        </p>
        <div className="mt-[1.2rem]">
          <TearsheetCardReference />
        </div>
      </section>

      <section className="section-block" id="tearsheet-rules">
        <p className="kicker">{"// family rules"}</p>
        <h2 className="title">Why this family is SVG.</h2>
        <p className="section-copy">
          The house rules for every tearsheet surface — the engine split, the sync contract, and
          the print grammar that makes the PDF export a feature instead of an afterthought.
        </p>
        <ol className="chart-rules">
          {FAMILY_RULES.map((rule) => (
            <li key={rule}>{rule}</li>
          ))}
        </ol>
      </section>
    </main>
  );
}
