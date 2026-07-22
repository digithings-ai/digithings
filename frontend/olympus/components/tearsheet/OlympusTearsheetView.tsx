'use client';

/**
 * Performance tear sheet — the hybrid, exportable surface for the single strategy
 * "Olympus": a live-NAV track + an Olympus-specific decision track-record track,
 * each degrading independently against its own empty-state predicate, plus the
 * absorbed Attribution diagnostics. One command band, one primary KPI rail,
 * and three flat hairline-led tracks. Render surfaces come from the
 * shared finance-tearsheet family (#1463): pure-SVG charts print to PDF crisply
 * via runTearsheetPrint, enabled in ALL states. The tracks stay static
 * (interactive={false} — no hover tips, matching the shipped dashboard).
 * F5 token rule: signed financial values use up/red (toneClass); cyan --accent
 * is reserved for the equity line + header chrome.
 */
import type React from 'react';
import { useState } from 'react';
import {
  Button,
  Kpi,
  KpiStrip,
  SignedBars,
  TimeSeries,
  fmtCompact,
  fmtNum,
  fmtPct,
  runTearsheetPrint,
  toneClass,
} from '@digithings/web';
import AttributionTab from '@/components/observability/AttributionTab';
import { SignedConvictionBadge } from '@/components/shared/signed-conviction-badge';
import type { OlympusTearsheet } from './types';

function Toned({ v, children }: { v: number | null | undefined; children: React.ReactNode }) {
  const c = toneClass(v);
  return c ? <span className={c}>{children}</span> : <>{children}</>;
}

const BUCKET_LABEL: Record<number, string> = { 5: 'high', 3: 'medium', 1: 'low' };
const DEFAULT_ROW_LIMIT = 12;

