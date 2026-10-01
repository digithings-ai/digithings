'use client';

import type { ComponentType } from 'react';
import { pct, px, signed, type Attribution, type Book, type BookRow, type Brief, type CashLedger, type NavSeries, type Performance, type Theses } from '@/lib/dq-api';
import { Block } from './Block';
import { KpiGrid, tone } from './atoms';
import { DataTable, type Col } from './DataTable';
import { Badge, BulletList, Prose, StateBlock, type BadgeTone } from './ui';

const num = (v: number | null | undefined, d = 2) => (v == null || !Number.isFinite(v) ? '—' : v.toFixed(d));
const usd = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
const bp = (v: number | null | undefined) => {
  if (v == null || !Number.isFinite(v)) return '—';
  const r = Math.round(v);
  return `${r > 0 ? '+' : r < 0 ? '−' : ''}${Math.abs(r)} bp`;
};
const withheld = (what: string) => <StateBlock kind="empty" title="Withheld." why={`${what} is not in the response yet; nothing is estimated.`} />;

/* ---- Holdings: grouped by sleeve, bar weights, cash and total rows ---- */
type HRow = { kind: 'grp' | 'pos' | 'cash' | 'total'; key: string; r?: BookRow; label?: string; w?: number | null; v?: number | null };

function holdingsRows(d: Book): HRow[] {
  const pos = d.rows.filter((r) => !r.is_cash);
  const groups = new Map<string, BookRow[]>();
  for (const r of pos) groups.set(r.sleeve ?? 'Unassigned', [...(groups.get(r.sleeve ?? 'Unassigned') ?? []), r]);
  const out: HRow[] = [];
  for (const [sleeve, rs] of groups) {
    out.push({ kind: 'grp', key: `g:${sleeve}`, label: `${sleeve} · ${rs.length} ${rs.length === 1 ? 'name' : 'names'}`, w: rs.every((r) => Number.isFinite(r.scaled_weight_pct)) ? rs.reduce((a, r) => a + r.scaled_weight_pct, 0) : null });
    rs.forEach((r) => out.push({ kind: 'pos', key: r.ticker, r }));
  }
  if (d.cash_value != null) out.push({ kind: 'cash', key: 'cash', label: 'Cash', v: d.cash_value });
  if (d.book_value != null) out.push({ kind: 'total', key: 'total', label: 'Book total', v: d.book_value });
  return out;
}

const holdCols: Col<HRow>[] = [
  { key: 't', label: 'Ticker', cell: (h) => (h.kind === 'pos' ? h.r!.ticker : h.label) },
  { key: 'n', label: 'Name', wrap: true, cell: (h) => (h.kind === 'pos' ? h.r!.name ?? '—' : '') },
  { key: 'w', label: 'Weight', num: true, bar: (h) => (h.kind === 'pos' ? h.r!.scaled_weight_pct : null), cell: (h) => (h.kind === 'pos' ? pct(h.r!.scaled_weight_pct) : h.w != null ? pct(h.w) : '') },
  { key: 's', label: 'Shares', num: true, cell: (h) => (h.kind === 'pos' ? num(h.r!.shares, 0) : '') },
  { key: 'm', label: 'Mark', num: true, cell: (h) => (h.kind === 'pos' ? (h.r!.current_price == null ? <Badge tone="unavailable">unavailable</Badge> : px(h.r!.current_price)) : '') },
  { key: 'v', label: 'Value', num: true, cell: (h) => (h.kind === 'pos' ? usd(h.r!.value) : h.v != null ? usd(h.v) : '') },
  { key: 'd', label: 'Day', num: true, cell: (h) => (h.kind === 'pos' ? signed(h.r!.day_return_pct ?? null) : ''), tone: (h) => (h.kind === 'pos' ? tone(h.r!.day_return_pct) : undefined) },
  { key: 'th', label: 'Thesis', cell: (h) => (h.kind === 'pos' ? h.r!.thesis_id ?? '—' : '') },
];

/** GET /allocations — holdings table. */
export function HoldingsBlock() {
  return (
    <Block<Book> no="09" label="Holdings · by sleeve" route="/allocations" asOf={(d) => d.book_as_of}>
      {(d) => <DataTable rows={holdingsRows(d)} cols={holdCols} rowKey={(h) => h.key} variant={(h) => (h.kind === 'grp' ? 'grp' : h.kind === 'total' ? 'total' : undefined)} empty="no positions" />}
    </Block>
  );
}

