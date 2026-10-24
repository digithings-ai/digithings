"use client";

import type { ReactNode } from "react";
import { BLOCKS } from "digiquant-tui/catalog";
import { DASH, cell } from "digiquant-tui/format";
import type { ReadResult } from "digiquant-tui/read";
import {
  BlockBoundary,
  DataTable,
  KpiGrid,
  Sparkline,
  StateBlock,
  type DataTableColumn,
  type KpiCell,
  type StateKind,
} from "@digithings/ui";

import { asRecord as rec, isRecord } from "@digithings/ui/lib/record";

/** The FX and rates panes. One block per catalog id, so no pane stays a text line. */
export const FX_BLOCK_IDS = [
  "fx-summary",
  "fx-pairs",
  "fx-levels",
  "fx-pair-path",
  "fx-sessions",
  "fx-ideas",
  "fx-idea-detail",
  "fx-flags",
  "fx-paper-exposure",
  "rt-summary",
  "rt-curve",
  "rt-watchlist",
  "rt-theses",
] as const;

export type FxBlockId = (typeof FX_BLOCK_IDS)[number];

const FX_IDS = new Set<string>(FX_BLOCK_IDS);

export function isFxBlock(id: string): boolean {
  return FX_IDS.has(id);
}

export type FxPaneBlockProps = {
  id: string;
  /** The desk read for this pane. `undefined` while the first fetch is in flight. */
  read?: ReadResult;
  /** The envelope's `data`, when the read is ok and carried one. */
  data?: unknown;
};

type Rec = Record<string, unknown>;

const ABSENT = "not in payload";
const NO_MARKS = "no bid, offer or mark in this payload";

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function tone(value: number | null): "pos" | "neg" | undefined {
  if (value === null || value === 0) return undefined;
  return value > 0 ? "pos" : "neg";
}

function missing(value: string | null): string | undefined {
  return value === null ? ABSENT : undefined;
}

function note(value: unknown): string | undefined {
  return text(value) ?? undefined;
}

/** The route a catalog block reads, for the reasons a StateBlock prints. */
function routeOf(id: string): string {
  return BLOCKS[id]?.route ?? id;
}

function Kpis({ items }: { items: KpiCell[] }) {
  return <KpiGrid items={items} missing={DASH} />;
}

function Prose({ lines }: { lines: (string | null)[] }) {
  const kept = lines.filter((line): line is string => typeof line === "string" && line.length > 0);
  if (kept.length === 0) return null;
  return (
    <div className="flex flex-col gap-1">
      {kept.map((line, index) => (
        <p key={index} className="m-0 whitespace-pre-wrap font-mono text-[0.72rem] leading-relaxed text-ink-soft">
          {line}
        </p>
      ))}
    </div>
  );
}

function Block({ title, reason }: { title: string; reason?: string }) {
  return <StateBlock kind="withheld" title={title} reason={reason} />;
}

/** `source` and `marks` from the read's own head lines, kept when a block replaces the text face. */
function Provenance({ read }: { read?: ReadResult }) {
  const bits = (read?.lines ?? []).filter((line) => line.startsWith("source  ") || line.startsWith("marks  "));
  if (bits.length === 0) return null;
  return <p className="m-0 font-mono text-[0.68rem] leading-relaxed text-ink-mute">{bits.join("   ")}</p>;
}

/** One row per pair the payload listed, with the marks it actually carried. */
type PairRow = { pair: string; bid: number | null; offer: number | null; day: number | null; bias: string; status: string };

function pairRows(d: Rec): { rows: PairRow[]; dropped: number } {
  const rows: PairRow[] = [];
  let dropped = 0;
  for (const item of list(d.pairs)) {
    const row = rec(item);
    const pair = row ? text(row.pair) : null;
    if (!row || !pair) {
      dropped += 1;
      continue;
    }
    rows.push({
      pair,
      bid: finite(row.bid),
      offer: finite(row.offer),
      day: finite(row.day_pct),
      bias: text(row.bias) ?? DASH,
      status: text(row.status) ?? DASH,
    });
  }
  return { rows, dropped };
}

