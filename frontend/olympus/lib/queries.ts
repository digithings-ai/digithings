/**
 * Data access layer — All data from Supabase. No static JSON fallback.
 * Components call these functions; never touch Supabase directly.
 */
import { supabase, isSupabaseConfigured } from './supabase';
import type { SupabaseClient } from '@supabase/supabase-js';
import type { Database, TableRow } from './database.types';
import type {
  DashboardData,
  Position,
  Thesis,
  Doc,
  BenchmarkHistoryMap,
  DeltaRequestMeta,
  ResearchChangelogMeta,
  DashboardPositionEvent,
  ServerPortfolioMetrics,
  HoldingTechnicalSnapshot,
  MacroSeriesPoint,
  ThesisHistoryPoint,
  PositionHistoryRow,
  PipelineObservabilityBundle,
  PipelineTickerDoc,
  PositionPriceChartData,
} from './types';
import { renderDigestMarkdownFromSnapshot, type DigestSnapshot } from './render-digest-from-snapshot';
import { renderDocumentMarkdownFromPayload } from './render-document-from-payload';
import { DASHBOARD_BENCHMARK_TICKERS, sortTickerUniverse } from './benchmark-tickers';
import { extractSnapshotContextBullets } from './snapshot-context';
import { MACRO_PREVIEW_SERIES_IDS } from './macro-curated';
import { getDocLibraryTier } from './library-doc-tier';

type SB = SupabaseClient<Database>;

async function querySupabase<T>(
  queryFn: (sb: SB) => PromiseLike<{ data: T | null; error: unknown }>,
  { retries = 3, delayMs = 500 }: { retries?: number; delayMs?: number } = {}
): Promise<T> {
  if (!isSupabaseConfigured() || !supabase) {
    throw new Error(
      'Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.'
    );
  }
  let lastError: unknown;
  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      const { data, error } = await queryFn(supabase);
      if (error) throw error;
      if (data === null) throw new Error('No data returned');
      return data;
    } catch (err) {
      lastError = err;
      if (attempt < retries - 1) {
        await new Promise((r) => setTimeout(r, delayMs * Math.pow(2, attempt)));
      }
    }
  }
  throw lastError;
}

function parseDeltaPayload(payload: unknown): DeltaRequestMeta {
  const empty: DeltaRequestMeta = { changed_paths: [], baseline_date: null, op_paths: [] };
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return empty;
  const o = payload as Record<string, unknown>;
  const cp = o.changed_paths;
  const changed_paths = Array.isArray(cp) ? cp.filter((x): x is string => typeof x === 'string') : [];
  const baseline_date = typeof o.baseline_date === 'string' ? o.baseline_date : null;
  const op_paths: string[] = [];
  const ops = o.ops;
  if (Array.isArray(ops)) {
    for (const op of ops) {
      if (op && typeof op === 'object' && typeof (op as Record<string, unknown>).path === 'string') {
        op_paths.push(String((op as Record<string, unknown>).path));
      }
    }
  }
  return { changed_paths, baseline_date, op_paths };
}

function parseResearchChangelogPayload(payload: unknown): ResearchChangelogMeta {
  const empty: ResearchChangelogMeta = { items: [], baseline_date: null };
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return empty;
  const o = payload as Record<string, unknown>;
  if (String(o.doc_type || '') !== 'research_changelog') return empty;
  const raw = o.items;
  const items: ResearchChangelogMeta['items'] = [];
  if (Array.isArray(raw)) {
    for (const it of raw) {
      if (!it || typeof it !== 'object' || Array.isArray(it)) continue;
      const r = it as Record<string, unknown>;
      const tk = typeof r.target_document_key === 'string' ? r.target_document_key : '';
      if (!tk) continue;
      items.push({
        target_document_key: tk,
        status: typeof r.status === 'string' ? r.status : '',
        one_line_change: typeof r.one_line_change === 'string' ? r.one_line_change : undefined,
        severity: typeof r.severity === 'string' ? r.severity : undefined,
      });
    }
  }
  const baseline_date = typeof o.baseline_date === 'string' ? o.baseline_date : null;
  return { items, baseline_date };
}

export type LibraryDocumentView =
  | 'markdown'
  | 'rebalance'
  | 'delta_request'
  | 'deliberation'
  | 'evolution_sources'
  | 'opportunity_screener'
  | 'diffable';

export interface LibraryDocumentResult {
  id: string;
  date: string;
  document_key: string;
  view: LibraryDocumentView;
  markdown: string;
  payload: Record<string, unknown> | null;
}

function resolveLibraryDocumentView(document_key: string, payload: unknown): LibraryDocumentView {
  const key = (document_key || '').toLowerCase();
  const p =
    payload && typeof payload === 'object' && !Array.isArray(payload)
      ? (payload as Record<string, unknown>)
      : null;
  const dt = String(p?.doc_type || '');

  if (key === 'rebalance-decision.json' || dt === 'rebalance_decision') return 'rebalance';
  if (key === 'delta-request.json' || dt === 'delta_request') return 'delta_request';
  if (key === 'opportunity-screener.json' || dt === 'opportunity_screen') return 'opportunity_screener';
  const isDeliberationTranscriptPath =
    dt === 'deliberation_transcript' ||
    (key.includes('deliberation-transcript/') && !key.includes('deliberation-transcript-index'));
  const isLegacyDeliberationArtifact =
    key === 'deliberation.json' ||
    key.endsWith('/deliberation.json') ||
    key === 'deliberation.md' ||
    key.endsWith('/deliberation.md');
  if (isDeliberationTranscriptPath || isLegacyDeliberationArtifact) {
    return 'deliberation';
  }
  if (dt === 'evolution_sources') return 'evolution_sources';
  if (
    dt === 'research_changelog' ||
    dt === 'document_delta' ||
    dt === 'research_baseline_manifest'
  ) {
    return 'markdown';
  }

  // Deliberation session index: markdown view (structured table of per-ticker sessions)
  if (key.startsWith('deliberation-transcript-index/') || dt === 'deliberation_session_index') {
    return 'markdown';
  }

  // Delta research docs and portfolio date-keyed docs get the diff view
  if (key.startsWith('deltas/')) return 'diffable';
  const PORTFOLIO_DATE_PREFIXES = [
    'market-thesis-exploration/',
    'thesis-vehicle-map/',
    'pm-allocation-memo/',
    'asset-rec/',
  ];
  if (PORTFOLIO_DATE_PREFIXES.some((pfx) => key.startsWith(pfx))) return 'diffable';

  return 'markdown';
}

function payloadAsRecord(raw: unknown): Record<string, unknown> | null {
  if (raw != null && typeof raw === 'object' && !Array.isArray(raw)) {
    return raw as Record<string, unknown>;
  }
  return null;
}

function tickerFromNestedDocKey(document_key: string, folder: string, date: string): string {
  const pref = `${folder}/${date}/`;
  const low = document_key.toLowerCase();
  const p = pref.toLowerCase();
  const idx = low.indexOf(p);
  if (idx === -1) {
    const tail = document_key.split('/').pop() || '';
    return tail.replace(/\.json$/i, '') || '?';
  }
  return document_key.slice(idx + pref.length).replace(/\.json$/i, '') || '?';
}

