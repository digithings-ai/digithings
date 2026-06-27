"use client";
/**
 * Renders a strategy tearsheet from the unified TearsheetData JSON. Fetches
 * /strategies/<slug>.json at runtime (keeps the large series out of the static
 * HTML), then renders KPIs, the All/Long/Short breakdown, theme-aware SVG charts
 * (equity with a log/linear scale toggle, drawdown, per-trade and cumulative
 * P&L — all sharing one zoom/pan time window), a returns heatmap, and the trade
 * log. "Download PDF" uses the browser's print-to-PDF.
 */
import { useEffect, useMemo, useState } from "react";
import {
  TimeSeries,
  ComboPnl,
  ReturnsMatrix,
  SegToggle,
  type Scale,
  type PnlScale,
  type ReturnsPeriod,
  type ViewWindow,
} from "./charts";
import { fmtCompact, fmtMoney, fmtNum, fmtPct, toneClass } from "./format";
import { avgTradePct, cagrPct, calmar, tradesPerYear } from "./stats";
import { type TearsheetBreakdown, type TearsheetData } from "./types";

function Kpi({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="ts-kpi">
      <span className="ts-kpi-label">{label}</span>
      <span className="ts-kpi-value">{value}</span>
      {sub ? <span className="ts-kpi-sub">{sub}</span> : null}
    </div>
  );
}

function Toned({ v, children }: { v: number | null | undefined; children: React.ReactNode }) {
  const c = toneClass(v);
  return c ? <span className={c}>{children}</span> : <>{children}</>;
}

