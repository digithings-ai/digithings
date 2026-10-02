'use client';

import { useState, type ComponentType } from 'react';
import { dqSend, pct, signed, type Theses } from '@/lib/dq-api';
import type {
  FxDirectives, FxDirectivesPut, FxFlag, FxIdeaDetail, FxIdeas, FxLevels, FxPairPath, FxPairs, FxPaperExposure, FxSessions, FxSummary,
  MkBars, MkQuote, MkQuotes, MkSeriesRegistry, MkTape, RtCurve, RtSummary, RtWatchlist,
} from '@/lib/api-markets';
import { Block } from './Block';
import { KpiGrid, Sparkline, tone } from './atoms';
import { Candles, LineChart } from './charts';
import { DataTable } from './DataTable';
import { Badge, BulletList, Button, KvList, MetaStrip, Prose, StateBlock, type BadgeTone } from './ui';
import { Field, Select, Toggle } from './ui-form';

/* ---- helpers: every one fails closed to an em dash ---- */
const fin = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const arr = <T,>(v: readonly T[] | null | undefined): T[] => (Array.isArray(v) ? [...v] : []);
const txt = (v: string | null | undefined) => (v == null || v === '' ? '—' : v);
const num = (v: number | null | undefined, d = 2) => (fin(v) ? v.toFixed(d) : '—');
/** Price as delivered: no rounding or padding that would invent precision (FX quotes vary in decimals). */
const raw = (v: number | null | undefined) => (fin(v) ? String(v) : '—');
const usd = (v: number | null | undefined) => (fin(v) ? v.toLocaleString('en-US', { maximumFractionDigits: 2 }) : '—');
const sgn = (v: number | null | undefined, d = 2) => (fin(v) ? `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(d)}` : '—');
const bp = (v: number | null | undefined) => (fin(v) ? `${Math.round(v) > 0 ? '+' : Math.round(v) < 0 ? '−' : ''}${Math.abs(Math.round(v))} bp` : '—');
const compact = (v: number | null | undefined) => {
  if (!fin(v)) return '—';
  const a = Math.abs(v);
  return a >= 1e9 ? `${(v / 1e9).toFixed(1)}b` : a >= 1e6 ? `${(v / 1e6).toFixed(1)}m` : a >= 1e3 ? `${(v / 1e3).toFixed(1)}k` : String(v);
};
const withheld = (what: string) => <StateBlock kind="empty" title="Withheld." why={`${what} is not in the response yet; nothing is estimated.`} />;
const lastFinite = (xs: (number | null | undefined)[] | null | undefined): number | null => {
  const a = arr(xs);
  for (let i = a.length - 1; i >= 0; i--) if (fin(a[i])) return a[i] as number;
  return null;
};

const statusTone = (s: string | null | undefined): BadgeTone => {
  const k = (s ?? '').toLowerCase();
  if (['missing_rates', 'incomplete', 'unavailable', 'error', 'failed'].includes(k)) return 'unavailable';
  if (['ok', 'carried', 'open', 'resolved', 'complete', 'live', 'active'].includes(k)) return 'ok';
  if (['wip', 'coming soon', 'soon', 'partial', 'watch'].includes(k)) return 'wip';
  return 'plain';
};
const StatusBadge = ({ s }: { s: string | null | undefined }) => (s ? <Badge tone={statusTone(s)}>{s}</Badge> : <>—</>);
const q = (s: string) => encodeURIComponent(s);

/**
 * Route configuration seeds. Blocks that are about one symbol/pair take it as a prop; these are the
 * defaults the registry uses until the grid supplies one. They are config, not data.
 */
export const MK_DEFAULT_SYMBOL = 'SPY';
export const MK_DEFAULT_INTERVAL = '1D';
export const FX_DEFAULT_PAIR = 'USDJPY';
const STRIP_SYMBOLS = 'SPY,QQQ,IWM,TLT,GLD,UUP';
const BOARD_SYMBOLS = 'SPY,QQQ,IWM,TLT,IEF,LQD,HYG,GLD,XLE,XLU,XLK,UUP,DBC';
const CROSS_SYMBOLS = 'EURUSD,USDJPY,GBPUSD,VIX';

/* =========================== Market tools =========================== */

function QuoteChg({ q: x }: { q: MkQuote }) {
  return <span className={tone(x.pct) ?? ''}>{signed(x.pct ?? null)}</span>;
}

