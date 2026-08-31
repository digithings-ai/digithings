"use client";
/**
 * Renders a strategy tearsheet from the unified TearsheetData JSON. Fetches
 * /strategies/<slug>.json at runtime (keeps the large series out of the static
 * HTML), then renders KPIs, a pivotable statistics table (direction / year /
 * quarter), theme-aware SVG charts
 * (equity with log/linear toggle, drawdown, dual-axis per-trade & cumulative
 * P&L — all sharing one zoom/pan time window), a returns heatmap, and the trade
 * log. "Download PDF" opens the system print dialog with a light-mode,
 * full-span export layout (all charts and tables, digiquant branding).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  CandlestickChart,
  ChartLegend,
  ChartResetButton,
  DirectionPill,
  Kpi,
  KpiStrip,
  LOOKBACK_OPTIONS,
  MultiTimeSeries,
  PRINT_FULL_VIEW,
  RISK_BANDS,
  ReturnsMatrix,
  RiskBandStrip,
  AllocationStepChart,
  SegToggle,
  TerminalMark,
  TimeSeries,
  TradeLogTable,
  TradeReturnChart,
  fmtCompact,
  fmtNum,
  fmtPct,
  matchLookbackPreset,
  runTearsheetPrint,
  toneClass,
  viewWindowForPreset,
  viewsNear,
  type ChartScale,
  type LookbackPreset,
  type MatrixMetric,
  type OverlaySeries,
  type ReturnsPeriod,
  type TradeLogColumn,
  type TradeLogRow,
  type ViewWindow,
} from "@digithings/web";
import { AssetLogoFor } from "./asset-logo";
import { CurrentPosition, TradeReturnCell } from "./current-position";
import { LiveMetricsBadge } from "./live-metrics";
import { PivotStatsPivotToggle, PivotStatsTable } from "./pivot-stats-table";
import { SignalDelayChip } from "./signal-delay";
import type { StatsPivot } from "./pivot-stats";
import { RemainingBookNotes, StrategyNotes } from "./strategy-notes";
import { strategyDisplayName, symbolBase } from "./strategy-names";
import { chartFullSpan, clipOhlc, clipPoints, closesFromOhlc } from "./series";
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
import { type TearsheetData, type TearsheetTrade } from "./types";
import { fetchTearsheet } from "@/lib/live/strategies";
import { hasTradeKpis, isDcaTearsheet, allocatedPctCurve, cashPctFromAllocated, fillMarkersForChart, indicatorPanels, curveKnees, lastAllocatedPct, ALLOCATED_KPI_LABEL, VS_FLAT_KPI_LABEL, VS_LUMP_KPI_LABEL, isValuationOnlyIndex } from "./dca";
import { BacktestOnlyChip, OosHonestyChip } from "./honesty";

function Toned({ v, children }: { v: number | null | undefined; children: React.ReactNode }) {
  const c = toneClass(v);
  return c ? <span className={c}>{children}</span> : <>{children}</>;
}

/** Trade-log wiring over the family TradeLogTable: the open leg renders its
 *  live mark and unrealized return (TradeReturnCell), closed rows the exit. */
const TRADE_LOG_COLUMNS: TradeLogColumn[] = [
  { label: "Direction" },
  { label: "Date" },
  { label: "Asset" },
  { label: "Entry", numeric: true },
  { label: "Mark", numeric: true },
  { label: "Return", numeric: true },
];

function TradeLog({
  trades,
  data,
  asset,
}: {
  trades: TearsheetTrade[];
  data: TearsheetData;
  asset: string;
}) {
  const rows: TradeLogRow[] = trades.map((t) => {
    const open = isOpenTrade(t);
    const mark = open ? markPriceForTrade(t, data) : t.exit_price;
    return {
      key: t.n,
      open,
      cells: [
        <DirectionPill key="dir" direction={t.direction} />,
        tradeLogDate(t),
        asset,
        fmtNum(t.entry_price, 2),
        fmtNum(mark, 2),
        <TradeReturnCell key="ret" t={t} data={data} />,
      ],
    };
  });
  return <TradeLogTable columns={TRADE_LOG_COLUMNS} rows={rows} />;
}

