"use client";
/**
 * Renders a strategy tearsheet from the unified TearsheetData JSON. Fetches
 * /strategies/<slug>.json at runtime (keeps the large series out of the static
 * HTML), then renders KPIs, a pivotable statistics table (direction / year /
 * quarter), theme-aware SVG charts
 * (equity with log/linear toggle, drawdown, dual-axis per-trade & cumulative
 * P&L — all sharing one zoom/pan time window), a returns heatmap, and the trade
 * log. "Download PDF" opens the system print dialog with a light-mode,
 * full-span export layout (all charts and tables, DigiQuant branding).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  CandlestickChart,
  ChartLegend,
  ChartResetButton,
  TimeSeries,
  TradeReturnChart,
  ReturnsMatrix,
  SegToggle,
  LOOKBACK_OPTIONS,
  matchLookbackPreset,
  viewWindowForPreset,
  viewsNear,
  type LookbackPreset,
  type MatrixMetric,
  type Scale,
  type ReturnsPeriod,
  type ViewWindow,
} from "./charts";
import { AssetLogoFor } from "./asset-logo";
import { CurrentPosition, TradeReturnCell } from "./current-position";
import { LiveMetricsBadge } from "./live-metrics";
import { fmtCompact, fmtNum, fmtPct, toneClass } from "./format";
import { PivotStatsPivotToggle, PivotStatsTable } from "./pivot-stats-table";
import type { StatsPivot } from "./pivot-stats";
import { StrategyNotes } from "./strategy-notes";
import { strategyDisplayName, symbolBase } from "./strategy-names";
import { chartFullSpan, clipOhlc, clipPoints } from "./series";
import {
  avgTradePct,
  cagrPct,
  tradesPerYear,
} from "./stats";
import {
  isOpenTrade,
  markPriceForTrade,
  sortTradesForLog,
  tradeLogDate,
  tradesForPnlChart,
  tradesForDisplay,
} from "./trades";
import { type TearsheetData, type TearsheetTrade, type StrategyIndexEntry } from "./types";
import { PRINT_FULL_VIEW, runPrintTearsheet } from "./print-tearsheet";
import index from "@/public/strategies/index.json";

const INDEX = index as StrategyIndexEntry[];

function Kpi({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="ts-kpi">
      <span className="ts-kpi-label">{label}</span>
      <span className="ts-kpi-value">{value}</span>
    </div>
  );
}

function Toned({ v, children }: { v: number | null | undefined; children: React.ReactNode }) {
  const c = toneClass(v);
  return c ? <span className={c}>{children}</span> : <>{children}</>;
}

function TradeLogTable({
  trades,
  data,
  asset,
}: {
  trades: TearsheetTrade[];
  data: TearsheetData;
  asset: string;
}) {
  return (
    <div className="ts-table-wrap ts-table-scroll">
      <table className="ts-table ts-trades">
        <thead>
          <tr>
            <th>Direction</th>
            <th>Date</th>
            <th>Asset</th>
            <th className="ts-num">Entry</th>
            <th className="ts-num">Mark</th>
            <th className="ts-num">Return</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => {
            const open = isOpenTrade(t);
            const mark = open ? markPriceForTrade(t, data) : t.exit_price;
            return (
              <tr key={t.n} className={open ? "ts-trade-open" : undefined}>
                <td><span className={`ts-dir ts-dir-${t.direction}`}>{t.direction}</span></td>
                <td>{tradeLogDate(t)}</td>
                <td>{asset}</td>
                <td className="ts-num">{fmtNum(t.entry_price, 2)}</td>
                <td className="ts-num">{fmtNum(mark, 2)}</td>
                <td className="ts-num">
                  <TradeReturnCell t={t} data={data} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

type TearsheetMode = "charts" | "tables";
type ChartTab = "price" | "equity" | "drawdown" | "pnl" | "matrix";
type TableTab = "stats" | "trades";

const CHART_H = 440;

function PrintHeading({ children }: { children: string }) {
  return <h2 className="ts-print-heading">{children}</h2>;
}

export function TearsheetView({ slug }: { slug: string }) {
  const [data, setData] = useState<TearsheetData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [scale, setScale] = useState<Scale>("linear");
  const [period, setPeriod] = useState<ReturnsPeriod>("monthly");
  const [matrixMetric, setMatrixMetric] = useState<MatrixMetric>("return");
  const [view, setView] = useState<ViewWindow>({ lo: 0, hi: 1 });
  const [lookback, setLookback] = useState<LookbackPreset>("1y");
  const [mode, setMode] = useState<TearsheetMode>("charts");
  const [chartTab, setChartTab] = useState<ChartTab>("equity");
  const [tableTab, setTableTab] = useState<TableTab>("stats");
  const [statsPivot, setStatsPivot] = useState<StatsPivot>("direction");
  const [printing, setPrinting] = useState(false);
  const printThemeRef = useRef<string | null>(null);
  const printTitleRef = useRef<string | null>(null);

  const entry = INDEX.find((e) => e.strategy === slug);

  useEffect(() => {
    let alive = true;
    const src = `/strategies/${slug}.json`;
    fetch(src)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        return r.json();
      })
      .then((d: TearsheetData) => { if (alive) setData(d); })
      .catch((e: unknown) => {
        if (alive) setErr(`Could not load tearsheet data (${src}): ${e instanceof Error ? e.message : String(e)}`);
      });
    return () => { alive = false; };
  }, [slug]);

  const displayTrades = useMemo(() => (data ? tradesForDisplay(data) : []), [data]);
  const sortedTrades = useMemo(() => sortTradesForLog(displayTrades), [displayTrades]);

  const chartEquity = useMemo(
    () => (data ? clipPoints(data.equity_curve, data.period_start) : []),
    [data],
  );
  const chartDrawdown = useMemo(
    () => (data ? clipPoints(data.drawdown_curve, data.period_start) : []),
    [data],
  );
  const chartOhlc = useMemo(
    () => (data?.ohlc_bars ? clipOhlc(data.ohlc_bars, data.period_start) : []),
    [data],
  );

  const pnlBars = useMemo(() => (data ? tradesForPnlChart(data) : []), [data]);

  const equityPct = useMemo(() => {
    if (!data || chartEquity.length === 0) return [];
    const base = data.initial_capital;
    return chartEquity.map((p) => ({ t: p.t, v: base > 0 ? (p.v / base - 1) * 100 : 0 }));
  }, [data, chartEquity]);

  const fullSpan = useMemo<[string, string] | undefined>(() => {
    if (!data) return undefined;
    return chartFullSpan(data.period_start, data.equity_curve, data.period_end);
  }, [data]);

  useEffect(() => {
    setLookback("1y");
  }, [slug]);

  const presetView = useMemo(
    () => viewWindowForPreset(lookback, fullSpan),
    [lookback, fullSpan],
  );

  useEffect(() => {
    if (fullSpan) setView(viewWindowForPreset(lookback, fullSpan));
  }, [slug, fullSpan, lookback]);

  const setViewFromChart = useCallback(
    (v: ViewWindow) => {
      setView(v);
      const matched = matchLookbackPreset(v, fullSpan);
      if (matched) setLookback(matched);
    },
    [fullSpan],
  );

  const applyLookback = useCallback(
    (preset: LookbackPreset) => {
      setLookback(preset);
      if (fullSpan) setView(viewWindowForPreset(preset, fullSpan));
    },
    [fullSpan],
  );

  const hasPrice = chartOhlc.length > 0;

  useEffect(() => {
    setChartTab(hasPrice ? "price" : "equity");
  }, [slug, hasPrice]);

  useEffect(() => {
    const sheetTitle = strategyDisplayName(slug, entry?.label);
    const onBeforePrint = () => {
      printThemeRef.current = document.documentElement.getAttribute("data-theme");
      printTitleRef.current = document.title;
      document.documentElement.setAttribute("data-theme", "light");
      document.documentElement.classList.add("ts-printing");
      document.title = `${sheetTitle} — DigiQuant`;
      setPrinting(true);
    };
    const onAfterPrint = () => {
      document.documentElement.classList.remove("ts-printing");
      if (printThemeRef.current) {
        document.documentElement.setAttribute("data-theme", printThemeRef.current);
      }
      if (printTitleRef.current) document.title = printTitleRef.current;
      setPrinting(false);
    };
    window.addEventListener("beforeprint", onBeforePrint);
    window.addEventListener("afterprint", onAfterPrint);
    return () => {
      window.removeEventListener("beforeprint", onBeforePrint);
      window.removeEventListener("afterprint", onAfterPrint);
    };
  }, [slug, entry?.label]);

  const avgTrade = useMemo(() => avgTradePct(data ? data.trades.map((t) => t.pnl_pct) : []), [data]);

  const chartTabOptions = useMemo(() => {
    const opts: { value: ChartTab; label: string }[] = [];
    if (hasPrice) opts.push({ value: "price", label: "Price" });
    opts.push(
      { value: "equity", label: "Equity" },
      { value: "drawdown", label: "Drawdown" },
      { value: "pnl", label: "P&L" },
      { value: "matrix", label: "Matrix" },
    );
    return opts;
  }, [hasPrice]);

  const chartLegend = useMemo(() => {
    switch (chartTab) {
      case "price":
        return (
          <ChartLegend
            items={[
              { kind: "marker-buy", label: "long" },
              { kind: "marker-sell", label: "short" },
            ]}
          />
        );
      case "equity":
        return <ChartLegend items={[{ kind: "line", label: scale === "log" ? "Equity ($)" : "Return %" }]} />;
      case "drawdown":
        return <ChartLegend items={[{ kind: "line", label: "Drawdown %" }]} />;
      case "pnl":
        return (
          <ChartLegend
            items={[
              { kind: "bar-up", label: "Realized %" },
              { kind: "bar-open", label: "Open (unrealized)" },
            ]}
          />
        );
      case "matrix":
        return null;
      default: {
        const _exhaustive: never = chartTab;
        return _exhaustive;
      }
    }
  }, [chartTab, scale]);

  if (err) return <p className="ts-status ts-status-error">{err}</p>;
  if (!data) return <p className="ts-status">Loading tearsheet…</p>;

  const title = strategyDisplayName(slug, entry?.label);
  const asset = symbolBase(data.symbol);
  const cagr = cagrPct(data.initial_capital, data.final_equity, data.period_start, data.period_end);

  const chartView = printing ? PRINT_FULL_VIEW : view;
  const chartScale = printing ? "linear" : scale;

  const handlePrint = () => {
    runPrintTearsheet({ strategyTitle: title, setPrinting });
  };

  const zoomed = !viewsNear(view, presetView);
  const resetZoom = () => applyLookback(lookback);

  const chartToolsExtra = chartTab === "matrix" ? (
    <>
      <SegToggle
        label="Matrix metric"
        value={matrixMetric}
        onChange={setMatrixMetric}
        options={[
          { value: "return", label: "Returns" },
          { value: "drawdown", label: "Drawdown" },
          { value: "volatility", label: "Volatility" },
        ]}
      />
      <SegToggle
        label="Returns granularity"
        value={period}
        onChange={setPeriod}
        options={[
          { value: "monthly", label: "Monthly" },
          { value: "quarterly", label: "Quarterly" },
          { value: "annual", label: "Annual" },
        ]}
      />
    </>
  ) : (
    <>
      <SegToggle
        className="ts-seg-compact"
        label="Chart time range"
        value={lookback}
        onChange={applyLookback}
        options={LOOKBACK_OPTIONS}
      />
      {chartTab === "price" || chartTab === "equity" ? (
        <SegToggle
          label="Chart Y-axis scale"
          value={scale}
          onChange={setScale}
          options={[
            { value: "linear", label: "Linear" },
            { value: "log", label: "Log" },
          ]}
        />
      ) : null}
    </>
  );

  return (
    <div className="ts-print-root">
      <div className="ts-print-brand" aria-hidden="true">
        <img src="/favicon-qr-mark-dark.svg" alt="" width={22} height={22} className="ts-print-brand-mark" />
        <span className="ts-print-brand-word">digiquant</span>
        <a className="ts-print-brand-link" href="https://digiquant.io">digiquant.io</a>
      </div>

      <header className="ts-header">
        <div className="ts-header-main">
          <Link href="/strategies" className="ts-back">← Strategies</Link>
          <h1 className="ts-h1 ts-h1-with-logo">
            <AssetLogoFor strategy={slug} symbol={data.symbol} size={36} className="ts-header-logo" />
            <span>{title}</span>
          </h1>
          <div className="ts-meta">
            <LiveMetricsBadge generatedAt={data.generated_at} />
            <span className="ts-chip">{data.symbol}</span>
            <span className="ts-meta-text">{data.period_start} → {data.period_end} · {fmtNum(data.bars)} bars</span>
          </div>
        </div>
        <div className="ts-header-actions">
          <button
            className="btn btn-ghost btn-sm btn-icon"
            type="button"
            onClick={handlePrint}
            aria-label="Download tearsheet as PDF"
            title="Download PDF (disable browser headers & footers for a clean export)"
          >
            <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 3v12m0 0l-4-4m4 4l4-4M5 21h14" />
            </svg>
          </button>
        </div>
      </header>

      <CurrentPosition data={data} asset={asset} />

      <section className="ts-kpis ts-kpis-primary" aria-label="Headline performance">
        <Kpi label="CAGR" value={<Toned v={cagr}>{fmtPct(cagr)}</Toned>} />
        <Kpi label="Max drawdown" value={<span className="is-neg">{fmtPct(data.max_drawdown_pct)}</span>} />
        <Kpi label="Profit factor" value={fmtNum(data.profit_factor, 2)} />
        <Kpi label="Win rate" value={fmtPct(data.win_rate_pct)} />
        <Kpi label="Avg trade return" value={<Toned v={avgTrade}>{fmtPct(avgTrade)}</Toned>} />
        <Kpi
          label="Trades / yr"
          value={fmtNum(tradesPerYear(data.total_trades, data.period_start, data.period_end), 1)}
        />
      </section>

      <div className="ts-mode-bar">
        <SegToggle
          label="Tearsheet view"
          value={mode}
          onChange={setMode}
          options={[
            { value: "charts", label: "Charts" },
            { value: "tables", label: "Tables" },
          ]}
        />
      </div>

      <section className="ts-panel ts-tab-stack" hidden={mode !== "charts"}>
        <PrintHeading>Charts</PrintHeading>
        <div className="ts-panel-head">
          <SegToggle label="Chart" value={chartTab} onChange={setChartTab} options={chartTabOptions} />
          <div className="ts-panel-tools ts-chart-controls">
            {chartLegend}
            {chartToolsExtra}
          </div>
        </div>
        <div className="ts-tab-content ts-tab-content-charts">
          {chartTab !== "matrix" && zoomed ? (
            <ChartResetButton onClick={resetZoom} />
          ) : null}
          {hasPrice ? (
            <div className="ts-tab-pane" hidden={chartTab !== "price"}>
              <PrintHeading>Price</PrintHeading>
              <div className="ts-chart">
                <CandlestickChart
                  bars={chartOhlc}
                  trades={data.trades}
                  height={CHART_H}
                  scale={chartScale === "log" ? "log" : "linear"}
                  view={chartView}
                  onView={setViewFromChart}
                  fullSpan={fullSpan}
                  resetView={presetView}
                />
              </div>
            </div>
          ) : null}
          <div className="ts-tab-pane" hidden={chartTab !== "equity"}>
            <PrintHeading>Equity</PrintHeading>
            <div className="ts-chart">
              {chartScale === "log" ? (
                <TimeSeries points={chartEquity} height={CHART_H} scale="log" tone="accent" fmt={fmtCompact} view={chartView} onView={setViewFromChart} fullSpan={fullSpan} resetView={presetView} />
              ) : (
                <TimeSeries points={equityPct} height={CHART_H} scale="linear" tone="accent" fmt={(v) => fmtCompact(v) + "%"} view={chartView} onView={setViewFromChart} fullSpan={fullSpan} resetView={presetView} />
              )}
            </div>
          </div>
          <div className="ts-tab-pane" hidden={chartTab !== "drawdown"}>
            <PrintHeading>Drawdown</PrintHeading>
            <div className="ts-chart">
              <TimeSeries points={chartDrawdown} height={CHART_H} scale="linear" tone="down" zeroBaseline fmt={(v) => v.toFixed(0) + "%"} view={chartView} onView={setViewFromChart} fullSpan={fullSpan} resetView={presetView} />
            </div>
          </div>
          <div className="ts-tab-pane" hidden={chartTab !== "pnl"}>
            <PrintHeading>Per-trade return</PrintHeading>
            <div className="ts-chart">
              <TradeReturnChart
                bars={pnlBars}
                height={CHART_H}
                view={chartView}
                onView={setViewFromChart}
                fullSpan={fullSpan}
                resetView={presetView}
              />
            </div>
          </div>
          <div className="ts-tab-pane ts-tab-pane-matrix" hidden={chartTab !== "matrix"}>
            <PrintHeading>Period matrix</PrintHeading>
            <ReturnsMatrix
              points={chartEquity}
              drawdown={chartDrawdown}
              period={period}
              metric={matrixMetric}
            />
          </div>
        </div>
      </section>

      <section className="ts-panel ts-tab-stack" hidden={mode !== "tables"}>
        <PrintHeading>Tables</PrintHeading>
        <div className="ts-panel-head">
          <SegToggle
            label="Table"
            value={tableTab}
            onChange={setTableTab}
            options={[
              { value: "stats", label: "Statistics" },
              { value: "trades", label: "Trade log" },
            ]}
          />
          {tableTab === "stats" ? (
            <PivotStatsPivotToggle value={statsPivot} onChange={setStatsPivot} />
          ) : null}
        </div>
        <div className="ts-tab-content ts-tab-content-tables">
          <div className="ts-tab-pane" hidden={tableTab !== "stats"}>
            <PrintHeading>Statistics</PrintHeading>
            <PivotStatsTable data={data} printing={printing} pivot={statsPivot} />
          </div>
          <div className="ts-tab-pane" hidden={tableTab !== "trades"}>
            <PrintHeading>Trade log</PrintHeading>
            <TradeLogTable trades={sortedTrades} data={data} asset={asset} />
          </div>
        </div>
      </section>

      <footer className="ts-print-footer" aria-hidden="true">
        <span className="ts-print-footer-brand">digiquant</span>
        <a href={`https://digiquant.io/strategies/${slug}`}>digiquant.io/strategies/{slug}</a>
        <span className="ts-print-footer-note">Illustrative backtest · not investment advice</span>
      </footer>

      <StrategyNotes data={data} asset={asset} printing={printing} />
    </div>
  );
}