/** GET /markets/quotes — single-line horizontal strip of quotes; scrolls inside its own frame. */
export function TickerStripBlock({ symbols = STRIP_SYMBOLS }: { symbols?: string }) {
  return (
    <Block<MkQuotes> no="31" label="Ticker strip" route={`/markets/quotes?symbols=${symbols}`}>
      {(d) => {
        const qs = arr(d.quotes);
        return qs.length ? (
          <div className="mk-strip" role="list" aria-label="Quotes">
            {qs.map((x, i) => (
              <span className="mk-q" role="listitem" key={`${x.symbol}:${i}`}>
                <span className="mk-q-s">{x.symbol}</span>
                <span className="mk-q-v">{fin(x.last) ? x.last.toFixed(2) : '—'}</span>
                {fin(x.last) ? <QuoteChg q={x} /> : <span className="mk-q-s">—</span>}
              </span>
            ))}
          </div>
        ) : <p className="note mute">no quotes</p>;
      }}
    </Block>
  );
}

const quoteCols = (withDepth: boolean) => [
  { key: 's', label: 'Symbol', cell: (x: MkQuote) => x.symbol },
  { key: 'n', label: 'Name', wrap: true, cell: (x: MkQuote) => txt(x.name) },
  { key: 'l', label: 'Last', num: true, cell: (x: MkQuote) => (fin(x.last) ? x.last.toFixed(2) : '—') },
  { key: 'c', label: 'Net', num: true, cell: (x: MkQuote) => sgn(x.net), tone: (x: MkQuote) => tone(x.net) },
  { key: 'p', label: '%', num: true, cell: (x: MkQuote) => (fin(x.last) ? signed(x.pct ?? null) : <Badge tone="unavailable">unavailable</Badge>), tone: (x: MkQuote) => tone(x.pct) },
  ...(withDepth
    ? [
        { key: 'b', label: 'Bid', num: true, cell: (x: MkQuote) => num(x.bid) },
        { key: 'a', label: 'Ask', num: true, cell: (x: MkQuote) => num(x.ask) },
        { key: 'v', label: 'Vol', num: true, cell: (x: MkQuote) => compact(x.volume) },
        { key: 't', label: 'Time', num: true, cell: (x: MkQuote) => txt(x.time) },
      ]
    : []),
];

/** GET /markets/quotes — full quote board. */
export function QuoteBoardBlock({ symbols = BOARD_SYMBOLS }: { symbols?: string }) {
  return (
    <Block<MkQuotes> no="32" label="Quote board" route={`/markets/quotes?symbols=${symbols}`}>
      {(d) => <DataTable rows={arr(d.quotes)} cols={quoteCols(true)} rowKey={(x, i) => `${x.symbol}:${i}`} empty="no quotes" />}
    </Block>
  );
}

/** GET /markets/quotes — FX crosses (and VIX) board. */
export function FxCrossesBlock({ symbols = CROSS_SYMBOLS }: { symbols?: string }) {
  return (
    <Block<MkQuotes> no="33" label="Crosses" route={`/markets/quotes?symbols=${symbols}`}>
      {(d) => (
        <DataTable
          rows={arr(d.quotes)}
          rowKey={(x, i) => `${x.symbol}:${i}`}
          empty="no quotes"
          cols={[
            { key: 's', label: 'Pair', cell: (x) => x.symbol },
            { key: 'l', label: 'Last', num: true, cell: (x) => raw(x.last) },
            { key: 'p', label: 'Day', num: true, cell: (x) => (fin(x.pct) ? signed(x.pct) : sgn(x.net)), tone: (x) => tone(x.pct ?? x.net) },
          ]}
        />
      )}
    </Block>
  );
}

const barsRoute = (symbol: string, interval: string, ind: string) => `/markets/bars?symbol=${q(symbol)}&interval=${q(interval)}&indicators=${ind}`;
const barX = (d: MkBars) => arr(d.bars).map((b) => String(b?.t ?? ''));

/** GET /markets/bars — price candles (volume has its own pane). */
export function PricePaneBlock({ symbol = MK_DEFAULT_SYMBOL, interval = MK_DEFAULT_INTERVAL }: { symbol?: string; interval?: string }) {
  return (
    <Block<MkBars> no="34" label={`Price · ${symbol} · ${interval}`} route={barsRoute(symbol, interval, 'ema20,rsi14')}>
      {(d) => <Candles bars={arr(d.bars).map((b) => ({ t: String(b?.t ?? ''), o: b?.o, h: b?.h, l: b?.l, c: b?.c }))} />}
    </Block>
  );
}

/** GET /markets/bars — volume pane. */
export function VolumePaneBlock({ symbol = MK_DEFAULT_SYMBOL, interval = MK_DEFAULT_INTERVAL }: { symbol?: string; interval?: string }) {
  return (
    <Block<MkBars> no="35" label={`Volume · ${symbol}`} route={barsRoute(symbol, interval, 'ema20,rsi14')}>
      {(d) => <LineChart series={[{ name: 'volume', values: arr(d.bars).map((b) => b?.v), tone: 'soft' }]} labels={barX(d)} fmt={compact} height={90} />}
    </Block>
  );
}

