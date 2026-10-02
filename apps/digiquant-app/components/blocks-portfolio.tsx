'use client';

import { useEffect, useState, type ComponentType } from 'react';
import { dqGet, pct, px, signed, type Attribution, type Book, type BookRow, type CashLedger, type Envelope, type NavSeries, type Theses } from '@/lib/dq-api';
import { Block } from './Block';
import { KpiGrid, tone } from './atoms';
import { AreaChart } from './charts-time';
import { DataTable, type Col } from './DataTable';
import { Drawer } from './Drawer';
import { Badge, BulletList, Prose, StateBlock, type BadgeTone } from './ui';

const num = (v: number | null | undefined, d = 2) => (v == null || !Number.isFinite(v) ? '—' : v.toFixed(d));
const usd = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? '—' : v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
const bp = (v: number | null | undefined) => {
  if (v == null || !Number.isFinite(v)) return '—';
  const r = Math.round(v);
  return `${r > 0 ? '+' : r < 0 ? '−' : ''}${Math.abs(r)} bp`;
};
const withheld = (what: string) => <StateBlock kind="empty" title="Withheld." why={`${what} is not in the response yet; nothing is estimated.`} />;

type Dossier = {
  ticker: string;
  thesis: { id: string | null; name: string | null; state: string | null } | null;
  vehicles: string[];
  pnl: { unrealized_pct: number | null };
  stop: number | null;
  target: number | null;
  events: { date: string | null; type: string | null }[];
  documents: { title: string | null }[];
};

type Drawdown = {
  max_pct: number | null;
  current_pct: number | null;
  peak_date: string | null;
  trough_date: string | null;
  series: { t: string; v: number | null }[];
  episodes: { depth_pct: number | null; start: string | null; trough: string | null; recovery: string | null; days: number | null }[];
};

type DecisionPayload = { decision: { lead: string; body: string | null; run_date: string | null } | null };
type RisksPayload = { risks: string[] };

function DossierDrawer({ ticker, onClose }: { ticker: string | null; onClose: () => void }) {
  const [env, setEnv] = useState<Envelope<Dossier> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!ticker) return;
    let cancel = false;
    setEnv(null);
    setErr(null);
    dqGet<Dossier>(`/dossier/${encodeURIComponent(ticker)}`).then(
      (e) => { if (!cancel) setEnv(e); },
      (e: unknown) => { if (!cancel) setErr(e instanceof Error ? e.message : 'failed'); },
    );
    return () => { cancel = true; };
  }, [ticker]);
  const d = env?.data;
  return (
    <Drawer open={ticker !== null} onClose={onClose} no="09" label={ticker ? `Dossier · ${ticker}` : 'Dossier'} right={env?.as_of ? `as of ${env.as_of}` : undefined}>
      {err ? <StateBlock kind="error" title="Withheld." why={err} />
        : !d ? <p className="note mute">loading…</p>
        : (
          <>
            <Prose lead={d.thesis?.name ?? d.ticker}>
              {d.thesis ? <p>{d.thesis.state ?? '—'} · {d.thesis.id ?? '—'}</p> : <p>no thesis for this ticker</p>}
            </Prose>
            <p className="meta pad">Vehicles <b>{d.vehicles.length ? d.vehicles.join(' ') : '—'}</b> P&L <b>{signed(d.pnl.unrealized_pct)}</b> Stop <b>{px(d.stop)}</b> Target <b>{px(d.target)}</b></p>
            <DataTable
              rows={d.events}
              rowKey={(e, i) => `${e.date ?? ''}:${e.type ?? ''}:${i}`}
              empty="no events"
              cols={[
                { key: 'd', label: 'Date', cell: (e) => e.date ?? '—' },
                { key: 't', label: 'Type', cell: (e) => e.type ?? '—' },
              ]}
            />
            <DataTable
              rows={d.documents}
              rowKey={(doc, i) => `${doc.title ?? ''}:${i}`}
              empty="no documents"
              cols={[{ key: 't', label: 'Document', wrap: true, cell: (doc) => doc.title ?? '—' }]}
            />
          </>
        )}
    </Drawer>
  );
}

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