async function fetchPipelineObservabilityForDate(dashboardDate: string): Promise<PipelineObservabilityBundle> {
  const sb = supabase as SB;
  const kExpl = `market-thesis-exploration/${dashboardDate}.json`;
  const kMap = `thesis-vehicle-map/${dashboardDate}.json`;
  const kMemo = `pm-allocation-memo/${dashboardDate}.json`;
  const kIdx = `deliberation-transcript-index/${dashboardDate}.json`;
  const [exactRes, arRes, delRes] = await Promise.all([
    sb
      .from('documents')
      .select('document_key, payload')
      .eq('date', dashboardDate)
      .in('document_key', [kExpl, kMap, kMemo, kIdx]),
    sb
      .from('documents')
      .select('document_key, payload')
      .eq('date', dashboardDate)
      .ilike('document_key', `asset-recommendations/${dashboardDate}/%`),
    sb
      .from('documents')
      .select('document_key, payload')
      .eq('date', dashboardDate)
      .ilike('document_key', `deliberation-transcript/${dashboardDate}/%`),
  ]);
  if (exactRes.error) console.warn('Supabase pipeline exact docs:', exactRes.error);
  if (arRes.error) console.warn('Supabase asset-recommendation docs:', arRes.error);
  if (delRes.error) console.warn('Supabase deliberation-transcript docs:', delRes.error);

  const byKey = new Map<string, unknown>();
  for (const row of (exactRes.data ?? []) as Pick<TableRow<'documents'>, 'document_key' | 'payload'>[]) {
    if (row?.document_key != null && row.payload != null) byKey.set(row.document_key, row.payload);
  }
  const get = (dk: string): Record<string, unknown> | null => payloadAsRecord(byKey.get(dk));

  const asset_recommendations: PipelineTickerDoc[] = [];
  for (const row of (arRes.data ?? []) as Pick<TableRow<'documents'>, 'document_key' | 'payload'>[]) {
    if (!row?.document_key) continue;
    const pl = payloadAsRecord(row.payload);
    if (!pl) continue;
    asset_recommendations.push({
      document_key: row.document_key,
      ticker: tickerFromNestedDocKey(row.document_key, 'asset-recommendations', dashboardDate),
      payload: pl,
    });
  }
  asset_recommendations.sort((a, b) => a.ticker.localeCompare(b.ticker));

  const deliberation_transcripts: PipelineTickerDoc[] = [];
  for (const row of (delRes.data ?? []) as Pick<TableRow<'documents'>, 'document_key' | 'payload'>[]) {
    if (!row?.document_key) continue;
    const pl = payloadAsRecord(row.payload);
    if (!pl) continue;
    deliberation_transcripts.push({
      document_key: row.document_key,
      ticker: tickerFromNestedDocKey(row.document_key, 'deliberation-transcript', dashboardDate),
      payload: pl,
    });
  }
  deliberation_transcripts.sort((a, b) => a.ticker.localeCompare(b.ticker));

  return {
    snapshot_date: dashboardDate,
    market_thesis_exploration: get(kExpl),
    thesis_vehicle_map: get(kMap),
    pm_allocation_memo: get(kMemo),
    deliberation_session_index: get(kIdx),
    deliberation_transcripts,
    asset_recommendations,
  };
}

/**
 * Load market thesis exploration + thesis vehicle map payloads for any run date (lazy / historical).
 * Uses the same document_key convention as the dashboard pipeline bundle.
 */
export async function fetchThesisPipelinePayloadsForDate(runDate: string): Promise<{
  market_thesis_exploration: Record<string, unknown> | null;
  thesis_vehicle_map: Record<string, unknown> | null;
}> {
  if (!isSupabaseConfigured() || !supabase) {
    return { market_thesis_exploration: null, thesis_vehicle_map: null };
  }
  const kExpl = `market-thesis-exploration/${runDate}.json`;
  const kMap = `thesis-vehicle-map/${runDate}.json`;
  const { data, error } = await supabase
    .from('documents')
    .select('document_key, payload')
    .eq('date', runDate)
    .in('document_key', [kExpl, kMap]);
  if (error) {
    console.warn('fetchThesisPipelinePayloadsForDate:', error);
    return { market_thesis_exploration: null, thesis_vehicle_map: null };
  }
  let market_thesis_exploration: Record<string, unknown> | null = null;
  let thesis_vehicle_map: Record<string, unknown> | null = null;
  for (const row of (data ?? []) as Pick<TableRow<'documents'>, 'document_key' | 'payload'>[]) {
    const pl = payloadAsRecord(row.payload);
    if (row.document_key === kExpl) market_thesis_exploration = pl;
    if (row.document_key === kMap) thesis_vehicle_map = pl;
  }
  return { market_thesis_exploration, thesis_vehicle_map };
}

/** PostgREST page size for Activity ledger (avoid 10k truncation on dense HOLD history). */
const POSITION_EVENTS_PAGE = 2500;
const POSITION_EVENTS_MAX = 80000;

type PositionEventRowPick = Pick<
  TableRow<'position_events'>,
  | 'date'
  | 'ticker'
  | 'event'
  | 'weight_pct'
  | 'prev_weight_pct'
  | 'weight_change_pct'
  | 'price'
  | 'thesis_id'
  | 'reason'
>;

async function fetchPositionEventsForDashboard(): Promise<PositionEventRowPick[]> {
  if (!supabase) return [];
  const out: PositionEventRowPick[] = [];
  for (let offset = 0; offset < POSITION_EVENTS_MAX; offset += POSITION_EVENTS_PAGE) {
    const { data, error } = await supabase
      .from('position_events')
      .select(
        'date,ticker,event,weight_pct,prev_weight_pct,weight_change_pct,price,thesis_id,reason'
      )
      .order('date', { ascending: false })
      .range(offset, offset + POSITION_EVENTS_PAGE - 1);
    if (error) {
      console.error('Supabase position_events query:', error);
      break;
    }
    const chunk = (data ?? []) as PositionEventRowPick[];
    out.push(...chunk);
    if (chunk.length < POSITION_EVENTS_PAGE) break;
  }
  return out;
}

/**
 * Load the complete dashboard data assembled from Supabase tables.
 */