/** GET /markets/bars — RSI pane. */
export function RsiPaneBlock({ symbol = MK_DEFAULT_SYMBOL, interval = MK_DEFAULT_INTERVAL }: { symbol?: string; interval?: string }) {
  return (
    <Block<MkBars> no="36" label={`RSI 14 · ${symbol}`} route={barsRoute(symbol, interval, 'ema20,rsi14')}>
      {(d) => (d.indicators?.rsi14?.length ? <LineChart series={[{ name: 'RSI 14', values: d.indicators.rsi14 }]} labels={barX(d)} fmt={(v) => v.toFixed(0)} height={90} /> : withheld('RSI 14'))}
    </Block>
  );
}

const indLabel = (k: string) => k.replace(/(\d+)$/, ' $1').toUpperCase();

/** GET /markets/bars — last-bar OHLC readout with indicator values. */
export function OhlcReadoutBlock({ symbol = MK_DEFAULT_SYMBOL, interval = MK_DEFAULT_INTERVAL }: { symbol?: string; interval?: string }) {
  return (
    <Block<MkBars> no="37" label={`OHLC · ${symbol}`} route={barsRoute(symbol, interval, 'ema20,rsi14')} asOf={(d) => arr(d.bars).at(-1)?.t}>
      {(d) => {
        const bars = arr(d.bars);
        const last = bars.at(-1);
        if (!last) return withheld('bars');
        const prev = bars.at(-2);
        const net = fin(last.c) && fin(prev?.c) ? last.c - prev.c : null;
        const chg = net != null && fin(prev?.c) && prev.c !== 0 ? (net / prev.c) * 100 : null;
        const inds = Object.entries(d.indicators ?? {}).map(([k, v]) => ({ label: indLabel(k), value: num(lastFinite(v)) }));
        return (
          <div className="pad">
            <MetaStrip items={[
              { label: 'Symbol', value: d.symbol }, { label: 'Interval', value: d.interval }, { label: 'Venue', value: txt(d.venue) },
              { label: 'O', value: num(last.o) }, { label: 'H', value: num(last.h) }, { label: 'L', value: num(last.l) }, { label: 'C', value: num(last.c) },
              { label: 'Chg', value: sgn(net) }, { label: '%', value: signed(chg) }, { label: 'Vol', value: compact(last.v) },
              ...inds,
            ]} />
          </div>
        );
      }}
    </Block>
  );
}

/** GET /tape — news / run-event tape, newest first. */
export function NewsTapeBlock() {
  return (
    <Block<MkTape> no="38" label="Tape" route="/tape">
      {(d) => (
        <DataTable
          rows={arr(d.items)}
          rowKey={(t, i) => `${t.time}:${i}`}
          empty="tape is empty"
          cols={[
            { key: 't', label: 'Time', cell: (t) => txt(t.time) },
            { key: 'h', label: 'Headline', wrap: true, cell: (t) => txt(t.headline) },
            { key: 'g', label: 'Tag', cell: (t) => (t.tag ? <Badge>{t.tag}</Badge> : '—') },
          ]}
        />
      )}
    </Block>
  );
}

/** GET /charts/series — registry of series the chart tool can draw. */
export function ChartSeriesRegistryBlock() {
  return (
    <Block<MkSeriesRegistry> no="39" label="Chart series" route="/charts/series">
      {(d) => (
        <>
          <div className="pad">
            <MetaStrip items={[{ label: 'Symbol', value: txt(d.defaults?.symbol) }, { label: 'Range', value: txt(d.defaults?.range) }, { label: 'Series', value: txt(d.defaults?.series) }]} />
          </div>
          <DataTable
            rows={arr(d.series)}
            rowKey={(s, i) => `${s.id}:${i}`}
            empty="no series registered"
            cols={[
              { key: 'l', label: 'Series', wrap: true, cell: (s) => txt(s.label) },
              { key: 's', label: 'Source', wrap: true, cell: (s) => txt(s.source) },
              { key: 'st', label: 'Status', cell: (s) => <StatusBadge s={s.status} /> },
            ]}
          />
        </>
      )}
    </Block>
  );
}

/* =========================== FX desk =========================== */

