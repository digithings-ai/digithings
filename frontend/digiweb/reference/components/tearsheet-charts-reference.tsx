"use client";
/**
 * Tearsheet charts — the print-grade tearsheet core: a 6-up KPI strip over
 * the tabbed SVG chart deck (candles with trade entry/exit markers + hover
 * cards, equity with a linear/log toggle, underwater drawdown, per-trade
 * P&L with the unrealized open leg, and the 3x3 returns matrix). All series
 * panes share ONE normalized ViewWindow — wheel-zoom or drag-pan any chart
 * and the others follow; lookback presets match back when a zoom lands on
 * one. The Download PDF button runs the real pipeline: flushSync re-renders
 * the same charts at full span, pins the light theme, and opens the system
 * print dialog — pure SVG is what makes the export crisp.
 */
import { useCallback, useMemo, useState } from "react";
import {
  CandlestickChart,
  ChartLegend,
  ChartResetButton,
  Kpi,
  KpiStrip,
  LOOKBACK_OPTIONS,
  PRINT_FULL_VIEW,
  ReturnsMatrix,
  SegToggle,
  TEARSHEET_DEMO,
  TimeSeries,
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
  type ReturnsPeriod,
  type ViewWindow,
} from "@digithings/web";

type ChartTab = "price" | "equity" | "drawdown" | "pnl" | "matrix";

const CHART_H = 440;
const D = TEARSHEET_DEMO;

function Toned({ v, children }: { v: number; children: React.ReactNode }) {
  const c = toneClass(v);
  return c ? <span className={c}>{children}</span> : <>{children}</>;
}