/** GET /allocations — sleeve exposure. */
export function SleevesBlock() {
  return (
    <Block<Book> no="10" label="Exposure · sleeve" route="/allocations" asOf={(d) => d.book_as_of}>
      {(d) => (d.sleeves?.length ? (
        <DataTable
          rows={d.sleeves}
          rowKey={(s) => s.sleeve}
          cols={[
            { key: 's', label: 'Sleeve', cell: (s) => s.sleeve },
            { key: 'n', label: 'Names', num: true, cell: (s) => String(s.names) },
            { key: 'w', label: 'Weight', num: true, bar: (s) => s.weight_pct, cell: (s) => pct(s.weight_pct) },
          ]}
        />
      ) : withheld('sleeves'))}
    </Block>
  );
}

/** GET /allocations — day movers (sorted by day return; rows without one are left out, not zeroed). */
export function MoversBlock() {
  return (
    <Block<Book> no="11" label="Book · movers" route="/allocations" asOf={(d) => d.book_as_of}>
      {(d) => {
        const rows = d.rows.filter((r) => !r.is_cash && Number.isFinite(r.day_return_pct)).sort((a, b) => (b.day_return_pct as number) - (a.day_return_pct as number));
        return rows.length ? (
          <DataTable
            rows={rows}
            rowKey={(r) => r.ticker}
            cols={[
              { key: 't', label: 'Ticker', cell: (r) => r.ticker },
              { key: 'm', label: 'Mark', num: true, cell: (r) => px(r.current_price) },
              { key: 'd', label: 'Day', num: true, cell: (r) => signed(r.day_return_pct ?? null), tone: (r) => tone(r.day_return_pct) },
            ]}
          />
        ) : withheld('day return');
      }}
    </Block>
  );
}

/** GET /brief — decision text. */
export function DecisionBlock() {
  return (
    <Block<Brief> no="12" label="Decision" route="/brief" asOf={(d) => d.decision?.run_date}>
      {(d) => (d.decision ? <Prose lead={d.decision.lead}>{d.decision.body ? <p>{d.decision.body}</p> : null}</Prose> : withheld('decision'))}
    </Block>
  );
}

/** GET /brief — what could break the view. */
export function RisksBlock() {
  return (
    <Block<Brief> no="13" label="What could break the view" route="/brief" asOf={(d) => d.book_as_of}>
      {(d) => (d.risks?.length ? <BulletList items={d.risks} /> : withheld('risks'))}
    </Block>
  );
}

const stateTone: Record<string, BadgeTone> = { active: 'ok', watch: 'wip', exited: 'plain' };

/** GET /theses — thesis list. */
export function ThesesBlock() {
  return (
    <Block<Theses> no="14" label="Theses" route="/theses">
      {(d) => (
        <>
          <p className="meta pad">Active <b>{d.counts?.active ?? '—'}</b> Watch <b>{d.counts?.watch ?? '—'}</b> Exited <b>{d.counts?.exited ?? '—'}</b></p>
          <DataTable
            rows={d.theses}
            rowKey={(t) => t.id}
            cols={[
              { key: 'i', label: 'Id', cell: (t) => t.id },
              { key: 'n', label: 'Thesis', wrap: true, cell: (t) => t.name },
              { key: 's', label: 'State', cell: (t) => <Badge tone={stateTone[t.state] ?? 'plain'}>{t.state}</Badge> },
              { key: 'v', label: 'Vehicles', cell: (t) => (t.vehicles?.length ? t.vehicles.join(' ') : '—') },
              { key: 'e', label: 'Evidence', wrap: true, cell: (t) => t.evidence ?? '—' },
              { key: 'k', label: 'Kill condition', wrap: true, cell: (t) => t.kill_condition ?? '—' },
            ]}
          />
        </>
      )}
    </Block>
  );
}

/** GET /theses?needs_resolution=1 — signals to resolve. */
export function SignalsBlock() {
  return (
    <Block<Theses> no="15" label="Signals to resolve" route="/theses?needs_resolution=1">
      {(d) => (
        <DataTable
          rows={d.theses}
          rowKey={(t) => t.id}
          empty="nothing to resolve"
          cols={[
            { key: 'i', label: 'Id', cell: (t) => t.id },
            { key: 'n', label: 'Thesis', wrap: true, cell: (t) => t.name },
            { key: 's', label: 'State', cell: (t) => <Badge tone={stateTone[t.state] ?? 'plain'}>{t.state}</Badge> },
            { key: 'o', label: 'Note', wrap: true, cell: (t) => t.note ?? '—' },
          ]}
        />
      )}
    </Block>
  );
}