/** GET /fx/summary — KPIs, read and what changed. */
export function FxSummaryBlock() {
  return (
    <Block<FxSummary> no="41" label="FX hub · summary" route="/fx/summary" asOf={(d) => d.run_date}>
      {(d) => (
        <>
          <KpiGrid items={[
            { label: 'Pairs', value: d.pairs?.count == null ? '—' : String(d.pairs.count), note: d.pairs?.note ?? undefined },
            { label: 'Ideas', value: d.ideas?.count == null ? '—' : String(d.ideas.count), note: d.ideas?.note ?? undefined },
            { label: 'Paper exposure', value: fin(d.paper_exposure?.gross_usd) ? usd(d.paper_exposure.gross_usd) : '—', note: d.paper_exposure?.venue ? `USD gross · ${d.paper_exposure.venue}` : undefined },
            { label: 'Session', value: txt(d.session?.name), note: d.session?.note ?? undefined },
            { label: 'Research flags', value: d.research_flags?.count == null ? '—' : String(d.research_flags.count) },
            { label: 'Run', value: txt(d.run_date) },
          ]} />
          <div className="pad"><MetaStrip items={[{ label: 'Desk', value: txt(d.desk) }, { label: 'Posture', value: txt(d.posture) }]} /></div>
          {d.read?.lead ? <Prose lead={d.read.lead}>{d.read.body ? <p className="soft">{d.read.body}</p> : null}</Prose> : null}
          {arr(d.changes).length ? <BulletList items={arr(d.changes)} /> : null}
        </>
      )}
    </Block>
  );
}

/** GET /fx/pairs — G10 board with session path. */
export function FxPairsBlock() {
  return (
    <Block<FxPairs> no="42" label="FX · pairs" route="/fx/pairs">
      {(d) => (
        <DataTable
          rows={arr(d.pairs)}
          rowKey={(p, i) => `${p.pair}:${i}`}
          empty="no pairs"
          cols={[
            { key: 'p', label: 'Pair', cell: (p) => p.pair },
            { key: 'b', label: 'Bid', num: true, cell: (p) => raw(p.bid) },
            { key: 'o', label: 'Offer', num: true, cell: (p) => raw(p.offer) },
            { key: 'd', label: 'Day', num: true, cell: (p) => signed(p.day_pct), tone: (p) => tone(p.day_pct) },
            { key: 's', label: 'Session', cell: (p) => txt(p.session) },
            { key: 'h', label: 'Path', cell: (p) => (arr(p.path).filter(fin).length >= 2 ? <span className="mk-path" style={{ display: 'inline-block', width: '5rem' }}><Sparkline values={arr(p.path)} height={18} /></span> : '—') },
            { key: 'bi', label: 'Bias', cell: (p) => txt(p.bias) },
            { key: 'st', label: 'Status', cell: (p) => <StatusBadge s={p.status} /> },
          ]}
        />
      )}
    </Block>
  );
}

/** GET /fx/pairs/:pair/path — session path for one pair. */
export function FxPairPathBlock({ pair = FX_DEFAULT_PAIR }: { pair?: string }) {
  return (
    <Block<FxPairPath> no="43" label={`Session path · ${pair}`} route={`/fx/pairs/${q(pair)}/path`}>
      {(d) => (
        <>
          <LineChart series={[{ name: d.pair || pair, values: arr(d.points).map((p) => p?.v) }]} labels={arr(d.points).map((p) => String(p?.t ?? ''))} fmt={(v) => String(+v.toFixed(5))} height={120} />
          <p className="mk-note">{[d.session, d.note].filter(Boolean).join(' · ') || 'Display-only path for the selected pair. Not a feed.'}</p>
        </>
      )}
    </Block>
  );
}

/** GET /fx/ideas — ranked idea board. */
export function FxIdeasBlock() {
  return (
    <Block<FxIdeas> no="44" label="FX · ideas" route="/fx/ideas">
      {(d) => (
        <DataTable
          rows={arr(d.ideas)}
          rowKey={(r, i) => `${r.pair}:${i}`}
          empty="no ideas on the board"
          cols={[
            { key: 'r', label: 'Rank', num: true, cell: (r) => (fin(r.rank) ? String(r.rank) : '—') },
            { key: 'p', label: 'Pair', cell: (r) => r.pair },
            { key: 'b', label: 'Bias', cell: (r) => txt(r.bias) },
            { key: 'h', label: 'Horizon', cell: (r) => txt(r.horizon) },
            { key: 'i', label: 'Invalidation', num: true, cell: (r) => raw(r.invalidation) },
            { key: 's', label: 'Status', cell: (r) => <StatusBadge s={r.status} /> },
            { key: 'l', label: 'Levels', cell: (r) => <StatusBadge s={r.levels} /> },
            { key: 't', label: 'Thread', wrap: true, cell: (r) => txt(r.thread) },
          ]}
        />
      )}
    </Block>
  );
}

const withProv = (v: string, p: string | null | undefined) => (v === '—' ? '—' : <>{v}{p ? <> <Badge>{p}</Badge></> : null}</>);