/** GET /allocations/enriched — holdings table. A position row opens the ticker dossier. */
export function HoldingsBlock() {
  const [ticker, setTicker] = useState<string | null>(null);
  return (
    <>
      <Block<Book> no="09" label="Holdings · by sleeve" route="/allocations/enriched" asOf={(d) => d.book_as_of}>
        {(d) => (
          <DataTable
            rows={holdingsRows(d)}
            cols={holdCols}
            rowKey={(h) => h.key}
            variant={(h) => (h.kind === 'grp' ? 'grp' : h.kind === 'total' ? 'total' : undefined)}
            empty="no positions"
            onRowClick={(h) => { if (h.kind === 'pos' && h.r?.ticker) setTicker(h.r.ticker); }}
          />
        )}
      </Block>
      <DossierDrawer ticker={ticker} onClose={() => setTicker(null)} />
    </>
  );
}

/** GET /allocations/enriched — sleeve exposure. */
export function SleevesBlock() {
  return (
    <Block<Book> no="10" label="Exposure · sleeve" route="/allocations/enriched" asOf={(d) => d.book_as_of}>
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

/** GET /allocations/enriched — day movers (sorted by day return; rows without one are left out, not zeroed). */
export function MoversBlock() {
  const [ticker, setTicker] = useState<string | null>(null);
  return (
    <>
      <Block<Book> no="11" label="Book · movers" route="/allocations/enriched" asOf={(d) => d.book_as_of}>
        {(d) => {
          const rows = d.rows.filter((r) => !r.is_cash && Number.isFinite(r.day_return_pct)).sort((a, b) => (b.day_return_pct as number) - (a.day_return_pct as number));
          return rows.length ? (
            <DataTable
              rows={rows}
              rowKey={(r) => r.ticker}
              onRowClick={(r) => setTicker(r.ticker)}
              cols={[
                { key: 't', label: 'Ticker', cell: (r) => r.ticker },
                { key: 'm', label: 'Mark', num: true, cell: (r) => px(r.current_price) },
                { key: 'd', label: 'Day', num: true, cell: (r) => signed(r.day_return_pct ?? null), tone: (r) => tone(r.day_return_pct) },
              ]}
            />
          ) : withheld('day return');
        }}
      </Block>
      <DossierDrawer ticker={ticker} onClose={() => setTicker(null)} />
    </>
  );
}

/** GET /brief/decision — decision text. */
export function DecisionBlock() {
  return (
    <Block<DecisionPayload> no="12" label="Decision" route="/brief/decision" asOf={(d) => d.decision?.run_date}>
      {(d) => (d.decision ? <Prose lead={d.decision.lead}>{d.decision.body ? <p>{d.decision.body}</p> : null}</Prose> : withheld('decision'))}
    </Block>
  );
}

/** GET /brief/risks — what could break the view. */
export function RisksBlock() {
  return (
    <Block<RisksPayload> no="13" label="What could break the view" route="/brief/risks">
      {(d) => (d.risks?.length ? <BulletList items={d.risks} /> : withheld('risks'))}
    </Block>
  );
}

const stateTone: Record<string, BadgeTone> = { active: 'ok', watch: 'wip', exited: 'plain' };

/** GET /theses — thesis list. A row with a vehicle opens that ticker's dossier. */
export function ThesesBlock() {
  const [ticker, setTicker] = useState<string | null>(null);
  return (
    <>
    <Block<Theses> no="14" label="Theses" route="/theses">
      {(d) => (
        <>
          <p className="meta pad">Active <b>{d.counts?.active ?? '—'}</b> Watch <b>{d.counts?.watch ?? '—'}</b> Exited <b>{d.counts?.exited ?? '—'}</b></p>
          <DataTable
            rows={d.theses}
            rowKey={(t) => t.id}
            onRowClick={(t) => { if (t.vehicles[0]) setTicker(t.vehicles[0]); }}
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
    <DossierDrawer ticker={ticker} onClose={() => setTicker(null)} />
    </>
  );
}

/** GET /theses/signals — signals to resolve. */
export function SignalsBlock() {
  return (
    <Block<Theses> no="15" label="Signals to resolve" route="/theses/signals">
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

/** GET /attribution — sleeve and name contribution in bp. Bars are relative to the largest figure in the table. */
export function AttributionBlock() {
  const [ticker, setTicker] = useState<string | null>(null);
  return (
    <>
    <Block<Attribution> no="16" label="Attribution" route="/attribution" asOf={(d) => [d.window.start, d.window.end].filter(Boolean).join(' → ') || undefined}>
      {(d) => {
        const scale = (rows: { contribution_bp: number | null }[]) => {
          const max = rows.reduce((m, r) => (r.contribution_bp != null && Math.abs(r.contribution_bp) > m ? Math.abs(r.contribution_bp) : m), 0);
          return (v: number | null) => (v == null || max === 0 ? null : (Math.abs(v) / max) * 100);
        };
        const sleeveBar = scale(d.sleeves);
        const nameBar = scale(d.names);
        return (
        <>
          <DataTable
            rows={d.sleeves}
            rowKey={(s) => s.sleeve}
            cols={[
              { key: 's', label: 'Sleeve', cell: (s) => s.sleeve },
              { key: 'c', label: 'Contribution', num: true, bar: (s) => sleeveBar(s.contribution_bp), cell: (s) => bp(s.contribution_bp), tone: (s) => tone(s.contribution_bp) },
            ]}
          />
          <DataTable
            rows={d.names}
            rowKey={(n) => n.ticker}
            onRowClick={(n) => setTicker(n.ticker)}
            cols={[
              { key: 't', label: 'Name', cell: (n) => n.ticker },
              { key: 's', label: 'Sleeve', cell: (n) => n.sleeve ?? '—' },
              { key: 'c', label: 'Contribution', num: true, bar: (n) => nameBar(n.contribution_bp), cell: (n) => bp(n.contribution_bp), tone: (n) => tone(n.contribution_bp) },
            ]}
          />
        </>
        );
      }}
    </Block>
    <DossierDrawer ticker={ticker} onClose={() => setTicker(null)} />
    </>
  );
}

/** GET /performance/drawdown — underwater series and recovered episodes. */
export function DrawdownBlock() {
  return (
    <Block<Drawdown> no="17" label="Drawdown" route="/performance/drawdown" asOf={(d) => d.trough_date}>
      {(d) => (
        <>
          <KpiGrid items={[
            { label: 'Max drawdown', value: signed(d.max_pct), tone: tone(d.max_pct), note: d.peak_date && d.trough_date ? `${d.peak_date} → ${d.trough_date}` : undefined },
            { label: 'Current drawdown', value: signed(d.current_pct), tone: tone(d.current_pct) },
          ]} />
          <AreaChart points={d.series} underwater ranges label="drawdown" fmt={(v) => `${v.toFixed(2)}%`} />
          <DataTable
            rows={d.episodes}
            rowKey={(e, i) => `${e.start ?? ''}:${e.trough ?? ''}:${i}`}
            empty="no recovered episodes"
            cols={[
              { key: 'd', label: 'Depth', num: true, cell: (e) => signed(e.depth_pct), tone: (e) => tone(e.depth_pct) },
              { key: 's', label: 'Start', cell: (e) => e.start ?? '—' },
              { key: 't', label: 'Trough', cell: (e) => e.trough ?? '—' },
              { key: 'r', label: 'Recovery', cell: (e) => e.recovery ?? '—' },
              { key: 'n', label: 'Days', num: true, cell: (e) => (e.days == null ? '—' : String(e.days)) },
            ]}
          />
        </>
      )}
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
  { id: 'holdings', title: 'Holdings · by sleeve', route: '/allocations/enriched', Component: HoldingsBlock },
  { id: 'sleeves', title: 'Exposure · sleeve', route: '/allocations/enriched', Component: SleevesBlock },
  { id: 'movers', title: 'Book · movers', route: '/allocations/enriched', Component: MoversBlock },
  { id: 'decision', title: 'Decision', route: '/brief/decision', Component: DecisionBlock },
  { id: 'risks', title: 'What could break the view', route: '/brief/risks', Component: RisksBlock },
  { id: 'theses', title: 'Theses', route: '/theses', Component: ThesesBlock },
  { id: 'signals', title: 'Signals to resolve', route: '/theses/signals', Component: SignalsBlock },
  { id: 'attribution', title: 'Attribution', route: '/attribution', Component: AttributionBlock },
  { id: 'drawdown', title: 'Drawdown', route: '/performance/drawdown', Component: DrawdownBlock },
  { id: 'navtable', title: 'NAV · by date', route: '/nav-series', Component: NavTableBlock },
  { id: 'cash', title: 'Cash ledger', route: '/ledger/cash', Component: CashLedgerBlock },
];
