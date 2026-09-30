'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { Download } from 'lucide-react';
import {
  MultiTimeSeries,
  ReturnsMatrix,
  annualizedVolPct,
  dailyReturnsFromEquity,
  fmtNum,
  relativeMetricsFromReturnSeries,
  runTearsheetPrint,
} from '@digithings/ui';
import {
  DivergingBars,
  IconButton,
  Label,
  SegmentedControl,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Stat,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableRowHeader,
} from '@digithings/ui/ui';
import type { TableRow as AttributionRow } from '@/lib/database.types';
import type { PerformanceTearsheet } from './types';
import { PortfolioContributionChart } from './PortfolioPerformanceCharts';
import { BookAttribution } from '@/components/portfolio/BookAttribution';
import { formatAllocationCategory } from '@/components/portfolio/tabs/palette-and-format';
import { ledgerHref } from '@/lib/portfolio-url-state';
import {
  metricsDivergenceBadgeLabel,
  navContractBadgeLabel,
  type PerformanceSsotMeta,
} from '@/lib/performance-ssot';
import {
  PERFORMANCE_RANGES,
  alignedBenchmark,
  drawdownFromReturns,
  navSummary,
  realizedBars,
  signedPct,
  unrealizedBars,
  windowReturns,
  type PerformanceRange,
} from '@/lib/portfolio-performance-view';

/** Sign tone for P&L-style figures only (returns, excess). */
const pnlTone = (v: number | null | undefined): 'up' | 'down' | 'mute' =>
  v == null || v === 0 ? 'mute' : v > 0 ? 'up' : 'down';

const pct = (n: number) => signedPct(n);

/**
 * Performance: one SVG finance-tearsheet page (NAV vs benchmark, drawdown,
 * returns calendar, contribution, attribution bridge, open/realized bars).
 * Stays SVG-only under `.ts-print-root` so PDF export keeps working.
 */