export async function getFullDashboardData(): Promise<DashboardData> {
  if (!isSupabaseConfigured() || !supabase) {
    throw new Error(
      'Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.'
    );
  }

  // Benchmarks are used for sparklines/tiles; we only need a recent window.
  // PostgREST defaults to paginating results, and ordering by oldest-first can
  // return only the longest-lived ticker (e.g. SPY) in the first page.
  const benchCutoff = (() => {
    const d = new Date();
    d.setUTCDate(d.getUTCDate() - 180);
    return d.toISOString().slice(0, 10);
  })();

  const [
    snapshotRes, positionsRes, thesesRes, navRes,
    benchRes, metricsRes, docsRes, deltaDocsRes, changelogDocsRes, tickerViewRes, snapshotRunTypesRes,
  ] = await Promise.all([
    supabase.from('daily_snapshots').select('*').order('date', { ascending: false }).limit(1).single(),
    supabase.from('positions').select('*').order('date', { ascending: false }).limit(1000),
    supabase.from('theses').select('*').order('date', { ascending: false }).limit(50),
    supabase.from('nav_history').select('*').order('date', { ascending: true }),
    supabase
      .from('price_history')
      .select('date, ticker, close')
      .in('ticker', [...DASHBOARD_BENCHMARK_TICKERS])
      .gte('date', benchCutoff)
      .order('date', { ascending: true }),
    supabase.from('portfolio_metrics').select('*').order('date', { ascending: false }).limit(1).single(),
    supabase.from('documents')
      .select('id, date, title, doc_type, phase, category, segment, sector, run_type, document_key')
      .order('date', { ascending: false })
      .limit(500),
    supabase
      .from('documents')
      .select('date, payload')
      .eq('document_key', 'delta-request.json')
      .order('date', { ascending: false })
      .limit(400),
    supabase
      .from('documents')
      .select('date, payload')
      .ilike('document_key', 'research-changelog/%')
      .order('date', { ascending: false })
      .limit(400),
    supabase.from('price_history_tickers').select('ticker'),
    supabase.from('daily_snapshots').select('date, run_type').order('date', { ascending: false }).limit(500),
  ]);

  const eventsRaw = await fetchPositionEventsForDashboard();

  if (docsRes.error) {
    console.error('Supabase documents query:', docsRes.error);
  }
  if (deltaDocsRes.error) {
    console.error('Supabase delta-request documents query:', deltaDocsRes.error);
  }
  if (changelogDocsRes.error) {
    console.error('Supabase research-changelog documents query:', changelogDocsRes.error);
  }

  const delta_request_meta_by_date: Record<string, DeltaRequestMeta> = {};
  const deltaRows = (deltaDocsRes.data ?? []) as Pick<TableRow<'documents'>, 'date' | 'payload'>[];
  for (const row of deltaRows) {
    if (!row?.date) continue;
    delta_request_meta_by_date[row.date] = parseDeltaPayload(row.payload);
  }

  const research_changelog_by_date: Record<string, ResearchChangelogMeta> = {};
  const changelogRows = (changelogDocsRes.data ?? []) as Pick<TableRow<'documents'>, 'date' | 'payload'>[];
  for (const row of changelogRows) {
    if (!row?.date) continue;
    research_changelog_by_date[row.date] = parseResearchChangelogPayload(row.payload);
  }
  if (benchRes.error) {
    console.error('Supabase price_history (benchmarks) query:', benchRes.error);
  }
  if (tickerViewRes.error) {
    console.warn('Supabase price_history_tickers view (apply migration 018 if missing):', tickerViewRes.error);
  }
  if (snapshotRunTypesRes.error) {
    console.error('Supabase daily_snapshots run_type query:', snapshotRunTypesRes.error);
  }

  const snapshot_run_type_by_date: Record<string, 'baseline' | 'delta'> = {};
  const snapRunRows = (snapshotRunTypesRes.data ?? []) as Pick<
    TableRow<'daily_snapshots'>,
    'date' | 'run_type'
  >[];
  for (const row of snapRunRows) {
    if (!row?.date) continue;
    const rt = String(row.run_type || '').toLowerCase();
    if (rt === 'baseline' || rt === 'delta') snapshot_run_type_by_date[row.date] = rt;
  }

  const snapshot: TableRow<'daily_snapshots'> = snapshotRes.data ?? ({} as TableRow<'daily_snapshots'>);
  const rawSnapshotJson = snapshot.snapshot;
  const snapshotJson: DigestSnapshot | null =
    rawSnapshotJson != null && typeof rawSnapshotJson === 'object' && !Array.isArray(rawSnapshotJson)
      ? (rawSnapshotJson as DigestSnapshot)
      : null;
  const allPositions: TableRow<'positions'>[] = positionsRes.data ?? [];
  const allTheses: TableRow<'theses'>[] = thesesRes.data ?? [];
  const navHistory: TableRow<'nav_history'>[] = navRes.data ?? [];
  const benchRows: Pick<TableRow<'price_history'>, 'date' | 'ticker' | 'close'>[] =
    benchRes.data ?? [];
  const metricsRow = metricsRes.data as TableRow<'portfolio_metrics'> | null;
  const metrics: TableRow<'portfolio_metrics'> =
    metricsRes.error || !metricsRow ? ({} as TableRow<'portfolio_metrics'>) : metricsRow;

  const position_events: DashboardPositionEvent[] = (
    eventsRaw as TableRow<'position_events'>[]
  )
    .map((e) => ({
      date: e.date,
      ticker: e.ticker,
      event: e.event,
      weight_pct: e.weight_pct != null ? Number(e.weight_pct) : null,
      prev_weight_pct: e.prev_weight_pct != null ? Number(e.prev_weight_pct) : null,
      weight_change_pct: e.weight_change_pct != null ? Number(e.weight_change_pct) : null,
      price: e.price != null ? Number(e.price) : null,
      thesis_id: e.thesis_id ?? null,
      reason: e.reason ?? null,
    }))
    .sort((a, b) => b.date.localeCompare(a.date) || a.ticker.localeCompare(b.ticker));

  const server_portfolio_metrics: ServerPortfolioMetrics | null =
    metrics.date != null && String(metrics.date).length > 0
      ? {
          date: metrics.date,
          as_of_date: metrics.as_of_date ?? null,
          pnl_pct: metrics.pnl_pct != null ? Number(metrics.pnl_pct) : null,
          sharpe: metrics.sharpe != null ? Number(metrics.sharpe) : null,
          volatility: metrics.volatility != null ? Number(metrics.volatility) : null,
          max_drawdown: metrics.max_drawdown != null ? Number(metrics.max_drawdown) : null,
          alpha: metrics.alpha != null ? Number(metrics.alpha) : null,
          cash_pct: metrics.cash_pct != null ? Number(metrics.cash_pct) : null,
          total_invested: metrics.total_invested != null ? Number(metrics.total_invested) : null,
          generated_at: metrics.generated_at ?? null,
        }
      : null;
  const rawDocs: Pick<
    TableRow<'documents'>,
    'id' | 'date' | 'title' | 'doc_type' | 'phase' | 'category' | 'segment' | 'sector' | 'run_type' | 'document_key'
  >[] = docsRes.data ?? [];

  const posDates = [...new Set(allPositions.map((p) => p.date))];
  const latestPosDate = posDates.length ? posDates[0] : null;
  const prevPosDate = posDates.length > 1 ? posDates[1] : null;
  const currentPositions = latestPosDate ? allPositions.filter((p) => p.date === latestPosDate) : [];
  const prevPositions = prevPosDate ? allPositions.filter((p) => p.date === prevPosDate) : [];
  const prevWeightByTicker = new Map(prevPositions.map((p) => [p.ticker, Number(p.weight_pct ?? 0)]));

  const latestThesisDate = allTheses.length ? allTheses[0].date : null;
  const currentTheses = latestThesisDate
    ? allTheses.filter((t) => t.date === latestThesisDate)
    : [];

  // Parse regime — stored as JSONB (may come back as string or object)
  const rawRegime = snapshot.regime;
  const regime: Record<string, unknown> =
    typeof rawRegime === 'string'
      ? (JSON.parse(rawRegime) as Record<string, unknown>)
      : typeof rawRegime === 'object' && rawRegime !== null
      ? (rawRegime as Record<string, unknown>)
      : {};

  // Build benchmark map
  const benchmarks: BenchmarkHistoryMap = {};
  for (const row of benchRows) {
    if (!benchmarks[row.ticker]) {
      benchmarks[row.ticker] = { current: null, history: [] };
    }
    benchmarks[row.ticker].history.push({ date: row.date, price: Number(row.close) });
  }
  for (const bData of Object.values(benchmarks)) {
    if (bData.history.length) {
      bData.current = bData.history[bData.history.length - 1].price;
    }
  }

  const tickerViewRows = (tickerViewRes.data ?? []) as { ticker: string }[];
  let price_history_tickers: string[] = [];
  if (!tickerViewRes.error && tickerViewRows.length > 0) {
    price_history_tickers = sortTickerUniverse(tickerViewRows.map((r) => r.ticker));
  } else {
    const fb = new Set<string>();
    for (const row of benchRows) {
      fb.add(row.ticker);
    }
    for (const t of DASHBOARD_BENCHMARK_TICKERS) {
      fb.add(t);
    }
    price_history_tickers = sortTickerUniverse([...fb]);
  }

  const theses: Thesis[] = currentTheses.map((t) => ({
    id: t.thesis_id,
    name: t.name,
    vehicle: t.vehicle,
    invalidation: t.invalidation,
    status: t.status,
    notes: t.notes,
  }));

  const docs: Doc[] = rawDocs.map((d) => ({
    id: d.id,
    date: d.date,
    title: d.title,
    type: d.doc_type,
    phase: d.phase,
    category: d.category,
    segment: d.segment,
    sector: d.sector,
    runType: d.run_type,
    path: d.document_key,
    filename: d.document_key?.split('/').pop() || d.document_key,
  }));

  // Proposed positions from the published digest snapshot (DB-first).
  const proposedPositions: { ticker: string; weight_pct: number; action?: string }[] = (() => {
    const p = snapshotJson?.portfolio as Record<string, unknown> | undefined;
    const pp = p?.proposed_positions;
    if (!Array.isArray(pp)) return [];
    return pp
      .map((x) => {
        if (!x || typeof x !== 'object') return null;
        const o = x as Record<string, unknown>;
        const ticker = String(o.ticker || '').trim().toUpperCase();
        const weight = Number(o.weight_pct ?? NaN);
        if (!ticker || Number.isNaN(weight)) return null;
        return { ticker, weight_pct: weight, action: o.action != null ? String(o.action) : undefined };
      })
      .filter(Boolean) as { ticker: string; weight_pct: number; action?: string }[];
  })();

  /** Digest target weight by ticker — drives target vs actual in the allocations table. */
  const targetWeightByTicker = new Map<string, number>(
    proposedPositions.map((p) => [p.ticker, Number(p.weight_pct ?? 0)])
  );

  // Treat proposed_positions as executed immediately (post-trade = current).
  const effectiveCurrentPositions: TableRow<'positions'>[] = proposedPositions.length
    ? proposedPositions
        .filter((p) => Number(p.weight_pct ?? 0) > 0)
        .map((p) => {
          const base = currentPositions.find((cp) => cp.ticker === p.ticker);
          return {
            ...(base || ({
              date: latestPosDate,
              ticker: p.ticker,
              name: p.ticker,
              category: null,
              weight_pct: 0,
              entry_date: null,
              entry_price: null,
              current_price: null,
              rationale: null,
              thesis_id: null,
              pm_notes: null,
              unrealized_pnl_pct: null,
              day_change_pct: null,
              since_entry_return_pct: null,
              contribution_pct: null,
              metrics_as_of: null,
            } as unknown as TableRow<'positions'>)),
            ticker: p.ticker,
            weight_pct: Number(p.weight_pct ?? 0),
          } as TableRow<'positions'>;
        })
    : currentPositions;

  // Fill position prices/P&L from price_history when positions table is sparse.
  const posTickers = [...new Set(effectiveCurrentPositions.map((p) => p.ticker))];
  const entryDatesByTicker = new Map(
    effectiveCurrentPositions
      .map((p) => [p.ticker, p.entry_date] as const)
      .filter(([, d]) => !!d)
  );

  const priceRows = posTickers.length
    ? await querySupabase<
        Pick<TableRow<'price_history'>, 'date' | 'ticker' | 'close'>[]
      >((sb) =>
        sb
          .from('price_history')
          .select('date, ticker, close')
          .in('ticker', posTickers)
          // fetch a small recent window + any entry dates
          .order('date', { ascending: false })
          .limit(5000)
      )
    : [];

  const closesByTicker = new Map<string, Array<{ date: string; close: number }>>();
  for (const r of priceRows) {
    const arr = closesByTicker.get(r.ticker) || [];
    arr.push({ date: r.date, close: Number(r.close) });
    closesByTicker.set(r.ticker, arr);
  }
  for (const [t, arr] of closesByTicker) {
    arr.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
    closesByTicker.set(t, arr);
  }

  function closeOnOrAfter(ticker: string, date: string): number | null {
    const arr = closesByTicker.get(ticker);
    if (!arr?.length) return null;
    for (const p of arr) {
      if (p.date >= date) return p.close;
    }
    return null;
  }

  function latestClose(ticker: string): { curr: number | null; prev: number | null } {
    const arr = closesByTicker.get(ticker);
    if (!arr?.length) return { curr: null, prev: null };
    const curr = arr[arr.length - 1]?.close ?? null;
    const prev = arr.length > 1 ? arr[arr.length - 2]?.close ?? null : null;
    return { curr, prev };
  }

  const totalInvested = effectiveCurrentPositions.reduce(
    (s, p) => s + Number(p.weight_pct ?? 0),
    0
  );

  /** Earliest OPEN/ADD mark for each ticker — used when `positions.entry_price` is null (digest-only rows). */
  const firstOpenAddPriceByTicker = (() => {
    const m = new Map<string, number>();
    const rows: Array<{ t: string; date: string; price: number }> = [];
    for (const e of position_events) {
      if (e.event !== 'OPEN' && e.event !== 'ADD') continue;
      if (e.price == null || Number.isNaN(Number(e.price))) continue;
      rows.push({
        t: e.ticker.toUpperCase(),
        date: e.date,
        price: Number(e.price),
      });
    }
    rows.sort((a, b) => a.date.localeCompare(b.date) || a.t.localeCompare(b.t));
    for (const r of rows) {
      if (!m.has(r.t)) m.set(r.t, r.price);
    }
    return m;
  })();

  function resolvedEntryPrice(px: TableRow<'positions'>): number | null {
    if (px.entry_price != null && !Number.isNaN(Number(px.entry_price))) {
      return Number(px.entry_price);
    }
    const fromEv = firstOpenAddPriceByTicker.get(String(px.ticker).toUpperCase());
    if (fromEv != null && fromEv > 0) return fromEv;
    if (px.entry_date) return closeOnOrAfter(px.ticker, px.entry_date);
    return null;
  }

  const positions: Position[] = effectiveCurrentPositions.map((p) => ({
    // Prices: prefer explicit position fields; else derive from price_history
    ticker: p.ticker,
    name: p.name ?? p.ticker,
    type: 'LONG' as const,
    weight_actual: Number(p.weight_pct ?? 0),
    weight_target: targetWeightByTicker.has(p.ticker) ? targetWeightByTicker.get(p.ticker)! : null,
    weight_delta:
      latestPosDate && prevPosDate
        ? Number(p.weight_pct ?? 0) - (prevWeightByTicker.get(p.ticker) ?? 0)
        : null,
    current_price: p.current_price != null ? Number(p.current_price) : latestClose(p.ticker).curr,
    entry_price: resolvedEntryPrice(p),
    entry_date: p.entry_date ?? null,
    rationale: p.rationale ?? '',
    thesis_ids: p.thesis_id ? [p.thesis_id] : [],
    category: p.category ?? '',
    pm_notes: p.pm_notes ?? '',
    stats: {},
    unrealized_pnl_pct: (() => {
      if (p.unrealized_pnl_pct != null) return Number(p.unrealized_pnl_pct);
      const entry = resolvedEntryPrice(p);
      const curr =
        p.current_price != null ? Number(p.current_price) : latestClose(p.ticker).curr;
      if (!entry || !curr || entry <= 0) return null;
      return ((curr - entry) / entry) * 100;
    })(),
    day_change_pct: (() => {
      if (p.day_change_pct != null) return Number(p.day_change_pct);
      const { curr, prev } = latestClose(p.ticker);
      if (!curr || !prev || prev <= 0) return null;
      return ((curr - prev) / prev) * 100;
    })(),
    since_entry_return_pct: (() => {
      if (p.since_entry_return_pct != null) return Number(p.since_entry_return_pct);
      const entry = resolvedEntryPrice(p);
      const curr =
        p.current_price != null ? Number(p.current_price) : latestClose(p.ticker).curr;
      if (!entry || !curr || entry <= 0) return null;
      return ((curr - entry) / entry) * 100;
    })(),
    contribution_pct: (() => {
      if (p.contribution_pct != null) return Number(p.contribution_pct);
      const entry = resolvedEntryPrice(p);
      const curr =
        p.current_price != null ? Number(p.current_price) : latestClose(p.ticker).curr;
      if (!entry || !curr || entry <= 0) return null;
      const pnlPct = ((curr - entry) / entry) * 100;
      return (pnlPct * Number(p.weight_pct ?? 0)) / 100;
    })(),
    metrics_as_of: p.metrics_as_of ?? null,
  }));

  const rebalanceActions = proposedPositions.map((p) => {
    const curr = Number(currentPositions.find((cp) => cp.ticker === p.ticker)?.weight_pct ?? 0);
    const rec = Number(p.weight_pct ?? 0);
    const action =
      rec === 0 && curr > 0 ? 'EXIT' :
      rec > 0 && curr === 0 ? 'OPEN' :
      Math.abs(rec - curr) >= 0.01 ? (rec < curr ? 'TRIM' : 'ADD') :
      'HOLD';
    return { ticker: p.ticker, current_pct: curr, recommended_pct: rec, action };
  });

  const snapshot_context_bullets = extractSnapshotContextBullets(
    snapshot.segment_biases,
    snapshot.market_data
  );

  const runTypeRaw = String(snapshot.run_type || '').toLowerCase();
  const latest_snapshot_run_type: 'baseline' | 'delta' | null =
    runTypeRaw === 'baseline' || runTypeRaw === 'delta' ? runTypeRaw : null;

  let holding_technicals: Record<string, HoldingTechnicalSnapshot> = {};
  const macro_series_preview: Record<string, MacroSeriesPoint[]> = {};

  if (posTickers.length > 0 || MACRO_PREVIEW_SERIES_IDS.length > 0) {
    const [techRes, macroRes] = await Promise.all([
      posTickers.length > 0
        ? supabase
            .from('price_technicals')
            .select('date,ticker,rsi_14,pct_vs_sma50')
            .in('ticker', posTickers)
            .order('date', { ascending: false })
            .limit(400)
        : Promise.resolve({ data: null as unknown, error: null }),
      supabase
        .from('macro_series_observations')
        .select('series_id,obs_date,value')
        .in('series_id', MACRO_PREVIEW_SERIES_IDS)
        .order('obs_date', { ascending: false })
        .limit(800),
    ]);

    if (techRes.error) {
      console.warn('Supabase price_technicals query:', techRes.error);
    } else if (techRes.data && Array.isArray(techRes.data)) {
      const seen = new Set<string>();
      for (const row of techRes.data as Pick<
        TableRow<'price_technicals'>,
        'date' | 'ticker' | 'rsi_14' | 'pct_vs_sma50'
      >[]) {
        if (!row?.ticker || seen.has(row.ticker)) continue;
        seen.add(row.ticker);
        holding_technicals[row.ticker] = {
          date: row.date,
          rsi_14: row.rsi_14 != null ? Number(row.rsi_14) : null,
          pct_vs_sma50: row.pct_vs_sma50 != null ? Number(row.pct_vs_sma50) : null,
        };
        if (seen.size >= posTickers.length) break;
      }
    }

    if (macroRes.error) {
      console.warn('Supabase macro_series_observations query:', macroRes.error);
    } else if (macroRes.data && Array.isArray(macroRes.data)) {
      const bySeries: Record<string, MacroSeriesPoint[]> = {};
      for (const row of macroRes.data as Pick<
        TableRow<'macro_series_observations'>,
        'series_id' | 'obs_date' | 'value'
      >[]) {
        if (!row?.series_id) continue;
        const sid = String(row.series_id);
        if (!bySeries[sid]) bySeries[sid] = [];
        if (bySeries[sid].length >= 60) continue;
        bySeries[sid].push({
          obs_date: row.obs_date,
          value: row.value != null ? Number(row.value) : null,
        });
      }
      for (const [sid, pts] of Object.entries(bySeries)) {
        macro_series_preview[sid] = [...pts].sort((a, b) =>
          a.obs_date < b.obs_date ? -1 : a.obs_date > b.obs_date ? 1 : 0
        );
      }
    }
  }

  const dashboardDate = snapshot.date ?? latestPosDate ?? null;
  let pipeline_observability: PipelineObservabilityBundle | null = null;
  if (dashboardDate) {
    pipeline_observability = await fetchPipelineObservabilityForDate(dashboardDate);
  }

  return {
    portfolio: {
      meta: {
        name: 'Market Digest Dynamic Portfolio',
        base_currency: 'CAD',
        last_updated: snapshot.date ?? latestPosDate,
        benchmarks: Object.keys(benchmarks),
        latest_snapshot_run_type,
      },
      snapshots: navHistory.map((h) => ({
        date: h.date,
        nav: Number(h.nav),
        cash_pct: h.cash_pct != null ? Number(h.cash_pct) : null,
        invested_pct: h.invested_pct != null ? Number(h.invested_pct) : null,
      })),
      strategy: {
        regime: String(regime.label ?? regime.regime ?? 'Unknown'),
        regime_label: String(regime.bias ?? regime.regime_label ?? 'neutral'),
        summary: String(regime.summary ?? ''),
        actionable: (snapshot.actionable ?? []) as string[],
        risks: (snapshot.risks ?? []) as string[],
        theses,
        next_review: 'Daily',
      },
    },
    positions,
    portfolio_management: {
      current_positions: effectiveCurrentPositions.map((p) => ({
        ticker: p.ticker,
        name: p.name ?? p.ticker,
        category: p.category ?? '',
        weight_pct: Number(p.weight_pct ?? 0),
        thesis_ids: p.thesis_id ? [p.thesis_id] : [],
        entry_date: p.entry_date ?? null,
        entry_price_usd: resolvedEntryPrice(p),
        notes: p.pm_notes ?? '',
      })),
      proposed_positions: proposedPositions.map((p) => ({
        ticker: p.ticker,
        weight_pct: p.weight_pct,
        action: p.action || '',
      })),
      constraints: {},
      rebalance_actions: rebalanceActions,
      pnl_fx_impact: null,
    },
    position_history: allPositions.map((p) => ({
      date: p.date,
      ticker: p.ticker,
      weight_pct: Number(p.weight_pct ?? 0),
      category: p.category ?? null,
      thesis_id: p.thesis_id ?? null,
    })),
    position_events,
    ratios: [],
    docs,
    delta_request_meta_by_date,
    research_changelog_by_date,
    snapshot_run_type_by_date,
    benchmarks,
    price_history_tickers,
    server_portfolio_metrics,
    calculated: {
      portfolio_pnl: metrics.pnl_pct != null ? Number(metrics.pnl_pct) : 0,
      total_invested:
        proposedPositions.length > 0
          ? totalInvested
          : (metrics.total_invested != null ? Number(metrics.total_invested) : totalInvested),
      cash_pct:
        proposedPositions.length > 0
          ? 100 - totalInvested
          : (metrics.cash_pct != null ? Number(metrics.cash_pct) : 100 - totalInvested),
      sharpe: metrics.sharpe != null ? Number(metrics.sharpe) : 0,
      volatility: metrics.volatility != null ? Number(metrics.volatility) : 0,
      max_drawdown: metrics.max_drawdown != null ? Number(metrics.max_drawdown) : 0,
      alpha: metrics.alpha != null ? Number(metrics.alpha) : 0,
    },
    snapshot_context_bullets,
    holding_technicals,
    macro_series_preview,
    pipeline_observability,
  };
}

