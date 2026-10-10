import type { BlockKind } from "./catalog";
import { DASH, cell } from "./format";

export { DASH };
export const STUB_READ = "The official API returned a stub envelope, not a house-book read.";
export const EMPTY_READ = "This read returned no values.";

export type ReadResult = {
  status: "ok" | "empty" | "stub" | "error";
  lines: string[];
  asOf: string | null;
  /** The date the payload actually holds (`provenance.tip_date`, `data.book_as_of`). `asOf` is the book asked for. */
  dataAsOf?: string | null;
};

const scalar = (v: unknown, key = ""): string => (typeof v === "object" && v !== null ? DASH : cell(v, key));

const STUB_NAV_VALUES = [99.909, 204.04];
const STUB_NAV_TEXT = new Set(["99.909", "204.04", "204.040"]);

/** The worker double's NAV figures, as values. A longer number that only contains those digits is not the fixture. */
function isExactStubNav(value: unknown): boolean {
  if (typeof value === "number" && Number.isFinite(value)) {
    return STUB_NAV_VALUES.some((target) => Math.abs(value - target) < 1e-6);
  }
  return typeof value === "string" && STUB_NAV_TEXT.has(value);
}

function hasExactStubNav(value: unknown): boolean {
  if (isExactStubNav(value)) return true;
  if (Array.isArray(value)) return value.some(hasExactStubNav);
  if (value !== null && typeof value === "object") {
    return Object.values(value as Record<string, unknown>).some(hasExactStubNav);
  }
  return false;
}

/**
 * Secretless worker doubles, plus the fixture ledger (XLF TRIM / GLD OPEN).
 * Withhold the worker double only: NAV tip 99.909 and series tip 204.04, matched as values.
 * A longer number that merely contains those digits is a house figure.
 * `legacy_estimate` on an older point is a house label, not that fixture.
 */
export function isStubEnvelope(body: unknown): boolean {
  if (hasExactStubNav(body)) return true;
  const text = JSON.stringify(body ?? null);
  if (text.includes("103.040192") || text.includes("104.44808") || text.includes("3.040191838399986")) return true;
  if (text.includes('"close":500') && text.includes("2026-08-20") && text.includes('"close":515')) return true;
  const xlf = text.includes("XLF") && text.includes("2026-09-03") && text.includes("54.1");
  const gld = text.includes("GLD") && text.includes("2026-06-01") && text.includes("180");
  return xlf && gld;
}

export function isEmptyPayload(data: unknown): boolean {
  if (data == null) return true;
  if (Array.isArray(data)) return data.length === 0;
  if (typeof data !== "object") return false;
  const vals = Object.values(data as Record<string, unknown>);
  if (vals.length === 0) return true;
  return vals.every((v) => v == null || v === "" || (Array.isArray(v) && v.length === 0));
}

function rowLine(row: unknown): string {
  if (!row || typeof row !== "object" || Array.isArray(row)) return scalar(row);
  return Object.entries(row as Record<string, unknown>)
    .slice(0, 6)
    .map(([k, v]) => `${k} ${scalar(v, k)}`)
    .join("  ");
}

/** One level of fields. Nulls are an em dash. Arrays say when they have no rows. */
export function fieldLines(data: unknown, limit = 16): string[] {
  if (data == null || (typeof data === "object" && !Array.isArray(data) && Object.keys(data).length === 0)) {
    return [EMPTY_READ];
  }
  if (Array.isArray(data) && data.length === 0) return [EMPTY_READ];
  const lines: string[] = [];
  const push = (line: string) => {
    if (lines.length < limit) lines.push(line);
  };
  const walk = (value: unknown, prefix: string, key = "") => {
    if (lines.length >= limit) return;
    if (value == null || value === "") {
      push(`${prefix}${DASH}`);
      return;
    }
    if (typeof value !== "object") {
      push(`${prefix}${scalar(value, key)}`);
      return;
    }
    if (Array.isArray(value)) {
      if (value.length === 0) {
        push(`${prefix}no rows`);
        return;
      }
      const shown = value.slice(0, 6);
      shown.forEach((row, i) => push(`${prefix}${i + 1}. ${rowLine(row)}`));
      if (value.length > shown.length) push(`${prefix}… ${value.length - shown.length} more`);
      return;
    }
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      if (v && typeof v === "object") walk(v, `${prefix}${k}  `, k);
      else push(`${prefix}${k}  ${scalar(v, k)}`);
    }
  };
  walk(data, "");
  if (lines.length === 0) return [EMPTY_READ];
  return lines;
}