type TearsheetMode = "charts" | "tables";
type ChartTab = "price" | "rails" | "risk" | "indicators" | "accumulation" | "equity" | "drawdown" | "pnl" | "matrix";
type TableTab = "stats" | "trades";

/** Honest chrome when Cloudflare Pages has the route but the live store has no payload yet. */
function TearsheetUnavailable({ slug, message }: { slug: string; message: string }) {
  const dca = slug.includes("sdca");
  const title = strategyDisplayName(slug);
  const asset = symbolBase(slug.split("_")[0]?.toUpperCase() || slug);
  const symbol = `${asset}-USD`;
  return (
    <div className="ts-print-root">
      <header className="ts-header">
        <div className="ts-header-main">
          <Link href="/strategies" className="ts-back">← Strategies</Link>
          <h1 className="ts-h1 ts-h1-with-logo">
            <AssetLogoFor strategy={slug} symbol={symbol} size={36} className="ts-header-logo" />
            <span>{title}</span>
          </h1>
          {dca ? (
            <div className="ts-meta">
              <span className="ts-chip">{symbol}</span>
              <SignalDelayChip days={3} detail="full" />
              <BacktestOnlyChip />
              <OosHonestyChip beatsFlatDcaOos={false} />
            </div>
          ) : null}
        </div>
      </header>
      <p className="ts-status ts-status-error" role="status">
        {message} Charts and KPIs appear after the operator publishes this backtest
        to the live store — they are not omitted to hide a result.
      </p>
      {dca ? <RemainingBookNotes strategy={slug} asset={asset} /> : null}
    </div>
  );
}

const CHART_H = 440;

function PrintHeading({ children }: { children: string }) {
  return <h2 className="ts-print-heading">{children}</h2>;
}