/**
 * Historical rows for one thesis_id from the theses table (status / name evolution).
 */
export async function getThesisHistoryById(thesisId: string): Promise<ThesisHistoryPoint[]> {
  if (!isSupabaseConfigured() || !supabase) return [];
  const id = thesisId.trim();
  if (!id) return [];
  const { data, error } = await supabase
    .from('theses')
    .select('date,thesis_id,name,status,notes')
    .eq('thesis_id', id)
    .order('date', { ascending: true });
  if (error) {
    console.error('Supabase theses history query:', error);
    return [];
  }
  return ((data ?? []) as Pick<TableRow<'theses'>, 'date' | 'thesis_id' | 'name' | 'status' | 'notes'>[]).map(
    (r) => ({
      date: r.date,
      thesis_id: r.thesis_id,
      name: r.name,
      status: r.status ?? null,
      notes: r.notes ?? null,
    })
  );
}

/** Sum position weights per calendar date for a single thesis (from position_history rows). */
export function aggregateThesisWeightsByDate(
  positionHistory: PositionHistoryRow[],
  thesisId: string
): { date: string; weight_pct: number }[] {
  const id = thesisId.trim();
  if (!id || id === '_unlinked') return [];
  const byDate = new Map<string, number>();
  for (const r of positionHistory) {
    if (r.thesis_id !== id) continue;
    const d = r.date;
    const w = Number(r.weight_pct ?? 0);
    byDate.set(d, (byDate.get(d) ?? 0) + w);
  }
  return [...byDate.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([date, weight_pct]) => ({ date, weight_pct }));
}