/** Pipeline graph as a node list. No canvas. */
export function graphLines(data: unknown): string[] {
  if (!data || typeof data !== "object") return ["No nodes in this read."];
  const d = data as { nodes?: unknown; run_date?: unknown; selected_node?: unknown };
  const nodes = Array.isArray(d.nodes) ? d.nodes : [];
  const lines = [`run  ${scalar(d.run_date)}`, `selected  ${scalar(d.selected_node)}`];
  if (nodes.length === 0) {
    lines.push("No nodes in this read.");
    return lines;
  }
  for (const n of nodes) {
    if (!n || typeof n !== "object") continue;
    const node = n as Record<string, unknown>;
    const to = Array.isArray(node.to) && node.to.length ? node.to.map((t) => String(t)).join(", ") : DASH;
    lines.push(`${scalar(node.label ?? node.id)}  ${scalar(node.stage)}  ${scalar(node.state)}  → ${to}`);
  }
  if (lines.length === 2) lines.push("No nodes in this read.");
  return lines;
}

function errorMessage(body: unknown): string {
  if (!body || typeof body !== "object") return "";
  const message = (body as { error?: { message?: unknown } }).error?.message;
  return typeof message === "string" ? message : "";
}

const text = (v: unknown): string | null => (typeof v === "string" && v ? v : null);

function provenance(body: unknown): { asOf: string | null; dataAsOf: string | null; head: string[] } {
  if (!body || typeof body !== "object") return { asOf: null, dataAsOf: null, head: [] };
  const env = body as {
    as_of?: unknown;
    data?: { book_as_of?: unknown; as_of?: unknown } | null;
    provenance?: { source?: unknown; marks?: unknown; tip_date?: unknown };
  };
  const asOf = text(env.as_of);
  const data = env.data && typeof env.data === "object" && !Array.isArray(env.data) ? env.data : null;
  const dataAsOf = text(env.provenance?.tip_date) ?? text(data?.book_as_of) ?? text(data?.as_of);
  const head: string[] = [];
  if (typeof env.provenance?.source === "string" && env.provenance.source) head.push(`source  ${env.provenance.source}`);
  if (typeof env.provenance?.marks === "string" && env.provenance.marks) head.push(`marks  ${env.provenance.marks}`);
  return { asOf, dataAsOf, head };
}

/** Paint one official response. Stub envelopes stay a sentence. The website uses this too. */
export function presentResponse(route: string, status: number, body: unknown, kind: BlockKind): ReadResult {
  if (status < 200 || status >= 300) {
    const message = errorMessage(body);
    const why = message ? `: ${message}` : "";
    return { status: "error", lines: [`${route} failed (${status})${why}`], asOf: null };
  }
  if (isStubEnvelope(body)) return { status: "stub", lines: [STUB_READ], asOf: null };
  if (!body || typeof body !== "object" || (body as { data?: unknown }).data == null) {
    return { status: "error", lines: [`${route} returned no data`], asOf: null };
  }
  const data = (body as { data: unknown }).data;
  const { asOf, dataAsOf, head } = provenance(body);
  const bodyLines = kind === "graph" ? graphLines(data) : fieldLines(data);
  const empty =
    kind === "graph"
      ? bodyLines[bodyLines.length - 1] === "No nodes in this read."
      : isEmptyPayload(data);
  return { status: empty ? "empty" : "ok", lines: [...head, ...bodyLines], asOf, dataAsOf };
}

export async function readBlock(api: string, route: string, kind: BlockKind, signal?: AbortSignal): Promise<ReadResult> {
  let res: Response;
  try {
    res = await fetch(`${api}${route}`, { signal });
  } catch {
    if (signal?.aborted) return { status: "error", lines: [], asOf: null };
    return { status: "error", lines: [`${route}: the official API could not be reached.`], asOf: null };
  }
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  return presentResponse(route, res.status, body, kind);
}
