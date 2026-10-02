/**
 * Route payloads for the "markets" group: market tools, FX desk, rates desk.
 * Every route returns the standard Envelope<T> (lib/dq-api.ts); the shapes below are the `data` part.
 * Nullable numbers stay nullable (null renders "—", never zero). Optional (?) fields may be
 * absent until the worker ships them.
 */

/* ---- Market tools ---- */

/** GET /markets/quotes?symbols=A,B,C  -> { quotes } . A symbol with no print has last=null. */
export type MkQuote = {
  symbol: string;
  name?: string | null;
  last: number | null;
  net?: number | null;
  pct?: number | null;
  bid?: number | null;
  ask?: number | null;
  volume?: number | null;
  /** Display time of the print, e.g. "16:00". Passed through as text. */
  time?: string | null;
};
export type MkQuotes = { quotes: MkQuote[] };

/** GET /markets/bars?symbol=&interval=&indicators=ema20,rsi14 */
export type MkBar = { t: string; o: number | null; h: number | null; l: number | null; c: number | null; v?: number | null };
export type MkBars = {
  symbol: string;
  interval: string;
  venue?: string | null;
  bars: MkBar[];
  /** Keyed by indicator id (ema20, rsi14, ...). Each array is aligned to `bars`; null = no value yet. */
  indicators?: Record<string, (number | null)[]>;
};

/** GET /tape  -> { items }  (newest first). */
export type MkTape = { items: { time: string | null; headline: string; tag?: string | null }[] };

/** GET /charts/series */
export type MkSeriesRegistry = {
  defaults?: { symbol?: string | null; range?: string | null; series?: string | null } | null;
  series: { id: string; label: string; source?: string | null; status?: string | null }[];
};

/* ---- FX desk ---- */

/** GET /fx/summary */
export type FxSummary = {
  desk?: string | null;
  run_date: string | null;
  posture?: string | null;
  pairs?: { count: number | null; note?: string | null } | null;
  ideas?: { count: number | null; note?: string | null } | null;
  paper_exposure?: { gross_usd: number | null; venue?: string | null } | null;
  session?: { name: string | null; note?: string | null } | null;
  research_flags?: { count: number | null } | null;
  read?: { lead: string; body?: string | null } | null;
  changes?: string[];
};

/** GET /fx/pairs  -> { pairs }. `path` is an optional recent session path (>= 2 points to draw). */
export type FxPair = {
  pair: string;
  bid: number | null;
  offer: number | null;
  day_pct: number | null;
  session?: string | null;
  path?: (number | null)[] | null;
  bias?: string | null;
  status?: string | null;
};
export type FxPairs = { pairs: FxPair[] };

/** GET /fx/pairs/:pair/path */
export type FxPairPath = {
  pair: string;
  session?: string | null;
  points: { t: string; v: number | null }[];
  note?: string | null;
};

/** GET /fx/ideas  -> { ideas } */
export type FxIdea = {
  rank: number | null;
  pair: string;
  bias?: string | null;
  horizon?: string | null;
  invalidation?: number | null;
  status?: string | null;
  levels?: string | null;
  thread?: string | null;
};
export type FxIdeas = { ideas: FxIdea[] };

/** GET /fx/ideas/:pair */
export type FxLevel = { value: number | null; provenance?: string | null };
export type FxIdeaDetail = {
  pair: string;
  rank?: number | null;
  headline?: string | null;
  rationale?: string | null;
  bias?: string | null;
  horizon?: string | null;
  status?: string | null;
  invalidation?: FxLevel | null;
  entry?: { low: number | null; high: number | null; provenance?: string | null } | null;
  target?: FxLevel | null;
  catalyst?: string | null;
  evidence_note?: string | null;
};

/** GET /fx/levels  -> { levels }. level/role/pips are null when the idea has no fix. */
export type FxLevels = {
  levels: { pair: string; mark: number | null; level: number | null; role?: string | null; pips?: number | null; provenance?: string | null; flag?: string | null }[];
};

/** GET /fx/flags/:pair */
export type FxFlag = { pair: string; flagged: boolean; level?: number | null; text?: string | null; scope_note?: string | null };

/** GET /fx/paper-exposure */
export type FxPaperExposure = {
  venue?: string | null;
  gross_usd: number | null;
  note?: string | null;
  lines: { pair: string; side: string | null; notional_usd: number | null; venue?: string | null }[];
};

/** GET /fx/sessions */
export type FxSessions = { sessions: { session: string; state: string | null; note?: string | null; active?: boolean }[] };

/** GET /fx/directives and PUT /fx/directives (PUT body = the four editable fields). */
export type FxDirectives = {
  allow_pairs: string[];
  deny_pairs: string[];
  risk_style: string | null;
  risk_style_options?: string[];
  ignore_sources: string[];
  /** false = the writer contract is not wired; the form renders read-only. */
  writable?: boolean;
  note?: string | null;
};
export type FxDirectivesPut = Pick<FxDirectives, 'allow_pairs' | 'deny_pairs' | 'risk_style' | 'ignore_sources'>;

/* ---- Rates desk ---- */

/** GET /rates/summary */
export type RtSummary = {
  desk?: string | null;
  run_date: string | null;
  posture?: string | null;
  watchlist?: { names: number | null; marks_available: number | null } | null;
  theses?: { active: string[]; watch: string[] } | null;
  last_run?: { date: string | null; note?: string | null } | null;
  budget?: { spent_usd: number | null; cap_usd: number | null } | null;
  read?: { lead: string; body?: string | null } | null;
  signals?: { id: string; name: string; state: string; note?: string | null }[];
  risks?: string[];
};

/** GET /rates/watchlist */
export type RtWatchlist = {
  names: { ticker: string; name?: string | null; mark: number | null; day_pct?: number | null; mark_source?: string | null; thesis_id?: string | null }[];
};

/** GET /rates/curve  (tenor yields, in percent; day_change in percentage points). */
export type RtCurve = {
  curve: { tenor: string; yield_pct: number | null; day_change?: number | null }[];
  spreads?: { label: string; bp: number | null; day_bp?: number | null }[];
};

/** GET /rates/theses — twelve-x theses, Theses shape (lib/dq-api.ts). */