export function TearsheetChartsReference() {
  const [scale, setScale] = useState<ChartScale>("linear");
  const [lookback, setLookback] = useState<LookbackPreset>("1y");
  const [viewOverride, setViewOverride] = useState<ViewWindow | null>(null);
  const [chartTab, setChartTab] = useState<ChartTab>("price");
  const [period, setPeriod] = useState<ReturnsPeriod>("monthly");
  const [metric, setMetric] = useState<MatrixMetric>("return");
  const [printing, setPrinting] = useState(false);

  const presetView = useMemo(() => viewWindowForPreset(lookback, D.fullSpan), [lookback]);
  const view = viewOverride ?? presetView;
  const chartView = printing ? PRINT_FULL_VIEW : view;
  const chartScale: ChartScale = printing ? "linear" : scale;

  const setViewFromChart = useCallback((v: ViewWindow) => {
    setViewOverride(v);
    const matched = matchLookbackPreset(v, D.fullSpan);
    if (matched) setLookback(matched);
  }, []);

  const applyLookback = useCallback((preset: LookbackPreset) => {
    setLookback(preset);
    setViewOverride(null);
  }, []);

  // Headline figures derived from the demo walk — data wiring stays with the
  // page (the family takes render-ready values).
  const kpis = useMemo(() => {
    const first = D.equity[0].v;
    const last = D.equity[D.equity.length - 1].v;
    const years =
      (new Date(D.periodEnd).getTime() - new Date(D.periodStart).getTime()) /
      (365.25 * 24 * 3600 * 1000);
    const cagr = (Math.pow(last / first, 1 / years) - 1) * 100;
    const maxDd = Math.min(...D.drawdown.map((p) => p.v));
    const closed = D.trades.filter((t) => t.exit_reason !== "open");
    const wins = closed.filter((t) => t.pnl > 0);
    const grossUp = wins.reduce((a, t) => a + t.pnl, 0);
    const grossDown = Math.abs(
      closed.filter((t) => t.pnl <= 0).reduce((a, t) => a + t.pnl, 0),
    );
    const avgTrade = closed.reduce((a, t) => a + t.pnl_pct, 0) / closed.length;
    return {
      cagr,
      maxDd,
      profitFactor: grossDown > 0 ? grossUp / grossDown : 0,
      winRate: (wins.length / closed.length) * 100,
      avgTrade,
      tradesPerYear: closed.length / years,
    };
  }, []);

  const zoomed = !viewsNear(view, presetView);

  const legend =
    chartTab === "price" ? (
      <ChartLegend
        items={[
          { kind: "marker-buy", label: "long" },
          { kind: "marker-sell", label: "short" },
        ]}
      />
    ) : chartTab === "equity" ? (
      <ChartLegend items={[{ kind: "line", label: scale === "log" ? "Equity ($)" : "Return %" }]} />
    ) : chartTab === "drawdown" ? (
      <ChartLegend items={[{ kind: "line", label: "Drawdown %" }]} />
    ) : chartTab === "pnl" ? (
      <ChartLegend
        items={[
          { kind: "bar-up", label: "Realized %" },
          { kind: "bar-open", label: "Open (unrealized)" },
        ]}
      />
    ) : null;

  const equityPct = useMemo(() => {
    const base = D.equity[0].v;
    return D.equity.map((p) => ({ t: p.t, v: (p.v / base - 1) * 100 }));
  }, []);

  return (
    <div>
      <div className="mb-[1rem] flex items-center justify-between gap-[1rem]">
        <span className="ts-panel-label">{D.symbol} · {D.periodStart} → {D.periodEnd}</span>
        <button
          type="button"
          className="ts-reset"
          onClick={() =>
            runTearsheetPrint({
              documentTitle: "finance-tearsheet specimen — digiweb",
              setPrinting,
            })
          }
        >
          Download PDF
        </button>
      </div>

      <KpiStrip primary ariaLabel="Headline performance">
        <Kpi label="CAGR" value={<Toned v={kpis.cagr}>{fmtPct(kpis.cagr)}</Toned>} />
        <Kpi label="Max drawdown" value={<span className="is-neg">{fmtPct(kpis.maxDd)}</span>} />
        <Kpi label="Profit factor" value={fmtNum(kpis.profitFactor, 2)} />
        <Kpi label="Win rate" value={fmtPct(kpis.winRate)} />
        <Kpi label="Avg trade" value={<Toned v={kpis.avgTrade}>{fmtPct(kpis.avgTrade)}</Toned>} />
        <Kpi label="Trades / yr" value={fmtNum(kpis.tradesPerYear, 1)} />
      </KpiStrip>

      <section className="ts-panel ts-tab-stack">
        <div className="ts-panel-head">
          <SegToggle
            label="Chart"
            value={chartTab}
            onChange={setChartTab}
            options={[
              { value: "price", label: "Price" },
              { value: "equity", label: "Equity" },
              { value: "drawdown", label: "Drawdown" },
              { value: "pnl", label: "P&L" },
              { value: "matrix", label: "Matrix" },
            ]}
          />
          <div className="ts-panel-tools ts-chart-controls">
            {legend}
            {chartTab === "matrix" ? (
              <>
                <SegToggle
                  label="Matrix metric"
                  value={metric}
                  onChange={setMetric}
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
            )}
          </div>
        </div>
        <div className="ts-tab-content ts-tab-content-charts">
          {chartTab !== "matrix" && zoomed ? (
            <ChartResetButton onClick={() => applyLookback(lookback)} />
          ) : null}
          <div className="ts-tab-pane" hidden={chartTab !== "price"}>
            <div className="ts-chart">
              <CandlestickChart
                bars={D.bars}
                trades={D.trades}
                height={CHART_H}
                scale={chartScale === "log" ? "log" : "linear"}
                view={chartView}
                onView={setViewFromChart}
                fullSpan={D.fullSpan}
                resetView={presetView}
              />
            </div>
          </div>
          <div className="ts-tab-pane" hidden={chartTab !== "equity"}>
            <div className="ts-chart">
              {chartScale === "log" ? (
                <TimeSeries points={D.equity} height={CHART_H} scale="log" tone="accent" fmt={fmtCompact} view={chartView} onView={setViewFromChart} fullSpan={D.fullSpan} resetView={presetView} />
              ) : (
                <TimeSeries points={equityPct} height={CHART_H} scale="linear" tone="accent" fmt={(v) => fmtCompact(v) + "%"} view={chartView} onView={setViewFromChart} fullSpan={D.fullSpan} resetView={presetView} />
              )}
            </div>
          </div>
          <div className="ts-tab-pane" hidden={chartTab !== "drawdown"}>
            <div className="ts-chart">
              <TimeSeries points={D.drawdown} height={CHART_H} scale="linear" tone="down" zeroBaseline fmt={(v) => v.toFixed(0) + "%"} view={chartView} onView={setViewFromChart} fullSpan={D.fullSpan} resetView={presetView} />
            </div>
          </div>
          <div className="ts-tab-pane" hidden={chartTab !== "pnl"}>
            <div className="ts-chart">
              <TradeReturnChart
                bars={D.tradeReturnBars}
                height={CHART_H}
                view={chartView}
                onView={setViewFromChart}
                fullSpan={D.fullSpan}
                resetView={presetView}
              />
            </div>
          </div>
          <div className="ts-tab-pane ts-tab-pane-matrix" hidden={chartTab !== "matrix"}>
            <ReturnsMatrix points={D.equity} drawdown={D.drawdown} period={period} metric={metric} />
          </div>
        </div>
      </section>
    </div>
  );
}
