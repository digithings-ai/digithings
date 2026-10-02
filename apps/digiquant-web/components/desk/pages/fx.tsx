"use client";

import { useEffect, useState } from "react";
import { BLOCKS, layoutFor } from "../../../../../clients/digiquant-tui/src/catalog";
import { DASH, EMPTY_READ, type ReadResult } from "../../../../../clients/digiquant-tui/src/read";
import { readOfficial } from "../read-block";

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

const tone: Record<ReadResult["status"] | "loading", string> = {
  ok: "text-ink",
  empty: "text-ink-mute",
  loading: "text-ink-mute",
  stub: "text-ink-soft",
  error: "text-ink-soft",
};

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

export function fxTone(result: ReadResult | null, lines: string[]): ReadResult["status"] | "loading" {
  if (!result) return "loading";
  if (result.status !== "ok") return result.status;
  const body = lines.filter((line) => !line.startsWith("source  ") && !line.startsWith("marks  "));
  return body.length > 0 && body.every(isQuiet) ? "empty" : "ok";
}

type Loaded = { result: ReadResult; data: unknown };

function FxBlock({ id }: { id: string }) {
  const def = BLOCKS[id];
  const route = def?.route;
  const kind = def?.kind;
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    if (!route || !kind) return;
    const ac = new AbortController();
    let cancel = false;
    setLoaded(null);
    void readOfficial(route, kind, ac.signal).then((next) => {
      if (!cancel) setLoaded(next);
    });
    return () => {
      cancel = true;
      ac.abort();
    };
  }, [route, kind]);

  if (!def) return null;
  const lines = loaded ? fxBlockLines(def.id, loaded.result, loaded.data) : ["loading…"];
  const status = fxTone(loaded?.result ?? null, lines);
  return (
    <section aria-label={def.title} className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden border border-hair bg-surface">
      <h2 className="m-0 shrink-0 border-b border-hair px-2 py-1 text-[0.65rem] font-normal text-ink-mute">{def.title}</h2>
      <p className={`m-0 min-h-0 flex-1 overflow-auto whitespace-pre-wrap px-2 py-1 text-[0.7rem] leading-[1.45] ${tone[status]}`}>
        {lines.slice(0, 14).join("\n")}
      </p>
      <p className="m-0 shrink-0 truncate border-t border-hair px-2 py-0.5 text-[0.6rem] text-ink-mute">
        {loaded?.result.asOf ? `as of ${loaded.result.asOf}` : def.route}
      </p>
    </section>
  );
}

/** FX hub, ideas, watch, rates, and settings. One block per catalog route. */
export function FxDesk({ path }: { path: string }) {
  if (!isFxPath(path)) return null;
  const layout = layoutFor(path);
  return (
    <div className="grid h-full min-h-0 grid-cols-12 grid-rows-12 gap-1 p-1">
      {layout.map((placement) => (
        <div
          key={placement.id}
          className="min-h-0 min-w-0"
          style={{ gridColumn: `${placement.x} / span ${placement.w}`, gridRow: `${placement.y} / span ${placement.h}` }}
        >
          <FxBlock id={placement.id} />
        </div>
      ))}
    </div>
  );
}