/** Sum position weights per calendar date for rows with no thesis_id (unlinked sleeve). */
export function aggregateUnlinkedWeightsByDate(
  positionHistory: PositionHistoryRow[]
): { date: string; weight_pct: number }[] {
  const byDate = new Map<string, number>();
  for (const r of positionHistory) {
    if (r.thesis_id != null && r.thesis_id !== '') continue;
    const d = r.date;
    const w = Number(r.weight_pct ?? 0);
    byDate.set(d, (byDate.get(d) ?? 0) + w);
  }
  return [...byDate.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([date, weight_pct]) => ({ date, weight_pct }));
}

export type ThesisRelatedDocLink = { document_key: string; date: string; label: string };

/**
 * Portfolio `documents` rows that relate to a thesis: global thesis artifacts on recent dates
 * plus per-ticker PM docs whose path contains a ticker linked to this thesis.
 */
export function collectThesisRelatedDocLinks(
  docs: Doc[] | undefined,
  opts: { tickers: Set<string>; recentDates: string[] }
): ThesisRelatedDocLink[] {
  const { tickers, recentDates } = opts;
  const dateSet = new Set(recentDates);
  if (!docs?.length || dateSet.size === 0) return [];
  const out: ThesisRelatedDocLink[] = [];
  const seen = new Set<string>();
  const tix = [...tickers].map((t) => t.toUpperCase());

  for (const d of docs) {
    if (getDocLibraryTier(d) !== 'portfolio') continue;
    if (!d.date || !dateSet.has(d.date)) continue;
    const p = d.path || '';
    const low = p.toLowerCase();
    const key = `${d.date}|${p}`;
    if (seen.has(key)) continue;

    if (
      low.startsWith('market-thesis-exploration/') ||
      low.startsWith('thesis-vehicle-map/') ||
      low.includes('opportunity-screen') ||
      low.includes('opportunity-screener')
    ) {
      seen.add(key);
      const label = p.split('/').pop()?.replace(/\.json$/i, '') ?? p;
      out.push({ document_key: p, date: d.date, label });
      continue;
    }

    for (const t of tix) {
      if (
        low.includes(`asset-recommendations/${d.date}/${t.toLowerCase()}`) ||
        low.includes(`deliberation-transcript/${d.date}/${t.toLowerCase()}`) ||
        low.includes(`/${t.toLowerCase()}.json`)
      ) {
        seen.add(key);
        out.push({
          document_key: p,
          date: d.date,
          label: `${t} — ${low.includes('deliberation') ? 'Deliberation' : low.includes('recommendations') ? 'Rec' : p.split('/').pop() ?? p}`,
        });
        break;
      }
    }
  }

  return out.sort((a, b) => b.date.localeCompare(a.date) || a.document_key.localeCompare(b.document_key));
}

const COMPARABLE_PAGE = 1000;
const COMPARABLE_MAX_ROWS = 80000;

/**
 * Load close prices from price_history for NAV comparables (date window inclusive).
 * Paginates past PostgREST default row limits.
 */