export function TearsheetView({ slug }: { slug: string }) {
  const [data, setData] = useState<TearsheetData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [scale, setScale] = useState<ChartScale>("linear");
  const [period, setPeriod] = useState<ReturnsPeriod>("monthly");
  const [matrixMetric, setMatrixMetric] = useState<MatrixMetric>("return");
  const [viewOverride, setViewOverride] = useState<ViewWindow | null>(null);
  const [lookback, setLookback] = useState<LookbackPreset>("1y");
  const [mode, setMode] = useState<TearsheetMode>("charts");
  const [chartTabPick, setChartTab] = useState<ChartTab | null>(null);
  const [tableTab, setTableTab] = useState<TableTab>("stats");
  const [statsPivot, setStatsPivot] = useState<StatsPivot>("direction");
  const [printing, setPrinting] = useState(false);
  const printThemeRef = useRef<string | null>(null);
  const printTitleRef = useRef<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetchTearsheet(slug)
      .then((d) => {
        if (!alive) return;
        if (d) setData(d);
        else setErr("Could not load tearsheet data — the live store returned nothing.");
      })
      .catch((e: unknown) => {
        if (alive) setErr(`Could not load tearsheet data: ${e instanceof Error ? e.message : String(e)}`);
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
  const chartSpot = useMemo(() => closesFromOhlc(chartOhlc), [chartOhlc]);
  const chartRails = useMemo(
    () => (data?.rails ? data.rails.filter((r) => !data.period_start || r.t >= data.period_start) : []),
    [data],
  );
  const chartRisk = useMemo(
    () => (data?.risk_curve ? clipPoints(data.risk_curve, data.period_start) : []),
    [data],
  );
  const chartCost = useMemo(
    () => (data?.cost_basis_curve ? clipPoints(data.cost_basis_curve, data.period_start) : []),
    [data],
  );
  const chartLump = useMemo(
    () => (data?.lump_equity_curve ? clipPoints(data.lump_equity_curve, data.period_start) : []),
    [data],
  );
  const chartFlat = useMemo(
    () => (data?.flat_dca_equity_curve ? clipPoints(data.flat_dca_equity_curve, data.period_start) : []),
    [data],
  );
  const chartAllocated = useMemo(() => (data ? clipPoints(allocatedPctCurve(data), data.period_start) : []), [data]);
  const chartCash = useMemo(() => cashPctFromAllocated(chartAllocated), [chartAllocated]);
  const chartFills = useMemo(() => (data ? fillMarkersForChart(data) : []), [data]);
  const chartIndicators = useMemo(() => (data ? indicatorPanels(data) : []), [data]);
  const chartKnees = useMemo(() => (data ? curveKnees(data) : { buy_knee_risk: 25, sell_knee_risk: 70 }), [data]);

  const pnlBars = useMemo(() => (data ? tradesForPnlChart(data) : []), [data]);

  const equityPct = useMemo(() => {
    if (!data || chartEquity.length === 0) return [];
    const base = data.initial_capital;
    return chartEquity.map((p) => ({ t: p.t, v: base > 0 ? (p.v / base - 1) * 100 : 0 }));
  }, [data, chartEquity]);

  const toReturnPct = useCallback(
    (points: { t: string; v: number }[], base: number) =>
      points.map((p) => ({ t: p.t, v: base > 0 ? (p.v / base - 1) * 100 : 0 })),
    [],
  );

  const fullSpan = useMemo<[string, string] | undefined>(() => {
    if (!data) return undefined;
    return chartFullSpan(data.period_start, data.equity_curve, data.period_end);
  }, [data]);

  const presetView = useMemo(
    () => (fullSpan ? viewWindowForPreset(lookback, fullSpan) : { lo: 0, hi: 1 }),
    [lookback, fullSpan],
  );
  const view = viewOverride ?? presetView;

  const setViewFromChart = useCallback(
    (v: ViewWindow) => {
      setViewOverride(v);
      const matched = matchLookbackPreset(v, fullSpan);
      if (matched) setLookback(matched);
    },
    [fullSpan],
  );

  const applyLookback = useCallback(
    (preset: LookbackPreset) => {
      setLookback(preset);
      setViewOverride(null);
    },
    [],
  );

  const hasPrice = chartOhlc.length > 0;
  const hasRails = chartRails.length > 0 && chartSpot.length > 0;
  const hasRisk = chartRisk.length > 0;
  const hasIndicators = chartIndicators.length > 0;
  const hasAccum = chartCost.length > 0 || chartAllocated.length > 0;
  const hasThreeWay = chartLump.length > 0 && chartFlat.length > 0;
  const showTradeKpis = data ? hasTradeKpis(data.win_rate_pct, data.profit_factor) : true;
  const dcaBook = data ? isDcaTearsheet(data) : false;
  const chartTab =
    chartTabPick ??
    (hasRails ? "rails" : hasPrice ? "price" : "equity");

  useEffect(() => {
    if (dcaBook) setScale("log");
  }, [dcaBook]);

  useEffect(() => {
    const sheetTitle = strategyDisplayName(slug, data?.label);
    const onBeforePrint = () => {
      printThemeRef.current = document.documentElement.getAttribute("data-theme");
      printTitleRef.current = document.title;
      document.documentElement.setAttribute("data-theme", "light");
      document.documentElement.classList.add("ts-printing");
      document.title = `${sheetTitle} — digiquant`;
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
  }, [slug, data?.label]);

  const avgTrade = useMemo(() => avgTradePct(data ? data.trades.map((t) => t.pnl_pct) : []), [data]);

  const chartTabOptions = useMemo(() => {
    const opts: { value: ChartTab; label: string }[] = [];
    if (hasPrice) opts.push({ value: "price", label: "Price" });
    if (hasRails) opts.push({ value: "rails", label: "Rails" });
    if (hasRisk) opts.push({ value: "risk", label: dcaBook ? "Risk" : "Index" });
    if (hasIndicators) opts.push({ value: "indicators", label: "Indicators" });
    if (hasAccum) opts.push({ value: "accumulation", label: "Allocation" });
    opts.push({ value: "equity", label: "Equity" }, { value: "drawdown", label: "Drawdown" });
    if (showTradeKpis) opts.push({ value: "pnl", label: "P&L" });
    opts.push({ value: "matrix", label: "Matrix" });
    return opts;
  }, [dcaBook, hasAccum, hasIndicators, hasPrice, hasRails, hasRisk, showTradeKpis]);

  const railsOverlay: OverlaySeries[] = useMemo(() => {
    if (!hasRails) return [];
    return [
      { id: "spot", label: "Spot", points: chartSpot, tone: "accent", fill: true },
      {
        id: "low",
        label: "Low",
        points: chartRails.map((r) => ({ t: r.t, v: r.low })),
        tone: "mute",
        dashed: true,
      },
      {
        id: "median",
        label: "Median",
        points: chartRails.map((r) => ({ t: r.t, v: r.median })),
        tone: "mute",
      },
      {
        id: "high",
        label: "High",
        points: chartRails.map((r) => ({ t: r.t, v: r.high })),
        tone: "mute",
        dashed: true,
      },
    ];
  }, [chartRails, chartSpot, hasRails]);

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
      case "rails":
        return (
          <ChartLegend
            items={[
              { kind: "line", label: "Spot" },
              { kind: "line-dashed", label: "Low / high (power law)" },
              { kind: "line-mute", label: "Median" },
            ]}
          />
        );
      case "risk":
        return (
          <span className="ts-panel-hint">
            {`accumulate starts at ${chartKnees.buy_knee_risk} · distribute starts at ${chartKnees.sell_knee_risk} · `}
            {RISK_BANDS.map((b) => `${b.lo}–${b.hi} ${b.label}`).join(" · ")}
          </span>
        );
      case "indicators":
        return (
          <span className="ts-panel-hint">
            {isValuationOnlyIndex(data?.indicator_weights)
              ? "Power-law only. Extra indicators are unused (weight 0)."
              : "Index members. Zero-weight extras are unused."}
          </span>
        );
      case "accumulation":
        return (
          <ChartLegend
            items={[
              { kind: "line", label: "% allocated" },
              { kind: "line-dashed", label: "% cash" },
              { kind: "marker-buy", label: "buy fill" },
              { kind: "marker-sell", label: "sell fill" },
            ]}
          />
        );
      case "equity":
        return hasThreeWay ? (
          <ChartLegend
            items={[
              { kind: "line", label: scale === "log" ? "SDCA ($)" : "SDCA %" },
              { kind: "line-dashed", label: "Lump" },
              { kind: "line-mute", label: "Flat DCA" },
            ]}
          />
        ) : (
          <ChartLegend items={[{ kind: "line", label: scale === "log" ? "Equity ($)" : "Return %" }]} />
        );
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
  }, [chartKnees.buy_knee_risk, chartKnees.sell_knee_risk, chartTab, data?.indicator_weights, hasThreeWay, scale]);

  if (err) return <TearsheetUnavailable slug={slug} message={err} />;
  if (!data) return <p className="ts-status">Loading tearsheet…</p>;

  const title = strategyDisplayName(slug, data?.label);
  const asset = symbolBase(data.symbol);
  const cagr = cagrPct(data.initial_capital, data.final_equity, data.period_start, data.period_end);

  const chartView = printing ? PRINT_FULL_VIEW : view;
  const chartScale = printing ? "linear" : scale;

  const handlePrint = () => {
    runTearsheetPrint({ documentTitle: `${title} — digiquant`, setPrinting });
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
      {chartTab === "price" || chartTab === "equity" || chartTab === "rails" ? (
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
        {/* Print brand uses TerminalMark in currentColor (the old QR tile was
            hardcoded to the dark variant and printed as a black square). */}
        <TerminalMark size={22} variant="compact" className="ts-print-brand-mark" />
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
            <SignalDelayChip days={data.signal_delay_days} detail="full" />
            {dcaBook ? <BacktestOnlyChip /> : null}
            {dcaBook ? <OosHonestyChip beatsFlatDcaOos={data.beats_flat_dca_oos} /> : null}
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

      <KpiStrip primary ariaLabel="Headline performance">
        <Kpi label="CAGR" value={<Toned v={cagr}>{fmtPct(cagr)}</Toned>} />
        <Kpi label="Max drawdown" value={<span className="is-neg">{fmtPct(data.max_drawdown_pct)}</span>} />
        {dcaBook && data.dca ? (
          <>
            <Kpi label={VS_LUMP_KPI_LABEL} value={<Toned v={data.dca.vs_lump_pct}>{fmtPct(data.dca.vs_lump_pct)}</Toned>} />
            <Kpi label={VS_FLAT_KPI_LABEL} value={<Toned v={data.dca.vs_flat_dca_pct}>{fmtPct(data.dca.vs_flat_dca_pct)}</Toned>} />
            <Kpi label={ALLOCATED_KPI_LABEL} value={fmtPct(lastAllocatedPct(data))} />
            <Kpi label="Units" value={fmtNum(data.dca.units_accumulated, 2)} />
          </>
        ) : showTradeKpis ? (
          <>
            <Kpi label="Profit factor" value={fmtNum(data.profit_factor, 2)} />
            <Kpi label="Win rate" value={fmtPct(data.win_rate_pct)} />
            <Kpi label="Avg trade return" value={<Toned v={avgTrade}>{fmtPct(avgTrade)}</Toned>} />
            <Kpi
              label="Trades / yr"
              value={fmtNum(tradesPerYear(data.total_trades, data.period_start, data.period_end), 1)}
            />
          </>
        ) : null}
      </KpiStrip>

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
                  ariaLabel={`${data.symbol} candlestick price chart`}
                />
              </div>
            </div>
          ) : null}
          {hasRails ? (
            <div className="ts-tab-pane" hidden={chartTab !== "rails"}>
              <PrintHeading>Power-law rails</PrintHeading>
              <div className="ts-chart">
                <MultiTimeSeries
                  series={railsOverlay}
                  height={CHART_H}
                  scale={chartScale === "log" ? "log" : "linear"}
                  fmt={fmtCompact}
                  view={chartView}
                  onView={setViewFromChart}
                  fullSpan={fullSpan}
                  resetView={presetView}
                  ariaLabel={`${data.symbol} log price with power-law rails`}
                />
              </div>
            </div>
          ) : null}
          {hasRisk ? (
            <div className="ts-tab-pane" hidden={chartTab !== "risk"}>
              <PrintHeading>Power-law risk</PrintHeading>
              <div className="ts-chart">
                <RiskBandStrip
                  points={chartRisk}
                  height={CHART_H}
                  view={chartView}
                  onView={setViewFromChart}
                  fullSpan={fullSpan}
                  resetView={presetView}
                  thresholds={[
                    {
                      id: "buy",
                      value: chartKnees.buy_knee_risk,
                      label: `accumulate (oversold) ${chartKnees.buy_knee_risk}`,
                    },
                    {
                      id: "sell",
                      value: chartKnees.sell_knee_risk,
                      label: `distribute (overbought) ${chartKnees.sell_knee_risk}`,
                    },
                  ]}
                  priceOverlay={chartSpot}
                  ariaLabel="Power-law risk 0 to 100 with accumulate and distribute knees and log BTC overlay"
                />
              </div>
            </div>
          ) : null}
          {hasIndicators ? (
            <div className="ts-tab-pane" hidden={chartTab !== "indicators"}>
              <PrintHeading>Underlying indicators</PrintHeading>
              <div className="ts-indicator-grid">
                {chartIndicators.map((ind) => (
                  <div key={ind.name} className={ind.in_index ? undefined : "ts-indicator-unused"}>
                    <p className="ts-indicator-caption">
                      {ind.display_name}
                      {ind.in_index ? ` · in index, weight ${ind.weight}` : " · unused extra, weight 0"}
                    </p>
                    {ind.points.length > 0 ? (
                      <TimeSeries
                        points={clipPoints(ind.points, data.period_start)}
                        height={200}
                        scale="linear"
                        tone="accent"
                        fmt={(v) => fmtCompact(v)}
                        view={chartView}
                        onView={setViewFromChart}
                        fullSpan={fullSpan}
                        resetView={presetView}
                        ariaLabel={`${ind.display_name} on the 0 to 100 risk scale`}
                      />
                    ) : (
                      <p className="ts-panel-hint">no series (unused extra, weight 0)</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {hasAccum ? (
            <div className="ts-tab-pane" hidden={chartTab !== "accumulation"}>
              <PrintHeading>Allocation</PrintHeading>
              {chartAllocated.length > 0 ? (
                <div className="ts-chart">
                  <AllocationStepChart
                    allocated={chartAllocated}
                    cash={chartCash}
                    markers={chartFills}
                    priceOverlay={chartSpot}
                    height={CHART_H}
                    view={chartView}
                    onView={setViewFromChart}
                    fullSpan={fullSpan}
                    resetView={presetView}
                    ariaLabel="Percent allocated versus percent cash, step chart, with fill dots sized by fraction of book moved"
                  />
                </div>
              ) : null}
              {chartCost.length > 0 ? (
                <div className="ts-chart">
                  <MultiTimeSeries
                    series={[
                      ...(chartSpot.length
                        ? [{ id: "spot", label: "Spot", points: chartSpot, tone: "accent" as const, fill: true }]
                        : []),
                      { id: "cost", label: "Cost basis", points: chartCost, tone: "up" as const },
                    ]}
                    height={Math.round(CHART_H * 0.55)}
                    scale={chartScale === "log" ? "log" : "linear"}
                    fmt={fmtCompact}
                    view={chartView}
                    onView={setViewFromChart}
                    fullSpan={fullSpan}
                    resetView={presetView}
                    ariaLabel="Cost basis versus spot price"
                  />
                </div>
              ) : null}
            </div>
          ) : null}
          <div className="ts-tab-pane" hidden={chartTab !== "equity"}>
            <PrintHeading>Equity</PrintHeading>
            <div className="ts-chart">
              {hasThreeWay ? (
                <MultiTimeSeries
                  series={
                    chartScale === "log"
                      ? [
                          { id: "sdca", label: "SDCA", points: chartEquity, tone: "accent", fill: true },
                          { id: "lump", label: "Lump", points: chartLump, tone: "mute", dashed: true },
                          { id: "flat", label: "Flat DCA", points: chartFlat, tone: "mute" },
                        ]
                      : [
                          { id: "sdca", label: "SDCA", points: equityPct, tone: "accent", fill: true },
                          {
                            id: "lump",
                            label: "Lump",
                            points: toReturnPct(chartLump, data.initial_capital),
                            tone: "mute",
                            dashed: true,
                          },
                          {
                            id: "flat",
                            label: "Flat DCA",
                            points: toReturnPct(chartFlat, data.initial_capital),
                            tone: "mute",
                          },
                        ]
                  }
                  height={CHART_H}
                  scale={chartScale === "log" ? "log" : "linear"}
                  fmt={chartScale === "log" ? fmtCompact : (v) => fmtCompact(v) + "%"}
                  view={chartView}
                  onView={setViewFromChart}
                  fullSpan={fullSpan}
                  resetView={presetView}
                  ariaLabel="SDCA equity versus lump-sum and flat DCA"
                />
              ) : chartScale === "log" ? (
                <TimeSeries points={chartEquity} height={CHART_H} scale="log" tone="accent" fmt={fmtCompact} view={chartView} onView={setViewFromChart} fullSpan={fullSpan} resetView={presetView} ariaLabel="Equity curve in dollars, log scale" />
              ) : (
                <TimeSeries points={equityPct} height={CHART_H} scale="linear" tone="accent" fmt={(v) => fmtCompact(v) + "%"} view={chartView} onView={setViewFromChart} fullSpan={fullSpan} resetView={presetView} ariaLabel="Equity curve, percent return, linear scale" />
              )}
            </div>
          </div>
          <div className="ts-tab-pane" hidden={chartTab !== "drawdown"}>
            <PrintHeading>Drawdown</PrintHeading>
            <div className="ts-chart">
              <TimeSeries points={chartDrawdown} height={CHART_H} scale="linear" tone="down" zeroBaseline fmt={(v) => v.toFixed(0) + "%"} view={chartView} onView={setViewFromChart} fullSpan={fullSpan} resetView={presetView} ariaLabel="Drawdown, percent below peak equity" />
            </div>
          </div>
          {showTradeKpis ? (
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
                  ariaLabel="Per-trade profit and loss, percent"
                />
              </div>
            </div>
          ) : null}
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
              ...(showTradeKpis
                ? [{ value: "trades" as const, label: "Trade log" }]
                : []),
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
            <TradeLog trades={sortedTrades} data={data} asset={asset} />
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
