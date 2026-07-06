import "./finance.css";
import { EquityCurveReference } from "@/components/equity-curve-reference";
import { MonthlyReturnsReference } from "@/components/monthly-returns-reference";
import { OrderbookReference } from "@/components/orderbook-reference";
import { PerfMetricsReference } from "@/components/perf-metrics-reference";
import { PriceChartReference } from "@/components/price-chart-reference";

export default function FinancePage() {
  return (
    <main className="reference-page accent-digiquant">
      <header className="hero">
        <p className="kicker">{"// finance"}</p>
        <h1>
          Quant surfaces, <em>money-colored.</em>
        </h1>
        <p>
          The finance-specific grammar behind DigiQuant: price charts on TradingView Lightweight
          Charts, order books, and tearsheet metrics. Gains and losses wear the sanctioned
          <code> --up</code> / <code>--down</code> money colors; the module livery stays for
          identity and chrome, never for P&amp;L.
        </p>
      </header>

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

      <PerfMetricsReference />
      <MonthlyReturnsReference />
      <OrderbookReference />
    </main>
  );
}
