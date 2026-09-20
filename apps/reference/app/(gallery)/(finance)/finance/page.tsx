import "./finance.css";
import { DrawdownPlotReference } from "@/components/drawdown-plot-reference";
import { EquityCurveReference } from "@/components/equity-curve-reference";
import { MonthlyReturnsReference } from "@/components/monthly-returns-reference";
import { OrderbookReference } from "@/components/orderbook-reference";
import { PageToc } from "@/components/page-toc";
import { PerfMetricsReference } from "@/components/perf-metrics-reference";
import { PerformanceDashboardReference } from "@/components/performance-dashboard-reference";
import { PortfolioReference } from "@/components/portfolio-reference";
import { PortfolioWorkspaceReference } from "@/components/portfolio-workspace-reference";
import { PriceChartReference } from "@/components/price-chart-reference";
import { StockTickerReference } from "@/components/stock-ticker-reference";
import { SyncedTearsheetReference } from "@/components/synced-tearsheet-reference";
import { TearsheetCardReference } from "@/components/tearsheet-card-reference";
import { TearsheetChartsReference } from "@/components/tearsheet-charts-reference";
import { TearsheetDcaReference } from "@/components/tearsheet-dca-reference";
import { TearsheetTradeLogReference } from "@/components/tearsheet-trade-log-reference";

const TOC_ITEMS = [
  { id: "ticker-tape", label: "Ticker" },
  { id: "price-chart", label: "Price chart" },
  { id: "equity-curve", label: "Equity curve" },
  { id: "drawdown", label: "Drawdown" },
  { id: "synced-tearsheet", label: "Synced tearsheet" },
  { id: "performance", label: "Performance" },
  { id: "portfolio-workspace", label: "Portfolio workspace" },
  { id: "portfolio", label: "Positions blotter" },
  { id: "charting-rules", label: "Charting rules" },
  { id: "perf-metrics", label: "Perf metrics" },
  { id: "returns-matrix", label: "Returns matrix" },
  { id: "order-book", label: "Order book" },
  { id: "print-tearsheet", label: "Print tearsheet" },
];

const CHART_RULES = [
  "Lightweight Charts (TradingView's open-source engine) is the price/series primitive for DASHBOARD surfaces. Print-grade surfaces (PDF-exporting tearsheets) compose the SVG finance-tearsheet family instead — canvas rasterizes in print. The split ruling: packages/ui/CHARTS.md.",
  "We feed it our own backtest data. No external feed, no market connection; attributionLogo is off, so there's no TradingView branding.",
  "The canvas background is always transparent and every color is read from a design token (--up/--down, --hair, --accent, --font-mono) — never hard-coded.",
  "A MutationObserver on data-theme re-applies the palette, so charts re-theme live on light/dark and livery changes.",
  "autoSize is on — the chart fills its pane's width and height; give the pane a definite height for it to fill.",
  "Money colors (--up/--down) are for P&L only. The module accent is identity/chrome, never a single gain or loss read.",
  "Multi-series views use panes with one shared time axis (or distinguishable hues as identifiers) — never money hues to tell series apart.",
];

const FAMILY_RULES = [
  "Print-first pure SVG is the hard constraint: Download PDF flushSync-re-renders the SAME chart instances at full span and calls window.print() — screen and print share one render tree, so canvas engines are disqualified here. Dashboards without a print path use the canvas finance-charts / finance-composites families instead (packages/ui/CHARTS.md).",
  "Every series pane shares one normalized ViewWindow (fractions over the backtest span): wheel-zoom, drag-pan and double-click reset stay synced across charts, and lookback presets match back when a zoom lands on one.",
  "Scales are linear / log / symlog — symlog carries series that cross zero (cumulative P&L).",
  "Money colors: positive wears --up, negative --down, and they NEVER follow a livery. The module accent is identity/chrome (equity line, markers' buy side, live badge).",
  "The print grammar is part of the family sheet: panes open ([hidden] included), scroll clamps release, rows and cards avoid page breaks, and the light tokens are pinned for paper. Import the sheet PLAINLY — it manages its own layering.",
  "Data derivation (series clipping, stat pivots, trade sorting) stays app-owned — every component takes render-ready props.",
];

