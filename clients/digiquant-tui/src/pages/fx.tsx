import { useEffect, useState } from "react";
import { BLOCKS, layoutFor, type BlockKind } from "../catalog";
import { COLS, ROWS } from "../grid";
import { DASH, EMPTY_READ, presentResponse, type ReadResult } from "../read";
import { DANGER, INK, MUTE, WARN } from "../theme";
import { PaneFrame, useFocusedPane } from "./pane";
import { shapeLines } from "./shape";
import { calendarDay, todayYmd, tradingSessionsSince } from "./trading-calendar";

const API = (process.env.DQ_API_URL ?? "http://127.0.0.1:8788").replace(/\/+$/, "");

const FX_BLOCK_IDS = [
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
  "se-fx-feed",
  "fx-directives",
  "se-brokers",
] as const;

export type FxBlockId = (typeof FX_BLOCK_IDS)[number];

export const FX_PATHS = ["/fx", "/fx/ideas", "/fx/watch", "/fx/rates", "/fx/settings"] as const;

const NOT_PROVISIONED = /not provisioned|migration drafted/i;
const NOT_CONFIGURED = /not configured/i;

const share = (cells: number, total: number): `${number}%` => `${(cells / total) * 100}%` as `${number}%`;

export function isFxBlock(id: string): id is FxBlockId {
  return (FX_BLOCK_IDS as readonly string[]).includes(id);
}

export function isFxPath(path: string): path is (typeof FX_PATHS)[number] {
  return (FX_PATHS as readonly string[]).includes(path);
}

