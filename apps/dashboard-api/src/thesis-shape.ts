/**
 * Shared thesis mapper for the core `theses` book.
 *
 * `theses` and `thesis_vehicles` are core tables and two routes read them —
 * /portfolio/theses and /rates/theses — so the mapping lives here once and both
 * routes return the same contract and the same counts.
 *
 * ## Column map (core `public.theses`)
 *
 * This mapper reads real columns only. The three it used to read —
 * `evidence`, `kill_condition`, `note` — do not exist on `theses`, so those three
 * cells were permanently `null` against every live row. They are wired to the
 * columns that do exist:
 *
 * | shape field  | reads                                          | migration |
 * | ------------ | ---------------------------------------------- | --------- |
 * | `evidence`   | `validation_criteria` jsonb                    | 025       |
 * | `kill_condition` | `invalidation_criteria` jsonb, else `invalidation` text | 025 / 001 |
 * | `note`       | `notes` text                                    | 001       |
 *
 * `confidence` numeric (025), `horizon`, `thesis_kind` and `topic_key` are real
 * columns with no representation in this shape; adding them is a contract
 * change for the three consumers, so they are left unmapped here.
 *
 * Join note: `theses.id` is a uuid and `thesis_vehicles.thesis_id` is the text
 * business key. The vehicles lookup is therefore keyed on `thesis_id`, never on
 * `id`. Keying it on `id` matched 0 of 3256 live rows and silently shipped
 * `vehicles: []` on every thesis.
 *
 * Date note: `theses` keeps one row per thesis per business `date`, and
 * `thesis_vehicles` is keyed `(date, thesis_id, ticker)` — so callers narrow both
 * sides to the tip with `maxThesisDate` + `rowsAtDate` before calling here.
 * `updated_at` exists (003) but is a row write timestamp and is never the as_of.
 */

export type ThesisRow = Record<string, unknown>;

/**
 * The status tokens `chk_theses_status` allows (002_schema_hardening.sql:37-40).
 * These are the only values `theses.status` can hold, so they are the only status
 * buckets that can ever be non-empty.
 */
export const THESIS_STATUSES = [
  "active",
  "monitoring",
  "challenged",
  "closed",
  "invalidated",
  "paused",
  "new",
] as const;

export type ThesisStatus = (typeof THESIS_STATUSES)[number];

const STATUS_LOOKUP = new Set<string>(THESIS_STATUSES);

export interface Thesis {
  id: string;
  name: string;
  state: string;
  vehicles: string[];
  evidence: string | null;
  kill_condition: string | null;
  note: string | null;
}

export interface ThesisCounts {
  /** `ACTIVE` only. */
  active: number;
  /** `MONITORING` + `CHALLENGED` — both are live theses under active management. */
  watch: number;
  /** `CLOSED` + `INVALIDATED` — both are off the book. */
  exited: number;
  /**
   * Every `chk_theses_status` token, plus `unknown` for a row whose `status` is
   * NULL or a value the constraint would reject. `by_status` is the honest
   * breakdown; `active`/`watch`/`exited` are rollups over it, so
   * `active + watch + exited + paused + new + unknown === theses.length`.
   */
  by_status: Record<ThesisStatus | "unknown", number>;
}

export interface ThesisShape {
  theses: Thesis[];
  counts: ThesisCounts;
}

function str(v: unknown): string | null {
  return typeof v === "string" && v.trim().length > 0 ? v.trim() : null;
}

/**
 * The thesis book's business date — one row per thesis per date, newest first
 * from the reader's `order=date.desc`. `date` is the field to age by; `updated_at`
 * is a write timestamp and says nothing about when the book was struck.
 */
export function maxThesisDate(rows: ThesisRow[]): string | null {
  let best: string | null = null;
  for (const r of rows) {
    const v = str(r.date);
    if (v && (best === null || v > best)) best = v;
  }
  return best;
}

/**
 * Rows at the newest business date only. The table keeps a row per thesis per
 * date, so an unfiltered read returns the same thesis on many dates and every
 * count in the envelope is inflated.
 */
export function rowsAtDate(rows: ThesisRow[], date: string | null): ThesisRow[] {
  if (date === null) return [];
  return rows.filter((r) => str(r.date) === date);
}

