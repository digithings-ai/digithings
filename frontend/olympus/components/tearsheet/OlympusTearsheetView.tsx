'use client';

/**
 * Performance tear sheet — the hybrid, exportable surface for the single strategy
 * "Olympus": a live-NAV track + an Olympus-specific decision track-record track,
 * each degrading independently against its own empty-state predicate, plus the
 * absorbed Attribution diagnostics. One serif H1, one primary KPI strip (NOT a
 * MetricCard wall), two labeled .ts-panel tracks. Render surfaces come from the
 * shared finance-tearsheet family (#1463): pure-SVG charts print to PDF crisply
 * via runTearsheetPrint, enabled in ALL states. The tracks stay static
 * (interactive={false} — no hover tips, matching the shipped dashboard).
 * F5 token rule: signed financial values use up/red (toneClass); cyan --accent
 * is reserved for the equity line + header chrome.
 */
import type React from 'react';
import { useState } from 'react';
import {
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

export function OlympusTearsheetView({ data }: { data: OlympusTearsheet }) {
  const { live, decision } = data;
  const hasLiveCurve = data.navPoints >= 2;
  const hasTrackRecord = data.nResolved >= 1;

  // The SVG tracks are static (no zoom state), but the flushSync re-render that
  // runTearsheetPrint drives through this setter makes the recharts Attribution
  // section re-read the pinned light data-theme (useChartColors reads it at
  // render) before the print dialog opens — so paper output stays coherent.
  const [, setPrinting] = useState(false);

  const resolvedAlphasPct = data.decisionRows
    .filter((r) => r.status === 'resolved' && r.alpha != null)
    .map((r) => (r.alpha as number) * 100);

  return (
    <div className="ts-page">
      <header className="ts-header">
        <div>
          <h1 className="ts-h1">Olympus — AI-intelligence strategy</h1>
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

      {/* Primary KPI strip — single headline NAV + the decision differentiators (not a 2×4 wall) */}
      <KpiStrip ariaLabel="Headline performance">
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

      {/* Track 1 — Live NAV */}
      <section className="ts-panel">
        <div className="ts-panel-head">
          <span className="ts-panel-label">Live NAV</span>
        </div>
        {hasLiveCurve ? (
          <div className="ts-grid-2">
            <div className="ts-chart">
              <div className="ts-subhead">Equity curve</div>
              <TimeSeries points={live.equity_curve} scale="linear" tone="accent" fmt={fmtCompact} height={260} interactive={false} />
            </div>
            <div className="ts-chart">
              <div className="ts-subhead">Drawdown</div>
              <TimeSeries points={live.drawdown_curve} tone="down" fmt={(v) => `${v.toFixed(1)}%`} zeroBaseline height={260} interactive={false} />
            </div>
          </div>
        ) : (
          <p className="ts-panel-body">
            NAV {data.latestNav != null ? fmtNum(data.latestNav, 2) : 'n/a'} —{' '}
            {data.inceptionDate ? `live since ${data.inceptionDate}` : 'awaiting inception'} — equity curve accrues
            daily.
          </p>
        )}
      </section>

      {/* Track 2 — Decision track record (resolved decisions only) */}
      <section className="ts-panel">
        <div className="ts-panel-head">
          <span className="ts-panel-label">Decision track record</span>
        </div>
        {hasTrackRecord ? (
          <>
            <KpiStrip ariaLabel="Decision track-record metrics">
              <Kpi label="Hit rate" value={fmtPct(decision.hit_rate * 100)} />
              <Kpi label="Mean alpha" value={<Toned v={decision.mean_alpha_pct}>{fmtPct(decision.mean_alpha_pct)}</Toned>} />
              <Kpi label="Information ratio" value={fmtNum(decision.information_ratio, 2)} />
              <Kpi label="Sortino" value={fmtNum(decision.sortino_ratio, 2)} />
              <Kpi label="Decision max DD" value={<span className="is-neg">{fmtPct(decision.max_drawdown_pct)}</span>} />
              <Kpi label="N decisions" value={fmtNum(decision.n_trades)} />
            </KpiStrip>

            <div className="ts-grid-2">
              <div className="ts-chart">
                <div className="ts-subhead">Per-decision alpha</div>
                <SignedBars values={resolvedAlphasPct} fmt={(v) => `${v.toFixed(1)}%`} />
              </div>
              <div className="ts-chart">
                <div className="ts-subhead">Conviction calibration</div>
                <SignedBars values={decision.conviction_buckets.map((b) => b.mean_alpha_pct)} fmt={(v) => `${v.toFixed(1)}%`} />
                <div className="ts-bar-labels">
                  {decision.conviction_buckets.map((b) => (
                    <span key={b.conviction}>{BUCKET_LABEL[b.conviction] ?? b.conviction}</span>
                  ))}
                </div>
              </div>
            </div>

            <div className="ts-table-wrap">
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
                  {data.decisionRows.map((r, i) => (
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
          </>
        ) : (
          <p className="ts-panel-body">
            {data.nPending} decision{data.nPending === 1 ? '' : 's'} in flight — track record resolves as holding
            windows close.
          </p>
        )}
      </section>

      {/* Attribution diagnostics — absorbed from System (renders its own empty state) */}
      <section className="ts-panel">
        <div className="ts-panel-head">
          <span className="ts-panel-label">Attribution</span>
        </div>
        <AttributionTab attribution={data.attribution} date={data.attributionDate} />
      </section>

      <ul className="ts-notes">
        <li>Data source: nav_history + decision_log</li>
        <li>Generated {data.generatedAt}</li>
      </ul>
    </div>
  );
}