function rec(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function str(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

function text(value: unknown): string {
  if (value == null || value === "") return DASH;
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : DASH;
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string") return value;
  return DASH;
}

function list(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter((row): row is Record<string, unknown> => !!row && typeof row === "object" && !Array.isArray(row));
}

function cells(row: Record<string, unknown>, spec: readonly (readonly [string, string])[]): string {
  return spec
    .filter(([key]) => key in row)
    .map(([key, label]) => `${label} ${text(row[key])}`)
    .join("  ");
}

function noteOf(data: unknown): string | null {
  const row = rec(data);
  if (!row) return null;
  return str(row.note) ?? str(row.scope_note);
}

function levelText(value: unknown): string {
  if (value == null || value === "") return DASH;
  if (typeof value === "number" || typeof value === "string") return text(value);
  const row = rec(value);
  if (!row) return DASH;
  const shown = text(row.value);
  const provenance = str(row.provenance);
  return provenance ? `${shown}  ${provenance}` : shown;
}

function entryText(value: unknown): string {
  const row = rec(value);
  if (!row || (row.low == null && row.high == null)) return DASH;
  return `${text(row.low)} – ${text(row.high)}`;
}

function summaryLines(data: unknown): string[] {
  const row = rec(data);
  if (!row) return [EMPTY_READ];
  const pairs = rec(row.pairs);
  const ideas = rec(row.ideas);
  const paper = rec(row.paper_exposure);
  const session = rec(row.session);
  const flags = rec(row.research_flags);
  const read = rec(row.read);
  const lines = [
    `desk  ${text(row.desk)}`,
    `run  ${text(row.run_date)}`,
    `posture  ${text(row.posture)}`,
    `pairs  ${text(pairs?.count)}`,
    `ideas  ${text(ideas?.count)}`,
    `paper  ${text(paper?.gross_usd)}`,
    `session  ${text(session?.name)}`,
    `flags  ${text(flags?.count)}`,
  ];
  const lead = str(read?.lead);
  if (lead) lines.push(lead);
  const body = str(read?.body);
  if (body) lines.push(body);
  if (Array.isArray(row.changes)) {
    for (const item of row.changes.slice(0, 6)) lines.push(text(item));
  }
  return lines;
}

function pairLines(data: unknown): string[] {
  const pairs = list(rec(data)?.pairs);
  if (pairs.length === 0) return ["no pairs"];
  return pairs
    .slice(0, 12)
    .map((row) => cells(row, [["pair", "pair"], ["bid", "bid"], ["offer", "offer"], ["day_pct", "day"], ["bias", "bias"], ["status", "status"]]));
}

function levelLines(data: unknown): string[] {
  const levels = list(rec(data)?.levels);
  if (levels.length === 0) return ["no levels"];
  return levels
    .slice(0, 12)
    .map((row) => cells(row, [["pair", "pair"], ["mark", "mark"], ["level", "level"], ["role", "role"], ["pips", "pips"], ["flag", "flag"]]));
}

function pathLines(data: unknown): string[] {
  const row = rec(data);
  if (!row) return [EMPTY_READ];
  const lines: string[] = [];
  if ("pair" in row) lines.push(`pair  ${text(row.pair)}`);
  const session = str(row.session);
  if (session) lines.push(`session  ${session}`);
  const note = str(row.note);
  if (note) lines.push(note);
  const points = list(row.points);
  if (points.length === 0) {
    lines.push("no points");
    return lines;
  }
  for (const point of points.slice(0, 8)) lines.push(`${text(point.t)}  ${text(point.v)}`);
  if (points.length > 8) lines.push(`… ${points.length - 8} more`);
  return lines;
}

function sessionLines(data: unknown): string[] {
  const sessions = list(rec(data)?.sessions);
  if (sessions.length === 0) return ["no sessions"];
  return sessions.map((row) => {
    const note = str(row.note);
    const base = cells(row, [["session", "session"], ["state", "state"]]);
    return note ? `${base}  ${note}` : base;
  });
}

function ideaLines(data: unknown): string[] {
  const ideas = list(rec(data)?.ideas);
  if (ideas.length === 0) return ["no ideas"];
  return ideas
    .slice(0, 12)
    .map((row) => cells(row, [["rank", "rank"], ["pair", "pair"], ["bias", "bias"], ["horizon", "horizon"], ["status", "status"], ["thread", "thread"]]));
}

function detailLines(data: unknown): string[] {
  const row = rec(data);
  if (!row) return [EMPTY_READ];
  const filled = ["headline", "rationale", "bias", "horizon", "status", "catalyst", "rank", "invalidation", "entry", "target", "evidence_note"].some(
    (key) => row[key] != null && row[key] !== "",
  );
  if (!filled) {
    const pair = str(row.pair);
    return [pair ? `no idea for ${pair}` : "no idea"];
  }
  const lines = [
    `pair  ${text(row.pair)}`,
    `rank  ${text(row.rank)}`,
    `bias  ${text(row.bias)}`,
    `horizon  ${text(row.horizon)}`,
    `status  ${text(row.status)}`,
    `invalidation  ${levelText(row.invalidation)}`,
    `entry  ${entryText(row.entry)}`,
    `target  ${levelText(row.target)}`,
  ];
  const headline = str(row.headline);
  if (headline) lines.unshift(headline);
  const rationale = str(row.rationale);
  if (rationale) lines.push(rationale);
  const catalyst = str(row.catalyst);
  if (catalyst) lines.push(`catalyst  ${catalyst}`);
  const evidence = str(row.evidence_note);
  if (evidence) lines.push(evidence);
  return lines;
}

function flagLines(data: unknown): string[] {
  const note = noteOf(data);
  const row = rec(data);
  if (!row || (note && NOT_PROVISIONED.test(note))) return [note ?? EMPTY_READ];
  if (row.flagged !== true && row.level == null && str(row.text) == null) return [note ?? "no research flag"];
  return [cells(row, [["pair", "pair"], ["flagged", "flagged"], ["level", "level"], ["text", "text"]])];
}

function paperLines(data: unknown): string[] {
  const note = noteOf(data);
  const row = rec(data);
  const lines = list(row?.lines);
  if (!row || (note && NOT_PROVISIONED.test(note)) || lines.length === 0) return [note ?? "no paper exposure"];
  const out = lines.map((line) => cells(line, [["pair", "pair"], ["side", "side"], ["notional_usd", "notional"], ["venue", "venue"]]));
  if ("gross_usd" in row) out.push(`gross  ${text(row.gross_usd)}`);
  return out;
}

function directiveLines(data: unknown): string[] {
  const note = noteOf(data);
  const row = rec(data);
  if (!row || row.writable === false || (note && NOT_PROVISIONED.test(note))) return [note ?? EMPTY_READ];
  const allow = Array.isArray(row.allow_pairs) ? row.allow_pairs : [];
  const deny = Array.isArray(row.deny_pairs) ? row.deny_pairs : [];
  const ignore = Array.isArray(row.ignore_sources) ? row.ignore_sources : [];
  return [
    allow.length ? `allow  ${allow.map((item) => text(item)).join(" ")}` : "allow  no rows",
    deny.length ? `deny  ${deny.map((item) => text(item)).join(" ")}` : "deny  no rows",
    `risk  ${text(row.risk_style)}`,
    ignore.length ? `ignore  ${ignore.map((item) => text(item)).join(" ")}` : "ignore  no rows",
  ];
}

function ratesSummaryLines(data: unknown): string[] {
  const row = rec(data);
  if (!row) return [EMPTY_READ];
  const watch = rec(row.watchlist);
  const last = rec(row.last_run);
  const budget = rec(row.budget);
  const read = rec(row.read);
  const lines = [
    `desk  ${text(row.desk)}`,
    `run  ${text(row.run_date)}`,
    `posture  ${text(row.posture)}`,
    `marks  ${text(watch?.marks_available)}`,
    `last run  ${text(last?.date)}`,
    `budget  ${text(budget?.spent_usd)}`,
  ];
  if (row.theses == null) lines.push(`theses  ${DASH}`);
  else {
    const theses = rec(row.theses);
    if (theses && (Array.isArray(theses.active) || Array.isArray(theses.watch))) {
      const active = Array.isArray(theses.active) ? String(theses.active.length) : DASH;
      const watch = Array.isArray(theses.watch) ? String(theses.watch.length) : DASH;
      lines.push(`theses  active ${active}  watch ${watch}`);
    } else lines.push(`theses  ${text(row.theses)}`);
  }
  const lead = str(read?.lead);
  if (lead) lines.push(lead);
  const signals = list(row.signals);
  if (signals.length === 0) lines.push("signals  no rows");
  else for (const signal of signals.slice(0, 6)) lines.push(cells(signal, [["id", "id"], ["name", "name"], ["state", "state"]]));
  if (Array.isArray(row.risks) && row.risks.length > 0) {
    for (const risk of row.risks.slice(0, 4)) lines.push(text(risk));
  } else lines.push("risks  no rows");
  return lines;
}

function curveLines(data: unknown): string[] {
  const row = rec(data);
  const curve = list(row?.curve);
  const spreads = list(row?.spreads);
  if (curve.length === 0 && spreads.length === 0) return [EMPTY_READ];
  const lines = curve.map((point) => cells(point, [["tenor", "tenor"], ["yield_pct", "yield"], ["day_change", "day"]]));
  for (const spread of spreads) lines.push(cells(spread, [["label", "spread"], ["bp", "bp"], ["day_bp", "day"]]));
  return lines;
}

function watchlistLines(data: unknown): string[] {
  const names = rec(data)?.names;
  if (!Array.isArray(names) || names.length === 0) return ["no names tracked"];
  if (names.every((name) => typeof name === "string")) return names.map((name) => text(name));
  const rows = list(names);
  if (rows.length === 0) return ["no names tracked"];
  return rows.map((row) => cells(row, [["ticker", "ticker"], ["name", "name"], ["mark", "mark"], ["day_pct", "day"]]));
}

function thesesLines(data: unknown): string[] {
  const row = rec(data);
  const theses = list(row?.theses);
  const counts = rec(row?.counts);
  const lines: string[] = [];
  if (counts) lines.push(`active ${text(counts.active)}  watch ${text(counts.watch)}  exited ${text(counts.exited)}`);
  if (theses.length === 0) {
    lines.push("no theses");
    return lines;
  }
  for (const thesis of theses.slice(0, 8)) {
    lines.push(cells(thesis, [["id", "id"], ["name", "name"], ["state", "state"]]));
  }
  return lines;
}

function feedLines(data: unknown): string[] {
  const row = rec(data);
  if (!row) return [EMPTY_READ];
  const generation = rec(row.generation);
  const feed = rec(row.feed);
  const note = str(generation?.note) ?? str(row.note);
  const keys = list(row.keys);
  const bare = row.grant == null && row.posture == null && feed == null && keys.length === 0;
  if (bare || (note && NOT_CONFIGURED.test(note) && keys.length === 0 && row.grant == null)) return [note ?? EMPTY_READ];
  const lines = [
    `grant  ${text(row.grant)}`,
    `posture  ${text(row.posture)}`,
    `provider  ${text(feed?.provider)}`,
    `status  ${text(feed?.status)}`,
  ];
  if (keys.length === 0) lines.push("keys  no rows");
  else for (const key of keys) lines.push(cells(key, [["label", "key"], ["status", "status"]]));
  if (note) lines.push(note);
  return lines;
}

function brokerLines(data: unknown): string[] {
  const row = rec(data);
  if (!row) return [EMPTY_READ];
  const brokers = list(row.brokers);
  const note = str(row.note);
  if (brokers.length === 0) return [note ?? "no brokers"];
  const lines = brokers.map((broker) => cells(broker, [["broker", "broker"], ["env", "env"], ["status", "status"]]));
  if (note) lines.push(note);
  return lines;
}

function fxLines(id: FxBlockId, data: unknown): string[] {
  switch (id) {
    case "fx-summary":
      return summaryLines(data);
    case "fx-pairs":
      return pairLines(data);
    case "fx-levels":
      return levelLines(data);
    case "fx-pair-path":
      return pathLines(data);
    case "fx-sessions":
      return sessionLines(data);
    case "fx-ideas":
      return ideaLines(data);
    case "fx-idea-detail":
      return detailLines(data);
    case "fx-flags":
      return flagLines(data);
    case "fx-paper-exposure":
      return paperLines(data);
    case "fx-directives":
      return directiveLines(data);
    case "rt-summary":
      return ratesSummaryLines(data);
    case "rt-curve":
      return curveLines(data);
    case "rt-watchlist":
      return watchlistLines(data);
    case "rt-theses":
      return thesesLines(data);
    case "se-fx-feed":
      return feedLines(data);
    case "se-brokers":
      return brokerLines(data);
    default: {
      const unreachable: never = id;
      return [String(unreachable)];
    }
  }
}

function isQuiet(line: string): boolean {
  return line === EMPTY_READ || line.startsWith("no ") || line.includes("not provisioned") || line.includes("not configured");
}

/** Provenance stays. Draft tables and unconfigured settings stay the empty note. */
export function fxBlockLines(id: string, result: ReadResult, data: unknown): string[] {
  if (result.status === "error" || result.status === "stub") return result.lines.length ? result.lines : [EMPTY_READ];
  const head = result.lines.filter((line) => line.startsWith("source  ") || line.startsWith("marks  "));
  const body = isFxBlock(id) ? fxLines(id, data) : [EMPTY_READ];
  const lines = [...head, ...body];
  return lines.length ? lines : [EMPTY_READ];
}

/**
 * Tone for an FX pane. `warn` and `stale` sit above `ok` on the same axis: the
 * read succeeded and has content, but it is no longer the run the pane owes the
 * reader. The 2026-09 outage served a healthy-looking pane for 12 trading
 * sessions because nothing here looked at the run date.
 */
export type FxTone = ReadResult["status"] | "loading" | "warn" | "stale";

/**
 * Age policy, in trading sessions behind the last run. Thresholds follow the
 * three cases DIG-183 asks for, so there is no separate number to reconcile:
 *   0-1  ok     the run is still the one the next session owes
 *   2    warn   past one trading session
 *   3+   stale  past the point where the next session should have landed
 * Weekends do not count (see trading-calendar), so Monday morning does not warn
 * on Friday's run.
 */
const SESSION_WARN = 2;
const SESSION_STALE = 3;

/** The run date for this block, or null when the block has no run to age.
 *  The envelope `as_of` is the backend's run date wherever it threads one; the
 *  payload fallbacks cover the read-routes that carry the date in the body only. */
export function fxRunDate(result: ReadResult | null, data: unknown): string | null {
  const envelope = calendarDay(result?.asOf);
  if (envelope) return envelope;
  const row = rec(data);
  if (!row) return null;
  const direct = calendarDay(str(row.run_date));
  if (direct) return direct;
  const lastRun = rec(row.last_run);
  return lastRun ? calendarDay(str(lastRun.date)) : null;
}

/** Trading sessions this read is behind, or null when it cannot be aged. */
function fxAge(result: ReadResult, data: unknown, now: string): number | null {
  const runDate = fxRunDate(result, data);
  return runDate === null ? null : tradingSessionsSince(runDate, now);
}

export function fxTone(
  result: ReadResult | null,
  lines: string[],
  options: { now?: string; data?: unknown } = {},
): FxTone {
  if (!result) return "loading";
  if (result.status !== "ok") return result.status;
  const body = lines.filter((line) => !line.startsWith("source  ") && !line.startsWith("marks  "));
  if (body.length === 0 || body.every(isQuiet)) return "empty";
  const sessions = fxAge(result, options.data, options.now ?? todayYmd());
  if (sessions === null) return "ok";
  if (sessions >= SESSION_STALE) return "stale";
  if (sessions >= SESSION_WARN) return "warn";
  return "ok";
}

/** The age in words. The tone alone is a colour; the reader needs the count. */
function ageLabel(sessions: number): string {
  if (sessions === 0) return "current session";
  return sessions === 1 ? "1 trading day old" : `${sessions} trading days old`;
}

/** The state word a footer names, or "" when the pane is not aged past `ok`.
 *  The footer renders in MUTE, so this word is the only part of it that carries
 *  severity without relying on body ink. An aged pane therefore names its state;
 *  an `ok` pane does not, because "current session" already carries the claim. */
function ageStateWord(sessions: number): string {
  if (sessions >= SESSION_STALE) return "stale";
  if (sessions >= SESSION_WARN) return "warn";
  return "";
}

/** Pane footer: the as-of date, how far behind it is, and which state that is. */
export function fxPaneStatus(
  result: ReadResult | null,
  data: unknown,
  route: string,
  now: string = todayYmd(),
): string {
  const runDate = result ? fxRunDate(result, data) : null;
  if (runDate === null) return route;
  const sessions = tradingSessionsSince(runDate, now);
  if (sessions === null) return `as of ${runDate}`;
  // A run dated ahead of the clock is skew or a bad write, not proof of staleness,
  // so the tone stays as it is. But "current session" is a positive claim about
  // freshness, and this one cannot be supported: show the date and stop there.
  // Both ends are normalised YYYY-MM-DD, so the string compare is the date compare.
  const today = calendarDay(now);
  if (today !== null && runDate > today) return `as of ${runDate}`;
  const state = ageStateWord(sessions);
  return `as of ${runDate} · ${ageLabel(sessions)}${state ? ` · ${state}` : ""}`;
}

type Loaded = { result: ReadResult; data: unknown };

async function loadBlock(api: string, route: string, kind: BlockKind, signal?: AbortSignal): Promise<Loaded> {
  let res: Response;
  try {
    res = await fetch(`${api}${route}`, { signal });
  } catch {
    if (signal?.aborted) return { result: { status: "error", lines: [], asOf: null }, data: null };
    return { result: { status: "error", lines: [`${route}: the official API could not be reached.`], asOf: null }, data: null };
  }
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  const result = presentResponse(route, res.status, body, kind);
  const data =
    result.status === "error" || result.status === "stub" || !body || typeof body !== "object" || !("data" in body)
      ? null
      : (body as { data: unknown }).data;
  return { result, data };
}

/** Pane ink for a tone. Exported so the mapping is pinned: a stale pane must
 *  never render in the same ink as a healthy one, which is the whole defect. */
export function fxInk(status: FxTone): string {
  if (status === "ok") return INK;
  if (status === "empty" || status === "loading") return MUTE;
  // Amber reads as "behind, still usable". Red is reserved for a read that failed.
  if (status === "warn") return WARN;
  return DANGER;
}

function FxBlock({ id, api, focused }: { id: string; api: string; focused: boolean }) {
  const def = BLOCKS[id];
  const route = def?.route;
  const kind = def?.kind;
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    if (!route || !kind) return;
    const ac = new AbortController();
    let cancel = false;
    setLoaded(null);
    void loadBlock(api, route, kind, ac.signal).then((next) => {
      if (!cancel) setLoaded(next);
    });
    return () => {
      cancel = true;
      ac.abort();
    };
  }, [api, route, kind]);

  if (!def) return null;
  const lines = loaded ? fxBlockLines(def.id, loaded.result, loaded.data) : ["loading…"];
  const status = fxTone(loaded?.result ?? null, lines, { data: loaded?.data });
  return (
    <PaneFrame
      title={def.title}
      status={fxPaneStatus(loaded?.result ?? null, loaded?.data, def.route)}
      focused={focused}
      blocks={shapeLines(lines)}
      ink={fxInk(status)}
    />
  );
}

/** FX hub, ideas, watch, rates, and settings. One block per catalog route. */
export function FxDesk({ path, api = API }: { path: string; api?: string }) {
  if (!isFxPath(path)) return null;
  return <FxLayout path={path} api={api} />;
}

function FxLayout({ path, api }: { path: string; api: string }) {
  const layout = layoutFor(path);
  const [focus, setFocus] = useFocusedPane(layout.length, path);
  return (
    <box width="100%" height="100%" position="relative" overflow="hidden">
      {layout.map((placement, index) => (
        <box
          key={placement.id}
          position="absolute"
          left={share(placement.x - 1, COLS)}
          top={share(placement.y - 1, ROWS)}
          width={share(placement.w, COLS)}
          height={share(placement.h, ROWS)}
          onMouseDown={() => setFocus(index)}
        >
          <FxBlock id={placement.id} api={api} focused={index === focus} />
        </box>
      ))}
    </box>
  );
}