export async function fetchComparablePriceHistory(
  tickers: string[],
  minDate: string,
  maxDate: string
): Promise<BenchmarkHistoryMap> {
  if (!isSupabaseConfigured() || !supabase || tickers.length === 0) return {};
  const norm = [...new Set(tickers.map((t) => String(t).toUpperCase().trim()).filter(Boolean))];
  if (norm.length === 0) return {};

  type Ph = Pick<TableRow<'price_history'>, 'date' | 'ticker' | 'close'>;
  const all: Ph[] = [];
  let offset = 0;
  while (offset < COMPARABLE_MAX_ROWS) {
    const { data, error } = await supabase
      .from('price_history')
      .select('date, ticker, close')
      .in('ticker', norm)
      .gte('date', minDate)
      .lte('date', maxDate)
      .order('date', { ascending: true })
      .range(offset, offset + COMPARABLE_PAGE - 1);

    if (error) {
      console.error('fetchComparablePriceHistory:', error);
      break;
    }
    const chunk = (data ?? []) as Ph[];
    all.push(...chunk);
    if (chunk.length < COMPARABLE_PAGE) break;
    offset += COMPARABLE_PAGE;
  }

  const out: BenchmarkHistoryMap = {};
  for (const row of all) {
    if (!out[row.ticker]) {
      out[row.ticker] = { current: null, history: [] };
    }
    out[row.ticker].history.push({ date: row.date, price: Number(row.close) });
  }
  for (const bData of Object.values(out)) {
    if (bData.history.length) {
      bData.current = bData.history[bData.history.length - 1].price;
    }
  }
  return out;
}

/** Page size for position chart queries (PostgREST caps single responses). */
const POSITION_CHART_PAGE = 1000;
/** Safety cap so a pathological range cannot fetch unbounded rows. */
const POSITION_CHART_MAX_PRICE_ROWS = 25000;

const positionPriceChartCache = new Map<string, PositionPriceChartData>();

/**
 * Load daily closes for one ticker from `fromDate` through `maxDate` (inclusive)
 * plus `position_events` in that window (for chart markers). Paginates so the
 * full window is returned — a plain `.limit(2000)` previously kept only the
 * oldest slice and cut off recent prices.
 * Results are memoized in-memory for the session (price + contribution charts).
 */
function subtractIsoDaysForChart(iso: string, days: number): string {
  const parts = iso.split('-').map(Number);
  if (parts.length < 3) return iso;
  const [y, m, d] = parts;
  const t = Date.UTC(y, m - 1, d);
  return new Date(t - days * 86400000).toISOString().slice(0, 10);
}

export async function fetchPositionPriceChart(
  ticker: string,
  fromDate: string,
  maxDate?: string
): Promise<PositionPriceChartData> {
  const t = String(ticker).toUpperCase().trim();
  if (!isSupabaseConfigured() || !supabase) {
    throw new Error(
      'Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.'
    );
  }
  if (!t || !fromDate?.trim()) {
    return { priceHistory: [], events: [] };
  }

  const end = (maxDate && maxDate.trim()) || new Date().toISOString().slice(0, 10);
  /** If `fromDate` is after `end` (e.g. future-dated OPEN events), widen lookback so the query is valid. */
  let safeFrom = fromDate.trim();
  if (safeFrom > end) {
    safeFrom = subtractIsoDaysForChart(end, 730);
  }
  const cacheKey = `${t}|${safeFrom}|${end}`;
  const hit = positionPriceChartCache.get(cacheKey);
  if (hit) return hit;

  type EvPick = Pick<
    TableRow<'position_events'>,
    'date' | 'event' | 'price' | 'reason' | 'weight_pct' | 'prev_weight_pct' | 'weight_change_pct'
  >;
  type PhPick = Pick<TableRow<'price_history'>, 'date' | 'close'>;

  const priceRows: PhPick[] = [];
  let phOffset = 0;
  while (phOffset < POSITION_CHART_MAX_PRICE_ROWS) {
    const { data, error } = await supabase
      .from('price_history')
      .select('date, close')
      .eq('ticker', t)
      .gte('date', safeFrom)
      .lte('date', end)
      .order('date', { ascending: true })
      .range(phOffset, phOffset + POSITION_CHART_PAGE - 1);

    if (error) {
      console.error('fetchPositionPriceChart price_history:', error);
      break;
    }
    const chunk = (data ?? []) as PhPick[];
    priceRows.push(...chunk);
    if (chunk.length < POSITION_CHART_PAGE) break;
    phOffset += POSITION_CHART_PAGE;
  }

  const evRows: EvPick[] = [];
  let evOffset = 0;
  const EVENT_MAX = 8000;
  while (evOffset < EVENT_MAX) {
    const { data, error } = await supabase
      .from('position_events')
      .select('date, event, price, reason, weight_pct, prev_weight_pct, weight_change_pct')
      .eq('ticker', t)
      .gte('date', safeFrom)
      .lte('date', end)
      .order('date', { ascending: true })
      .range(evOffset, evOffset + POSITION_CHART_PAGE - 1);

    if (error) {
      console.error('fetchPositionPriceChart position_events:', error);
      break;
    }
    const chunk = (data ?? []) as EvPick[];
    evRows.push(...chunk);
    if (chunk.length < POSITION_CHART_PAGE) break;
    evOffset += POSITION_CHART_PAGE;
  }

  const priceHistory = priceRows.map((row) => ({
    date: row.date,
    close: Number(row.close),
  }));

  const events = evRows.map((row) => ({
    date: row.date,
    event: row.event,
    price: row.price != null ? Number(row.price) : null,
    reason: row.reason ?? null,
    weight_pct: row.weight_pct != null ? Number(row.weight_pct) : null,
    prev_weight_pct: row.prev_weight_pct != null ? Number(row.prev_weight_pct) : null,
    weight_change_pct: row.weight_change_pct != null ? Number(row.weight_change_pct) : null,
  }));

  const result = { priceHistory, events };
  positionPriceChartCache.set(cacheKey, result);
  return result;
}

/** Resolve markdown + structured view for the Research Library. */
export async function getLibraryDocumentById(id: string): Promise<LibraryDocumentResult> {
  if (!isSupabaseConfigured() || !supabase) {
    throw new Error(
      'Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.'
    );
  }

  type DocPick = Pick<
    TableRow<'documents'>,
    'id' | 'content' | 'payload' | 'date' | 'document_key'
  >;

  const { data: row, error } = await supabase
    .from('documents')
    .select('id, content, payload, date, document_key')
    .eq('id', id)
    .maybeSingle();

  if (error) throw error;
  if (!row) throw new Error('Document not found');

  const doc = row as DocPick;
  const payload =
    doc.payload != null && typeof doc.payload === 'object' && !Array.isArray(doc.payload)
      ? (doc.payload as Record<string, unknown>)
      : null;

  let md = doc.content?.trim() ? doc.content : '';

  if (!md && doc.payload != null) {
    md = renderDocumentMarkdownFromPayload(doc.payload, doc.document_key ?? undefined) || md;
  }

  if (!md && doc.document_key === 'digest') {
    const { data: snapRow } = await supabase
      .from('daily_snapshots')
      .select('digest_markdown, snapshot')
      .eq('date', doc.date)
      .maybeSingle();
    const snap = snapRow as {
      digest_markdown?: string | null;
      snapshot?: TableRow<'daily_snapshots'>['snapshot'];
    } | null;
    if (snap?.digest_markdown?.trim()) {
      md = snap.digest_markdown;
    } else if (snap?.snapshot != null && typeof snap.snapshot === 'object' && !Array.isArray(snap.snapshot)) {
      try {
        md = renderDigestMarkdownFromSnapshot(snap.snapshot as DigestSnapshot);
      } catch {
        /* noop */
      }
    }
  }

  const view = resolveLibraryDocumentView(doc.document_key, doc.payload);
  const markdown = md || '_No content available._';

  return {
    id: doc.id,
    date: doc.date,
    document_key: doc.document_key,
    view,
    markdown,
    payload,
  };
}

export async function getDocumentContentById(
  id: string
): Promise<Pick<TableRow<'documents'>, 'id' | 'content'>> {
  const r = await getLibraryDocumentById(id);
  return { id: r.id, content: r.markdown };
}

/** What to diff the digest against in the library. */
export type DigestCompareKind = 'previous_digest' | 'delta_baseline' | 'custom_date';

export type DigestDiffContext = {
  previousDigestDate: string | null;
  deltaBaselineDate: string | null;
  changeCount: number;
};

export type DigestMarkdownDiffPair = {
  compareDate: string;
  targetDate: string;
  changeCount: number;
  beforeMarkdown: string;
  afterMarkdown: string;
  compareKind: DigestCompareKind;
  /** Latest `daily_snapshots.date` strictly before `targetDate` (when that row exists). */
  previousDigestDate: string | null;
  /** Weekly / delta anchor from `delta-request.json` or `daily_snapshots.baseline_date` for the target row. */
  deltaBaselineDate: string | null;
};