const PAIR_COLS: DataTableColumn<PairRow>[] = [
  { key: "pair", label: "pair", role: "key", cell: (row) => row.pair, sort: (row) => row.pair },
  { key: "bid", label: "bid", num: true, cell: (row) => cell(row.bid, "bid"), sort: (row) => row.bid },
  { key: "offer", label: "offer", num: true, cell: (row) => cell(row.offer, "offer"), sort: (row) => row.offer },
  {
    key: "day",
    label: "day",
    num: true,
    cell: (row) => cell(row.day, "day_pct"),
    tone: (row) => tone(row.day),
    sort: (row) => row.day,
  },
  { key: "bias", label: "bias", cell: (row) => row.bias, sort: (row) => row.bias },
  { key: "status", label: "status", cell: (row) => row.status },
];

function fxPairs(d: Rec): ReactNode {
  const { rows, dropped } = pairRows(d);
  if (rows.length === 0) {
    return <StateBlock kind="empty" title="No FX pairs in this read." reason={`pairs ${ABSENT} or empty.`} />;
  }
  const marked = rows.filter((row) => row.bid !== null || row.offer !== null).length;
  return (
    <div className="flex flex-col gap-2">
      <Kpis
        items={[
          { label: "Pairs", value: rows.length },
          { label: "Marks", value: marked, note: marked === 0 ? NO_MARKS : undefined },
          {
            label: "With bias",
            value: rows.filter((row) => row.bias !== DASH).length,
            note: rows.every((row) => row.bias === DASH) ? ABSENT : undefined,
          },
        ]}
      />
      <DataTable rows={rows} cols={PAIR_COLS} rowKey={(row) => row.pair} label="FX pairs" empty="no pairs" />
      {dropped > 0 ? (
        <p className="m-0 font-mono text-[0.72rem] text-ink-mute">{`${dropped} ${dropped === 1 ? "row" : "rows"} without a pair dropped`}</p>
      ) : null}
    </div>
  );
}

type LevelRow = { pair: string; mark: number | null; level: number | null; role: string; pips: number | null };

const LEVEL_COLS: DataTableColumn<LevelRow>[] = [
  { key: "pair", label: "pair", role: "key", cell: (row) => row.pair, sort: (row) => row.pair },
  { key: "mark", label: "mark", num: true, cell: (row) => cell(row.mark, "mark"), sort: (row) => row.mark },
  { key: "level", label: "level", num: true, cell: (row) => cell(row.level, "level"), sort: (row) => row.level },
  { key: "role", label: "role", cell: (row) => row.role, sort: (row) => row.role },
  { key: "pips", label: "pips", num: true, cell: (row) => cell(row.pips, "pips"), sort: (row) => row.pips },
];

function fxLevels(d: Rec): ReactNode {
  const rows: LevelRow[] = [];
  for (const item of list(d.levels)) {
    const row = rec(item);
    const pair = row ? text(row.pair) : null;
    if (!row || !pair) continue;
    rows.push({
      pair,
      mark: finite(row.mark),
      level: finite(row.level),
      role: text(row.role) ?? DASH,
      pips: finite(row.pips),
    });
  }
  if (rows.length === 0) {
    return <StateBlock kind="empty" title="No FX levels in this read." reason={`levels ${ABSENT} or empty.`} />;
  }
  const marked = rows.filter((row) => row.mark !== null || row.level !== null).length;
  return (
    <div className="flex flex-col gap-2">
      <Kpis
        items={[
          { label: "Levels", value: rows.length },
          { label: "Marked", value: marked, note: marked === 0 ? `${NO_MARKS}` : undefined },
        ]}
      />
      <DataTable rows={rows} cols={LEVEL_COLS} rowKey={(row) => row.pair} label="FX levels" empty="no levels" />
    </div>
  );
}

type SessionRow = { session: string; state: string; note: string };

const SESSION_COLS: DataTableColumn<SessionRow>[] = [
  { key: "session", label: "session", role: "key", cell: (row) => row.session, sort: (row) => row.session },
  { key: "state", label: "state", cell: (row) => row.state, sort: (row) => row.state },
  { key: "note", label: "note", wrap: true, cell: (row) => row.note },
];