/** GET /fx/ideas/:pair — one idea in detail. */
export function FxIdeaDetailBlock({ pair = FX_DEFAULT_PAIR }: { pair?: string }) {
  return (
    <Block<FxIdeaDetail> no="45" label={`Idea · ${pair}`} route={`/fx/ideas/${q(pair)}`}>
      {(d) => {
        const e = d.entry;
        const entry = e && (fin(e.low) || fin(e.high)) ? `${raw(e.low)} – ${raw(e.high)}` : '—';
        return (
          <>
            <Prose lead={d.headline ?? undefined}>{d.rationale ? <p className="soft">{d.rationale}</p> : null}</Prose>
            <KvList rows={[
              { k: 'Rank', v: fin(d.rank) ? String(d.rank) : '—' },
              { k: 'Bias', v: txt(d.bias) },
              { k: 'Horizon', v: txt(d.horizon) },
              { k: 'Invalidation', v: withProv(raw(d.invalidation?.value), d.invalidation?.provenance), mono: true },
              { k: 'Entry', v: withProv(entry, e?.provenance), mono: true },
              { k: 'Target', v: withProv(raw(d.target?.value), d.target?.provenance), mono: true },
              { k: 'Status', v: <StatusBadge s={d.status} /> },
              { k: 'Catalyst', v: txt(d.catalyst) },
            ]} />
            {d.evidence_note ? <p className="mk-note">{d.evidence_note}</p> : null}
          </>
        );
      }}
    </Block>
  );
}

/** GET /fx/levels — display-only levels per pair. */
export function FxLevelsBlock() {
  return (
    <Block<FxLevels> no="46" label="FX · levels" route="/fx/levels">
      {(d) => (
        <DataTable
          rows={arr(d.levels)}
          rowKey={(l, i) => `${l.pair}:${i}`}
          empty="no levels"
          cols={[
            { key: 'p', label: 'Pair', cell: (l) => l.pair },
            { key: 'm', label: 'Mark', num: true, cell: (l) => raw(l.mark) },
            { key: 'l', label: 'Level', num: true, cell: (l) => raw(l.level) },
            { key: 'r', label: 'Role', cell: (l) => txt(l.role) },
            { key: 'pi', label: 'Pips', num: true, cell: (l) => raw(l.pips) },
            { key: 'pr', label: 'Provenance', cell: (l) => <StatusBadge s={l.provenance} /> },
            { key: 'f', label: 'Flag', cell: (l) => (l.flag ? <Badge>{l.flag}</Badge> : '—') },
          ]}
        />
      )}
    </Block>
  );
}

/** GET /fx/flags/:pair — research flag for one pair (display-only, never a send). */
export function FxFlagsBlock({ pair = FX_DEFAULT_PAIR }: { pair?: string }) {
  return (
    <Block<FxFlag> no="47" label={`Flag · ${pair}`} route={`/fx/flags/${q(pair)}`}>
      {(d) => (
        <>
          {d.flagged ? (
            <>
              <KvList rows={[{ k: 'Pair', v: txt(d.pair) }, { k: 'Level', v: raw(d.level), mono: true }]} />
              <Prose>{d.text ? <p>{d.text}</p> : null}</Prose>
            </>
          ) : <p className="note mute">no research flag on {d.pair || pair}</p>}
          {d.scope_note ? <p className="mk-note">{d.scope_note}</p> : null}
        </>
      )}
    </Block>
  );
}

/** GET /fx/paper-exposure — paper lines and gross. */
export function FxPaperExposureBlock() {
  return (
    <Block<FxPaperExposure> no="48" label="Open risk · paper" route="/fx/paper-exposure">
      {(d) => {
        const lines = arr(d.lines);
        return (
          <>
            {d.note ? <p className="mk-note">{d.note}</p> : null}
            <DataTable
              rows={[...lines.map((l) => ({ kind: 'line' as const, l })), ...(fin(d.gross_usd) ? [{ kind: 'total' as const, l: null }] : [])]}
              rowKey={(r, i) => `${r.kind}:${r.l?.pair ?? ''}:${i}`}
              variant={(r) => (r.kind === 'total' ? 'total' : undefined)}
              empty="no paper exposure"
              cols={[
                { key: 'p', label: 'Pair', cell: (r) => (r.l ? r.l.pair : 'Gross') },
                { key: 's', label: 'Side', cell: (r) => (r.l ? txt(r.l.side) : '') },
                { key: 'n', label: 'Notional USD', num: true, cell: (r) => (r.l ? usd(r.l.notional_usd) : usd(d.gross_usd)) },
                { key: 'v', label: 'Venue', cell: (r) => (r.l ? txt(r.l.venue ?? d.venue) : txt(d.venue)) },
              ]}
            />
          </>
        );
      }}
    </Block>
  );
}