async function loadDigestDiffAnchors(targetDate: string): Promise<{
  changeCount: number;
  resolvedDeltaBaseline: string | null;
  previousDigestDate: string | null;
}> {
  if (!isSupabaseConfigured() || !supabase) {
    throw new Error(
      'Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.'
    );
  }

  const { data: deltaRow, error: deltaErr } = await supabase
    .from('documents')
    .select('payload')
    .eq('date', targetDate)
    .eq('document_key', 'delta-request.json')
    .maybeSingle();

  if (deltaErr) throw deltaErr;
  const deltaPick = deltaRow as Pick<TableRow<'documents'>, 'payload'> | null;

  let changeCount = 0;
  let deltaPayloadBaseline: string | null = null;
  if (deltaPick?.payload) {
    const meta = parseDeltaPayload(deltaPick.payload);
    changeCount = new Set([...meta.changed_paths, ...meta.op_paths].filter(Boolean)).size;
    const b = meta.baseline_date;
    deltaPayloadBaseline = b && b !== targetDate ? b : null;
  }

  const { data: targetSnapMeta, error: targetMetaErr } = await supabase
    .from('daily_snapshots')
    .select('baseline_date')
    .eq('date', targetDate)
    .maybeSingle();

  if (targetMetaErr) throw targetMetaErr;
  const rowBaseline =
    (targetSnapMeta as Pick<TableRow<'daily_snapshots'>, 'baseline_date'> | null)?.baseline_date ?? null;
  const rowBaselineOk = rowBaseline && rowBaseline !== targetDate ? rowBaseline : null;

  const resolvedDeltaBaseline = deltaPayloadBaseline || rowBaselineOk;

  const { data: prev, error: prevErr } = await supabase
    .from('daily_snapshots')
    .select('date')
    .lt('date', targetDate)
    .order('date', { ascending: false })
    .limit(1)
    .maybeSingle();
  if (prevErr) throw prevErr;
  const previousDigestDate =
    (prev as Pick<TableRow<'daily_snapshots'>, 'date'> | null)?.date ?? null;

  return { changeCount, resolvedDeltaBaseline, previousDigestDate };
}

/** Digest comparison anchors only (no snapshot markdown fetch). */
export async function fetchDigestDiffContext(targetDate: string): Promise<DigestDiffContext> {
  if (!isSupabaseConfigured() || !supabase) {
    throw new Error(
      'Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.'
    );
  }
  const { changeCount, resolvedDeltaBaseline, previousDigestDate } = await loadDigestDiffAnchors(targetDate);
  return {
    previousDigestDate,
    deltaBaselineDate: resolvedDeltaBaseline,
    changeCount,
  };
}

/**
 * Loads digest diff anchors once, then markdown pair for the chosen comparison mode.
 * Use this from the library UI so comparison toggles stay accurate when a mode returns no pair.
 */
export async function loadDigestLibraryDiff(
  targetDate: string,
  compareKind: DigestCompareKind = 'previous_digest',
  customCompareDate?: string
): Promise<{ context: DigestDiffContext; pair: DigestMarkdownDiffPair | null }> {
  if (!isSupabaseConfigured() || !supabase) {
    throw new Error(
      'Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.'
    );
  }
  const sb = supabase;
  const { changeCount, resolvedDeltaBaseline, previousDigestDate } = await loadDigestDiffAnchors(targetDate);

  const context: DigestDiffContext = {
    previousDigestDate,
    deltaBaselineDate: resolvedDeltaBaseline,
    changeCount,
  };

  let compareDate = '';
  if (compareKind === 'delta_baseline') {
    if (!resolvedDeltaBaseline) return { context, pair: null };
    compareDate = resolvedDeltaBaseline;
  } else if (compareKind === 'custom_date') {
    const d = (customCompareDate ?? '').trim();
    if (!/^\d{4}-\d{2}-\d{2}$/.test(d) || d === targetDate) return { context, pair: null };
    compareDate = d;
  } else {
    if (!previousDigestDate) return { context, pair: null };
    compareDate = previousDigestDate;
  }

  const { data: snaps, error: snapErr } = await sb
    .from('daily_snapshots')
    .select('date, snapshot, digest_markdown')
    .in('date', [targetDate, compareDate]);

  if (snapErr) throw snapErr;

  type SnapPick = Pick<TableRow<'daily_snapshots'>, 'date' | 'snapshot' | 'digest_markdown'>;
  const byDate = new Map<string, SnapPick>();
  for (const s of (snaps ?? []) as SnapPick[]) {
    if (s?.date) byDate.set(s.date, s);
  }

  const beforeRow = byDate.get(compareDate);
  const afterRow = byDate.get(targetDate);
  if (!beforeRow || !afterRow) return { context, pair: null };

  function parseSnap(v: unknown): unknown {
    if (v == null) return {};
    if (typeof v === 'string') {
      try {
        return JSON.parse(v) as unknown;
      } catch {
        return {};
      }
    }
    return typeof v === 'object' ? v : {};
  }

  function markdownFromRow(row: SnapPick): string {
    const dm = row.digest_markdown?.trim();
    if (dm) return dm;
    const parsed = parseSnap(row.snapshot) as DigestSnapshot;
    try {
      return renderDigestMarkdownFromSnapshot(parsed);
    } catch {
      return '';
    }
  }

  const beforeMarkdown = markdownFromRow(beforeRow);
  const afterMarkdown = markdownFromRow(afterRow);
  if (!afterMarkdown.trim()) return { context, pair: null };

  return {
    context,
    pair: {
      compareDate,
      targetDate,
      changeCount,
      beforeMarkdown,
      afterMarkdown,
      compareKind,
      previousDigestDate,
      deltaBaselineDate: resolvedDeltaBaseline,
    },
  };
}

/**
 * Markdown pair only (same as `loadDigestLibraryDiff(...).pair`).
 * @see loadDigestLibraryDiff — prefer that when the UI needs `DigestDiffContext` for toggles.
 */
export async function getDigestMarkdownDiffPair(
  targetDate: string,
  compareKind: DigestCompareKind = 'previous_digest',
  customCompareDate?: string
): Promise<DigestMarkdownDiffPair | null> {
  const { pair } = await loadDigestLibraryDiff(targetDate, compareKind, customCompareDate);
  return pair;
}

export async function getDailySnapshots(
  fromDate?: string
): Promise<TableRow<'daily_snapshots'>[]> {
  return querySupabase<TableRow<'daily_snapshots'>[]>((sb) => {
    let q = sb
      .from('daily_snapshots')
      .select('date, regime, market_data, segment_biases')
      .order('date', { ascending: true });
    if (fromDate) q = q.gte('date', fromDate);
    return q;
  });
}

export async function getPositionHistory(
  fromDate?: string
): Promise<Pick<TableRow<'positions'>, 'date' | 'ticker' | 'weight_pct'>[]> {
  return querySupabase((sb) => {
    let q = sb
      .from('positions')
      .select('date, ticker, weight_pct')
      .order('date', { ascending: true });
    if (fromDate) q = q.gte('date', fromDate);
    return q;
  });
}

export async function getPositionEvents(
  fromDate?: string,
  ticker?: string
): Promise<TableRow<'position_events'>[]> {
  return querySupabase((sb) => {
    let q = sb
      .from('position_events')
      .select('*')
      .order('date', { ascending: false });
    if (fromDate) q = q.gte('date', fromDate);
    if (ticker) q = q.eq('ticker', ticker);
    return q.limit(200);
  });
}

// ─── Generic document diff (used by the library diff view) ───────────────────

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export type DocumentDiffCompareKind = 'previous_day' | 'delta_baseline' | 'custom_date';

export type DocumentDiffPair = {
  targetDate: string;
  compareDate: string;
  compareKey: string;
  /** How the comparison document was resolved */
  compareMode: 'baseline_doc' | 'previous_day' | 'delta_baseline' | 'custom_date';
  beforeMarkdown: string;
  afterMarkdown: string;
};

export type DocumentDiffAnchors = {
  previousDayDate: string | null;
  deltaBaselineDate: string | null;
};

type DocContentPick = Pick<TableRow<'documents'>, 'date' | 'document_key' | 'content' | 'payload'>;

async function getDeltaBaselineDateForRun(sb: SB, targetDate: string): Promise<string | null> {
  const { data: deltaRow, error } = await sb
    .from('documents')
    .select('payload')
    .eq('date', targetDate)
    .eq('document_key', 'delta-request.json')
    .maybeSingle();
  if (error) throw error;
  const pick = deltaRow as Pick<TableRow<'documents'>, 'payload'> | null;
  const b = pick?.payload ? parseDeltaPayload(pick.payload).baseline_date : null;
  const trimmed = (b ?? '').trim();
  if (!trimmed || trimmed === targetDate) return null;
  return trimmed;
}

