'use client';

import type { ComponentType } from 'react';
import {
  pct, px, signed,
  type Benchmarks, type Book, type BookRow, type Brief, type KpisLive,
  type Ledger, type NavSeries, type Performance, type Portfolio,
} from '@/lib/dq-api';
import { Block } from './Block';
import { KpiGrid, Sparkline, tone } from './atoms';
import { DataTable, type Col } from './DataTable';
import { PORTFOLIO_BLOCKS } from './blocks-portfolio';

const num = (v: number | null | undefined, d = 2) => (v == null || !Number.isFinite(v) ? '—' : v.toFixed(d));

const bookCols: Col<BookRow>[] = [
  { key: 't', label: 'Ticker', cell: (r) => r.ticker },
  { key: 'w', label: 'Weight', num: true, cell: (r) => pct(r.scaled_weight_pct) },
  { key: 'e', label: 'Entry', num: true, cell: (r) => px(r.entry_price) },
  { key: 'm', label: 'Mark', num: true, cell: (r) => px(r.current_price) },
  { key: 'u', label: 'Unrealised', num: true, cell: (r) => signed(r.unrealized_pct), tone: (r) => tone(r.unrealized_pct) },
];

/** GET /allocations */
export function BookBlock() {
  return (
    <Block<Book> no="01" label="Book · allocation" route="/allocations" asOf={(d) => d.book_as_of}>
      {(d) => <DataTable rows={d.rows} cols={bookCols} rowKey={(r) => r.ticker} />}
    </Block>
  );
}

/** GET /portfolio */
export function PortfolioBlock() {
  return (
    <Block<Portfolio> no="02" label="Portfolio · envelope" route="/portfolio" asOf={(d) => d.book_as_of}>
      {(d) => (
        <>
          <KpiGrid items={[
            { label: 'NAV', value: num(d.nav_tip?.nav, 3), note: d.nav_tip?.contract },
            { label: 'Invested', value: pct(d.invested.kpi_pct), note: d.invested.definition },
            { label: 'Cash', value: pct(d.invested.cash_pct) },
            { label: 'Day', value: signed(d.nav_tip?.day_return_pct ?? null), tone: tone(d.nav_tip?.day_return_pct) },
            { label: 'Seam', value: d.seam ? (d.seam.crosses_nav_seam ? 'crosses' : 'clean') : '—', note: d.seam ? `${d.seam.lag_days}d ${d.seam.lag_direction}` : undefined },
          ]} />
          <DataTable
            rows={d.positions}
            rowKey={(r) => r.ticker}
            cols={[
              { key: 't', label: 'Position', cell: (r) => r.ticker },
              { key: 'w', label: 'Weight', num: true, cell: (r) => pct(r.weight_pct) },
              { key: 's', label: 'Scaled', num: true, cell: (r) => pct(r.scaled_weight_pct) },
            ]}
          />
        </>
      )}
    </Block>
  );
}

/** GET /brief */
export function BriefBlock() {
  return (
    <Block<Brief> no="03" label="Brief · scoreboard" route="/brief" asOf={(d) => d.book_as_of}>
      {(d) => (
        <KpiGrid items={[
          { label: 'NAV', value: num(d.nav_tip?.nav, 3), note: d.nav_tip?.contract },
          { label: 'Day', value: signed(d.day_return_pct), tone: tone(d.day_return_pct) },
          { label: 'Since inception', value: signed(d.since_inception_pct), tone: tone(d.since_inception_pct), note: d.since_inception_start_date ? `from ${d.since_inception_start_date}` : undefined },
          { label: 'Invested', value: pct(d.invested_pct) },
          { label: 'Overlay', value: d.overlay.badge, note: d.overlay.active ? `${signed(d.overlay.live_vs_mark_pct)} vs mark` : undefined },
          { label: 'Session events', value: String(d.session_events.length) },
        ]} />
      )}
    </Block>
  );
}

/** GET /performance */
export function PerformanceBlock() {
  return (
    <Block<Performance> no="04" label="Performance · tearsheet" route="/performance" asOf={(d) => d.nav.tip_date}>
      {(d) => (
        <>
          <KpiGrid items={[
            { label: 'Since inception', value: signed(d.metrics.since_inception_pct), tone: tone(d.metrics.since_inception_pct) },
            { label: `Excess vs ${d.benchmark.ticker}`, value: signed(d.metrics.excess_return_pct), tone: tone(d.metrics.excess_return_pct) },
            { label: 'Alpha', value: signed(d.metrics.alpha_pct), note: d.metrics.alpha_pct == null && d.metrics.overlap_days != null && d.metrics.overlap_days < 20 ? `${d.metrics.overlap_days} overlapping days (needs 20)` : undefined },
            { label: 'Info ratio', value: num(d.metrics.information_ratio) },
            { label: 'Beta', value: num(d.metrics.beta) },
          ]} />
          <div className="pad"><Sparkline values={d.nav.points.map((p) => p.index)} /></div>
        </>
      )}
    </Block>
  );
}