function fxSessions(d: Rec): ReactNode {
  const rows: SessionRow[] = [];
  for (const item of list(d.sessions)) {
    const row = rec(item);
    const session = row ? text(row.session) : null;
    if (!row || !session) continue;
    rows.push({
      session,
      state: text(row.state) ?? DASH,
      note: text(row.note) ?? DASH,
    });
  }
  if (rows.length === 0) {
    return <StateBlock kind="empty" title="No FX sessions in this read." reason={`sessions ${ABSENT} or empty.`} />;
  }
  const stated = rows.filter((row) => row.state !== DASH).length;
  return (
    <div className="flex flex-col gap-2">
      <Kpis
        items={[
          { label: "Sessions", value: rows.length },
          {
            label: "Stated",
            value: stated,
            note: stated === 0 ? "no session state in this payload" : undefined,
          },
        ]}
      />
      <DataTable rows={rows} cols={SESSION_COLS} rowKey={(row) => row.session} label="FX sessions" empty="no sessions" />
    </div>
  );
}

type IdeaRow = {
  rank: number | null;
  pair: string;
  bias: string;
  horizon: string;
  invalidation: number | null;
  status: string;
  thread: string;
};

const IDEA_COLS: DataTableColumn<IdeaRow>[] = [
  { key: "rank", label: "rank", num: true, cell: (row) => cell(row.rank, "rank"), sort: (row) => row.rank },
  { key: "pair", label: "pair", role: "key", cell: (row) => row.pair, sort: (row) => row.pair },
  { key: "bias", label: "bias", cell: (row) => row.bias, sort: (row) => row.bias },
  { key: "horizon", label: "horizon", cell: (row) => row.horizon },
  {
    key: "invalidation",
    label: "invalidation",
    num: true,
    cell: (row) => cell(row.invalidation, "invalidation"),
    sort: (row) => row.invalidation,
  },
  { key: "status", label: "status", cell: (row) => row.status },
  { key: "thread", label: "thread", wrap: true, cell: (row) => row.thread },
];

function fxIdeas(d: Rec): ReactNode {
  const rows: IdeaRow[] = [];
  for (const item of list(d.ideas)) {
    const row = rec(item);
    const pair = row ? text(row.pair) : null;
    if (!row || !pair) continue;
    rows.push({
      rank: finite(row.rank),
      pair,
      bias: text(row.bias) ?? DASH,
      horizon: text(row.horizon) ?? DASH,
      invalidation: finite(row.invalidation),
      status: text(row.status) ?? DASH,
      thread: text(row.thread) ?? DASH,
    });
  }
  if (rows.length === 0) {
    return <StateBlock kind="empty" title="No FX ideas in this read." reason={`ideas ${ABSENT} or empty.`} />;
  }
  return (
    <div className="flex flex-col gap-2">
      <Kpis
        items={[
          { label: "Ideas", value: rows.length },
          { label: "Pairs", value: new Set(rows.map((row) => row.pair)).size },
          {
            label: "Invalidations",
            value: rows.filter((row) => row.invalidation !== null).length,
            note: rows.every((row) => row.invalidation === null) ? ABSENT : undefined,
          },
        ]}
      />
      <DataTable rows={rows} cols={IDEA_COLS} rowKey={(row, index) => `${row.pair}-${index}`} label="FX ideas" empty="no ideas" />
    </div>
  );
}

function fxIdeaDetail(d: Rec): ReactNode {
  const pair = text(d.pair);
  const items: KpiCell[] = [
    { label: "Pair", value: pair, note: missing(pair) },
    { label: "Bias", value: text(d.bias), note: missing(text(d.bias)) },
    { label: "Horizon", value: text(d.horizon), note: missing(text(d.horizon)) },
    { label: "Status", value: text(d.status), note: missing(text(d.status)) },
    { label: "Rank", value: finite(d.rank), note: d.rank == null ? ABSENT : undefined },
    {
      label: "Invalidation",
      value: d.invalidation == null ? null : cell(d.invalidation, "invalidation"),
      note: d.invalidation == null ? ABSENT : undefined,
    },
    {
      label: "Entry",
      value: d.entry == null ? null : cell(d.entry, "entry"),
      note: d.entry == null ? ABSENT : undefined,
    },
    {
      label: "Target",
      value: d.target == null ? null : cell(d.target, "target"),
      note: d.target == null ? ABSENT : undefined,
    },
  ];
  return (
    <div className="flex flex-col gap-2">
      <Kpis items={items} />
      <Prose
        lines={[
          text(d.headline),
          text(d.rationale),
          text(d.catalyst) ? `catalyst · ${text(d.catalyst)}` : null,
          text(d.evidence_note),
        ]}
      />
    </div>
  );
}

