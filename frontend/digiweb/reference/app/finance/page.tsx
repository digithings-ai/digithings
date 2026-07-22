import "./finance.css";
import { DashboardWorkspaceReference } from "@/components/dashboard-workspace-reference";
import { DrawdownPlotReference } from "@/components/drawdown-plot-reference";
import { EquityCurveReference } from "@/components/equity-curve-reference";
import { MonthlyReturnsReference } from "@/components/monthly-returns-reference";
import { OrderbookReference } from "@/components/orderbook-reference";
import { PerfMetricsReference } from "@/components/perf-metrics-reference";
import { PerformanceDashboardReference } from "@/components/performance-dashboard-reference";
import { PortfolioReference } from "@/components/portfolio-reference";
import { PortfolioWorkspaceReference } from "@/components/portfolio-workspace-reference";
import { PriceChartReference } from "@/components/price-chart-reference";
import { StockTickerReference } from "@/components/stock-ticker-reference";
import { SyncedTearsheetReference } from "@/components/synced-tearsheet-reference";

const CHART_RULES = [
  "Lightweight Charts (TradingView's open-source engine) is the price/series primitive for DASHBOARD surfaces. Print-grade surfaces (PDF-exporting tearsheets) compose the SVG finance-tearsheet family instead — canvas rasterizes in print. The split ruling: frontend/digiweb/CHARTS.md.",
  "We feed it our own backtest data. No external feed, no market connection; attributionLogo is off, so there's no TradingView branding.",
  "The canvas background is always transparent and every color is read from a design token (--up/--down, --hair, --accent, --font-mono) — never hard-coded.",
  "A MutationObserver on data-theme re-applies the palette, so charts re-theme live on light/dark and livery changes.",
  "autoSize is on — the chart fills its pane's width and height; give the pane a definite height for it to fill.",
  "Money colors (--up/--down) are for P&L only. The module accent is identity/chrome, never a single gain or loss read.",
  "Multi-series views use panes with one shared time axis (or distinguishable hues as identifiers) — never money hues to tell series apart.",
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
          Charts, order books, and tearsheet metrics. Gains and losses wear the sanctioned
          <code> --up</code> / <code>--down</code> money colors; the module livery stays for
          identity and chrome, never for P&amp;L.
        </p>
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
          <a href="/tearsheet">finance-tearsheet family</a> instead.
        </p>
        <div className="pc-frame pc-frame--tall">
          <SyncedTearsheetReference />
        </div>
      </section>

      <PerformanceDashboardReference />
      <PortfolioWorkspaceReference />
      <DashboardWorkspaceReference />
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
    </main>
  );
}