export function OlympusTearsheetView({ data }: { data: OlympusTearsheet }) {
  const { live, decision } = data;
  const hasLiveCurve = data.navPoints >= 2;
  const hasTrackRecord = data.nResolved >= 1;

  // The SVG tracks are static (no zoom state), but the flushSync re-render that
  // runTearsheetPrint drives through this setter makes the recharts Attribution
  // section re-read the pinned light data-theme (useChartColors reads it at
  // render) before the print dialog opens — so paper output stays coherent.
  const [printing, setPrinting] = useState(false);

  // Decision table pagination: default to 12 most-recent rows on screen;
  // "Show N older" reveals all. When printing, render all rows so PDF stays complete.
  const [showAllDecisions, setShowAllDecisions] = useState(false);

  const resolvedAlphasPct = data.decisionRows
    .filter((r) => r.status === 'resolved' && r.alpha != null)
    .map((r) => (r.alpha as number) * 100);

  // Slice decision rows: show all during print or when user expanded, else 12 most recent
  const totalRows = data.decisionRows.length;
  const shouldShowAll = printing || showAllDecisions || totalRows <= DEFAULT_ROW_LIMIT;
  const visibleRows = shouldShowAll ? data.decisionRows : data.decisionRows.slice(-DEFAULT_ROW_LIMIT);
  const hiddenCount = totalRows - DEFAULT_ROW_LIMIT;

  return (
    <div className="ts-page">
      <section
        data-testid="performance-command-band"
        aria-label="Olympus performance summary"
        className="mb-5 border-y border-hair bg-surface"
      >
        <header className="ts-header m-0 border-0 px-5 py-5 md:px-6">
          <div>
            <span className="ts-kicker">AI-intelligence strategy</span>
            <h1 className="ts-h1 mb-2 tracking-normal">Olympus</h1>
            <div className="ts-meta">
              <span className="ts-meta-text">
                {data.inceptionDate ? `live since ${data.inceptionDate}` : 'awaiting inception'}
              </span>
              <span className="ts-meta-text">
                · {data.navPoints} NAV point{data.navPoints === 1 ? '' : 's'} · {data.nResolved} resolved /{' '}
                {data.nPending} pending
              </span>
            </div>
          </div>
          <div className="ts-header-actions">
            <button
              type="button"
              className="ts-btn"
              onClick={() =>
                runTearsheetPrint({ documentTitle: 'Olympus — AI-intelligence strategy', setPrinting })
              }
            >
              Download PDF
            </button>
          </div>
        </header>

        {/* Primary KPI rail — one divided ledger, not a card wall. */}
        <KpiStrip
          ariaLabel="Headline performance"
          className="ts-performance-kpis ts-performance-headline-kpis"
        >
          <Kpi
            label="NAV"
            value={data.latestNav != null ? fmtNum(data.latestNav, 2) : '—'}
            sub={
              data.latestNav != null
                ? `${live.net_profit_pct >= 0 ? '+' : ''}${fmtPct(live.net_profit_pct)} since inception`
                : 'awaiting inception'
            }
          />
          <Kpi
            label="Hit rate"
            value={hasTrackRecord ? fmtPct(decision.hit_rate * 100) : '—'}
            sub={hasTrackRecord ? 'positive-alpha share' : 'in flight'}
          />
          <Kpi
            label="Mean alpha"
            value={
              hasTrackRecord ? <Toned v={decision.mean_alpha_pct}>{fmtPct(decision.mean_alpha_pct)}</Toned> : '—'
            }
            sub={hasTrackRecord ? 'per resolved decision' : 'in flight'}
          />
          <Kpi
            label="Information ratio"
            value={hasTrackRecord ? fmtNum(decision.information_ratio, 2) : '—'}
            sub={hasTrackRecord ? 'mean α / σ(α)' : 'in flight'}
          />
        </KpiStrip>
      </section>

      {/* Track 1 — Live NAV */}
      <section className="ts-panel ts-performance-track">
        <div className="ts-panel-head m-0 px-4 py-3 md:px-5">
          <span className="ts-panel-label">Live NAV</span>
        </div>
        {hasLiveCurve ? (
          <div
            data-region="performance-chart-grid"
            data-layout="asymmetric"
            className="grid grid-cols-1 gap-0 lg:grid-cols-[minmax(0,1.55fr)_minmax(18rem,0.75fr)]"
          >
            <div className="min-w-0 p-4 md:p-5 lg:border-r lg:border-hair">
              <div className="ts-subhead">Equity curve</div>
              <div className="ts-chart h-[260px]">
                <TimeSeries points={live.equity_curve} scale="linear" tone="accent" fmt={fmtCompact} height={260} interactive={false} />
              </div>
            </div>
            <div className="min-w-0 border-t border-hair p-4 md:p-5 lg:border-t-0">
              <div className="ts-subhead">Drawdown</div>
              <div className="ts-chart h-[260px]">
                <TimeSeries points={live.drawdown_curve} tone="down" fmt={(v) => `${v.toFixed(1)}%`} zeroBaseline height={260} interactive={false} />
              </div>
            </div>
          </div>
        ) : (
          <p className="ts-panel-body px-4 py-5 md:px-5">
            NAV {data.latestNav != null ? fmtNum(data.latestNav, 2) : 'n/a'} —{' '}
            {data.inceptionDate ? `live since ${data.inceptionDate}` : 'awaiting inception'} — equity curve accrues
            daily.
          </p>
        )}
      </section>

      {/* Track 2 — Decision track record (resolved decisions only) */}
      <section
        data-region="decision-ledger"
        className="ts-panel ts-performance-track"
      >
        <div className="ts-panel-head m-0 px-4 py-3 md:px-5">
          <span className="ts-panel-label">Decision track record</span>
        </div>
        {hasTrackRecord ? (
          <>
            <KpiStrip
              ariaLabel="Decision track-record metrics"
              className="ts-performance-kpis ts-performance-decision-kpis"
            >
              <Kpi label="Hit rate" value={fmtPct(decision.hit_rate * 100)} />
              <Kpi label="Mean alpha" value={<Toned v={decision.mean_alpha_pct}>{fmtPct(decision.mean_alpha_pct)}</Toned>} />
              <Kpi label="Information ratio" value={fmtNum(decision.information_ratio, 2)} />
              <Kpi label="Sortino" value={fmtNum(decision.sortino_ratio, 2)} />
              <Kpi label="Decision max DD" value={<span className="is-neg">{fmtPct(decision.max_drawdown_pct)}</span>} />
              <Kpi label="N decisions" value={fmtNum(decision.n_trades)} />
            </KpiStrip>

            <div className="grid grid-cols-1 border-b border-hair lg:grid-cols-2">
              <div className="ts-chart min-w-0 p-4 md:p-5 lg:border-r lg:border-hair">
                <div className="ts-subhead">Per-decision alpha</div>
                <SignedBars values={resolvedAlphasPct} fmt={(v) => `${v.toFixed(1)}%`} />
              </div>
              <div className="ts-chart min-w-0 border-t border-hair p-4 md:p-5 lg:border-t-0">
                <div className="ts-subhead">Conviction calibration</div>
                <SignedBars values={decision.conviction_buckets.map((b) => b.mean_alpha_pct)} fmt={(v) => `${v.toFixed(1)}%`} />
                <div className="ts-bar-labels">
                  {decision.conviction_buckets.map((b) => (
                    <span key={b.conviction}>{BUCKET_LABEL[b.conviction] ?? b.conviction}</span>
                  ))}
                </div>
              </div>
            </div>

            <div className="ts-table-wrap max-h-[32rem] print:max-h-none print:overflow-visible">
              <table className="ts-table ts-trades">
                <thead>
                  <tr>
                    <th>Run date</th>
                    <th>Ticker</th>
                    <th>Stance</th>
                    <th>Conviction</th>
                    <th>Status</th>
                    <th className="ts-num">Alpha %</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map((r, i) => (
                    <tr key={`${r.ticker}-${r.run_date}-${i}`}>
                      <td>{r.run_date}</td>
                      <td>{r.ticker}</td>
                      <td>{r.conviction != null ? <SignedConvictionBadge value={r.conviction} /> : r.stance}</td>
                      <td>{r.conviction != null ? fmtNum(r.conviction) : '—'}</td>
                      <td>{r.status}</td>
                      <td className="ts-num">
                        {r.alpha != null ? <Toned v={r.alpha}>{fmtPct(r.alpha * 100)}</Toned> : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {totalRows > DEFAULT_ROW_LIMIT && !printing && (
              <div className="flex justify-center border-t border-hair p-4">
                <Button
                  variant="quiet"
                  onClick={() => setShowAllDecisions(!showAllDecisions)}
                  type="button"
                >
                  {showAllDecisions ? 'Show fewer' : `Show ${hiddenCount} older`}
                </Button>
              </div>
            )}
          </>
        ) : (
          <p className="ts-panel-body px-4 py-5 md:px-5">
            {data.nPending} decision{data.nPending === 1 ? '' : 's'} in flight — track record resolves as holding
            windows close.
          </p>
        )}
      </section>

      {/* Attribution diagnostics — absorbed from System (renders its own empty state) */}
      <section className="ts-panel ts-performance-track">
        <div className="ts-panel-head m-0 px-4 py-3 md:px-5">
          <span className="ts-panel-label">Attribution</span>
        </div>
        <div className="p-4 md:p-5">
          <AttributionTab attribution={data.attribution} date={data.attributionDate} embedded />
        </div>
      </section>

      <ul className="ts-notes">
        <li>Data source: nav_history + decision_log</li>
        <li>Generated {data.generatedAt}</li>
      </ul>
    </div>
  );
}