function Breakdown({ d }: { d: TearsheetData }) {
  const cols: TearsheetBreakdown[] = [d.overall, d.long, d.short];
  const rows: { label: string; render: (b: TearsheetBreakdown) => React.ReactNode }[] = [
    { label: "Closed trades", render: (b) => fmtNum(b.trades) },
    { label: "Net profit", render: (b) => <Toned v={b.net_profit}>{fmtMoney(b.net_profit)}</Toned> },
    { label: "Net profit %", render: (b) => fmtPct(b.net_profit_pct) },
    { label: "Gross profit", render: (b) => fmtMoney(b.gross_profit) },
    { label: "Gross loss", render: (b) => fmtMoney(b.gross_loss) },
    { label: "Percent profitable", render: (b) => fmtPct(b.percent_profitable) },
    { label: "Profit factor", render: (b) => fmtNum(b.profit_factor, 2) },
    { label: "Avg trade", render: (b) => <Toned v={b.avg_trade}>{fmtMoney(b.avg_trade)}</Toned> },
  ];
  return (
    <table className="ts-table ts-breakdown">
      <thead>
        <tr><th>Metric</th><th>All</th><th>Long</th><th>Short</th></tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.label}>
            <th scope="row">{r.label}</th>
            {cols.map((b, i) => <td key={i}>{r.render(b)}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function TearsheetView({ slug }: { slug: string }) {
  const [data, setData] = useState<TearsheetData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [scale, setScale] = useState<Scale>("log");
  const [pnlScale, setPnlScale] = useState<PnlScale>("log");
  const [period, setPeriod] = useState<ReturnsPeriod>("monthly");
  // One shared x-window (date-span fraction) drives all three time-series charts.
  const [view, setView] = useState<ViewWindow>({ lo: 0, hi: 1 });

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

  const cumPts = useMemo(() => {
    if (!data) return [];
    let cum = 0;
    return data.trades.map((t) => { cum += t.pnl; return { t: t.exit_date, v: cum }; });
  }, [data]);

  // Canonical full date span — the equity curve endpoints. Passed to every
  // time-series chart so the shared {lo,hi} fraction maps to the SAME calendar
  // window everywhere (equity, drawdown, and the combo's trade filter), even
  // though the series sample at different cadences.
  const fullSpan = useMemo<[string, string] | undefined>(() => {
    if (!data || data.equity_curve.length === 0) return undefined;
    return [data.equity_curve[0].t, data.equity_curve[data.equity_curve.length - 1].t];
  }, [data]);

  // Mean per-trade return — more representative than a dollar average, which is
  // dominated by late compounding trades.
  const avgTrade = useMemo(() => avgTradePct(data ? data.trades.map((t) => t.pnl_pct) : []), [data]);

  if (err) return <p className="ts-status ts-status-error">{err}</p>;
  if (!data) return <p className="ts-status">Loading tearsheet…</p>;

  // Annualized return — computed once and reused for the headline KPI and the
  // Calmar fallback when a Sharpe ratio is not available.
  const cagr = cagrPct(data.initial_capital, data.final_equity, data.period_start, data.period_end);
  const hasSharpe = data.sharpe_ratio !== null && data.sharpe_ratio !== undefined;

  // Zoom/pan chrome: a Reset appears once the window is narrowed from full range.
  const zoomed = view.lo > 0 || view.hi < 1;
  const resetView = () => setView({ lo: 0, hi: 1 });
  const ResetBtn = zoomed ? (
    <button type="button" className="ts-reset" onClick={resetView} aria-label="Reset zoom to full range">
      Reset
    </button>
  ) : null;

  const notes = [
    ...(data.data_source ? [`Data source: ${data.data_source}`] : []),
    // Drop the engine brand from the persisted notes (kept out of the chrome).
    ...data.notes.map((n) => n.replace(/NautilusTrader\s+backtest,?\s*/gi, "").trim()).filter(Boolean),
    ...(data.generated_at ? [`Generated ${data.generated_at}`] : []),
  ];

  return (
    <div>
      <header className="ts-header">
        <div className="ts-header-main">
          <a href="/strategies" className="ts-back">← Strategy library</a>
          <span className="ts-kicker">// tearsheet</span>
          <h1 className="ts-h1">{data.strategy}</h1>
          <div className="ts-meta">
            <span className="ts-chip">{data.symbol}</span>
            <span className="ts-meta-text">{data.period_start} → {data.period_end} · {fmtNum(data.bars)} bars</span>
          </div>
        </div>
        <div className="ts-header-actions">
          <button
            className="btn btn-ghost btn-sm btn-icon"
            type="button"
            onClick={() => window.print()}
            aria-label="Download tearsheet as PDF"
            title="Download PDF"
          >
            <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 3v12m0 0l-4-4m4 4l4-4M5 21h14" />
            </svg>
          </button>
        </div>
      </header>

      <section className="ts-kpis" aria-label="Headline metrics">
        <Kpi label="Annualized (CAGR)" value={<Toned v={cagr}>{fmtPct(cagr)}</Toned>} sub="compound annual growth" />
        {hasSharpe ? (
          <Kpi label="Risk-adjusted" value={fmtNum(data.sharpe_ratio, 2)} sub="Sharpe · annualized" />
        ) : (
          <Kpi label="Risk-adjusted" value={fmtNum(calmar(cagr, data.max_drawdown_pct), 2)} sub="Calmar · CAGR / max DD" />
        )}
        <Kpi label="Avg trade" value={<Toned v={avgTrade}>{fmtPct(avgTrade)}</Toned>} sub="per closed trade" />
        <Kpi label="Trades / year" value={fmtNum(tradesPerYear(data.total_trades, data.period_start, data.period_end), 1)} sub={`${data.total_trades} total`} />
        <Kpi label="Max drawdown" value={<span className="is-neg">{fmtPct(data.max_drawdown_pct)}</span>} sub="mark-to-market" />
        <Kpi label="Win rate" value={fmtPct(data.win_rate_pct)} sub={`${data.total_trades} trades`} />
        <Kpi label="Profit factor" value={fmtNum(data.profit_factor, 2)} sub="gross win / gross loss" />
        <Kpi label="Total return" value={<Toned v={data.net_profit_pct}>{fmtPct(data.net_profit_pct)}</Toned>} sub={`${fmtMoney(data.initial_capital)} → ${fmtMoney(data.final_equity)}`} />
      </section>

      <section className="ts-panel">
        <div className="ts-panel-head">
          <span className="ts-panel-label">Equity curve</span>
          <div className="ts-panel-tools">
            <span className="ts-hint">scroll to zoom · drag to pan</span>
            {ResetBtn}
            <label className="ts-scale">
              <span>Scale</span>
              <SegToggle
                label="Equity curve scale"
                value={scale}
                onChange={setScale}
                options={[
                  { value: "linear", label: "Linear" },
                  { value: "log", label: "Log" },
                ]}
              />
            </label>
          </div>
        </div>
        <div className="ts-chart">
          <TimeSeries points={data.equity_curve} height={340} scale={scale} tone="accent" fmt={fmtCompact} view={view} onView={setView} fullSpan={fullSpan} />
        </div>
      </section>

      <section className="ts-panel">
        <div className="ts-panel-head">
          <span className="ts-panel-label">Drawdown (underwater)</span>
          {ResetBtn}
        </div>
        <div className="ts-chart">
          <TimeSeries points={data.drawdown_curve} height={220} scale="linear" tone="down" zeroBaseline fmt={(v) => v.toFixed(0) + "%"} view={view} onView={setView} fullSpan={fullSpan} />
        </div>
      </section>

      <section className="ts-panel">
        <div className="ts-panel-head"><span className="ts-panel-label">Performance — All / Long / Short</span></div>
        <div className="ts-table-wrap"><Breakdown d={data} /></div>
      </section>

      <section className="ts-panel">
        <div className="ts-panel-head">
          <span className="ts-panel-label">Trade P&amp;L — per-trade &amp; cumulative</span>
          <div className="ts-panel-tools">
            {ResetBtn}
            <label className="ts-scale">
              <span>Cumulative</span>
              <SegToggle
                label="Cumulative P&L scale"
                value={pnlScale}
                onChange={setPnlScale}
                options={[
                  { value: "log", label: "Log $" },
                  { value: "pct", label: "%" },
                ]}
              />
            </label>
          </div>
        </div>
        <div className="ts-chart">
          <ComboPnl pnl={data.trades.map((t) => t.pnl)} cumulative={cumPts} initialCapital={data.initial_capital} scale={pnlScale} height={300} view={view} onView={setView} fullSpan={fullSpan} />
        </div>
      </section>

      <section className="ts-panel">
        <div className="ts-panel-head">
          <span className="ts-panel-label">Returns</span>
          <label className="ts-scale">
            <span>Period</span>
            <SegToggle
              label="Returns matrix period"
              value={period}
              onChange={setPeriod}
              options={[
                { value: "monthly", label: "Monthly" },
                { value: "quarterly", label: "Quarterly" },
                { value: "annual", label: "Annual" },
              ]}
            />
          </label>
        </div>
        <ReturnsMatrix points={data.equity_curve} period={period} />
      </section>

      <section className="ts-panel">
        <div className="ts-panel-head"><span className="ts-panel-label">Trade log</span></div>
        <div className="ts-table-wrap ts-table-scroll">
          <table className="ts-table ts-trades">
            <thead>
              <tr>
                <th>#</th><th>Dir</th><th>Entry signal</th><th>Entry date</th>
                <th className="ts-num">Entry px</th><th>Exit date</th><th className="ts-num">Exit px</th>
                <th className="ts-num">P&amp;L</th><th className="ts-num">P&amp;L %</th><th>Exit</th>
              </tr>
            </thead>
            <tbody>
              {data.trades.map((t) => (
                <tr key={t.n}>
                  <td>{t.n}</td>
                  <td><span className={`ts-dir ts-dir-${t.direction}`}>{t.direction}</span></td>
                  <td>{t.entry_label}</td>
                  <td>{t.entry_date}</td>
                  <td className="ts-num">{fmtMoney(t.entry_price)}</td>
                  <td>{t.exit_date}</td>
                  <td className="ts-num">{fmtMoney(t.exit_price)}</td>
                  <td className={`ts-num ${toneClass(t.pnl)}`}>{fmtMoney(t.pnl)}</td>
                  <td className={`ts-num ${toneClass(t.pnl_pct)}`}>{fmtPct(t.pnl_pct)}</td>
                  <td>{t.exit_reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {notes.length ? (
        <ul className="ts-notes">{notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
      ) : null}
    </div>
  );
}