/** GET /attribution — sleeve and name contribution in bp. */
export function AttributionBlock() {
  return (
    <Block<Attribution> no="16" label="Attribution" route="/attribution" asOf={(d) => `${d.window.start} → ${d.window.end}`}>
      {(d) => (
        <>
          <DataTable
            rows={d.sleeves}
            rowKey={(s) => s.sleeve}
            cols={[
              { key: 's', label: 'Sleeve', cell: (s) => s.sleeve },
              { key: 'c', label: 'Contribution', num: true, cell: (s) => bp(s.contribution_bp), tone: (s) => tone(s.contribution_bp) },
            ]}
          />
          <DataTable
            rows={d.names}
            rowKey={(n) => n.ticker}
            cols={[
              { key: 't', label: 'Name', cell: (n) => n.ticker },
              { key: 's', label: 'Sleeve', cell: (n) => n.sleeve ?? '—' },
              { key: 'c', label: 'Contribution', num: true, cell: (n) => bp(n.contribution_bp), tone: (n) => tone(n.contribution_bp) },
            ]}
          />
        </>
      )}
    </Block>
  );
}

/** GET /performance — drawdown. */
export function DrawdownBlock() {
  return (
    <Block<Performance> no="17" label="Drawdown" route="/performance" asOf={(d) => d.nav.tip_date}>
      {(d) => (d.drawdown ? (
        <KpiGrid items={[
          { label: 'Max drawdown', value: signed(d.drawdown.max_pct), tone: tone(d.drawdown.max_pct), note: d.drawdown.peak_date && d.drawdown.trough_date ? `${d.drawdown.peak_date} → ${d.drawdown.trough_date}` : undefined },
          { label: 'Current drawdown', value: signed(d.drawdown.current_pct), tone: tone(d.drawdown.current_pct) },
        ]} />
      ) : withheld('drawdown'))}
    </Block>
  );
}

/** GET /nav-series — most recent NAV points (date-sorted, last 60), newest first. */
export function NavTableBlock() {
  return (
    <Block<NavSeries> no="18" label="NAV · by date" route="/nav-series" asOf={(d) => d.tip.date}>
      {(d) => (
        <DataTable
          rows={[...d.points].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 60)}
          rowKey={(p, i) => `${p.date}:${i}`}
          cols={[
            { key: 'd', label: 'Date', cell: (p) => p.date },
            { key: 'n', label: 'NAV', num: true, cell: (p) => num(p.nav, 3) },
            { key: 'r', label: 'Day', num: true, cell: (p) => signed(p.day_return_pct), tone: (p) => tone(p.day_return_pct) },
            { key: 'c', label: 'Contract', cell: (p) => p.contract },
          ]}
        />
      )}
    </Block>
  );
}

/** GET /ledger/cash — cash movements. */
export function CashLedgerBlock() {
  return (
    <Block<CashLedger> no="19" label="Cash ledger" route="/ledger/cash">
      {(d) => (
        <DataTable
          rows={d.entries}
          rowKey={(e, i) => `${e.date}:${e.kind}:${i}`}
          empty="no cash movements"
          cols={[
            { key: 'd', label: 'Date', cell: (e) => e.date },
            { key: 'k', label: 'Kind', cell: (e) => e.kind },
            { key: 'a', label: 'Amount', num: true, cell: (e) => usd(e.amount), tone: (e) => tone(e.amount) },
            { key: 'b', label: 'Balance', num: true, cell: (e) => usd(e.balance) },
          ]}
        />
      )}
    </Block>
  );
}

export type PortfolioBlockDef = { id: string; title: string; route: string; Component: ComponentType };
export const PORTFOLIO_BLOCKS: PortfolioBlockDef[] = [
  { id: 'holdings', title: 'Holdings · by sleeve', route: '/allocations', Component: HoldingsBlock },
  { id: 'sleeves', title: 'Exposure · sleeve', route: '/allocations', Component: SleevesBlock },
  { id: 'movers', title: 'Book · movers', route: '/allocations', Component: MoversBlock },
  { id: 'decision', title: 'Decision', route: '/brief', Component: DecisionBlock },
  { id: 'risks', title: 'What could break the view', route: '/brief', Component: RisksBlock },
  { id: 'theses', title: 'Theses', route: '/theses', Component: ThesesBlock },
  { id: 'signals', title: 'Signals to resolve', route: '/theses?needs_resolution=1', Component: SignalsBlock },
  { id: 'attribution', title: 'Attribution', route: '/attribution', Component: AttributionBlock },
  { id: 'drawdown', title: 'Drawdown', route: '/performance', Component: DrawdownBlock },
  { id: 'navtable', title: 'NAV · by date', route: '/nav-series', Component: NavTableBlock },
  { id: 'cash', title: 'Cash ledger', route: '/ledger/cash', Component: CashLedgerBlock },
];
