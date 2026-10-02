import type { StageName } from "@/lib/run-snapshot";
import {
  PIPELINE_ROUTE,
  isStubPayload,
  runFromDocuments,
  type OfficialFailure,
  type OfficialSuccess,
} from "@/lib/official-api";

/** A prose field the documents API actually returned. Empty when that field is missing. */
export interface StepTextField {
  key: string;
  text: string;
}

export interface StepDocumentView {
  documentKey: string;
  title: string | null;
  fields: StepTextField[];
}

export interface StepOutputRead {
  runDate: string | null;
  documents: StepDocumentView[];
  reason: string;
  /** True when there is no prose to show, so the panel paints an em dash. */
  missing: boolean;
}

type OfficialGet = (path: string, query?: Record<string, string>) => Promise<OfficialSuccess | OfficialFailure>;
type Matcher = (key: string) => boolean;

const exact = (want: string): Matcher => (key) => key.toLowerCase() === want;
const prefix = (head: string): Matcher => (key) => key.toLowerCase().startsWith(head);

const ASSET_CLASSES = new Set(["bonds", "commodities", "forex", "crypto", "equity", "international"]);

/** document_key → sub-step. Keys mirror the dashboard topology leaves and fan-out prefixes. */
const STEP_MATCH: Record<StageName, Record<string, Matcher>> = {
  Inputs: {
    "Preflight / market data": exact("inputs"),
    "Attention plan (shadow, conditional)": exact("attention-plan"),
  },
  Research: {
    "Alt-data": prefix("alt-"),
    Institutional: prefix("inst-"),
    Macro: exact("macro"),
    "Asset-classes": (key) => ASSET_CLASSES.has(key.toLowerCase()),
    Sectors: prefix("sector-"),
  },
  Synthesis: {
    "Consolidate bias": exact("bias-row"),
    "Daily digest": (key) => {
      const k = key.toLowerCase();
      return k === "digest" || k === "digest-delta";
    },
  },
  Selection: {
    "Thesis framing": prefix("thesis/"),
    Screener: (key) => {
      const k = key.toLowerCase();
      return k === "opportunity-screener" || k === "opportunity-screener.json";
    },
    Analysts: prefix("analyst/"),
    Deliberation: prefix("deliberation/"),
    "PM direction": exact("pm-direction-memo"),
    "Risk sizing": (key) => {
      const k = key.toLowerCase();
      return k === "pm-rebalance" || k === "risk-debate";
    },
  },
  Decision: {
    Commit: prefix("commit-run/"),
  },
  Learning: {
    "Beliefs fold": exact("beliefs"),
  },
};

const SKIP_KEYS = new Set([
  "doc_type",
  "date",
  "run_type",
  "segment",
  "document_key",
  "id",
  "phase",
  "category",
  "sector",
  "title",
  "workspace_id",
  "body",
]);