export default function FinancePage() {
  return (
    <main className="reference-page accent-digiquant">
      <header className="hero">
        <p className="kicker">{"// finance"}</p>
        <h1>
          Quant surfaces, <em>money-colored.</em>
        </h1>
        <p>
          The finance-specific grammar behind digiquant: price charts on TradingView Lightweight
          Charts, order books, and tearsheet metrics. Gains and losses wear the sanctioned{" "}
          <code>--up</code> / <code>--down</code>
          {" "}money colors; the module livery stays for identity and chrome, never for P&amp;L.
          One family, two engines: canvas for dashboards, pure SVG for the print branch at the
          foot of the page.
        </p>
        <PageToc items={TOC_ITEMS} />
      </header>

      <StockTickerReference />

      <section className="section-block" id="price-chart">
        <p className="kicker">{"// price chart"}</p>
        <h2 className="title">Prices on Lightweight Charts.</h2>
        <p className="section-copy">
          Candlesticks and volume rendered by TradingView&apos;s open-source{" "}
          <code>lightweight-charts</code> — we feed it our own backtest OHLC, so there&apos;s no
          external data feed or branding, just the engine. It reads the design tokens (up/down,
          hairlines, mono type) and re-themes live when the theme or livery changes. This is the
          standard price-plotting primitive; custom SVG candles are retired.
        </p>
        <div className="pc-frame">
          <PriceChartReference />
        </div>
      </section>

      <section className="section-block" id="equity-curve">
        <p className="kicker">{"// equity curve"}</p>
        <h2 className="title">Cumulative equity, one line.</h2>
        <p className="section-copy">
          The tearsheet&apos;s headline: an area series on the same Lightweight Charts engine,
          tracking cumulative equity from a hundred. It wears the module accent (not the money
          colors — this is identity, not a single P&amp;L reading) and re-themes live.
        </p>
        <div className="pc-frame">
          <EquityCurveReference />
        </div>
      </section>

      <section className="section-block" id="drawdown">
        <p className="kicker">{"// drawdown"}</p>
        <h2 className="title">Underwater, in the red.</h2>
        <p className="section-copy">
          The companion to the equity curve: percent below the running peak, hanging under a zero
          baseline. It only ever reads negative, so it takes the <code>--down</code> money color —
          the depth and duration of the red is the risk story the CAGR hides.
        </p>
        <div className="pc-frame">
          <DrawdownPlotReference />
        </div>
      </section>

      <section className="section-block" id="synced-tearsheet">
        <p className="kicker">{"// synced tearsheet"}</p>
        <h2 className="title">Two panes, one time axis.</h2>
        <p className="section-copy">
          Equity and its underwater drawdown in a single chart, split into stacked panes. Because
          they share one time scale, the x-axis, crosshair and zoom move together — hover the top
          pane and the drawdown reads the same bar. Both series come from the same walk, so every
          dip lines up with the red beneath it. This is the multi-chart primitive for screen-only
          dashboards; add a pane per series rather than stacking separate charts. Print-grade
          tearsheets — anything with a PDF export — compose the SVG{" "}
          <a href="#print-tearsheet">finance-tearsheet family</a> instead.
        </p>
        <div className="pc-frame pc-frame--tall">
          <SyncedTearsheetReference />
        </div>
      </section>

      <PerformanceDashboardReference />
      <PortfolioWorkspaceReference />
      <PortfolioReference />

      <section className="section-block" id="charting-rules">
        <p className="kicker">{"// charting rules"}</p>
        <h2 className="title">How we embed TradingView charts.</h2>
        <p className="section-copy">
          The house rules for every embedded Lightweight Charts surface — follow these and a chart
          drops into any page, any theme, any livery without a second thought.
        </p>
        <ol className="chart-rules">
          {CHART_RULES.map((rule) => (
            <li key={rule}>{rule}</li>
          ))}
        </ol>
      </section>

      <PerfMetricsReference />
      <MonthlyReturnsReference />
      <OrderbookReference />

      <section className="section-block" id="print-tearsheet">
        <p className="kicker">{"// print branch — finance-tearsheet family"}</p>
        <h2 className="title">Backtests, print-grade.</h2>
        <p className="section-copy">
          The other engine in the finance family: dependency-free SVG charts with synced zoom and
          trade markers, the KPI strip, signed contribution with exact portfolio return, the
          returns matrix, the trade log, and the library card. Everything below survives{" "}
          <code>window.print()</code> — hit Download PDF and the same components re-render at full
          span into a paper-white export. Canvas dashboards above; SVG here.
        </p>
      </section>

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

      <section className="section-block" id="tearsheet-dca">
        <p className="kicker">{"// dca overlays"}</p>
        <h2 className="title">Rails, then the band.</h2>
        <p className="section-copy">
          Schema 1.3 DCA books overlay valuation rails on log price and paint composite
          risk 0–100 with the labelled Fire sale → Bubble bands. Same SVG engine, same
          print path — no canvas, no one-off styling.
        </p>
        <div className="mt-[1.2rem]">
          <TearsheetDcaReference />
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