export function PerformanceTearsheetView({
  data,
  ssot = null,
  attribution = [],
}: {
  data: PerformanceTearsheet;
  /** Optional full SSOT meta from `getPerformanceBundle` (#3580). */
  ssot?: PerformanceSsotMeta | null;
  /** Latest current-book lookback rows (fail-soft; empty when unavailable). */
  attribution?: readonly AttributionRow<'position_attribution'>[];
}) {
  const [, setPrinting] = useState(false);
  const [range, setRange] = useState<PerformanceRange>('all');
  const [benchmarkTicker, setBenchmarkTicker] = useState(
    data.benchmarkComparisons.find((c) => c.ticker === 'SPY')?.ticker ?? data.benchmarkTicker
  );
  const benchmark = data.benchmarkComparisons.find((c) => c.ticker === benchmarkTicker) ?? null;

  const navWindow = useMemo(
    () => windowReturns(data.navSeries.map((p) => ({ date: p.date, returnPct: p.returnPct })), range),
    [data.navSeries, range]
  );
  const benchWindow = useMemo(
    () => alignedBenchmark(navWindow, benchmark?.series ?? []),
    [navWindow, benchmark]
  );
  const drawdown = useMemo(() => drawdownFromReturns(navWindow), [navWindow]);

  const isAll = range === 'all';
  const tip = (s: { returnPct: number }[]) => (s.length ? s[s.length - 1].returnPct : null);
  const portfolioReturnPct = isAll ? data.netReturnPct : tip(navWindow);
  const benchmarkReturnPct = isAll
    ? (benchmark?.returnPct ?? data.benchmarkReturnPct)
    : tip(benchWindow);

  const relative = useMemo(
    () =>
      relativeMetricsFromReturnSeries(
        portfolioReturnPct,
        benchmarkReturnPct,
        navWindow.map((p) => p.returnPct),
        benchWindow.map((p) => p.returnPct)
      ),
    [portfolioReturnPct, benchmarkReturnPct, navWindow, benchWindow]
  );
  const excessPct = relative.excessReturnPct ?? (isAll ? data.relativeReturnPct : null);

  const equity = useMemo(
    () => navWindow.map((p) => ({ t: p.date, v: 100 * (1 + p.returnPct / 100) })),
    [navWindow]
  );
  const volPct = useMemo(() => annualizedVolPct(dailyReturnsFromEquity(equity)), [equity]);

  const periodEnd = ssot?.navAsOf ?? data.metricsAsOf;
  const performancePeriod =
    data.inceptionDate && periodEnd ? `${data.inceptionDate}–${periodEnd}` : null;
  const sellCount = data.historicalHoldings.length;
  const navContract = ssot?.navContract ?? data.navContract ?? null;
  const metricsLagging = ssot?.metricsLagging ?? data.metricsLagging ?? false;
  const divergenceLabel = ssot
    ? metricsDivergenceBadgeLabel(ssot)
    : metricsLagging
      ? 'metrics lag'
      : null;

  const navSeries = [
    {
      id: 'portfolio',
      label: 'Portfolio',
      tone: 'accent' as const,
      points: navWindow.map((p) => ({ t: p.date, v: p.returnPct })),
    },
    ...(benchmark && benchWindow.length
      ? [
          {
            id: 'benchmark',
            label: benchmark.ticker,
            tone: 'mute' as const,
            dashed: true,
            points: benchWindow.map((p) => ({ t: p.date, v: p.returnPct })),
          },
        ]
      : []),
  ];
  const unrealized = unrealizedBars(data.currentHoldings);
  const realized = realizedBars(data.historicalHoldings);
  const matrixPoints = data.navSeries.map((p) => ({ t: p.date, v: p.nav }));

  return (
    <div className="ts-print-root flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-hair pb-3">
        <h1 className="font-display text-2xl font-normal text-ink">Performance</h1>
        <div className="flex flex-wrap items-center gap-3 print:hidden">
          {navContract && navContract !== 'empty' ? (
            <span
              data-testid="tearsheet-nav-contract-badge"
              className="font-mono text-[0.62rem] uppercase tracking-wider text-ink-mute"
            >
              {navContractBadgeLabel(navContract)}
            </span>
          ) : null}
          {divergenceLabel ? (
            <span
              data-testid="tearsheet-metrics-lag-badge"
              className="font-mono text-[0.62rem] uppercase tracking-wider text-warn"
            >
              {divergenceLabel}
              {ssot?.metricsAsOf ? ` · ${ssot.metricsAsOf}` : ''}
            </span>
          ) : null}
          <SegmentedControl
            dress="accent"
            aria-label="Performance range"
            options={PERFORMANCE_RANGES.map((r) => ({ value: r.value, label: r.label }))}
            value={range}
            onChange={setRange}
          />
          {data.benchmarkComparisons.length ? (
            <Label
              data-testid="global-benchmark-control"
              className="inline-flex w-auto items-center gap-2 font-mono text-[0.68rem] text-ink-mute"
            >
              <span className="uppercase tracking-wider">Benchmark</span>
              <Select
                value={benchmark?.ticker ?? null}
                onValueChange={(next) => {
                  if (typeof next === 'string') setBenchmarkTicker(next);
                }}
              >
                <SelectTrigger
                  aria-label="Comparison benchmark"
                  className="h-8 border-hair bg-surface px-2 font-mono text-[0.72rem] text-ink"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {data.benchmarkComparisons.map((c) => (
                    <SelectItem key={c.ticker} value={c.ticker}>
                      {c.ticker}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Label>
          ) : null}
          <IconButton
            aria-label="Download performance tear sheet as PDF"
            title="Download PDF"
            onClick={() => runTearsheetPrint({ documentTitle: 'digiquant performance', setPrinting })}
          >
            <Download size={17} aria-hidden />
          </IconButton>
        </div>
      </header>

      <section
        data-testid="performance-command-band"
        aria-label="Key performance metrics"
        className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-7"
      >
        <Stat
          label="Portfolio"
          value={signedPct(portfolioReturnPct)}
          deltaTone={pnlTone(portfolioReturnPct)}
          hint={isAll ? 'since inception' : `last ${range.toUpperCase()}`}
        />
        <Stat
          label={benchmark ? benchmark.ticker : 'Benchmark'}
          value={signedPct(benchmarkReturnPct)}
        />
        <Stat
          label="Excess"
          value={signedPct(excessPct)}
          hint={benchmark ? `Rp − ${benchmark.ticker}` : 'Rp − Rb'}
        />
        <Stat
          data-testid="performance-insight-band"
          label="Alpha"
          value={signedPct(relative.alphaPct)}
          hint="Jensen, β from daily overlap"
        />
        <Stat
          label="Info ratio"
          value={relative.informationRatio == null ? null : fmtNum(relative.informationRatio, 2)}
          hint="ann. excess / tracking error"
        />
        <Stat
          label="Max drawdown"
          value={navWindow.length > 1 ? signedPct(drawdown.maxDrawdownPct) : null}
          hint={drawdown.troughDate ? `trough ${drawdown.troughDate}` : undefined}
        />
        <Stat
          label="Volatility"
          value={volPct == null ? null : `${volPct.toFixed(1)}%`}
          hint="annualized, daily NAV"
        />
      </section>
      <p
        data-region="stamp"
        className="m-0 flex flex-wrap items-center gap-x-4 font-mono text-[0.65rem] uppercase tracking-wider text-ink-mute"
      >
        <span>{performancePeriod ? 'period' : periodEnd ? 'as of' : 'status'}</span>
        <strong className="font-medium text-accent">
          {performancePeriod ?? periodEnd ?? 'awaiting persisted metrics'}
        </strong>
        {ssot?.navAsOf && ssot.navAsOf !== data.metricsAsOf ? (
          <span data-testid="tearsheet-nav-as-of">nav tip {ssot.navAsOf}</span>
        ) : null}
      </p>

      <section
        aria-label="Cumulative return versus benchmark"
        className="border border-hair bg-surface p-4"
        data-testid="performance-nav-chart"
      >
        <h2 className="m-0 mb-2 font-display text-xl font-normal text-ink">
          Cumulative return{benchmark ? ` vs ${benchmark.ticker}` : ''}
        </h2>
        <MultiTimeSeries
          series={navSeries}
          height={300}
          fmt={(v) => `${v.toFixed(1)}%`}
          zeroBaseline
          interactive={false}
          ariaLabel="Portfolio cumulative return versus benchmark"
        />
        <p className="sr-only">{navSummary(navWindow, benchWindow, benchmark?.ticker ?? null)}</p>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section
          aria-label="Drawdown"
          className="border border-hair bg-surface p-4"
          data-testid="performance-drawdown"
        >
          <h2 className="m-0 mb-2 font-display text-xl font-normal text-ink">Drawdown</h2>
          <MultiTimeSeries
            series={[
              {
                id: 'drawdown',
                label: 'Drawdown',
                tone: 'down',
                fill: true,
                points: drawdown.series.map((p) => ({ t: p.date, v: p.returnPct })),
              },
            ]}
            height={200}
            fmt={(v) => `${v.toFixed(1)}%`}
            interactive={false}
            ariaLabel="Portfolio drawdown from running peak"
          />
          <p className="sr-only">
            Max drawdown {signedPct(drawdown.maxDrawdownPct)}
            {drawdown.troughDate ? ` on ${drawdown.troughDate}` : ''}; currently{' '}
            {signedPct(drawdown.currentPct)} below peak.
          </p>
        </section>
        <section
          aria-label="Monthly returns"
          className="border border-hair bg-surface p-4"
          data-testid="performance-returns-matrix"
        >
          <h2 className="m-0 mb-2 font-display text-xl font-normal text-ink">Monthly returns</h2>
          <ReturnsMatrix points={matrixPoints} period="monthly" />
        </section>
      </div>

      <PortfolioContributionChart
        points={data.contributionSeries}
        benchmark={benchmark}
        source={data.contributionSource}
        startsOn={data.contributionStartsOn}
      />

      <BookAttribution rows={attribution} />

      <section
        className="border border-hair bg-surface p-4"
        data-testid="open-positions-panel"
        aria-label="Open positions"
      >
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <h2 className="m-0 font-display text-xl font-normal text-ink">Open positions</h2>
          <span className="font-mono text-[0.62rem] uppercase tracking-wider text-ink-mute">
            open book · unrealized
          </span>
        </div>
        {unrealized.length ? (
          <DivergingBars
            items={unrealized.map((b) => ({
              id: b.id,
              label: b.label,
              value: b.value,
              display: pct(b.value),
            }))}
            sort="abs"
            label="Unrealized return by open position, percent"
          />
        ) : (
          <p className="m-0 py-8 text-center text-sm text-ink-mute">
            No open position performance is stored yet.
          </p>
        )}
        {data.currentHoldings.length ? (
          <div className="mt-3 max-h-[22rem] overflow-auto print:max-h-none print:overflow-visible">
            <Table
              density="compact"
              className="font-mono"
              aria-label="Open positions"
              data-testid="open-positions-table"
            >
              <TableHeader>
                <TableRow>
                  <TableHead>Holding</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead numeric>Weight</TableHead>
                  <TableHead numeric>Unrealized</TableHead>
                  <TableHead numeric>As of</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.currentHoldings.map((row) => (
                  <TableRow key={row.eventId ?? `${row.ticker}-${row.attributionDate ?? ''}`}>
                    <TableRowHeader className="font-semibold text-ink">{row.ticker}</TableRowHeader>
                    <TableCell className="text-ink-soft">
                      {formatAllocationCategory(row.category)}
                    </TableCell>
                    <TableCell numeric>
                      {row.weightPct != null ? `${row.weightPct.toFixed(1)}%` : '—'}
                    </TableCell>
                    <TableCell numeric>
                      {row.unrealizedReturnPct != null ? pct(row.unrealizedReturnPct) : '—'}
                    </TableCell>
                    <TableCell numeric className="text-ink-mute">
                      {row.attributionDate ?? '—'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : null}
      </section>

      <section
        data-testid="ledger-doorway"
        aria-label="Realized exits and trims"
        className="border border-hair bg-surface p-4"
      >
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="m-0 font-display text-xl font-normal text-ink">Realized</h2>
          <span className="font-mono text-[0.62rem] uppercase tracking-wider text-ink-mute">
            {sellCount > 0
              ? `${sellCount} recorded ${sellCount === 1 ? 'exit or trim' : 'exits & trims'}`
              : 'No recorded exits or trims'}
            {' · '}
            <Link
              href={ledgerHref()}
              className="font-medium text-accent hover:underline print:hidden"
              data-testid="ledger-doorway-link"
            >
              Open ledger
            </Link>
          </span>
        </div>
        {realized.length ? (
          <DivergingBars
            items={realized.map((b) => ({
              id: b.id,
              label: b.label,
              value: b.value,
              display: pct(b.value),
            }))}
            sort="abs"
            label="Realized return by exit or trim, percent"
          />
        ) : null}
      </section>

      <p className="m-0 text-right font-mono text-[0.62rem] text-ink-mute">
        Holdings as of {data.holdingsAsOf ?? '—'}
      </p>
    </div>
  );
}

/** @deprecated Use PerformanceTearsheetView. One-release alias (ADR-0026 wave 3). */
export const DashboardTearsheetView = PerformanceTearsheetView;