/** GET /kpis/live */
export function LiveKpisBlock() {
  return (
    <Block<KpisLive> no="05" label="Live marks · snapshot" route="/kpis/live" asOf={(d) => d.quote_date}>
      {(d) => (
        <>
          <KpiGrid items={[
            { label: 'Live vs mark', value: signed(d.live_vs_mark_pct), tone: tone(d.live_vs_mark_pct) },
            { label: 'Day (live)', value: signed(d.day_return_live_pct), tone: tone(d.day_return_live_pct) },
            { label: 'Since inception (live)', value: signed(d.since_inception_live_pct), tone: tone(d.since_inception_live_pct) },
            { label: 'Excess (live)', value: signed(d.excess_live_pct), tone: tone(d.excess_live_pct) },
            { label: 'Overlay', value: d.overlay_eligible ? 'eligible' : 'off' },
          ]} />
          <p className="note mute">live marks — not finalized accounting · {d.universe.join(' ')}</p>
        </>
      )}
    </Block>
  );
}

/** GET /nav-series */
export function NavSeriesBlock() {
  return (
    <Block<NavSeries> no="06" label="NAV · series" route="/nav-series" asOf={(d) => d.tip.date}>
      {(d) => (
        <>
          <KpiGrid items={[
            { label: 'Tip', value: num(d.points.at(-1)?.nav, 3), note: d.tip.contract },
            { label: 'Points', value: String(d.points.length) },
          ]} />
          <div className="pad"><Sparkline values={d.points.map((p) => p.nav)} height={80} /></div>
        </>
      )}
    </Block>
  );
}

/** GET /benchmarks */
export function BenchmarksBlock() {
  return (
    <Block<Benchmarks> no="07" label="Benchmarks · aligned" route="/benchmarks">
      {(d) => (
        <DataTable
          rows={d.universe}
          rowKey={(t) => t}
          cols={[
            { key: 't', label: 'Ticker', cell: (t) => t },
            { key: 'n', label: 'Points', num: true, cell: (t) => String(d.series[t]?.length ?? 0) },
            { key: 'c', label: 'Last close', num: true, cell: (t) => px(d.series[t]?.at(-1)?.close ?? null) },
            { key: 'l', label: 'Trend', cell: (t) => (d.series[t] ? <Sparkline values={d.series[t].map((p) => p.close)} height={14} /> : '—') },
          ]}
        />
      )}
    </Block>
  );
}

type Ev = Ledger['events'][number];
const evCols: Col<Ev>[] = [
  { key: 'd', label: 'Date', cell: (r) => r.date },
  { key: 't', label: 'Ticker', cell: (r) => r.ticker },
  { key: 'y', label: 'Type', cell: (r) => r.type },
  { key: 'f', label: 'Fill', num: true, cell: (r) => px(r.fill_price) },
  { key: 'w', label: 'Weight', num: true, cell: (r) => `${num(r.prev_weight_pct, 1)} → ${num(r.weight_pct, 1)}` },
  { key: 'r', label: 'Realised', num: true, cell: (r) => signed(r.realized_pct), tone: (r) => tone(r.realized_pct) },
];

/** GET /ledger */
export function LedgerBlock() {
  return (
    <Block<Ledger> no="08" label="Ledger · position events" route="/ledger?limit=50">
      {(d) => (
        <>
          <DataTable rows={d.events} cols={evCols} rowKey={(r, i) => `${r.date}:${r.ticker}:${r.type}:${i}`} empty="no events in range" />
          {d.next_cursor ? <p className="note mute">more events not shown — latest 50 only</p> : null}
        </>
      )}
    </Block>
  );
}

/** Block registry: every placeable block, keyed by id, bound to one API route. */
export type BlockDef = { id: string; title: string; route: string; Component: ComponentType };
export const BLOCKS: BlockDef[] = [
  ...PORTFOLIO_BLOCKS,
  { id: 'book', title: 'Book · allocation', route: '/allocations', Component: BookBlock },
  { id: 'portfolio', title: 'Portfolio · envelope', route: '/portfolio', Component: PortfolioBlock },
  { id: 'brief', title: 'Brief · scoreboard', route: '/brief', Component: BriefBlock },
  { id: 'performance', title: 'Performance · tearsheet', route: '/performance', Component: PerformanceBlock },
  { id: 'live', title: 'Live marks · snapshot', route: '/kpis/live', Component: LiveKpisBlock },
  { id: 'nav', title: 'NAV · series', route: '/nav-series', Component: NavSeriesBlock },
  { id: 'benchmarks', title: 'Benchmarks · aligned', route: '/benchmarks', Component: BenchmarksBlock },
  { id: 'ledger', title: 'Ledger · position events', route: '/ledger', Component: LedgerBlock },
];
