/**
 * Shared thesis mapper for the core `theses` book.
 *
 * `theses` and `thesis_vehicles` are core tables and two routes read them —
 * /portfolio/theses and /rates/theses — so the mapping lives here once and both
 * routes return the same contract and the same counts.
 *
 * Join note: `theses.id` is a uuid and `thesis_vehicles.thesis_id` is the text
 * business key. The vehicles lookup is therefore keyed on `thesis_id`, never on
 * `id`. Keying it on `id` matched 0 of 3256 live rows and silently shipped
 * `vehicles: []` on every thesis.
 */

export type ThesisRow = Record<string, unknown>;

export interface Thesis {
  id: string;
  name: string;
  state: string;
  vehicles: string[];
  evidence: string | null;
  kill_condition: string | null;
  note: string | null;
}

export interface ThesisShape {
  theses: Thesis[];
  counts: { active: number; watch: number; exited: number };
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

const STATES = new Set(["active", "watch", "exited"]);

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
    const state = (str(r.state) ?? str(r.status) ?? "").toLowerCase();
    // `thesis_id` is the key thesis_vehicles joins on; `id` is the uuid and
    // never matches, so it is only a fallback for rows that predate thesis_id.
    const joinKey = str(r.thesis_id) ?? str(r.id) ?? "";
    return {
      id,
      name: str(r.name) ?? str(r.title) ?? id,
      state: STATES.has(state) ? state : state || "—",
      vehicles: byThesisId.get(joinKey) ?? [],
      evidence: str(r.evidence),
      kill_condition: str(r.kill_condition),
      note: str(r.note),
    };
  });
  return {
    theses,
    counts: {
      active: theses.filter((t) => t.state === "active").length,
      watch: theses.filter((t) => t.state === "watch").length,
      exited: theses.filter((t) => t.state === "exited").length,
    },
  };
}
