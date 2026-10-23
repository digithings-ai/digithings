"use client";

import type { ReadResult } from "digiquant-tui/read";
import { isRecord } from "@digithings/ui/lib/record";
import { BlockBoundary, KpiGrid, Sparkline, StateBlock, type KpiCell } from "@digithings/ui";

const ROUTE = "/kpis/live";

export type LiveMarksBlockProps = {
  /** The desk read for `/kpis/live`. `undefined` while the first fetch is in flight. */
  read?: ReadResult;
  /** The envelope's `data`, when the read is ok and carried one. */
  data?: unknown;
};

/** One figure that the payload did not carry, plus the reason it is missing. */
type Read = { value: string | null; note?: string; tone?: KpiCell["tone"] };

const ABSENT = "not in payload";
const NOT_AVAILABLE = "not available";

/** A signed percentage in two places. `null` stays `null` — never a zero the data did not hold. */
function signedPct(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function readPct(payload: Record<string, unknown>, key: string): Read {
  if (!(key in payload)) return { value: null, note: ABSENT };
  const raw = payload[key];
  if (raw === null || raw === undefined) return { value: null, note: NOT_AVAILABLE };
  if (typeof raw !== "number" || !Number.isFinite(raw)) {
    return { value: null, note: `not a number (${typeof raw})` };
  }
  const tone = raw > 0 ? "pos" : raw < 0 ? "neg" : undefined;
  return { value: signedPct(raw), tone };
}

function readOverlay(payload: Record<string, unknown>): Read {
  const key = "overlay_eligible";
  if (!(key in payload)) return { value: null, note: ABSENT };
  const raw = payload[key];
  if (raw === null || raw === undefined) return { value: null, note: NOT_AVAILABLE };
  if (typeof raw !== "boolean") return { value: null, note: `not a boolean (${typeof raw})` };
  return { value: raw ? "eligible" : "off" };
}

/** A live series, when a read ever carries one. Points that are not numbers are dropped, not zero-filled. */
function readSeries(payload: Record<string, unknown>): (number | null | undefined)[] | null {
  const raw = payload.series;
  if (!Array.isArray(raw)) return null;
  return raw.map((point) => {
    if (typeof point === "number") return Number.isFinite(point) ? point : null;
    if (isRecord(point) && typeof point.v === "number" && Number.isFinite(point.v)) return point.v;
    return null;
  });
}

function readUniverse(payload: Record<string, unknown>): string[] {
  const raw = payload.universe;
  if (!Array.isArray(raw)) return [];
  return raw.filter((name): name is string => typeof name === "string" && name.trim().length > 0);
}

function readQuoteDate(payload: Record<string, unknown>): string | null {
  const raw = payload.quote_date;
  return typeof raw === "string" && raw.trim() ? raw.trim() : null;
}

function MissingRead({ kind, title, reason }: {
  kind: "empty" | "loading" | "error" | "withheld";
  title: string;
  reason?: string;
}) {
  // No retry control: the desk's refresh is a page-level generation, not a
  // per-block callback, so a button here would have nothing honest to call.
  return <StateBlock kind={kind} title={title} reason={reason} />;
}

/**
 * The `/kpis/live` payload as a real block: the five live figures on hairlines,
 * a sparkline when the read carries a series, and the one line this read must
 * always say — live marks, never finalized accounting.
 *
 * Nothing is derived from a value the payload did not hold: an absent field is
 * `—` with its reason under it, a null is "not available", and a field of the
 * wrong type is named as such.
 */
function LiveMarksBody({ read, data }: LiveMarksBlockProps) {
  if (!read) {
    return <MissingRead kind="loading" title="Live marks" reason={`reading ${ROUTE}`} />;
  }
  if (read.status === "error") {
    return (
      <MissingRead
        kind="error"
        title="Live marks could not be read."
        reason={read.lines.join(" ") || `${ROUTE} failed without a message.`}
      />
    );
  }
  if (read.status === "stub") {
    return <MissingRead kind="withheld" title="Live marks withheld." reason={read.lines.join(" ")} />;
  }
  if (read.status === "empty") {
    return <MissingRead kind="empty" title="No live marks in this read." reason={read.lines.join(" ")} />;
  }
  if (!isRecord(data)) {
    return (
      <MissingRead
        kind="withheld"
        title="Live marks withheld."
        reason={`${ROUTE} returned ${data === null ? "no data object" : `a ${Array.isArray(data) ? "list" : typeof data}, not an object`}.`}
      />
    );
  }

  const liveVsMark = readPct(data, "live_vs_mark_pct");
  const day = readPct(data, "day_return_live_pct");
  const sinceInception = readPct(data, "since_inception_live_pct");
  const excess = readPct(data, "excess_live_pct");
  const overlay = readOverlay(data);
  const series = readSeries(data);
  const universe = readUniverse(data);
  const quoteDate = readQuoteDate(data);

  const items: KpiCell[] = [
    { label: "Live vs mark", value: liveVsMark.value, note: liveVsMark.note, tone: liveVsMark.tone },
    { label: "Day (live)", value: day.value, note: day.note, tone: day.tone },
    {
      label: "Since inception (live)",
      value: sinceInception.value,
      note: sinceInception.note,
      tone: sinceInception.tone,
    },
    { label: "Excess (live)", value: excess.value, note: excess.note, tone: excess.tone },
    { label: "Overlay", value: overlay.value, note: overlay.note },
  ];

  const footer = [
    "live marks",
    "not finalized accounting",
    quoteDate ? `quotes ${quoteDate}` : null,
    universe.length ? universe.join(" ") : null,
  ]
    .filter((part): part is string => part !== null)
    .join(" · ");

  return (
    <div className="flex flex-col gap-2">
      <KpiGrid items={items} missing="—" />
      {series ? (
        <div className="border-x border-b border-hair px-3 py-2">
          <Sparkline
            values={series}
            height={56}
            label={`live marks over ${series.length} points`}
            placeholder="live marks · no series in this read"
          />
        </div>
      ) : null}
      <p className="m-0 font-mono text-[0.72rem] leading-relaxed text-ink-mute">{footer}</p>
    </div>
  );
}

/** One block throwing on an odd payload must not take the desk down. */
export function LiveMarksBlock({ read, data }: LiveMarksBlockProps) {
  return (
    <BlockBoundary label={ROUTE}>
      <LiveMarksBody read={read} data={data} />
    </BlockBoundary>
  );
}