/** Keys a jsonb criteria object may carry its human text in, best first. */
const CRITERION_KEYS = [
  "condition",
  "criterion",
  "text",
  "statement",
  "label",
  "description",
  "reason",
  "value",
] as const;

function criterionText(item: unknown): string | null {
  const text = str(item);
  if (text) return text;
  if (typeof item === "number" || typeof item === "boolean") return String(item);
  if (item != null && typeof item === "object") {
    const rec = item as Record<string, unknown>;
    for (const key of CRITERION_KEYS) {
      const hit = str(rec[key]);
      if (hit) return hit;
    }
  }
  return null;
}

/**
 * Render a jsonb criteria column as one line of prose.
 *
 * `validation_criteria` and `invalidation_criteria` are jsonb arrays of objects
 * ("JSON array of observable conditions that keep/nullify the thesis", 025).
 * PostgREST returns them parsed, and these cells go into table rows, so they are
 * flattened here rather than shipped as raw JSON into a cell. An array element
 * with no recognisable text key is dropped rather than stringified — a cell of
 * `{"a":1}` reads as noise, not as evidence.
 *
 * A column that arrives as a JSON *string* (a text-path writer, or a proxy that
 * double-encoded it) is parsed and flattened the same way; if it does not parse,
 * it is shown as the text it is.
 */
function criteriaText(v: unknown): string | null {
  if (v == null) return null;
  if (typeof v === "string") {
    const head = v.trimStart()[0];
    if (head !== "[" && head !== "{") return str(v);
    try {
      return criteriaText(JSON.parse(v));
    } catch {
      return str(v);
    }
  }
  const items = Array.isArray(v) ? v : [v];
  const parts: string[] = [];
  for (const item of items) {
    const part = criterionText(item);
    if (part && !parts.includes(part)) parts.push(part);
  }
  return parts.length > 0 ? parts.join("; ") : null;
}

function emptyCounts(): Record<ThesisStatus | "unknown", number> {
  const out = { unknown: 0 } as Record<ThesisStatus | "unknown", number>;
  for (const status of THESIS_STATUSES) out[status] = 0;
  return out;
}

function countsFor(theses: Thesis[]): ThesisCounts {
  const by_status = emptyCounts();
  for (const t of theses) {
    const key: ThesisStatus | "unknown" = STATUS_LOOKUP.has(t.state)
      ? (t.state as ThesisStatus)
      : "unknown";
    by_status[key] += 1;
  }
  return {
    active: by_status.active,
    watch: by_status.monitoring + by_status.challenged,
    exited: by_status.closed + by_status.invalidated,
    by_status,
  };
}

export function thesisShape(rows: ThesisRow[], vehicles: ThesisRow[]): ThesisShape {
  const byThesisId = new Map<string, string[]>();
  for (const v of vehicles) {
    const id = str(v.thesis_id);
    const ticker = str(v.ticker) ?? str(v.vehicle);
    if (!id || !ticker) continue;
    byThesisId.set(id, [...(byThesisId.get(id) ?? []), ticker]);
  }
  const theses = rows.map((r): Thesis => {
    const id = str(r.id) ?? str(r.thesis_id) ?? "";
    // `status` is the constrained column; `state` is not a `theses` column and is
    // read only as a fallback for a pre-shaped row.
    const state = (str(r.status) ?? str(r.state) ?? "").toLowerCase();
    // `thesis_id` is the key thesis_vehicles joins on; `id` is the uuid and
    // never matches, so it is only a fallback for rows that predate thesis_id.
    const joinKey = str(r.thesis_id) ?? str(r.id) ?? "";
    return {
      id,
      name: str(r.name) ?? str(r.title) ?? id,
      // A NULL `status` is legal (the constraint allows NULL) and is shown as
      // "—"; a token the constraint would reject passes through rather than
      // being silently relabelled.
      state: state === "" ? "—" : state,
      vehicles: byThesisId.get(joinKey) ?? [],
      evidence: criteriaText(r.validation_criteria),
      kill_condition: criteriaText(r.invalidation_criteria) ?? str(r.invalidation),
      note: str(r.notes),
    };
  });
  return { theses, counts: countsFor(theses) };
}