/** GET /fx/sessions — Asia / London / New York state. */
export function FxSessionsBlock() {
  return (
    <Block<FxSessions> no="49" label="FX · sessions" route="/fx/sessions">
      {(d) => (
        <DataTable
          rows={arr(d.sessions)}
          rowKey={(s, i) => `${s.session}:${i}`}
          variant={(s) => (s.active ? 'sel' : undefined)}
          empty="no sessions"
          cols={[
            { key: 's', label: 'Session', cell: (s) => s.session },
            { key: 'st', label: 'State', cell: (s) => <StatusBadge s={s.state} /> },
            { key: 'n', label: 'Note', wrap: true, cell: (s) => txt(s.note) },
          ]}
        />
      )}
    </Block>
  );
}

/* ---- directives: GET + PUT, with visible result ---- */
const words = (s: string) => s.split(/[\s,]+/).filter(Boolean);

function DirectivesForm({ d }: { d: FxDirectives }) {
  const [allow, setAllow] = useState(arr(d.allow_pairs).join(' '));
  const [deny, setDeny] = useState(arr(d.deny_pairs).join(' '));
  const [risk, setRisk] = useState(d.risk_style ?? '');
  const [ignore, setIgnore] = useState(arr(d.ignore_sources).join(' '));
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<{ ok: boolean; text: string } | null>(null);
  const readOnly = d.writable === false;
  const opts = arr(d.risk_style_options);

  const save = async () => {
    const body: FxDirectivesPut = { allow_pairs: words(allow).map((w) => w.toUpperCase()), deny_pairs: words(deny).map((w) => w.toUpperCase()), risk_style: risk === '' ? null : risk, ignore_sources: words(ignore) };
    setBusy(true);
    setRes(null);
    try {
      await dqSend('PUT', '/fx/directives', body);
      setRes({ ok: true, text: 'PUT /fx/directives accepted by the server.' });
    } catch (e) {
      setRes({ ok: false, text: e instanceof Error ? e.message : 'save failed' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <p className="mk-note">{d.note ?? 'Affects generation only when a writer contract is wired. Display-only watch flags do not write these fields.'}</p>
      <Field label="Allow pairs" value={allow} onChange={(e) => setAllow(e.target.value)} disabled={readOnly} hint="Space separated." />
      <Field label="Deny pairs" value={deny} onChange={(e) => setDeny(e.target.value)} disabled={readOnly} placeholder="none" hint="A denied pair is omitted from generation, not from the watch." />
      {opts.length ? (
        <Select label="Risk style" value={risk} onChange={setRisk} options={[...(risk === '' ? [{ value: '', label: '—' }] : []), ...opts.map((o) => ({ value: o, label: o }))]} />
      ) : (
        <Field label="Risk style" value={risk} onChange={(e) => setRisk(e.target.value)} disabled={readOnly} placeholder="none" />
      )}
      <Field label="Ignore sources" value={ignore} onChange={(e) => setIgnore(e.target.value)} disabled={readOnly} placeholder="none" hint="Contributing research sources." />
      <Toggle label="Confirm: these directives steer generation" on={confirm} onChange={setConfirm} hint="Required before saving." />
      <div className="mk-acts">
        <Button primary onClick={save} disabled={busy || readOnly || !confirm}>{busy ? 'Saving…' : 'Save directives'}</Button>
        {readOnly ? <span className="mk-q-s">read-only: writer contract not wired</span> : null}
      </div>
      {res ? <p className={`mk-result ${res.ok ? 'ok' : 'err'}`} role={res.ok ? 'status' : 'alert'}>{res.text}</p> : null}
    </div>
  );
}

/** GET /fx/directives (+ PUT /fx/directives) — generation directives. */
export function FxDirectivesBlock() {
  return (
    <Block<FxDirectives> no="50" label="Generation directives" route="/fx/directives">
      {(d) => <DirectivesForm d={d} />}
    </Block>
  );
}

/* =========================== Rates desk =========================== */

/** GET /rates/summary — digest KPIs, read, signals, risks. */
export function RtSummaryBlock() {
  return (
    <Block<RtSummary> no="51" label="Rates · digest" route="/rates/summary" asOf={(d) => d.run_date}>
      {(d) => {
        const w = d.watchlist;
        const marks = fin(w?.marks_available) && fin(w?.names) ? `${w.marks_available} of ${w.names}` : fin(w?.marks_available) ? String(w.marks_available) : '—';
        const signals = arr(d.signals);
        return (
          <>
            <KpiGrid items={[
              { label: 'Watchlist', value: fin(w?.names) ? String(w.names) : '—', note: 'names' },
              { label: 'Marks', value: marks },
              { label: 'Active theses', value: d.theses ? String(arr(d.theses.active).length) : '—', note: d.theses ? arr(d.theses.active).join(', ') || undefined : undefined },
              { label: 'Watch', value: d.theses ? String(arr(d.theses.watch).length) : '—', note: d.theses ? arr(d.theses.watch).join(', ') || undefined : undefined },
              { label: 'Last run', value: txt(d.last_run?.date), note: d.last_run?.note ?? undefined },
              { label: 'Research budget', value: fin(d.budget?.spent_usd) ? `$${d.budget.spent_usd.toFixed(2)}` : '—', note: fin(d.budget?.cap_usd) ? `of $${d.budget.cap_usd.toFixed(2)} per run` : undefined },
            ]} />
            <div className="pad"><MetaStrip items={[{ label: 'Desk', value: txt(d.desk) }, { label: 'Posture', value: txt(d.posture) }]} /></div>
            {d.read?.lead ? <Prose lead={d.read.lead}>{d.read.body ? <p className="soft">{d.read.body}</p> : null}</Prose> : null}
            {signals.length ? (
              <DataTable
                rows={signals}
                rowKey={(s, i) => `${s.id}:${i}`}
                cols={[
                  { key: 'i', label: 'Thesis', cell: (s) => s.id },
                  { key: 'n', label: 'Name', wrap: true, cell: (s) => txt(s.name) },
                  { key: 's', label: 'State', cell: (s) => <StatusBadge s={s.state} /> },
                  { key: 'o', label: 'Note', wrap: true, cell: (s) => txt(s.note) },
                ]}
              />
            ) : null}
            {arr(d.risks).length ? <BulletList items={arr(d.risks)} /> : null}
          </>
        );
      }}
    </Block>
  );
}

/** GET /rates/watchlist — tracked names with marks. */
export function RtWatchlistBlock() {
  return (
    <Block<RtWatchlist> no="52" label="Rates · watchlist" route="/rates/watchlist">
      {(d) => (
        <DataTable
          rows={arr(d.names)}
          rowKey={(n, i) => `${n.ticker}:${i}`}
          empty="no names tracked"
          cols={[
            { key: 't', label: 'Ticker', cell: (n) => n.ticker },
            { key: 'n', label: 'Name', wrap: true, cell: (n) => txt(n.name) },
            { key: 'm', label: 'Mark', num: true, cell: (n) => num(n.mark) },
            { key: 'd', label: 'Day', num: true, cell: (n) => signed(n.day_pct ?? null), tone: (n) => tone(n.day_pct) },
            { key: 's', label: 'Mark source', cell: (n) => (fin(n.mark) ? <StatusBadge s={n.mark_source} /> : <Badge tone="unavailable">unavailable</Badge>) },
            { key: 'th', label: 'Thesis', cell: (n) => txt(n.thesis_id) },
          ]}
        />
      )}
    </Block>
  );
}

/** GET /rates/curve — yield curve with day change and spreads. */
export function RtCurveBlock() {
  return (
    <Block<RtCurve> no="53" label="Rates · curve" route="/rates/curve">
      {(d) => {
        const curve = arr(d.curve);
        const spreads = arr(d.spreads);
        return (
          <>
            <LineChart series={[{ name: 'yield', values: curve.map((c) => c?.yield_pct) }]} labels={curve.map((c) => String(c?.tenor ?? ''))} fmt={(v) => `${v.toFixed(2)}%`} height={110} />
            <DataTable
              rows={curve}
              rowKey={(c, i) => `${c.tenor}:${i}`}
              empty="no curve points"
              cols={[
                { key: 't', label: 'Tenor', cell: (c) => txt(c.tenor) },
                { key: 'y', label: 'Yield', num: true, cell: (c) => pct(c.yield_pct) },
                { key: 'd', label: 'Day', num: true, cell: (c) => sgn(c.day_change), tone: (c) => tone(c.day_change) },
              ]}
            />
            {spreads.length ? (
              <DataTable
                rows={spreads}
                rowKey={(s, i) => `${s.label}:${i}`}
                cols={[
                  { key: 'l', label: 'Spread', cell: (s) => txt(s.label) },
                  { key: 'b', label: 'Level', num: true, cell: (s) => bp(s.bp) },
                  { key: 'd', label: 'Day', num: true, cell: (s) => bp(s.day_bp), tone: (s) => tone(s.day_bp) },
                ]}
              />
            ) : null}
          </>
        );
      }}
    </Block>
  );
}

const thesisTone: Record<string, BadgeTone> = { active: 'ok', watch: 'wip', exited: 'plain' };

/** GET /rates/theses — rates desk theses. */
export function RtThesesBlock() {
  return (
    <Block<Theses> no="54" label="Rates · theses" route="/rates/theses">
      {(d) => (
        <>
          <p className="meta pad">Active <b>{d.counts?.active ?? '—'}</b> Watch <b>{d.counts?.watch ?? '—'}</b> Exited <b>{d.counts?.exited ?? '—'}</b></p>
          <DataTable
            rows={arr(d.theses)}
            rowKey={(t, i) => `${t.id}:${i}`}
            empty="no theses"
            cols={[
              { key: 'i', label: 'Id', cell: (t) => t.id },
              { key: 'n', label: 'Thesis', wrap: true, cell: (t) => txt(t.name) },
              { key: 's', label: 'State', cell: (t) => <Badge tone={thesisTone[t.state] ?? 'plain'}>{t.state}</Badge> },
              { key: 'v', label: 'Vehicles', cell: (t) => (arr(t.vehicles).length ? arr(t.vehicles).join(' ') : '—') },
              { key: 'e', label: 'Evidence', wrap: true, cell: (t) => txt(t.evidence) },
              { key: 'k', label: 'Kill condition', wrap: true, cell: (t) => txt(t.kill_condition) },
            ]}
          />
        </>
      )}
    </Block>
  );
}

/* =========================== Registry =========================== */
export type MarketsBlockDef = { id: string; title: string; route: string; Component: ComponentType };
export const MARKETS_BLOCKS: MarketsBlockDef[] = [
  { id: 'mk-ticker-strip', title: 'Ticker strip', route: `/markets/quotes?symbols=${STRIP_SYMBOLS}`, Component: TickerStripBlock },
  { id: 'mk-quote-board', title: 'Quote board', route: `/markets/quotes?symbols=${BOARD_SYMBOLS}`, Component: QuoteBoardBlock },
  { id: 'mk-fx-crosses', title: 'Crosses', route: `/markets/quotes?symbols=${CROSS_SYMBOLS}`, Component: FxCrossesBlock },
  { id: 'mk-price-pane', title: 'Price pane', route: barsRoute(MK_DEFAULT_SYMBOL, MK_DEFAULT_INTERVAL, 'ema20,rsi14'), Component: PricePaneBlock },
  { id: 'mk-volume-pane', title: 'Volume pane', route: barsRoute(MK_DEFAULT_SYMBOL, MK_DEFAULT_INTERVAL, 'ema20,rsi14'), Component: VolumePaneBlock },
  { id: 'mk-rsi-pane', title: 'RSI pane', route: barsRoute(MK_DEFAULT_SYMBOL, MK_DEFAULT_INTERVAL, 'ema20,rsi14'), Component: RsiPaneBlock },
  { id: 'mk-ohlc-readout', title: 'OHLC readout', route: barsRoute(MK_DEFAULT_SYMBOL, MK_DEFAULT_INTERVAL, 'ema20,rsi14'), Component: OhlcReadoutBlock },
  { id: 'mk-news-tape', title: 'Tape', route: '/tape', Component: NewsTapeBlock },
  { id: 'mk-chart-series', title: 'Chart series', route: '/charts/series', Component: ChartSeriesRegistryBlock },
  { id: 'fx-summary', title: 'FX hub · summary', route: '/fx/summary', Component: FxSummaryBlock },
  { id: 'fx-pairs', title: 'FX · pairs', route: '/fx/pairs', Component: FxPairsBlock },
  { id: 'fx-pair-path', title: 'Session path', route: `/fx/pairs/${FX_DEFAULT_PAIR}/path`, Component: FxPairPathBlock },
  { id: 'fx-ideas', title: 'FX · ideas', route: '/fx/ideas', Component: FxIdeasBlock },
  { id: 'fx-idea-detail', title: 'Idea detail', route: `/fx/ideas/${FX_DEFAULT_PAIR}`, Component: FxIdeaDetailBlock },
  { id: 'fx-levels', title: 'FX · levels', route: '/fx/levels', Component: FxLevelsBlock },
  { id: 'fx-flags', title: 'Research flag', route: `/fx/flags/${FX_DEFAULT_PAIR}`, Component: FxFlagsBlock },
  { id: 'fx-paper-exposure', title: 'Open risk · paper', route: '/fx/paper-exposure', Component: FxPaperExposureBlock },
  { id: 'fx-sessions', title: 'FX · sessions', route: '/fx/sessions', Component: FxSessionsBlock },
  { id: 'fx-directives', title: 'Generation directives', route: '/fx/directives', Component: FxDirectivesBlock },
  { id: 'rt-summary', title: 'Rates · digest', route: '/rates/summary', Component: RtSummaryBlock },
  { id: 'rt-watchlist', title: 'Rates · watchlist', route: '/rates/watchlist', Component: RtWatchlistBlock },
  { id: 'rt-curve', title: 'Rates · curve', route: '/rates/curve', Component: RtCurveBlock },
  { id: 'rt-theses', title: 'Rates · theses', route: '/rates/theses', Component: RtThesesBlock },
];