function fxPairPath(d: Rec): ReactNode {
  const pair = text(d.pair);
  const noteLine = text(d.note);
  const points = list(d.points).filter(isRecord);
  const values = points
    .map((point) => finite(point.v))
    .filter((value): value is number => value !== null);
  const tipRaw = points.at(-1) ? text(points.at(-1)?.t) : null;
  // The payload's own date portion, not a zone-shifted timestamp.
  const tip = tipRaw && /^\d{4}-\d{2}-\d{2}/.test(tipRaw) ? tipRaw.slice(0, 10) : tipRaw;
  if (values.length === 0) {
    return (
      <StateBlock
        kind="empty"
        title="No session path for this pair."
        reason={noteLine ?? `${ABSENT} · points carries no close`}
      />
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <Kpis
        items={[
          { label: "Pair", value: pair, note: missing(pair) },
          { label: "Points", value: points.length, note: `${values.length} with a close` },
          { label: "Tip", value: tip, note: missing(tip) },
          { label: "Session", value: text(d.session), note: missing(text(d.session)) },
        ]}
      />
      <div className="border-x border-b border-hair px-3 py-2">
        <Sparkline values={values} height={56} label={`${pair ?? "FX"} session path over ${values.length} points`} />
      </div>
      <Prose lines={[noteLine]} />
    </div>
  );
}

function fxSummary(d: Rec): ReactNode {
  const pairs = rec(d.pairs);
  const ideas = rec(d.ideas);
  const paper = rec(d.paper_exposure);
  const sessions = rec(d.session);
  const flags = rec(d.research_flags);
  const digest = rec(d.read);
  const changes = list(d.changes).filter((value): value is string => typeof value === "string" && value.length > 0);
  const items: KpiCell[] = [
    { label: "Run", value: text(d.run_date), note: missing(text(d.run_date)) },
    { label: "Pairs", value: finite(pairs?.count), note: pairs?.note == null ? (finite(pairs?.count) === null ? ABSENT : undefined) : note(pairs?.note) },
    { label: "Ideas", value: finite(ideas?.count), note: ideas?.note == null ? (finite(ideas?.count) === null ? ABSENT : undefined) : note(ideas?.note) },
    {
      label: "Paper gross",
      value: paper?.gross_usd == null ? null : cell(paper.gross_usd, "gross_usd"),
      note: text(paper?.venue) ?? ABSENT,
    },
    { label: "Flags", value: finite(flags?.count), note: finite(flags?.count) === null ? ABSENT : undefined },
    { label: "Session", value: text(sessions?.name), note: text(sessions?.note) ?? missing(text(sessions?.name)) },
    { label: "Posture", value: text(d.posture), note: missing(text(d.posture)) },
  ];
  return (
    <div className="flex flex-col gap-2">
      <Kpis items={items} />
      <Prose lines={[text(digest?.lead), text(digest?.body)]} />
      {changes.length > 0 ? (
        <ul className="m-0 flex list-none flex-col gap-0.5 p-0 font-mono text-[0.72rem] text-ink-mute">
          {changes.map((change, index) => (
            <li key={index} className="flex gap-1.5">
              <span aria-hidden="true">·</span>
              <span className="whitespace-pre-wrap">{change}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function rtSummary(d: Rec): ReactNode {
  const watchlist = rec(d.watchlist);
  const budget = rec(d.budget);
  const last = rec(d.last_run);
  const names = list(watchlist?.names).filter((name): name is string => typeof name === "string" && name.length > 0);
  const items: KpiCell[] = [
    { label: "Run", value: text(d.run_date), note: missing(text(d.run_date)) },
    {
      label: "Marks",
      value: finite(watchlist?.marks_available),
      note: finite(watchlist?.marks_available) === null ? ABSENT : "curve points with a yield",
    },
    { label: "Watchlist", value: names.length > 0 ? names.length : null, note: names.length === 0 ? ABSENT : undefined },
    { label: "Last run", value: text(last?.date), note: text(last?.note) ?? missing(text(last?.date)) },
    {
      label: "Spent",
      value: budget?.spent_usd == null ? null : cell(budget.spent_usd, "spent_usd"),
      note: budget?.cap_usd == null ? `${ABSENT} cap` : `cap ${cell(budget.cap_usd, "cap_usd")}`,
    },
    { label: "Posture", value: text(d.posture), note: missing(text(d.posture)) },
  ];
  return (
    <div className="flex flex-col gap-2">
      <Kpis items={items} />
      <Prose lines={[text(d.theses) ? `theses · ${text(d.theses)}` : null]} />
    </div>
  );
}

type CurveRow = { tenor: string; yieldPct: number | null; dayChange: number | null };

const CURVE_COLS: DataTableColumn<CurveRow>[] = [
  { key: "tenor", label: "tenor", role: "key", cell: (row) => row.tenor, sort: (row) => row.tenor },
  {
    key: "yield",
    label: "yield",
    num: true,
    cell: (row) => cell(row.yieldPct, "yield_pct"),
    sort: (row) => row.yieldPct,
  },
  {
    key: "day",
    label: "day",
    num: true,
    cell: (row) => cell(row.dayChange, "day_change_pct"),
    tone: (row) => tone(row.dayChange),
    sort: (row) => row.dayChange,
  },
];

function rtCurve(d: Rec): ReactNode {
  const rows: CurveRow[] = [];
  for (const item of list(d.curve)) {
    const row = rec(item);
    const tenor = row ? text(row.tenor) : null;
    if (!row || !tenor) continue;
    rows.push({ tenor, yieldPct: finite(row.yield_pct), dayChange: finite(row.day_change) });
  }
  if (rows.length === 0) {
    return <StateBlock kind="empty" title="No curve points in this read." reason={`curve ${ABSENT} or empty.`} />;
  }
  const spreads = list(d.spreads).filter(isRecord);
  const spread = spreads[0];
  const marked = rows.filter((row) => row.yieldPct !== null).length;
  return (
    <div className="flex flex-col gap-2">
      <Kpis
        items={[
          { label: "Tenors", value: rows.length },
          { label: "Marked", value: marked, note: marked === 0 ? "no yield in this payload" : undefined },
          {
            label: spread ? text(spread.label) ?? "Spread" : "Spread",
            value: spread?.bp == null ? null : cell(spread.bp, "spread_bp"),
            note: spread ? (spread.bp == null ? ABSENT : "bp") : `spreads ${ABSENT}`,
          },
          {
            label: "Spread day",
            value: spread?.day_bp == null ? null : cell(spread.day_bp, "day_bp"),
            tone: tone(finite(spread?.day_bp)),
            note: spread?.day_bp == null ? ABSENT : "bp",
          },
        ]}
      />
      <DataTable rows={rows} cols={CURVE_COLS} rowKey={(row) => row.tenor} label="Rates curve" empty="no tenors" />
    </div>
  );
}

function rtWatchlist(d: Rec): ReactNode {
  const names = list(d.names).filter((name): name is string => typeof name === "string" && name.length > 0);
  if (names.length === 0) {
    return (
      <StateBlock
        kind="empty"
        title="No watchlist names in this read."
        reason={Array.isArray(d.names) ? "names is an empty list in this payload." : `names ${ABSENT}.`}
      />
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <Kpis items={[{ label: "Names", value: names.length }]} />
      <Prose lines={names} />
    </div>
  );
}

type ThesisRow = { id: string; name: string; state: string; vehicles: string; evidence: string };

const THESIS_COLS: DataTableColumn<ThesisRow>[] = [
  { key: "name", label: "thesis", role: "key", cell: (row) => row.name, sort: (row) => row.name },
  { key: "state", label: "state", cell: (row) => row.state, sort: (row) => row.state },
  { key: "vehicles", label: "vehicles", cell: (row) => row.vehicles },
  { key: "evidence", label: "evidence", wrap: true, cell: (row) => row.evidence },
];

function rtTheses(d: Rec): ReactNode {
  const rows: ThesisRow[] = [];
  for (const item of list(d.theses)) {
    const row = rec(item);
    const id = row ? text(row.id) : null;
    if (!row || !id) continue;
    const vehicles = list(row.vehicles).filter((name): name is string => typeof name === "string" && name.length > 0);
    rows.push({
      id,
      name: text(row.name) ?? id,
      state: text(row.state) ?? DASH,
      vehicles: vehicles.length > 0 ? vehicles.join(" ") : DASH,
      evidence: text(row.evidence) ?? DASH,
    });
  }
  if (rows.length === 0) {
    return <StateBlock kind="empty" title="No rates theses in this read." reason={`theses ${ABSENT} or empty.`} />;
  }
  const counts = rec(d.counts);
  const counted = (key: string): KpiCell => {
    const value = finite(counts?.[key]);
    return { label: key, value, note: value === null ? ABSENT : undefined };
  };
  return (
    <div className="flex flex-col gap-2">
      <Kpis items={[{ label: "Theses", value: rows.length }, counted("active"), counted("watch"), counted("exited")]} />
      <DataTable rows={rows} cols={THESIS_COLS} rowKey={(row) => row.id} label="Rates theses" empty="no theses" />
    </div>
  );
}

function fxFlags(d: Rec): ReactNode {
  const pair = text(d.pair);
  const scope = text(d.scope_note);
  if (d.flagged == null) {
    return (
      <Block
        title={`No research flag for ${pair ?? "this pair"}.`}
        reason={scope ?? `flagged ${ABSENT}`}
      />
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <Kpis
        items={[
          { label: "Pair", value: pair, note: missing(pair) },
          { label: "Flagged", value: d.flagged === true ? "yes" : d.flagged === false ? "no" : null },
          { label: "Level", value: d.level == null ? null : cell(d.level, "level"), note: d.level == null ? ABSENT : undefined },
        ]}
      />
      <Prose lines={[text(d.text), scope]} />
    </div>
  );
}

function fxPaperExposure(d: Rec): ReactNode {
  const scope = text(d.note);
  const gross = d.gross_usd == null ? null : cell(d.gross_usd, "gross_usd");
  if (gross === null) {
    return <Block title="Paper exposure not reported." reason={scope ?? `gross_usd ${ABSENT}`} />;
  }
  return (
    <div className="flex flex-col gap-2">
      <Kpis
        items={[
          { label: "Gross", value: gross, note: "USD" },
          { label: "Venue", value: text(d.venue), note: missing(text(d.venue)) },
        ]}
      />
      <Prose lines={[scope]} />
    </div>
  );
}

const RENDERERS: Record<FxBlockId, (d: Rec) => ReactNode> = {
  "fx-summary": fxSummary,
  "fx-pairs": fxPairs,
  "fx-levels": fxLevels,
  "fx-pair-path": fxPairPath,
  "fx-sessions": fxSessions,
  "fx-ideas": fxIdeas,
  "fx-idea-detail": fxIdeaDetail,
  "fx-flags": fxFlags,
  "fx-paper-exposure": fxPaperExposure,
  "rt-summary": rtSummary,
  "rt-curve": rtCurve,
  "rt-watchlist": rtWatchlist,
  "rt-theses": rtTheses,
};

function stateOf(read: ReadResult | undefined, id: string): { kind: StateKind; title: string; reason?: string } | null {
  const route = routeOf(id);
  if (!read) return { kind: "loading", title: "FX pane", reason: `reading ${route}` };
  if (read.status === "error") {
    return {
      kind: "error",
      title: "This pane could not be read.",
      reason: read.lines.join(" ") || `${route} failed without a message.`,
    };
  }
  if (read.status === "stub") {
    return { kind: "withheld", title: "This pane is withheld.", reason: read.lines.join(" ") };
  }
  if (read.status === "empty") {
    return { kind: "empty", title: "Nothing in this read.", reason: read.lines.join(" ") };
  }
  return null;
}

function FxPaneBody({ id, read, data }: FxPaneBlockProps) {
  const state = stateOf(read, id);
  if (state) return <StateBlock kind={state.kind} title={state.title} reason={state.reason} />;
  if (!isRecord(data)) {
    return (
      <Block
        title="This pane is withheld."
        reason={`the read returned ${data == null ? "no data object" : `a ${Array.isArray(data) ? "list" : typeof data}, not an object`}.`}
      />
    );
  }
  const render = FX_IDS.has(id) ? RENDERERS[id as FxBlockId] : null;
  if (!render) {
    // A catalog block with no FX renderer says so instead of painting a text line.
    return <Block title="No block for this pane." reason={`${id} has no FX block (${routeOf(id)}).`} />;
  }
  return (
    <>
      {render(data)}
      <Provenance read={read} />
    </>
  );
}

/** One FX pane: a KPI strip and a sortable table, or a StateBlock that names why not. */
export function FxPaneBlock({ id, read, data }: FxPaneBlockProps) {
  return (
    <BlockBoundary label={id}>
      <FxPaneBody id={id} read={read} data={data} />
    </BlockBoundary>
  );
}