async function findTemplateDocBeforeDate(
  sb: SB,
  documentKey: string,
  targetDate: string
): Promise<Pick<TableRow<'documents'>, 'date' | 'document_key' | 'content'> | null> {
  const datePattern = /\d{4}-\d{2}-\d{2}/g;
  const keyWithPlaceholder = documentKey.replace(datePattern, '__DATE__');
  const { data: allPrior, error } = await sb
    .from('documents')
    .select('date, document_key, content')
    .lt('date', targetDate)
    .order('date', { ascending: false })
    .limit(50);
  if (error) throw error;
  const priorDocs = (allPrior ?? []) as Pick<TableRow<'documents'>, 'date' | 'document_key' | 'content'>[];
  return (
    priorDocs.find((r) => r.document_key.replace(datePattern, '__DATE__') === keyWithPlaceholder) ?? null
  );
}

async function findTemplateDocOnDate(
  sb: SB,
  documentKey: string,
  onDate: string
): Promise<Pick<TableRow<'documents'>, 'date' | 'document_key' | 'content'> | null> {
  const datePattern = /\d{4}-\d{2}-\d{2}/g;
  const template = documentKey.replace(datePattern, '__DATE__');
  const { data: rows, error } = await sb
    .from('documents')
    .select('date, document_key, content')
    .eq('date', onDate)
    .limit(400);
  if (error) throw error;
  const list = (rows ?? []) as Pick<TableRow<'documents'>, 'date' | 'document_key' | 'content'>[];
  return list.find((r) => r.document_key.replace(datePattern, '__DATE__') === template) ?? null;
}

/** Labels for compare-target dropdowns without loading full diff bodies. */
export async function fetchDocumentDiffAnchors(
  targetDate: string,
  documentKey: string,
  payload: Record<string, unknown> | null
): Promise<DocumentDiffAnchors> {
  if (!isSupabaseConfigured() || !supabase) {
    return { previousDayDate: null, deltaBaselineDate: null };
  }
  const sb = supabase;
  const key = documentKey.toLowerCase();
  let deltaBaselineDate: string | null = null;
  try {
    deltaBaselineDate = await getDeltaBaselineDateForRun(sb, targetDate);
  } catch {
    deltaBaselineDate = null;
  }

  if (key.startsWith('deltas/')) {
    const { data: prior, error } = await sb
      .from('documents')
      .select('date')
      .eq('document_key', documentKey)
      .lt('date', targetDate)
      .order('date', { ascending: false })
      .limit(1)
      .maybeSingle();
    if (error) return { previousDayDate: null, deltaBaselineDate };
    const previousDayDate =
      (prior as Pick<TableRow<'documents'>, 'date'> | null)?.date?.trim() || null;
    return { previousDayDate, deltaBaselineDate };
  }

  try {
    const matchingPrior = await findTemplateDocBeforeDate(sb, documentKey, targetDate);
    return { previousDayDate: matchingPrior?.date ?? null, deltaBaselineDate };
  } catch {
    return { previousDayDate: null, deltaBaselineDate };
  }
}

export type DocumentDiffLoadOptions = {
  compare?: DocumentDiffCompareKind;
  customCompareDate?: string;
};

/**
 * Resolve a before/after markdown pair for diffing `targetDate / documentKey`.
 *
 * Default compare is **previous calendar run** of the same artifact (prior `documents` row
 * for `deltas/*` keys, or template-matched prior day for date-keyed keys). Use `delta_baseline`
 * to compare against the run's `delta-request.json` baseline anchor, or `custom_date` with
 * `customCompareDate` for an explicit snapshot day.
 */
export async function loadDocumentDiff(
  targetDate: string,
  documentKey: string,
  payload: Record<string, unknown> | null,
  opts?: DocumentDiffLoadOptions
): Promise<DocumentDiffPair | null> {
  if (!isSupabaseConfigured() || !supabase) return null;
  const sb = supabase;
  const compare = opts?.compare ?? 'previous_day';
  const customRaw = (opts?.customCompareDate ?? '').trim();
  const customOk = ISO_DATE_RE.test(customRaw) && customRaw !== targetDate ? customRaw : null;
  const key = documentKey.toLowerCase();

  type DocPick = DocContentPick;

  // ── Research delta file (`deltas/foo.delta.md`) ───────────────────────────
  if (key.startsWith('deltas/')) {
    const stripped = documentKey.slice('deltas/'.length).replace(/\.delta\.md$/i, '.md');

    const { data: afterPick, error: afterErr } = await sb
      .from('documents')
      .select('content')
      .eq('date', targetDate)
      .eq('document_key', documentKey)
      .maybeSingle();
    if (afterErr) throw afterErr;
    if (!afterPick) return null;
    const afterMarkdown =
      (afterPick as Pick<TableRow<'documents'>, 'content'>).content?.trim() || '_No content._';

    if (compare === 'custom_date') {
      if (!customOk) return null;
      const { data: beforePick, error: bErr } = await sb
        .from('documents')
        .select('date, document_key, content')
        .eq('date', customOk)
        .eq('document_key', documentKey)
        .maybeSingle();
      if (bErr) throw bErr;
      if (!beforePick) return null;
      const beforeMarkdown =
        (beforePick as Pick<TableRow<'documents'>, 'content'>).content?.trim() || '_No content._';
      return {
        targetDate,
        compareDate: customOk,
        compareKey: documentKey,
        compareMode: 'custom_date',
        beforeMarkdown,
        afterMarkdown,
      };
    }

    if (compare === 'delta_baseline') {
      const baselineDate = String((payload?.baseline_date as string | undefined) ?? '').trim();
      if (!baselineDate || baselineDate === targetDate) return null;
      const { data: rows, error } = await sb
        .from('documents')
        .select('date, document_key, content, payload')
        .in('date', [targetDate, baselineDate])
        .in('document_key', [documentKey, stripped]);
      if (error) throw error;
      const byKey = new Map<string, DocPick>();
      for (const r of (rows ?? []) as DocPick[]) {
        byKey.set(`${r.date}__${r.document_key}`, r);
      }
      const beforeRow = byKey.get(`${baselineDate}__${stripped}`);
      const afterRow = byKey.get(`${targetDate}__${documentKey}`);
      if (!beforeRow || !afterRow) return null;
      return {
        targetDate,
        compareDate: baselineDate,
        compareKey: stripped,
        compareMode: 'baseline_doc',
        beforeMarkdown: beforeRow.content?.trim() || '_No content._',
        afterMarkdown: afterRow.content?.trim() || '_No content._',
      };
    }

    const { data: priorRow, error: prErr } = await sb
      .from('documents')
      .select('date, document_key, content')
      .eq('document_key', documentKey)
      .lt('date', targetDate)
      .order('date', { ascending: false })
      .limit(1)
      .maybeSingle();
    if (prErr) throw prErr;
    if (!priorRow) return null;
    const p = priorRow as Pick<TableRow<'documents'>, 'date' | 'document_key' | 'content'>;
    const beforeMarkdown = p.content?.trim() || '_No content._';
    return {
      targetDate,
      compareDate: p.date,
      compareKey: documentKey,
      compareMode: 'previous_day',
      beforeMarkdown,
      afterMarkdown,
    };
  }

  // ── Date-keyed and other documents ───────────────────────────────────────
  const { data: currentRow, error: currErr } = await sb
    .from('documents')
    .select('content')
    .eq('date', targetDate)
    .eq('document_key', documentKey)
    .maybeSingle();
  if (currErr) throw currErr;
  if (!currentRow) return null;
  const afterMarkdown =
    (currentRow as Pick<TableRow<'documents'>, 'content'>).content?.trim() || '_No content._';

  if (compare === 'custom_date') {
    if (!customOk) return null;
    const beforeRow = await findTemplateDocOnDate(sb, documentKey, customOk);
    if (!beforeRow) return null;
    return {
      targetDate,
      compareDate: beforeRow.date,
      compareKey: beforeRow.document_key,
      compareMode: 'custom_date',
      beforeMarkdown: beforeRow.content?.trim() || '_No content._',
      afterMarkdown,
    };
  }

  if (compare === 'delta_baseline') {
    const baselineDate = await getDeltaBaselineDateForRun(sb, targetDate);
    if (!baselineDate) return null;
    const beforeRow = await findTemplateDocOnDate(sb, documentKey, baselineDate);
    if (!beforeRow) return null;
    return {
      targetDate,
      compareDate: beforeRow.date,
      compareKey: beforeRow.document_key,
      compareMode: 'delta_baseline',
      beforeMarkdown: beforeRow.content?.trim() || '_No content._',
      afterMarkdown,
    };
  }

  const matchingPrior = await findTemplateDocBeforeDate(sb, documentKey, targetDate);
  if (!matchingPrior) return null;
  return {
    targetDate,
    compareDate: matchingPrior.date,
    compareKey: matchingPrior.document_key,
    compareMode: 'previous_day',
    beforeMarkdown: matchingPrior.content?.trim() || '_No content._',
    afterMarkdown,
  };
}