const SECRET = /eyJ[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{10,}/;
const STUB_TEXT = ["legacy_estimate", "99.909", "204.040", "204.04"];

const dayCache = new Map<string, unknown[]>();

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

export function stepIsMapped(stage: StageName, step: string): boolean {
  return STEP_MATCH[stage]?.[step] != null;
}

export function matchDocumentKey(stage: StageName, step: string, documentKey: string): boolean {
  return STEP_MATCH[stage]?.[step]?.(documentKey) ?? false;
}

function isStubText(text: string): boolean {
  return STUB_TEXT.some((marker) => text.includes(marker));
}

function skipKey(key: string): boolean {
  if (SKIP_KEYS.has(key)) return true;
  if (key.endsWith("_id") || key.endsWith("_digest")) return true;
  return /price|pnl|nav|weight|vix|sharpe|drawdown/i.test(key);
}

function scrub(text: string): string | null {
  const trimmed = text.trim();
  if (!trimmed || isStubText(trimmed)) return null;
  if (SECRET.test(trimmed) && trimmed.length < 160) return null;
  if (/^-?\d+(\.\d+)?%?$/.test(trimmed)) return null;
  return trimmed;
}

function textOf(value: unknown): string | null {
  if (typeof value === "string") return scrub(value);
  if (Array.isArray(value)) {
    const lines: string[] = [];
    for (const item of value) {
      if (typeof item === "string") {
        const line = scrub(item);
        if (line) lines.push(line);
        continue;
      }
      if (!isRecord(item)) continue;
      const bits = ["label", "headline", "text", "summary", "rationale", "notes"]
        .map((key) => (typeof item[key] === "string" ? scrub(item[key]) : null))
        .filter((bit): bit is string => bit != null);
      if (bits.length > 0) lines.push(bits.join(": "));
    }
    return lines.length > 0 ? lines.join("\n") : null;
  }
  if (isRecord(value)) {
    for (const key of ["markdown", "body", "text", "content"]) {
      if (typeof value[key] === "string") {
        const found = scrub(value[key]);
        if (found) return found;
      }
    }
  }
  return null;
}

function fieldsFromPayload(payload: unknown): StepTextField[] {
  if (typeof payload === "string") {
    const text = scrub(payload);
    return text ? [{ key: "payload", text }] : [];
  }
  if (!isRecord(payload)) return [];
  const body = textOf(payload.body);
  if (body) return [{ key: "body", text: body }];
  const fields: StepTextField[] = [];
  for (const [key, value] of Object.entries(payload)) {
    if (skipKey(key)) continue;
    const text = textOf(value);
    if (text) fields.push({ key, text });
  }
  return fields;
}

function fieldsFromRow(row: Record<string, unknown>): StepTextField[] | "stub" {
  if (isStubPayload(row)) return "stub";
  if (typeof row.content === "string" && row.content.trim()) {
    if (isStubText(row.content)) return "stub";
    const content = scrub(row.content);
    if (content) return [{ key: "content", text: content }];
  }
  if (isStubPayload(row.payload)) return "stub";
  const fields = fieldsFromPayload(row.payload);
  if (fields.some((field) => isStubText(field.text))) return "stub";
  return fields;
}

function titleOf(title: unknown): string | null {
  if (typeof title !== "string") return null;
  const trimmed = title.trim();
  if (!trimmed || isStubText(trimmed)) return null;
  return trimmed;
}

export interface StepDocumentRead {
  documents: StepDocumentView[];
  /** A matching row was a stub envelope and was not painted. */
  withheldStub: boolean;
}

/** Documents on `runDate` whose key belongs to this sub-step. No fabricated rows. */
export function documentsForStep(rows: unknown[], stage: StageName, step: string, runDate: string): StepDocumentRead {
  const documents: StepDocumentView[] = [];
  let withheldStub = false;
  for (const row of rows) {
    if (!isRecord(row) || typeof row.document_key !== "string" || row.date !== runDate) continue;
    if (!matchDocumentKey(stage, step, row.document_key)) continue;
    const fields = fieldsFromRow(row);
    if (fields === "stub") {
      withheldStub = true;
      continue;
    }
    documents.push({
      documentKey: row.document_key,
      title: titleOf(row.title),
      fields,
    });
  }
  documents.sort((a, b) => a.documentKey.localeCompare(b.documentKey));
  return { documents, withheldStub };
}

function emptyRead(runDate: string | null, reason: string): StepOutputRead {
  return { runDate, documents: [], reason, missing: true };
}

async function rowsForRun(
  get: OfficialGet,
  runDate: string,
  cache: Map<string, unknown[]>,
): Promise<{ ok: true; rows: unknown[] } | { ok: false; reason: string }> {
  const cached = cache.get(runDate);
  if (cached) return { ok: true, rows: cached };
  const read = await get(PIPELINE_ROUTE, {
    select: "document_key,title,date,content,payload",
    "eq.date": runDate,
    order: "document_key.asc",
    limit: "1000",
  });
  if (!read.ok) return { ok: false, reason: read.reason };
  const rows = Array.isArray(read.body) ? read.body : [];
  cache.set(runDate, rows);
  return { ok: true, rows };
}

/** Load the recorded run's documents for one sub-step. Failures stay empty. */
export async function loadStepOutput(
  get: OfficialGet,
  stage: StageName,
  step: string,
  runDate: string | null,
  cache: Map<string, unknown[]> = dayCache,
): Promise<StepOutputRead> {
  if (!stepIsMapped(stage, step)) {
    return emptyRead(runDate, `No document mapping for ${step}.`);
  }

  let date = runDate;
  if (!date) {
    const index = await get(PIPELINE_ROUTE, {
      select: "document_key,title,run_type,date",
      order: "date.desc",
      limit: "1000",
    });
    if (!index.ok) return emptyRead(null, index.reason);
    const rows = Array.isArray(index.body) ? index.body : [];
    date = runFromDocuments(rows)?.runDate ?? null;
    if (!date) return emptyRead(null, "The official API returned no documents for the latest run.");
  }

  const read = await rowsForRun(get, date, cache);
  if (!read.ok) return emptyRead(date, read.reason);

  const parsed = documentsForStep(read.rows, stage, step, date);
  const documents = parsed.documents;
  if (documents.length === 0) {
    return emptyRead(
      date,
      parsed.withheldStub
        ? "The official API returned a stub envelope, not a house-book read."
        : `No document for this step on the recorded run ${date}.`,
    );
  }

  const missing = documents.every((doc) => doc.fields.length === 0);
  return {
    runDate: date,
    documents,
    missing,
    reason: missing
      ? `Recorded run ${date}. The API returned this step's document with no text field.`
      : `Recorded run ${date}.`,
  };
}
